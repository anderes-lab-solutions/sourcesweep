# Web app and command line

Both run the whole pipeline unattended: scan, screen with the Anthropic API, write the
briefing and render the report. Without an API key they still run and score sources by keyword
(2 = keyword in the title, 1 = keyword only in the text), with no written briefing.

## Install

```bash
pip install -e .          # command line only: no third-party dependencies
pip install -e ".[app]"   # adds Streamlit for the web app
```

Environment variables:

| Name | Needed for |
|---|---|
| `SOURCESWEEP_EMAIL` | The contact address NCBI and the SEC ask API users to send. Please set it |
| `ANTHROPIC_API_KEY` | AI screening and the written briefing (optional) |
| `SOURCESWEEP_MODEL` | Overrides the model (default in `sourcesweep/screen.py`) |

## Command line

```bash
sourcesweep run profiles/claudin-18-2            # full run; tracks changes in profiles/claudin-18-2/history/
sourcesweep run my-profile.json --days 30 --no-ai
sourcesweep due                                  # run every profile whose cadence_days have passed
sourcesweep check                                # can each source be reached from here?
```

The low-level steps the Claude skill uses are also available: `scan`, `show`, `render`
(`sourcesweep render --out DIR --no-abstracts` leaves publisher abstracts out of the page).

**Cost.** Screening sends about 40 sources per API call and the briefing is one more call. A
60-day scan of 200 to 400 sources is typically 6 to 12 calls. `run.json` in each output folder
records the calls and tokens used.

## Web app

```bash
streamlit run app.py
```

- **Profiles**: one card per saved profile with its keywords, scope, latest scan and buttons to open the
  latest report, run a fresh scan or download `profile.json`. The newest report is featured at the top.
  *Add a profile* creates a new one.
- **One-off scan**: type keywords and run a scan without saving a profile.
- **History**: every saved report across profiles, newest first.

Reports open inside the app with download buttons (report, source pack, briefing, or everything as a zip).

### Host it from your own repo

The app is part of the package, so a private repo of your own profiles can host it with one file,
`streamlit_app.py`:

```python
from sourcesweep.webapp import main

main(profiles_dir="profiles", title="Client scans", subtitle="Powered by SourceSweep")
```

and a `requirements.txt` containing `sourcesweep[app]` (or a pinned git URL). Reports committed by the
scheduled workflow to `profiles/<name>/reports/` then show up on the Profiles and History pages.

### Deploy on Streamlit Community Cloud

1. *Create app* → pick the repo, branch `main` and the app file (`app.py` here, `streamlit_app.py` in your own repo).
2. *Advanced settings* → Python 3.12, and secrets:

   ```toml
   APP_PASSWORD = "..."                  # recommended for anything private, and if you add your key
   SOURCESWEEP_EMAIL = "you@example.com"
   ANTHROPIC_API_KEY = "sk-ant-..."      # optional: without it visitors paste their own key or get keyword scores
   ```
3. Deploy. Files the app writes (new profiles, scans run from the app) are temporary on Streamlit Cloud:
   commit `profile.json` files to the repo, and let the scheduled GitHub workflow produce saved reports.

Each browser session is limited to 10 runs. If you host it with your own key, you pay for every visitor's
scans, so set a password or leave the key out. Under the AGPL, a hosted copy must offer its users the
source: the sidebar link does that, so keep it.
