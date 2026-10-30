"""Ask: the local AI answers a question from the library.

1. A small model turns the question into a few search words.
2. Those words, and the question's meaning, find the best document pages and
   encyclopedia articles.
3. The main model answers from those passages, citing them as [1], [2]…, streamed
   to the page as it writes. Nothing is stored.
"""
import json
import re
import urllib.request

from . import documents, search, semantic, settings, zims

PROMPT = """You answer questions on an offline homestead library computer. The internet,
hospitals and stores may be unavailable. The person asking may be stressed, injured,
or have no training.

Numbered passages from the library are below. Answer from them, citing them inline
like [1] or [2]. If they don't cover the question, say so in one sentence, then answer
from general knowledge and say that's what you're doing.

- Be practical: steps, amounts, materials likely to be on hand.
- Medical: the life-saving action first. Never invent a drug dose; point to the cited page.
- Food and water safety: follow tested USDA/CDC/WHO methods; say when a shortcut is dangerous.
- Planning: show the arithmetic so it can be checked.
- Short and plain unless asked for more."""


def _ollama(path: str, body: dict, timeout: int):
    cfg = settings.load()["ai"]
    req = urllib.request.Request(cfg["ollama"].rstrip("/") + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def search_words(question: str) -> str:
    """2–4 words to look up, from the small model; the question's own key words if it's slow or off."""
    cfg = settings.load()["ai"]
    try:
        with _ollama("/api/generate", {
            "model": cfg["helper"], "stream": False, "think": False, "keep_alive": "30m",
            "options": {"num_predict": 12, "temperature": 0},
            "prompt": ("Give the 2 to 4 most important words to look up in a library index to answer this "
                       "question. Reply with only the words.\nQuestion: " + question + "\nWords:")}, 15) as r:
            text = json.load(r).get("response", "")
    except (OSError, ValueError):
        text = ""
    text = " ".join(re.sub(r"[^\w\s'-]", " ", text.split("\n")[0]).split()[:4])
    return text or " ".join(search.words(question)[:4])


def passages(question: str) -> tuple[list[dict], str]:
    """(sources, text for the model): up to 2 document pages and 2 encyclopedia articles."""
    qv = search._pool.submit(semantic.query_vector, question)
    terms = search_words(question)
    own = " ".join(search.words(question))
    hits, _ = search.pages([terms, own], qv, limit=2, per_doc=1)
    key = [w for w in f"{terms} {own}".lower().split() if len(w) > 2]
    sources, parts = [], []
    for h in hits:
        page = h["pages"][0]["page"]
        # the whole page (tables lose their meaning when cut), up to a limit
        text = best_window(" ".join(documents.page_text(h["path"], page).split()), key, size=3000)
        n = len(sources) + 1
        sources.append({"n": n, "title": f"{h['title']}, page {page}", "url": f"{h['url']}#page={page}"})
        parts.append(f"[{n}] {h['title']}, page {page}\n{text}")
    for g in zims.search_all(terms, per_book=2, max_books=3)[:3]:
        for hit in g["hits"][:1]:
            title, text = zims.page_text(g["book"], hit["path"])
            if not text or not relevant(title + " " + text[:3000], key):
                continue
            n = len(sources) + 1
            sources.append({"n": n, "title": f"{title} ({g['book'].title})", "url": hit["url"]})
            parts.append(f"[{n}] {title} ({g['book'].title})\n{best_window(text, key)}")
            if n >= 4:
                break
        if len(sources) >= 4:
            break
    return sources, "\n\n".join(parts)


def relevant(text: str, key: list[str]) -> bool:
    low = text.lower()
    stems = {w[:5] for w in key}
    return bool(stems) and sum(1 for s in stems if s in low) * 2 >= len(stems)


def best_window(text: str, key: list[str], size: int = 1100) -> str:
    if len(text) <= size:
        return text
    low, stems = text.lower(), [w[:6] for w in key]
    best, score = 0, -1
    for start in range(0, len(text) - size + 1, size // 4):
        s = sum(low[start:start + size].count(t) for t in stems)
        if s > score:
            best, score = start, s
    return text[best:best + size]


def answer(question: str, history: list[dict]):
    """Lines of JSON for the page: status, sources, pieces of the answer, then done or error."""
    yield json.dumps({"status": "Looking it up in the library…"}) + "\n"
    try:
        sources, text = passages(question)
    except Exception as e:  # a search problem shouldn't stop the answer
        sources, text = [], ""
        yield json.dumps({"status": f"The library search failed ({e}); answering without it…"}) + "\n"
    yield json.dumps({"sources": sources}) + "\n"
    yield json.dumps({"status": "Writing the answer (this computer takes about half a minute to start)…"}) + "\n"
    msgs = [{"role": "system", "content": PROMPT}]
    for m in history[-6:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": m["content"][:4000]})
    msgs.append({"role": "user", "content": f"Library passages:\n\n{text}\n\nQuestion: {question}" if text else question})
    cfg = settings.load()["ai"]
    try:
        with _ollama("/api/chat", {"model": cfg["model"], "messages": msgs, "stream": True, "think": False,
                                   "keep_alive": "30m"}, 600) as r:
            for line in r:
                if not line.strip():
                    continue
                part = json.loads(line)
                piece = part.get("message", {}).get("content", "")
                if piece:
                    yield json.dumps({"t": piece}) + "\n"
                if part.get("done"):
                    break
    except OSError:
        yield json.dumps({"error": "The AI isn't running right now (power saving, or still starting up). "
                                   "The sources above still answer most questions."}) + "\n"
        return
    yield json.dumps({"done": True}) + "\n"
