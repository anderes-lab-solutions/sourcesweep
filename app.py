"""SourceSweep web app (Streamlit).

    pip install -e ".[app]"
    streamlit run app.py

Optional secrets (.streamlit/secrets.toml locally, or your host's secrets settings):
    ANTHROPIC_API_KEY = "sk-ant-..."   # AI screening + briefing; visitors can also paste their own key
    APP_PASSWORD = "..."               # simple password gate for a hosted copy
    SOURCESWEEP_EMAIL = "you@example.com"   # contact address NCBI and SEC ask API users to send
"""
import base64
import hmac
import io
import json
import os
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import streamlit as st

from sourcesweep import __version__, pipeline, screen
from sourcesweep.scanner import REPO_URL

ROOT = Path(__file__).parent
PROFILES = ROOT / "profiles"
MAX_RUNS_PER_SESSION = 10

st.set_page_config(page_title="SourceSweep", page_icon="🔭", layout="wide")


def secret(name, default=""):
    try:
        return st.secrets.get(name, default) or os.environ.get(name, default)
    except Exception:  # no secrets file
        return os.environ.get(name, default)


for key in ("ANTHROPIC_API_KEY", "SOURCESWEEP_EMAIL", "SOURCESWEEP_MODEL"):
    if secret(key) and not os.environ.get(key):
        os.environ[key] = secret(key)

password = secret("APP_PASSWORD")
if password and not st.session_state.get("authed"):
    st.title("SourceSweep")
    entered = st.text_input("Password", type="password")
    if entered and hmac.compare_digest(entered, password):
        st.session_state.authed = True
        st.rerun()
    elif entered:
        st.error("Incorrect password.")
    st.stop()

st.session_state.setdefault("runs", 0)


def split(text):
    return [x.strip() for x in text.replace("\n", ",").split(",") if x.strip()]


def saved_profiles():
    out = {}
    for f in sorted(PROFILES.glob("*/profile.json")):
        try:
            out[f.parent.name] = json.loads(f.read_text())
        except ValueError:
            pass
    return out


def files_of(folder):
    return {f.name: f.read_bytes() for f in sorted(Path(folder).iterdir())
            if f.name in ("report.html", "briefing.md", "sources.md", "sources.json", "screening.json")}


def show_report(html_bytes):
    """Show the report in an iframe. A data: URL gives it its own opaque origin, apart from the app."""
    st.iframe("data:text/html;base64," + base64.b64encode(html_bytes).decode(), height=1500)


def downloads(files, stem, key):
    cols = st.columns(4)
    cols[0].download_button("Report (HTML)", files["report.html"], f"{stem}_report.html", "text/html", key=f"h{key}",
                            help="Opens in any browser. Print to PDF from there.")
    if "sources.md" in files:
        cols[1].download_button("Source pack (for AI)", files["sources.md"], f"{stem}_sources.md", "text/markdown", key=f"m{key}",
                                help="Every source with its ID, abstract and link. Give it to an AI assistant to ask follow-up questions.")
    if "briefing.md" in files:
        cols[2].download_button("Briefing (Markdown)", files["briefing.md"], f"{stem}_briefing.md", "text/markdown", key=f"b{key}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(f"{stem}/{name}", data)
    cols[3].download_button("Everything (zip)", buf.getvalue(), f"{stem}.zip", "application/zip", key=f"z{key}")


# ------------------------------------------------------------------ layout

st.title("🔭 SourceSweep™")
st.caption("Cited competitive landscape scans for biotech. Recent US and EU trials, PubMed papers, preprints, SEC filings, trade press and news for your keywords, "
           "screened for relevance into a cited report.")

with st.sidebar:
    st.subheader("AI screening")
    if not secret("ANTHROPIC_API_KEY"):
        key_in = st.text_input("Anthropic API key", type="password",
                               help="Used only for this session to screen sources and write the briefing. Not stored.")
        if key_in:
            os.environ["ANTHROPIC_API_KEY"] = key_in
    st.write("On" if screen.available() else "Off: keyword scores only")
    st.caption(f"Model: {screen.model()}. A 60-day scan typically takes 5 to 20 API calls.")
    st.divider()
    st.caption(f"v{__version__} · [Source and docs]({REPO_URL})  \nBuilt by Tegan Anderes / Anderes Lab Solutions. AGPL-3.0: this page's full source is at the link above.")

tab_run, tab_saved, tab_profile = st.tabs(["Run a scan", "Saved reports", "Profile file"])

with tab_run:
    left, right = st.columns([1, 2], gap="large")
    profiles = saved_profiles()
    with left:
        mode = st.radio("Keywords", ["Saved profile", "My own keywords"], horizontal=True,
                        index=0 if profiles else 1, disabled=not profiles)
        if mode == "Saved profile" and profiles:
            slug = st.selectbox("Profile", list(profiles), format_func=lambda s: profiles[s].get("name", s))
            cfg = dict(profiles[slug], slug=slug)
            st.write(" · ".join(f"`{k}`" for k in cfg.get("keywords", [])))
        else:
            name = st.text_input("Name", placeholder="e.g. KRAS G12D landscape")
            kws = st.text_area("Search keywords (comma or line separated)", height=110,
                               placeholder="KRAS G12D\nG12D inhibitor\npan-KRAS inhibitor",
                               help="Gene symbols, protein names, mechanisms, drug code names. Avoid single common words.")
            context = st.text_area("Reader and scope (steers relevance screening)", height=110,
                                   placeholder="Who reads this and what counts as in scope or off-topic.")
            c1, c2 = st.columns(2)
            restrict_text = c1.text_input("Papers must mention (optional)", placeholder="e.g. breast")
            restrict_cond = c2.text_input("Limit trials to condition (optional)", placeholder="e.g. breast cancer")
            cfg = {"name": name or "Custom scan", "keywords": split(kws), "context": context,
                   "restrict": {k: v for k, v in (("text", restrict_text), ("condition", restrict_cond)) if v}}
        days = st.slider("Look back (days)", 7, 120, int(cfg.get("days") or 60))
        use_ai = st.checkbox("AI screening and briefing", value=screen.available(), disabled=not screen.available())
        ready = bool(cfg.get("keywords"))
        run = st.button("Run scan", type="primary", use_container_width=True,
                        disabled=not ready or st.session_state.runs >= MAX_RUNS_PER_SESSION)
        if st.session_state.runs >= MAX_RUNS_PER_SESSION:
            st.caption("Run limit for this session reached. Reload the page to start a new session.")
        st.caption("Sources are public APIs and feeds, searched on a best-effort basis. Check the cited sources before relying on a finding.")

    with right:
        if run:
            st.session_state.runs += 1
            out = Path(tempfile.mkdtemp(prefix="scan_"))
            with st.status("Scanning…", expanded=True) as status:
                summary = pipeline.run(cfg, out, days=days, use_ai=use_ai, progress=status.write)
                status.update(label="Done", state="complete", expanded=False)
            stem = f"{cfg.get('slug') or 'scan'}_{date.today().isoformat()}"
            st.session_state.result = {"files": files_of(out), "summary": summary, "stem": stem}
        res = st.session_state.get("result")
        if res:
            s = res["summary"]
            failed = {k: v for k, v in s["status"].items() if not str(v).startswith(("ok", "skipped"))}
            if failed:
                st.warning("Some sources failed: " + "; ".join(f"{k} ({v})" for k, v in failed.items()))
            m = st.columns(4)
            m[0].metric("Sources", s["total"])
            m[1].metric("Directly relevant", s["direct"])
            m[2].metric("Context", s["context"])
            m[3].metric("AI calls", (s.get("ai") or {}).get("calls", 0))
            downloads(res["files"], res["stem"], "run")
            show_report(res["files"]["report.html"])
        else:
            st.info("Choose a profile or enter your own keywords, then run a scan.")

with tab_saved:
    runs = sorted((d for d in PROFILES.glob("*/reports/*") if (d / "report.html").exists()), reverse=True)
    if not runs:
        st.info("No saved reports yet. Scheduled GitHub runs (or `sourcesweep run profiles/<name>`) save them here.")
    else:
        pick = st.selectbox("Report", runs, format_func=lambda d: f"{d.parent.parent.name} · {d.name}")
        files = files_of(pick)
        downloads(files, f"{pick.parent.parent.name}_{pick.name}", "saved")
        show_report(files["report.html"])

with tab_profile:
    st.write("A profile is a folder in `profiles/` with a `profile.json`. Commit one to the repo to scan it on a schedule.")
    draft = {"name": cfg.get("name", ""), "keywords": cfg.get("keywords", []), "days": days, "cadence_days": 14,
             "context": cfg.get("context", ""), "restrict": cfg.get("restrict", {})}
    text = json.dumps(draft, indent=2)
    st.code(text, language="json")
    st.download_button("Download profile.json", text, "profile.json", "application/json")
