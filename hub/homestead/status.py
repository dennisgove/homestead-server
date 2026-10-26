"""What's up and what isn't: apps, disks, power, backups, jobs. Read by /status and the status strip."""
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config
from .jobs.common import read_status

JOBS = ["fetch", "fetch-plan", "catalog-apply", "books", "maps", "kb-sync"]


def _sh(*cmd) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def disk(path: Path) -> dict | None:
    try:
        u = shutil.disk_usage(path)
    except OSError:
        return None
    return {"total": u.total, "used": u.used, "free": u.free, "mounted": os.path.ismount(path)}


def library_state() -> dict:
    lib = config.path("library")
    src = _sh("findmnt", "-no", "SOURCE", str(lib)).strip()
    return {"mounted": os.path.ismount(lib), "temporary": "lv_library" in src}


def wifi_clients() -> int | None:
    n, found, iface = 0, False, None
    for line in _sh("iw", "dev").splitlines():
        line = line.strip()
        if line.startswith("Interface "):
            iface = line.split()[1]
        elif line == "type AP" and iface:
            found = True
            n += _sh("iw", "dev", iface, "station", "dump").count("Station ")
    return n if found else None


def power() -> dict:
    state = config.path("state")
    try:
        p = json.loads((state / "power.json").read_text())
    except (OSError, ValueError):
        p = None
    return {"reading": p, "eco": (state / "eco").exists()}


def last_backup() -> dict:
    try:
        t = (config.path("state") / "last-backup").stat().st_mtime
        return {"when": int(t), "stale": time.time() - t > 8 * 86400}
    except OSError:
        return {"when": None, "stale": True}


def _check(app: dict) -> dict:
    url = app.get("health")
    if not url:
        return {"id": app["id"], "up": None}
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            ok = r.status < 500
    except urllib.error.HTTPError as e:
        ok = e.code < 500  # 401/403/404 still means it's answering
    except OSError:
        ok = False
    return {"id": app["id"], "up": ok, "ms": int((time.time() - t0) * 1000)}


def apps() -> dict[str, dict]:
    with ThreadPoolExecutor(max_workers=8) as ex:
        return {r["id"]: r for r in ex.map(_check, config.load()["apps"])}


def uptime() -> str:
    try:
        secs = int(float(Path("/proc/uptime").read_text().split()[0]))
    except OSError:
        return "?"
    d, rem = divmod(secs, 86400)
    h, m = divmod(rem // 60, 60)
    return f"{d}d {h}h" if d else f"{h}h {m}m"


def strip() -> dict:
    """The small status strip on every page (cheap: no app checks)."""
    return {"library": library_state(), "wifi": wifi_clients(), "power": power(),
            "backup": last_backup(), "uptime": uptime(), "time": int(time.time())}


def full() -> dict:
    return {**strip(), "apps": apps(),
            "disks": {"core": disk(config.path("core")), "library": disk(config.path("library"))},
            "jobs": {j: read_status(j) for j in JOBS}}
