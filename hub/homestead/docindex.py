"""Full-text search of the documents (PDFs and text files under docs/), page by page.

The index is a SQLite FTS5 file built by the docindex job (jobs/docindex.py);
the Hub only reads it. Each row is one page of one document.
"""
import html
import re
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime INTEGER, size INTEGER, pages INTEGER);
CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(
    text, title, path UNINDEXED, category UNINDEXED, page UNINDEXED,
    tokenize = 'porter unicode61 remove_diacritics 2');
"""


def db_path() -> Path:
    return config.path("hub_state") / "docs.sqlite"


def match_query(q: str, any_word: bool = False) -> str:
    """Every word must appear (prefix match on the last one, as people type),
    or with any_word, at least one (best matches still rank first)."""
    words = re.findall(r"\w+", q.lower())
    if not words:
        return ""
    parts = [f'"{w}"' for w in words[:-1]] + [f'"{words[-1]}"*']
    return (" OR " if any_word else " ").join(parts)


def _highlight(snip: str) -> str:
    """Snippet with \x02...\x03 markers -> safe HTML with <mark>."""
    return html.escape(snip).replace("\x02", "<mark>").replace("\x03", "</mark>")


def search(q: str, category: str | None = None, limit: int = 20, per_doc: int = 3,
           any_word: bool = False) -> list[dict]:
    """Documents matching q, best first; each with its best pages.

    [{title, path, category, pages: [{page, snippet_html}]}]  (path is relative to docs/)
    """
    m = match_query(q, any_word)
    db = db_path()
    if not m or not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        sql = ("SELECT path, title, category, page, snippet(pages, 0, char(2), char(3), ' … ', 28), "
               "bm25(pages, 1.0, 4.0) AS r FROM pages WHERE pages MATCH ?")
        args: list = [m]
        if category:
            sql += " AND category = ?"
            args.append(category)
        sql += " ORDER BY r LIMIT ?"
        args.append(limit * per_doc * 4)
        rows = con.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    docs: dict[str, dict] = {}
    for path, title, cat, page, snip, _r in rows:
        d = docs.setdefault(path, {"title": title, "path": path, "category": cat, "pages": []})
        if len(d["pages"]) < per_doc:
            d["pages"].append({"page": int(page), "snippet_html": _highlight(snip)})
    return list(docs.values())[:limit]


def page_text(path: str, page: int) -> str:
    db = db_path()
    if not db.exists():
        return ""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT text FROM pages WHERE path = ? AND page = ?", (path, page)).fetchone()
    except sqlite3.Error:
        row = None
    finally:
        con.close()
    return row[0] if row else ""


def stats() -> dict:
    db = db_path()
    if not db.exists():
        return {"files": 0, "pages": 0}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        files = con.execute("SELECT count(*), coalesce(sum(pages), 0) FROM files").fetchone()
    except sqlite3.Error:
        files = (0, 0)
    finally:
        con.close()
    return {"files": files[0], "pages": files[1]}
