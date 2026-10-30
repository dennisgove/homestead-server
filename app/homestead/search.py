"""One search across the whole library: documents (page by page), encyclopedias,
lessons, and places on the map.

Documents and lessons are found two ways at once, and the two lists are merged:
by their words (with synonyms, terms.py) and by their meaning (semantic.py), so a
page that answers the question in other words still comes up.
"""
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor

from . import courses, documents, maps, semantic, terms, zims

_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="search")

STOP = terms.STOP
words = terms.words

RRF = 60    # how strongly the top of each list counts more than the rest (reciprocal rank fusion)


def fuse(*lists: list) -> list:
    """Merge best-first lists of ids into one best-first list: a page near the top of
    both lists comes first, then pages near the top of either."""
    score: dict = {}
    for ids in lists:
        for rank, i in enumerate(ids):
            score[i] = score.get(i, 0.0) + 1.0 / (RRF + rank)
    return sorted(score, key=score.get, reverse=True)


def _vector(qv):
    try:
        return qv.result() if isinstance(qv, Future) else qv
    except Exception:   # no meaning search this time; words still work
        return None


def pages(keys: str | list[str], qv=None, topic: str | None = None, limit: int = 15,
          per_doc: int = 3) -> tuple[list[dict], bool]:
    """(documents with their best pages, loose) for search words and a question's meaning.

    keys: search words, or several tries in order (the first with matches is used).
    qv: the question's meaning (semantic.query_vector), or a Future of it, or None.
    loose: True when nothing had every word and the pages shown have only some of them.
    """
    keys = [keys] if isinstance(keys, str) else keys
    n = limit * per_doc * 4
    by_words = []
    for k in keys:
        by_words = documents.hits(k, topic, n)
        if by_words:
            break
    by_meaning = semantic.pages(_vector(qv), topic, n)
    loose = False
    if not by_words and not by_meaning and len(words(" ".join(keys))) > 1:
        by_words = documents.hits(" ".join(keys), topic, n, any_word=True)
        loose = bool(by_words)
    found = {h["id"]: h for h in by_words}
    extra = documents.pages_by_id([i for i, _, _ in by_meaning if i not in found])
    hl = terms.every_word(" ".join(keys))
    for i, pos, _ in by_meaning:
        if i in extra:
            h = extra[i]
            text = semantic.flat(h.pop("text"))
            h["snippet"] = zims.snippet(text[pos:pos + semantic.CHUNK], hl, 260)
            found[i] = h
    order = fuse([h["id"] for h in by_words], [i for i, _, _ in by_meaning if i in found])
    return documents.group([found[i] for i in order], limit, per_doc), loose


def lessons(key: str, qv=None, limit: int = 12) -> list[dict]:
    by_words = courses.search(key, limit=limit * 2)
    by_meaning = semantic.lessons(_vector(qv), limit * 2)
    found = {h["node"]: h for h in by_words}
    found.update(courses.lessons_by_node([n for n, _ in by_meaning if n not in found]))
    order = fuse([h["node"] for h in by_words], [n for n, _ in by_meaning if n in found])
    return [found[n] for n in order[:limit]]


def everything(q: str, topic: str | None = None) -> dict:
    """{documents, encyclopedias, lessons, places}; each part fails on its own without breaking the rest."""
    def safe(f, *a, **k):
        try:
            return f(*a, **k)
        except (OSError, RuntimeError, sqlite3.Error, ValueError):
            return []
    key = " ".join(words(q)) or q     # "how to splint a broken arm" -> "splint broken arm"
    qv = _pool.submit(semantic.query_vector, q)   # the whole question: its meaning, not just its words
    want_lessons = topic in (None, "learning")
    jobs = {
        "documents": _pool.submit(safe, pages, key, qv, topic, 15),
        "encyclopedias": _pool.submit(safe, zims.search_all, key, topic),
        "lessons": _pool.submit(safe, lessons, key, qv) if want_lessons else None,
        "places": _pool.submit(safe, maps.places, q, 5) if topic is None else None,
    }
    out = {k: (f.result() if f else []) for k, f in jobs.items()}
    out["documents"], out["loose"] = out["documents"] or ([], False)
    return out
