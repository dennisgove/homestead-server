"""Background jobs (download, index, maps): one at a time each, with progress in a JSON file
the Status page reads."""
import fcntl
import json
import os
import time
from pathlib import Path

from . import settings

JOBS = {"fetch": "Download and update the library", "index": "Index documents and courses for search",
        "maps": "Build the offline maps"}


class Job:
    def __init__(self, name: str):
        self.name = name
        self.file = settings.path("status") / f"{name}.json"
        self.state = {"job": name, "state": "running", "started": int(time.time()), "finished": None,
                      "step": "", "done": 0, "total": 0, "log": [], "items": {}}
        self._lock = None

    def __enter__(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = open(self.file.with_suffix(".lock"), "w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit(f"{self.name} is already running")
        prev = read(self.name) or {}
        self.state["items"] = prev.get("items", {})
        self.save()
        return self

    def __exit__(self, kind, exc, tb):
        self.state["finished"] = int(time.time())
        if kind and kind is not SystemExit:
            self.state["state"] = "failed"
            self.say(f"failed: {kind.__name__}: {exc}")
        elif self.state["state"] == "running":
            self.state["state"] = "done"
        self.state["step"] = ""
        self.save()
        return False

    def save(self):
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1))
        os.chmod(tmp, 0o644)
        os.replace(tmp, self.file)

    def say(self, msg: str):
        print(msg, flush=True)
        self.state["log"] = (self.state["log"] + [f"{time.strftime('%H:%M')} {msg}"])[-40:]
        self.save()

    def step(self, text: str, done: int | None = None, total: int | None = None):
        self.state["step"] = text
        if done is not None:
            self.state["done"] = done
        if total is not None:
            self.state["total"] = total
        self.save()

    def item(self, item_id: str, **fields):
        self.state["items"].setdefault(item_id, {}).update(fields, at=int(time.time()))
        self.save()


def read(name: str) -> dict | None:
    try:
        return json.loads((settings.path("status") / f"{name}.json").read_text())
    except (OSError, ValueError):
        return None


def free(p: Path) -> int:
    import shutil
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def human(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"
