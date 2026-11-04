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
emptied = set()          # folders files were moved out of: the only ones tidied away afterwards


def move(src: Path, dst: Path):
    global changed
    if not src.exists() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.rename(src, dst)
    emptied.add(src.parent)
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
# Folders this left empty go, and their parents if that leaves them empty too; never a folder it didn't
# move anything out of (the website's empty binder-covers folder, say, which setup makes just before this).
for d in sorted(emptied, key=lambda p: len(p.parts), reverse=True):
    while d != docs and docs in d.parents:
        try:
            d.rmdir()      # only if empty
        except OSError:
            break
        d = d.parent
if (lib / "kolibri" / "content").is_dir() and not (lib / "courses").exists():
    os.rename(lib / "kolibri" / "content", lib / "courses")
    changed += 1
    shutil.rmtree(lib / "kolibri", ignore_errors=True)
print(f"moved {changed}" + (" changed" if changed else ""))
