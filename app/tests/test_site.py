import json
import re
import urllib.parse

from fastapi.testclient import TestClient

PAGES = ["/", "/t/medical", "/t/learning", "/t/family", "/book/field-doctor", "/read/medical/stop-the-bleed.pdf",
         "/read/medical/field-doctor/en_fd_01.pdf", "/wiki/test-medicine_en_all/home", "/wiki-search/test-medicine_en_all?q=burn",
         "/search?q=burns", "/search?q=burns&t=medical", "/search?q=fractions", "/search?q=zzzzzz", "/ask", "/learn/c0ffee00c0ffee00c0ffee00c0ffee00",
         "/learn/c0ffee00c0ffee00c0ffee00c0ffee00/v1", "/videos", "/videos?play=Repair/fix_a_leak.mp4", "/maps", "/emergency",
         "/print", "/tools", "/status", "/strip"]


def client():
    from homestead.web.site import app
    return TestClient(app)


def test_every_page(indexed):
    c = client()
    for p in PAGES:
        r = c.get(p)
        assert r.status_code == 200, (p, r.text[:300])


def test_every_link_works_and_points_here(indexed):
    """Crawl the site from the home page: every link and file it shows must work, and none may
    name a host (so the site works by any name or IP)."""
    c = client()
    seen, todo, bad = set(), ["/"] + PAGES, []
    while todo:
        url = todo.pop()
        if url in seen or len(seen) > 400:
            continue
        seen.add(url)
        r = c.get(url, follow_redirects=True)
        if r.status_code != 200:
            bad.append((url, r.status_code))
            continue
        if "text/html" not in r.headers.get("content-type", ""):
            continue
        base = str(r.url)
        for link in re.findall(r'(?:href|src)="([^"]+)"', r.text):
            link = link.replace("&amp;", "&")
            if link.startswith(("#", "data:", "javascript:")) or link.startswith("/static/"):
                continue
            if re.match(r"^[a-z]+://", link):
                assert "library.lan" not in link and "homestead.local" not in link, (url, link)
                continue     # the tools on their own ports
            todo.append(urllib.parse.urljoin(base, link).split("#")[0].replace("http://testserver", ""))
    assert not bad, bad


def test_encyclopedia_pages_get_the_bar_and_keep_their_links(site):
    c = client()
    r = c.get("/wiki/test-medicine_en_all/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/wiki/test-medicine_en_all/home"
    page = c.get("/wiki/test-medicine_en_all/home").text
    assert 'id="hs-bar"' in page and 'href="Burns"' in page
    assert c.get("/wiki/test-medicine_en_all/pic.png").headers["content-type"] == "image/png"
    assert c.get("/wiki/test-medicine_en_all/Nope").status_code == 404


def test_drive_shows_connected_wherever_the_strip_is(site, monkeypatch):
    from homestead import settings
    c = client()
    for p in ("/status", "/strip"):
        assert "Library drive connected" in c.get(p).text, p
    monkeypatch.setattr(settings, "library_drive_ok", lambda: False)
    for p in ("/status", "/strip"):
        assert "Library drive not connected" in c.get(p).text, p


def test_files_stay_inside_their_folders(site):
    c = client()
    assert c.get("/files/docs/medical/stop-the-bleed.pdf").status_code == 200
    assert c.get("/files/docs/../site.json").status_code == 404
    assert c.get("/files/etc/passwd").status_code == 404
    assert c.get("/read/../../site.json").status_code == 404


def test_video_files_support_seeking(indexed):
    r = client().get("/files/video/Repair/fix_a_leak.mp4", headers={"Range": "bytes=0-0"})
    assert r.status_code == 206


def test_ask_shows_sources_then_says_the_ai_is_off(indexed):
    r = client().post("/api/ask", json={"question": "how do I treat a burn"})
    lines = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    srcs = next(m["sources"] for m in lines if "sources" in m)
    assert srcs and all(s["url"].startswith("/") for s in srcs)
    assert "error" in lines[-1]


def test_epub_reader(site):
    import zipfile
    f = site["core"] / "docs" / "family" / "book.epub"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/c.opf"/></rootfiles></container>')
        z.writestr("OEBPS/c.opf", '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   '<metadata><dc:title>Field Book</dc:title></metadata><manifest><item id="a" href="a.xhtml"/></manifest>'
                   '<spine><itemref idref="a"/></spine></package>')
        z.writestr("OEBPS/a.xhtml", '<html><body><h1 class="x">Knots</h1><p onclick="x()">Tie it.</p><script>alert(1)</script></body></html>')
    r = client().get("/read/family/book.epub")
    assert r.status_code == 200 and "<h1>Knots</h1>" in r.text and "alert(1)" not in r.text and "onclick" not in r.text


def test_no_login_anywhere(indexed):
    c = client()
    for p in PAGES:
        assert not re.search(r'type="password"|log ?in|sign ?in', c.get(p).text, re.I), p
