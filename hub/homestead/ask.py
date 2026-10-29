"""The Hub's Ask page: answer a question from the library, with the local AI.

Finds passages for the question (the documents' full-text index and every Kiwix
library), then streams the planner model's answer from Ollama, citing the
passages as [1], [2]... No accounts: nothing is stored on the server.
"""
import json
import urllib.request

from . import config, content, docindex, librarysearch

SYSTEM_EXTRA = """
Passages from the homestead library are given below, numbered. Answer from them
when they cover the question, and cite them inline like [1] or [2]. If they don't
cover it, say so plainly, then answer from general knowledge and say that you are.
Never invent a drug dose; point to the cited page instead.
"""


def doc_sources(question: str, terms: str, n: int = 2, start: int = 1) -> tuple[list[dict], list[str]]:
    """The best document pages: every search word if possible, else the pages with the most of them."""
    simple = librarysearch.keywords_simple(question)
    hits = (docindex.search(terms, limit=n, per_doc=1) or docindex.search(simple, limit=n, per_doc=1)
            or docindex.search(f"{terms} {simple}", limit=n, per_doc=1, any_word=True))
    terms = [t for t in f"{terms} {simple}".lower().split() if len(t) > 2]
    sources, parts = [], []
    for i, h in enumerate(hits, start):
        page = h["pages"][0]["page"]
        text = librarysearch.best_passage(" ".join(docindex.page_text(h["path"], page).split()), terms)
        sources.append({"n": i, "title": f"{h['title']}, p. {page}", "book": "Document",
                        "url": f"{content.doc_url(h['path'])}#page={page}"})
        parts.append(f"[{i}] {h['title']}, page {page}\n{text}")
    return sources, parts


def gather(question: str) -> tuple[list[dict], str]:
    terms = librarysearch.keywords_ai(question)
    srcs, parts = doc_sources(question, terms)
    lib = librarysearch.context(question, max_articles=2, start=len(srcs) + 1, terms=terms)
    srcs += lib["sources"]
    return srcs, "\n\n".join(parts + ([lib["context"]] if lib["context"] else []))


def stream(question: str, history: list[dict]):
    """NDJSON lines: {"sources": [...]}, then {"t": "..."} pieces, then {"done": true} or {"error": "..."}."""
    cfg = config.load()["ai"]
    yield json.dumps({"status": "Searching the library…"}) + "\n"
    try:
        sources, passages = gather(question)
    except Exception as e:  # search trouble shouldn't stop the answer
        sources, passages = [], ""
        yield json.dumps({"status": f"Library search failed ({e}); answering without it…"}) + "\n"
    yield json.dumps({"sources": sources}) + "\n"
    yield json.dumps({"status": "Reading the sources and writing an answer (about a minute on this computer)…"}) + "\n"
    msgs = [{"role": "system", "content": SYSTEM_EXTRA}]
    for m in history[-6:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": m["content"][:4000]})
    user = question if not passages else f"Library passages:\n\n{passages}\n\nQuestion: {question}"
    msgs.append({"role": "user", "content": user})
    body = {"model": cfg.get("model", "homestead-planner"), "messages": msgs, "stream": True, "think": False,
            "keep_alive": "30m"}
    req = urllib.request.Request(cfg["ollama"].rstrip("/") + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            for line in r:
                if not line.strip():
                    continue
                part = json.loads(line)
                piece = part.get("message", {}).get("content", "")
                if piece:
                    yield json.dumps({"t": piece}) + "\n"
                if part.get("done"):
                    break
    except OSError as e:
        yield json.dumps({"error": "The AI isn't running right now (power saving, or still starting). "
                                   f"The sources above are still worth reading. ({e})"}) + "\n"
        return
    yield json.dumps({"done": True}) + "\n"
