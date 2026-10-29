"""A small fake server for the tests: an encyclopedia (a real ZIM, built here), a book of
chapter PDFs, a single PDF, a course channel with one video, and the settings to match."""
import json
import sqlite3
from pathlib import Path

import pytest
from libzim.writer import Creator, Hint, Item, StringProvider

LIST = """
topics:
  medical:
    name: Medical
    icon: "🩺"
    blurb: First aid and more
    quick: [burns]
    items:
      - zim: test-medicine_en_all
        essential: true
      - book: https://example.org/book.html
        title: Field Doctor
        print: true
      - pdf: https://example.org/bleed.pdf
        title: Stop the Bleed
  learning:
    name: Learning
    icon: "🎓"
    blurb: Courses
    items:
      - course: c0ffee00c0ffee00c0ffee00c0ffee00
        title: Test Academy
  family:
    name: Family documents
    icon: "🗂️"
    blurb: Ours
    items: []
by_hand:
  - { title: A book to buy, where: a shop }
phone_apps:
  - { title: An app, where: somewhere }
"""


class Page(Item):
    def __init__(self, path, title, body, mime="text/html"):
        super().__init__()
        self.path, self.title, self.body, self.mime = path, title, body, mime

    def get_path(self):
        return self.path

    def get_title(self):
        return self.title

    def get_mimetype(self):
        return self.mime

    def get_contentprovider(self):
        return StringProvider(self.body)

    def get_hints(self):
        return {Hint.FRONT_ARTICLE: self.mime == "text/html"}


def make_zim(path: Path):
    with Creator(str(path)).config_indexing(True, "eng") as c:
        c.set_mainpath("home")
        for k, v in {"Title": "Test Medicine", "Description": "Medicine for tests", "Language": "eng",
                     "Name": "test-medicine_en_all", "Creator": "tests", "Publisher": "tests", "Date": "2026-01-01"}.items():
            c.add_metadata(k, v)
        c.add_item(Page("home", "Home", '<html><head><title>Home</title></head><body><h1>Test Medicine</h1>'
                                        '<a href="Burns">Burns</a> <img src="pic.png"></body></html>'))
        c.add_item(Page("Burns", "Burns", "<html><head><title>Burns</title></head><body><h1>Burns</h1>"
                                          "<p>Cool the burn under running water for twenty minutes. Cover it loosely.</p>"
                                          '<a href="home">Home</a></body></html>'))
        c.add_item(Page("Splints", "Splints", "<html><body><p>A splint keeps a broken bone still.</p></body></html>"))
        c.add_item(Page("pic.png", "", "PNG", "image/png"))


def make_pdf(path: Path, lines: list[tuple[int, str]]):
    """A real one-page PDF with lines of text at the given font sizes (biggest = the heading)."""
    y, ops = 760, []
    for size, text in lines:
        ops.append(f"BT /F1 {size} Tf 72 {y} Td ({text}) Tj ET")
        y -= size + 14
    stream = "\n".join(ops).encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))


def make_course(root: Path, channel: str):
    (root / "databases").mkdir(parents=True)
    con = sqlite3.connect(root / "databases" / f"{channel}.sqlite3")
    con.executescript("""
        CREATE TABLE content_channelmetadata (id TEXT, name TEXT, description TEXT);
        CREATE TABLE content_contentnode (id TEXT, parent_id TEXT, kind TEXT, title TEXT, description TEXT,
            sort_order REAL, available BOOL, duration INTEGER);
        CREATE TABLE content_file (id TEXT, contentnode_id TEXT, local_file_id TEXT, preset TEXT, lang_id TEXT, priority INTEGER);
        CREATE TABLE content_localfile (id TEXT, extension TEXT, file_size INTEGER);""")
    con.execute("INSERT INTO content_channelmetadata VALUES (?, 'Test Academy', 'Lessons for tests')", (channel,))
    con.executemany("INSERT INTO content_contentnode VALUES (?, ?, ?, ?, ?, ?, 1, ?)", [
        (channel, None, "topic", "Test Academy", "", 1, None),
        ("math", channel, "topic", "Math", "", 1, None),
        ("v1", "math", "video", "Adding fractions", "How to add fractions", 1, 125),
        ("v2", "math", "video", "Subtracting fractions", "", 2, 90),
        ("ex", channel, "topic", "Practice only", "", 2, None),
        ("e1", "ex", "exercise", "Practice", "", 1, None)])
    vid = "ab" + "0" * 30
    con.execute("INSERT INTO content_localfile VALUES (?, 'mp4', 4)", (vid,))
    con.execute("INSERT INTO content_file VALUES ('f1', 'v1', ?, 'low_res_video', NULL, 1)", (vid,))
    con.commit()
    con.close()
    d = root / "storage" / vid[0] / vid[1]
    d.mkdir(parents=True)
    (d / f"{vid}.mp4").write_bytes(b"\x00\x00\x00\x18")


@pytest.fixture
def site(tmp_path, monkeypatch):
    core, lib, state = tmp_path / "core", tmp_path / "library", tmp_path / "state"
    (core / "zim").mkdir(parents=True)
    make_zim(core / "zim" / "test-medicine_en_all_2026-01.zim")
    book = core / "docs" / "medical" / "field-doctor"
    book.mkdir(parents=True)
    make_pdf(book / "en_fd_01.pdf", [(28, "Burns and Scalds"), (11, "Cool the burn with clean water.")])
    make_pdf(book / "en_fd_02.pdf", [(28, "Broken Bones"), (11, "Splint the limb above and below the break.")])
    make_pdf(book / "en_fd_gloss.pdf", [(28, "Words to Know"), (11, "Tourniquet: a tight band.")])
    make_pdf(core / "docs" / "medical" / "stop-the-bleed.pdf", [(24, "Stop the Bleed"), (11, "Apply a tourniquet high and tight.")])
    (core / "docs" / "family").mkdir()
    (core / "docs" / "family" / "our-plan.txt").write_text("Meet at the oak tree if the house is unsafe.")
    make_course(lib / "courses", "c0ffee00c0ffee00c0ffee00c0ffee00")
    (lib / "video" / "Repair").mkdir(parents=True)
    (lib / "video" / "Repair" / "fix_a_leak.mp4").write_bytes(b"\x00")
    (core / "share" / "apps").mkdir(parents=True)
    (core / "share" / "apps" / "kiwix.apk").write_bytes(b"x")
    lst = tmp_path / "library.yaml"
    lst.write_text(LIST)
    cfg = {"paths": {"core": str(core), "library": str(lib), "state": str(state), "list": str(lst),
                     "power": str(tmp_path / "power.json"), "last_backup": str(tmp_path / "last-backup")},
           "library_is_folder": True,
           "site": {"name": "Homestead Library", "ssid": "HOMESTEAD", "lan_name": "library.lan", "region": "Massachusetts"},
           "ai": {"ollama": "http://127.0.0.1:9", "model": "homestead", "helper": "small"},
           "tools": [{"id": "pantry", "title": "Pantry", "icon": "🥫", "hint": "Food storage", "port": 7008, "group": "Everyday"}]}
    p = tmp_path / "site.json"
    p.write_text(json.dumps(cfg))
    monkeypatch.setenv("HOMESTEAD_SETTINGS", str(p))
    from homestead import settings
    settings.reset()
    yield {"core": core, "lib": lib, "state": state, "list": lst}
    settings.reset()


@pytest.fixture
def indexed(site):
    from homestead import fetch
    fetch.index()
    return site
