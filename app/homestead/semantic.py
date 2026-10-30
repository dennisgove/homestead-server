"""Meaning search: finds document pages and lessons that are about the question even when
they use other words ("green beans" finds a page about "snap beans").

The index job asks the AI engine (Ollama) for an embedding of every page and lesson (a
list of numbers that stands for what the text means) and keeps them in the search index.
A search turns the question into the same kind of numbers and finds the closest ones.
That takes the AI engine about a twentieth of a second per question; when the engine is
off (power saving), search simply goes on with words alone.

The first run takes a couple of hours on this computer; after that only new documents
and lessons are added.
"""
import hashlib
import json
import threading
import time
import urllib.request

import numpy as np

from . import documents, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS vec_pages (page INTEGER, pos INTEGER, path TEXT, vec BLOB);  -- page: rowid in pages
CREATE INDEX IF NOT EXISTS vec_pages_path ON vec_pages(path);
CREATE TABLE IF NOT EXISTS vec_docs (path TEXT PRIMARY KEY, stamp TEXT);              -- documents finished
CREATE TABLE IF NOT EXISTS vec_lessons (node TEXT PRIMARY KEY, hash TEXT, vec BLOB);
CREATE TABLE IF NOT EXISTS vec_state (key TEXT PRIMARY KEY, value TEXT);
"""

CHUNK = 1500        # characters of a page per embedding (a long page gets several)
MIN_TEXT = 150      # pages with less text than this (covers, blank pages) are skipped
DIMS = 768          # dimensions used for searching (fewer is faster but lets nonsense match)
MIN_SCORE = 0.40    # weaker matches than this aren't shown (real ones scored 0.42+, junk 0.33 or less)
NEAR_BEST = 0.15    # nor ones this far below the best match

# How each model wants questions and passages introduced.
PROMPTS = {
    "embeddinggemma": ("task: search result | query: {q}", "title: {title} | text: {text}"),
    "nomic-embed-text": ("search_query: {q}", "search_document: {title}. {text}"),
}


def model() -> str:
    return settings.load()["ai"].get("embed", "")


def _prompts() -> tuple[str, str]:
    m = model()
    for name, p in PROMPTS.items():
        if m.startswith(name):
            return p
    return "{q}", "{title}. {text}"


def embed(texts: list[str], timeout: float = 600, threads: int | None = None) -> np.ndarray:
    """Unit-length float32 vectors for texts, one row each. OSError when the engine isn't there."""
    cfg = settings.load()["ai"]
    body = {"model": model(), "input": texts, "keep_alive": "24h", "truncate": True}
    if threads:
        body["options"] = {"num_thread": threads}
    req = urllib.request.Request(cfg["ollama"].rstrip("/") + "/api/embed", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        v = np.asarray(json.load(r)["embeddings"], dtype=np.float32)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def chunks(text: str) -> list[tuple[int, str]]:
    """(start, piece) pieces of about CHUNK characters, cut between words."""
    out, start = [], 0
    while start < len(text):
        end = len(text) if len(text) - start <= CHUNK * 1.3 else text.rfind(" ", start, start + CHUNK)
        end = start + CHUNK if end <= start else end
        out.append((start, text[start:end]))
        start = end + 1
    return out


def flat(text: str) -> str:
    return " ".join(text.split())


# --- building ---------------------------------------------------------------------------

def _blob(v: np.ndarray) -> bytes:
    return v.astype(np.float16).tobytes()


def build(log=print, progress=None, threads: int = 4) -> dict:
    """Embed what isn't embedded yet. Stops (and picks up next time) if the engine goes away."""
    if not model():
        return {"skipped": "no embedding model set"}
    con = documents.connect(readonly=False)
    con.executescript(SCHEMA)
    state = dict(con.execute("SELECT key, value FROM vec_state"))
    if state.get("model") != model():      # a different model's numbers can't be mixed in
        con.executescript("DELETE FROM vec_pages; DELETE FROM vec_docs; DELETE FROM vec_lessons;")
        con.execute("INSERT OR REPLACE INTO vec_state VALUES ('model', ?)", (model(),))
        con.commit()
    doc_p = _prompts()[1]
    out = {"pages": 0, "lessons": 0}
    last_bump = time.time()

    def bump(force=False):
        nonlocal last_bump
        if force or time.time() - last_bump > 600:     # the website reloads the numbers when this changes
            con.execute("INSERT OR REPLACE INTO vec_state VALUES ('version', ?)", (str(time.time()),))
            con.commit()
            last_bump = time.time()

    def run(batches, total, what, store):
        done, t0 = 0, time.time()
        for batch in batches:
            vecs = embed([t for t, _ in batch], threads=threads)
            store(batch, vecs)
            con.commit()
            done += len(batch)
            out[what] += len(batch)
            if progress:
                left = (time.time() - t0) / done * (total - done)
                progress(f"meaning search: {what} ({done:,} of {total:,}, about {left / 60:.0f} min left)",
                         done, total)
            bump()

    try:
        # documents: drop what changed or went, then embed the pages not yet done
        docs = {p: f"{m}:{s}" for p, m, s in con.execute("SELECT path, mtime, size FROM docs")}
        finished = dict(con.execute("SELECT path, stamp FROM vec_docs"))
        for p in [p for p, m in finished.items() if docs.get(p) != m]:
            con.execute("DELETE FROM vec_docs WHERE path = ?", (p,))
        con.execute("DELETE FROM vec_pages WHERE path NOT IN (SELECT path FROM docs)")
        finished = {p for p, m in finished.items() if docs.get(p) == m}
        todo = [p for p in docs if p not in finished]
        if todo:
            want = set(todo)
            pages: dict[str, list] = {}
            for rowid, path, text, title in con.execute("SELECT rowid, path, text, title FROM pages"):
                if path in want:
                    pages.setdefault(path, []).append((rowid, flat(text), title))
            items = []
            for path in todo:
                rows = pages.get(path, [])
                have = {r for (r,) in con.execute("SELECT DISTINCT page FROM vec_pages WHERE path = ?", (path,))}
                live = {r for r, _, _ in rows}
                con.executemany("DELETE FROM vec_pages WHERE path = ? AND page = ?",
                                [(path, r) for r in have - live])
                for rowid, text, title in rows:
                    if rowid in have or len(text) < MIN_TEXT:
                        continue
                    for pos, piece in chunks(text):
                        items.append((doc_p.format(title=title or "none", text=piece), (path, rowid, pos)))
                items.append((None, (path, None, None)))     # marks the document finished
            log(f"meaning search: {len(todo)} documents to do")

            def doc_batches():
                batch = []
                for text, ref in items:
                    if text is None:
                        if batch:
                            yield batch
                            batch = []
                        con.execute("INSERT OR REPLACE INTO vec_docs VALUES (?, ?)", (ref[0], docs[ref[0]]))
                        continue
                    batch.append((text, ref))
                    if len(batch) == 16:
                        yield batch
                        batch = []
                if batch:
                    yield batch

            def store_pages(batch, vecs):
                con.executemany("INSERT INTO vec_pages VALUES (?, ?, ?, ?)",
                                [(rowid, pos, path, _blob(v)) for (_, (path, rowid, pos)), v in zip(batch, vecs)])
            run(doc_batches(), sum(1 for t, _ in items if t), "pages", store_pages)
            con.commit()
            bump(force=True)

        # lessons: titles, where they sit, and their descriptions
        want = {}
        for title, desc, place, kind, node in con.execute("SELECT title, description, place, kind, node FROM lessons"):
            text = doc_p.format(title=title, text=f"{place}. {(desc or '')[:600]}".strip(". "))
            want[node] = (text, hashlib.sha1(text.encode()).hexdigest()[:16])
        have = dict(con.execute("SELECT node, hash FROM vec_lessons"))
        con.executemany("DELETE FROM vec_lessons WHERE node = ?",
                        [(n,) for n, h in have.items() if want.get(n, (None, None))[1] != h])
        todo = [(t, (n, h)) for n, (t, h) in want.items() if have.get(n) != h]
        if todo:
            log(f"meaning search: {len(todo):,} lessons to do")

            def store_lessons(batch, vecs):
                con.executemany("INSERT OR REPLACE INTO vec_lessons VALUES (?, ?, ?)",
                                [(n, h, _blob(v)) for (_, (n, h)), v in zip(batch, vecs)])
            run((todo[i:i + 32] for i in range(0, len(todo), 32)), len(todo), "lessons", store_lessons)
        bump(force=True)
    except OSError as e:
        con.commit()
        bump(force=True)
        log(f"meaning search stopped: the AI engine isn't answering ({e}); it carries on next time")
        out["stopped"] = True
    finally:
        con.close()
    return out


# --- searching --------------------------------------------------------------------------

class _Store:
    """The numbers, in memory, reloaded when the index job has added more."""
    lock = threading.Lock()
    version = None
    checked = 0.0
    pages = None        # (matrix, rowids, positions, topics)
    lessons = None      # (matrix, nodes)


def reset():
    """Forget the numbers in memory (the tests use a new index each time)."""
    _Store.version, _Store.checked, _Store.pages, _Store.lessons = None, 0.0, None, None


def _norm(raw: list[bytes]) -> np.ndarray:
    m = np.frombuffer(b"".join(raw), dtype=np.float16).reshape(len(raw), -1)[:, :DIMS].astype(np.float32)
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)


def _load():
    with _Store.lock:
        if time.time() - _Store.checked < 30:
            return
        _Store.checked = time.time()
        con = documents.connect()
        if con is None:
            return
        try:
            row = con.execute("SELECT value FROM vec_state WHERE key = 'version'").fetchone()
            if not row or row[0] == _Store.version:
                return
            rows = con.execute("SELECT v.page, v.pos, d.topic, v.vec FROM vec_pages v "
                               "JOIN docs d ON d.path = v.path").fetchall()
            _Store.pages = (_norm([r[3] for r in rows]), np.array([r[0] for r in rows]),
                            np.array([r[1] for r in rows]), np.array([r[2] or "" for r in rows])) if rows else None
            rows = con.execute("SELECT node, vec FROM vec_lessons").fetchall()
            _Store.lessons = (_norm([r[1] for r in rows]), [r[0] for r in rows]) if rows else None
            _Store.version = row[0]
        except Exception:   # no numbers yet, or a half-written index: search goes on with words
            return
        finally:
            con.close()


def ready() -> bool:
    _load()
    return _Store.pages is not None or _Store.lessons is not None


def query_vector(q: str) -> np.ndarray | None:
    """The question's numbers, or None (no numbers built yet, or the engine is off or slow)."""
    if not q.strip() or not model() or not ready():
        return None
    try:
        v = embed([_prompts()[0].format(q=q)], timeout=4)[0][:DIMS]
    except (OSError, ValueError, KeyError):
        return None
    return v / max(float(np.linalg.norm(v)), 1e-9)


def _best(m: np.ndarray, qv: np.ndarray, k: int, mask=None) -> list[tuple[int, float]]:
    s = m @ qv
    if mask is not None:
        s = np.where(mask, s, -1.0)
    idx = np.argpartition(-s, min(k, len(s) - 1))[:k]
    idx = idx[np.argsort(-s[idx])]
    top = float(s[idx[0]]) if len(idx) else 0.0
    return [(int(i), float(s[i])) for i in idx if s[i] >= MIN_SCORE and s[i] >= top - NEAR_BEST]


def pages(qv: np.ndarray | None, topic: str | None = None, k: int = 40) -> list[tuple[int, int, float]]:
    """[(rowid in pages, position in the page's text, score)], best first, one per page."""
    if qv is None or _Store.pages is None:
        return []
    m, rowids, pos, topics = _Store.pages
    out, seen = [], set()
    for i, s in _best(m, qv, k * 3, (topics == topic) if topic else None):
        if rowids[i] not in seen:
            seen.add(rowids[i])
            out.append((int(rowids[i]), int(pos[i]), s))
    return out[:k]


def lessons(qv: np.ndarray | None, k: int = 20) -> list[tuple[str, float]]:
    """[(node, score)], best first."""
    if qv is None or _Store.lessons is None:
        return []
    m, nodes = _Store.lessons
    return [(nodes[i], s) for i, s in _best(m, qv, k)]
