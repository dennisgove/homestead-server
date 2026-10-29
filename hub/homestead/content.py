"""What's in the library, by topic, for the website: documents on disk (single
files and split books), the Kiwix libraries (with their real titles and
summaries from kiwix-serve), and courses. Only what's actually on disk is listed.
"""
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from . import catalog, config, kiwix

READABLE = (".pdf", ".txt", ".md", ".html", ".htm", ".epub", ".jpg", ".jpeg", ".png")
_kiwix_cache: dict[str, tuple[float, dict]] = {}


def kiwix_books(base: str) -> dict[str, dict]:
    """Books on a kiwix-serve by file stem: title, summary, content link, icon. Cached 5 minutes."""
    hit = _kiwix_cache.get(base)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    books = {}
    try:
        root = ET.fromstring(kiwix._get(f"{base.rstrip('/')}/catalog/v2/entries?count=-1", timeout=10))
    except (OSError, ET.ParseError):
        return hit[1] if hit else {}
    for e in root.findall("a:entry", kiwix.NS):
        def t(tag):
            return (e.findtext(f"a:{tag}", "", kiwix.NS) or "").strip()
        link = next((l.get("href") for l in e.findall("a:link", kiwix.NS) if l.get("type") == "text/html"), "")
        icon = next((l.get("href") for l in e.findall("a:link", kiwix.NS)
                     if "thumbnail" in (l.get("rel") or "")), "")
        stem = link.rsplit("/", 1)[-1]
        name = t("name") + (f"_{t('flavour')}" if t("flavour") else "")
        books[stem] = {"title": t("title"), "summary": t("summary"), "link": link, "icon": icon,
                       "name": name, "articles": int(t("articleCount") or 0)}
    _kiwix_cache[base] = (time.time(), books)
    return books


def libraries(category: str | None = None) -> list[dict]:
    """The ZIM libraries on disk, by topic: [{id, title, summary, category, url, icon, essential, stem}]."""
    cfg = config.load()["kiwix"]
    full = kiwix_books(cfg["search_url"])
    core = kiwix_books(cfg["core_search_url"])
    out = []
    for it in catalog.items():
        if it["type"] != "zim" or (category and it["category"] != category):
            continue
        files = catalog.zim_files(it["name"])
        if not files:
            continue
        stem = files[0].stem
        # The full library serves both disks; if the USB drive is missing, the essentials server still works.
        if stem in full:
            b, public = full[stem], cfg["public_url"]
        elif stem in core:
            b, public = core[stem], cfg["core_public_url"]
        else:
            continue
        out.append({"id": it["id"], "title": b["title"] or it.get("title") or it["name"], "summary": b["summary"],
                    "category": it["category"], "url": public.rstrip("/") + b["link"],
                    "icon": (public.rstrip("/") + b["icon"]) if b["icon"] else "", "stem": stem,
                    "articles": b["articles"], "essential": it.get("disk") == "core"})
    out.sort(key=lambda b: (not b["essential"], b["title"].lower()))
    return out


def doc_url(rel: str) -> str:
    """Where a document opens: PDFs and pictures straight from disk, ebooks in the Hub's reader."""
    q = urllib.parse.quote(rel)
    return f"/read?path={q}" if rel.lower().endswith(".epub") else f"/docs/{q}"


def documents(category: str | None = None) -> list[dict]:
    """Documents on disk, by topic. A folder of parts (a split book) is one entry with its parts.

    [{title, category, url, size, parts: [{title, url}] | None, binder, essential}]
    """
    docs = config.path("docs")
    if not docs.is_dir():
        return []
    titles = catalog.doc_titles()
    books = {(i["category"], i["folder"]): i for i in catalog.items() if i["type"] == "docpage"}
    singles = {(i["category"], i["file"]): i for i in catalog.items() if i["type"] == "doc" and i.get("file")}
    out = []
    for cat_dir in sorted(p for p in docs.iterdir() if p.is_dir() and not p.name.startswith(".")):
        cat = cat_dir.name
        if category and cat != category:
            continue
        for p in sorted(cat_dir.iterdir()):
            if p.name.startswith(".") or p.name == ".homestead-partial":
                continue
            if p.is_dir():
                parts = [f for f in sorted(p.rglob("*")) if f.is_file() and not f.name.startswith(".")
                         and f.suffix.lower() in READABLE]
                if not parts:
                    continue
                it = books.get((cat, p.name), {})
                title = it.get("title") or ((p / ".title").read_text().strip() if (p / ".title").exists()
                                            else p.name.replace("-", " ").capitalize())
                plist = []
                for f in parts:
                    t = catalog.doc_title(f, titles)
                    # "Book - Ch 01 Title" -> "Ch 01 Title" inside the book's own list
                    short = t.split(" - ", 1)[1] if " - " in t else t.split(": ", 1)[-1]
                    plist.append({"title": short, "url": doc_url(str(f.relative_to(docs)))})
                out.append({"title": title, "category": cat, "url": plist[0]["url"], "parts": plist,
                            "size": sum(f.stat().st_size for f in parts), "binder": it.get("binder", False),
                            "essential": True})
            elif p.is_file() and p.suffix.lower() in READABLE:
                it = singles.get((cat, p.name), {})
                out.append({"title": catalog.doc_title(p, titles), "category": cat,
                            "url": doc_url(str(p.relative_to(docs))), "parts": None, "size": p.stat().st_size,
                            "binder": it.get("binder", False), "essential": True})
    out.sort(key=lambda d: d["title"].lower())
    return out


def courses() -> list[dict]:
    return [i for i in catalog.items() if i["type"] == "kolibri"]


def topics() -> list[dict]:
    """Every topic with how much is in it, in the catalog's order."""
    cats = catalog.merged().get("categories", {})
    docs, libs = documents(), libraries()
    out = []
    for key, name in cats.items():
        nd = sum(1 for d in docs if d["category"] == key)
        nl = sum(1 for b in libs if b["category"] == key)
        if nd or nl or key == "personal":
            out.append({"key": key, "name": name, "docs": nd, "libraries": nl})
    return out


def doc_path(rel: str) -> Path | None:
    """A document's file from a docs-relative path, refusing anything outside docs/."""
    docs = config.path("docs").resolve()
    p = (docs / rel).resolve()
    return p if p.is_file() and docs in p.parents else None
