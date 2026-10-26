"""Kiwix: the online catalog (to find and download ZIMs) and the local server (to search them)."""
import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

OPDS = "https://opds.library.kiwix.org/catalog/v2/entries"
UA = {"User-Agent": "homestead-hub/1.0 (offline preparedness library)"}
NS = {"a": "http://www.w3.org/2005/Atom", "os": "http://a9.com/-/spec/opensearch/1.1/"}
DATE = re.compile(r"_(\d{4}-\d{2}[a-z]?)\.zim")


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _entry(e: ET.Element) -> dict:
    def t(tag):
        x = e.find(f"a:{tag}", NS)
        return (x.text or "").strip() if x is not None else ""
    acq = next((l for l in e.findall("a:link", NS) if "acquisition" in (l.get("rel") or "")), None)
    url = acq.get("href") if acq is not None else ""
    tags = t("tags").split(";") if t("tags") else []
    m = DATE.search(url)
    return {
        "name": t("name"), "title": t("title"), "summary": t("summary"), "language": t("language"),
        "category": t("category"), "flavour": t("flavour"), "tags": [x for x in tags if not x.startswith("_")],
        "searchable": "_ftindex:no" not in tags,
        "articles": int(t("articleCount") or 0), "media": int(t("mediaCount") or 0),
        "size": int(acq.get("length") or 0) if acq is not None else 0,
        "url": url, "release": m.group(1) if m else "", "updated": t("updated")[:10],
    }


def search_catalog(q: str = "", lang: str = "eng", category: str = "", count: int = 30, start: int = 0) -> tuple[int, list[dict]]:
    """Search library.kiwix.org. Returns (total, entries)."""
    params = {"count": count, "start": start}
    if q:
        params["q"] = q
    if lang:
        params["lang"] = lang
    if category:
        params["category"] = category
    root = ET.fromstring(_get(f"{OPDS}?{urllib.parse.urlencode(params)}"))
    total = int((root.findtext("a:totalResults", "0", NS) or "0").replace(",", ""))
    return total, [_entry(e) for e in root.findall("a:entry", NS)]


def latest(name: str) -> dict | None:
    """The newest release of a ZIM by name, or None."""
    root = ET.fromstring(_get(f"{OPDS}?{urllib.parse.urlencode({'name': name, 'count': 5})}"))
    entries = [_entry(e) for e in root.findall("a:entry", NS)]
    entries = [e for e in entries if e["name"] == name and e["url"]]
    return max(entries, key=lambda e: e["release"]) if entries else None


# --- the local kiwix-serve ------------------------------------------------------

def _text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def search_local(base: str, pattern: str, count: int = 5, lang: str = "eng") -> list[dict]:
    """Full-text search across every book on a kiwix-serve. Each hit: title, book, link, snippet."""
    q = urllib.parse.urlencode({"pattern": pattern, "format": "xml", "pageLength": count, "books.filter.lang": lang})
    try:
        root = ET.fromstring(_get(f"{base.rstrip('/')}/search?{q}", timeout=20))
    except (OSError, ET.ParseError):
        return []
    hits = []
    for it in root.iter("item"):
        hits.append({
            "title": _text(it.findtext("title")), "book": _text(it.findtext("book/title")),
            "link": it.findtext("link") or "", "snippet": _text(it.findtext("description")),
        })
    return hits


def article_text(base: str, link: str, limit: int = 4000) -> str:
    """Plain text of an article (scripts, styles and navigation dropped)."""
    try:
        raw = _get(base.rstrip("/") + link, timeout=20).decode("utf-8", "replace")
    except OSError:
        return ""
    raw = re.sub(r"(?is)<(script|style|nav|header|footer|table)[^>]*>.*?</\1>", " ", raw)
    return _text(raw)[:limit]
