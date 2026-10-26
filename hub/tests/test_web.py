from fastapi.testclient import TestClient

from homestead import catalog


def client():
    from homestead.web.app import app
    return TestClient(app)


def test_pages_render(site):
    c = client()
    for path in ["/", "/emergency", "/maps", "/binder", "/status", "/library", "/library/items", "/library/add",
                 "/library/health", "/library/updates", "/api/apps", "/api/catalog", "/api/status"]:
        r = c.get(path)
        assert r.status_code == 200, (path, r.text[:500])
    assert "MEDICAL EMERGENCY" in c.get("/").text
    assert "stop-the-bleed" in c.get("/").text


def test_health_finds_orphans_and_dupes(site):
    from homestead.web.app import health
    h = health()
    assert any(o["name"] == "orphan_en_all" for o in h["orphans"])
    assert any(o["name"] == "stray.pdf" for o in h["orphans"])
    assert any(r["id"] == "zimgit-medicine_en" for r in h["dupes"])


def test_change_and_remove_via_forms(site, monkeypatch):
    import homestead.web.app as web
    monkeypatch.setattr(web, "run_job", lambda *a, **k: True)
    c = client()
    r = c.post("/library/items/zimgit-water_en", data={"field": "tier", "value": "1"}, follow_redirects=False)
    assert r.status_code == 303 and catalog.get("zimgit-water_en")["tier"] == 1
    c.post("/library/items/zimgit-water_en/remove", data={"delete": "1"})
    assert catalog.get("zimgit-water_en")["removed"]["delete"] is True


def test_upload(site, monkeypatch):
    import homestead.web.app as web
    monkeypatch.setattr(web, "run_job", lambda *a, **k: True)
    c = client()
    r = c.post("/library/upload", data={"title": "My Guide", "category": "food", "ai": "1"},
               files={"file": ("My Guide.pdf", b"%PDF-1.4 hi", "application/pdf")}, follow_redirects=False)
    assert r.status_code == 303
    assert (site["core"] / "docs" / "food" / "my-guide.pdf").exists()
    it = catalog.get("my-guide")
    assert it and it["ai"] is True and it["url"] is None if "url" in it else True


def test_admin_header_enforced(site, monkeypatch):
    import json
    from homestead import config
    p = config.load()
    p["admin_header"] = "s3cret"
    c = client()
    assert c.get("/library").status_code == 403
    assert c.get("/library", headers={"x-homestead-admin": "s3cret"}).status_code == 200
    assert c.get("/").status_code == 200


def test_places(site):
    import sqlite3
    db = site["core"] / "maps" / "places.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE VIRTUAL TABLE places USING fts5(name, kind, admin, lat UNINDEXED, lon UNINDEXED, score UNINDEXED)")
    con.execute("INSERT INTO places VALUES ('Concord','PPL','MA, US',42.46,-71.35,1000000000)")
    con.commit()
    con.close()
    r = client().get("/api/places", params={"q": "conc"})
    assert r.json()[0]["name"] == "Concord"
