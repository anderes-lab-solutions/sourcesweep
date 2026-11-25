# Scheduled scans with GitHub Actions

`.github/workflows/scan.yml` runs saved profiles and commits each report to
`profiles/<name>/reports/<date>/`. It also keeps a snapshot in `profiles/<name>/history/` so the next
report gets a **Changes since last scan** section: trials that changed status (stopped trials
first), phase, enrollment, start or primary-completion date or primary endpoints, trials new to the
scan, and how many sources are new.

## Set up

1. Fork the repo. For client work, make your copy **private**: see below.
2. Add a profile folder in `profiles/` with a `profile.json` that includes `cadence_days`.
3. In the repo settings, add the secret `ANTHROPIC_API_KEY` (optional) and the variable
   `SOURCESWEEP_EMAIL`.
4. Actions → *scheduled-scan* → *Run workflow*. Enter a profile folder name, or `due`.
5. To run automatically, uncomment the `schedule:` lines in the workflow. It checks weekly, and
   each profile runs only once its `cadence_days` have passed.

## Public and private repos

Abstracts and filing excerpts belong to their publishers. In a **public** repo the workflow
renders reports without abstracts and doesn't commit the source packs (`sources.md`,
`sources.json`). In a **private** repo it commits everything, which is what you want for internal
use and for asking follow-up questions of the source pack.

Keep client profiles and their reports in a private repo. Their keywords and scope notes can
reveal what a client is working on.
