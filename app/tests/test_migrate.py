"""The one-time move of an older install's files (roles/homestead/files/migrate-layout.py)."""
import json
import subprocess
import sys
from pathlib import Path

ROLE = Path(__file__).resolve().parents[2] / "roles" / "homestead" / "files"


def test_old_files_move_into_the_new_layout(tmp_path):
    core, lib = tmp_path / "core", tmp_path / "library"
    layout = json.loads((ROLE / "old-layout.json").read_text())
    some = dict(list(layout["files"].items())[:5])
    for old in some:
        f = core / "docs" / old
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(old)
    (core / "docs" / "personal").mkdir(parents=True)
    (core / "docs" / "personal" / "deed.pdf").write_text("deed")
    (lib / "kolibri" / "content" / "databases").mkdir(parents=True)
    run = lambda: subprocess.run([sys.executable, str(ROLE / "migrate-layout.py"), str(core), str(lib),
                                  str(ROLE / "old-layout.json")], capture_output=True, text=True, check=True).stdout
    assert "changed" in run()
    for old, new in some.items():
        assert (core / "docs" / new).read_text() == old
        assert not (core / "docs" / old).exists()
    assert (core / "docs" / "family" / "deed.pdf").exists()        # personal -> family
    assert (lib / "courses" / "databases").is_dir() and not (lib / "kolibri").exists()
    assert "changed" not in run()                                   # safe to run again


def test_every_old_document_has_a_place_in_the_new_list():
    """Each old single document lands where the new library list expects it (so it isn't downloaded again)."""
    import os
    os.environ.pop("HOMESTEAD_SETTINGS", None)
    import yaml
    from homestead.library import slug
    lst = yaml.safe_load((ROLE.parents[2] / "library.yaml").read_text())
    expected = set()
    for tid, t in lst["topics"].items():
        for it in t["items"]:
            kind = next((k for k in ("pdf", "epub", "book") if k in it), None)
            if kind:
                expected.add(f"{tid}/{slug(it['title'])}" + ("" if kind == "book" else f".{kind}"))
    layout = json.loads((ROLE / "old-layout.json").read_text())
    targets = {new for new in layout["files"].values() if new.count("/") == 1} | set(layout["folders"].values())
    assert targets == expected
