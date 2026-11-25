---
name: "sourcesweep"
description: "Run a SourceSweep competitive landscape scan (also called a landscape scan or Landscape Watch scan) for keyword profiles or ad-hoc keywords: pulls recent US/EU clinical trials, PubMed papers, preprints, SEC filings, trade press and news, screens them for relevance, and publishes a cited HTML report plus a source pack."
---

# SourceSweep™: competitive landscape scan

<!-- Built from https://github.com/anderes-lab-solutions/sourcesweep (v1.1.0). Copyright 2026 Tegan Anderes / Anderes Lab Solutions. GNU AGPL-3.0-only; keep this attribution (see NOTICE). Edit skill/SKILL.template.md and sourcesweep/scanner.py, then run tools/build_skill.py. -->

Targeted pre-scrape for any set of search keywords. A bundled script searches seven public sources
over a lookback window (default 60 days). You then screen every source for relevance, write a
briefing that cites sources as [S#], and publish an HTML report the user can browse and open links from.

Sources:
- **trials**: ClinicalTrials.gov (API v2), active trials plus anything updated in the window
- **eu_trials**: EU Clinical Trials Information System (CTIS) public search; catches EU-only records. Date = last update, so older records appear too
- **pubmed**: NCBI E-utilities, with abstracts
- **preprints**: Europe PMC (bioRxiv, medRxiv, etc.)
- **sec**: SEC EDGAR full-text search (8-K decks and press releases, 10-Q, S-1, S-4, 424B). Pipeline changes, program cuts, IND timing and deal disclosures. The script pulls short excerpts around each keyword mention
- **press**: trade press and wires (Fierce Biotech, Endpoints, BioSpace, STAT, BioPharma Dive, GlobeNewswire, Business Wire, PR Newswire) through a site-restricted Google News search that matches article text, not just titles
- **news**: general Google News, title-matched; items already found by **press** are dropped

Not covered: patents (no keyless official API; Google Patents scraping is off-limits) and conference
abstracts (no open API). For those, suggest a targeted web search around meeting dates.

## Keywords come from the user

A scan is driven only by the user's search keywords. **Use the keywords exactly as given. Never add
drugs, assets, synonyms or other terms on your own initiative.** If you think a term is missing, you may
mention it in one line at the end; the user decides.

Optional: the user may keep profiles on their own Landscape Watch page (an artifact with a `profiles`
collection: `{name, keywords: [...], days, context, restrictText, restrictCondition}` and a `scans`
collection). Use it only if the user gives you its link or slug and you can read it.

## Step 1: Get the keywords

- **The request lists keywords** (for example a "Run in Claude" request: "Run a landscape watch scan for the
  <name> profile using exactly these keywords: ..."): use exactly those keywords, plus any lookback, paper
  word, trial condition and scope it states.
- **The user names a profile without keywords**: if they gave a Landscape Watch page link, read the profile
  there with `db_list` (collection `profiles`); otherwise ask for the keywords.

Lookback: the request's value, else the profile's `days`, else 60 (allowed 7–120).

Build the run config (the `email` is the contact NCBI and the SEC require: use the user's email if you know it, otherwise ask once):
```json
{"name": "<profile name>", "slug": "<profile id or a slug of the keywords>",
 "keywords": ["<exactly the user's keywords>"],
 "context": "<profile context, or a one-line scope inferred from the request if none>",
 "restrict": {"text": "<restrictText or omit>", "condition": "<restrictCondition or omit>"},
 "email": "<the user's email>"}
```
Optional keys: `skip_sources` (e.g. `["sec", "press"]`), `press_sites` (replaces the default trade-press domain list).

Show the user the keywords in one short line and proceed.

## Step 2: Set up the script

The script is embedded at the end of this file. Extract it to disk; don't retype it:

```bash
SKILL_MD=$(find / -path '*sourcesweep*' -name SKILL.md 2>/dev/null | head -1)
python3 - "$SKILL_MD" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
code = re.search(r"```python sourcesweep\.py\n(.*?)\n```", text, re.S).group(1)
open("/tmp/sourcesweep.py", "w").write(code)
print("script ready:", len(code.splitlines()), "lines")
PY
```

If `find` returns nothing, write the code block under "Bundled script" to `/tmp/sourcesweep.py` with your file tool, copied exactly.

## Step 3: Check network access

```bash
python3 /tmp/sourcesweep.py check
```

If any source shows BLOCKED, stop and tell the user how to allow it:
- **Pro / Max:** Settings → Capabilities → Create and edit files → turn on **Use the internet while making files**, then **Allowed websites → Manage** and add: `clinicaltrials.gov`, `euclinicaltrials.eu`, `eutils.ncbi.nlm.nih.gov`, `www.ebi.ac.uk`, `news.google.com`, `efts.sec.gov`, `www.sec.gov`. Choosing all sites also works. Then start a new chat.
- **Team / Enterprise:** an admin sets this in Organization settings → Capabilities.
- **Free:** only package managers can be allowed, so the scan can't run.

If only some sources are blocked, offer to run with the ones that work and say clearly which are missing.

## Step 4: Run the scan

Write the config to `/tmp/lw_cfg.json`, then run:
```bash
OUT=/mnt/user-data/outputs; [ -d "$OUT" ] || OUT=$PWD
OUT="$OUT/landscape_<slug>_$(date +%F)"
python3 /tmp/sourcesweep.py scan --config /tmp/lw_cfg.json --days <days> --out "$OUT"
```
It takes 2–5 minutes. The script writes:
- `index.md`: one row per source (ID, type, date, matched keywords, title, sponsor or venue). Types: trial, eu_trial, paper, preprint, sec, press, news
- `sources.md`: the full source pack with abstracts, trial details, filing excerpts and links
- `sources.json`: the same data, machine-readable

If a source shows FAILED in the summary, continue with the rest and mention it in your reply.

## Step 5: Screen for relevance

Read `index.md` first. Then read abstracts in batches for anything you can't judge from the title:
```bash
python3 /tmp/sourcesweep.py show --out "$OUT" S3 S7 S12
```
With more than about 80 sources, don't read `sources.md` in one go. Use `show` in batches of about 15.

Score every source against the profile's `context` (or the user's evident scope):
- **3, directly relevant:** about the keywords' subject, its assets or competitors in scope
- **2, relevant context:** mechanism, biomarker, indication, or an adjacent competitor
- **1, tangential:** mentions a keyword in passing
- **0, off-topic**

Type-specific notes:
- **sec**: read the excerpts. 8-K decks and 10-Qs often hold the most decision-relevant facts (dropped trials, IND timing, competitor lists). Boilerplate risk-factor mentions are 1
- **eu_trial**: CTIS status is a numeric code; rely on the last-updated date and title. Flag EU-only trials and ones that differ from the US record
- **press** items marked "(in article text)" have no abstract; judge them by title and company, and don't state facts that aren't in the title

Give each source scored 2 or 3 a one-sentence note on what it adds. Use only facts in the source.
Write every score to `$OUT/screening.json`, covering all sources:
```json
{"S1": {"rel": 3, "note": "ASPENOVA confirmatory trial"}, "S2": {"rel": 1, "note": ""}}
```

## Step 6: Write the briefing

Report what the sources say and attribute it ("the registry lists...", "the company reported..."). Don't add your own
scientific interpretation, predictions, rankings of assets or strategic recommendations: the reader draws the conclusions.

Create `briefing.md` in `$OUT`:

```
# <profile name>: Landscape briefing
Window: <start> to <end> · <N> sources screened (<n3> directly relevant, <n2> context)
Source status: <any failures>

## State of the field
2–3 short paragraphs, max 250 words, every claim cited [S#]. Lead with what changed, if tracked.
## Key assets & companies
| Asset | Company | Mechanism | Stage | What happened | Last mention |
|---|---|---|---|---|---|
| <asset> | <company> | <mechanism> | <stage> | <what happened in the window> [S#, S#] | |
## Biology & biomarker signals
3–5 bullets [S#]

## Screened sources
| ID | Type | Rel. | Matched | Title | Note |
(all 3s, then 2s; then one line: "<k> tangential/off-topic sources: S.., S..")
```

Key assets & companies is a table, one row per asset (or tightly linked pair), with every source for that asset cited in its row. Leave **Last mention** empty: `render` fills it with the date and ID of the newest source the row cites. Write "Not stated" where the sources don't give a mechanism or stage. Don't add a follow-up questions section.

Cite as `[S1]` or `[S1, S36]`; ranges like `[S40–S48]` also work. Rules: cite only sources in the pack.
Never add results, numbers or drug facts that aren't in them. If the evidence on a point is thin, say so.

## Step 7: Publish the report and record the scan

1. Render the HTML report (run timestamp and window length in days, briefing with clickable citations and the assets table with Download CSV / Copy CSV, relevance chart, filterable source list, links open in new tabs). Rendering also fills the assets table's Last mention column in `briefing.md`:
   ```bash
   python3 /tmp/sourcesweep.py render --out "$OUT" --title "<Profile name> scan <YYYY-MM-DD>"   # add --hub <their Landscape Watch page URL> if they have one
   ```
2. Publish `$OUT/report.html` as a new artifact (title `<Profile name> scan <YYYY-MM-DD>`, icon `report`) if this session can publish artifacts, and give it the `downloads` capability so Download CSV works; otherwise send `report.html` as a file (it opens in any browser). If a report for the same profile and date was already published in this conversation, republish that artifact instead.
3. Only if the user has their own Landscape Watch page and can edit it: record the scan there with `db_write` (`set` on `scans/<profile-id>-<YYYY-MM-DD>` with `profile`, `profileName`, `date`, `ranAt` = `generated_at` from `sources.json`, `days`, `window`, `total`, `direct` (count of 3s), `context` (count of 2s), `url`, `artifactSlug`).
4. Share `briefing.md` and `sources.md` as files too. In chat give:
   - the counts per source type, and any source that failed
   - 3–5 headline findings with [S#] citations
   - a note that `sources.md` can be added to a Claude Project as project knowledge for ongoing questions

Summarize abstracts in your own words; don't paste them in full into chat. They belong to their publishers.

## Follow-up questions

Answer from the scan. Find the right sources by `grep -i "<term>" "$OUT/index.md"`, then read them with `show`. Cite [S#].
- If the pack doesn't cover something, say so and offer to rerun with added keywords (only the ones the user approves) or a different window.
- To narrow to one indication, rerun with `restrict` rather than filtering by eye.
- New keywords mean a new scan. Keep the earlier output folder, because its [S#] IDs only apply to that run.

## Bundled script
```python sourcesweep.py
#!/usr/bin/env python3
"""SourceSweep: US + EU trials, PubMed, preprints, SEC filings, trade press and news
for a set of search keywords. Standard library only, so the same file runs inside a Claude skill.

Copyright (C) 2026 Tegan Anderes / Anderes Lab Solutions.
Licensed under the GNU Affero General Public License v3.0 only (AGPL-3.0-only); see LICENSE and NOTICE.
https://github.com/anderes-lab-solutions/sourcesweep

  python3 sourcesweep.py check
  python3 sourcesweep.py scan --config cfg.json --days 60 --out DIR
  python3 sourcesweep.py show --out DIR S3 S12
  python3 sourcesweep.py render --out DIR [--hub https://claude.ai/...]   # writes DIR/report.html
"""
import argparse, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import os
from pathlib import Path

__version__ = "1.1.0"
UA_NAME = "sourcesweep"
REPO_URL = "https://github.com/anderes-lab-solutions/sourcesweep"


def contact(cfg):
    """Contact address sent to NCBI and SEC, which ask API users to identify themselves."""
    return cfg.get("email") or os.environ.get("SOURCESWEEP_EMAIL") or "contact@example.com"

HOSTS = {"trials": "https://clinicaltrials.gov/api/v2/studies?pageSize=1",
         "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi?retmode=json",
         "preprints": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=test&format=json&pageSize=1",
         "news": "https://news.google.com/rss/search?q=test",
         "eu_trials": "https://euclinicaltrials.eu/ctis-public-api/search",
         "sec": "https://efts.sec.gov/LATEST/search-index?q=%22CDK2%22"}
PRESS_SITES = ["fiercebiotech.com", "endpts.com", "biospace.com", "statnews.com", "biopharmadive.com",
               "globenewswire.com", "businesswire.com", "prnewswire.com"]
ACTIVE = {"RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}
TAG = re.compile(r"<[^>]+>")


def get(url, params=None, data=None, timeout=60, json_body=None, ua=f"{UA_NAME}/{__version__}"):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"User-Agent": ua}
    if json_body is not None:
        body = json.dumps(json_body).encode(); headers["Content-Type"] = "application/json"
    else:
        body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            code = getattr(e, "code", None)
            if attempt == 2 or (code and code < 500 and code != 429):
                raise
            time.sleep(3 * (attempt + 1))


def normalize_keywords(cfg):
    """A profile is a flat keyword list. Older profiles with targets/drugs/mechanisms are merged into it."""
    out = []
    for k in (cfg.get("keywords") or []) + (cfg.get("targets") or []) + (cfg.get("drugs") or []) + (cfg.get("mechanisms") or []):
        k = str(k).strip()
        if k and k.lower() not in {x.lower() for x in out}:
            out.append(k)
    return out


def q(t):
    return f'"{t}"' if re.search(r"[\s\-/+]", t) else t


def txt(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def clean(s):
    return re.sub(r"\s+", " ", TAG.sub(" ", s or "")).strip()


# ------------------------------------------------------------------ sources

def trials(cfg, start):
    cond = cfg.get("restrict", {}).get("condition")
    kw = cfg["keywords"]
    queries = [{"query.term": " OR ".join(q(x) for x in kw[i:i + 5]), **({"query.cond": cond} if cond else {})}
               for i in range(0, len(kw), 5)]
    out = {}
    for params in queries:
        token = None
        while True:
            p = {**params, "pageSize": 100, "format": "json", **({"pageToken": token} if token else {})}
            data = json.loads(get("https://clinicaltrials.gov/api/v2/studies", p))
            for s in data.get("studies", []):
                ps = s.get("protocolSection", {})
                st, ident, des = ps.get("statusModule", {}), ps.get("identificationModule", {}), ps.get("designModule", {})
                nct, updated = ident.get("nctId"), st.get("lastUpdatePostDateStruct", {}).get("date", "")
                if not nct or not (st.get("overallStatus") in ACTIVE or updated >= start):
                    continue
                out[nct] = {
                    "kind": "trial", "id": nct, "url": f"https://clinicaltrials.gov/study/{nct}",
                    "title": ident.get("briefTitle", nct), "date": updated,
                    "venue": ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", ""),
                    "abstract": (ps.get("descriptionModule", {}).get("briefSummary") or "").strip(),
                    "status": st.get("overallStatus", ""), "phases": des.get("phases", []) or [],
                    "enrollment": des.get("enrollmentInfo", {}).get("count"),
                    "start": st.get("startDateStruct", {}).get("date", ""),
                    "primary_completion": st.get("primaryCompletionDateStruct", {}).get("date", ""),
                    "conditions": ps.get("conditionsModule", {}).get("conditions", []) or [],
                    "interventions": [f"{i.get('type', '')}: {i.get('name', '')}" for i in
                                      ps.get("armsInterventionsModule", {}).get("interventions", []) or []],
                    "endpoints": [o.get("measure", "") for o in ps.get("outcomesModule", {}).get("primaryOutcomes", []) or []],
                }
            token = data.get("nextPageToken")
            if not token:
                break
    return list(out.values())


def pubmed(cfg, days):
    base, email = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils", contact(cfg)
    text = cfg.get("restrict", {}).get("text")
    kw = cfg["keywords"]
    queries = ["(" + " OR ".join(f"{q(x)}[tiab]" for x in kw[i:i + 8]) + ")" + (f" AND {q(text)}[tiab]" if text else "")
               for i in range(0, len(kw), 8)]
    ids = []
    for term in queries:
        r = json.loads(get(f"{base}/esearch.fcgi", {"db": "pubmed", "term": term, "reldate": days, "datetype": "edat",
                                                     "retmax": 300, "retmode": "json", "tool": UA_NAME, "email": email}))
        ids += [i for i in r["esearchresult"].get("idlist", []) if i not in ids]
        time.sleep(0.4)
    papers = []
    for i in range(0, len(ids), 100):
        root = ET.fromstring(get(f"{base}/efetch.fcgi", data={"db": "pubmed", "id": ",".join(ids[i:i + 100]),
                                                              "retmode": "xml", "tool": UA_NAME, "email": email}))
        for art in root.iter("PubmedArticle"):
            mc = art.find("MedlineCitation"); a = mc.find("Article"); pmid = txt(mc.find("PMID"))
            abstract = "\n".join((f"{ab.get('Label')}: " if ab.get("Label") else "") + txt(ab) for ab in a.findall("Abstract/AbstractText"))
            au = a.findall("AuthorList/Author")
            first = (txt(au[0].find("LastName")) + " " + txt(au[0].find("Initials"))).strip() if au else ""
            pd = a.find("Journal/JournalIssue/PubDate")
            doi = next((txt(x) for x in art.findall("PubmedData/ArticleIdList/ArticleId") if x.get("IdType") == "doi"), "")
            papers.append({"kind": "paper", "id": pmid, "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                           "title": txt(a.find("ArticleTitle")).rstrip("."), "abstract": abstract,
                           "authors": first + (" et al." if len(au) > 1 else ""), "doi": doi,
                           "venue": txt(a.find("Journal/ISOAbbreviation")) or txt(a.find("Journal/Title")),
                           "date": " ".join(x for x in (txt(pd.find("Year")), txt(pd.find("Month"))) if x) if pd is not None else "",
                           "types": [txt(x) for x in a.findall("PublicationTypeList/PublicationType") if txt(x) != "Journal Article"]})
        time.sleep(0.4)
    return papers


def preprints(cfg, start, end):
    terms = cfg["keywords"]
    query = "(" + " OR ".join(f'TITLE:"{x}" OR ABSTRACT:"{x}"' for x in terms) + ")"
    if cfg.get("restrict", {}).get("text"):
        t = cfg["restrict"]["text"]; query += f' AND (TITLE:"{t}" OR ABSTRACT:"{t}")'
    query += f" AND SRC:PPR AND FIRST_PDATE:[{start} TO {end}]"
    out, cursor = [], "*"
    while len(out) < 300:
        d = json.loads(get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                           {"query": query, "format": "json", "resultType": "core", "pageSize": 100, "cursorMark": cursor}))
        res = d.get("resultList", {}).get("result", [])
        for r in res:
            doi, names = r.get("doi", ""), [n for n in r.get("authorString", "").rstrip(".").split(", ") if n]
            out.append({"kind": "preprint", "id": r.get("id", ""), "title": clean(r.get("title", "")).rstrip("."),
                        "abstract": clean(r.get("abstractText", "")), "doi": doi, "date": r.get("firstPublicationDate", ""),
                        "venue": (r.get("bookOrReportDetails") or {}).get("publisher", "Preprint"),
                        "authors": (names[0] + (" et al." if len(names) > 1 else "")) if names else "",
                        "url": f"https://doi.org/{doi}" if doi else f"https://europepmc.org/article/PPR/{r.get('id', '')}"})
        nxt = d.get("nextCursorMark")
        if not res or not nxt or nxt == cursor:
            break
        cursor = nxt
    return out


def news(cfg, days):
    terms = cfg["keywords"]
    kws = [k.lower() for k in terms]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items, seen = [], set()
    for i in range(0, len(terms), 5):
        qs = " OR ".join(f'"{x}"' for x in terms[i:i + 5])
        if cfg.get("restrict", {}).get("text"):
            qs = f'({qs}) {cfg["restrict"]["text"]}'
        root = ET.fromstring(get("https://news.google.com/rss/search", {"q": qs, "hl": "en-US", "gl": "US", "ceid": "US:en"}))
        for it in root.iter("item"):
            title = clean(txt(it.find("title")))
            if kws and not any(k in title.lower() for k in kws):
                continue
            try:
                when = parsedate_to_datetime(txt(it.find("pubDate")))
            except (TypeError, ValueError):
                when = None
            if when and when < cutoff:
                continue
            key = news_key(title)
            if key in seen:
                continue
            seen.add(key)
            items.append({"kind": "news", "id": txt(it.find("link")), "url": txt(it.find("link")), "title": title,
                          "venue": txt(it.find("source")), "date": when.strftime("%Y-%m-%d") if when else "", "abstract": ""})
    return items


def eu_trials(cfg, start):
    """EU Clinical Trials Information System (CTIS) public search. Returns every hit; date = last update."""
    terms = cfg["keywords"]
    out, page = [], 1
    while page <= 5:
        d = json.loads(get("https://euclinicaltrials.eu/ctis-public-api/search", json_body={
            "pagination": {"page": page, "size": 100}, "sort": {"property": "decisionDate", "direction": "DESC"},
            "searchCriteria": {"containAny": ", ".join(terms)}}))
        for t in d.get("data", []):
            dmy = lambda s: "-".join(reversed(s.split("/"))) if s and s.count("/") == 2 else (s or "")
            ct = t.get("ctNumber", "")
            out.append({"kind": "eu_trial", "id": ct, "title": clean(t.get("ctTitle", ct)),
                        "url": f"https://euclinicaltrials.eu/search-for-clinical-trials/?lang=en&EUCT={ct}",
                        "date": dmy(t.get("lastUpdated")), "venue": t.get("sponsor", ""),
                        "abstract": clean(t.get("endPoint") or t.get("primaryEndPoint") or ""),
                        "phase": t.get("trialPhase", ""), "decision": dmy(t.get("decisionDateOverall")),
                        "start": dmy(t.get("startDateEU")), "countries": t.get("trialCountries", []) or [],
                        "conditions": [clean(t.get("conditions", ""))], "interventions": [clean(t.get("product") or "")],
                        "status_code": t.get("ctStatus")})
        if not d.get("pagination", {}).get("nextPage"):
            break
        page += 1
    return out


def sec_filings(cfg, start, end):
    """SEC EDGAR full-text search: 8-K, 10-Q, 10-K, S-1 etc. that mention any profile term in the window."""
    ua = f"{UA_NAME} {contact(cfg)}"
    hits = {}
    for term in cfg["keywords"]:
        frm = 0
        while frm < 300:
            d = json.loads(get("https://efts.sec.gov/LATEST/search-index", {
                "q": f'"{term}"', "dateRange": "custom", "startdt": start, "enddt": end, "from": frm}, ua=ua))
            batch = d.get("hits", {}).get("hits", [])
            for h in batch:
                src = h["_source"]; adsh, _, fname = h["_id"].partition(":")
                cik = (src.get("ciks") or ["0"])[0]
                company = re.sub(r"\s+\(CIK.*$", "", (src.get("display_names") or ["?"])[0]).strip()
                company = re.sub(r"\s+", " ", company)
                it = hits.setdefault(h["_id"], {
                    "kind": "sec", "id": h["_id"], "date": src.get("file_date", ""), "venue": company,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{fname}",
                    "title": f"{company}: {src.get('form', '')} {src.get('file_description') or src.get('file_type') or ''}".strip(),
                    "form": src.get("form", ""), "terms": []})
                if term not in it["terms"]:
                    it["terms"].append(term)
            frm += len(batch)
            if len(batch) < 100 or frm >= d.get("hits", {}).get("total", {}).get("value", 0):
                break
            time.sleep(0.2)
        time.sleep(0.2)
    latest = {}  # collapse repeat amendments/exhibits of the same company + form, keeping the newest
    for it in sorted(hits.values(), key=lambda x: x["date"], reverse=True):
        desc = re.sub(r"\bNO\.?\s*\d+\b", "", it["title"].split(":", 1)[-1], flags=re.I).split()
        k = (it["venue"], it["form"].replace("/A", ""), desc[-1].upper() if desc else "")
        if k in latest:
            latest[k]["terms"] = sorted(set(latest[k]["terms"]) | set(it["terms"]))
            latest[k].setdefault("also", []).append(it["date"])
        else:
            latest[k] = it
    for it in latest.values():
        terms = it.pop("terms")
        it["abstract"] = "Filing text mentions: " + ", ".join(terms)
        try:  # pull short excerpts around the first mentions so the filing can be screened without opening it
            body = clean(re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", get(it["url"], ua=ua, timeout=90).decode("utf-8", "replace")))
            body = body.replace("&#160;", " ").replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8217;", "'")
            snips, spans = [], []
            for t in terms:
                for m in re.finditer(re.escape(t), body, re.I):
                    if len(snips) >= 4 or any(abs(m.start() - x) < 500 for x in spans):
                        continue
                    spans.append(m.start()); snips.append("..." + body[max(0, m.start() - 250): m.end() + 350].strip() + "...")
                    break
            if snips:
                it["abstract"] += "\n" + "\n".join(snips)
        except Exception as e:
            it["abstract"] += f" (excerpt unavailable: {type(e).__name__})"
        time.sleep(0.2)
        if it.get("also"):
            it["abstract"] += f" · {len(it['also'])} earlier similar filing(s) in window: " + ", ".join(sorted(it.pop("also")))
    return list(latest.values())


def trade_press(cfg, days):
    """Trade press and press-release wires via a site-restricted Google News search (article text, not just titles)."""
    terms = cfg["keywords"]
    sites = " OR ".join(f"site:{s}" for s in cfg.get("press_sites") or PRESS_SITES)
    items, seen = [], set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for i in range(0, len(terms), 6):
        qs = "(" + " OR ".join(f'"{x}"' for x in terms[i:i + 6]) + f") ({sites}) when:{days}d"
        if cfg.get("restrict", {}).get("text"):
            qs += f' {cfg["restrict"]["text"]}'
        root = ET.fromstring(get("https://news.google.com/rss/search", {"q": qs, "hl": "en-US", "gl": "US", "ceid": "US:en"}))
        for it in root.iter("item"):
            title = clean(txt(it.find("title")))
            key = news_key(title)
            if key in seen:
                continue
            seen.add(key)
            try:
                dt = parsedate_to_datetime(txt(it.find("pubDate")))
            except (TypeError, ValueError):
                dt = None
            if dt is None or dt < cutoff:  # Google ignores when: alongside site: filters, so enforce the window here
                continue
            when = dt.strftime("%Y-%m-%d")
            items.append({"kind": "press", "id": txt(it.find("link")), "url": txt(it.find("link")), "title": title,
                          "venue": txt(it.find("source")), "date": when, "abstract": ""})
        time.sleep(0.5)
    return items


def news_key(title):
    return re.sub(r"\W+", " ", re.sub(r"\s+-\s+[^-]+$", "", title).lower()).strip()


# ------------------------------------------------------------------ matching & output

def matched(cfg, item):
    text = " ".join([item["title"], item.get("abstract", "")] + item.get("conditions", []) + item.get("interventions", []))
    hit = lambda t: re.search(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", text, re.I)
    return [t for t in cfg["keywords"] if hit(t)]


def label(item):
    fallback = {"trial": "(registry fields)", "eu_trial": "(registry fields)", "press": "(in article text)"}
    return ", ".join(item["matched"]) or fallback.get(item["kind"], "(none in text)")


def write(cfg, items, status, start, end, out):
    out.mkdir(parents=True, exist_ok=True)
    kind_order = {"trial": 0, "eu_trial": 1, "paper": 2, "preprint": 3, "sec": 4, "press": 5, "news": 6}
    items.sort(key=lambda i: (kind_order[i["kind"]], -len(i["matched"]), i["title"]))
    for n, it in enumerate(items, 1):
        it["sid"] = f"S{n}"
    head = f"{cfg['name']} · {start} to {end}"
    idx = [f"# Index: {head}", f"Source status: {status}", "",
           "| ID | Type | Date | Matched terms | Title | Sponsor/venue |", "|---|---|---|---|---|---|"]
    for i in items:
        extra = (f" [{', '.join(i['phases'])} · {i['status']}]" if i["kind"] == "trial"
                 else f" [{i['phase']}]" if i["kind"] == "eu_trial" else "")
        idx.append(f"| {i['sid']} | {i['kind']} | {i['date']} | {label(i)} | {i['title'].replace('|', '/')}{extra} | {i.get('venue', '')} |")
    (out / "index.md").write_text("\n".join(idx) + "\n")
    L = [f"# Source pack: {cfg['name']}", f"Window: {start} to {end} · generated {date.today()} with SourceSweep ({REPO_URL})", "",
         "## How to use this file",
         "Pre-screened US/EU clinical trials, papers, preprints, SEC filings, trade press and news with abstracts and links. Answer only from these "
         "sources and cite IDs like [S12]. Abstracts belong to their publishers; follow links for full text.", "",
         "## Scope", cfg.get("context", ""), "", f"## Sources ({len(items)})"]
    for i in items:
        L += ["", f"### [{i['sid']}] {i['title']}",
              f"- Type: {i['kind']}" + "".join(f" · {x}" for x in (i.get("venue"), i.get("date"), i.get("authors")) if x),
              f"- Link: {i['url']}" + (f" · DOI: {i['doi']}" if i.get("doi") else ""), f"- Matched terms: {label(i)}"]
        if i["kind"] == "trial":
            L += [f"- Trial: {i['id']} · {', '.join(i['phases']) or 'phase n/a'} · {i['status']} · n={i['enrollment'] or '?'} · "
                  f"start {i['start'] or '?'} · primary completion {i['primary_completion'] or '?'}",
                  f"- Conditions: {'; '.join(i['conditions'])}", f"- Interventions: {'; '.join(i['interventions'])}",
                  f"- Primary endpoints: {'; '.join(i['endpoints'])}"]
        if i["kind"] == "eu_trial":
            L += [f"- EU trial: {i['id']} · {i['phase'] or 'phase n/a'} · CTIS status code {i['status_code']} · "
                  f"decision {i['decision'] or '?'} · EU start {i['start'] or '?'} · last updated {i['date'] or '?'}",
                  f"- Countries: {', '.join(i['countries'])}", f"- Conditions: {'; '.join(i['conditions'])}",
                  f"- Product: {'; '.join(i['interventions'])}"]
        if i.get("abstract"):
            L += ["", "> " + i["abstract"].strip().replace("\n", "\n> ")]
    (out / "sources.md").write_text("\n".join(L) + "\n")
    (out / "sources.json").write_text(json.dumps({"config": cfg, "window": [start, end], "status": status,
                                                  "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": items}, indent=1))


# ------------------------------------------------------------------ HTML report

def md_inline(s):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    def cite(m):
        ids = re.findall(r"S\d+(?:\s*[–-]\s*S?\d+)?", m.group(1))
        out = []
        for x in ids:
            r = re.match(r"S(\d+)\s*[–-]\s*S?(\d+)", x)
            out += [f"S{n}" for n in range(int(r.group(1)), int(r.group(2)) + 1)] if r else [x]
        return '<span class="cites">' + "".join(f'<a class="cite" href="#{x}" data-s="{x}">{x}</a>' for x in out) + "</span>"
    return re.sub(r"\[(S\d+(?:\s*[–-]\s*S?\d+)?(?:,\s*S\d+(?:\s*[–-]\s*S?\d+)?)*)\]", cite, s)


def table_csv_rows(head, body, urls):
    """Plain rows for CSV export: citations moved to a Sources column, Last mention split into date / source / link."""
    strip = lambda c: re.sub(r"\s*\[(S\d+[^\]]*)\]", "", c).replace("**", "").strip()
    lm = next((n for n, h in enumerate(head) if h.strip().lower() == "last mention"), None)
    cols = [h for n, h in enumerate(head) if n != lm] + ["Sources", "Source links"]
    if lm is not None:
        cols += ["Last mention date", "Last mention source", "Last mention link"]
    out = [cols]
    for r in body:
        r = r + [""] * (len(head) - len(r))
        ids = list(dict.fromkeys(cited_ids(" ".join(c for n, c in enumerate(r) if n != lm))))
        row = [strip(c) for n, c in enumerate(r) if n != lm] + ["; ".join(ids), " ".join(urls.get(i, "") for i in ids).strip()]
        if lm is not None:
            m = re.match(r"\s*(\S+)\s*\[(S\d+)\]", r[lm])
            row += [m.group(1), m.group(2), urls.get(m.group(2), "")] if m else ["", "", ""]
        out.append(row)
    return out


_NOWRAP = {"last mention", "date", "dates", "id"}


def _nw(head, n):
    """Keep short date/ID columns on one line; every other column wraps."""
    return ' class="nw"' if n < len(head) and head[n].strip().lower() in _NOWRAP else ""


def md_to_html(md, urls=None, tables=None):
    """Small Markdown subset for briefings: headings, paragraphs, bullet and numbered lists, bold, [S#] citations.
    Stops at '## Screened sources', which the report shows as its interactive source list instead."""
    html, para, lst, tbl = [], [], None, []
    def flush_table():
        nonlocal tbl
        rows = [r for r in tbl if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
        if rows:
            head, body = rows[0], rows[1:]
            if tables is not None:
                tables.append(table_csv_rows(head, body, urls or {}))
                n = len(tables) - 1
                html.append(f'<div class="tbar"><button type="button" class="tbtn" data-csv="{n}">Download table (CSV)</button>'
                            f'<button type="button" class="tbtn" data-copycsv="{n}">Copy table</button></div>')
            html.append('<div class="scroll"><table class="stack"><thead><tr>' + "".join(f"<th>{md_inline(h)}</th>" for h in head) +
                        "</tr></thead><tbody>" + "".join("<tr>" + "".join(
                            f'<td data-l="{md_inline(head[n]) if n < len(head) else ""}"{_nw(head, n)}>{md_inline(c)}</td>' for n, c in enumerate(r)) + "</tr>" for r in body) +
                        "</tbody></table></div>")
        tbl = []
    def flush():
        nonlocal para, lst
        if tbl:
            flush_table()
        if para:
            html.append("<p>" + md_inline(" ".join(para)) + "</p>"); para = []
        if lst:
            html.append(f"</{lst}>"); lst = None
    for line in md.splitlines():
        t = line.strip()
        if re.match(r"^#{1,3}\s+screened sources", t, re.I):
            break
        if not t:
            flush(); continue
        h = re.match(r"^(#{1,3})\s+(.*)", t)
        if h:
            flush()
            if len(h.group(1)) > 1:
                html.append(f"<h{len(h.group(1)) + 1}>{md_inline(h.group(2))}</h{len(h.group(1)) + 1}>")
            continue
        b = re.match(r"^([-*]|\d+\.)\s+(.*)", t)
        if b:
            kind = "ol" if b.group(1)[0].isdigit() else "ul"
            if para:
                html.append("<p>" + md_inline(" ".join(para)) + "</p>"); para = []
            if lst != kind:
                if lst:
                    html.append(f"</{lst}>")
                html.append(f"<{kind}>"); lst = kind
            html.append("<li>" + md_inline(b.group(2)) + "</li>"); continue
        if t.startswith("|"):
            if lst or para:
                flush()
            tbl.append([c.strip() for c in t.strip("|").split("|")]); continue
        if tbl:
            flush_table()
        if re.match(r"^(window|source status):", t, re.I):
            continue
        if lst:
            html.append(f"</{lst}>"); lst = None
        para.append(t)
    flush()
    return "\n".join(html)


def screening_from_briefing(md):
    """Fallback when screening.json is missing: read ID / Rel. / Note from the briefing's screened-sources table."""
    scr, cols = {}, None
    for line in md.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cols is None and "ID" in cells:
            cols = {c.lower().rstrip("."): n for n, c in enumerate(cells)}; continue
        if cols and re.match(r"^S\d+$", cells[0]):
            rel = cells[cols["rel"]] if "rel" in cols and cols["rel"] < len(cells) else ""
            note = cells[cols["note"]] if "note" in cols and cols["note"] < len(cells) else ""
            scr[cells[0]] = {"rel": int(rel) if rel.isdigit() else None, "note": note}
    return scr


def norm_date(d):
    """'2026-11-20' stays; '2026 Nov' becomes '2026-11'; '2026' stays. Sorts as text."""
    d = (d or "").strip()
    m = re.match(r"^(\d{4})\s+([A-Za-z]{3})", d)
    if m:
        mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        return f"{m.group(1)}-{mon.index(m.group(2).lower()) + 1:02d}" if m.group(2).lower() in mon else m.group(1)
    return d[:10]


def cited_ids(text):
    out = []
    for grp in re.findall(r"\[(S\d+(?:\s*[–-]\s*S?\d+)?(?:,\s*S\d+(?:\s*[–-]\s*S?\d+)?)*)\]", text):
        for x in re.findall(r"S\d+(?:\s*[–-]\s*S?\d+)?", grp):
            r = re.match(r"S(\d+)\s*[–-]\s*S?(\d+)", x)
            out += [f"S{n}" for n in range(int(r.group(1)), int(r.group(2)) + 1)] if r else [x]
    return out


def fill_last_mention(md, items):
    """In any briefing table with a 'Last mention' column, write the date and ID of the newest source the row cites."""
    dates = {i["sid"]: norm_date(i.get("date", "")) for i in items}
    lines, col = md.splitlines(), None
    for n, line in enumerate(lines):
        t = line.strip()
        if not t.startswith("|"):
            col = None; continue
        cells = [c.strip() for c in t.strip("|").split("|")]
        if col is None:
            low = [c.lower() for c in cells]
            col = low.index("last mention") if "last mention" in low else -1
            continue
        if col < 0 or all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        ids = [x for x in cited_ids(" ".join(c for k, c in enumerate(cells) if k != col)) if dates.get(x)]
        if ids:
            best = max(ids, key=lambda x: (dates[x], -int(x[1:])))
            while len(cells) <= col:
                cells.append("")
            cells[col] = f"{dates[best]} [{best}]"
            lines[n] = "| " + " | ".join(cells) + " |"
    return "\n".join(lines) + ("\n" if md.endswith("\n") else "")


def render(out, hub="", title="", abstracts=True):
    """Write out/report.html. abstracts=False leaves publisher abstracts out, e.g. for a page posted publicly."""
    data = json.loads((out / "sources.json").read_text())
    cfg, items = data["config"], data["items"]
    cfg["keywords"] = normalize_keywords(cfg)
    for i in items:  # scans made before profiles became flat keyword lists stored matches by group
        if isinstance(i.get("matched"), dict):
            i["matched"] = [t for g in ("targets", "drugs", "mechanisms") for t in i["matched"].get(g, [])]
    brief = (out / "briefing.md").read_text() if (out / "briefing.md").exists() else ""
    if brief:
        filled = fill_last_mention(brief, items)
        if filled != brief:
            (out / "briefing.md").write_text(filled); brief = filled
    scr = json.loads((out / "screening.json").read_text()) if (out / "screening.json").exists() else screening_from_briefing(brief)
    rows = []
    for i in items:
        sc = scr.get(i["sid"], {})
        rel = sc.get("rel")
        meta = ""
        if i["kind"] == "trial":
            meta = f"{i['id']} · {', '.join(i['phases']) or 'phase n/a'} · {i['status'].replace('_', ' ').lower()} · n={i['enrollment'] or '?'}"
        elif i["kind"] == "eu_trial":
            meta = f"{i['id']} · {i['phase']}"
        elif i.get("authors"):
            meta = i["authors"]
        rows.append({"s": i["sid"], "k": i["kind"], "d": i.get("date", ""), "t": i["title"], "u": i["url"],
                     "v": i.get("venue", ""), "m": label(i), "r": rel if rel is not None else (0 if scr else None),
                     "n": sc.get("note", ""), "a": i.get("abstract", "")[:6000] if abstracts else "", "x": meta})
    payload = {"name": cfg.get("name", "Landscape scan"), "window": data["window"], "status": data["status"],
               "keywords": cfg["keywords"], "hub": hub if hub.startswith("https://") else "", "rows": rows,
               "screened": bool(scr), "generated": date.today().isoformat(), "repo": REPO_URL,
               "ran_at": data.get("generated_at") or datetime.fromtimestamp((out / "sources.json").stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
               "days": (date.fromisoformat(data["window"][1]) - date.fromisoformat(data["window"][0])).days,
               "lookback": cfg.get("days"), "cadence": cfg.get("cadence_days")}
    page = REPORT_HTML.replace("<title>__TITLE__ report</title>", "<title>" + md_inline(title or cfg.get("name", "Landscape scan") + " report") + "</title>")
    page = page.replace("__TITLE__", md_inline(cfg.get("name", "Landscape scan")))
    page = page.replace("__REPO__", REPO_URL).replace("__VERSION__", __version__)
    tables = []
    brief_html = md_to_html(brief, {i["sid"]: i["url"] for i in items}, tables) if brief else "<p class=quiet>No briefing was written for this scan.</p>"
    payload["tables"] = tables
    payload["slug"] = cfg.get("slug") or re.sub(r"[^a-z0-9]+", "-", cfg.get("name", "scan").lower()).strip("-")
    page = page.replace("__BRIEF__", brief_html)
    page = page.replace("__DATA__", json.dumps(payload).replace("<", "\\u003c"))
    (out / "report.html").write_text(page)
    return out / "report.html"


REPORT_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="SourceSweep __VERSION__ (__REPO__)">
<title>__TITLE__ report</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600&display=swap" rel="stylesheet">
<style>
/* Clean intelligence report: navy header band, white page, one blue accent.
   Header: brand, actions, title, window, profile keywords, source status.
   Body: page menu on the left, then figures, source mix, briefing and the filterable source list. */
:root{color-scheme:light;--bg:#fff;--soft:#F6F7F9;--ink:#111827;--mute:#4B5563;--line:#E5E7EB;--faint:#F1F5F9;--accent:#1F4FD8;--navy:#0F172A;--sky:#7DD3FC}
*{box-sizing:border-box;min-width:0}
html,body{margin:0;background:var(--bg);color:var(--ink)}
body{font:16px/1.6 Inter,system-ui,sans-serif;overflow-x:clip}
a{color:var(--accent)}
.disp{font-family:"Space Grotesk",Inter,sans-serif}
.wrap{max-width:1360px;margin:0 auto;padding:0 28px}
.top{background:var(--navy);color:#E2E8F0;padding:24px 0 28px}
.bar1{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:16px}
.brand{display:inline-flex;align-items:center;gap:10px;color:#fff;text-decoration:none;font:600 24px/1 "Space Grotesk",Inter,sans-serif;letter-spacing:-.01em}
.brand:hover,.brand:focus-visible{color:var(--sky);outline:none}
.hbtns{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.hbtn{font:500 14px Inter,sans-serif;min-height:40px;padding:0 14px;border-radius:8px;cursor:pointer;display:inline-flex;align-items:center;gap:8px}
.hbtn:focus-visible{outline:2px solid var(--sky);outline-offset:2px}
.ask{border:1px solid var(--sky);background:#0B2540;color:#E0F2FE}
.ask:hover{background:#12355C}
.pr{border:0;background:#fff;color:var(--navy);font-weight:600}
.askwrap{position:relative}
.tip{position:absolute;right:0;top:48px;width:300px;background:#fff;color:var(--ink);border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.5;box-shadow:0 8px 24px rgba(15,23,42,.25);z-index:4;opacity:0;visibility:hidden;transition:opacity .15s}
.askwrap:hover .tip,.askwrap:focus-within .tip{opacity:1;visibility:visible}
h1{font:600 clamp(30px,4vw,40px)/1.1 "Space Grotesk",Inter,sans-serif;letter-spacing:-.01em;margin:0 0 10px;color:#fff;text-wrap:balance}
.sub{color:#CBD5E1;margin:0;font-size:14px}
.kwrow{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:14px 0 0}
.lbl{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#94A3B8;margin-right:4px}
.kw{display:contents;list-style:none}
.kw li{font-size:12px;background:#1E293B;color:#E0F2FE;border:1px solid #334155;border-radius:999px;padding:3px 10px}
.status{margin:12px 0 0;font-size:14px;color:#86EFAC}
.status.bad{color:#FCA5A5;font-weight:500}
.status.bad a{color:#FCA5A5}
.layout{display:flex;flex-wrap:wrap;gap:48px;align-items:flex-start;padding-top:28px;padding-bottom:56px}
.toc{flex:0 1 168px;max-width:168px;margin-left:-10px;position:sticky;top:16px;display:flex;flex-direction:column;gap:2px;font-size:14px}
.toc .lbl{color:var(--mute);padding:0 10px 8px}
.toc a{padding:7px 10px;border-radius:6px;color:#374151;text-decoration:none}
.toc a:hover,.toc a:focus-visible{background:#EFF6FF;color:var(--accent);outline:none}
.main{flex:999 1 640px;max-width:1080px;display:flex;flex-direction:column;gap:36px}
h2,h3{font:600 22px/1.25 "Space Grotesk",Inter,sans-serif;margin:0 0 12px;scroll-margin-top:16px}
h4{font:600 17px/1.3 Inter,sans-serif;margin:20px 0 6px}
.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(10em,1fr));gap:12px}
.fig{border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.fig span{font-size:12px;color:var(--mute)}
.fig b{display:block;font:600 28px/1.2 "Space Grotesk",Inter,sans-serif}
.card{border:1px solid var(--line);border-radius:10px;padding:18px 20px}
.tape{display:grid;gap:8px}
.tr{display:grid;grid-template-columns:7.5em minmax(0,1fr) 3em;gap:12px;align-items:center;font-size:14px}
.tr button{all:unset;cursor:pointer;color:#374151;border-radius:4px}
.tr button:hover,.tr button:focus-visible{color:var(--accent);outline:2px solid #BFDBFE;outline-offset:2px}
.bar{display:flex;height:12px;border-radius:4px;overflow:hidden;background:var(--faint)}
.bar i{display:block;height:100%}
.r3{background:var(--accent)}.r2{background:#93C5FD}.r1{background:#CBD5E1}.r0{background:#E5E7EB}
.tr .c{text-align:right;font-variant-numeric:tabular-nums;color:var(--mute)}
.key{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px;font-size:13px;color:var(--mute)}
.key i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.brief{display:flex;flex-direction:column}
.brief h3{margin-top:28px}.brief h3:first-child{margin-top:0}
.brief p,.brief li{max-width:72ch}
.brief table{width:100%;border-collapse:collapse;font-size:14px}
.brief th{text-align:left;font-weight:500;color:var(--mute);font-size:12px;background:#F9FAFB;padding:10px 12px;vertical-align:bottom}
.brief td{border-top:1px solid var(--faint);padding:11px 12px;vertical-align:top}
.brief td:first-child{font-weight:600}
.brief td.nw{white-space:nowrap;color:var(--mute)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin:4px 0 10px}
.hrow{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin:28px 0 12px}
.hrow h3{margin:0!important}
.tbar{display:flex;flex-wrap:wrap;gap:8px}
.tbtn{font:500 14px Inter,sans-serif;color:var(--ink);background:#fff;border:1px solid #D1D5DB;border-radius:8px;min-height:40px;padding:0 14px;cursor:pointer}
.tbtn:hover{border-color:var(--mute)}
.tbtn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:var(--navy);color:#fff;padding:10px 16px;border-radius:8px;font:500 15px Inter,sans-serif;opacity:0;pointer-events:none;transition:opacity .2s;max-width:calc(100% - 32px);z-index:5}
.toast.on{opacity:1}
.brief li{margin:6px 0}
.cites{white-space:nowrap}
.cite{display:inline-block;font-size:12px;font-weight:600;text-decoration:none;color:#1E40AF;background:#DBEAFE;border-radius:4px;padding:0 5px;margin-left:3px;line-height:18px}
.cite:hover,.cite:focus-visible{background:var(--accent);color:#fff;outline:none}
.tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 12px}
.tools input{flex:1 1 240px;font:15px Inter,sans-serif;color:var(--ink);background:#fff;border:1px solid #D1D5DB;border-radius:8px;padding:10px 12px;min-height:44px}
.tools input:focus-visible,.chip:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font:500 13px Inter,sans-serif;color:#374151;background:#fff;border:1px solid #D1D5DB;border-radius:999px;padding:8px 14px;min-height:40px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--navy);color:#fff;border-color:var(--navy)}
select{font:15px Inter,sans-serif;color:var(--ink);background:#fff;border:1px solid #D1D5DB;border-radius:8px;padding:9px 10px;min-height:44px}
.count{color:var(--mute);font-size:14px;margin:12px 0 10px}
#list{border:1px solid var(--line);border-radius:10px}
.src{padding:14px 16px;display:grid;grid-template-columns:7em minmax(0,1fr);gap:4px 14px;scroll-margin-top:20px;border-top:1px solid var(--faint)}
.src:first-child{border-top:0}
.src:target{background:#EFF6FF}
.sid{font:600 14px Inter,sans-serif;color:var(--accent)}
.sid em{display:block;font-style:normal;font-weight:600;font-size:12px;margin-top:4px;padding:2px 8px;border-radius:6px;width:max-content}
.g3{background:#DCFCE7;color:#166534}.g2{background:#DBEAFE;color:#1E40AF}.g1,.g0{background:#F3F4F6;color:#374151}
.t{font-weight:500;font-size:16px;text-decoration:none;color:var(--ink);line-height:1.4}
.t:hover,.t:focus-visible{color:var(--accent);text-decoration:underline}
.t::after{content:" ↗";color:var(--mute);font-weight:400}
.meta{color:var(--mute);font-size:13px;margin-top:3px}
.note{margin-top:6px;font-size:15px}
.mt{font-size:13px;color:var(--mute);margin-top:4px}
details{margin-top:6px}
summary{cursor:pointer;color:var(--mute);font-size:14px;min-height:28px}
details p{white-space:pre-wrap;font-size:14px;color:#374151;margin:6px 0 0;overflow-wrap:anywhere}
.quiet{color:var(--mute);padding:14px 16px;margin:0}
footer{color:var(--mute);font-size:13px;border-top:1px solid var(--line);padding-top:14px}
.made{display:inline-flex;align-items:center;gap:6px;margin:0 0 10px;padding:3px 10px;border:1px solid var(--line);border-radius:999px;font-size:12.5px;color:var(--mute);text-decoration:none}
.made b{font-weight:600;color:var(--ink)}
.made:hover,.made:focus-visible{color:var(--ink);border-color:var(--mute)}
.printmark{display:none}
@media print{.made,.hbtns,.toc,.tbar,.tools,.chips{display:none}.top{background:#fff;color:#111}.top h1,.brand{color:#111}.layout{display:block}.printmark{display:block;position:fixed;bottom:0;left:0;right:0;text-align:center;font-size:10px;color:#777;background:#fff;padding:4px 0}}
@media(max-width:900px){.toc{display:none}}
@media(max-width:600px){.wrap{padding:0 16px}.stack thead{display:none}.stack tr{display:grid;padding-block:10px;border-bottom:1px solid var(--line)}.stack td{display:block;position:relative;border:0;padding:2px 0 2px 7.5em;white-space:normal!important}.stack td::before{content:attr(data-l);position:absolute;left:0;width:7em;color:var(--mute);font-weight:500}.tr{grid-template-columns:6em minmax(0,1fr) 2.5em}.src{grid-template-columns:minmax(0,1fr)}.sid{display:flex;gap:8px;align-items:center}.sid em{margin:0}.tip{right:auto;left:0;width:min(300px,80vw)}}
@media(prefers-reduced-motion:no-preference){.bar i{transition:flex-grow .4s}}
</style></head><body>
<header class="top"><div class="wrap">
<div class="bar1">
<a class="brand" href="__REPO__" target="_blank" rel="noopener" aria-label="SourceSweep (opens the source code)"><svg aria-hidden="true" width="30" height="30" viewBox="0 0 26 26" fill="none" stroke="#7DD3FC" stroke-width="2" stroke-linecap="round"><path d="M11 11 L11 3.5 A7.5 7.5 0 0 1 17.5 7.25 Z" fill="#7DD3FC" fill-opacity=".35" stroke="none"></path><circle cx="11" cy="11" r="7.5"></circle><path d="M11 11 L11 4.5"></path><circle cx="11" cy="11" r="1.2" fill="#7DD3FC" stroke="none"></circle><path d="M16.6 16.6 L23 23" stroke-width="2.6"></path></svg>SourceSweep</a>
<div class="hbtns">
<div class="askwrap"><button type="button" class="hbtn ask" id="ask" aria-describedby="asktip"><svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"></path></svg>Ask Claude about these sources</button>
<div class="tip" id="asktip" role="tooltip">Downloads this report's source pack and opens a new Claude chat with a starter prompt (also copied to your clipboard). Drop the file in, and answers will cite the same S# IDs as this report. Nothing is shared until you send.</div></div>
<button type="button" class="hbtn pr" id="print">Print / PDF</button>
</div></div>
<h1 id="title">__TITLE__</h1>
<p class="sub" id="window"></p>
<div class="kwrow"><span class="lbl">Profile keywords</span><ul class="kw" id="kw" aria-label="Profile keywords"></ul><span class="lbl" id="cadence" style="text-transform:none;letter-spacing:0"></span></div>
<p class="status" id="srcstatus"></p>
</div></header>
<div class="wrap layout">
<nav class="toc" id="toc" aria-label="On this page"></nav>
<main class="main">
<div class="figs" id="figs" aria-label="At a glance"></div>
<section class="card" id="mix" aria-labelledby="mixh"><h2 id="mixh" style="font-size:16px;font-family:Inter,sans-serif">Source mix</h2>
<div class="tape" id="tape" aria-label="Sources by type and relevance"></div>
<div class="key" id="key"></div></section>
<section class="brief" id="briefing">
__BRIEF__
</section>
<section id="sources" aria-labelledby="srch">
<h2 id="srch">Sources</h2>
<div class="tools">
<input id="q" type="search" placeholder="Search titles, companies, notes, IDs" aria-label="Search sources">
<select id="rel" aria-label="Relevance"><option value="2">Relevant (2–3)</option><option value="3">Directly relevant (3)</option><option value="0">All sources</option></select>
<select id="sort" aria-label="Sort"><option value="id">By source ID</option><option value="date">Newest first</option><option value="rel">Most relevant first</option></select>
</div>
<div class="chips" id="types" role="group" aria-label="Source types"></div>
<p class="count" id="count"></p>
<div id="list"></div>
</section>
<footer><a class="made" href="__REPO__" target="_blank" rel="noopener">Made with <b>SourceSweep™</b> ↗</a><div id="foot"></div></footer>
</main></div>
<div class="toast" id="toast" role="status"></div>
<div class="printmark">Created with SourceSweep™ · __REPO__</div>
<script id="data" type="application/json">__DATA__</script>
<script>
{
const D = JSON.parse(document.getElementById("data").textContent);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const safe = u => /^https:\/\//.test(u || "") ? u : "";
const KIND = {trial:"US trial", eu_trial:"EU trial", paper:"Paper", preprint:"Preprint", sec:"SEC filing", press:"Trade press", news:"News"};
const REL = {3:"Directly relevant", 2:"Context", 1:"Tangential", 0:"Off-topic"};
const TAG = {3:"Direct", 2:"Context", 1:"Tangential", 0:"Off-topic"};
const SRC = {trials:["US trials (ClinicalTrials.gov)","https://clinicaltrials.gov/"], eu_trials:["EU trials (CTIS)","https://euclinicaltrials.eu/"],
  pubmed:["PubMed","https://pubmed.ncbi.nlm.nih.gov/"], preprints:["Preprints (Europe PMC)","https://europepmc.org/"],
  sec:["SEC filings (EDGAR)","https://www.sec.gov/edgar/search/"], press:["Trade press","https://news.google.com/"], news:["News","https://news.google.com/"]};
const kinds = Object.keys(KIND).filter(k => D.rows.some(r => r.k === k));
const rows = D.rows;
const st = {types:new Set(kinds), q:"", rel:D.screened ? 2 : 0, sort:"id"};
try { const saved = JSON.parse(localStorage.getItem("lw-filter") || "null"); if (saved) { st.rel = saved.rel ?? st.rel; st.sort = saved.sort || st.sort; } } catch (e) {}
document.getElementById("rel").value = String(st.rel);
document.getElementById("sort").value = st.sort;
if (!D.screened) document.getElementById("rel").disabled = true;

const when = iso => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString("en-US", {month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"}); };
document.getElementById("window").textContent = `${D.window[0]} to ${D.window[1]} (${D.days} days) · ${rows.length} sources` + (when(D.ran_at) ? ` · run ${when(D.ran_at)}` : "");
document.getElementById("kw").innerHTML = D.keywords.map(k => `<li>${esc(k)}</li>`).join("");
document.getElementById("cadence").textContent = `${D.lookback || D.days}-day window` + (D.cadence ? ` · runs every ${D.cadence} days` : "");
const n3 = rows.filter(r => r.r === 3).length, n2 = rows.filter(r => r.r === 2).length;
const statusOk = v => /^ok|^skipped/.test(String(v));
const failed = Object.entries(D.status).filter(([, v]) => !statusOk(v)).map(([k]) => k);
const total = Object.keys(D.status).length, sEl = document.getElementById("srcstatus");
if (!failed.length) sEl.textContent = `All ${total} sources verified`;
else { sEl.classList.add("bad");
  sEl.innerHTML = `${total - failed.length} of ${total} sources verified · ` + failed.map(k => { const [name, url] = SRC[k] || [k, ""];
    return `${esc(name)} not reached, so it is missing from this report` + (url ? `: <a href="${esc(url)}" target="_blank" rel="noopener">check it directly ↗</a>` : ""); }).join("; "); }
const nTrials = rows.filter(r => r.k.includes("trial")).length, nPapers = rows.filter(r => r.k === "paper" || r.k === "preprint").length;
const figs = D.screened ? [[n3, "Directly relevant"], [n2, "Context"], [nTrials, "Trials"], [nPapers, "Papers & preprints"]]
  : [[rows.length, "Sources found"], [nTrials, "Trials"], [nPapers, "Papers & preprints"], [kinds.length, "Source types"]];
document.getElementById("figs").innerHTML = figs.map(([v, l]) => `<div class="fig"><span>${esc(l)}</span><b>${esc(v)}</b></div>`).join("");

const max = Math.max(1, ...kinds.map(k => rows.filter(r => r.k === k).length));
document.getElementById("tape").innerHTML = kinds.map(k => {
  const rs = rows.filter(r => r.k === k);
  const seg = [3, 2, 1, 0].map(v => [v, rs.filter(r => (r.r ?? 0) === v).length]).filter(([, c]) => c);
  return `<div class="tr"><button type="button" data-only="${k}" title="Show only ${KIND[k]}">${KIND[k]}</button>
    <div class="bar" style="width:${(rs.length / max * 100).toFixed(1)}%">${seg.map(([v, c]) => `<i class="r${v}" style="flex-grow:${c}" title="${c} ${REL[v].toLowerCase()}"></i>`).join("")}</div>
    <span class="c">${rs.length}</span></div>`;
}).join("");
document.getElementById("key").innerHTML = D.screened ? [3, 2, 1].map(v => `<span><i class="r${v}"></i>${REL[v]}</span>`).join("") + `<span><i class="r0"></i>Off-topic</span>` : `<span>Not yet screened for relevance</span>`;

// Table buttons sit beside the heading of the table they export.
for (const bar of document.querySelectorAll(".brief .tbar")) {
  const h = bar.previousElementSibling;
  if (h && h.tagName === "H3") { const row = document.createElement("div"); row.className = "hrow"; h.replaceWith(row); row.append(h, bar); }
}
// Page menu from the briefing's headings.
const slugify = s => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const toc = [`<span class="lbl">On this page</span>`];
for (const h of document.querySelectorAll(".brief h3")) { h.id = h.id || "b-" + slugify(h.textContent); toc.push(`<a href="#${h.id}">${esc(h.textContent)}</a>`); }
toc.push(`<a href="#sources">Sources (${rows.filter(r => !D.screened || (r.r ?? 0) >= 2).length})</a>`);
document.getElementById("toc").innerHTML = toc.join("");

const tchips = document.getElementById("types");
tchips.innerHTML = kinds.map(k => `<button type="button" class="chip" data-k="${k}" aria-pressed="true">${KIND[k]}</button>`).join("");

function card(r) {
  const u = safe(r.u), relTag = r.r != null && D.screened ? `<em class="g${r.r}">${TAG[r.r]}</em>` : "";
  const title = u ? `<a class="t" href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(r.t)}</a>` : `<span class="t">${esc(r.t)}</span>`;
  const meta = [KIND[r.k], r.v, r.d, r.x].filter(Boolean).map(esc).join(" · ");
  return `<article class="src" id="${esc(r.s)}"><div class="sid">${esc(r.s)}${relTag}</div><div>${title}
    <div class="meta">${meta}</div>${r.n ? `<div class="note">${esc(r.n)}</div>` : ""}
    <div class="mt">Matched: ${esc(r.m)}</div>${r.a ? `<details><summary>${r.k === "sec" ? "Filing excerpts" : r.k.includes("trial") ? "Summary" : "Abstract"}</summary><p>${esc(r.a)}</p></details>` : ""}</div></article>`;
}

function draw() {
  const q = st.q.toLowerCase();
  let list = rows.filter(r => st.types.has(r.k) && (st.rel === 0 || (r.r ?? 0) >= st.rel) &&
    (!q || [r.t, r.v, r.n, r.a, r.m, r.s].join(" ").toLowerCase().includes(q)));
  const num = s => +s.slice(1);
  if (st.sort === "date") list = list.slice().sort((a, b) => (b.d || "").localeCompare(a.d || "") || num(a.s) - num(b.s));
  if (st.sort === "rel") list = list.slice().sort((a, b) => (b.r ?? 0) - (a.r ?? 0) || num(a.s) - num(b.s));
  document.getElementById("count").textContent = `Showing ${list.length} of ${rows.length} sources`;
  document.getElementById("list").innerHTML = list.length ? list.map(card).join("") : `<p class="quiet">No sources match these filters.</p>`;
  for (const b of tchips.querySelectorAll(".chip")) b.setAttribute("aria-pressed", String(st.types.has(b.dataset.k)));
  try { localStorage.setItem("lw-filter", JSON.stringify({rel: st.rel, sort: st.sort})); } catch (e) {}
}

function reveal(id) {
  const r = rows.find(x => x.s === id);
  if (!r) return;
  if (!document.getElementById(id)) { st.types.add(r.k); st.rel = 0; st.q = ""; document.getElementById("q").value = ""; document.getElementById("rel").value = "0"; draw(); }
  const el = document.getElementById(id);
  if (el) { el.scrollIntoView({block:"start"}); const d = el.querySelector("details"); if (d) d.open = true; }
}

tchips.addEventListener("click", e => { const b = e.target.closest(".chip"); if (!b) return;
  st.types.has(b.dataset.k) && st.types.size > 1 ? st.types.delete(b.dataset.k) : st.types.add(b.dataset.k); draw(); });
document.getElementById("tape").addEventListener("click", e => { const b = e.target.closest("[data-only]"); if (!b) return;
  st.types = new Set([b.dataset.only]); draw(); document.getElementById("sources").scrollIntoView({block:"start"}); });
document.getElementById("q").addEventListener("input", e => { st.q = e.target.value; draw(); });
document.getElementById("rel").addEventListener("change", e => { st.rel = +e.target.value; draw(); });
document.getElementById("sort").addEventListener("change", e => { st.sort = e.target.value; draw(); });
document.addEventListener("click", e => { const a = e.target.closest("a.cite"); if (!a) return; e.preventDefault(); reveal(a.dataset.s); try { history.replaceState(null, "", "#" + a.dataset.s); } catch (err) {} });
window.addEventListener("hashchange", () => { if (/^#S\d+$/.test(location.hash)) reveal(location.hash.slice(1)); });

document.getElementById("foot").innerHTML = `Scan run ${esc(when(D.ran_at) || D.generated)} by <a href="${esc(D.repo)}">SourceSweep™</a>, built by Tegan Anderes / Anderes Lab Solutions. Every statement in the briefing cites a numbered source. Source status: ${Object.entries(D.status).map(([k, v]) => esc(k + " " + v)).join(" · ")}.` +
  (safe(D.hub) ? ` <a href="${esc(D.hub)}">Edit profiles and see past scans</a>.` : "");
const toCSV = t => t.map(r => r.map(c => /[",\n]/.test(String(c)) ? `"${String(c).replace(/"/g, '""')}"` : String(c)).join(",")).join("\r\n") + "\r\n";
const toast = m => { const t = document.getElementById("toast"); t.textContent = m; t.classList.add("on"); clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("on"), 3200); };
let dl = null;
(async () => { try { dl = await window.claude?.use?.("downloads"); } catch (e) { dl = null; } })();
async function save(name, text, type) {
  if (dl) { try { await dl.save({filename: name, data: text}); return true; } catch (err) { return err?.code === "declined" ? null : false; } }
  try {
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name;
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); return true;
  } catch (err) { return false; }
}
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-csv],[data-copycsv]"); if (!b) return;
  const n = +(b.dataset.csv ?? b.dataset.copycsv), csv = toCSV(D.tables[n] || []);
  if (b.dataset.copycsv !== undefined) {
    try { await navigator.clipboard.writeText(csv); toast("Table copied. Paste it into Excel or Google Sheets"); } catch (err) { toast("Copying isn't allowed here. Use Download table"); }
    return;
  }
  const ok = await save(`${D.slug || "landscape"}_assets_${D.window[1]}.csv`, "﻿" + csv, "text/csv");
  if (ok) toast("Table saved as CSV"); else if (ok === false) toast("Download isn't available here. Use Copy table");
});

// Ask Claude: the source pack as markdown, plus a starter prompt.
function pack() {
  const L = [`# Source pack: ${D.name}`, `Window: ${D.window[0]} to ${D.window[1]} · generated by SourceSweep`, "",
    "Answer only from these sources and cite their IDs like [S12]. Follow the links for full text.", "",
    `Profile keywords: ${D.keywords.join(", ")}`, "", `## Sources (${rows.length})`];
  for (const r of rows) {
    L.push("", `### [${r.s}] ${r.t}`, `- Type: ${[KIND[r.k], r.v, r.d, r.x].filter(Boolean).join(" · ")}`, `- Link: ${r.u}`);
    if (r.r != null && D.screened) L.push(`- Relevance: ${REL[r.r]}` + (r.n ? ` · ${r.n}` : ""));
    if (r.a) L.push("", "> " + r.a.trim().replace(/\n/g, "\n> "));
  }
  return L.join("\n") + "\n";
}
document.getElementById("ask").addEventListener("click", async () => {
  const name = `${D.slug || "landscape"}_sources_${D.window[1]}.md`;
  const prompt = `I'm attaching a SourceSweep source pack for "${D.name}" (${D.window[0]} to ${D.window[1]}, ${rows.length} sources). Answer only from these sources and cite their IDs like [S12]. If the pack doesn't cover something, say so. My first question: `;
  const ok = await save(name, pack(), "text/markdown");
  try { await navigator.clipboard.writeText(prompt); } catch (err) {}
  window.open("https://claude.ai/new?q=" + encodeURIComponent(prompt), "_blank", "noopener");
  toast(ok ? `Saved ${name}. Drop it into the new Claude chat` : "Couldn't save the source pack here. Download it from the app instead");
});
document.getElementById("print").addEventListener("click", () => window.print());
draw();
if (/^#S\d+$/.test(location.hash)) reveal(location.hash.slice(1));
}
</script></body></html>
"""



def scan(cfg, days, out, log=None):
    """Search every source for cfg["keywords"] over the last `days` days and write index.md,
    sources.md and sources.json to `out`. Returns a summary dict. A failing source is recorded, not raised."""
    log = log or (lambda m: print(m, file=sys.stderr))
    cfg = dict(cfg); cfg["keywords"] = normalize_keywords(cfg)
    if not cfg["keywords"]:
        raise ValueError("config has no keywords")
    end = date.today().isoformat(); start = (date.today() - timedelta(days=days)).isoformat()
    items, status = [], {}
    sources = {"trials": lambda: trials(cfg, start), "eu_trials": lambda: eu_trials(cfg, start),
               "pubmed": lambda: pubmed(cfg, days), "preprints": lambda: preprints(cfg, start, end),
               "sec": lambda: sec_filings(cfg, start, end), "press": lambda: trade_press(cfg, days),
               "news": lambda: news(cfg, days)}
    skip = set(cfg.get("skip_sources") or [])
    for name, fn in sources.items():
        if name in skip:
            status[name] = "skipped"; continue
        try:
            got = fn(); items += got; status[name] = f"ok ({len(got)})"
        except Exception as e:
            status[name] = f"FAILED: {type(e).__name__}: {str(e)[:120]}"
        log(f"{name}: {status[name]}")
    press_keys = {news_key(i["title"]) for i in items if i["kind"] == "press"}
    items = [i for i in items if not (i["kind"] == "news" and news_key(i["title"]) in press_keys)]
    for it in items:
        it["matched"] = matched(cfg, it)
    write(cfg, items, status, start, end, Path(out))
    return {"out": str(out), "window": [start, end], "status": status, "total": len(items),
            "with_keyword_in_text": sum(1 for i in items if i["matched"])}

def main(argv=None):
    ap = argparse.ArgumentParser(prog="sourcesweep")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    s = sub.add_parser("scan"); s.add_argument("--config", required=True); s.add_argument("--days", type=int, default=60)
    s.add_argument("--out", required=True)
    sh = sub.add_parser("show"); sh.add_argument("--out", required=True); sh.add_argument("ids", nargs="+")
    rd = sub.add_parser("render"); rd.add_argument("--out", required=True); rd.add_argument("--hub", default=""); rd.add_argument("--title", default="")
    rd.add_argument("--no-abstracts", action="store_true", help="leave publisher abstracts out of the page")
    a = ap.parse_args(argv)

    if a.cmd == "check":
        res = {}
        for name, url in HOSTS.items():
            try:
                if name == "eu_trials":
                    get(url, timeout=20, json_body={"pagination": {"page": 1, "size": 1}, "searchCriteria": {"containAll": "cancer"}})
                else:
                    get(url, timeout=20, ua=f"{UA_NAME} check@example.com")
                res[name] = "ok"
            except Exception as e:
                res[name] = f"BLOCKED ({type(e).__name__}: {str(e)[:80]})"
        print(json.dumps(res, indent=1))
        sys.exit(0 if all(v == "ok" for v in res.values()) else 1)

    if a.cmd == "show":
        want = {x.strip(",").upper() for x in a.ids}
        text = (Path(a.out) / "sources.md").read_text()
        for block in text.split("\n### ")[1:]:
            if block.split("]")[0].lstrip("[") in want:
                print("### " + block.strip() + "\n")
        return

    if a.cmd == "render":
        print(render(Path(a.out), a.hub, a.title, abstracts=not a.no_abstracts)); return

    cfg = json.loads(Path(a.config).read_text())
    print(json.dumps(scan(cfg, a.days, Path(a.out)), indent=1))


if __name__ == "__main__":
    main()
```
