# How it works

```
profile.json ──► scan ──► sources.json / sources.md / index.md      (scanner.py, standard library)
                   │
                   ▼
                screen ──► screening.json                          (Claude in the skill, or screen.py + API)
                   │
                   ▼
   history/ ──► track ──► "Changes since last scan"                (track.py, scheduled runs only)
                   │
                   ▼
                brief ──► briefing.md                              (Claude, or screen.py + API)
                   │
                   ▼
                render ──► report.html                             (scanner.py)
```

1. **Scan.** Each source is searched for your keywords over the window. Results are deduplicated,
   sorted by type and given IDs S1, S2, … for this run. Each source records which keywords appear
   in its text.
2. **Screen.** Every source gets a relevance score for the reader described in the profile's
   `context`: 3 directly relevant, 2 relevant context, 1 tangential, 0 off-topic. Sources scored 2
   or 3 get a one-line note on what they add.
3. **Track** (scheduled runs). Trial fields are compared with the last run's snapshot.
4. **Brief.** A state-of-the-field summary, a key assets and companies table and biology and
   biomarker bullets are written from the screened sources only, each claim cited. Citations to
   IDs that aren't in the pack are removed. The renderer fills the table's *Last mention* column
   with the date and ID of the newest source each row cites.
5. **Render.** One self-contained HTML file, with no external requests except web fonts.

## Why the scanner is standard-library only

The same file runs inside a Claude skill, where installing packages may not be possible. It is
embedded in the skill's SKILL.md by `tools/build_skill.py`, and CI checks the two are in step.

## Source IDs belong to one run

`[S12]` means source 12 of that run. A new run, or new keywords, renumber everything. Keep each
run's folder together.
