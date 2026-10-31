"""Printing any document: the whole thing, some of a book's chapters, or a few pages.

Either straight to a printer the server can see (CUPS, the `lp` command), or as one PDF
to print from whatever phone or laptop is looking at the page.
"""
import re
import subprocess
import tempfile
from pathlib import Path

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
    from pypdf import PdfReader
    try:
        return len(PdfReader(path).pages)
    except Exception:   # a damaged file: counted as unknown, not fatal
        return 0


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
