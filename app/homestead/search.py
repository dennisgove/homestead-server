"""One search across the whole library: documents (page by page), encyclopedias,
lessons, and places on the map."""
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from . import courses, documents, maps, zims

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="search")

STOP = set("""a an and are as at be but by can do does for from how i if in into is it its me my of on or
should so than that the their them then there these they this to was what when where which who why will
with would you your about after before during without we our us have has had get got make made need
long much many best way use using tell know want""".split())


def words(q: str) -> list[str]:
    return [w for w in re.findall(r"[\w'-]+", q.lower()) if w not in STOP and len(w) > 1]


def everything(q: str, topic: str | None = None) -> dict:
    """{documents, encyclopedias, lessons, places}; each part fails on its own without breaking the rest."""
    def safe(f, *a, **k):
        try:
            return f(*a, **k)
        except (OSError, RuntimeError, sqlite3.Error, ValueError):
            return []
    key = " ".join(words(q)) or q     # "how to splint a broken arm" -> "splint broken arm"
    jobs = {
        "documents": _pool.submit(safe, documents.search, key, topic, 15),
        "encyclopedias": _pool.submit(safe, zims.search_all, key, topic),
        "lessons": _pool.submit(safe, courses.search, key) if topic in (None, "learning") else None,
        "places": _pool.submit(safe, maps.places, q, 5) if topic is None else None,
    }
    out = {k: (f.result() if f else []) for k, f in jobs.items()}
    if not out["documents"] and len(words(q)) > 1:   # nothing has every word: pages with the most of them
        out["documents"] = safe(documents.search, key, topic, 15, 3, True)
        out["loose"] = True
    return out
