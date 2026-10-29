from fastapi.testclient import TestClient

from homestead import catalog


def client():
    from homestead.web.app import app
    return TestClient(app)


def test_pages_render(site):
    c = client()
    for path in ["/", "/emergency", "/maps", "/binder", "/status", "/videos", "/topic/medical", "/topic/personal",
                 "/search", "/search?q=bleeding", "/search?q=bleeding&topic=medical", "/ask", "/tools",
                 "/library", "/library/items", "/library/add",
                 "/library/health", "/library/updates", "/api/apps", "/api/catalog", "/api/status"]:
        r = c.get(path)
        assert r.status_code == 200, (path, r.text[:500])
    home = c.get("/").text
    assert "Medical emergency" in home and "/topic/medical" in home
    assert "/docs/medical/stop-the-bleed.pdf" in c.get("/topic/medical").text
    assert c.get("/topic/nonsense").status_code == 404


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


def test_example_module_loads_when_enabled(site, monkeypatch):
    import importlib
    import homestead.web.modules.example as ex
    monkeypatch.setattr(ex, "enabled", True)
    import homestead.web.app as web
    web = importlib.reload(web)
    from fastapi.testclient import TestClient
    c = TestClient(web.app)
    assert c.get("/api/example").json() == {"ok": True}
    assert "Hello from a Hub module." in c.get("/example").text
    assert ">Example<" in c.get("/").text


def test_videos_page(site):
    d = site["lib"] / "video" / "Repair"
    d.mkdir(parents=True)
    (d / "fix_a_leak.mp4").write_bytes(b"x")
    c = client()
    assert "fix a leak" in c.get("/videos").text
    r = c.get("/videos", params={"play": "Repair/fix_a_leak.mp4"})
    assert "<video" in r.text and "/videos/files/Repair/fix_a_leak.mp4" in r.text


def test_split_book_parts_titled_the_same_everywhere(site):
    from homestead import catalog
    from homestead.jobs import books
    catalog.add({"id": "wtnd", "type": "docpage", "page": "https://example.org/", "folder": "wtnd",
                 "title": "Where There Is No Doctor (Hesperian)", "category": "medical",
                 "file_names": {"x.pdf": "Where There Is No Doctor - Vocabulary.pdf"}})
    d = catalog.docs_dir("medical") / "wtnd"
    d.mkdir(parents=True)
    (d / ".title").write_text("Where There Is No Doctor (Hesperian)")
    (d / "Where There Is No Doctor - Vocabulary.pdf").write_bytes(b"%PDF")
    (d / "other_part.pdf").write_bytes(b"%PDF")
    want = {"Where There Is No Doctor - Vocabulary", "Where There Is No Doctor (Hesperian): other part"}
    assert want <= {t for f, t, _ in books.sources()}
    from homestead import content
    book = next(d for d in content.documents("medical") if d["parts"])
    assert book["title"] == "Where There Is No Doctor (Hesperian)"
    assert {p["title"] for p in book["parts"]} == {"Vocabulary", "other part"}


def test_document_index_and_search(site):
    from homestead import docindex
    from homestead.jobs import docindex as job
    (site["core"] / "docs" / "water").mkdir()
    (site["core"] / "docs" / "water" / "boiling.txt").write_text("Bring water to a rolling boil for one minute.")
    job.main()
    hits = docindex.search("rolling boil")
    assert hits and hits[0]["path"] == "water/boiling.txt" and "<mark>" in hits[0]["pages"][0]["snippet_html"]
    assert docindex.search("rolling boil", category="medical") == []
    assert "boiling.txt" in client().get("/search", params={"q": "rolling boil"}).text
    (site["core"] / "docs" / "water" / "boiling.txt").unlink()
    job.main()
    assert docindex.search("rolling boil") == []


def test_epub_reader(site):
    import zipfile
    f = site["core"] / "docs" / "medical" / "book.epub"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/c.opf"/></rootfiles></container>')
        z.writestr("OEBPS/c.opf", '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   '<metadata><dc:title>Field Book</dc:title></metadata><manifest><item id="a" href="a.xhtml"/></manifest>'
                   '<spine><itemref idref="a"/></spine></package>')
        z.writestr("OEBPS/a.xhtml", '<html><body><h1 class="x">Splints</h1><p onclick="x()">Pad it.</p>'
                   '<script>alert(1)</script></body></html>')
    r = client().get("/read", params={"path": "medical/book.epub"})
    assert r.status_code == 200 and "<h1>Splints</h1>" in r.text and "<p>Pad it.</p>" in r.text
    assert "alert(1)" not in r.text and "onclick" not in r.text
    assert client().get("/read", params={"path": "../hub.json"}).status_code == 404


def test_ask_streams_sources_then_reports_the_ai_down(site):
    import json
    r = client().post("/api/ask", json={"question": "how do I stop bleeding"})
    lines = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    assert any("sources" in m for m in lines)
    assert "error" in lines[-1]  # no Ollama in tests
