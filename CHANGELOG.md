# Changelog

## 1.2.0 (2026-11-25)

- New report design: navy header with the SourceSweep mark, profile keywords, window and schedule, and a source status line ("All 7 sources verified", or which source wasn't reached with a link to check it directly). A page menu on the left, figure cards, source mix, then the briefing and source list.
- "Ask Claude about these sources": downloads the report's source pack, opens a new Claude chat with a starter prompt (also copied to the clipboard).
- Table export buttons sit beside the table's heading ("Download table (CSV)", "Copy table"); Print / PDF button.
- Web app and report pages use the SourceSweep logo as their browser-tab icon.
- Web app: matching palette, logo and type; the title no longer sits under Streamlit's top bar.
- `render --heading` sets the page heading for special runs (e.g. a year in review); the header shows the scan's real window length.

## 1.1.0 (2026-11-24)

- Screening cache for tracked profiles: sources are always fetched fresh, but AI relevance scores are reused for sources whose text hasn't changed, under unchanged keywords and scope (`history/screening_cache.json`). Only new or changed sources go to the API.
- Quiet runs: when nothing new is relevant and no tracked trial changed, the briefing call is skipped and the report says "No material changes since the last scan".
- `run.json` records `screening_reused` and `briefing_skipped`.
- Update briefings lead with "Changes since last scan", above the state of the field.
- Briefings report and attribute what sources say, with no added interpretation, predictions or recommendations.
- Report tables: only date and ID columns stay on one line; the last column (e.g. "What happened") now wraps.
- CI tests on Python 3.14.

## 1.0.1 (2026-11-25)

- Reports carry a "Made with SourceSweep™" badge linking to this repository, a credit line on printed/PDF pages, and a generator tag.
- New web app: a profiles page (cards with keywords, scope, latest report, run now), report viewer, one-off scans and run history. The app now lives in the package (`sourcesweep.webapp`), so your own repo can host it with a one-line `streamlit_app.py`.
- PyPI publishing through GitHub trusted publishing.

## 1.0.0 (2026-11-24)

First public release of SourceSweep™, under AGPL-3.0-only.

- Seven sources in one scan: ClinicalTrials.gov, EU CTIS, PubMed, Europe PMC preprints, SEC EDGAR full-text search with excerpts, trade press and news.
- Profiles are only the user's keywords, plus an optional scope note, lookback and restrictions.
- One scanner for every way of running it: Claude skill, web app, command line and scheduled GitHub runs.
- Report: briefing with a key assets & companies table (CSV export, automatic "Last mention" column), relevance-filtered source list, run time and window length.
- Relevance screening and briefing through the Anthropic API for unattended runs, with a keyword fallback.
- Trial change tracking between scheduled runs.
- `--no-abstracts` for reports that will be posted publicly.

Development history before this release, under the working name Landscape Watch, is in the author's private repository (started November 2026).
