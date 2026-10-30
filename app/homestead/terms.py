"""Search words: the key words of a question, and other words for the same thing.

synonyms.txt lists words that mean the same thing ("green beans, snap beans, string beans").
A search for any of them finds all of them, in the documents, the lessons and the
encyclopedias alike.
"""
import re
from functools import lru_cache
from pathlib import Path

STOP = set("""a an and are as at be but by can do does for from how i if in into is it its me my of on or
should so than that the their them then there these they this to was what when where which who why will
with would you your about after before during without we our us have has had get got make made need
long much many best way use using tell know want""".split())


def words(q: str) -> list[str]:
    """The words that matter: "how to splint a broken arm" -> splint, broken, arm."""
    return [w for w in re.findall(r"[\w'-]+", q.lower()) if w not in STOP and len(w) > 1]


def _plain(q: str) -> list[str]:
    return [w for w in re.findall(r"\w+", q.lower()) if w not in STOP]


@lru_cache(maxsize=1)
def groups() -> dict[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """{phrase: every phrase in its group}, phrases as word tuples."""
    out: dict = {}
    for line in (Path(__file__).with_name("synonyms.txt").read_text().splitlines()):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        group = tuple(dict.fromkeys(tuple(_plain(p)) for p in line.split(",") if _plain(p)))
        for p in group:
            out[p] = tuple(dict.fromkeys(out.get(p, ()) + group))
    return out


def expand(q: str) -> list[tuple[tuple[str, ...], ...]]:
    """The question as a list of terms, each term its alternatives (phrases as word tuples),
    the words as typed first.

    "canning snap beans" -> [(canning,), (bottling,)), ((snap beans), (green beans), (string beans))]
    """
    ws, g = _plain(q), groups()
    longest = max((len(p) for p in g), default=1)
    out, i = [], 0
    while i < len(ws):
        for n in range(min(longest, len(ws) - i), 0, -1):
            typed = tuple(ws[i:i + n])
            alts = g.get(typed)
            if alts:
                out.append((typed,) + tuple(a for a in alts if a != typed))
                i += n
                break
        else:
            out.append(((ws[i],),))
            i += 1
    return out


def every_word(q: str) -> list[str]:
    """All the words a match could show, synonyms included (for highlighting)."""
    return list(dict.fromkeys(w for alts in expand(q) for p in alts for w in p))


def fts(q: str, any_word: bool = False) -> str:
    """A SQLite FTS5 query: every term (or any, with any_word), each one as any of its synonyms.
    The last word also matches as the start of a word, for words still being typed."""
    terms = expand(q)
    parts = []
    for n, alts in enumerate(terms):
        last = n == len(terms) - 1 and len(alts) == 1 and len(alts[0]) == 1
        ps = [f'"{" ".join(p)}"' + ("*" if last else "") for p in alts]
        parts.append(ps[0] if len(ps) == 1 else "(" + " OR ".join(ps) + ")")
    return (" OR " if any_word else " ").join(parts)


def variants(q: str, most: int = 3) -> list[str]:
    """The question as typed, then with other words for the same thing, for searches that
    take only plain words (the encyclopedias' own search treats "OR" as just another word).

    "canning snap beans" -> ["canning snap beans", "bottling snap beans", "canning green beans"]
    """
    terms = expand(q)
    out = [q]
    for j in range(1, max((len(a) for a in terms), default=1)):     # each term's next other word in turn
        for n, alts in enumerate(terms):
            if j < len(alts) and len(out) < most:
                out.append(" ".join(" ".join(alts[j] if i == n else a[0]) for i, a in enumerate(terms)))
    return out
