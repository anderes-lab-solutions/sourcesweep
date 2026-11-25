# SourceSweep™

**Cited competitive landscape scans for biotech.** SourceSweep pulls the last N days of US and EU clinical trials, PubMed papers, preprints, SEC filings, trade press and news,
screens every source for relevance, and writes a briefing where each claim cites its source as `[S12]`.

**[See an example report →](https://anderes-lab-solutions.github.io/sourcesweep/)**
(Claudin 18.2, 60 days, 270 sources. Publisher abstracts are left out of the public example.)

Built by **Tegan Anderes / [Anderes Lab Solutions](https://andereslabsolutions.bio)**.
Licensed under [AGPL-3.0](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/LICENSE): see [License](#license).

---

## What you get

Each scan writes one folder:

| File | What it is |
|---|---|
| `report.html` | The report: summary figures, the briefing (state of the field, a key assets & companies table with CSV export, biology and biomarker signals), and every source, filterable by type and relevance |
| `briefing.md` | The same briefing as Markdown |
| `sources.md` | The **source pack**: every source with its ID, abstract or excerpt, and link. Give it to an AI assistant to ask follow-up questions that come back with citations |
| `sources.json`, `screening.json` | Machine-readable sources and relevance scores |

Scheduled runs also add a **Changes since last scan** section: trial status, phase, enrollment and
date changes, new trials, and how many sources are new.

## Three ways to run it

All three use the same scanner (`sourcesweep/scanner.py`, Python standard library only) and the same report.

| | Who screens the sources | Needs |
|---|---|---|
| **[Claude skill](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/docs/claude-skill.md)**: ask Claude in your own account | Claude, in your chat | A Claude plan with code execution and web access for files. No API key |
| **[Web app](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/docs/app-and-cli.md)** (Streamlit) and **[command line](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/docs/app-and-cli.md)** | The Anthropic API, with your key | Python 3.10+. Without a key you get keyword scores |
| **[Scheduled GitHub runs](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/docs/scheduling.md)** | The Anthropic API, with your key | A fork of this repo. Change tracking between runs |

### Quick start (command line)

```bash
git clone https://github.com/anderes-lab-solutions/sourcesweep
cd sourcesweep
pip install -e .
export SOURCESWEEP_EMAIL=you@example.com   # contact address NCBI and SEC ask API users for
export ANTHROPIC_API_KEY=sk-ant-...           # optional: AI screening and the written briefing
sourcesweep run profiles/claudin-18-2      # report in profiles/claudin-18-2/reports/<date>/
```

### Quick start (Claude skill)

Download `sourcesweep.zip` from the [latest release](https://github.com/anderes-lab-solutions/sourcesweep/releases/latest), upload it
under **Settings → Capabilities → Skills**, allow the source websites (see [the skill guide](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/docs/claude-skill.md)),
then ask:

> Run a SourceSweep scan for a new profile called "KRAS G12D" using exactly these keywords:
> KRAS G12D, G12D inhibitor, pan-KRAS inhibitor. Lookback 60 days.

## Profiles are just your keywords

A profile is a folder in `profiles/` with a `profile.json`:

```json
{
  "name": "Claudin 18.2 (example)",
  "keywords": ["CLDN18.2", "claudin 18.2", "claudin-18.2", "claudin18.2", "CLDN18"],
  "days": 60,
  "cadence_days": 14,
  "context": "Who reads the report and what is in or out of scope. Steers relevance screening.",
  "restrict": {"text": "optional word every paper must mention", "condition": "optional trial condition"}
}
```

The scan searches **only your keywords**. Nothing adds drugs or synonyms for you. Good keywords
are specific: gene symbols, protein names, mechanisms ("CDK2 degrader"), drug code names. Avoid
single common words. Optional keys: `skip_sources` (for example `["sec", "press"]`) and `press_sites`
(replaces the default trade-press domains). See [how it works](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/docs/how-it-works.md).

## Sources

Built for biotech and pharma, but nothing is limited to them: the scan searches whatever keywords
you give it. Papers, preprints, SEC filings and news cover any field of science and industry, the
trade-press list is configurable, and the trial registries can be skipped for non-clinical topics.


| Source | Via | Notes |
|---|---|---|
| US trials | ClinicalTrials.gov API v2 | Active trials plus any updated in the window |
| EU trials | EU CTIS public search | Catches EU-only records |
| Papers | PubMed E-utilities | Title/abstract search, abstracts fetched |
| Preprints | Europe PMC | bioRxiv, medRxiv, Research Square and others |
| SEC filings | EDGAR full-text search | 8-K decks and releases, 10-Q, 10-K, S-1, with short excerpts |
| Trade press | Google News, site-restricted | Fierce, Endpoints, BioSpace, STAT, BioPharma Dive, wires |
| News | Google News | Title-matched; duplicates of trade press dropped |

All are public and keyless, searched on a best-effort basis. Read the [data source notes](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/docs/data-sources.md)
for coverage gaps and terms of use. Patents and conference abstracts are not covered: neither has an
open, keyless API.

## How this differs from hosted trackers

- **Every claim is cited** to a numbered source you can open, and the briefing is told never to add facts that aren't in the sources.
- **Your keywords, not a fixed taxonomy.** Any target, mechanism, biomarker or modality.
- **Seven source types in one pass**, including EU trials, SEC filing excerpts and trade press.
- **The source pack** lets you keep asking questions of the same evidence with any AI assistant.
- **You run it.** In your own Claude account, on your machine, or in your own GitHub repo. Nothing goes through a third-party service.

## Known limitations

- Relevance scores and briefings are screening aids drafted by a language model. Check the cited sources before relying on a finding.
- Search is keyword-based. A program that never names your keywords won't be found, and recall depends on choosing good keywords.
- News and trade-press items are headlines and snippets from Google News, not full articles.
- EU trial dates are last-update dates, so older records can appear.
- Public APIs change and rate-limit. A failing source is reported in the report header; the rest of the scan continues.
- Abstracts and filings belong to their publishers. Reports link to the originals and are meant for internal use.

## Development

```bash
pip install -e ".[dev,app]"
python -m pytest -q                 # offline tests on synthetic data
python tools/build_skill.py         # rebuild the skill after editing scanner.py or skill/SKILL.template.md
streamlit run app.py
```

The skill embeds the scanner, so `tools/build_skill.py --check` runs in CI to keep them in step.
Contributions are welcome: see [CONTRIBUTING.md](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/CONTRIBUTING.md).

## License

SourceSweep is free software under the [GNU Affero General Public License v3.0 only](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/LICENSE).
You can use, study, change and share it. If you distribute it, or run a modified version as a
network service, you must make your source available under the same license. Copies and
modified versions must keep the [NOTICE](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/NOTICE) file and the author attribution it describes.
A commercial license is available for organizations that can't use AGPL software.

## Credit and citation

If you use or build on SourceSweep, please cite it (GitHub shows a "Cite this repository"
button from [CITATION.cff](https://github.com/anderes-lab-solutions/sourcesweep/blob/main/CITATION.cff)).

For custom scans, recurring landscape briefings or help setting this up for your team, contact
[Anderes Lab Solutions](https://andereslabsolutions.bio).
