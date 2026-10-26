import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .. import config


class Job:
    """Status file + single-instance lock for one job."""

    def __init__(self, name: str):
        self.name = name
        self.status_path = config.path("status") / f"{name}.json"
        self.status = {"job": name, "state": "running", "started": int(time.time()), "finished": None,
                       "message": "", "current": "", "done": 0, "total": 0, "items": {}}
        self._lock = None

    def __enter__(self):
        config.path("status").mkdir(parents=True, exist_ok=True)
        self._lock = open(config.path("status") / f".{self.name}.lock", "w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit(f"{self.name} is already running")
        prev = read_status(self.name)
        self.status["items"] = prev.get("items", {}) if prev else {}
        self.save()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.status["finished"] = int(time.time())
        if exc_type and exc_type is not SystemExit:
            self.status["state"] = "failed"
            self.status["message"] = f"{exc_type.__name__}: {exc}"
        elif self.status["state"] == "running":
            self.status["state"] = "done"
        self.status["current"] = ""
        self.save()
        return False

    def save(self):
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.status, indent=1))
        os.replace(tmp, self.status_path)

    def log(self, msg: str):
        print(msg, flush=True)
        self.status["message"] = msg
        self.save()

    def item(self, item_id: str, **fields):
        cur = self.status["items"].setdefault(item_id, {})
        cur.update(fields, updated=int(time.time()))
        self.save()


def read_status(name: str) -> dict | None:
    try:
        return json.loads((config.path("status") / f"{name}.json").read_text())
    except (OSError, ValueError):
        return None


def free_bytes(p: Path) -> int:
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def is_mounted(p: Path) -> bool:
    return os.path.ismount(p)


def start_unit(unit: str):
    """Start another job without waiting (systemd)."""
    subprocess.run(["systemctl", "start", "--no-block", unit], check=False)


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.1f} {u}" if u != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"
