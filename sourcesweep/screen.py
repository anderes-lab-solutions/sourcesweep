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

def describe(item, chars=600):
    if item["kind"] == "trial":
        body = (f"{item.get('venue', '')} · {', '.join(item.get('phases') or []) or 'phase n/a'} · {item.get('status', '')} · "
                f"conditions: {'; '.join(item.get('conditions', [])[:6])} · interventions: {'; '.join(item.get('interventions', [])[:6])} · "
                f"{item.get('abstract', '')}")
    else:
        body = f"{item.get('venue', '')} · {item.get('abstract', '')}"
    body = re.sub(r"\s+", " ", body)[:chars]
    return f"[{item['sid']}] ({item['kind']}, {item.get('date', '')}) {item['title']} | {body}"


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
        listing = "\n".join(describe(i) for i in batch)
        prompt = f"""You are screening sources for a competitive landscape scan.

READER AND SCOPE:
{cfg.get('context') or 'Not given: judge relevance to the search keywords.'}

SEARCH KEYWORDS: {', '.join(cfg['keywords'])}

Score every source for this reader:
3 = directly relevant: about the keywords' subject, its assets or competitors in scope
2 = relevant context: mechanism, biomarker, indication or an adjacent competitor
1 = tangential: mentions a keyword in passing
0 = off-topic

For sources scored 2 or 3, write a note: one sentence, at most 20 words, on what the source adds.
Use only facts in the text given. Never invent results, numbers or drug facts.

Reply with only a JSON array, one object per source:
[{{"id": "S1", "rel": 2, "note": "..."}}]

SOURCES:
{listing}"""
        res = _json(call(prompt, usage, max_tokens=8000), "[") or []
        for r in res:
            sid = str(r.get("id", ""))
            if sid in scr:
                try:
                    scr[sid] = {"rel": max(0, min(3, int(r.get("rel")))), "note": str(r.get("note") or "")[:300], "by": "ai"}
                except (TypeError, ValueError):
                    pass
    return scr


# ------------------------------------------------------------------ briefing

def _strip_unknown_cites(text, known):
    def fix(m):
        ids = [x.strip() for x in m.group(1).split(",")]
        keep = [x for x in ids if x in known]
        return f"[{', '.join(keep)}]" if keep else ""
    return re.sub(r"\[((?:S\d+\s*,?\s*)+)\]", fix, text)


def narrative(cfg, items, scr, usage, window, changes_md=""):
    """State of the field, key assets table and biology bullets, citing [S#]. Returns markdown or ''."""
    if not available():
        return ""
    top = sorted([i for i in items if scr[i["sid"]]["rel"] >= 2], key=lambda i: (-scr[i["sid"]]["rel"], i["sid"]))[:90]
    if not top:
        return ""
    listing = "\n".join(describe(i, 400) + (f" | NOTE: {scr[i['sid']]['note']}" if scr[i["sid"]]["note"] else "") for i in top)
    changes = ("Changes since the previous scan:\n" + changes_md) if changes_md else ""
    prompt = f"""Write a landscape briefing for this reader:
{cfg.get('context') or 'A biotech analyst following: ' + ', '.join(cfg['keywords'])}

Window: {window[0]} to {window[1]}.
{changes}
Use ONLY the sources below. Cite every claim with source IDs like [S3] or [S3, S8].
Do not add facts, numbers, dates or drug names that are not in the sources. If the evidence on a point is thin, say so.

Reply in markdown with exactly these three sections and nothing else:

## State of the field
2-3 short paragraphs, at most 250 words in total.

## Key assets & companies
A table with this header, one row per asset or company, at most 20 rows. Leave "Last mention" empty: it is filled in automatically.
| Asset | Company | Mechanism | Stage | What happened | Last mention |
|---|---|---|---|---|---|

## Biology & biomarker signals
3-5 bullets.

SOURCES:
{listing}"""
    text = call(prompt, usage, max_tokens=5000).strip()
    if usage.last_stop == "max_tokens":
        text = call(prompt, usage, max_tokens=10000).strip()
    i = text.find("## State of the field")
    text = text[i:] if i >= 0 else text
    return _strip_unknown_cites(text, {it["sid"] for it in items})


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
    if story:
        L += [story, ""]
    if changes_md:
        L += [changes_md, ""]
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
