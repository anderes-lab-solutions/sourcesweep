#!/usr/bin/env python3
"""Build the SourceSweep Claude skill from skill/SKILL.template.md and sourcesweep/scanner.py.

    python3 tools/build_skill.py          # writes skill/sourcesweep/SKILL.md and dist/sourcesweep.zip
    python3 tools/build_skill.py --check  # exit 1 if the committed SKILL.md is out of date

The scanner is embedded in SKILL.md so the skill is one self-contained file that runs in any Claude
session with code execution. Upload the zip under Settings → Capabilities → Skills.
"""
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "sourcesweep"


def build():
    script = (ROOT / "sourcesweep" / "scanner.py").read_text().rstrip("\n")
    version = re.search(r'__version__ = "([^"]+)"', script).group(1)
    template = (ROOT / "skill" / "SKILL.template.md").read_text()
    return template.replace("__VERSION__", version).replace("__SCRIPT__", script), version


def main():
    text, version = build()
    target = ROOT / "skill" / NAME / "SKILL.md"
    if "--check" in sys.argv:
        ok = target.exists() and target.read_text() == text
        print("SKILL.md is up to date" if ok else "SKILL.md is out of date: run python3 tools/build_skill.py")
        sys.exit(0 if ok else 1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    with zipfile.ZipFile(dist / f"{NAME}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{NAME}/SKILL.md", text)
        z.write(ROOT / "LICENSE", f"{NAME}/LICENSE")
        z.write(ROOT / "NOTICE", f"{NAME}/NOTICE")
    print(f"v{version}: wrote {target.relative_to(ROOT)} and dist/{NAME}.zip")


if __name__ == "__main__":
    main()
