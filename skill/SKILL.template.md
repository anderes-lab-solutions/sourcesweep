---
name: "sourcesweep"
description: "Run a SourceSweep competitive landscape scan (also called a landscape scan or Landscape Watch scan) for keyword profiles or ad-hoc keywords: pulls recent US/EU clinical trials, PubMed papers, preprints, SEC filings, trade press and news, screens them for relevance, and publishes a cited HTML report plus a source pack."
---

# SourceSweep™: competitive landscape scan

<!-- Built from https://github.com/anderes-lab-solutions/sourcesweep (v__VERSION__). Copyright 2026 Tegan Anderes / Anderes Lab Solutions. GNU AGPL-3.0-only; keep this attribution (see NOTICE). Edit skill/SKILL.template.md and sourcesweep/scanner.py, then run tools/build_skill.py. -->

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

Read `index.md` first. Then read the abstracts in batches. **Never score a paper, preprint or filing on its title
alone**: a finding about a keyword is often only in the results or conclusions.
```bash
python3 /tmp/sourcesweep.py show --out "$OUT" S3 S7 S12
```
With more than about 80 sources, don't read `sources.md` in one go. Use `show` in batches of about 15.

Score every source against the profile's `context` (or the user's evident scope):
- **3, directly relevant:** about the keywords' subject, its assets or competitors in scope
- **2, relevant context:** mechanism, biomarker, indication, or an adjacent competitor
- **1, tangential:** mentions a keyword in passing
- **0, off-topic**

Judge by the findings and conclusions: a source whose results or conclusions report something about a keyword is at
least 2, even if its main topic is something else. Before writing the scores, re-read in full every source you scored
0 or 1 whose text names a keyword (`grep -il` on `sources.md` helps find them).
Sources marked "Commentary or editorial on [S#]" are not independent evidence: score them, but cite the primary paper.

Type-specific notes:
- **sec**: read the excerpts. 8-K decks and 10-Qs often hold the most decision-relevant facts (dropped trials, IND timing, competitor lists). Boilerplate risk-factor mentions are 1
- **eu_trial**: CTIS status is a numeric code; rely on the last-updated date and title. Flag EU-only trials and ones that differ from the US record
- **press** items marked "(in article text)" have no abstract; judge them by title and company, and don't state facts that aren't in the title

Give each source scored 2 or 3:
- **note**: one sentence on what it adds;
- **type**: clinical trial, observational, preclinical, review, commentary, company statement, registry record or news;
- **limits**: up to 30 words of qualifiers the source itself states that limit its main finding (significant only in a
  subgroup, a non-significant endpoint, small n, the definition or cutoff used, model system, interim data), or "".
Use only facts in the source. Write every score to `$OUT/screening.json`, covering all sources:
```json
{"S1": {"rel": 3, "note": "ASPENOVA confirmatory trial", "type": "registry record", "limits": ""}, "S2": {"rel": 1, "note": ""}}
```

## Step 6: Write the briefing

Report what the sources say and attribute it ("the registry lists...", "the company reported..."). Don't add your own
scientific interpretation, predictions, rankings of assets or strategic recommendations: the reader draws the conclusions.

Rules for every claim:
- Keep the qualifiers from **limits**: a subgroup-only result, a non-significant endpoint, the sample size, the
  definition or cutoff. Leave a finding out rather than state it without the qualifier that changes it.
- Say what kind of evidence it is when it isn't a clinical result (preclinical, observational, review, company statement).
- A general claim ("companies", "studies") cites every source in the pack that supports it, or is narrowed to what it cites.
- When sources complicate or contradict a statement, say so in the same place; when findings point in opposite
  directions, give the condition that separates them if a source states it, otherwise say they disagree.
- Cite a commentary's primary paper, not the commentary, for findings.
- Don't merge different drugs, mechanisms, combinations or definitions into one claim. A source may be cited in more than one section.

**Check before publishing.** Re-read the full text (`show`) of every source the briefing cites and correct any claim
that is unsupported, drops a stated qualifier, rests a general claim on one source, or merges different things.
Then list the sources you scored 2 or 3 but did not cite, and add any that belong in the briefing.

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
__SCRIPT__
```
