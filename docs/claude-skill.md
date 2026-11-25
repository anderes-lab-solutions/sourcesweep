# The SourceSweep Claude skill

The skill lets anyone with a Claude plan run a scan in their own Claude chat. Claude runs the
scanner, reads and screens the sources itself, writes the briefing and publishes the report. No API
key is needed and nothing is billed to you beyond your Claude plan.

## Install (once)

1. **Allow the source websites.** In Claude: Settings → Capabilities → Create and edit files → turn on
   *Use the internet while making files*. Under *Allowed websites*, add:
   `clinicaltrials.gov`, `euclinicaltrials.eu`, `eutils.ncbi.nlm.nih.gov`, `www.ebi.ac.uk`,
   `news.google.com`, `efts.sec.gov`, `www.sec.gov` (or allow all sites).
   On Team and Enterprise plans an admin manages this.
2. **Upload the skill.** Download `sourcesweep.zip` from the
   [latest release](https://github.com/anderes-lab-solutions/sourcesweep/releases/latest).
   Upload it under Settings → Capabilities → Skills, without unzipping it, and make sure it is switched on.
3. **Start a new chat** so both settings apply.

Menu names change from time to time. If a setting isn't where this says, search Claude's help
center for "skills" and "allowed websites".

## Run a scan

Paste a request like this into a new chat:

> Run a SourceSweep scan for a new profile called "<name>" using exactly these keywords:
> <keyword 1>, <keyword 2>, <keyword 3>. Lookback 60 days.
> Scope: <who reads it and what is in or out of scope>.

Options you can add in plain words:

- a lookback from 7 to 120 days
- "papers must mention breast" (restricts papers and preprints)
- "limit trials to ovarian cancer" (restricts US trials)
- "skip SEC filings" or "skip trade press"

Claude will first check that each source is reachable. If one shows BLOCKED, that website is
missing from your allowed list. A run takes a few minutes. You get the report as a page plus
`briefing.md` and `sources.md`. Keep asking questions in the same chat and Claude answers from the
source pack, with citations.

## Why the skill uses only your keywords

The skill is told to use the keywords exactly as given and never add drugs, assets or synonyms
on its own. That keeps every scan reproducible and makes you the one who decides what is tracked.
Claude may suggest a missing term in one line at the end. You decide whether to add it.

## Build it yourself

The skill is generated from `skill/SKILL.template.md` and `sourcesweep/scanner.py`:

```bash
python tools/build_skill.py     # writes skill/sourcesweep/SKILL.md and dist/sourcesweep.zip
```
