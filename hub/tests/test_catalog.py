from homestead import catalog


def test_merge_add_change_remove(site):
    base_ids = {i["id"] for i in catalog.items()}
    assert "zimgit-medicine_en" in base_ids
    catalog.add({"id": "new_zim", "type": "zim", "name": "new_zim", "category": "food", "tier": 1, "disk": "core"})
    assert catalog.get("new_zim")["origin"] == "added"
    catalog.change("zimgit-medicine_en", tier=2, ai=True)
    it = catalog.get("zimgit-medicine_en")
    assert it["tier"] == 2 and it["ai"] is True
    catalog.remove("zimgit-medicine_en", delete_files=True)
    assert "zimgit-medicine_en" not in {i["id"] for i in catalog.items()}
    assert catalog.get("zimgit-medicine_en")["removed"] == {"delete": True}
    catalog.restore("zimgit-medicine_en")
    assert "zimgit-medicine_en" in {i["id"] for i in catalog.items()}


def test_docs_always_core(site):
    catalog.add({"id": "d", "type": "doc", "url": "http://x/y.pdf", "file": "y.pdf", "category": "medical", "disk": "library"})
    assert catalog.get("d")["disk"] == "core"


def test_zim_files_newest_first(site):
    files = catalog.zim_files("zimgit-medicine_en")
    assert [f.name for f in files] == ["zimgit-medicine_en_2024-08.zim", "zimgit-medicine_en_2023-01.zim"]


def test_forget_removed_keeps_baseline_marker(site):
    catalog.remove("zimgit-water_en", delete_files=True)
    catalog.forget_removed("zimgit-water_en")
    assert catalog.local()["removed"]["zimgit-water_en"] == {"delete": False}
    catalog.add({"id": "tmp", "type": "zim", "name": "tmp", "category": "food"})
    catalog.remove("tmp", delete_files=True)
    catalog.forget_removed("tmp")
    assert "tmp" not in catalog.local()["removed"]
    assert catalog.get("tmp") is None


def test_export_patch(site):
    catalog.add({"id": "x", "type": "zim", "name": "x", "category": "food"})
    assert "x" in catalog.export_patch()


def test_unknown_field_rejected(site):
    import pytest
    with pytest.raises(ValueError):
        catalog.change("zimgit-water_en", name="nope")
