"""One unattended run: scan, screen, compare with the last run, write the briefing, render the report."""
import hashlib
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
    ai = use_ai and screen.available()
    cache = load_cache(cfg, history_dir) if (history_dir and ai) else {}
    hits = {i["sid"]: cache[track._key(i)] for i in items
            if track._key(i) in cache and cache[track._key(i)]["h"] == content_hash(i)}
    if hits:
        progress(f"Reusing earlier screening for {len(hits)} of {len(items)} sources")
    scr = screen.screen(cfg, [i for i in items if i["sid"] not in hits], usage, progress=progress, use_ai=use_ai)
    scr.update({sid: {"rel": c["rel"], "note": c["note"], "by": "ai"} for sid, c in hits.items()})
    scr = {i["sid"]: scr[i["sid"]] for i in items}
    (out / "screening.json").write_text(json.dumps({k: {"rel": v["rel"], "note": v["note"]} for k, v in scr.items()}, indent=1))
    if history_dir and ai:
        save_cache(cfg, history_dir, items, scr)

    changes_md, change_summary = "", None
    if history_dir:
        changes_md, change_summary = track.compare(items, history_dir, date.today().isoformat())

    story, skipped = "", False
    if ai:
        new_relevant = [s for s, v in scr.items() if v["rel"] >= 2 and s not in hits]
        quiet = (change_summary and not change_summary["first_run"] and not new_relevant
                 and not change_summary["changed_trials"] and not change_summary["new_trials"])
        if quiet:
            skipped = True
            progress("No new relevant sources since the last scan: skipping the briefing")
            story = (f"## State of the field\nNo material changes since the last scan ({change_summary['since']}): "
                     "no new relevant sources and no trial changes. The previous report's briefing still stands; "
                     "the sources below are re-checked and current.")
        else:
            progress("Writing the briefing")
            story = screen.narrative(cfg, items, scr, usage, data["window"], changes_md)
    (out / "briefing.md").write_text(screen.briefing(cfg, items, scr, data["status"], data["window"], story, changes_md))
    scanner.render(out, hub=hub, title=f"{cfg.get('name')} scan {date.today().isoformat()}", abstracts=abstracts)

    summary.update(direct=sum(1 for v in scr.values() if v["rel"] == 3),
                   context=sum(1 for v in scr.values() if v["rel"] == 2),
                   ai=usage.as_dict() if usage.calls else None, changes=change_summary,
                   screening_reused=len(hits), briefing_skipped=skipped,
                   ran_at=data.get("generated_at"))
    (out / "run.json").write_text(json.dumps(summary, indent=1))
    return summary


# ------------------------------------------------------------------ screening cache
# Sources are always fetched fresh (it costs nothing). Only the AI relevance scores are reused, for a source
# whose text is unchanged and a profile whose keywords and scope are unchanged; anything else is screened again.

CACHE_FILE = "screening_cache.json"
_HASHED = ("title", "abstract", "status", "phases", "enrollment", "primary_completion", "endpoints", "conditions")


def _h(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def profile_hash(cfg):
    return _h([sorted(cfg.get("keywords", [])), cfg.get("context", ""), cfg.get("restrict", {})])


def content_hash(item):
    return _h([item.get(f) for f in _HASHED])


def load_cache(cfg, history_dir):
    f = Path(history_dir) / CACHE_FILE
    try:
        c = json.loads(f.read_text())
    except (OSError, ValueError):
        return {}
    return c.get("items", {}) if c.get("profile") == profile_hash(cfg) else {}


def save_cache(cfg, history_dir, items, scr):
    """Keep scores for every source screened by the AI under this profile (older entries are kept too)."""
    f = Path(history_dir) / CACHE_FILE
    old = load_cache(cfg, history_dir)
    old.update({track._key(i): {"h": content_hash(i), "rel": scr[i["sid"]]["rel"], "note": scr[i["sid"]]["note"]}
                for i in items if scr[i["sid"]].get("by") == "ai"})
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"profile": profile_hash(cfg), "items": old}, indent=0, sort_keys=True))


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
