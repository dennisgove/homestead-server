"""Settings, from /etc/homestead/hub.json (written by Ansible, roles/hub).

HOMESTEAD_CONFIG points somewhere else for development and tests.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT = "/etc/homestead/hub.json"


@lru_cache(maxsize=1)
def load() -> dict:
    with open(os.environ.get("HOMESTEAD_CONFIG", DEFAULT)) as f:
        return json.load(f)


def path(key: str) -> Path:
    return Path(load()["paths"][key])


def reset():
    """Forget the cached settings (tests)."""
    load.cache_clear()
