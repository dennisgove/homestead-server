"""Printing any document: the whole thing, some of a book's chapters, or a few pages.

Either straight to a printer the server can see (CUPS, the `lp` command), or as one PDF
to print from whatever phone or laptop is looking at the page.
"""
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from . import documents, library, settings

TEXT = (".txt", ".md")
MOST_COPIES = 20


def target(rel: str) -> dict | None:
    """What /print/<rel> prints: a document, or a book (its folder).

    {rel, title, topic, kind (pdf, epub, text or book), parts: [{rel, title, label, pages, path}], pages}

    Only paths the library shows can be printed, so nothing outside it can be named.
    """
    rel = rel.strip("/")
    topic = rel.split("/", 1)[0]

    def one(title, kind, pages):
        return {"rel": rel, "title": title, "topic": topic, "kind": kind,
                "parts": [{"rel": rel, "title": title, "label": "", "pages": pages, "path": documents.file_for(rel)}]}
    for d in documents.shelf(topic):
        if d["rel"] == rel:
            if d["kind"] != "book":
                return _counted(one(d["title"], d["kind"], d["pages"]))
            parts = [x | {"path": documents.file_for(x["rel"])} for x in d["parts"]]
            return _counted({"rel": rel, "title": d["title"], "topic": topic, "kind": "book", "parts": parts})
        for x in d["parts"]:     # one chapter of a book
            if x["rel"] == rel:
                return _counted(one(f"{d['title']}: {x['title']}", "pdf", x["pages"]))
    for d in documents.loose(topic):     # copied in by hand, not in the library list
        if d["rel"] == rel:
            ext = Path(rel).suffix.lower()
            kind = "text" if ext in TEXT else "epub" if ext == ".epub" else "pdf"
            return _counted(one(d["title"], kind, documents.info([rel]).get(rel, {}).get("pages")))
    return None


def _counted(t: dict) -> dict:
    """With each part's pages counted from the file itself (what gets printed), not the index."""
    for x in t["parts"]:
        if x["path"] is not None and x["path"].suffix.lower() == ".pdf":
            x["pages"] = pdf_pages(x["path"])
    t["pages"] = sum(x["pages"] or 0 for x in t["parts"])
    return t


def pdf_pages(path: Path) -> int:
    try:
        st = path.stat()
    except OSError:
        return 0
    return _pdf_facts(str(path), st.st_mtime_ns, st.st_size)[0]


def pdf_large(path: Path) -> bool:
    """Pages bigger than legal paper (a USGS quad is 22 x 27 inches): best printed full size elsewhere."""
    try:
        st = path.stat()
    except OSError:
        return False
    return _pdf_facts(str(path), st.st_mtime_ns, st.st_size)[1]


@lru_cache(maxsize=2048)
def _pdf_facts(path: str, _mtime: int, _size: int) -> tuple[int, bool]:
    """(pages, large), remembered until the file changes: opening a 700-page PDF takes a while."""
    from pypdf import PdfReader
    try:
        r = PdfReader(path)
        box = r.pages[0].mediabox if len(r.pages) else None
        large = bool(box) and max(float(box.width), float(box.height)) > 14.5 * 72
        return len(r.pages), large
    except Exception:   # a damaged file: counted as unknown, not fatal
        return 0, False


def ranges(text: str, total: int) -> list[tuple[int, int]]:
    """ "1-5, 9, 20-" -> [(1, 5), (9, 9), (20, total)]. Empty means every page."""
    out = []
    for bit in re.split(r"[,\s]+", text.strip()):
        if not bit:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)|(\d+)", bit)
        if not m or bit == "-":
            raise ValueError(f"“{bit}” isn't a page or a range of pages (like 5 or 10-20).")
        a, b = (int(m[3]), int(m[3])) if m[3] else (int(m[1] or 1), int(m[2] or total))
        if not 1 <= a <= b <= total:
            raise ValueError(f"Pages go from 1 to {total}; “{bit}” is outside that." if a <= b
                             else f"“{bit}” runs backwards.")
        out.append((a, b))
    return out


def choose(t: dict, parts: list[str] | None, pages: str) -> tuple[list[dict], list[tuple[int, int]], int]:
    """(the chosen parts, page ranges within them, how many pages that is)."""
    chosen = [x for x in t["parts"] if not parts or x["rel"] in parts]
    if not chosen:
        raise ValueError("Pick at least one chapter.")
    total = sum(x["pages"] or 0 for x in chosen)
    rs = ranges(pages, total) if total else []
    if pages.strip() and not total:
        raise ValueError("This document's pages can't be counted, so it can only be printed whole.")
    return chosen, rs, sum(b - a + 1 for a, b in rs) if rs else total


def pdf(t: dict, chosen: list[dict], rs: list[tuple[int, int]]) -> tuple[Path, bool]:
    """(one PDF of just what was chosen, True if it's a temporary file to delete afterwards)."""
    if len(chosen) == 1 and not rs:
        return chosen[0]["path"], False
    from pypdf import PdfWriter
    order = [(x["path"], i) for x in chosen for i in range(x["pages"] or 0)]
    if rs:
        order = [order[n - 1] for a, b in rs for n in range(a, b + 1)]
    w = PdfWriter()
    run: list = []
    for f, i in order + [(None, None)]:          # consecutive pages of one file go in together
        if run and (f != run[0][0] or i != run[-1][1] + 1):
            w.append(str(run[0][0]), pages=[j for _, j in run], import_outline=not rs)
            run = []
        if f is not None:
            run.append((f, i))
    tmp = tempfile.NamedTemporaryFile(prefix="print-", suffix=".pdf", delete=False)
    with tmp:
        w.write(tmp)
    return Path(tmp.name), True


# --- the printers (CUPS) --------------------------------------------------------------

def _run(*cmd: str) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def printers() -> list[dict]:
    """[{name, label, ready, default}]: what the server can print on (none if CUPS isn't there)."""
    default = (re.search(r"destination: (\S+)", _run("lpstat", "-d")) or [None, None])[1]
    out = []
    for line in _run("lpstat", "-p").splitlines():
        m = re.match(r"printer (\S+) (.*)", line)
        if m:
            out.append({"name": m[1], "label": m[1].replace("_series", "").replace("_", " "),
                        "ready": "disabled" not in m[2], "default": m[1] == default})
    out.sort(key=lambda p: (not p["default"], not p["ready"], p["label"].lower()))
    return out


def send(t: dict, chosen: list[dict], rs: list[tuple[int, int]], printer: str,
         copies: int = 1, two_sided: bool = True, color: bool = False) -> str:
    """Print it; returns the print job's name. ValueError if it can't be sent."""
    if printer not in {p["name"] for p in printers()}:
        raise ValueError("That printer isn't available. Is it switched on?")
    if t["kind"] == "epub":
        raise ValueError("Ebooks print from the reader: open it and use your browser's Print.")
    copies = max(1, min(int(copies), MOST_COPIES))
    title = t["title"] if len(chosen) == len(t["parts"]) else f"{t['title']} ({len(chosen)} chapters)"
    opts = ["-o", "sides=two-sided-long-edge" if two_sided else "sides=one-sided",
            "-o", "print-color-mode=color" if color else "print-color-mode=monochrome"]
    if not color:
        opts += ["-o", "ColorModel=Gray"]
    if t["kind"] == "text":
        path, temp = chosen[0]["path"], False
        if rs:
            opts += ["-o", "page-ranges=" + ",".join(f"{a}-{b}" for a, b in rs)]
    else:
        path, temp = pdf(t, chosen, rs)
    try:
        r = subprocess.run(["lp", "-d", printer, "-n", str(copies), "-t", title[:120], *opts, str(path)],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"The print system didn't answer ({e}).")
    finally:
        if temp:
            path.unlink(missing_ok=True)
    if r.returncode != 0:
        raise ValueError("The printer refused it: " + (r.stderr.strip() or "no reason given"))
    m = re.search(r"request id is (\S+)", r.stdout)
    return m[1] if m else ""


def queue() -> list[dict]:
    """[{job, printer, title, size}]: what's waiting to print or printing now."""
    out = []
    for p in printers():
        for line in _run("lpq", "-P", p["name"]).splitlines():
            m = re.match(r"(active|\d+\w*)\s+(\S+)\s+(\d+)\s+(.*?)\s+(\d+) bytes$", line.strip())
            if m:
                out.append({"job": int(m[3]), "printer": p["label"], "state": "printing" if m[1] == "active" else "waiting",
                            "title": m[4], "size": int(m[5])})
    return out


def cancel(job: int) -> bool:
    try:
        return subprocess.run(["cancel", str(int(job))], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def everything() -> list[dict]:
    """Every printable document, by topic: the library's and those copied in by hand."""
    out = [d for d in documents.shelf()]
    out += [d | {"kind": "text" if d["rel"].endswith(TEXT) else "pdf", "pages": documents.info([d["rel"]]).get(d["rel"], {}).get("pages")}
            for d in documents.loose()]
    order = list(library.topics())
    out.sort(key=lambda d: (order.index(d["topic"]) if d["topic"] in order else 99, d["title"].lower()))
    for d in out:
        d["print_url"] = "/print/" + settings.url_path(d["rel"])
        d["total"] = sum(x["pages"] or 0 for x in d["parts"]) if d.get("parts") else d.get("pages")
    return out


# --- the binder: what to keep on paper ------------------------------------------------

HOLDS = 100        # sheets a half-inch ring binder takes


def binders() -> list[dict]:
    """library.yaml's binders, each entry ready to print: the chapters and pages picked, its link to the
    print form with them filled in, and how many pages and sheets (printed on both sides) that is. Then
    documents marked print: true that the list leaves out.

    [{binder, color, note, pages, sheets, first_pages, full, items: [{title, what, why, first, color, section, sub,
      pages, sheets, url, pdf_url, read_url, large, problem}]}]
    """
    by_title = {it.title: it for it in library.items() if it.kind in ("pdf", "epub", "book")}
    listed, out = set(), []
    for b in library.raw_list().get("binders") or []:
        items, section = [], ""
        for e in b.get("items") or []:
            section = e.get("section", section)
            if e.get("folder"):
                items += [r | {"section": section} for r in _folder_items(e)]
            else:
                listed.add(e.get("doc"))
                items.append(_entry(e, by_title.get(e.get("doc"))) | {"section": section})
        out.append(_totals({"binder": b.get("binder", ""), "color": b.get("color", ""), "note": b.get("note", ""), "items": items}))
    extra = [_entry({"doc": it.title}, it) | {"section": ""} for it in library.items() if it.print and it.title not in listed]
    if extra:
        out.append(_totals({"binder": "Also marked for printing", "color": "", "note": "Marked print: true in the library list.",
                            "items": extra}))
    return out


def _totals(b: dict) -> dict:
    kept = [i for i in b["items"] if not i["large"]]                 # full-size sheets don't go in a binder
    b["pages"] = sum(i["pages"] for i in kept)
    b["sheets"] = sum(i["sheets"] for i in kept)
    b["first_pages"] = sum(i["pages"] for i in kept if i["first"])
    b["full"] = b["sheets"] > HOLDS
    return b


def _links(rel: str, parts: list[str], pages: str, color: bool) -> tuple[str, str]:
    q = [("part", p) for p in parts] + ([("pages", pages)] if pages else []) + ([("color", "1")] if color else [])
    tail = ("?" + urlencode(q)) if q else ""
    return "/print/" + settings.url_path(rel) + tail, "/print-pdf/" + settings.url_path(rel) + tail


def _entry(e: dict, it) -> dict:
    color = bool(e.get("color"))
    row = {"title": e.get("doc", ""), "what": e.get("what", ""), "why": e.get("why", ""), "first": bool(e.get("first")),
           "color": color, "sub": "", "pages": 0, "sheets": 0, "url": "", "pdf_url": "", "read_url": "", "large": False,
           "problem": ""}
    if it is None:
        row["problem"] = "Not in the library list."
        return row
    rel = documents.rel(it.book_dir() if it.kind == "book" else it.doc_path())
    t = target(rel)
    if t is None:
        row["problem"] = "Not downloaded yet."
        return row
    row["title"] = t["title"]
    row["read_url"] = f"/book/{it.id}" if it.kind == "book" else "/read/" + settings.url_path(rel)
    parts = []
    if e.get("chapters"):
        want = [c.lower() for c in e["chapters"]]
        parts = [x["rel"] for x in t["parts"] if (x.get("label") or "").lower() in want or (x.get("title") or "").lower() in want]
        if len(parts) < len(want):
            row["problem"] = "Some of these chapters aren't in the book any more."
    try:
        _, _, n = choose(t, parts, e.get("pages", ""))
    except ValueError as err:
        row["problem"] = str(err)
        n = 0
    row["pages"], row["sheets"] = n, (n + 1) // 2
    row["url"], row["pdf_url"] = _links(rel, parts, e.get("pages", ""), color)
    return row


def _in_folder(e: dict, rel: str) -> bool:
    """Whether a binder folder entry takes this file: in the folder, and named as its files: list says."""
    only = tuple(e.get("files") or ())
    return rel.startswith(e["folder"].strip("/") + "/") and (not only or Path(rel).stem.startswith(only))


def _folder_items(g: dict) -> list[dict]:
    """Every PDF in a folder of the documents (and its subfolders), whole."""
    folder = g["folder"].strip("/")
    first = tuple(g.get("first_files") or ())
    rows = []
    for d in documents.loose():
        r = d["rel"]
        if not _in_folder(g, r) or not r.lower().endswith(".pdf"):
            continue
        sub, _, name = r[len(folder) + 1:].rpartition("/")
        path = documents.file_for(r)
        stem = Path(name).stem
        large = path is not None and pdf_large(path)
        url, pdf_url = _links(r, [], "", bool(g.get("color")))
        n = pdf_pages(path) if path else 0
        rows.append({"title": stem, "what": "Full-size sheet: best printed at a print shop, or used on screen." if large else "",
                     "why": "", "first": stem.startswith(first) if first else False, "color": bool(g.get("color")), "sub": sub,
                     "pages": n, "sheets": (n + 1) // 2, "url": url, "pdf_url": pdf_url,
                     "read_url": "/read/" + settings.url_path(r), "large": large, "problem": ""})
    rows.sort(key=lambda x: (x["sub"] != "", x["sub"].lower(), x["title"].lower()))
    return rows


def recommended(t: dict) -> dict | None:
    """What the binder list recommends printing of this document, to start its print form with:
    {parts, pages, color, sections: [what...]}, or None if the binder doesn't list it.

    A document listed more than once (three parts of a manual) gets all of them together."""
    entries = []
    for b in library.raw_list().get("binders") or []:
        for e in b.get("items") or []:
            if e.get("folder"):
                if _in_folder(e, t["rel"]):
                    entries.append({"color": e.get("color"), "what": ""})
                continue
            it = next((i for i in library.items() if i.title == e.get("doc")), None)
            if it and it.kind in ("pdf", "book") and documents.rel(it.book_dir() if it.kind == "book" else it.doc_path()) == t["rel"]:
                entries.append(e)
    if not entries:
        return None
    parts, pages = [], []
    whole = any(not e.get("chapters") and not e.get("pages") for e in entries)
    for e in entries:
        want = [c.lower() for c in e.get("chapters") or []]
        parts += [x["rel"] for x in t["parts"] if want and ((x.get("label") or "").lower() in want or (x.get("title") or "").lower() in want)
                  and x["rel"] not in parts]
        if e.get("pages"):
            pages.append(e["pages"])
    if whole or (parts and pages and len(entries) > 1):     # chapters of one entry and pages of another don't add up
        parts, pages = ([], []) if whole else (parts, [])
    order = [x["rel"] for x in t["parts"]]
    parts.sort(key=order.index)
    return {"parts": parts, "pages": ", ".join(pages), "color": any(e.get("color") for e in entries),
            "sections": [e["what"] for e in entries if e.get("what")]}
