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

from . import __version__, overview, pipeline, screen
from .scanner import REPO_URL

MAX_RUNS_PER_SESSION = 10
EX = {  # grey example text in the profile forms; never saved into a profile
    "name": "e.g. KRAS G12D landscape",
    "keywords": "e.g. KRAS G12D, G12D inhibitor, pan-KRAS inhibitor, KRAS degrader",
    "context": "e.g. BD analyst at an oncology biotech tracking KRAS G12D: inhibitors and degraders, their trials and "
               "readouts, deals and company moves, and patient selection. Out of scope: other KRAS alleles unless compared.",
    "text": "e.g. pancreatic",
    "condition": "e.g. pancreatic cancer",
}
REPORT_FILES = ("report.html", "briefing.md", "sources.md", "sources.json", "screening.json")

LOGO = ('<svg aria-hidden="true" width="34" height="34" viewBox="0 0 26 26" fill="none" stroke="#1F4FD8" stroke-width="2" '
        'stroke-linecap="round"><path d="M11 11 L11 3.5 A7.5 7.5 0 0 1 17.5 7.25 Z" fill="#1F4FD8" fill-opacity=".25" stroke="none"></path>'
        '<circle cx="11" cy="11" r="7.5"></circle><path d="M11 11 L11 4.5"></path><circle cx="11" cy="11" r="1.2" fill="#1F4FD8" stroke="none">'
        '</circle><path d="M16.6 16.6 L23 23" stroke-width="2.6"></path></svg>')

LOGO_DARK = LOGO.replace("#1F4FD8", "#7DD3FC").replace('width="34" height="34"', 'width="28" height="28"')

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&display=swap');
.block-container{padding-top:4rem;max-width:1360px}
.ss-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.ss-head h1{font-family:'Space Grotesk',sans-serif;font-size:2rem;line-height:1.3;font-weight:600;margin:0;padding:0;color:#0F172A}
.ss-sub{color:#4B5563;font-size:.9rem;margin:0 0 4px}
.ss-crumb{color:#4B5563;font-size:.85rem;margin:0}
.ss-h1{font-family:'Space Grotesk',sans-serif!important;font-size:1.9rem!important;line-height:1.3!important;font-weight:600!important;letter-spacing:-.01em;margin:2px 0 4px!important;padding:0!important;color:#111827}
.ss-h3{font-family:'Space Grotesk',sans-serif!important;font-size:1.05rem!important;font-weight:600!important;margin:0 0 6px!important;padding:0!important}
.ss-label{text-transform:uppercase;letter-spacing:.08em;font-size:.72rem;color:#4B5563;margin:0 0 4px}
.ss-chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px;align-items:center}
.ss-chips span{background:#EEF2FF;color:#3730A3;border-radius:999px;padding:2px 10px;font-size:.8rem}
.ss-chips em{font-style:normal;color:#4B5563;font-size:.8rem;margin-left:4px}
.ss-muted{color:#4B5563;font-size:.85rem;margin:4px 0 0}
.ss-ctx{color:#374151;font-size:.88rem;margin:4px 0 6px}
.ss-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:6px 0 16px}
@media(max-width:900px){.ss-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
.ss-tile{background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:14px 18px}
.ss-tl{font-size:.78rem;color:#4B5563}.ss-tv{font-family:'Space Grotesk',sans-serif;font-size:1.9rem;font-weight:600;line-height:1.3}
.ss-tf{font-size:.78rem}.ss-tf a{color:#B91C1C}
.ss-pill{display:inline-block;font-size:.75rem;font-weight:600;border-radius:999px;padding:2px 9px;white-space:nowrap}
.ss-feed .ss-row{display:grid;grid-template-columns:110px minmax(0,1fr) 130px;gap:12px;padding:9px 0;border-top:1px solid #F1F5F9;font-size:.9rem;align-items:start}
.ss-feed a{color:#111827;text-decoration:none}.ss-feed a:hover{color:#1F4FD8;text-decoration:underline}
.ss-note{color:#4B5563;font-size:.8rem;margin-top:2px}.ss-when{color:#4B5563;font-size:.8rem;text-align:right}
.ss-scroll{overflow-x:auto}
.ss-table{width:100%;border-collapse:collapse;font-size:.88rem;min-width:520px}
.ss-table th{text-align:left;color:#4B5563;font-weight:500;font-size:.75rem;padding:6px 8px 6px 0;border-bottom:1px solid #E5E7EB}
.ss-table td{padding:9px 8px 9px 0;border-top:1px solid #F1F5F9;vertical-align:top}.ss-nw{white-space:nowrap;color:#4B5563}
.ss-mix{display:grid;grid-template-columns:92px minmax(0,1fr) 34px;gap:8px;align-items:center;font-size:.82rem;margin:6px 0}
.ss-bar{display:flex;height:8px;border-radius:4px;overflow:hidden;background:#F1F5F9}.ss-bar i{display:block;height:100%}
.ss-num{text-align:right;color:#4B5563}
.ss-key{font-size:.75rem;color:#4B5563;margin:8px 0 0}.ss-key i{display:inline-block;width:9px;height:9px;border-radius:2px;margin:0 4px 0 8px}
[data-testid="stMetric"]{border:1px solid #E5E7EB;border-radius:10px;padding:10px 14px;background:#fff}
.ss-table,.ss-table th,.ss-table td{border-left:0!important;border-right:0!important;background:transparent}
.ss-table{border:0!important}.ss-table th{white-space:nowrap;border-top:0!important}
p.ss-muted{font-size:.82rem!important;color:#4B5563!important}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.2rem}
section[data-testid="stSidebar"] [data-baseweb="input"] button{background:#1E293B!important}
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{color:#CBD5E1!important}
[class*="st-key-rr_"] button > div{justify-content:flex-start}
[class*="st-key-rr_"] button p{text-align:left}
p.ss-key{font-size:.75rem!important}
section[data-testid="stSidebar"] [data-testid="stTextInputRootElement"], section[data-testid="stSidebar"] [data-testid="stTextInputRootElement"] *{background:#1E293B!important}
/* dark sidebar */
section[data-testid="stSidebar"]{background:#0F172A}
section[data-testid="stSidebar"] *{color:#CBD5E1}
section[data-testid="stSidebar"] button{justify-content:flex-start;border-radius:8px;padding:6px 12px;min-height:38px}
section[data-testid="stSidebar"] button > div{justify-content:flex-start}
section[data-testid="stSidebar"] button:hover{background:#1E293B}
section[data-testid="stSidebar"] button:hover p{color:#fff}
section[data-testid="stSidebar"] [data-baseweb="input"],section[data-testid="stSidebar"] [data-baseweb="base-input"],section[data-testid="stSidebar"] input{background:#1E293B!important;border-color:#334155!important;color:#fff!important}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *{color:#94A3B8}
[data-testid="stSidebarCollapseButton"] *, [data-testid="stSidebarHeader"] *{color:#CBD5E1!important}
.ss-brand{display:flex;align-items:center;gap:10px;margin:-8px 0 18px}
.ss-brand small{display:block;font-size:.78rem;color:#94A3B8!important;margin-top:2px;line-height:1.3}
.ss-brand span{font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:1.35rem;color:#fff!important;letter-spacing:-.01em}
.ss-side-label{font-size:.68rem!important;line-height:1.4!important;letter-spacing:.08em;text-transform:uppercase;color:#94A3B8!important;margin:20px 0 8px 12px!important}
.ss-side-foot{margin-top:26px;border-top:1px solid #1E293B;padding-top:14px;display:flex;flex-direction:column;gap:6px;font-size:.82rem}
.ss-side-foot a{color:#7DD3FC!important;text-decoration:none}.ss-side-foot a:hover{text-decoration:underline}
.ss-side-foot p{color:#94A3B8!important;font-size:.75rem;margin:8px 0 0}
</style>
"""


# ------------------------------------------------------------------ helpers

def _secret(name, default=""):
    try:
        return st.secrets.get(name, default) or os.environ.get(name, default)
    except Exception:
        return os.environ.get(name, default)


def _chips(words, tail=""):
    return ("<div class='ss-chips'>" + "".join(f"<span>{html.escape(str(w))}</span>" for w in words)
            + (f"<em>{html.escape(tail)}</em>" if tail else "") + "</div>")


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


PILL = {"green": ("#DCFCE7", "#166534"), "blue": ("#E0F2FE", "#075985"), "grey": ("#F3F4F6", "#374151")}
TAGC = {"Trial update": ("#FEF3C7", "#92400E"), "Trial": ("#E0E7FF", "#3730A3"), "Paper": ("#DBEAFE", "#1E40AF"),
        "Preprint": ("#DBEAFE", "#1E40AF"), "Filing": ("#F3E8FF", "#6B21A8"), "Press": ("#DCFCE7", "#166534"),
        "News": ("#F3F4F6", "#374151")}
SRC_HOME = {"trials": ("US trials", "https://clinicaltrials.gov/"), "eu_trials": ("EU trials (CTIS)", "https://euclinicaltrials.eu/"),
            "pubmed": ("PubMed", "https://pubmed.ncbi.nlm.nih.gov/"), "preprints": ("Preprints", "https://europepmc.org/"),
            "sec": ("SEC filings", "https://www.sec.gov/edgar/search/"), "press": ("Trade press", "https://news.google.com/"),
            "news": ("News", "https://news.google.com/")}
e = html.escape


def _pill(text, colors):
    bg, fg = colors
    return f"<span class='ss-pill' style='background:{bg};color:{fg}'>{e(text)}</span>"


def _stage_colors(stage):
    s = stage.lower()
    if any(w in s for w in ("phase 3", "phase iii", "approved", "marketed", "priority", "registr", "bla", "nda")):
        return PILL["green"]
    if any(w in s for w in ("phase 2", "phase ii", "1/2", "1b/2")):
        return PILL["blue"]
    return PILL["grey"]


def _open(run, cfg, slug):
    st.session_state.view = {"path": run["path"], "title": f"{cfg['name']} · {run['name']}", "stem": f"{slug}_{run['name']}"}
    st.rerun()


def _tile(label, value, foot, foot_color="#4B5563", value_color="#111827"):
    return (f"<div class='ss-tile'><div class='ss-tl'>{e(label)}</div><div class='ss-tv' style='color:{value_color}'>{e(str(value))}</div>"
            f"<div class='ss-tf' style='color:{foot_color}'>{foot}</div></div>")


def _verified_tile(links, n, state, ok, total, failed_html):
    """Every source found is opened once during the scan; the 7 databases must all have answered too."""
    if links is None:
        return _tile("Databases searched", f"{ok} / {total}", "Source links not checked in this run" if state == "verified"
                     else f"Not reached: {failed_html}", foot_color="#4B5563" if state == "verified" else "#B91C1C")
    if state != "verified":
        foot, color = f"Not reached: {failed_html}", "#B91C1C"
    elif links["broken"]:
        foot, color = f"{links['broken']} broken link{'s' if links['broken'] != 1 else ''}: see the full report", "#B91C1C"
    else:
        foot = f"All {total} databases searched" + (f" · {links['unchecked']} not checkable" if links["unchecked"] else "")
        color = "#047857"
    return _tile("Sources verified", f"{links['ok']} / {n}", foot, foot_color=color)


def _overview(p, can_save, use_ai):
    cfg, slug = p["cfg"], p["slug"]
    rs = overview.runs(p["folder"])
    rout = overview.routine(rs)
    latest = rout[0] if rout else (rs[0] if rs else None)
    prev = rout[1] if len(rout) > 1 else None

    left, right = st.columns([3, 1.3], vertical_alignment="bottom")
    with left:
        st.markdown(f"<p class='ss-crumb'>Profiles / {e(cfg['name'])}</p><h1 class='ss-h1'>{e(cfg['name'])}</h1>", unsafe_allow_html=True)
        facts = [f"{cfg.get('days', 60)}-day window"]
        if cfg.get("cadence_days"):
            facts.append(f"runs every {cfg['cadence_days']} days")
        st.markdown(_chips(cfg.get("keywords", []), tail=" · ".join(facts)), unsafe_allow_html=True)
    with right:
        b1, b2 = st.columns(2)
        with b1.popover("Edit profile", width="stretch"):
            st.caption("Profiles live in your repo as profile.json. Change the file there, or download it, edit and commit it.")
            if cfg.get("context"):
                st.markdown(f"**Scope**  \n{cfg['context']}")
            st.download_button("profile.json", json.dumps(cfg, indent=2), f"{slug}.json", "application/json", width="stretch")
        run = b2.button("Run now", type="primary", width="stretch", key=f"run_{slug}",
                        disabled=st.session_state.runs >= MAX_RUNS_PER_SESSION,
                        help="Runs a fresh scan with this profile." + ("" if can_save else " The result is shown here but not saved."))
    if run:
        folder = p["folder"]
        out = folder / "reports" / date.today().isoformat() if can_save else Path(tempfile.mkdtemp(prefix="scan_"))
        _run(dict(cfg, slug=slug), out, cfg.get("days"), use_ai, history_dir=folder / "history" if can_save else None)
        st.session_state.view = {"path": out, "title": f"{cfg['name']} · {date.today().isoformat()}", "stem": f"{slug}_{date.today().isoformat()}"}
        st.rerun()

    if not latest:
        st.info("Not scanned yet. Press Run now, or let the scheduled GitHub run make the first report.")
        return
    items, scr, status, brief = overview.load(latest)
    fig = overview.figures(items, scr)
    new_all, new_rel, changes = [], [], []
    if prev:
        pitems, _, _, _ = overview.load(prev)
        new_all, new_rel = overview.new_since(items, scr, pitems)
        changes = overview.trial_changes(items, pitems)
    state, ok, total, failed = overview.status_line(status)
    w = latest["window"] or ["", ""]
    fmt = lambda d: datetime.fromisoformat(d).strftime("%b %-d") if d else ""
    failed_html = "; ".join(f"<a href='{SRC_HOME.get(k, (k, ''))[1]}' target='_blank'>{e(SRC_HOME.get(k, (k, ''))[0])} ↗</a>" for k in failed)
    tiles = [
        _tile("Sources screened", fig["total"], f"{e(fmt(w[0]))} – {e(fmt(w[1]))}"),
        _tile("Directly relevant", fig["direct"], f"{fig['context']} more as context"),
        _tile("New since last run", len(new_rel) if prev else "–",
              (f"{len(changes)} trial change{'s' if len(changes) != 1 else ''}" if prev else "First scan"), value_color="#1F4FD8"),
        _verified_tile(overview.link_counts(items), fig["total"], state, ok, total, failed_html),
    ]
    st.markdown("<div class='ss-tiles'>" + "".join(tiles) + "</div>", unsafe_allow_html=True)

    with st.container(border=True):
        h, link = st.columns([4, 1], vertical_alignment="center")
        h.markdown(f"<h3 class='ss-h3'>What changed{' since ' + e(fmt(prev['date'])) if prev else ''}</h3>", unsafe_allow_html=True)
        if link.button("Open full report →", key=f"full_{slug}", type="tertiary", width="stretch"):
            _open(latest, cfg, slug)
        if not prev:
            st.markdown("<p class='ss-muted'>This is the first routine scan for this profile. Changes show here after the next one.</p>", unsafe_allow_html=True)
        else:
            rows = []
            for c in changes[:4]:
                i = c["item"]
                rows.append((_pill("Trial update", TAGC["Trial update"]),
                             f"<a href='{e(i['url'])}' target='_blank'>{e(i['title'][:110])}</a>: {e(c['field'])} {e(c['before'])} → {e(c['now'])}",
                             f"{e(i['sid'])} · registry"))
            for i in new_rel[: 10 - len(rows)]:
                tag = overview.TAG.get(i["kind"], "Source")
                note = scr.get(i["sid"], {}).get("note") or ""
                rows.append((_pill(tag, TAGC.get(tag, PILL["grey"])),
                             f"<a href='{e(i['url'])}' target='_blank'>{e(i['title'][:110])}</a>" + (f"<div class='ss-note'>{e(note)}</div>" if note else ""),
                             f"{e(i['sid'])} · {e(str(i.get('date', '')))}"))
            if rows:
                st.markdown("<div class='ss-feed'>" + "".join(f"<div class='ss-row'><div>{a}</div><div>{b}</div><div class='ss-when'>{c}</div></div>" for a, b, c in rows)
                            + "</div>", unsafe_allow_html=True)
                more = len(new_rel) + len(changes) - len(rows)
                st.markdown(f"<p class='ss-muted'>{len(new_all)} new sources in all{f'; {more} more relevant changes in the full report' if more > 0 else ''}.</p>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<p class='ss-muted'>No new relevant sources or trial changes since {e(fmt(prev['date']))}.</p>", unsafe_allow_html=True)

    a, b = st.columns([2, 1], gap="medium")
    with a, st.container(border=True):
        st.markdown("<h3 class='ss-h3'>Key assets</h3>", unsafe_allow_html=True)
        head, body = overview.assets_table(brief)
        if body:
            want = [n for n, h_ in enumerate(head) if h_.lower() in ("asset", "company", "mechanism", "stage", "last mention")]
            ths = "".join(f"<th>{e(head[n])}</th>" for n in want)
            trs = ""
            for r in body[:12]:
                cells = []
                for n in want:
                    v = r[n] if n < len(r) else ""
                    name = head[n].lower()
                    if name == "stage" and v:
                        cells.append(f"<td>{_pill(v, _stage_colors(v))}</td>")
                    elif name == "last mention":
                        cells.append(f"<td class='ss-nw'>{e(v)}</td>")
                    elif name == "asset":
                        cells.append(f"<td><b>{e(v)}</b></td>")
                    else:
                        cells.append(f"<td>{e(v)}</td>")
                trs += "<tr>" + "".join(cells) + "</tr>"
            st.markdown(f"<div class='ss-scroll'><table class='ss-table'><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>", unsafe_allow_html=True)
            if len(body) > 12:
                st.markdown(f"<p class='ss-muted'>{len(body) - 12} more in the full report.</p>", unsafe_allow_html=True)
        else:
            st.markdown("<p class='ss-muted'>No key assets table in the latest briefing (it needs AI screening or a skill run).</p>", unsafe_allow_html=True)
    with b:
        with st.container(border=True):
            st.markdown("<h3 class='ss-h3'>Source mix</h3>", unsafe_allow_html=True)
            m = overview.mix(items, scr)
            top = max([x["total"] for x in m] or [1])
            bars = ""
            for x in m:
                segs = "".join(f"<i style='flex-grow:{x['by'][n]};background:{c}'></i>" for n, c in ((3, "#1F4FD8"), (2, "#93C5FD"), (1, "#CBD5E1"), (0, "#E5E7EB")) if x["by"][n])
                bars += (f"<div class='ss-mix'><span>{e(x['label'])}</span><div class='ss-bar' style='width:{x['total'] / top * 100:.0f}%'>{segs}</div>"
                         f"<span class='ss-num'>{x['total']}</span></div>")
            st.markdown(bars + "<p class='ss-key'><i style='background:#1F4FD8'></i>Direct <i style='background:#93C5FD'></i>Context "
                        "<i style='background:#CBD5E1'></i>Tangential</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h3 class='ss-h3'>Recent runs</h3>", unsafe_allow_html=True)
            for n, r in enumerate(rs[:6]):
                label = f"{fmt(r['date'])} · {(r['kind'] or ('scheduled' if r['run'] else 'Claude session')).split(',')[0]}"
                if st.button(label, key=f"rr_{slug}_{n}", type="tertiary", width="stretch", icon=":material/description:"):
                    _open(r, cfg, slug)


def _new_profile(root, can_save):
    st.caption("A profile is just your search keywords, plus an optional scope note. Nothing is added for you. "
               "The grey text in each field is only an example.")
    with st.form("newprofile", border=False):
        name = st.text_input("Name", placeholder=EX["name"])
        kws = st.text_area("Search keywords (comma or line separated)", height=100, placeholder=EX["keywords"],
                           help="Gene symbols, protein names, mechanisms, drug code names. Avoid single common words.")
        context = st.text_area("Reader and scope", height=100, placeholder=EX["context"])
        c1, c2, c3, c4 = st.columns(4)
        days = c1.number_input("Lookback (days)", 7, 120, 60)
        cadence = c2.number_input("Schedule every (days, 0 = off)", 0, 120, 14)
        rtext = c3.text_input("Papers must mention", placeholder=EX["text"], help="Optional. Every paper and preprint must contain this word.")
        rcond = c4.text_input("Trials limited to", placeholder=EX["condition"], help="Optional. Trials must list this condition.")
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
        name = st.text_input("Name", placeholder=EX["name"], key="adhoc_name")
        kws = st.text_area("Search keywords", height=110, placeholder=EX["keywords"], key="adhoc_kws")
        context = st.text_area("Reader and scope (steers relevance screening)", height=110, placeholder=EX["context"], key="adhoc_ctx")
        c1, c2 = st.columns(2)
        rtext = c1.text_input("Papers must mention", placeholder=EX["text"], key="adhoc_rt")
        rcond = c2.text_input("Trials limited to", placeholder=EX["condition"], key="adhoc_rc")
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

def _sidebar(profiles, title, subtitle=""):
    page = st.session_state.page
    active = page if page != "profile" else f"p_{st.session_state.profile}"
    st.markdown(f"<style>.st-key-nav_{active} button{{background:#1E293B!important}}.st-key-nav_{active} button p{{color:#fff!important;font-weight:600}}</style>",
                unsafe_allow_html=True)
    with st.sidebar:
        st.markdown(f"<div class='ss-brand'>{LOGO_DARK}<div><span>{html.escape(title.replace('™', ''))}</span>"
                    + (f"<small>{html.escape(subtitle)}</small>" if subtitle else "") + "</div></div>", unsafe_allow_html=True)
        for key, label, icon in (("profile_home", "Profiles", ":material/dashboard:"), ("adhoc", "One-off scan", ":material/search:"),
                                 ("history", "Run history", ":material/history:")):
            target = "profile" if key == "profile_home" else key
            k = key if key != "profile_home" else ("profile_home")
            if st.button(label, key=f"nav_{k}", type="tertiary", width="stretch", icon=icon):
                st.session_state.page, st.session_state.view = target, None
                st.rerun()
        st.markdown("<p class='ss-side-label'>Watchlist</p>", unsafe_allow_html=True)
        for p in profiles:
            if st.button(p["cfg"]["name"], key=f"nav_p_{p['slug']}", type="tertiary", width="stretch"):
                st.session_state.page, st.session_state.profile, st.session_state.view = "profile", p["slug"], None
                st.rerun()
        if st.button("New profile", key="nav_new", type="tertiary", width="stretch", icon=":material/add:"):
            st.session_state.page, st.session_state.view = "new", None
            st.rerun()
        st.markdown("<p class='ss-side-label'>AI screening</p>", unsafe_allow_html=True)
        if not _secret("ANTHROPIC_API_KEY"):
            key_in = st.text_input("Anthropic API key", type="password",
                                   help="Used only in this session to screen sources and write the briefing. Not stored.")
            if key_in:
                os.environ["ANTHROPIC_API_KEY"] = key_in
        use_ai = st.toggle("Screen and write briefings with AI", value=screen.available(), disabled=not screen.available())
        st.caption("Without a key, sources get keyword scores and no written briefing." if not screen.available()
                   else f"Model: {screen.model()} · runs this session: {st.session_state.runs} of {MAX_RUNS_PER_SESSION}")
        st.markdown(
            f"<div class='ss-side-foot'><a href='{REPO_URL}' target='_blank'>Source code on GitHub ↗</a>"
            f"<a href='{REPO_URL}/tree/main/docs' target='_blank'>Docs ↗</a>"
            f"<a href='{REPO_URL}/blob/main/CHANGELOG.md' target='_blank'>What's new ↗</a>"
            f"<a href='{REPO_URL}/issues' target='_blank'>Report an issue ↗</a>"
            f"<p>SourceSweep™ v{__version__} · open source (AGPL-3.0): the full source of this app is at the link above. "
            f"Built by Tegan Anderes / Anderes Lab Solutions.</p></div>", unsafe_allow_html=True)
    return use_ai


def main(profiles_dir=None, title="SourceSweep™", subtitle="Cited competitive landscape scans for biotech"):
    st.set_page_config(page_title=title.replace("™", ""), page_icon=str(Path(__file__).with_name("logo.png")), layout="wide")
    for key in ("ANTHROPIC_API_KEY", "SOURCESWEEP_EMAIL", "SOURCESWEEP_MODEL"):
        if _secret(key) and not os.environ.get(key):
            os.environ[key] = _secret(key)
    password = _secret("APP_PASSWORD")
    if password and not st.session_state.get("authed"):
        st.markdown(CSS, unsafe_allow_html=True)
        st.markdown(f"<div class='ss-head'>{LOGO}<h1>{html.escape(title)}</h1></div>", unsafe_allow_html=True)
        entered = st.text_input("Password", type="password")
        if entered and hmac.compare_digest(entered, password):
            st.session_state.authed = True
            st.rerun()
        elif entered:
            st.error("Incorrect password.")
        st.stop()
    st.session_state.setdefault("runs", 0)
    st.session_state.setdefault("page", "profile")
    root = Path(profiles_dir or os.environ.get("SOURCESWEEP_PROFILES") or "profiles").resolve()
    profiles = load_profiles(root)
    if "profile" not in st.session_state and profiles:
        latest = sorted(profiles, key=lambda p: max((str(r["ran_at"] or r["date"]) for r in runs_for(p["folder"])), default=""), reverse=True)
        st.session_state.profile = latest[0]["slug"]

    st.markdown(CSS, unsafe_allow_html=True)
    use_ai = _sidebar(profiles, title, subtitle)
    if _report_view():
        return
    page = st.session_state.page
    if page == "adhoc":
        st.markdown("<h1 class='ss-h1'>One-off scan</h1>", unsafe_allow_html=True)
        _adhoc_tab(use_ai)
    elif page == "history":
        st.markdown("<h1 class='ss-h1'>Run history</h1>", unsafe_allow_html=True)
        _history_tab(root)
    elif page == "new" or not profiles:
        st.markdown("<h1 class='ss-h1'>New profile</h1>", unsafe_allow_html=True)
        if not profiles:
            st.info(f"No profiles yet. Add a folder with a profile.json to `{root}`, or create one here.")
        _new_profile(root, _writable(root))
    else:
        p = next((x for x in profiles if x["slug"] == st.session_state.get("profile")), profiles[0])
        _overview(p, _writable(root), use_ai)
