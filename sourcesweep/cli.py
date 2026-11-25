"""Command line: `sourcesweep <command>`.

  sourcesweep run profiles/claudin-18-2 [--days 60] [--no-ai] [--no-track]
  sourcesweep due [--profiles profiles]      # run every profile whose cadence is up
  sourcesweep check | scan | show | render   # the low-level steps the Claude skill uses
"""
import argparse
import sys
from datetime import date
from pathlib import Path

from . import pipeline, scanner


def _run_profile(path, days, use_ai, track, abstracts):
    cfg, folder = pipeline.load_profile(path)
    out = folder / "reports" / date.today().isoformat()
    s = pipeline.run(cfg, out, days=days, use_ai=use_ai, history_dir=folder / "history" if track else None,
                     progress=lambda m: print(m, file=sys.stderr), abstracts=abstracts)
    print(f"{cfg['name']}: {s['total']} sources, {s['direct']} directly relevant, {s['context']} context -> {out / 'report.html'}")
    return s


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("run", "due"):
        return scanner.main(argv)
    ap = argparse.ArgumentParser(prog="sourcesweep")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="scan, screen, track changes and render one profile")
    r.add_argument("profile", help="profile folder (with profile.json) or a profile JSON file")
    r.add_argument("--days", type=int)
    d = sub.add_parser("due", help="run every profile whose cadence_days have passed")
    d.add_argument("--profiles", default="profiles")
    for p in (r, d):
        p.add_argument("--no-ai", action="store_true", help="keyword scores only, no Anthropic API calls")
        p.add_argument("--no-track", action="store_true", help="don't compare with or update the profile's history")
        p.add_argument("--no-abstracts", action="store_true", help="leave publisher abstracts out of report.html")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        _run_profile(a.profile, a.days, not a.no_ai, not a.no_track, not a.no_abstracts)
        return
    todo = pipeline.due(a.profiles)
    if not todo:
        print("No profiles are due.")
    for folder in todo:
        _run_profile(folder, None, not a.no_ai, not a.no_track, not a.no_abstracts)


if __name__ == "__main__":
    main()
