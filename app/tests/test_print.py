import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

BOOK = "medical/field-doctor"
CH2, GLOSS = f"{BOOK}/en_fd_02.pdf", f"{BOOK}/en_fd_gloss.pdf"


def client():
    from homestead.web.site import app
    return TestClient(app)


def texts(pdf: bytes) -> list[str]:
    return [p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages]


@pytest.fixture
def cups(tmp_path, monkeypatch):
    """Stand-ins for CUPS's commands: one printer, a job waiting, and a log of what was sent."""
    bin, log = tmp_path / "bin", tmp_path / "sent"
    bin.mkdir()
    log.mkdir()
    scripts = {
        "lpstat": """case "$1" in -p) echo "printer Office_Laser_series is idle.  enabled since today";;
                     -d) echo "system default destination: Office_Laser_series";; esac""",
        "lpq": """echo "Office_Laser_series is ready and printing"
                  echo "Rank    Owner   Job     File(s)                         Total Size"
                  echo "active  homestead 7     Where There Is No Doctor        1048576 bytes" """,
        "lp": f"""python3 - "$@" <<'EOF'
import json, shutil, sys
args = sys.argv[1:]
shutil.copy(args[-1], "{log}/job.pdf")
open("{log}/args.json", "w").write(json.dumps(args))
EOF
echo "request id is Office_Laser_series-8 (1 file(s))" """,
        "cancel": f'echo "$@" > {log}/cancelled',
    }
    for name, body in scripts.items():
        (bin / name).write_text("#!/bin/sh\n" + body + "\n")
        (bin / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin}:{__import__('os').environ['PATH']}")
    return log


def test_page_ranges():
    from homestead.printing import ranges
    assert ranges("", 10) == []
    assert ranges("1-3, 5 8-", 10) == [(1, 3), (5, 5), (8, 10)]
    assert ranges("-2", 10) == [(1, 2)]
    for bad in ("0", "11", "5-3", "x", "-"):
        with pytest.raises(ValueError):
            ranges(bad, 10)


def test_every_print_page(indexed, cups):
    c = client()
    for p in ["/print", f"/print/{BOOK}", "/print/medical/stop-the-bleed.pdf", "/print/family/our-plan.txt"]:
        r = c.get(p)
        assert r.status_code == 200, (p, r.text[:300])
    page = c.get("/print").text
    assert "Office Laser" in page and f'href="/print/{BOOK}"' in page and 'href="/print/family/our-plan.txt"' in page
    assert "Where There Is No Doctor" in page and 'action="/print-cancel/7"' in page      # the queue
    assert c.get("/print/medical/nothing.pdf").status_code == 404
    assert c.get("/print/../site.json").status_code == 404


def test_chapters_and_pages_as_one_pdf(indexed):
    c = client()
    whole = c.get(f"/print-pdf/{BOOK}")
    assert whole.headers["content-type"] == "application/pdf"
    assert [t.split("\n")[0] for t in texts(whole.content)] == ["Burns and Scalds", "Broken Bones", "Words to Know"]
    two = texts(c.get(f"/print-pdf/{BOOK}", params={"part": [CH2, GLOSS]}).content)
    assert [t.split("\n")[0] for t in two] == ["Broken Bones", "Words to Know"]
    one = texts(c.get(f"/print-pdf/{BOOK}", params={"part": [CH2, GLOSS], "pages": "2"}).content)
    assert [t.split("\n")[0] for t in one] == ["Words to Know"]
    assert c.get(f"/print-pdf/{BOOK}", params={"pages": "4"}).status_code == 400


def test_send_to_the_printer(indexed, cups):
    c = client()
    r = c.post(f"/print/{BOOK}", data={"part": [CH2, GLOSS], "pages": "1", "printer": "Office_Laser_series",
                                       "copies": "2", "sides": "two", "color": "gray"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/print?")
    args = json.loads((cups / "args.json").read_text())
    assert args[:4] == ["-d", "Office_Laser_series", "-n", "2"]
    assert "sides=two-sided-long-edge" in args and "print-color-mode=monochrome" in args
    assert [t.split("\n")[0] for t in texts((cups / "job.pdf").read_bytes())] == ["Broken Bones"]
    assert not Path(args[-1]).exists()          # the temporary PDF is cleaned up
    assert "2 pages" in c.get(r.headers["location"]).text      # 1 page, 2 copies


def test_a_whole_document_goes_as_it_is(indexed, cups):
    c = client()
    c.post("/print/medical/stop-the-bleed.pdf", data={"printer": "Office_Laser_series", "sides": "one", "color": "color"})
    args = json.loads((cups / "args.json").read_text())
    assert args[-1].endswith("docs/medical/stop-the-bleed.pdf")
    assert "sides=one-sided" in args and "print-color-mode=color" in args


def test_mistakes_are_explained(indexed, cups):
    c = client()
    r = c.post(f"/print/{BOOK}", data={"pages": "9", "printer": "Office_Laser_series"})
    assert r.status_code == 400 and "Pages go from 1 to 3" in r.text
    r = c.post(f"/print/{BOOK}", data={"printer": "Somebody_Elses"})
    assert r.status_code == 400 and "That printer isn&#39;t available" in r.text
    assert not (cups / "args.json").exists()


def test_cancel(indexed, cups):
    r = client().post("/print-cancel/7", follow_redirects=False)
    assert r.status_code == 303 and (cups / "cancelled").read_text().strip() == "7"


def test_without_a_printer_it_still_makes_the_pdf(indexed, cups):
    (cups.parent / "bin" / "lpstat").write_text("#!/bin/sh\nexit 1\n")
    page = client().get(f"/print/{BOOK}").text
    assert "can't see a printer" in page and f'formaction="/print-pdf/{BOOK}"' in page


def test_old_indexes_get_their_page_counts_fixed(indexed):
    """Indexes made before counted only up to the last page with text (a scan came out as 0)."""
    import sqlite3
    from homestead import documents, settings
    con = sqlite3.connect(settings.path("index"))
    con.execute("UPDATE docs SET npages = 0 WHERE path = 'medical/stop-the-bleed.pdf'")
    con.execute("PRAGMA user_version = 0")
    con.commit()
    con.close()
    r = documents.build(log=lambda *a: None)
    assert r["read"] == 0                       # nothing read again
    assert documents.info(["medical/stop-the-bleed.pdf"])["medical/stop-the-bleed.pdf"]["pages"] == 1


BINDER = """
binder:
  - group: Medical
    tab: RED
    note: Emergencies first.
    items:
      - { doc: Field Doctor, chapters: ["Chapter 2", "Glossary"], what: Bones and words, first: true }
      - { doc: Stop the Bleed, pages: "1", color: true }
      - { doc: Not In The List }
  - group: Our maps
    tab: ORANGE
    folder: family/maps
    color: true
    first_files: ["Area"]
"""


def test_the_binder(indexed, cups):
    """The binder list: chapters and pages picked, links that fill in the print form, the maps folder."""
    from pypdf import PdfWriter
    from conftest import make_pdf
    indexed["list"].write_text(indexed["list"].read_text() + BINDER)
    maps = indexed["core"] / "docs" / "family" / "maps"
    (maps / "Routes").mkdir(parents=True)
    make_pdf(maps / "Area 1 - Our Town.pdf", [(24, "Our Town")])
    make_pdf(maps / "Routes" / "Route A - Highways.pdf", [(24, "Route A")])
    w = PdfWriter()
    w.add_blank_page(width=22 * 72, height=27 * 72)            # a full-size USGS quad
    w.write(maps / "Quad.pdf")
    c = client()
    page = c.get("/binder").text
    assert "RED tab" in page and "Emergencies first." in page and "Bones and words" in page
    assert "Not in the library list" in page and "Also marked for the binder" not in page    # Field Doctor is listed
    assert "Area 1 - Our Town" in page and "Route A - Highways" in page and "<h3>Routes</h3>" in page    # names keep their capitals
    assert "Full-size sheet" in page
    assert page.index("Area 1 - Our Town") < page.index("Quad") < page.index("Route A")      # loose files first, then subfolders
    from homestead import printing
    groups = printing.binder()
    med, maps_g = groups
    fd, bleed, missing = med["items"]
    assert fd["pages"] == 2 and fd["first"] and bleed["pages"] == 1 and bleed["color"] and missing["problem"]
    assert med["pages"] == 3 and med["first_pages"] == 2
    assert maps_g["pages"] == 2                                   # the full-size sheet isn't counted
    assert [i["first"] for i in maps_g["items"]] == [True, False, False]

    form = c.get(fd["url"]).text                                  # the print form, filled in
    assert 'value="medical/field-doctor/en_fd_02.pdf" data-pages="1" checked' in form
    assert 'value="medical/field-doctor/en_fd_01.pdf" data-pages="1" >' in form
    form = c.get(bleed["url"]).text
    assert 'name="pages" id="pages" value="1"' in form and 'value="color" checked' in form
    pdf = c.get(fd["pdf_url"])
    assert [t.split("\n")[0] for t in texts(pdf.content)] == ["Broken Bones", "Words to Know"]
    assert "/binder" in c.get("/print").text


def test_every_binder_entry_is_in_the_library_list():
    """library.yaml's binder names documents by title: a renamed document mustn't silently drop out."""
    import yaml
    lst = yaml.safe_load((Path(__file__).parents[2] / "library.yaml").read_text())
    titles = {i.get("title") for t in lst["topics"].values() for i in t["items"]}
    for g in lst["binder"]:
        for e in g.get("items") or []:
            assert e["doc"] in titles, e["doc"]
