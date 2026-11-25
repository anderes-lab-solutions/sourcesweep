# Changelog

## 1.3.1 (2026-11-25)

- Link check: DOI links (most preprints) are checked at doi.org without following the redirect, since preprint and publisher sites often block automated visits; SEC links use the "name email" User-Agent the SEC asks for. On the KLA year review this verified all 94 links that 1.3.0 could not check.
- Reports no longer list "Relevant sources not cited above"; every relevant source is still in the source list. The skill now checks its uncited relevant sources itself before publishing.
- Reports: wide tables fit without sideways scrolling (citation chips wrap; wider main column); the page menu has arrows, bold labels and drops trailing date ranges in parentheses.
- Web app: Run history lists each run with its date, time and time zone, its type (scheduled, Claude session, baseline or year in review) and an Open button on the same row. The profile overview compares the latest scan with the run saved just before it, including a baseline report.

## 1.3.0 (2026-11-25)

Accuracy and coverage, from a line-by-line review of a client briefing against its sources:
- Screening reads the parts of each abstract that matter (sentences naming a keyword, plus results and conclusions) instead of the first 600 characters. Anything scored tangential or off-topic whose text names a keyword is screened again with the whole abstract.
- Screening records each relevant source's evidence type and the limits it states (subgroup-only results, non-significant endpoints, sample size, definitions, model system). The briefing is written from these, and reports show them under each source.
- New writing rules: keep stated qualifiers, label non-clinical evidence, cite every supporting source for a general claim or narrow it, surface contradicting evidence where it bears, don't merge different drugs or definitions, cite a commentary's primary paper.
- Citation check: before a briefing is saved, a second pass reads the full text of every cited source and corrects unsupported claims, dropped qualifiers and overgeneralizations. Its changes are logged in run.json.
- Commentaries and editorials are detected and linked to the paper they discuss.
- Every report lists relevant sources the briefing doesn't cite, so nothing screened as relevant goes unseen.
- The Claude skill follows the same screening and writing rules, including never scoring on a title alone.

App and reports:

- Web app: a profile overview page for each profile, laid out like the report: keywords and schedule, figure cards (sources screened, directly relevant, new since the last run, sources verified), what changed since the last routine scan, the key assets table, source mix and recent runs.
- Web app: dark sidebar with the SourceSweep mark, navigation, a watchlist of profiles, AI screening settings and links to the source code, docs, changelog and issues.
- Profile forms show grey example text in every field; examples are never saved into a profile.
- Every source found is now checked: each link is opened once during the scan and recorded as ok, broken (404/410) or couldn't be checked. Reports say "All 7 databases searched · N of M source links verified" and flag broken links in red; the app's "Sources verified" card counts them. Skip with `scan --no-link-check`.
- The app's subtitle sits under the name in the sidebar instead of at the top of the page.
- New `sourcesweep.overview` module: the overview's numbers, read only from saved run files. One-off runs such as a year in review are listed but not used for routine comparisons.

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
