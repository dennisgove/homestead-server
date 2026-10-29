from homestead import courses, documents, library, zims


def test_items_and_files(site):
    ids = {i.id: i for i in library.items()}
    assert set(ids) == {"test-medicine_en_all", "field-doctor", "stop-the-bleed", "c0ffee00c0ffee00c0ffee00c0ffee00"}
    assert [f.name for f in ids["test-medicine_en_all"].zim_files()] == ["test-medicine_en_all_2026-01.zim"]
    assert len(ids["field-doctor"].files()) == 3
    assert ids["stop-the-bleed"].on_disk()


def test_newest_release_wins(site):
    import shutil
    z = site["core"] / "zim"
    shutil.copy(z / "test-medicine_en_all_2026-01.zim", z / "test-medicine_en_all_2026-06.zim")
    assert library.get("test-medicine_en_all").zim_files()[0].name == "test-medicine_en_all_2026-06.zim"


def test_add_and_remove_are_kept_as_changes(site):
    library.add({"pdf": "https://example.org/x.pdf", "title": "Seed Saving", "topic": "family"})
    assert library.get("seed-saving").added
    library.remove("seed-saving")
    assert library.get("seed-saving") is None
    library.remove("stop-the-bleed")
    assert "stop-the-bleed" not in {i.id for i in library.items()}
    assert "stop-the-bleed" in library.changes()["removed"]


def test_chapters_name_themselves(indexed):
    d = next(d for d in documents.shelf("medical") if d["item"] == "field-doctor")
    assert [(p["label"], p["title"]) for p in d["parts"]] == [
        ("Chapter 1", "Burns and Scalds"), ("Chapter 2", "Broken Bones"), ("Glossary", "Words to Know")]


def test_document_search_by_page(indexed):
    hits = documents.search("splint limb")
    assert hits and hits[0]["path"] == "medical/field-doctor/en_fd_02.pdf" and "<mark>" in hits[0]["pages"][0]["snippet"]
    assert documents.search("oak tree")[0]["topic"] == "family"   # loose files are searchable too
    assert documents.search("splint", topic="family") == []


def test_zim_reading_and_search(site):
    b = zims.get_book("test-medicine_en_all")
    assert b.title == "Test Medicine" and b.essential
    assert zims.main_path(b) == "home"
    kind, (mime, content, title) = zims.entry(b, "Burns")
    assert kind == "item" and mime.startswith("text/html") and b"running water" in content
    r = zims.search_book(b, "running water")
    assert r["hits"][0]["path"] == "Burns" and "<mark>" in r["hits"][0]["snippet"]
    groups = zims.search_all("broken bone")
    assert groups and groups[0]["book"].id == "test-medicine_en_all"


def test_courses(indexed):
    root = courses.node("c0ffee00c0ffee00c0ffee00c0ffee00")
    assert [k["title"] for k in root["children"]] == ["Math"]   # "Practice only" has no videos
    v = courses.node("c0ffee00c0ffee00c0ffee00c0ffee00", "v1")
    assert v["files"]["video"].endswith(".mp4") and v["next"]["id"] == "v2" and v["prev"] is None
    assert courses.search("fractions")[0]["url"].startswith("/learn/")


def test_part_names_from_file_names():
    assert documents.part_label("en_wtnd_2025_07.pdf") == "Chapter 7"
    assert documents.part_label("Ch 12.pdf") == "Chapter 12"
    assert documents.part_label("GUIDE03_HomeCan_rev0715.pdf") == "Guide 3"
    assert documents.part_label("en_cgeh_2012_appb.pdf") == "Appendix B"
    assert documents.part_label("en_wtnd_2025_indx.pdf") == "Index"
    order = sorted(["en_x_10.pdf", "en_x_gloss.pdf", "en_x_02.pdf", "en_x_fm.pdf", "en_x_appa.pdf"], key=documents.part_order)
    assert order == ["en_x_fm.pdf", "en_x_02.pdf", "en_x_10.pdf", "en_x_appa.pdf", "en_x_gloss.pdf"]
