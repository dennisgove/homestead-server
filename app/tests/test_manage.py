from fastapi.testclient import TestClient

from homestead import library


def client(monkeypatch):
    import homestead.web.manage as m
    monkeypatch.setattr(m, "start", lambda job: True)
    return TestClient(m.app)


def test_pages(site, monkeypatch):
    c = client(monkeypatch)
    for p in ("/", "/items", "/items?t=medical", "/add"):
        assert c.get(p).status_code == 200, p


def test_add_link_and_remove(site, monkeypatch):
    c = client(monkeypatch)
    r = c.post("/add/link", data={"url": "https://example.org/a.pdf", "title": "Seed Saving", "topic": "food" if "food" in library.topics() else "family"},
               follow_redirects=False)
    assert r.status_code == 303 and library.get("seed-saving")
    c.post("/items/stop-the-bleed/remove", data={"delete": "1"})
    assert not (site["core"] / "docs" / "medical" / "stop-the-bleed.pdf").exists()
    assert library.get("stop-the-bleed").id in library.changes()["removed"]
    c.post("/items/stop-the-bleed/restore")
    assert "stop-the-bleed" in {i.id for i in library.items()}


def test_upload(site, monkeypatch):
    c = client(monkeypatch)
    r = c.post("/add/upload", data={"topic": "family"}, files={"file": ("Our Deed.pdf", b"%PDF-1.4", "application/pdf")},
               follow_redirects=False)
    assert r.status_code == 303 and (site["core"] / "docs" / "family" / "Our Deed.pdf").exists()
    assert c.post("/add/upload", data={"topic": "family"}, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400
