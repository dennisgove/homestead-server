"""Library search for the AI: question -> search terms -> Kiwix full-text search
across every ZIM -> the best passages, with their titles, to put in the prompt.

Used by the Open WebUI filter (via /api/library/context) and by the Hub's own AI endpoint.
"""
import json
import re
import urllib.request
from itertools import zip_longest

from . import config, kiwix

STOP = set("""a an and are as at be but by can do does for from how i if in into is it its me my of on or
should so than that the their them then there these they this to was what when where which who why will
with would you your about after before during without we our us have has had get got make made need""".split())


def keywords_simple(question: str) -> str:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", question.lower())
    kept = [w for w in words if w not in STOP and len(w) > 2]
    return " ".join(kept[:8]) or question


def keywords_ai(question: str) -> str:
    """Ask the small model for search terms; fall back to the simple version if it's slow or down."""
    cfg = config.load()["ai"]
    # Few words work best: Kiwix's search wants every word, so long lists find loosely related pages.
    body = {"model": cfg["fast_model"], "stream": False, "think": False, "keep_alive": "30m",
            "options": {"num_predict": 12, "temperature": 0},
            "prompt": ("Give the 2 or 3 most important words to look up in an encyclopedia to answer this question. "
                       "Reply with only those words.\nQuestion: " + question + "\nWords:")}
    try:
        req = urllib.request.Request(cfg["ollama"].rstrip("/") + "/api/generate", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=cfg.get("keyword_timeout", 15)) as r:
            text = json.load(r).get("response", "")
    except (OSError, ValueError):
        return keywords_simple(question)
    text = re.sub(r"[^\w\s'-]", " ", text.split("\n")[0])
    text = " ".join(text.split()[:5])
    return text or keywords_simple(question)


def best_passage(text: str, terms: list[str], size: int = 1200) -> str:
    """The window of the article with the most search terms in it."""
    if len(text) <= size:
        return text
    low = text.lower()
    best, best_score = 0, -1
    for start in range(0, len(text) - size + 1, size // 4):
        window = low[start:start + size]
        score = sum(window.count(t) for t in terms)
        if score > best_score:
            best, best_score = start, score
    return text[best:best + size]


def context(question: str, max_articles: int = 3) -> dict:
    cfg = config.load()
    base = cfg["kiwix"]["search_url"]
    public = cfg["kiwix"]["public_url"]
    terms = keywords_ai(question)
    simple = keywords_simple(question)

    def search(b):
        # The model's words and the question's own words find different good pages; take both, alternating.
        a = kiwix.search_local(b, terms, count=6)
        s = kiwix.search_local(b, simple, count=6) if simple != terms else []
        return [h for pair in zip_longest(a, s) for h in pair if h]

    hits = search(base)
    if not hits:  # full library down (USB drive missing)? the essentials still answer
        base, public = cfg["kiwix"]["core_search_url"], cfg["kiwix"]["core_public_url"]
        hits = search(base)
    seen, picked = set(), []
    for h in hits:
        key = h["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        picked.append(h)
        if len(picked) == max_articles:
            break
    tl = [t for t in (terms + " " + simple).lower().split() if len(t) > 2]
    sources, parts = [], []
    for n, h in enumerate(picked, 1):
        text = kiwix.article_text(base, h["link"], limit=20000)
        passage = best_passage(text, tl) if text else h["snippet"]
        url = public.rstrip("/") + h["link"]
        sources.append({"n": n, "title": h["title"], "book": h["book"], "url": url})
        parts.append(f"[{n}] {h['title']} ({h['book']})\n{passage}")
    return {"query": terms if terms == simple else f"{terms} / {simple}", "sources": sources,
            "context": "\n\n".join(parts)}
