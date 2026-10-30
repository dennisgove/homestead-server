"""Course channels (Khan Academy and the like, in Kolibri's channel format), read directly:
the channel's own database for the lessons, and its files for the videos.

    courses/databases/<channel>.sqlite3     the lesson tree
    courses/storage/<a>/<b>/<file id>.<ext>  videos, subtitles, pictures

Videos play in the website. Practice exercises need Khan Academy's own exercise
engine, so they aren't shown.
"""
import html
import sqlite3
from dataclasses import dataclass

from . import documents, library, settings

SHOWN = ("topic", "video", "audio", "document")


@dataclass
class Channel:
    id: str
    title: str
    description: str
    topic: str


def _db(channel: str) -> sqlite3.Connection | None:
    p = settings.path("courses") / "databases" / f"{channel}.sqlite3"
    if not p.is_file():
        return None
    con = sqlite3.connect(f"file:{p}?immutable=1", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def channels(topic: str | None = None) -> list[Channel]:
    out = []
    for it in library.items():
        if it.kind != "course" or (topic and it.topic != topic):
            continue
        con = _db(it.source)
        if con is None:
            continue
        try:
            row = con.execute("SELECT name, description FROM content_channelmetadata WHERE id = ?", (it.source,)).fetchone()
        finally:
            con.close()
        out.append(Channel(it.source, it.title or (row["name"] if row else it.source),
                           (row["description"] if row else "") or "", it.topic))
    return out


def file_url(file_id: str, ext: str) -> str:
    return f"/files/courses/storage/{file_id[0]}/{file_id[1]}/{file_id}.{ext}"


def file_on_disk(file_id: str, ext: str) -> bool:
    return (settings.path("courses") / "storage" / file_id[0] / file_id[1] / f"{file_id}.{ext}").is_file()


def _counts() -> dict[str, int]:
    """Videos under each topic (built by the indexer; empty until it has run)."""
    con = documents.connect()
    if con is None:
        return {}
    try:
        return dict(con.execute("SELECT node, videos FROM course_counts"))
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def node(channel: str, node_id: str | None = None) -> dict | None:
    """A topic (its children) or a lesson (its video and neighbours).

    {id, kind, title, description, path: [{id, title}], children: [...], files: {...}, prev, next}
    """
    con = _db(channel)
    if con is None:
        return None
    try:
        nid = node_id or channel
        row = con.execute("SELECT * FROM content_contentnode WHERE id = ?", (nid,)).fetchone()
        if row is None:
            row = con.execute("SELECT * FROM content_contentnode WHERE parent_id IS NULL").fetchone()
        if row is None:
            return None
        crumbs, p = [], row["parent_id"]
        while p:
            r = con.execute("SELECT id, title, parent_id FROM content_contentnode WHERE id = ?", (p,)).fetchone()
            if r is None:
                break
            crumbs.insert(0, {"id": r["id"], "title": r["title"]})
            p = r["parent_id"]
        out = {"id": row["id"], "kind": row["kind"], "title": row["title"],
               "description": row["description"] or "", "path": crumbs, "channel": channel}
        if row["kind"] == "topic":
            counts = _counts()
            kids = []
            for k in con.execute("SELECT id, kind, title, description, duration FROM content_contentnode "
                                 "WHERE parent_id = ? AND available = 1 ORDER BY sort_order", (row["id"],)):
                if k["kind"] not in SHOWN:
                    continue
                n = counts.get(k["id"], None) if k["kind"] == "topic" else None
                if k["kind"] == "topic" and n == 0:
                    continue   # only exercises inside
                kids.append({"id": k["id"], "kind": k["kind"], "title": k["title"], "videos": n,
                             "duration": k["duration"], "description": (k["description"] or "")[:200]})
            out["children"] = kids
        else:
            files = {"video": None, "subtitles": [], "thumbnail": None, "document": None, "audio": None}
            for f in con.execute("SELECT f.preset, f.lang_id, l.id, l.extension FROM content_file f "
                                 "JOIN content_localfile l ON l.id = f.local_file_id WHERE f.contentnode_id = ? "
                                 "ORDER BY f.priority", (row["id"],)):
                if not file_on_disk(f["id"], f["extension"]):
                    continue
                url = file_url(f["id"], f["extension"])
                if f["preset"] in ("high_res_video", "low_res_video") and (files["video"] is None or f["preset"] == "high_res_video"):
                    files["video"] = url
                elif f["preset"] == "video_subtitle":
                    files["subtitles"].append({"lang": f["lang_id"] or "en", "url": url})
                elif f["preset"].endswith("thumbnail"):
                    files["thumbnail"] = url
                elif f["preset"] == "document":
                    files["document"] = url
                elif f["preset"] == "audio":
                    files["audio"] = url
            files["subtitles"].sort(key=lambda s: (not s["lang"].startswith("en"), s["lang"]))
            out["files"] = files
            sib = [r["id"] for r in con.execute(
                "SELECT id FROM content_contentnode WHERE parent_id = ? AND kind IN ('video','audio','document') "
                "AND available = 1 ORDER BY sort_order", (row["parent_id"],))]
            i = sib.index(row["id"]) if row["id"] in sib else -1
            titles = {r["id"]: r["title"] for r in con.execute(
                f"SELECT id, title FROM content_contentnode WHERE id IN ({','.join('?' * len(sib))})", sib)} if sib else {}
            out["prev"] = {"id": sib[i - 1], "title": titles[sib[i - 1]]} if i > 0 else None
            out["next"] = {"id": sib[i + 1], "title": titles[sib[i + 1]]} if 0 <= i < len(sib) - 1 else None
        return out
    finally:
        con.close()


# --- index (for search and the topic counts) -------------------------------------------------

COURSE_SCHEMA = """
CREATE TABLE IF NOT EXISTS course_counts (node TEXT PRIMARY KEY, videos INTEGER);
CREATE TABLE IF NOT EXISTS course_channels (channel TEXT PRIMARY KEY, mtime INTEGER);
CREATE VIRTUAL TABLE IF NOT EXISTS lessons USING fts5(
    title, description, place, channel UNINDEXED, node UNINDEXED, kind UNINDEXED,
    tokenize = 'porter unicode61 remove_diacritics 2');
"""


def build(log=print) -> dict:
    """Index each channel's lessons (titles, descriptions, where they sit) once per channel version."""
    con = documents.connect(readonly=False)
    con.executescript(COURSE_SCHEMA)
    known = dict(con.execute("SELECT channel, mtime FROM course_channels"))
    done = 0
    for ch in channels():
        p = settings.path("courses") / "databases" / f"{ch.id}.sqlite3"
        mtime = int(p.stat().st_mtime)
        if known.get(ch.id) == mtime:
            continue
        src = _db(ch.id)
        rows = src.execute("SELECT id, parent_id, kind, title, description, available FROM content_contentnode").fetchall()
        src.close()
        by_id = {r["id"]: r for r in rows}
        counts: dict[str, int] = {}
        for r in rows:
            if r["kind"] == "video" and r["available"]:
                p_id = r["parent_id"]
                while p_id:
                    counts[p_id] = counts.get(p_id, 0) + 1
                    p_id = by_id[p_id]["parent_id"] if p_id in by_id else None
        con.execute("DELETE FROM lessons WHERE channel = ?", (ch.id,))
        con.executemany("INSERT OR REPLACE INTO course_counts VALUES (?, ?)",
                        [(r["id"], counts.get(r["id"], 0)) for r in rows if r["kind"] == "topic"])

        def place(r):
            names, p_id = [], r["parent_id"]
            while p_id and p_id in by_id and by_id[p_id]["parent_id"]:
                names.insert(0, by_id[p_id]["title"])
                p_id = by_id[p_id]["parent_id"]
            return " › ".join(names[-3:])
        con.executemany("INSERT INTO lessons VALUES (?, ?, ?, ?, ?, ?)",
                        [(r["title"], r["description"] or "", place(r), ch.id, r["id"], r["kind"]) for r in rows
                         if r["available"] and (r["kind"] == "video" or (r["kind"] == "topic" and counts.get(r["id"])))])
        con.execute("INSERT OR REPLACE INTO course_channels VALUES (?, ?)", (ch.id, mtime))
        con.commit()
        done += 1
        log(f"indexed course {ch.title}: {sum(1 for r in rows if r['kind'] == 'video')} videos")
    con.close()
    return {"channels": done}


def search(q: str, limit: int = 12) -> list[dict]:
    m = documents.match_query(q)
    con = documents.connect()
    if not m or con is None:
        return []
    try:
        rows = con.execute("SELECT title, place, channel, node, kind, snippet(lessons, 1, char(2), char(3), ' … ', 20) "
                           "FROM lessons WHERE lessons MATCH ? ORDER BY bm25(lessons, 6.0, 1.0, 2.0) LIMIT ?",
                           (m, limit)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return [{"title": t, "place": p, "url": f"/learn/{c}/{n}", "kind": k, "node": n, "snippet": documents._mark(s)}
            for t, p, c, n, k, s in rows]


def lessons_by_node(nodes: list[str]) -> dict[str, dict]:
    """{node: lesson} for lessons found some other way (meaning search), with the start of their description."""
    con = documents.connect()
    if con is None or not nodes:
        return {}
    try:
        rows = con.execute("SELECT title, place, channel, node, kind, description FROM lessons WHERE node IN "
                           f"({','.join('?' * len(nodes))})", nodes).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        con.close()
    out = {}
    for t, p, c, n, k, d in rows:
        d = d or ""
        out[n] = {"title": t, "place": p, "url": f"/learn/{c}/{n}", "kind": k, "node": n,
                  "snippet": html.escape(d[:200] + ("…" if len(d) > 200 else ""))}
    return out
