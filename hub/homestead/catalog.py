"""The content catalog: the repo baseline plus the Library manager's edits.

baseline  content/catalog.yaml (installed to paths.catalog_base)
local     paths.catalog_local, written only by the Hub:
            added:   [item, ...]           new items
            removed: {id: {delete: bool}}  items to drop (delete=True: the file goes too)
            changed: {id: {field: value}}  overrides on baseline items
"""
import copy
import os
import re
import tempfile
from pathlib import Path

import yaml

from . import config

TYPES = ("zim", "doc", "docpage", "kolibri")
ITEM_DEFAULTS = {"tier": 3, "disk": "library", "ai": False, "binder": False, "update": True}
EDITABLE = ("title", "category", "tier", "disk", "ai", "binder", "update")
ZIM_FILE = re.compile(r"^(?P<name>.+)_(?P<date>\d{4}-\d{2})(?P<rev>[a-z]?)\.zim$")


def _read(path: Path) -> dict:
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def baseline() -> dict:
    return _read(config.path("catalog_base"))


def local() -> dict:
    d = _read(config.path("catalog_local"))
    d.setdefault("added", [])
    d.setdefault("removed", {})
    d.setdefault("changed", {})
    return d


def save_local(d: dict):
    """Write the local edits atomically."""
    p = config.path("catalog_local")
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".catalog.")
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, p)


def normalize(item: dict) -> dict:
    it = {**ITEM_DEFAULTS, **item}
    if it["type"] in ("doc", "docpage"):
        it["disk"] = "core"  # documents always live on the NVMe
    it.setdefault("title", it.get("name") or it["id"])
    return it


def merged(include_removed: bool = False) -> dict:
    """The catalog as the jobs and pages use it."""
    base = baseline()
    loc = local()
    out = {k: v for k, v in base.items() if k != "items"}
    items = []
    for it in base.get("items", []) + loc["added"]:
        it = copy.deepcopy(it)
        it.update(loc["changed"].get(it["id"], {}))
        it = normalize(it)
        it["origin"] = "added" if any(a["id"] == it["id"] for a in loc["added"]) else "baseline"
        if it["id"] in loc["removed"]:
            if not include_removed:
                continue
            it["removed"] = loc["removed"][it["id"]]
        items.append(it)
    out["items"] = items
    return out


def items(tier: int | None = None) -> list[dict]:
    its = merged()["items"]
    return [i for i in its if tier is None or i["tier"] <= tier]


def get(item_id: str) -> dict | None:
    return next((i for i in merged(include_removed=True)["items"] if i["id"] == item_id), None)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", text.lower()).strip("-")[:80] or "item"


def add(item: dict) -> dict:
    """Add an item from the Library manager (or un-remove it if it was removed)."""
    if item.get("type") not in TYPES:
        raise ValueError(f"unknown type {item.get('type')!r}")
    loc = local()
    if item["id"] in loc["removed"]:
        del loc["removed"][item["id"]]
    elif get(item["id"]):
        raise ValueError(f"{item['id']} is already in the catalog")
    else:
        loc["added"].append({k: v for k, v in item.items() if v is not None})
    save_local(loc)
    return get(item["id"])


def change(item_id: str, **fields):
    bad = set(fields) - set(EDITABLE)
    if bad:
        raise ValueError(f"can't change {', '.join(sorted(bad))}")
    loc = local()
    added = next((a for a in loc["added"] if a["id"] == item_id), None)
    if added is not None:
        added.update(fields)
    else:
        loc["changed"].setdefault(item_id, {}).update(fields)
    save_local(loc)


def remove(item_id: str, delete_files: bool):
    """Mark an item removed. The apply job deletes its files (if asked) and tidies up."""
    loc = local()
    loc["removed"][item_id] = {"delete": bool(delete_files)}
    save_local(loc)


def restore(item_id: str):
    loc = local()
    loc["removed"].pop(item_id, None)
    save_local(loc)


def forget_removed(item_id: str):
    """Called by the apply job once a removed item's files are gone."""
    loc = local()
    if item_id in loc["removed"]:
        loc["added"] = [a for a in loc["added"] if a["id"] != item_id]
        loc["changed"].pop(item_id, None)
        # keep a plain "removed" marker for baseline items so they stay removed
        if any(i["id"] == item_id for i in baseline().get("items", [])):
            loc["removed"][item_id] = {"delete": False}
        else:
            del loc["removed"][item_id]
        save_local(loc)


def export_patch() -> str:
    """The local edits as YAML to paste into content/catalog.yaml (or review)."""
    loc = local()
    lines = ["# Local catalog edits, exported from the Library manager.", ""]
    if loc["added"]:
        lines.append("# Add to items:")
        lines.append(yaml.safe_dump(loc["added"], sort_keys=False, allow_unicode=True))
    if loc["changed"]:
        lines.append("# Change these baseline items:")
        lines.append(yaml.safe_dump(loc["changed"], sort_keys=False, allow_unicode=True))
    if loc["removed"]:
        lines.append("# Remove these items:")
        lines.append(yaml.safe_dump(sorted(loc["removed"]), allow_unicode=True))
    return "\n".join(lines)


# --- where things live on disk ------------------------------------------------

def zim_dir(disk: str) -> Path:
    return config.path("zim_core" if disk == "core" else "zim_library")


def docs_dir(category: str) -> Path:
    return config.path("docs") / category


def zim_files(name: str) -> list[Path]:
    """Finished releases of a ZIM on either disk, newest first."""
    found = []
    for disk in ("core", "library"):
        d = zim_dir(disk)
        if not d.is_dir():
            continue
        for f in d.iterdir():
            m = ZIM_FILE.match(f.name)
            if m and m["name"] == name and not Path(str(f) + ".aria2").exists():
                found.append(f)
    return sorted(found, key=lambda p: p.name, reverse=True)


def item_files(it: dict) -> list[Path]:
    """Files on disk that belong to an item."""
    if it["type"] == "zim":
        return zim_files(it["name"])
    if it["type"] == "doc":
        p = docs_dir(it["category"]) / it["file"]
        return [p] if p.exists() else []
    if it["type"] == "docpage":
        d = docs_dir(it["category"]) / it["folder"]
        return sorted(p for p in d.iterdir() if p.is_file() and not p.name.startswith(".")) if d.is_dir() else []
    return []
