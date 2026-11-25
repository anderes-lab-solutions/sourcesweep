"""SourceSweep web app (Streamlit): saved profiles, their reports and history, and ad-hoc scans.

Run it from a folder that has a profiles/ directory:

    streamlit run app.py                         # this repo (example profile)
    # or, in your own repo, a one-line streamlit_app.py:
    from sourcesweep.webapp import main
    main(profiles_dir="profiles", title="Client scans")

Secrets / environment (all optional):
    ANTHROPIC_API_KEY      AI screening and the written briefing; visitors can paste their own key
    APP_PASSWORD           simple password gate for a hosted copy
    SOURCESWEEP_EMAIL      contact address NCBI and SEC ask API users to send

Copyright (C) 2026 Tegan Anderes / Anderes Lab Solutions. AGPL-3.0-only; see LICENSE and NOTICE.
Under AGPL section 13, a hosted copy must offer its users the source: keep the sidebar link.
"""
import base64
import hmac
import html
import io
import json
import os
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path

import streamlit as st

from . import __version__, pipeline, screen
from .scanner import REPO_URL

MAX_RUNS_PER_SESSION = 10
REPORT_FILES = ("report.html", "briefing.md", "sources.md", "sources.json", "screening.json")

LOGO = ('<svg aria-hidden="true" width="34" height="34" viewBox="0 0 26 26" fill="none" stroke="#1F4FD8" stroke-width="2" '
        'stroke-linecap="round"><path d="M11 11 L11 3.5 A7.5 7.5 0 0 1 17.5 7.25 Z" fill="#1F4FD8" fill-opacity=".25" stroke="none"></path>'
        '<circle cx="11" cy="11" r="7.5"></circle><path d="M11 11 L11 4.5"></path><circle cx="11" cy="11" r="1.2" fill="#1F4FD8" stroke="none">'
        '</circle><path d="M16.6 16.6 L23 23" stroke-width="2.6"></path></svg>')

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&display=swap');
.block-container{padding-top:4.5rem;max-width:1360px}
.ss-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px;overflow:visible}
.ss-head h1{font-family:'Space Grotesk',sans-serif;font-size:2rem;line-height:1.3;font-weight:600;letter-spacing:-.01em;margin:0;padding:0;color:#0F172A}
.ss-tag{color:#4B5563;font-size:.95rem}
.ss-label{text-transform:uppercase;letter-spacing:.08em;font-size:.72rem;color:#4B5563;margin:0 0 4px}
.ss-chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.ss-chips span{background:#EEF2FF;color:#3730A3;border-radius:999px;padding:2px 10px;font-size:.8rem}
.ss-muted{color:#4B5563;font-size:.85rem;margin:0}
.ss-ctx{color:#374151;font-size:.88rem;margin:4px 0 6px}
.ss-new{display:inline-block;background:#DBEAFE;color:#1E40AF;border-radius:6px;padding:0 6px;font-size:.75rem;margin-left:6px}
h3,h4{font-family:'Space Grotesk',sans-serif!important;letter-spacing:-.01em}
[data-testid="stMetric"]{border:1px solid #E5E7EB;border-radius:10px;padding:10px 14px;background:#fff}
[data-testid="stMetricValue"]{font-family:'Space Grotesk',sans-serif}
</style>
"""


# ------------------------------------------------------------------ helpers

def _secret(name, default=""):
    try:
        return st.secrets.get(name, default) or os.environ.get(name, default)
    except Exception:
        return os.environ.get(name, default)


def _chips(words):
    return "<div class='ss-chips'>" + "".join(f"<span>{html.escape(str(w))}</span>" for w in words) + "</div>"


def _when(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().strftime("%b %-d, %Y %-I:%M %p")
    except ValueError:
        return str(iso)


def _writable(path):
    try:
        path.mkdir(parents=True, exist_ok=True)
        return os.access(path, os.W_OK)
    except OSError:
        return False


def load_profiles(root):
    out = []
    for f in sorted(Path(root).glob("*/profile.json")):
        try:
            cfg = json.loads(f.read_text())
        except ValueError:
            continue
        cfg.setdefault("name", f.parent.name)
        out.append({"slug": f.parent.name, "cfg": cfg, "folder": f.parent})
    return out


def run_summary(run_dir):
    """Counts for a saved report folder, from run.json or, for skill-made reports, the other files."""
    run_dir = Path(run_dir)
    s = {"date": run_dir.name[:10], "path": run_dir, "total": None, "direct": None, "context": None, "ran_at": None}
    try:
        if (run_dir / "run.json").exists():
            r = json.loads((run_dir / "run.json").read_text())
            s.update(total=r.get("total"), direct=r.get("direct"), context=r.get("context"), ran_at=r.get("ran_at"))
        if (run_dir / "sources.json").exists():
            d = json.loads((run_dir / "sources.json").read_text())
            s["total"] = s["total"] or len(d.get("items", []))
            s["ran_at"] = s["ran_at"] or d.get("generated_at")
        if s["direct"] is None and (run_dir / "screening.json").exists():
            scr = json.loads((run_dir / "screening.json").read_text())
            s["direct"] = sum(1 for v in scr.values() if v.get("rel") == 3)
            s["context"] = sum(1 for v in scr.values() if v.get("rel") == 2)
    except (ValueError, OSError):
        pass
    return s


def runs_for(folder):
    rdir = Path(folder) / "reports"
    if not rdir.exists():
        return []
    return [run_summary(d) for d in sorted(rdir.iterdir(), reverse=True) if (d / "report.html").exists()]


def files_of(folder):
    folder = Path(folder)
    return {n: (folder / n).read_bytes() for n in REPORT_FILES if (folder / n).exists()}


def downloads(files, stem, key):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(f"{stem}/{name}", data)
    items = [("Report (HTML)", files["report.html"], f"{stem}_report.html", "text/html", "Opens in any browser. Print to PDF from there.")]
    if "sources.md" in files:
        items.append(("Source pack", files["sources.md"], f"{stem}_sources.md", "text/markdown",
                      "Every source with its ID and link, to ask an AI assistant follow-up questions."))
    if "briefing.md" in files:
        items.append(("Briefing (.md)", files["briefing.md"], f"{stem}_briefing.md", "text/markdown", None))
    items.append(("Everything (.zip)", buf.getvalue(), f"{stem}.zip", "application/zip", None))
    cols = st.columns(4)
    for i, (label, data, fname, mime, tip) in enumerate(items):
        cols[i].download_button(label, data, fname, mime, key=f"dl{key}{i}", width="stretch", help=tip)


def show_report(html_bytes, height=1400):
    """A data: URL gives the report its own opaque origin, apart from the app."""
    st.iframe("data:text/html;base64," + base64.b64encode(html_bytes).decode(), height=height)


def split(text):
    return [x.strip() for x in text.replace("\n", ",").split(",") if x.strip()]


def _run(cfg, out, days, use_ai, history_dir=None):
    st.session_state.runs += 1
    with st.status(f"Scanning {cfg.get('name')}…", expanded=True) as status:
        summary = pipeline.run(cfg, out, days=days, use_ai=use_ai, history_dir=history_dir, progress=status.write)
        status.update(label="Done", state="complete", expanded=False)
    return summary


# ------------------------------------------------------------------ sections

def _report_view():
    view = st.session_state.get("view")
    if not view:
        return False
    head, back = st.columns([5, 1])
    head.markdown(f"<p class='ss-label'>Report</p><h3 style='margin:0'>{html.escape(view['title'])}</h3>", unsafe_allow_html=True)
    if back.button("← Back", width="stretch"):
        st.session_state.view = None
        st.rerun()
    files = files_of(view["path"])
    if "report.html" not in files:
        st.error("This report folder has no report.html.")
        return True
    downloads(files, view["stem"], "view")
    show_report(files["report.html"])
    return True


def _profile_card(p, can_save, use_ai, key):
    cfg, runs = p["cfg"], runs_for(p["folder"])
    last = runs[0] if runs else None
    with st.container(border=True):
        st.markdown(f"#### {html.escape(cfg['name'])}", unsafe_allow_html=True)
        st.markdown(_chips(cfg.get("keywords", [])), unsafe_allow_html=True)
        if cfg.get("context"):
            ctx = cfg["context"]
            st.markdown(f"<p class='ss-ctx'>{html.escape(ctx[:230] + ('…' if len(ctx) > 230 else ''))}</p>", unsafe_allow_html=True)
        facts = [f"{cfg.get('days', 60)}-day lookback"]
        if cfg.get("cadence_days"):
            facts.append(f"scheduled every {cfg['cadence_days']} days")
        if cfg.get("restrict", {}).get("text"):
            facts.append(f"papers must mention “{cfg['restrict']['text']}”")
        if cfg.get("restrict", {}).get("condition"):
            facts.append(f"trials limited to {cfg['restrict']['condition']}")
        st.markdown(f"<p class='ss-muted'>{html.escape(' · '.join(facts))}</p>", unsafe_allow_html=True)
        if last:
            counts = f"{last['direct']} of {last['total']} sources directly relevant" if last["direct"] is not None else f"{last['total']} sources"
            st.markdown(f"<p class='ss-muted'>Latest scan {html.escape(_when(last['ran_at']) if last['ran_at'] else last['date'])} · "
                        f"{html.escape(counts)} · {len(runs)} report{'s' if len(runs) != 1 else ''}</p>", unsafe_allow_html=True)
        else:
            st.markdown("<p class='ss-muted'>Not scanned yet.</p>", unsafe_allow_html=True)
        b1, b2, b3 = st.columns(3)
        if last and b1.button("Open report", key=f"o{key}", type="primary", width="stretch"):
            st.session_state.view = {"path": last["path"], "title": f"{cfg['name']} · {last['date']}", "stem": f"{p['slug']}_{last['date']}"}
            st.rerun()
        run = b2.button("Run now", key=f"r{key}", width="stretch",
                        disabled=st.session_state.runs >= MAX_RUNS_PER_SESSION,
                        help="Runs a fresh scan with this profile." + ("" if can_save else " The result is shown here but not saved."))
        b3.download_button("profile.json", json.dumps(cfg, indent=2), f"{p['slug']}.json", "application/json",
                           key=f"d{key}", width="stretch")
        if run:
            folder = p["folder"]
            out = folder / "reports" / date.today().isoformat() if can_save else Path(tempfile.mkdtemp(prefix="scan_"))
            _run(dict(cfg, slug=p["slug"]), out, cfg.get("days"), use_ai, history_dir=folder / "history" if can_save else None)
            st.session_state.view = {"path": out, "title": f"{cfg['name']} · {date.today().isoformat()}", "stem": f"{p['slug']}_{date.today().isoformat()}"}
            st.rerun()


def _profiles_tab(root, use_ai):
    profiles = load_profiles(root)
    can_save = _writable(Path(root))
    all_runs = sorted(((p, r) for p in profiles for r in runs_for(p["folder"])), key=lambda x: str(x[1]["ran_at"] or x[1]["date"]), reverse=True)
    if all_runs:
        p, r = all_runs[0]
        with st.container(border=True):
            left, right = st.columns([3, 2], vertical_alignment="center")
            with left:
                st.markdown("<p class='ss-label'>Latest report</p>", unsafe_allow_html=True)
                st.markdown(f"### {html.escape(p['cfg']['name'])}", unsafe_allow_html=True)
                st.markdown(f"<p class='ss-muted'>Run {html.escape(_when(r['ran_at']) if r['ran_at'] else r['date'])}</p>", unsafe_allow_html=True)
                st.markdown(_chips(p["cfg"].get("keywords", [])), unsafe_allow_html=True)
            with right:
                m = st.columns(3)
                m[0].metric("Sources", r["total"] if r["total"] is not None else "–")
                m[1].metric("Directly relevant", r["direct"] if r["direct"] is not None else "–")
                m[2].metric("Context", r["context"] if r["context"] is not None else "–")
                if st.button("Open latest report", type="primary", width="stretch", key="hero"):
                    st.session_state.view = {"path": r["path"], "title": f"{p['cfg']['name']} · {r['date']}", "stem": f"{p['slug']}_{r['date']}"}
                    st.rerun()
    if not profiles:
        st.info(f"No profiles yet. Add a folder with a profile.json to `{root}`, or create one below.")
    cols = st.columns(2, gap="medium")
    for i, p in enumerate(profiles):
        with cols[i % 2]:
            _profile_card(p, can_save, use_ai, i)
    with st.expander("Add a profile"):
        _new_profile(root, can_save)


def _new_profile(root, can_save):
    st.caption("A profile is just your search keywords, plus an optional scope note. Nothing is added for you.")
    with st.form("newprofile", border=False):
        name = st.text_input("Name", placeholder="e.g. KRAS G12D landscape")
        kws = st.text_area("Search keywords (comma or line separated)", height=100,
                           help="Gene symbols, protein names, mechanisms, drug code names. Avoid single common words.")
        context = st.text_area("Reader and scope", height=90, placeholder="Who reads the report and what is in or out of scope.")
        c1, c2, c3, c4 = st.columns(4)
        days = c1.number_input("Lookback (days)", 7, 120, 60)
        cadence = c2.number_input("Schedule every (days, 0 = off)", 0, 120, 14)
        rtext = c3.text_input("Papers must mention")
        rcond = c4.text_input("Trials limited to")
        submitted = st.form_submit_button("Create profile", type="primary")
    if submitted:
        keywords = split(kws)
        if not (name and keywords):
            st.error("Add a name and at least one keyword.")
            return
        slug = "-".join("".join(ch if ch.isalnum() else " " for ch in name.lower()).split())[:60] or "profile"
        cfg = {"name": name, "keywords": keywords, "days": int(days), "context": context,
               "restrict": {k: v for k, v in (("text", rtext), ("condition", rcond)) if v}}
        if cadence:
            cfg["cadence_days"] = int(cadence)
        text = json.dumps(cfg, indent=2)
        if can_save and not (Path(root) / slug).exists():
            (Path(root) / slug).mkdir(parents=True)
            (Path(root) / slug / "profile.json").write_text(text)
            st.success(f"Saved to {root}/{slug}/profile.json. On a hosted app, saved files are temporary: "
                       "commit the file to your repo to keep it.")
        st.download_button("Download profile.json", text, f"{slug}.json", "application/json")
        st.code(text, language="json")


def _adhoc_tab(use_ai):
    left, right = st.columns([1, 2], gap="large")
    with left:
        name = st.text_input("Name", placeholder="e.g. KRAS G12D landscape", key="adhoc_name")
        kws = st.text_area("Search keywords", height=110, placeholder="KRAS G12D\nG12D inhibitor\npan-KRAS inhibitor", key="adhoc_kws")
        context = st.text_area("Reader and scope (steers relevance screening)", height=100, key="adhoc_ctx")
        c1, c2 = st.columns(2)
        rtext = c1.text_input("Papers must mention", key="adhoc_rt")
        rcond = c2.text_input("Trials limited to", key="adhoc_rc")
        days = st.slider("Look back (days)", 7, 120, 60, key="adhoc_days")
        go = st.button("Run scan", type="primary", width="stretch",
                       disabled=not split(kws) or st.session_state.runs >= MAX_RUNS_PER_SESSION)
        st.caption("Sources are public APIs and feeds, searched on a best-effort basis. Check cited sources before relying on a finding.")
    with right:
        if go:
            cfg = {"name": name or "Custom scan", "keywords": split(kws), "context": context,
                   "restrict": {k: v for k, v in (("text", rtext), ("condition", rcond)) if v}}
            out = Path(tempfile.mkdtemp(prefix="scan_"))
            summary = _run(cfg, out, days, use_ai)
            st.session_state.adhoc = {"files": files_of(out), "summary": summary, "stem": f"scan_{date.today().isoformat()}"}
        res = st.session_state.get("adhoc")
        if res:
            s = res["summary"]
            failed = {k: v for k, v in s["status"].items() if not str(v).startswith(("ok", "skipped"))}
            if failed:
                st.warning("Some sources failed: " + "; ".join(f"{k} ({v})" for k, v in failed.items()))
            m = st.columns(3)
            m[0].metric("Sources", s["total"])
            m[1].metric("Directly relevant", s["direct"])
            m[2].metric("Context", s["context"])
            downloads(res["files"], res["stem"], "adhoc")
            show_report(res["files"]["report.html"])
        else:
            st.info("Enter keywords and run a one-off scan. To keep a scan and re-run it, add a profile instead.")


def _history_tab(root):
    rows = [(p, r) for p in load_profiles(root) for r in runs_for(p["folder"])]
    if not rows:
        st.info("No saved reports yet. Scheduled GitHub runs (or `sourcesweep run profiles/<name>`) save them here.")
        return
    rows.sort(key=lambda x: str(x[1]["ran_at"] or x[1]["date"]), reverse=True)
    st.dataframe([{"Profile": p["cfg"]["name"], "Run": _when(r["ran_at"]) if r["ran_at"] else r["date"],
                   "Sources": r["total"], "Directly relevant": r["direct"], "Context": r["context"]} for p, r in rows],
                 hide_index=True, width="stretch")
    labels = [f"{p['cfg']['name']} · {r['date']}" for p, r in rows]
    pick = st.selectbox("Open a report", range(len(rows)), format_func=lambda i: labels[i])
    if st.button("Open", type="primary"):
        p, r = rows[pick]
        st.session_state.view = {"path": r["path"], "title": labels[pick], "stem": f"{p['slug']}_{r['date']}"}
        st.rerun()


# ------------------------------------------------------------------ app

def main(profiles_dir=None, title="SourceSweep™", subtitle="Cited competitive landscape scans for biotech"):
    st.set_page_config(page_title=title.replace("™", ""), page_icon="🔭", layout="wide")
    for key in ("ANTHROPIC_API_KEY", "SOURCESWEEP_EMAIL", "SOURCESWEEP_MODEL"):
        if _secret(key) and not os.environ.get(key):
            os.environ[key] = _secret(key)
    password = _secret("APP_PASSWORD")
    if password and not st.session_state.get("authed"):
        st.title(title)
        entered = st.text_input("Password", type="password")
        if entered and hmac.compare_digest(entered, password):
            st.session_state.authed = True
            st.rerun()
        elif entered:
            st.error("Incorrect password.")
        st.stop()
    st.session_state.setdefault("runs", 0)
    root = Path(profiles_dir or os.environ.get("SOURCESWEEP_PROFILES") or "profiles").resolve()

    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f"<div class='ss-head'>{LOGO}<h1>{html.escape(title)}</h1><span class='ss-tag'>{html.escape(subtitle)}</span></div>",
                unsafe_allow_html=True)

    with st.sidebar:
        st.subheader("AI screening")
        if not _secret("ANTHROPIC_API_KEY"):
            key_in = st.text_input("Anthropic API key", type="password",
                                   help="Used only in this session to screen sources and write the briefing. Not stored.")
            if key_in:
                os.environ["ANTHROPIC_API_KEY"] = key_in
        use_ai = st.toggle("Screen and write briefings with AI", value=screen.available(), disabled=not screen.available())
        st.caption("Without a key, sources get keyword scores and no written briefing." if not screen.available()
                   else f"Model: {screen.model()}")
        st.divider()
        st.caption(f"Runs this session: {st.session_state.runs} of {MAX_RUNS_PER_SESSION}")
        st.caption(f"[SourceSweep™ v{__version__}]({REPO_URL}) · built by Tegan Anderes / Anderes Lab Solutions.  \n"
                   "AGPL-3.0: the full source of this app is at that link.")

    if _report_view():
        return
    tab_p, tab_a, tab_h = st.tabs(["Profiles", "One-off scan", "History"])
    with tab_p:
        _profiles_tab(root, use_ai)
    with tab_a:
        _adhoc_tab(use_ai)
    with tab_h:
        _history_tab(root)
