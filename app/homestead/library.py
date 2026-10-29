"""What the library holds: the list (library.yaml) plus the changes made on this
server (changes.yaml), and where each item's files are on disk.

Kinds of item:
    zim     an encyclopedia/website in one ZIM file        id = its Kiwix name
    pdf     one document         epub   one ebook          id = from its title
    book    one PDF per chapter, from a web page           id = from its title
    course  a course channel (lessons and videos)          id = the channel id
"""
import copy
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import settings

KINDS = ("zim", "pdf", "epub", "book", "course")
ZIM_FILE = re.compile(r"^(?P<name>.+)_(?P<date>\d{4}-\d{2})(?P<rev>[a-z]?)\.zim$")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:70].strip("-") or "item"


@dataclass
class Item:
    kind: str
    source: str               # zim name, URL, or channel id
    topic: str
    title: str = ""
    essential: bool = False   # on the internal disk
    print: bool = False       # in the printed binder
    priority: int = 1
    match: str = ""           # book: which linked PDFs belong to it
    added: bool = False       # added on this server, not in library.yaml
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        if self.kind in ("zim", "course"):
            return self.source
        return slug(self.title or self.source.rsplit("/", 1)[-1])

    @property
    def disk_essential(self) -> bool:
        # documents are small: always on the internal disk
        return self.essential or self.kind in ("pdf", "epub", "book")

    # --- on disk ---------------------------------------------------------------------
    def doc_path(self) -> Path:
        ext = "epub" if self.kind == "epub" else "pdf"
        return settings.path("docs") / self.topic / f"{self.id}.{ext}"

    def book_dir(self) -> Path:
        return settings.path("docs") / self.topic / self.id

    def zim_files(self) -> list[Path]:
        """Finished releases on either disk, newest first (the essentials copy first on a tie)."""
        found = []
        for essential in (True, False):
            d = settings.zim_dir(essential)
            if not d.is_dir():
                continue
            for f in d.glob(f"{glob_escape(self.source)}_*.zim"):
                m = ZIM_FILE.match(f.name)
                if m and m["name"] == self.source:
                    found.append((m["date"] + m["rev"], essential, f))
        found.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [f for _, _, f in found]

    def files(self) -> list[Path]:
        if self.kind == "zim":
            return self.zim_files()
        if self.kind in ("pdf", "epub"):
            p = self.doc_path()
            return [p] if p.is_file() else []
        if self.kind == "book":
            d = self.book_dir()
            return sorted(p for p in d.iterdir() if p.is_file() and not p.name.startswith(".")) if d.is_dir() else []
        if self.kind == "course":
            db = settings.path("courses") / "databases" / f"{self.source}.sqlite3"
            return [db] if db.is_file() else []
        return []

    def on_disk(self) -> bool:
        return bool(self.files())

    def as_dict(self) -> dict:
        d = {self.kind: self.source, "topic": self.topic}
        for k in ("title", "match"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.essential:
            d["essential"] = True
        if self.print:
            d["print"] = True
        if self.priority != 1:
            d["priority"] = self.priority
        return d


def glob_escape(s: str) -> str:
    return re.sub(r"([*?\[])", r"[\1]", s)


# --- loading -----------------------------------------------------------------------------

_cache: dict = {}


def _read(path: Path) -> dict:
    """Parsed YAML, re-read only when the file changes."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return {}
    key = (st.st_mtime_ns, st.st_size)
    hit = _cache.get(str(path))
    if not hit or hit[0] != key:
        with open(path) as f:
            hit = _cache[str(path)] = (key, yaml.safe_load(f) or {})
    return copy.deepcopy(hit[1])


def _item(raw: dict, topic: str, added: bool = False) -> Item:
    kind = next((k for k in KINDS if k in raw), None)
    if kind is None:
        raise ValueError(f"item without a kind ({', '.join(KINDS)}): {raw}")
    known = {"title", "essential", "print", "priority", "match", "topic", kind}
    return Item(kind=kind, source=str(raw[kind]), topic=raw.get("topic", topic), title=raw.get("title", ""),
                essential=bool(raw.get("essential")), print=bool(raw.get("print")),
                priority=int(raw.get("priority", 1)), match=raw.get("match", ""), added=added,
                extra={k: v for k, v in raw.items() if k not in known})


def raw_list() -> dict:
    return _read(settings.path("list"))


def changes() -> dict:
    c = _read(settings.path("changes"))
    c.setdefault("added", [])
    c.setdefault("removed", [])
    return c


def save_changes(c: dict):
    p = settings.path("changes")
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".changes.")
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(c, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, p)


def topics() -> dict[str, dict]:
    """{topic id: {name, icon, blurb, quick}} in the list's order."""
    return {tid: {k: v for k, v in t.items() if k != "items"} | {"id": tid}
            for tid, t in (raw_list().get("topics") or {}).items()}


def items(include_removed: bool = False) -> list[Item]:
    lst, ch = raw_list(), changes()
    out = []
    for tid, t in (lst.get("topics") or {}).items():
        for raw in t.get("items") or []:
            out.append(_item(raw, tid))
    for raw in ch["added"]:
        out.append(_item(raw, raw.get("topic", "family"), added=True))
    removed = set(ch["removed"])
    seen, uniq = set(), []
    for it in out:
        if it.id in seen or (it.id in removed and not include_removed):
            continue
        seen.add(it.id)
        uniq.append(it)
    return uniq


def get(item_id: str) -> Item | None:
    return next((i for i in items(include_removed=True) if i.id == item_id), None)


def add(raw: dict) -> Item:
    it = _item(raw, raw.get("topic", "family"), added=True)
    if it.topic not in topics():
        raise ValueError(f"no topic {it.topic!r}")
    c = changes()
    if it.id in c["removed"]:
        c["removed"].remove(it.id)
    elif get(it.id):
        raise ValueError(f"{it.id} is already in the library")
    else:
        c["added"].append(it.as_dict())
    save_changes(c)
    return it


def remove(item_id: str):
    c = changes()
    before = len(c["added"])
    c["added"] = [a for a in c["added"] if _item(a, a.get("topic", "family")).id != item_id]
    if len(c["added"]) == before and item_id not in c["removed"]:
        c["removed"].append(item_id)
    save_changes(c)


def by_hand() -> list[dict]:
    return raw_list().get("by_hand") or []


def phone_apps() -> list[dict]:
    return raw_list().get("phone_apps") or []
