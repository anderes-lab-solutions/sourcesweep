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
