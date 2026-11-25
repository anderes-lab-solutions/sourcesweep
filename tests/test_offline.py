"""Offline tests on synthetic sources: no network, no API key needed.

    python -m pytest -q
"""
import json
import re
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


def test_overview_from_saved_runs(tmp_path):
    from sourcesweep import overview
    prof = tmp_path / "prof"
    old_dir, new_dir = prof / "reports" / "2026-11-10", prof / "reports" / "2026-11-24"
    old_items = items()[:2]
    write_pack(old_dir, old_items)
    cur = items()
    cur[0]["status"] = "ACTIVE_NOT_RECRUITING"
    write_pack(new_dir, cur)
    scr = {"S1": {"rel": 3, "note": "n"}, "S2": {"rel": 2, "note": ""}, "S3": {"rel": 3, "note": "n"}, "S4": {"rel": 0, "note": ""}}
    for d in (old_dir, new_dir):
        (d / "screening.json").write_text(json.dumps(scr))
        (d / "briefing.md").write_text("## Key assets & companies\n| Asset | Company | Stage | Last mention |\n|---|---|---|---|\n"
                                       "| ACM-1 | Acme Bio | Phase 1 [S1] | 2026-11-01 [S1] |\n\n## Biology\n- x\n")
        (d / "report.html").write_text("<html></html>")
    special = prof / "reports" / "2026-11-25-year-review"
    write_pack(special); (special / "report.html").write_text("x"); (special / "run.json").write_text('{"kind": "year in review"}')

    rs = overview.runs(prof)
    assert [r["name"] for r in rs][0] == "2026-11-25-year-review" and len(overview.routine(rs)) == 2
    latest, prev = overview.routine(rs)
    li, ls, st_, brief = overview.load(latest)
    pi, _, _, _ = overview.load(prev)
    new, rel = overview.new_since(li, ls, pi)
    assert len(new) == 2 and [i["title"] for i in rel] == ["Target one drives resistance"]
    ch = overview.trial_changes(li, pi)
    assert ch and ch[0]["field"] == "status" and ch[0]["now"] == "active not recruiting"
    head, body = overview.assets_table(brief)
    assert head[0] == "Asset" and body == [["ACM-1", "Acme Bio", "Phase 1", "2026-11-01"]]
    assert overview.status_line({"a": "ok (2)", "b": "FAILED (x)"}) == ("missing", 1, 2, ["b"])
    assert overview.figures(li, ls) == {"total": 4, "direct": 2, "context": 1}
    assert [m["kind"] for m in overview.mix(li, ls)] == ["trial", "paper", "news"]


def test_link_check(tmp_path, monkeypatch):
    import urllib.error
    def fake_open(req, timeout=None):
        if "gone" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        if "blocked" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s, n=-1): return b"x"
        return R()
    monkeypatch.setattr(scanner.urllib.request, "urlopen", fake_open)
    its = [{"url": "https://a.org/ok"}, {"url": "https://a.org/gone"}, {"url": "https://a.org/blocked"}, {"url": "http://insecure"}]
    assert scanner.verify_links(its, {}) == {"ok": 1, "broken": 1, "unchecked": 2}
    pack = items()
    pack[0]["link"], pack[1]["link"] = "ok", "broken"
    for i in pack[2:]:
        i["link"] = "ok"
    write_pack(tmp_path, pack)
    html = scanner.render(tmp_path).read_text()
    assert '"l": "broken"' in html and "source links verified" in html
    from sourcesweep import overview
    assert overview.link_counts(json.loads((tmp_path / "sources.json").read_text())["items"]) == {"ok": 3, "broken": 1, "unchecked": 0}


def test_excerpt_keeps_keyword_sentences_and_conclusions():
    abstract = ("BACKGROUND: Ovarian cancer outcomes vary. " + "Filler sentence about methods. " * 60 +
                "\nRESULTS: KELIM was prognostic. CCNE1 amplifications, seen in 20% of patients, were linked to moderate chemo sensitivity."
                "\nCONCLUSION: HRD status and KELIM are independent biomarkers.")
    ex = screen.excerpt(abstract, ["CCNE1"], chars=600)
    assert "CCNE1 amplifications" in ex and "CONCLUSION" in ex and "Filler" not in ex


def test_commentary_linked_to_primary(tmp_path):
    pack = items()
    pack.append({"kind": "paper", "id": "222", "url": "https://pubmed.ncbi.nlm.nih.gov/222/", "title": "An unexpected role for TGT1",
                 "date": "2026 Oct", "venue": "J Test", "abstract": "In this issue of J Test, Doe et al. show TGT1 does X.",
                 "authors": "Roe R", "types": ["Comment"]})
    its = write_pack(tmp_path, pack)
    c = next(i for i in its if i["id"] == "222")
    primary = next(i for i in its if i["id"] == "111")
    assert c["commentary"] and c["comments_on"] == primary["sid"]
    assert f"Commentary or editorial on [{primary['sid']}]" in (tmp_path / "sources.md").read_text()


def test_briefing_lists_relevant_sources_not_cited(tmp_path):
    its = write_pack(tmp_path)
    scr = {i["sid"]: {"rel": 3 if n < 3 else 0, "note": "n", "by": "ai"} for n, i in enumerate(its)}
    md = screen.briefing(dict(CFG), its, scr, {"trials": "ok (2)"}, ["2026-09-25", "2026-11-24"], "## State of the field\nText [S1].")
    assert "## Relevant sources not cited above" in md and "- [S2]" in md and "- [S1]" not in md.split("not cited above")[1].split("## Screened")[0]


def test_citation_check_and_low_score_recheck(tmp_path, monkeypatch):
    its = write_pack(tmp_path)
    scr = {i["sid"]: {"rel": 3, "note": "n", "type": "observational", "limits": "n=12", "by": "ai"} for i in its}
    monkeypatch.setattr(screen, "call", lambda prompt, usage, max_tokens=0, system=None:
                        "## State of the field\nFixed text [S1].\n=== CHANGES ===\n- [S1] added the sample size")
    text, changes = screen.check_briefing("## State of the field\nDraft [S1].", its, scr, screen.Usage())
    assert text.startswith("## State of the field\nFixed") and changes == ["[S1] added the sample size"]
    monkeypatch.setattr(screen, "call", lambda *a, **k: "no usable output")
    text, changes = screen.check_briefing("## State of the field\nDraft [S1].", its, scr, screen.Usage())
    assert "Draft" in text and "draft kept" in changes[0]
    # first pass calls everything off-topic; the full-abstract recheck finds the keyword in S3's text
    seen = []
    def fake(prompt, usage, max_tokens=0, system=None):
        seen.append("whole abstract" in prompt)
        ids = re.findall(r"^\[(S\d+)\]", prompt, re.M)
        return json.dumps([{"id": s, "rel": (2 if seen[-1] else 0), "note": "x", "type": "review", "limits": ""} for s in ids])
    monkeypatch.setattr(screen, "call", fake)
    monkeypatch.setattr(screen, "available", lambda: True)
    out = screen.screen(dict(CFG), its, screen.Usage())
    assert seen == [False, True] and out["S3"]["rel"] == 2 and out["S4"]["rel"] == 0


def test_report_adds_not_cited_list_for_hand_written_briefings(tmp_path):
    its = write_pack(tmp_path)
    (tmp_path / "screening.json").write_text(json.dumps({i["sid"]: {"rel": 3, "note": "n"} for i in its}))
    (tmp_path / "briefing.md").write_text("# T\n\n## State of the field\nText [S1].\n\n## Screened sources\n| ID |\n")
    html = scanner.render(tmp_path).read_text()
    assert "Relevant sources not cited above" in html and "S4" in html.split("Relevant sources not cited above")[1][:4000]
