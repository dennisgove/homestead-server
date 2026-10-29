"""Where everything lives. Read from the JSON file Ansible writes (/etc/homestead/site.json),
or the file named by $HOMESTEAD_SETTINGS (tests, trying things out)."""
import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT = "/etc/homestead/site.json"


@lru_cache(maxsize=1)
def load() -> dict:
    with open(os.environ.get("HOMESTEAD_SETTINGS", DEFAULT)) as f:
        return json.load(f)


def reset():
    load.cache_clear()


def path(name: str) -> Path:
    """A named place on disk. The basics come from the settings; the rest follow from them."""
    p = load()["paths"]
    core, lib, state = Path(p["core"]), Path(p["library"]), Path(p["state"])
    places = {
        "core": core, "library": lib, "state": state,
        "list": Path(p["list"]),                        # library.yaml
        "changes": state / "changes.yaml",              # additions and removals made on this server
        "index": state / "index.sqlite",                # documents' and courses' search index
        "status": state / "status",                     # job progress, for the Status page
        "docs": core / "docs",
        "maps": core / "maps",
        "share": core / "share",
        "courses": lib / "courses",
        "video": lib / "video",
        "power": Path(p.get("power", "/var/lib/homestead/power.json")),
        "last_backup": Path(p.get("last_backup", "/var/lib/homestead/last-backup")),
    }
    return places[name]


def inside(root: Path, rel: str) -> Path | None:
    """root/rel if it's a file inside root ("../" can't climb out); None otherwise."""
    base = os.path.normpath(root)
    p = os.path.normpath(os.path.join(base, rel))
    return Path(p) if p.startswith(base + os.sep) and os.path.isfile(p) else None


def url_path(p: str) -> str:
    """A file or page path made safe to put in a link (spaces, quotes, &, #, ?)."""
    from urllib.parse import quote
    return quote(p, safe="/:,;=@!$()*+'~-._")


def zim_dir(essential: bool) -> Path:
    return path("core" if essential else "library") / "zim"


def partial_dir(essential: bool) -> Path:
    """Unfinished downloads, kept out of the folders the website reads."""
    return path("core" if essential else "library") / ".partial"


def library_drive_ok() -> bool:
    """The USB library drive is plugged in (not just its empty mount point)."""
    lib = path("library")
    return os.path.ismount(lib) or bool(load().get("library_is_folder"))
