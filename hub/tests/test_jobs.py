from homestead import catalog
from homestead.jobs import apply, fetch
from homestead.jobs.common import Job, read_status


def test_library_zims_one_per_name(site):
    names = [h.name for _c, h in apply.library_zims()]
    assert names.count("zimgit-medicine_en_2024-08.zim") == 1
    assert "zimgit-medicine_en_2023-01.zim" not in names  # older release isn't served
    assert "orphan_en_all_2025-01.zim" in names           # on disk = served, catalog or not


def test_delete_removed(site):
    catalog.remove("zimgit-medicine_en", delete_files=True)
    with Job("catalog-apply") as job:
        apply.delete_removed(job)
    assert not catalog.zim_files("zimgit-medicine_en")
    assert catalog.local()["removed"]["zimgit-medicine_en"] == {"delete": False}


def test_plan_zim_states(site, monkeypatch):
    rel = {"url": "https://x/zim/other/zimgit-medicine_en_2025-09.zim.meta4", "size": 123, "release": "2025-09"}
    monkeypatch.setattr(fetch.kiwix, "latest", lambda name: rel)
    it = catalog.get("zimgit-medicine_en")
    assert fetch.plan_zim(it)["state"] == "update"
    catalog.change("zimgit-medicine_en", update=False)
    assert fetch.plan_zim(catalog.get("zimgit-medicine_en"))["state"] == "done"
    assert fetch.plan_zim(catalog.get("zimgit-water_en"))["state"] == "pending"


def test_queue(site):
    fetch.queue(["a", "b"])
    fetch.queue(["b", "c"])
    assert fetch.take_queue() == ["a", "b", "c"]
    assert fetch.take_queue() == []


def test_job_status_file(site):
    with Job("books") as job:
        job.item("x", state="done")
    s = read_status("books")
    assert s["state"] == "done" and s["items"]["x"]["state"] == "done"


def test_maps_detailed_area():
    from homestead.jobs import maps
    boxes = {s: (i, i, i + 1, i + 1) for i, s in enumerate(maps.NEIGHBORS)}
    states, bbox = maps.detailed_area("Massachusetts", boxes)
    assert states[0] == "Massachusetts" and set(states[1:]) == {"Connecticut", "New Hampshire", "New York", "Rhode Island", "Vermont"}
    # every neighbor relation is mutual
    for s, ns in maps.NEIGHBORS.items():
        for n in ns:
            assert s in maps.NEIGHBORS[n], (s, n)


def test_split_book_parts_get_catalog_names(site):
    from homestead import catalog
    from homestead.jobs import apply
    from homestead.jobs.common import Job
    catalog.add({"id": "wtnd", "type": "docpage", "page": "https://example.org/", "folder": "wtnd",
                 "title": "Where There Is No Doctor", "category": "medical",
                 "file_names": {"en_wtnd_10.pdf": "Where There Is No Doctor - Ch 10 First Aid.pdf"}})
    d = catalog.docs_dir("medical") / "wtnd"
    d.mkdir(parents=True)
    (d / "en_wtnd_10.pdf").write_bytes(b"%PDF")
    with Job("catalog-apply") as job:
        apply.rename_parts(job)
    assert not (d / "en_wtnd_10.pdf").exists()
    assert (d / "Where There Is No Doctor - Ch 10 First Aid.pdf").exists()
