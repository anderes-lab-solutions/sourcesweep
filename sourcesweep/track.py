"""Change tracking between scheduled runs of the same profile.

Each run saves a small snapshot in <profile>/history/: trial fields worth watching, and the IDs of
every source seen so far. The next run compares against it and lists what changed, citing the
current run's [S#] IDs. Only factual registry fields are compared; nothing here calls an AI.
"""
import json
from pathlib import Path

WATCHED = {  # field -> how it reads in the change table
    "status": "Status", "phases": "Phase", "enrollment": "Enrollment",
    "primary_completion": "Primary completion", "start": "Start", "endpoints": "Primary endpoints",
}
STOPPED = {"TERMINATED", "WITHDRAWN", "SUSPENDED"}


def _key(item):
    return f"{item['kind']}:{item.get('id') or item.get('url')}"


def _fields(item):
    return {f: item.get(f) for f in WATCHED if f in item}


def _fmt(v):
    if v is None or v == "" or v == []:
        return "—"
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)[:160]
    return str(v).replace("_", " ").lower() if str(v).isupper() else str(v)


def compare(items, history_dir, run_date):
    """Return (markdown section or '', summary dict) and save the new snapshot."""
    history_dir = Path(history_dir)
    snap_path, seen_path = history_dir / "trials.json", history_dir / "seen.json"
    prev = json.loads(snap_path.read_text()) if snap_path.exists() else None
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else None
    trials = [i for i in items if i["kind"] in ("trial", "eu_trial")]

    rows, summary = [], {"first_run": prev is None, "changed_trials": 0, "new_trials": 0, "new_sources": 0, "since": None}
    if prev is not None:
        summary["since"] = prev.get("_run_date")
        for it in trials:
            old = prev.get(_key(it))
            if old is None:
                summary["new_trials"] += 1
                rows.append((1, f"| [{it['sid']}] | {it['title'].replace('|', '/')[:90]} | New to the scan | — | {_fmt(it.get('status'))} |"))
                continue
            changed = False
            for f, label in WATCHED.items():
                a, b = old.get(f), it.get(f)
                if f in it and a != b and not (a in (None, "", []) and b in (None, "", [])):
                    changed = True
                    rank = 0 if f == "status" and str(b) in STOPPED else 2
                    rows.append((rank, f"| [{it['sid']}] | {it['title'].replace('|', '/')[:90]} | {label} | {_fmt(a)} | {_fmt(b)} |"))
            summary["changed_trials"] += changed
    if seen is not None:
        summary["new_sources"] = sum(1 for i in items if _key(i) not in seen)

    history_dir.mkdir(parents=True, exist_ok=True)
    snap = dict(prev or {})
    snap.update({_key(i): _fields(i) for i in trials})
    snap["_run_date"] = run_date
    snap_path.write_text(json.dumps(snap, indent=0, sort_keys=True))
    seen_path.write_text(json.dumps(sorted(set(seen or []) | {_key(i) for i in items})))

    if prev is None:
        return "", summary
    head = [f"## Changes since last scan ({summary['since']})",
            f"{summary['new_sources']} of {len(items)} sources are new since then. "
            f"{summary['changed_trials']} tracked trials changed and {summary['new_trials']} trials are new to the scan."]
    if rows:
        head += ["", "| Source | Trial | Field | Before | Now |", "|---|---|---|---|---|"]
        head += [r for _, r in sorted(rows, key=lambda x: x[0])][:80]
    return "\n".join(head), summary
