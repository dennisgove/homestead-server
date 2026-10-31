"""Documents: PDFs and ebooks. Their names, their text (page by page) in a search
index, and search over it.

A book that comes as one PDF per chapter gets each chapter's name from the chapter
itself (the biggest heading on its first page), so nobody has to type them in.
"""
import html
import re
import sqlite3
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from . import library, settings, terms

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
    path TEXT PRIMARY KEY,      -- relative to docs/
    item TEXT, topic TEXT, title TEXT, label TEXT, sort INTEGER,
    npages INTEGER, mtime INTEGER, size INTEGER);
CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(
    text, title, path UNINDEXED, topic UNINDEXED, page UNINDEXED,
    tokenize = 'porter unicode61 remove_diacritics 2');
"""

# Parts of a book that aren't chapters, by the word in their file name.
FRONT = {"fm": "Front matter", "toc": "Contents", "int": "Introduction", "intro": "Introduction",
         "info": "Additional information"}
BACK = {"gloss": "Glossary", "indx": "Index", "index": "Index", "resc": "Resources", "bm": "Back matter",
        "gp": "Medicines pages", "ob": "Other books", "abbrevacro": "Abbreviations", "prodmfg": "Product manufacturers",
        "envoi": "Envoi", "skills": "Health care skills", "ddc": "Due date calculator"}


# --- names ---------------------------------------------------------------------------

def _first_page_lines(path: Path) -> list[tuple[float, float, str]]:
    """(text height, top, text) for each line on page 1. A drop capital printed as its own
    word ("T he") is joined back onto the rest of its word."""
    try:
        r = subprocess.run(["pdftotext", "-f", "1", "-l", "1", "-bbox-layout", str(path), "-"],
                           capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return []
    word = re.compile(r'<word[^>]*xMin="([\d.]+)"[^>]*yMin="([\d.]+)"[^>]*xMax="([\d.]+)"[^>]*yMax="([\d.]+)"[^>]*>(.*?)</word>', re.S)
    out = []
    for line in re.findall(r"<line\b[^>]*>(.*?)</line>", r.stdout.decode("utf-8", "replace"), re.S):
        words = [(float(x0), float(y0), float(x1), float(y1), html.unescape(t).strip()) for x0, y0, x1, y1, t in word.findall(line)]
        if not words:
            continue
        text, prev = "", None
        for w in words:
            glued = prev is not None and len(prev[4]) == 1 and prev[4].isupper() and w[0] - prev[2] < 2.5
            text += ("" if glued or not text else " ") + w[4]
            prev = w
        out.append((round(max(w[3] - w[1] for w in words), 1), words[0][1], text.strip()))
    return out


NOT_TITLE = re.compile(r"^(c\s*h\s*a\s*p\s*t\s*e\s*r|appendix|section|guide|part|contents?|page|(in|about) this chapter:?)"
                       r"\s*[\dA-Z]?$|^[ivxlcdm]+$|^\d+$", re.I)


def _plain(t: str) -> str:
    return re.sub(r"[\W\d_]+", " ", t.lower()).strip()


def heading(path: Path, book_title: str = "") -> str:
    """The biggest text on the first page that reads like a title and isn't just the book's name;
    failing that, the page's running header ("180 Sexual Health")."""
    every = _first_page_lines(path)
    t = _biggest(every, book_title)
    if t:
        return t
    for h, y, text in sorted(every, key=lambda l: l[1]):
        m = re.fullmatch(r"\d{1,4}\s+(\D{3,80}?)|(\D{3,80}?)\s+\d{1,4}", text.strip())
        if y < 60 and m and not NOT_TITLE.match((m.group(1) or m.group(2)).strip()):
            return (m.group(1) or m.group(2)).strip()
    return ""


def _biggest(every: list, book_title: str) -> str:
    lines = [l for l in every
             if len(re.sub(r"[\W\d_]", "", l[2])) >= 3 and not NOT_TITLE.match(l[2].strip())
             and not re.search(r"\.{4,}|( \.){3,}", l[2])]
    book = _plain(book_title)
    for _ in range(4):
        if not lines:
            return ""
        top = max(h for h, _, _ in lines)
        big = sorted((l for l in lines if l[0] >= top * 0.8), key=lambda l: l[1])
        group, last = [big[0]], big[0][1]
        for l in big[1:]:
            if l[1] - last > big[0][0] * 2.2 or len(group) == 4 or l[2] in [g[2] for g in group]:
                break
            group.append(l)
            last = l[1]
        t = re.sub(r"\s+", " ", " ".join(g[2] for g in group))
        t = re.sub(r"^c\s*h\s*a\s*p\s*t\s*e\s*r\s*\d+\s*", "", t, flags=re.I)
        t = re.sub(r"^\d+\s+", "", t).strip(" :-–")
        t = re.sub(r"\s\d{1,4}(?=\s)", "", f" {t} ").strip()               # stray page numbers
        t = re.sub(r"^(.+?)(?: \1)+$", r"\1", t)                          # "Vocabulary Vocabulary"
        if book and _plain(t) and _plain(t) in book:   # the book's own name (a running header): look further
            lines = [l for l in lines if l not in group]
            continue
        return "" if len(t) > 90 or len(t) < 3 else t[0].upper() + t[1:]
    return ""


def part_order(name: str) -> tuple[int, int, str]:
    """Where a part goes in its book: front matter, chapters by number, appendices, back matter."""
    stem = PurePosixPath(name).stem.lower()
    tokens = re.split(r"[\s_\-.]+", stem)
    if any(t in FRONT for t in tokens):
        return (0, 0, stem)
    if any(t in BACK for t in tokens) or stem.replace(" ", "") in BACK:
        return (4, 0, stem)
    num = None
    for t in tokens:
        m = re.fullmatch(r"[a-z]*?(\d{1,2})", t)
        if m:
            num = int(m.group(1))
    m = re.search(r"\bapp(?:endix)?\s*([a-z0-9]+)\b|_app([a-z])\b", stem)
    if m:
        return (3, 0, stem)
    if num is not None:
        return (1, num, stem)
    return (2, 0, stem)


def part_label(name: str) -> str:
    """'Chapter 7' / 'Appendix A' / 'Glossary'... from the file name alone."""
    stem = PurePosixPath(name).stem.lower()
    tokens = re.split(r"[\s_\-.]+", stem)
    for t in tokens:
        if t in FRONT:
            return FRONT[t]
        if t in BACK:
            return BACK[t]
    if stem.replace(" ", "") in BACK:
        return BACK[stem.replace(" ", "")]
    m = re.search(r"\bapp(?:endix)?\s*([a-z0-9]+)\b|_app([a-z])\b", stem)
    if m:
        return f"Appendix {(m.group(1) or m.group(2)).upper()}"
    kind, num, _ = part_order(name)
    if kind == 1:
        return f"{'Guide' if 'guide' in stem else 'Chapter'} {num}"
    return ""


# --- reading -------------------------------------------------------------------------

def pdf_pages(path: Path) -> list[str]:
    r = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:200] or "pdftotext failed")
    pages = r.stdout.decode("utf-8", "replace").split("\f")
    if pages and not pages[-1].strip():      # after the last page's form feed: not a page
        pages.pop()
    return pages


def page_count(path: Path) -> int:
    """How many pages a PDF has (blank and scanned ones too), 0 if it can't be read."""
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m[1]) if m else 0


KEEP = re.compile(r"</?(p|h[1-6]|ul|ol|li|blockquote|pre|em|strong|b|i|br|hr|table|tr|td|th|dl|dt|dd)\b[^>]*>", re.I)
OPF = {"c": "urn:oasis:names:tc:opendocument:xmlns:container", "o": "http://www.idpf.org/2007/opf",
       "dc": "http://purl.org/dc/elements/1.1/"}


def epub(path: Path) -> tuple[str, list[str]]:
    """(title, chapters as safe HTML): text structure only, no scripts, styles or pictures."""
    with zipfile.ZipFile(path) as z:
        opf_path = ET.fromstring(z.read("META-INF/container.xml")).find(".//c:rootfile", OPF).get("full-path")
        opf = ET.fromstring(z.read(opf_path))
        base = PurePosixPath(opf_path).parent
        title = (opf.findtext(".//dc:title", "", OPF) or "").strip()
        hrefs = {i.get("id"): i.get("href") for i in opf.findall(".//o:manifest/o:item", OPF)}
        chapters = []
        for ref in opf.findall(".//o:spine/o:itemref", OPF):
            href = hrefs.get(ref.get("idref"))
            if not href:
                continue
            raw = z.read(str(base / href)).decode("utf-8", "replace")
            m = re.search(r"(?is)<body[^>]*>(.*)</body>", raw)
            raw = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", "", m.group(1) if m else raw)
            out, pos = [], 0
            for t in re.finditer(r"<[^>]+>", raw):
                out.append(html.escape(html.unescape(raw[pos:t.start()])))
                if KEEP.fullmatch(t.group(0)):
                    name = re.match(r"</?\s*(\w+)", t.group(0)).group(1).lower()
                    out.append(f"</{name}>" if t.group(0).startswith("</") else f"<{name}>")
                pos = t.end()
            out.append(html.escape(html.unescape(raw[pos:])))
            text = "".join(out).strip()
            if text:
                chapters.append(text)
    return title, chapters


def file_pages(path: Path) -> list[str]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return pdf_pages(path)
    if ext == ".epub":
        return [html.unescape(re.sub(r"<[^>]+>", " ", c)) for c in epub(path)[1]]
    return [path.read_text(errors="replace")]


# --- the index -----------------------------------------------------------------------

def connect(readonly: bool = True) -> sqlite3.Connection | None:
    db = settings.path("index")
    if readonly:
        if not db.exists():
            return None
        return sqlite3.connect(f"file:{db}?mode=ro", uri=True, check_same_thread=False)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    return con


def match_query(q: str, any_word: bool = False) -> str:
    """The FTS query for q: every word (or any), each also as its synonyms (terms.py)."""
    return terms.fts(q, any_word)


def _mark(snip: str) -> str:
    return html.escape(snip).replace("\x02", "<mark>").replace("\x03", "</mark>")


def hits(q: str, topic: str | None = None, limit: int = 200, any_word: bool = False) -> list[dict]:
    """Matching pages, best first: [{id, path, title, item, topic, page, snippet}] (id: the page's rowid)."""
    m = match_query(q, any_word)
    con = connect()
    if not m or con is None:
        return []
    try:
        sql = ("SELECT pages.rowid, pages.path, pages.title, docs.item, pages.topic, pages.page, "
               "snippet(pages, 0, char(2), char(3), ' … ', 26), bm25(pages, 1.0, 5.0) AS r "
               "FROM pages LEFT JOIN docs ON docs.path = pages.path WHERE pages MATCH ?")
        args: list = [m]
        if topic:
            sql += " AND pages.topic = ?"
            args.append(topic)
        sql += " ORDER BY r LIMIT ?"
        args.append(limit)
        rows = con.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return [{"id": i, "path": path, "title": title, "item": item, "topic": top, "page": int(page), "snippet": _mark(snip)}
            for i, path, title, item, top, page, snip, _ in rows]


def pages_by_id(ids: list[int]) -> dict[int, dict]:
    """{rowid: {id, path, title, item, topic, page, text}} for pages found some other way."""
    con = connect()
    if con is None or not ids:
        return {}
    try:
        rows = con.execute("SELECT pages.rowid, pages.path, pages.title, docs.item, pages.topic, pages.page, pages.text "
                           "FROM pages LEFT JOIN docs ON docs.path = pages.path WHERE pages.rowid IN "
                           f"({','.join('?' * len(ids))})", ids).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        con.close()
    return {r[0]: {"id": r[0], "path": r[1], "title": r[2], "item": r[3], "topic": r[4], "page": int(r[5]), "text": r[6]}
            for r in rows}


def group(found: list[dict], limit: int = 20, per_doc: int = 3) -> list[dict]:
    """Pages, best first, as documents, best first: [{path, url, title, item, topic, pages: [{page, snippet}]}]."""
    out: dict[str, dict] = {}
    for h in found:
        d = out.setdefault(h["path"], {"path": h["path"], "url": f"/read/{settings.url_path(h['path'])}",
                                       "title": h["title"], "item": h["item"], "topic": h["topic"], "pages": []})
        if len(d["pages"]) < per_doc:
            d["pages"].append({"page": h["page"], "snippet": h["snippet"]})
    return list(out.values())[:limit]


def search(q: str, topic: str | None = None, limit: int = 20, per_doc: int = 3, any_word: bool = False) -> list[dict]:
    """Documents with every word of q (or any), best first, with their best pages."""
    return group(hits(q, topic, limit * per_doc * 4, any_word), limit, per_doc)


def page_text(path: str, page: int) -> str:
    con = connect()
    if con is None:
        return ""
    try:
        row = con.execute("SELECT text FROM pages WHERE path = ? AND page = ?", (path, page)).fetchone()
    except sqlite3.Error:
        row = None
    finally:
        con.close()
    return row[0] if row else ""


def info(paths: list[str]) -> dict[str, dict]:
    """What the index knows about these files: {path: {title, label, sort, pages}}."""
    con = connect()
    if con is None or not paths:
        return {}
    try:
        q = f"SELECT path, title, label, sort, npages FROM docs WHERE path IN ({','.join('?' * len(paths))})"
        return {r[0]: {"title": r[1], "label": r[2], "sort": r[3], "pages": r[4]} for r in con.execute(q, paths)}
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def rel(p: Path) -> str:
    return str(p.relative_to(settings.path("docs")))


def file_for(relpath: str) -> Path | None:
    """A document's file from its docs-relative path; nothing outside docs/."""
    return settings.inside(settings.path("docs"), relpath)


def build(log=print, progress=None) -> dict:
    """Bring the index up to date with the documents on disk. Only new or changed files are read."""
    docs = settings.path("docs")
    con = connect(readonly=False)
    owner: dict[str, library.Item] = {}
    for it in library.items():
        for f in it.files() if it.kind in ("pdf", "epub", "book") else []:
            owner[rel(f)] = it
    want = {}
    for f in sorted(docs.rglob("*")) if docs.is_dir() else []:
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in (".pdf", ".epub", ".txt", ".md") \
                and ".partial" not in f.parts:
            want[rel(f)] = f
    known = {p: (m, s) for p, m, s in con.execute("SELECT path, mtime, size FROM docs")}
    gone = [p for p in known if p not in want]
    todo = [(r, f) for r, f in want.items() if known.get(r) != (int(f.stat().st_mtime), f.stat().st_size)]
    for r in gone + [r for r, _ in todo]:
        con.execute("DELETE FROM pages WHERE path = ?", (r,))
        con.execute("DELETE FROM docs WHERE path = ?", (r,))
    con.commit()
    failed = []
    for n, (r, f) in enumerate(todo, 1):
        it = owner.get(r)
        topic = r.split("/", 1)[0]
        if it and it.kind == "book":
            label = part_label(f.name)
            title = heading(f, it.title) if f.suffix.lower() == ".pdf" else ""
            title = title or label or f.stem
            sort = part_order(f.name)
            sort_key = sort[0] * 1000 + sort[1]
        else:
            title = (it.title if it else "") or (epub(f)[0] if f.suffix.lower() == ".epub" else "") \
                or re.sub(r"[_-]+", " ", f.stem).strip().capitalize()
            label, sort_key = "", 0
        if progress:
            progress(n, len(todo), title)
        try:
            pages = file_pages(f)
        except Exception as e:  # one unreadable file mustn't stop the rest
            failed.append((r, str(e)[:200]))
            log(f"couldn't read {r}: {e}")
            continue
        search_title = f"{it.title} · {title}" if it and it.kind == "book" else title
        con.executemany("INSERT INTO pages (text, title, path, topic, page) VALUES (?, ?, ?, ?, ?)",
                        [(t, search_title, r, topic, i) for i, t in enumerate(pages, 1) if t.strip()])
        st = f.stat()
        con.execute("INSERT INTO docs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (r, it.id if it else None, topic, title, label, sort_key, len(pages), int(st.st_mtime), st.st_size))
        con.commit()
    if con.execute("PRAGMA user_version").fetchone()[0] < 1:
        # Indexes made before 2026-10-31 counted only up to the last page with text on it
        # (a scanned book came out as a few pages): count them again, without reading them again.
        for r, in con.execute("SELECT path FROM docs WHERE path LIKE '%.pdf'").fetchall():
            if r in want:
                con.execute("UPDATE docs SET npages = ? WHERE path = ?", (page_count(want[r]), r))
        con.execute("PRAGMA user_version = 1")
        con.commit()
    con.execute("INSERT INTO pages(pages) VALUES ('optimize')")
    con.commit()
    con.close()
    settings.path("index").chmod(0o644)
    return {"files": len(want), "read": len(todo) - len(failed), "dropped": len(gone), "failed": failed}


# --- for the pages -------------------------------------------------------------------

def shelf(topic: str | None = None) -> list[dict]:
    """The documents of a topic for the website, books with their chapters in order.

    [{item, title, kind, topic, rel, url, size, print, pages, parts: [{title, label, rel, url, pages}]}]
    """
    out = []
    for it in library.items():
        if it.kind not in ("pdf", "epub", "book") or (topic and it.topic != topic):
            continue
        files = it.files()
        if not files:
            continue
        meta = info([rel(f) for f in files])
        parts = []
        if it.kind == "book":
            for f in files:
                m = meta.get(rel(f), {})
                parts.append({"title": m.get("title") or part_label(f.name) or f.stem, "label": m.get("label", ""),
                              "rel": rel(f),
                              "url": f"/read/{settings.url_path(rel(f))}", "pages": m.get("pages"),
                              "sort": m.get("sort", part_order(f.name)[0] * 1000 + part_order(f.name)[1])})
            parts.sort(key=lambda p: (p["sort"], p["title"].lower()))
        first = meta.get(rel(files[0]), {})
        out.append({"item": it.id, "title": it.title or first.get("title") or it.id, "kind": it.kind, "topic": it.topic,
                    "rel": rel(it.book_dir()) if it.kind == "book" else rel(files[0]),
                    "url": f"/book/{it.id}" if it.kind == "book" else f"/read/{settings.url_path(rel(files[0]))}",
                    "size": sum(f.stat().st_size for f in files), "print": it.print, "parts": parts,
                    "pages": first.get("pages")})
    out.sort(key=lambda d: d["title"].lower())
    return out


def loose(topic: str | None = None) -> list[dict]:
    """Documents on disk that aren't in the library list (copied in by hand), so they still show."""
    owned = set()
    for it in library.items():
        if it.kind in ("pdf", "epub", "book"):
            owned.update(rel(f) for f in it.files())
    docs = settings.path("docs")
    out = []
    for f in sorted(docs.rglob("*")) if docs.is_dir() else []:
        if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in (".pdf", ".epub", ".txt", ".md"):
            continue
        r = rel(f)
        if r in owned or (topic and not r.startswith(topic + "/")):
            continue
        out.append({"title": re.sub(r"[_-]+", " ", f.stem).strip().capitalize(), "url": f"/read/{settings.url_path(r)}", "rel": r,
                    "size": f.stat().st_size, "topic": r.split("/", 1)[0]})
    return out
