#!/usr/bin/env python3
"""One-time move of an older install's files into this layout (nothing is downloaded again):

    docs/<old category>/<file>          -> docs/<topic>/<name from the title>   (old-layout.json)
    docs/<category>/<book>/<renamed>    -> docs/<topic>/<book>/<name as downloaded>
    anything else under docs/<category> -> docs/<topic>/ (same relative path)
    library/kolibri/content             -> library/courses

Safe to run again: anything already moved is skipped. Prints "changed" when it moved something.
"""
import json
import os
import shutil
import sys
from pathlib import Path

core, lib, layout = Path(sys.argv[1]), Path(sys.argv[2]), json.load(open(sys.argv[3]))
docs = core / "docs"
changed = 0


def move(src: Path, dst: Path):
    global changed
    if not src.exists() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.rename(src, dst)
    changed += 1


for old, new in layout["files"].items():
    move(docs / old, docs / new)
for old in layout["folders"]:
    (docs / old / ".title").unlink(missing_ok=True)
for old_cat, topic in layout["topics"].items():
    src = docs / old_cat
    if old_cat == topic or not src.is_dir():
        continue
    for f in sorted(src.rglob("*")):
        if f.is_file():
            rel = f.relative_to(src)
            if len(rel.parts) > 1 and f"{old_cat}/{rel.parts[0]}" in layout["folders"]:
                rel = Path(layout["folders"][f"{old_cat}/{rel.parts[0]}"]).relative_to(topic).joinpath(*rel.parts[1:])
            move(f, docs / topic / rel)
for d in sorted((p for p in docs.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
    try:
        d.rmdir()          # only empty ones
    except OSError:
        pass
if (lib / "kolibri" / "content").is_dir() and not (lib / "courses").exists():
    os.rename(lib / "kolibri" / "content", lib / "courses")
    changed += 1
    shutil.rmtree(lib / "kolibri", ignore_errors=True)
print(f"moved {changed}" + (" changed" if changed else ""))
