"""Relevance screening and the written briefing, using the Anthropic API.

This is what Claude does by hand when the scan runs as a skill. Here it runs unattended (app,
command line, scheduled GitHub runs) with your own API key. With no key, every source gets a
keyword score instead and the briefing has only the screened-sources table.

Outputs match the skill's: screening.json ({"S1": {"rel": 0-3, "note": "..."}}) and briefing.md.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5-5"
LABELS = {3: "Directly relevant", 2: "Relevant context", 1: "Tangential", 0: "Off-topic"}


def model():
    return os.environ.get("SOURCESWEEP_MODEL") or DEFAULT_MODEL


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


class Usage:
    """Running token count so each run can say what it used."""
    def __init__(self):
        self.calls = self.input = self.output = 0
        self.last_stop = None
        self.check = []

    def add(self, u):
        self.calls += 1
        self.input += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
        self.output += u.get("output_tokens", 0)

    def as_dict(self):
        return {"calls": self.calls, "input_tokens": self.input, "output_tokens": self.output, "model": model()}


def call(prompt, usage, max_tokens=4000, system=None):
    body = {"model": model(), "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
        "content-type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
            usage.add(data.get("usage", {}))
            usage.last_stop = data.get("stop_reason")
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(5 * (attempt + 1)); continue
            raise RuntimeError(f"Anthropic API error {e.code}: {e.read()[:300]!r}") from None


def _json(text, opener):
    closer = "]" if opener == "[" else "}"
    a, b = text.find(opener), text.rfind(closer)
    try:
        return json.loads(text[a:b + 1])
    except ValueError:
        return None


# ------------------------------------------------------------------ item text

SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
SECTION = re.compile(r"^\s*(RESULTS?|CONCLUSIONS?|FINDINGS|INTERPRETATION|SIGNIFICANCE)\s*:", re.I)


def excerpt(text, keywords=(), chars=1200):
    """The parts of an abstract that matter for screening: sentences naming a keyword, plus the results and
    conclusions, in their original order. Short abstracts come back whole."""
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if len(text) <= chars:
        return text
    kws = [k.lower() for k in keywords]
    keep, in_tail = [], False
    for para in text.split("\n"):
        if SECTION.match(para):
            in_tail = bool(re.match(r"^\s*(RESULTS?|CONCLUSIONS?|FINDINGS|INTERPRETATION)", para, re.I))
        for sent in SENT.split(para):
            if in_tail or any(k in sent.lower() for k in kws):
                keep.append(sent.strip())
    if not keep:
        sents = SENT.split(text.replace("\n", " "))
        keep = sents[:2] + sents[-2:]
    out = " … ".join(dict.fromkeys(keep))
    return out if len(out) <= chars else out[:chars - 1] + "…"


def describe(item, chars=600, keywords=()):
    head = ""
    if item["kind"] == "trial":
        head = (f"{', '.join(item.get('phases') or []) or 'phase n/a'} · {item.get('status', '')} · n={item.get('enrollment') or '?'} · "
                f"conditions: {'; '.join(item.get('conditions', [])[:6])} · interventions: {'; '.join(item.get('interventions', [])[:6])} · ")
    extra = ""
    if item.get("commentary"):
        extra = f" [COMMENTARY{' on ' + item['comments_on'] if item.get('comments_on') else ''}]"
    body = excerpt(item.get("abstract", ""), keywords, max(200, chars - len(head)))
    return f"[{item['sid']}] ({item['kind']}, {item.get('date', '')}){extra} {item['title']} | {item.get('venue', '')} · {head}{body}"


def keyword_rel(item, keywords):
    kws = [k.lower() for k in keywords]
    if any(k in item["title"].lower() for k in kws):
        return 2
    return 1 if item.get("matched") else 0


# ------------------------------------------------------------------ screening

def screen(cfg, items, usage, progress=None, use_ai=True, batch_size=40, max_items=600):
    """Return {sid: {"rel": int, "note": str, "by": "ai"|"keyword"}} for every item."""
    scr = {i["sid"]: {"rel": keyword_rel(i, cfg["keywords"]), "note": "", "by": "keyword"} for i in items}
    if not (use_ai and available()):
        return scr
    todo = items[:max_items]
    batches = [todo[i:i + batch_size] for i in range(0, len(todo), batch_size)]
    for n, batch in enumerate(batches, 1):
        if progress:
            progress(f"Screening relevance ({n}/{len(batches)})")
        _screen_batch(cfg, batch, scr, usage, chars=1200)
    # Safety net: a source the first pass called tangential or off-topic, but whose text names a keyword,
    # is screened again with its whole abstract, so a finding buried in the conclusions is not missed.
    kws = [k.lower() for k in cfg["keywords"]]
    again = [i for i in todo if scr[i["sid"]]["rel"] <= 1 and any(k in (i.get("abstract") or "").lower() for k in kws)][:250]
    for n in range(0, len(again), 15):
        if progress:
            progress(f"Re-checking low scores with full abstracts ({n // 15 + 1}/{(len(again) + 14) // 15})")
        _screen_batch(cfg, again[n:n + 15], scr, usage, chars=6000, recheck=True)
    return scr


def _screen_batch(cfg, batch, scr, usage, chars, recheck=False):
    listing = "\n".join(describe(i, chars, cfg["keywords"]) for i in batch)
    prompt = f"""You are screening sources for a competitive landscape scan.

READER AND SCOPE:
{cfg.get('context') or 'Not given: judge relevance to the search keywords.'}

SEARCH KEYWORDS: {', '.join(cfg['keywords'])}

Score every source for this reader:
3 = directly relevant: about the keywords' subject, its assets or competitors in scope
2 = relevant context: mechanism, indication, method or an adjacent competitor
1 = tangential: mentions a keyword in passing
0 = off-topic
Judge by the findings and conclusions, not only the title: a source whose results or conclusions report something
about a keyword is at least 2, even if its main topic is something else.{" These sources scored low on a first pass that saw only part of the text; you now see the whole abstract." if recheck else ""}

For sources scored 2 or 3 also give:
- note: one sentence, at most 20 words, on what the source adds.
- type: one of clinical trial, observational, preclinical, review, commentary, company statement, registry record, news.
- limits: at most 30 words, the qualifiers the source itself states that limit its main finding: e.g. significant
  only in a subgroup, a non-significant endpoint, small sample (give n), a definition or cutoff used, model system,
  early or interim data. "" if none are stated.
Use only facts in the text given. Never invent results, numbers or drug facts.

Reply with only a JSON array, one object per source:
[{{"id": "S1", "rel": 2, "note": "...", "type": "observational", "limits": "..."}}]

SOURCES:
{listing}"""
    res = _json(call(prompt, usage, max_tokens=12000), "[") or []
    for r in res:
        sid = str(r.get("id", ""))
        if sid in scr:
            try:
                scr[sid] = {"rel": max(0, min(3, int(r.get("rel")))), "note": str(r.get("note") or "")[:300], "by": "ai",
                            "type": str(r.get("type") or "")[:40], "limits": str(r.get("limits") or "")[:300]}
            except (TypeError, ValueError):
                pass


# ------------------------------------------------------------------ briefing

def _strip_unknown_cites(text, known):
    def fix(m):
        ids = [x.strip() for x in m.group(1).split(",")]
        keep = [x for x in ids if x in known]
        return f"[{', '.join(keep)}]" if keep else ""
    return re.sub(r"\[((?:S\d+\s*,?\s*)+)\]", fix, text)


WRITING_RULES = """Rules, all of them:
- Use ONLY the sources below. Cite every claim with source IDs like [S3] or [S3, S8]. Never add facts, numbers,
  dates or names that are not in the sources. If the evidence on a point is thin, say so.
- Report what the sources say and attribute it ("the registry lists...", "the company reported..."). No
  interpretation of your own, no predictions, no ranking of assets, no recommendations: the reader decides.
- Keep each finding's qualifiers (see LIMITS): a subgroup-only result, a non-significant endpoint, a small sample,
  the definition or cutoff used. Leave a finding out rather than state it without the qualifier that changes it.
- Say what kind of evidence it is when it is not a clinical result: preclinical, observational, review,
  company statement. Company statements are the company's claims ("the company reported").
- A general claim ("companies", "studies", "several trials") cites every source below that supports it, or is
  narrowed to the sources it cites.
- When sources complicate or contradict a statement, say so in the same place. When two findings point in opposite
  directions, give the condition that separates them if a source states it; otherwise say they disagree.
- A COMMENTARY is not independent evidence: cite the paper it comments on for the findings.
- Do not merge different drugs, mechanisms, combinations or definitions into one claim.
- A source may be cited in more than one section."""


def narrative(cfg, items, scr, usage, window, changes_md=""):
    """State of the field, key assets table and biology/science bullets, citing [S#], then a citation check."""
    if not available():
        return ""
    top = sorted([i for i in items if scr[i["sid"]]["rel"] >= 2], key=lambda i: (-scr[i["sid"]]["rel"], i["sid"]))[:160]
    if not top:
        return ""
    def line(i):
        sc = scr[i["sid"]]
        extra = "".join(f" | {k.upper()}: {sc[k]}" for k in ("note", "type", "limits") if sc.get(k))
        return describe(i, 500, cfg["keywords"]) + extra
    listing = "\n".join(line(i) for i in top)
    changes = ("Changes since the previous scan:\n" + changes_md) if changes_md else ""
    prompt = f"""Write a landscape briefing for this reader:
{cfg.get('context') or 'A biotech analyst following: ' + ', '.join(cfg['keywords'])}

Window: {window[0]} to {window[1]}.
{changes}
{WRITING_RULES}
If there are changes since the previous scan, open "State of the field" with them.

Reply in markdown with exactly these three sections and nothing else:

## State of the field
2-3 short paragraphs, at most 300 words in total.

## Key assets & companies
A table with this header, one row per asset or company, at most 20 rows. Leave "Last mention" empty: it is filled in automatically.
| Asset | Company | Mechanism | Stage | What happened | Last mention |
|---|---|---|---|---|---|

## Biology & biomarker signals
3-6 bullets on the science in the sources (mechanism, patient selection, resistance, safety), each with its qualifiers.

SOURCES:
{listing}"""
    text = call(prompt, usage, max_tokens=6000).strip()
    if usage.last_stop == "max_tokens":
        text = call(prompt, usage, max_tokens=12000).strip()
    i = text.find("## State of the field")
    text = text[i:] if i >= 0 else text
    known = {it["sid"] for it in items}
    text = _strip_unknown_cites(text, known)
    checked, usage.check = check_briefing(text, items, scr, usage)
    return _strip_unknown_cites(checked, known)


def check_briefing(text, items, scr, usage, per_source=2500):
    """A second reader checks every cited sentence against the full text of the sources it cites and returns the
    briefing with only the needed corrections. Returns (text, list of changes)."""
    cited = sorted(set(re.findall(r"S\d+", text)), key=lambda x: int(x[1:]))
    by = {i["sid"]: i for i in items}
    srcs = []
    for sid in cited:
        i = by.get(sid)
        if not i:
            continue
        sc = scr.get(sid, {})
        head = f"[{sid}] ({i['kind']}{', ' + sc['type'] if sc.get('type') else ''}{', COMMENTARY on ' + i['comments_on'] if i.get('comments_on') else ''}) {i['title']}"
        srcs.append(head + " | " + re.sub(r"\s+", " ", (describe(i, 400) if i["kind"] in ("trial", "eu_trial") else "") + " " + (i.get("abstract") or ""))[:per_source])
    if not srcs:
        return text, []
    prompt = f"""You are checking a landscape briefing against its sources before a client reads it.

For every sentence or table cell that cites sources, check:
1. Every claim is supported by the sources it cites (a claim supported only by an uncited source in the list may
   cite it instead).
2. No qualifier the sources state is dropped in a way that changes the meaning (subgroup-only significance,
   non-significant endpoints, sample size, definitions or cutoffs, preclinical model, company-reported).
3. A general claim ("companies", "studies") is not resting on one source; narrow it or add the other cited sources.
4. Different drugs, mechanisms, combinations or definitions are not merged.
5. A commentary is not used as independent support for the paper it comments on.

Return the briefing with ONLY the corrections needed, same sections and table, same markdown. Remove a claim the
sources do not support. Do not add new topics, interpretation or recommendations. Then a line "=== CHANGES ===" and
one bullet per change ("- [S12] added that the effect was significant only in HER2+ disease"), or "- none".

BRIEFING:
{text}

SOURCES (full text as available):
{chr(10).join(srcs)}"""
    out = call(prompt, usage, max_tokens=12000).strip()
    if "=== CHANGES ===" not in out or "## State of the field" not in out:
        return text, ["citation check did not return a usable result; draft kept"]
    body, changes = out.split("=== CHANGES ===", 1)
    body = body[body.find("## State of the field"):].strip()
    changes = [c.strip("- ").strip() for c in changes.strip().splitlines() if c.strip().startswith("-")]
    return body, [c for c in changes if c.lower() != "none"]


def not_cited(story, items, scr):
    """Relevant sources (2-3) the written briefing does not cite, so nothing relevant goes unseen."""
    cited = set(re.findall(r"S\d+", story or ""))
    return [i for i in items if scr.get(i["sid"], {}).get("rel", 0) >= 2 and i["sid"] not in cited]


def briefing(cfg, items, scr, status, window, story="", changes_md=""):
    """Assemble briefing.md in the format the skill writes, so `render` treats both the same."""
    n3 = sum(1 for v in scr.values() if v["rel"] == 3)
    n2 = sum(1 for v in scr.values() if v["rel"] == 2)
    by_ai = any(v.get("by") == "ai" for v in scr.values())
    kinds = {"trials": "US trials", "eu_trials": "EU trials (CTIS)", "pubmed": "PubMed", "preprints": "preprints",
             "sec": "SEC filings", "press": "trade press", "news": "news"}
    ok = all(str(v).startswith(("ok", "skipped")) for v in status.values())
    num_only = lambda v: re.sub(r"^ok \((\d+)\)$", r"\1", str(v))
    counts = " · ".join(f"{kinds.get(k, k)} {num_only(v)}" for k, v in status.items())
    L = [f"# {cfg.get('name', 'Landscape scan')}: Landscape briefing",
         f"Window: {window[0]} to {window[1]} · {len(items)} sources screened ({n3} directly relevant, {n2} context)",
         f"Source status: {'all sources ok. ' if ok else ''}{counts}", ""]
    if not by_ai:
        L += ["*No AI screening on this run: relevance is a keyword match (2 = keyword in the title, 1 = keyword in the text). "
              "Add an Anthropic API key, or run the scan as a Claude skill, for screened scores and a written briefing.*", ""]
    if changes_md:  # updates lead with what changed since the last scan
        L += [changes_md, ""]
    if story:
        L += [story, ""]
    L += ["## Screened sources", "| ID | Type | Rel. | Matched | Title | Note |", "|---|---|---|---|---|---|"]
    num = lambda s: int(s[1:])
    by_sid = {i["sid"]: i for i in items}
    for r in (3, 2):
        for sid in sorted((s for s, v in scr.items() if v["rel"] == r), key=num):
            it = by_sid[sid]
            m = it.get("matched") or []
            if isinstance(m, dict):
                m = [t for v in m.values() for t in v]
            L.append(f"| {sid} | {it['kind']} | {r} | {', '.join(m) or '(text)'} | {it['title'].replace('|', '/')[:100]} | "
                     f"{scr[sid]['note'].replace('|', '/')} |")
    low = sorted((s for s, v in scr.items() if v["rel"] < 2), key=num)
    if low:
        L += ["", f"{len(low)} tangential/off-topic sources: " + ", ".join(low)]
    return "\n".join(L) + "\n"
