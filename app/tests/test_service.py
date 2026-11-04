"""The website's service runs with the disk read-only (ProtectSystem=strict): every folder setup makes for
it to write to must be listed in its ReadWritePaths, or writing there fails without a word."""
from pathlib import Path

import yaml

TASKS = Path(__file__).resolve().parents[2] / "roles" / "homestead" / "tasks" / "main.yml"


def test_the_website_can_write_its_folders():
    tasks = yaml.safe_load(TASKS.read_text())
    folders = next(t for t in tasks if t.get("name", "").startswith("Folders the website writes to"))
    mine = [i["path"] for i in folders["loop"] if i["owner"] == "homestead"]
    units = next(t for t in tasks if t.get("name") == "Services and timers")["loop"]
    site = next(u for u in units if u["name"] == "homestead-site.service")["content"]
    assert "ProtectSystem=strict" in site
    writable = next(l for l in site.splitlines() if l.startswith("ReadWritePaths=")).split("=", 1)[1]
    assert mine and all(f"{p} " in writable + " " for p in mine)
