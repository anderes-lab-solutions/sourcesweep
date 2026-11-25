"""Offline tests on synthetic sources: no network, no API key needed.

    python -m pytest -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sourcesweep import pipeline, scanner, screen, track

ROOT = Path(__file__).resolve().parent.parent
CFG = {"name": "Test target", "slug": "test", "keywords": ["TGT1", "target one", "TGT1 inhibitor"],
       "context": "Reader follows TGT1 therapeutics.", "restrict": {}}


def trial(nct, title, status="RECRUITING", enrollment=40, **kw):
    return {"kind": "trial", "id": nct, "url": f"https://clinicaltrials.gov/study/{nct}", "title": title,
            "date": "2026-11-01", "venue": "Acme Bio", "abstract": "A study of a TGT1 inhibitor.", "status": status,
            "phases": ["PHASE1"], "enrollment": enrollment, "start": "2026-01", "primary_completion": "2027-06",
            "conditions": ["Solid tumor"], "interventions": ["DRUG: ACM-1"], "endpoints": ["DLTs"], **kw}


def items():
    return [
        trial("NCT00000001", "ACM-1, a TGT1 inhibitor, in solid tumors"),
        trial("NCT00000002", "Basket study in solid tumors"),
        {"kind": "paper", "id": "111", "url": "https://pubmed.ncbi.nlm.nih.gov/111/", "title": "Target one drives resistance",
         "date": "2026 Oct", "venue": "J Test", "abstract": "We show TGT1 ...", "authors": "Doe J et al."},
        {"kind": "news", "id": "n1", "url": "https://example.com/n1", "title": "Unrelated market news",
         "date": "2026-11-02", "venue": "Example", "abstract": ""},
    ]


def write_pack(out, its=None):
    its = its or items()
    for it in its:
        it["matched"] = scanner.matched(CFG, it)
    scanner.write(dict(CFG), its, {"trials": "ok (2)", "pubmed": "ok (1)", "news": "ok (1)"}, "2026-09-25", "2026-11-24", out)
    return json.loads((out / "sources.json").read_text())["items"]


def test_write_assigns_ids_and_files(tmp_path):
    its = write_pack(tmp_path)
    assert [i["sid"] for i in its] == ["S1", "S2", "S3", "S4"]
    for f in ("index.md", "sources.md", "sources.json"):
        assert (tmp_path / f).exists()
    assert "[S1]" in (tmp_path / "sources.md").read_text()


def test_keyword_screen_and_briefing_render(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    its = write_pack(tmp_path)
    scr = screen.screen(CFG, its, screen.Usage())
    assert scr["S1"]["rel"] == 2 and scr["S4"]["rel"] == 0 and scr["S1"]["by"] == "keyword"
    md = screen.briefing(CFG, its, scr, {"trials": "ok (2)"}, ["2026-09-25", "2026-11-24"])
    assert "No AI screening" in md and "| S1 | trial | 2 |" in md
    (tmp_path / "briefing.md").write_text(md)
    (tmp_path / "screening.json").write_text(json.dumps(scr))
    html = scanner.render(tmp_path).read_text()
    assert "sourcesweep" in html and "Test target" in html


def test_last_mention_filled_from_cited_sources(tmp_path):
    its = write_pack(tmp_path)
    md = ("# T\n\n## Key assets & companies\n| Asset | Company | Mechanism | Stage | What happened | Last mention |\n"
          "|---|---|---|---|---|---|\n| ACM-1 | Acme | TGT1 inhibitor | Phase 1 | Recruiting [S1, S3] | |\n")
    filled = scanner.fill_last_mention(md, its)
    assert "2026-11-01 [S1]" in filled


def test_no_abstracts_option(tmp_path):
    write_pack(tmp_path)
    assert "We show TGT1" in scanner.render(tmp_path).read_text()
    assert "We show TGT1" not in scanner.render(tmp_path, abstracts=False).read_text()


def test_unknown_citations_are_dropped():
    assert screen._strip_unknown_cites("Up [S1, S99] and [S98].", {"S1"}) == "Up [S1] and ."


def test_change_tracking(tmp_path):
    hist = tmp_path / "history"
    first = write_pack(tmp_path / "a")
    md, s = track.compare(first, hist, "2026-11-10")
    assert md == "" and s["first_run"]
    second = items()
    second[0]["status"] = "TERMINATED"
    second[1]["enrollment"] = 80
    second.append(trial("NCT00000003", "New TGT1 trial"))
    second = write_pack(tmp_path / "b", second)
    md, s = track.compare(second, hist, "2026-11-24")
    assert s["changed_trials"] == 2 and s["new_trials"] == 1 and s["new_sources"] == 1
    assert "## Changes since last scan (2026-11-10)" in md
    lines = [l for l in md.splitlines() if l.startswith("| [S")]
    assert "terminated" in lines[0].lower()  # stopped trials sort first, then new ones


def test_pipeline_run_offline(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def fake_scan(cfg, days, out, log=None):
        write_pack(Path(out))
        return {"out": str(out), "window": ["2026-09-25", "2026-11-24"], "status": {"trials": "ok (2)"}, "total": 4}

    monkeypatch.setattr(scanner, "scan", fake_scan)
    s = pipeline.run(dict(CFG), tmp_path / "out", days=60, history_dir=tmp_path / "hist", progress=lambda m: None)
    assert s["total"] == 4 and s["ai"] is None
    for f in ("report.html", "briefing.md", "screening.json", "run.json"):
        assert (tmp_path / "out" / f).exists()


def test_due_profiles(tmp_path):
    from datetime import date
    p = tmp_path / "a"; (p / "reports" / "2026-11-01").mkdir(parents=True)
    (p / "profile.json").write_text(json.dumps({"name": "A", "keywords": ["x"], "cadence_days": 14}))
    q = tmp_path / "b"; q.mkdir()
    (q / "profile.json").write_text(json.dumps({"name": "B", "keywords": ["y"]}))  # no cadence: never scheduled
    assert pipeline.due(tmp_path, date(2026, 11, 10)) == []
    assert pipeline.due(tmp_path, date(2026, 11, 15)) == [p]


def test_example_profile_loads():
    cfg, folder = pipeline.load_profile(ROOT / "profiles" / "claudin-18-2")
    assert cfg["keywords"] and cfg["slug"] == "claudin-18-2"


def test_skill_is_built_from_current_scanner():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "build_skill.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_webapp_summaries(tmp_path):
    pytest.importorskip("streamlit")
    from sourcesweep import webapp
    run = tmp_path / "p" / "reports" / "2026-11-24"; run.mkdir(parents=True)
    (run / "report.html").write_text("<html></html>")
    (run / "run.json").write_text(json.dumps({"total": 5, "direct": 2, "context": 1, "ran_at": "2026-11-24T10:00:00+00:00"}))
    (tmp_path / "p" / "profile.json").write_text(json.dumps({"name": "P", "keywords": ["x"]}))
    profiles = webapp.load_profiles(tmp_path)
    assert profiles[0]["slug"] == "p"
    s = webapp.runs_for(profiles[0]["folder"])[0]
    assert (s["total"], s["direct"], s["context"]) == (5, 2, 1)


def test_report_has_watermark(tmp_path):
    write_pack(tmp_path)
    html = scanner.render(tmp_path).read_text()
    assert "Made with <b>SourceSweep" in html and scanner.REPO_URL in html and "__REPO__" not in html


def test_screening_cache_and_quiet_run(tmp_path, monkeypatch):
    """Second run reuses AI scores for unchanged sources and skips the briefing when nothing new is relevant."""
    calls = {"screened": [], "briefings": 0}

    def fake_scan(cfg, days, out, log=None):
        write_pack(Path(out))
        return {"out": str(out), "window": ["2026-09-25", "2026-11-24"], "status": {"trials": "ok (2)"}, "total": 4}

    def fake_screen(cfg, its, usage, progress=None, use_ai=True):
        calls["screened"].append(len(its))
        return {i["sid"]: {"rel": 3 if "TGT1" in i["title"] or "Target one" in i["title"] else 0,
                           "note": "n", "by": "ai"} for i in its}

    def fake_narrative(*a, **k):
        calls["briefings"] += 1
        return "## State of the field\nText [S1]."

    monkeypatch.setattr(scanner, "scan", fake_scan)
    monkeypatch.setattr(screen, "available", lambda: True)
    monkeypatch.setattr(screen, "screen", fake_screen)
    monkeypatch.setattr(screen, "narrative", fake_narrative)
    run = lambda n, cfg=CFG: pipeline.run(dict(cfg), tmp_path / n, history_dir=tmp_path / "hist", progress=lambda m: None)

    first = run("r1")
    assert calls["screened"] == [4] and calls["briefings"] == 1 and first["screening_reused"] == 0
    second = run("r2")
    assert calls["screened"][-1] == 0 and second["screening_reused"] == 4
    assert second["briefing_skipped"] and calls["briefings"] == 1
    assert "No material changes" in (tmp_path / "r2" / "briefing.md").read_text()
    changed = run("r3", {**CFG, "context": "A different scope."})  # new scope: everything screened again
    assert calls["screened"][-1] == 4 and changed["screening_reused"] == 0
