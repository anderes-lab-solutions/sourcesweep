"""Data for the web app's profile overview, read from a profile's saved report folders. No network, no AI.

Every number here comes from files a run already saves: run.json, sources.json, screening.json and briefing.md.
Special runs (a run.json with a "kind", such as a year in review) are listed with the others but are not used
as the "latest" or "previous" scan, so routine comparisons stay like for like.
"""
import json
import re
from pathlib import Path

from .scanner import norm_date

KIND_LABEL = {"trial": "US trial", "eu_trial": "EU trial", "paper": "Paper", "preprint": "Preprint",
              "sec": "SEC filing", "press": "Trade press", "news": "News"}
TAG = {"trial": "Trial", "eu_trial": "Trial", "paper": "Paper", "preprint": "Preprint", "sec": "Filing",
       "press": "Press", "news": "News"}


def _json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def runs(folder):
    """Saved report folders, newest first, with what each holds."""
    rdir = Path(folder) / "reports"
    if not rdir.exists():
        return []
    out = []
    for d in sorted((p for p in rdir.iterdir() if p.is_dir()), reverse=True):
        if not (d / "report.html").exists():
            continue
        run = _json(d / "run.json") or {}
        src = _json(d / "sources.json") or {}
        out.append({"path": d, "date": d.name[:10], "name": d.name, "kind": run.get("kind"), "run": run,
                    "window": run.get("window") or src.get("window"), "ran_at": run.get("ran_at") or src.get("generated_at")})
    return out


def routine(rs):
    """Runs that are ordinary scans of the profile (not a year in review or other one-off)."""
    return [r for r in rs if not r["kind"]]


def load(run):
    """sources, screening and briefing for one run (missing pieces come back empty)."""
    d = run["path"]
    src = _json(d / "sources.json") or {}
    scr = _json(d / "screening.json") or {}
    brief = (d / "briefing.md").read_text() if (d / "briefing.md").exists() else ""
    return src.get("items", []), scr, src.get("status", {}), brief


def _key(item):
    return f"{item['kind']}:{item.get('id') or item.get('url')}"


def status_line(status):
    """('verified', n, total, []) or ('missing', ok, total, [failed source keys])."""
    failed = [k for k, v in status.items() if not str(v).startswith(("ok", "skipped"))]
    return ("verified" if not failed else "missing", len(status) - len(failed), len(status), failed)


def link_counts(items):
    """Counts from the per-source link check, or None for scans made before links were checked."""
    if not any("link" in i for i in items):
        return None
    return {k: sum(1 for i in items if i.get("link") == k) for k in ("ok", "broken", "unchecked")}


def figures(items, scr):
    rel = lambda n: sum(1 for i in items if scr.get(i["sid"], {}).get("rel") == n)
    return {"total": len(items), "direct": rel(3), "context": rel(2)}


def new_since(cur_items, cur_scr, prev_items):
    """Relevant sources (2-3) in the current run that the previous run did not have, newest first."""
    seen = {_key(i) for i in prev_items}
    new = [i for i in cur_items if _key(i) not in seen]
    rel = [i for i in new if cur_scr.get(i["sid"], {}).get("rel", 0) >= 2]
    rel.sort(key=lambda i: norm_date(i.get("date", "")) or "", reverse=True)
    return new, rel


def trial_changes(cur_items, prev_items, fields=("status", "phases", "enrollment", "primary_completion")):
    """Registry fields that changed between two runs, for trials in both."""
    prev = {_key(i): i for i in prev_items if i["kind"] in ("trial", "eu_trial")}
    out = []
    for i in cur_items:
        old = prev.get(_key(i))
        if not old:
            continue
        for f in fields:
            a, b = old.get(f), i.get(f)
            if f in i and a != b and not (a in (None, "", []) and b in (None, "", [])):
                out.append({"item": i, "field": f.replace("_", " "), "before": _fmt(a), "now": _fmt(b)})
    return out


def _fmt(v):
    if v in (None, "", []):
        return "—"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    s = str(v)
    return s.replace("_", " ").lower() if s.isupper() else s


def assets_table(brief):
    """The Key assets & companies table from a briefing: (header, rows), citations stripped."""
    lines = brief.splitlines()
    try:
        start = next(n for n, l in enumerate(lines) if re.match(r"^#{2,3}\s+key assets", l.strip(), re.I))
    except StopIteration:
        return [], []
    rows = []
    for l in lines[start + 1:]:
        t = l.strip()
        if t.startswith("#"):
            break
        if t.startswith("|"):
            cells = [c.strip() for c in t.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                rows.append(cells)
    if not rows:
        return [], []
    clean = lambda c: re.sub(r"\s*\[(?:S\d+\s*,?\s*)+\]", "", c).strip()
    return [clean(c) for c in rows[0]], [[clean(c) for c in r] for r in rows[1:]]


def mix(items, scr):
    """Per source type: total and counts by relevance, in a fixed order."""
    out = []
    for k, label in KIND_LABEL.items():
        rs = [i for i in items if i["kind"] == k]
        if rs:
            by = {n: sum(1 for i in rs if scr.get(i["sid"], {}).get("rel", 0) == n) for n in (3, 2, 1, 0)}
            out.append({"kind": k, "label": label, "total": len(rs), "by": by})
    return out
