"""One unattended run: scan, screen, compare with the last run, write the briefing, render the report."""
import json
from datetime import date
from pathlib import Path

from . import scanner, screen, track


def load_profile(path):
    """A profile is a folder with profile.json, or the JSON file itself."""
    path = Path(path)
    f = path / "profile.json" if path.is_dir() else path
    cfg = json.loads(f.read_text())
    cfg["keywords"] = scanner.normalize_keywords(cfg)
    cfg.setdefault("slug", f.parent.name if f.name == "profile.json" else f.stem)
    cfg.setdefault("name", cfg["slug"])
    return cfg, f.parent


def run(cfg, out, days=None, use_ai=True, history_dir=None, progress=print, hub="", abstracts=True):
    """Run everything and return a summary. `history_dir` turns on change tracking."""
    days = int(days or cfg.get("days") or 60)
    out = Path(out)
    progress(f"Searching sources for {len(cfg['keywords'])} keywords over {days} days")
    summary = scanner.scan(cfg, days, out, log=progress)
    data = json.loads((out / "sources.json").read_text())
    items = data["items"]

    usage = screen.Usage()
    scr = screen.screen(cfg, items, usage, progress=progress, use_ai=use_ai)
    (out / "screening.json").write_text(json.dumps({k: {"rel": v["rel"], "note": v["note"]} for k, v in scr.items()}, indent=1))

    changes_md, change_summary = "", None
    if history_dir:
        changes_md, change_summary = track.compare(items, history_dir, date.today().isoformat())

    story = ""
    if use_ai and screen.available():
        progress("Writing the briefing")
        story = screen.narrative(cfg, items, scr, usage, data["window"], changes_md)
    (out / "briefing.md").write_text(screen.briefing(cfg, items, scr, data["status"], data["window"], story, changes_md))
    scanner.render(out, hub=hub, title=f"{cfg.get('name')} scan {date.today().isoformat()}", abstracts=abstracts)

    summary.update(direct=sum(1 for v in scr.values() if v["rel"] == 3),
                   context=sum(1 for v in scr.values() if v["rel"] == 2),
                   ai=usage.as_dict() if usage.calls else None, changes=change_summary)
    (out / "run.json").write_text(json.dumps(summary, indent=1))
    return summary


def due(profiles_root, today=None):
    """Profiles whose cadence_days have passed since their last saved report."""
    today = today or date.today()
    out = []
    for f in sorted(Path(profiles_root).glob("*/profile.json")):
        cfg = json.loads(f.read_text())
        cadence = cfg.get("cadence_days")
        if not cadence:
            continue
        runs = sorted(d.name for d in (f.parent / "reports").glob("*") if d.is_dir())
        last = date.fromisoformat(runs[-1][:10]) if runs else None
        if last is None or (today - last).days >= int(cadence):
            out.append(f.parent)
    return out
