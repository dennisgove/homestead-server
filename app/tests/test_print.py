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
binders:
  - binder: First aid
    group: Emergency medical
    color: red
    note: Emergencies first.
    how: Print it double-sided.
    items:
      - { doc: Field Doctor, section: Injuries, chapters: ["Chapter 2", "Glossary"], what: Bones and words, first: true }
      - { doc: Stop the Bleed, pages: "1", color: true }
      - { doc: Not In The List, section: Other }
  - binder: Maps
    color: orange
    items:
      - { folder: family/maps, files: ["Area", "Quad", "Route"], first_files: ["Area"], color: true }
      - { doc: Not In The List Either, section: And a guide }
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
    assert '<span class="bnum">1</span>' in page and "<h2>First aid</h2>" in page and "red label" in page and "Emergencies first." in page and "Bones and words" in page
    assert "<h3>Injuries</h3>" in page and "<h3>Other</h3>" in page and "<h3>And a guide</h3>" in page
    assert "Not in the library list" in page and "Also marked for printing" not in page    # Field Doctor is listed
    assert "Area 1 - Our Town" in page and "Route A - Highways" in page and "<h3>Routes</h3>" in page    # names keep their capitals
    assert "Full-size sheet" in page
    cover = page[page.index('<section class="cover printonly">'):]                # a cover per binder: what's in it, not how to print
    assert cover.count('class="cover printonly"') == 2 and "First aid" in cover and "Emergencies first." in cover
    assert "<h2>Injuries</h2>" in cover and "Bones and words" in cover and "<h3>Routes</h3>" in cover
    assert "Print it double-sided." in page and "Print it double-sided." not in cover and "Full-size sheet" not in cover
    assert " p." not in cover and "★" not in cover
    assert '<h2 class="bshelf">Emergency medical</h2>' in page and '<h2 class="bshelf">Other binders</h2>' in page
    assert '<p class="bnav-shelf">Emergency medical</p>' in page
    assert '<p class="kind">Emergency medical</p>' in cover
    assert page.index("Area 1 - Our Town") < page.index("Quad") < page.index("Route A")      # loose files first, then subfolders
    from homestead import printing
    med, maps_b = printing.binders()
    fd, bleed, missing = med["items"]
    assert fd["pages"] == 2 and fd["first"] and bleed["pages"] == 1 and bleed["color"] and missing["problem"]
    assert med["pages"] == 3 and med["sheets"] == 2 and med["first_pages"] == 2 and not med["full"]
    assert maps_b["pages"] == 2 and maps_b["sheets"] == 2       # the full-size sheet isn't counted; each map its own sheet
    assert [i["first"] for i in maps_b["items"]] == [True, False, False, False]
    assert [i["section"] for i in med["items"]] == ["Injuries", "Injuries", "Other"]

    assert '<nav class="bnav"' in page and 'href="#binder-1"' in page and 'href="#binder-2"' in page   # quick links
    assert '<details class="bgroup" id="binder-1" data-n="1" open>' in page                          # collapsible
    assert f'data-version="{fd["version"]}"' in page and "Changed since you printed it" in page
    area = maps_b["items"][0]
    assert fd["version"] and area["version"] and fd["version"] != area["version"]
    assert printing.binders()[1]["items"][0]["version"] == area["version"]        # the same file: the same version
    import os
    st = os.stat(maps / "Area 1 - Our Town.pdf")
    os.utime(maps / "Area 1 - Our Town.pdf", ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))   # made again
    assert printing.binders()[1]["items"][0]["version"] != area["version"]       # so it shows as changed

    form = c.get(fd["url"]).text                                  # the print form, filled in
    assert 'value="medical/field-doctor/en_fd_02.pdf" data-pages="1" checked' in form
    assert 'value="medical/field-doctor/en_fd_01.pdf" data-pages="1" >' in form
    form = c.get(bleed["url"]).text
    assert 'name="pages" id="pages" value="1"' in form and 'value="color" checked' in form
    pdf = c.get(fd["pdf_url"])
    assert [t.split("\n")[0] for t in texts(pdf.content)] == ["Broken Bones", "Words to Know"]

    assert page.count('<button class="btn" type="submit">Quick print</button>') == 4      # not the full-size sheet
    assert '<input type="hidden" name="printer" value="Office_Laser_series">' in page
    r = c.post(fd["url"].split("?")[0], data={"part": fd["parts"], "pages": fd["range"], "printer": "Office_Laser_series",
                                             "copies": "1", "sides": "two", "color": "gray", "quick": "1"},
               follow_redirects=False)                            # Quick print: straight to the printer, the page stays put
    assert r.status_code == 200 and r.json() == {"sent": fd["title"], "to": "Office Laser", "n": 2}
    assert "sides=two-sided-long-edge" in json.loads((cups / "args.json").read_text())
    assert [t.split("\n")[0] for t in texts((cups / "job.pdf").read_bytes())] == ["Broken Bones", "Words to Know"]
    r = c.post(fd["url"].split("?")[0], data={"printer": "Gone", "quick": "1"})
    assert r.status_code == 400 and "isn't available" in r.json()["error"]

    out = {"X-Homestead-Via": "tunnel"}                           # from outside the home (the Cloudflare Tunnel)
    page = c.get("/binder", headers=out).text
    assert "Quick print</button>" not in page and "printing on the home printer is off" in page
    assert "printing on the home printer is off" in c.get(fd["url"], headers=out).text
    assert 'name="printer"' not in c.get(fd["url"], headers=out).text
    assert "Cancel</button>" not in c.get("/print", headers=out).text and "Cancel</button>" in c.get("/print").text
    (cups / "job.pdf").unlink()
    r = c.post(fd["url"].split("?")[0], headers=out, data={"printer": "Office_Laser_series", "quick": "1"})
    assert r.status_code == 403 and not (cups / "job.pdf").exists()
    assert c.post("/print-cancel/7", headers=out, follow_redirects=False).status_code == 403
    assert c.get(fd["pdf_url"], headers=out).status_code == 200           # a PDF to print where they are still works
    assert "/binder" in c.get("/print").text


def test_every_binder_entry_is_in_the_library_list():
    """library.yaml's binder names documents by title: a renamed document mustn't silently drop out."""
    import yaml
    lst = yaml.safe_load((Path(__file__).parents[2] / "library.yaml").read_text())
    titles = {i.get("title") for t in lst["topics"].values() for i in t["items"]}
    for b in lst["binders"]:
        for e in b.get("items") or []:
            assert e.get("folder") or e["doc"] in titles, e["doc"]


def test_print_forms_start_with_what_the_binder_recommends(indexed):
    indexed["list"].write_text(indexed["list"].read_text() + BINDER)
    c = client()
    form = c.get(f"/print/{BOOK}").text                            # no choices in the link: the binder's
    assert "Picked for you" in form and "Bones and words" in form
    assert 'value="medical/field-doctor/en_fd_02.pdf" data-pages="1" checked' in form
    assert 'value="medical/field-doctor/en_fd_01.pdf" data-pages="1" >' in form
    form = c.get(f"/print/{BOOK}", params={"all": "1"}).text      # the whole thing instead
    assert "Picked for you" not in form and 'value="medical/field-doctor/en_fd_01.pdf" data-pages="1" checked' in form
    form = c.get("/print/medical/stop-the-bleed.pdf").text
    assert 'name="pages" id="pages" value="1"' in form and 'value="color" checked' in form
    form = c.get("/print/family/our-plan.txt").text                # not in the binder: everything, as before
    assert "Picked for you" not in form
