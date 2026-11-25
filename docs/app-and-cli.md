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

Pick a saved profile or type your own keywords, set the lookback, and run. The app shows the
report and offers downloads (report, source pack, briefing, or everything as a zip). The
*Saved reports* tab shows reports committed to `profiles/*/reports/`.

To host it (for example on Streamlit Community Cloud), add secrets:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."      # or leave it out and let visitors paste their own key
APP_PASSWORD = "..."                  # optional password gate
SOURCESWEEP_EMAIL = "you@example.com"
```

Each browser session is limited to 10 runs. If you host it with your own key, you pay for every
visitor's scans, so set a password or leave the key out.
