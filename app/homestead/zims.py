"""Encyclopedias and websites stored as ZIM files, read directly (python-libzim).

Every book is addressed by its Kiwix name (stable across releases):
    /wiki/<name>/<path>   a page or a picture inside it
The website wraps each page with its own top bar; links inside a book stay inside it.
"""
import html
import math
import re
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path

from libzim.reader import Archive
from libzim.search import Query, Searcher
from libzim.suggestion import SuggestionSearcher

from . import library, terms

_lock = threading.Lock()
_open: dict[str, tuple[float, Archive]] = {}   # path -> (mtime, archive)
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="zimsearch")


@dataclass
class Book:
    id: str
    topic: str
    title: str
    description: str
    path: Path
    articles: int
    searchable: bool
    essential: bool          # this copy is on the internal disk
    language: str
    has_icon: bool = False

    @property
    def url(self) -> str:
        return f"/wiki/{self.id}/"


def archive(path: Path) -> Archive:
    key = str(path)
    mtime = path.stat().st_mtime
    with _lock:
        hit = _open.get(key)
        if hit is None or hit[0] != mtime:
            hit = _open[key] = (mtime, Archive(key))
        return hit[1]


def _meta(a: Archive, name: str) -> str:
    try:
        return a.get_metadata(name).decode("utf-8", "replace").strip()
    except (KeyError, RuntimeError):
        return ""


_books: dict = {"key": None, "list": []}
LITE = ("nopic", "mini")


def _all_books() -> list[Book]:
    """Every ZIM on disk as a book, re-read only when the ZIM folders or the list change."""
    watch = [library.settings.zim_dir(True), library.settings.zim_dir(False),
             library.settings.path("list"), library.settings.path("changes")]
    key = tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in watch) + (str(watch[0]),)
    if _books["key"] != key:
        found = [b for b in (book_for(it) for it in library.items() if it.kind == "zim") if b]
        # A text-only copy (kept on the internal disk in case the USB drive fails) is hidden
        # while the full copy with pictures is here.
        full = {b.id.rsplit("_", 1)[0] for b in found if b.id.rsplit("_", 1)[-1] not in LITE}
        _books["list"] = [b for b in found if not (b.id.rsplit("_", 1)[-1] in LITE and b.id.rsplit("_", 1)[0] in full)]
        _books["key"] = key
    return _books["list"]


def books(topic: str | None = None) -> list[Book]:
    """The encyclopedias on disk (newest release of each)."""
    return [b for b in _all_books() if not topic or b.topic == topic]


def book_for(it: library.Item) -> Book | None:
    files = it.zim_files()
    for f in files:   # a damaged newest file shouldn't hide an older good one
        try:
            a = archive(f)
        except (RuntimeError, OSError):
            continue
        return Book(id=it.id, topic=it.topic, title=it.title or _meta(a, "Title") or it.id,
                    description=_meta(a, "Description"), path=f, articles=a.article_count,
                    searchable=a.has_fulltext_index, essential=f.parent == library.settings.zim_dir(True),
                    language=_meta(a, "Language"), has_icon=_has_icon(a))
    return None


def _has_icon(a: Archive) -> bool:
    try:
        if hasattr(a, "has_illustration"):
            return a.has_illustration(48)
        return 48 in a.get_illustration_sizes()          # older libzim
    except (AttributeError, RuntimeError, TypeError):
        return False


def get_book(book_id: str) -> Book | None:
    it = library.get(book_id)
    return book_for(it) if it and it.kind == "zim" else None


def icon(book: Book) -> bytes | None:
    a = archive(book.path)
    try:
        return bytes(a.get_illustration_item(48).content)
    except (KeyError, RuntimeError, AttributeError):
        return None


# --- reading -------------------------------------------------------------------------------

def main_path(book: Book) -> str:
    e = archive(book.path).main_entry
    return e.get_item().path if e.is_redirect else e.path


def entry(book: Book, path: str):
    """(kind, value): ("redirect", path) | ("item", (mimetype, bytes, title)) | ("missing", None)."""
    a = archive(book.path)
    try:
        e = a.get_entry_by_path(path)
    except KeyError:
        return "missing", None
    if e.is_redirect:
        return "redirect", e.get_redirect_entry().path
    it = e.get_item()
    return "item", (it.mimetype, bytes(it.content), it.title)


BODY = re.compile(rb"<body\b[^>]*>", re.I)


def wrap_page(content: bytes, bar: str) -> bytes:
    """The page with the website's bar at the top of its body."""
    bar_b = bar.encode()
    m = BODY.search(content)
    if not m:
        return bar_b + content
    return content[:m.end()] + bar_b + content[m.end():]


# --- search ---------------------------------------------------------------------------------

def _text(raw: bytes) -> str:
    s = raw.decode("utf-8", "replace")
    s = re.sub(r"(?is)<(script|style|head|nav|footer|table)\b.*?</\1>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def snippet(text: str, words: list[str], size: int = 240) -> str:
    """The part of a page with most of the search words; HTML with <mark>."""
    low = text.lower()
    stems = [w.lower()[:6] for w in words if len(w) > 2] or [w.lower() for w in words]
    best, score = 0, -1
    for start in range(0, max(1, len(text) - size), size // 3):
        win = low[start:start + size]
        s = sum(win.count(t) for t in stems)
        if s > score:
            best, score = start, s
    piece = text[best:best + size]
    out = html.escape(("… " if best else "") + piece + ("…" if best + size < len(text) else ""))
    for t in sorted(set(stems), key=len, reverse=True):
        out = re.sub(rf"(?i)\b({re.escape(html.escape(t))}\w*)", r"<mark>\1</mark>", out)
    return out


def page_text(book: Book, path: str, limit: int = 30000) -> tuple[str, str]:
    """(title, plain text) of a page."""
    kind, val = entry(book, path)
    if kind == "redirect":
        kind, val = entry(book, val)
    if kind != "item" or not val[0].startswith("text/html"):
        return "", ""
    return val[2], _text(val[1])[:limit]


def search_book(book: Book, q: str, start: int = 0, count: int = 10, snippets: bool = True) -> dict:
    """Full-text search in one book: {total, hits: [{title, url, snippet}]}. Synonyms count too (terms.py)."""
    words = terms.every_word(q) or re.findall(r"\w+", q)
    a = archive(book.path)
    paths, total = [], 0
    if a.has_fulltext_index:
        # the question as typed, and with other words for the same thing, taken in turn
        lists = []
        for v in terms.variants(q):
            s = Searcher(a).search(Query().set_query(v))
            total += s.getEstimatedMatches()
            lists.append(list(s.getResults(0, start + count)))
        paths = list(dict.fromkeys(p for row in zip_longest(*lists) for p in row if p))[start:start + count]
    if not paths and a.has_title_index:   # small books without a text index: titles only
        s = SuggestionSearcher(a).suggest(q)
        total = s.getEstimatedMatches()
        paths = list(s.getResults(start, count))
    hits = []
    for p in paths:
        title, text = page_text(book, p) if snippets else ("", "")
        if not title:
            try:
                title = a.get_entry_by_path(p).title
            except KeyError:
                continue
        hits.append({"title": title or p, "url": f"/wiki/{book.id}/{library.settings.url_path(p)}", "path": p,
                     "snippet": snippet(text, words) if text else ""})
    return {"total": total, "hits": hits}


def titles(book: Book, q: str, count: int = 5) -> list[dict]:
    a = archive(book.path)
    if not a.has_title_index:
        return []
    out = []
    for p in SuggestionSearcher(a).suggest(q).getResults(0, count):
        try:
            out.append({"title": a.get_entry_by_path(p).title, "url": f"/wiki/{book.id}/{library.settings.url_path(p)}", "path": p})
        except KeyError:
            pass
    return out


def search_all(q: str, topic: str | None = None, per_book: int = 3, max_books: int = 8,
               timeout: float = 8.0) -> list[dict]:
    """Search every book at once. Groups, best first: [{book, total, hits}].

    Books are ranked by how much of them is about the question (matches relative to the
    book's size), so a small medical book outranks Wikipedia's thousand passing mentions.
    """
    pool = books(topic)
    if not pool:
        return []

    def count(b: Book):
        a = archive(b.path)
        if not a.has_fulltext_index:
            return b, 0
        return b, sum(Searcher(a).search(Query().set_query(v)).getEstimatedMatches() for v in terms.variants(q))

    futs = [_pool.submit(count, b) for b in pool]
    done, _ = wait(futs, timeout=timeout)
    counted = [f.result() for f in done if not f.exception()]
    counted = [(b, n) for b, n in counted if n]
    counted.sort(key=lambda bn: bn[1] / math.sqrt(max(bn[0].articles, 1)) * (1.5 if bn[0].essential else 1),
                 reverse=True)
    top = counted[:max_books]
    # snippets for the best few books; titles only for the rest (each snippet is a page read)
    futs = {_pool.submit(search_book, b, q, 0, per_book, i < 4): (b, n) for i, (b, n) in enumerate(top)}
    done, _ = wait(futs, timeout=timeout)
    groups = []
    for f, (b, n) in futs.items():
        if f in done and not f.exception():
            r = f.result()
            if r["hits"]:
                groups.append({"book": b, "total": n, "hits": r["hits"]})
    order = {b.id: i for i, (b, _) in enumerate(top)}
    groups.sort(key=lambda g: order[g["book"].id])
    return groups
