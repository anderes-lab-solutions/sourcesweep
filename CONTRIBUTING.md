# Contributing

Issues and pull requests are welcome, especially new public data sources, better relevance
prompts and fixes for API changes.

- Keep `sourcesweep/scanner.py` standard-library only: it is embedded in the Claude skill.
- After changing `scanner.py` or `skill/SKILL.template.md`, run `python tools/build_skill.py` and commit the rebuilt skill.
- Run `python -m pytest -q` before opening a pull request. Tests must not need network access or an API key.
- Don't commit API keys, client profiles or source packs containing publisher abstracts.

By contributing you agree that your contribution is licensed under AGPL-3.0-only, and that
Tegan Anderes / Anderes Lab Solutions may also distribute it under other license terms (this
keeps a commercial license possible for organizations that can't use AGPL software).

## Working on the report design

You don't need the network or an API key to change how reports look. The report is rendered from a
saved scan, so start the live preview and edit the template and styles in `sourcesweep/scanner.py`:

```bash
python tools/preview.py                          # bundled example scan (examples/claudin-18-2, no abstracts)
python tools/preview.py path/to/a/saved/scan     # any folder with sources.json (+ screening.json, briefing.md)
```

Open http://localhost:8765 (or `/app` to see it inside a frame the width of the web app). Each save
re-renders the page and the browser reloads. The scan folder you preview is never modified.
To see the web app itself with saved reports, run `streamlit run app.py`; it reads `profiles/*/reports/`.
