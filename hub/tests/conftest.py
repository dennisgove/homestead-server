import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A fake server: essentials and library folders, a catalog, a config."""
    core, lib, state = tmp_path / "core", tmp_path / "library", tmp_path / "state"
    for d in (core / "zim", core / "docs" / "medical", lib / "zim", state / "status", state / "hub", core / "maps"):
        d.mkdir(parents=True)
    (core / "zim" / "zimgit-medicine_en_2024-08.zim").write_bytes(b"x" * 10)
    (lib / "zim" / "zimgit-medicine_en_2023-01.zim").write_bytes(b"x" * 5)    # older duplicate
    (lib / "zim" / "orphan_en_all_2025-01.zim").write_bytes(b"x" * 7)         # not in the catalog
    (core / "docs" / "medical" / "stop-the-bleed.pdf").write_bytes(b"%PDF-1.4")
    (core / "docs" / "medical" / "stray.pdf").write_bytes(b"%PDF-1.4")
    shutil.copy(REPO / "content" / "catalog.yaml", state / "catalog.yaml")
    cfg = {
        "paths": {"core": str(core), "library": str(lib), "state": str(state), "status": str(state / "status"),
                  "hub_state": str(state / "hub"), "docs": str(core / "docs"), "zim_core": str(core / "zim"),
                  "zim_library": str(lib / "zim"), "books": str(lib / "books" / "calibre"),
                  "books_incoming": str(lib / "books" / "incoming"), "maps": str(core / "maps"),
                  "catalog_base": str(state / "catalog.yaml"), "catalog_local": str(state / "hub" / "catalog.local.yaml")},
        "site": {"hostname": "homestead", "lan_name": "library.lan", "ssid": "HOMESTEAD", "region_state": "Massachusetts"},
        "apps": [{"id": "library", "title": "Full library", "icon": "📚", "section": "library", "port": 7001, "scheme": "http",
                  "path": "/", "access": "public", "health": ""},
                 {"id": "core-library", "title": "Essentials", "icon": "📖", "section": "library", "port": 7002,
                  "scheme": "http", "path": "/", "access": "public", "health": ""}],
        "kiwix": {"container": "homestead-kiwix", "core_app": "core-library", "search_url": "http://127.0.0.1:1",
                  "public_url": "http://library.lan:7001", "core_search_url": "http://127.0.0.1:1", "core_public_url": "http://library.lan:7002"},
        "ai": {"ollama": "http://127.0.0.1:1", "fast_model": "qwen3:4b-instruct", "keyword_timeout": 1},
        "power": {"eco": 35, "shutdown": 15}, "content_tier": 3, "admin_header": "",
    }
    p = tmp_path / "hub.json"
    p.write_text(json.dumps(cfg))
    monkeypatch.setenv("HOMESTEAD_CONFIG", str(p))
    from homestead import config
    config.reset()
    yield {"core": core, "lib": lib, "state": state, "cfg": cfg}
    config.reset()
