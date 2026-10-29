"""Build the documents' full-text index (homestead-docindex.service).

Every PDF (and EPUB, .txt and .md file) under docs/ goes into a SQLite FTS5 index, one row
per page, for the Hub's search and Ask pages. Incremental: only new or changed
files are read again. The new index is built next to the old one and swapped in,
so the Hub never sees a half-built file.
"""
import html
import os
import re
import shutil
import sqlite3
import subprocess

from .. import catalog, config, docindex, epub
from .common import Job

TEXT_EXTS = (".txt", ".md")


def pdf_pages(path) -> list[str]:
    r = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:200] or "pdftotext failed")
    pages = r.stdout.decode("utf-8", "replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def epub_pages(path) -> list[str]:
    """One "page" per chapter of an ebook, as plain text."""
    _title, body = epub.to_html(path)
    return [html.unescape(re.sub(r"<[^>]+>", " ", ch)) for ch in body.split("\n<hr>\n")]


def file_pages(path) -> list[str]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return pdf_pages(path)
    if ext == ".epub":
        return epub_pages(path)
    return [path.read_text(errors="replace")]


def main(argv=None):
    docs = config.path("docs")
    db = docindex.db_path()
    tmp = db.with_suffix(".new")
    with Job("docindex") as job:
        db.parent.mkdir(parents=True, exist_ok=True)
        tmp.unlink(missing_ok=True)
        if db.exists():
            shutil.copyfile(db, tmp)
        con = sqlite3.connect(tmp)
        con.executescript(docindex.SCHEMA)
        known = {p: (m, s) for p, m, s in con.execute("SELECT path, mtime, size FROM files")}
        titles = catalog.doc_titles()
        want = {}
        for f in sorted(docs.rglob("*")) if docs.is_dir() else []:
            if (f.is_file() and not f.name.startswith(".") and ".homestead-partial" not in str(f)
                    and f.suffix.lower() in (".pdf", ".epub", *TEXT_EXTS)):
                want[str(f.relative_to(docs))] = f
        gone = [p for p in known if p not in want]
        todo = [(rel, f) for rel, f in want.items()
                if known.get(rel) != (int(f.stat().st_mtime), f.stat().st_size)]
        for rel in gone + [rel for rel, _ in todo]:
            con.execute("DELETE FROM pages WHERE path = ?", (rel,))
            con.execute("DELETE FROM files WHERE path = ?", (rel,))
        job.status["total"] = len(todo)
        failed = 0
        for n, (rel, f) in enumerate(todo, 1):
            title = catalog.doc_title(f, titles)
            job.status["current"], job.status["done"] = title, n - 1
            job.save()
            try:
                pages = file_pages(f)
            except Exception as e:  # one unreadable file mustn't stop the rest
                failed += 1
                job.item(rel, state="failed", error=str(e)[:200])
                continue
            cat = rel.split("/", 1)[0]
            con.executemany("INSERT INTO pages (text, title, path, category, page) VALUES (?, ?, ?, ?, ?)",
                            [(t, title, rel, cat, i) for i, t in enumerate(pages, 1) if t.strip()])
            st = f.stat()
            con.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (rel, int(st.st_mtime), st.st_size, len(pages)))
            con.commit()
            job.status["items"].pop(rel, None)
        con.commit()
        con.execute("INSERT INTO pages(pages) VALUES ('optimize')")
        con.commit()
        con.close()
        os.chmod(tmp, 0o644)  # the Hub reads it as its own user
        os.replace(tmp, db)
        job.status["done"] = len(todo)
        job.log(f"{len(want)} documents indexed ({len(todo) - failed} read now, {len(gone)} dropped, {failed} failed)")


if __name__ == "__main__":
    main()
