# Changelog

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
