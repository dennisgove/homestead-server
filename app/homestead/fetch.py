"""Downloading and updating the library (needs internet).

For every item in the library list, in priority order:
    zim     the newest release from Kiwix's catalog; checksum-verified (metalink);
            the older release is deleted once the new one is in place
    pdf/epub  the file, if it isn't here yet
    book    every chapter PDF linked from the page that isn't here yet
    course  the channel's lesson database, then any of its files that are missing
Downloads go to a .partial folder first and resume after interruptions. Anything that
won't fit (keeping 5% of the disk free) is skipped and reported. Afterwards the search
index is updated.
"""
import html
import os
import re
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

from . import courses, documents, jobs, library, settings

UA = {"User-Agent": "homestead/1.0 (offline preparedness library)"}
OPDS = "https://opds.library.kiwix.org/catalog/v2/entries"
NS = {"a": "http://www.w3.org/2005/Atom"}
STUDIO = "https://studio.learningequality.org/content"
MARGIN = 0.05


def _get(url: str, timeout: int = 60) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def safe_url(u: str) -> str:
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit(p._replace(path=urllib.parse.quote(urllib.parse.unquote(p.path))))


# --- Kiwix's catalog -----------------------------------------------------------------------

def _entries(params: dict) -> list[dict]:
    root = ET.fromstring(_get(f"{OPDS}?{urllib.parse.urlencode(params)}"))
    out = []
    for e in root.findall("a:entry", NS):
        t = lambda tag: (e.findtext(f"a:{tag}", "", NS) or "").strip()
        acq = next((l for l in e.findall("a:link", NS) if "acquisition" in (l.get("rel") or "")), None)
        if acq is None:
            continue
        url = acq.get("href")
        m = re.search(r"/([^/]+?)_(\d{4}-\d{2}[a-z]?)\.zim", url)
        if not m:
            continue
        out.append({"name": m.group(1), "release": m.group(2), "url": url, "size": int(acq.get("length") or 0),
                    "title": t("title"), "summary": t("summary"), "language": t("language")})
    return out


def latest(name: str) -> dict | None:
    """The newest release of a ZIM by its full name (with flavour, e.g. mdwiki_en_all_maxi)."""
    found = _entries({"name": name, "count": 10})
    if not any(e["name"] == name for e in found) and "_" in name:
        base, flavour = name.rsplit("_", 1)
        found = _entries({"name": base, "count": 20})
    found = [e for e in found if e["name"] == name]
    return max(found, key=lambda e: e["release"]) if found else None


def find(q: str, count: int = 30) -> list[dict]:
    """Search Kiwix's catalog (for adding things)."""
    return _entries({"q": q, "count": count, "lang": "eng"})


# --- downloading ---------------------------------------------------------------------------

def download(url: str, dest: Path, essential: bool, job: jobs.Job, label: str, metalink: bool = False) -> bool:
    """Into the partial folder, resuming; moved into place only when complete."""
    part = settings.partial_dir(essential)
    part.mkdir(parents=True, exist_ok=True)
    tmp = part / dest.name
    job.step(f"downloading {label}")
    if shutil.which("aria2c"):
        cmd = ["aria2c", "--continue=true", "--max-tries=10", "--retry-wait=30", "--summary-interval=60",
               "--console-log-level=warn", "--file-allocation=none", "--allow-overwrite=true",
               f"--user-agent={UA['User-Agent']}", "-d", str(part), "-o", tmp.name]
        if metalink:
            cmd += ["--follow-metalink=mem", "--check-integrity=true", url + ".meta4"]
        else:
            cmd += ["-x", "4", safe_url(url)]
        ok = subprocess.run(cmd).returncode == 0 and tmp.exists() and not tmp.with_name(tmp.name + ".aria2").exists()
    else:
        ok = _plain_download(safe_url(url), tmp)
    if not ok:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp, dest)
    os.chmod(dest, 0o644)
    return True


def _plain_download(url: str, tmp: Path) -> bool:
    have = tmp.stat().st_size if tmp.exists() else 0
    headers = dict(UA, Range=f"bytes={have}-") if have else UA
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r, \
                open(tmp, "ab" if have and r.status == 206 else "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        return True
    except (OSError, urllib.error.URLError):
        return False


def room(essential: bool, size: int) -> bool:
    d = settings.path("core" if essential else "library")
    total = shutil.disk_usage(d).total
    return jobs.free(d) - size > total * MARGIN


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if ".pdf" in href.lower():
                self.links.append(html.unescape(href))


def book_links(it: library.Item) -> list[str]:
    p = Links()
    p.feed(_get(it.source).decode("utf-8", "replace"))
    links = sorted({urllib.parse.urljoin(it.source, h) for h in p.links})
    return [u for u in links if not it.match or re.search(it.match, u)]


# --- per kind ----------------------------------------------------------------------------------

def fetch_zim(it: library.Item, job: jobs.Job):
    have = it.zim_files()
    try:
        new = latest(it.source)
    except (OSError, ET.ParseError) as e:
        job.item(it.id, state="offline" if have else "error", note=f"catalog not reachable: {e}")
        return
    if new is None:
        job.item(it.id, state="here" if have else "not found", note="not in Kiwix's catalog")
        return
    current = library.ZIM_FILE.match(have[0].name)["date"] + (library.ZIM_FILE.match(have[0].name)["rev"] or "") if have else ""
    if current >= new["release"]:
        job.item(it.id, state="here", release=current, size=new["size"])
        return
    if not it.disk_essential and not settings.library_drive_ok():
        job.item(it.id, state="waiting", note="the USB library drive isn't plugged in")
        return
    if not room(it.disk_essential, new["size"]):
        job.item(it.id, state="no room", size=new["size"], note=f"needs {jobs.human(new['size'])}")
        return
    dest = settings.zim_dir(it.disk_essential) / f"{new['name']}_{new['release']}.zim"
    if download(new["url"], dest, it.disk_essential, job, f"{it.title or it.id} ({jobs.human(new['size'])})", metalink=True):
        for old in have:       # the new release is in place: the old one goes
            old.unlink(missing_ok=True)
        job.item(it.id, state="here", release=new["release"], size=new["size"], note="updated" if have else "downloaded")
    else:
        job.item(it.id, state="failed", note="download failed; it resumes next time")


def fetch_doc(it: library.Item, job: jobs.Job):
    dest = it.doc_path()
    if dest.is_file():
        job.item(it.id, state="here")
        return
    if download(it.source, dest, True, job, it.title or it.id):
        magic = dest.read_bytes()[:4]
        if magic not in (b"%PDF", b"PK\x03\x04"):
            dest.unlink()
            job.item(it.id, state="failed", note="the link didn't give a PDF/ebook (page moved?)")
            return
        job.item(it.id, state="here", note="downloaded")
    else:
        job.item(it.id, state="failed", note="download failed")


def fetch_book(it: library.Item, job: jobs.Job):
    try:
        links = book_links(it)
    except OSError as e:
        job.item(it.id, state="offline" if it.on_disk() else "error", note=f"page not reachable: {e}")
        return
    d = it.book_dir()
    missing = [u for u in links if not (d / os.path.basename(urllib.parse.unquote(urllib.parse.urlsplit(u).path))).exists()]
    failed = 0
    for n, u in enumerate(missing, 1):
        name = os.path.basename(urllib.parse.unquote(urllib.parse.urlsplit(u).path))
        if not download(u, d / name, True, job, f"{it.title} ({n}/{len(missing)})"):
            failed += 1
    job.item(it.id, state="failed" if failed else "here", parts=len(links),
             note=f"{failed} chapters failed" if failed else (f"{len(missing)} chapters downloaded" if missing else ""))


def fetch_course(it: library.Item, job: jobs.Job):
    if not settings.library_drive_ok():
        job.item(it.id, state="waiting", note="the USB library drive isn't plugged in")
        return
    root = settings.path("courses")
    db = root / "databases" / f"{it.source}.sqlite3"
    if not db.exists() and not download(f"{STUDIO}/databases/{it.source}.sqlite3", db, False, job, f"{it.title} lessons"):
        job.item(it.id, state="failed", note="couldn't get the lesson list")
        return
    con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    files = con.execute("SELECT DISTINCT l.id, l.extension, l.file_size FROM content_localfile l "
                        "JOIN content_file f ON f.local_file_id = l.id WHERE f.preset != 'exercise'").fetchall()
    con.close()
    missing = [(i, e, s or 0) for i, e, s in files if not courses.file_on_disk(i, e)]
    need = sum(s for _, _, s in missing)
    if missing and not room(False, need):
        job.item(it.id, state="no room", note=f"needs {jobs.human(need)} more")
        return
    done = [0]

    def one(f):
        i, e, _ = f
        dest = root / "storage" / i[0] / i[1] / f"{i}.{e}"
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        if _plain_download(f"{STUDIO}/storage/{i[0]}/{i[1]}/{i}.{e}", tmp):
            tmp.replace(dest)
        done[0] += 1
        if done[0] % 200 == 0:
            job.step(f"{it.title}: {done[0]}/{len(missing)} files", done[0], len(missing))
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(one, missing))
    left = sum(1 for i, e, _ in missing if not courses.file_on_disk(i, e))
    job.item(it.id, state="here" if not left else "failed", files=len(files),
             note=f"{left} files still missing" if left else (f"{len(missing)} files downloaded" if missing else ""))


FETCHERS = {"zim": fetch_zim, "pdf": fetch_doc, "epub": fetch_doc, "book": fetch_book, "course": fetch_course}


def run(max_priority: int = 3, only: list[str] | None = None):
    with jobs.Job("fetch") as job:
        todo = [i for i in library.items() if i.priority <= max_priority and (not only or i.id in only)]
        todo.sort(key=lambda i: (i.priority, not i.disk_essential, i.kind != "zim"))
        for n, it in enumerate(todo, 1):
            job.step(it.title or it.id, n - 1, len(todo))
            try:
                FETCHERS[it.kind](it, job)
            except Exception as e:  # one bad item mustn't stop the rest
                job.item(it.id, state="failed", note=f"{type(e).__name__}: {e}"[:200])
        job.step("done", len(todo), len(todo))
        states = [v.get("state") for k, v in job.state["items"].items() if any(i.id == k for i in todo)]
        job.say(f"{states.count('here')} of {len(todo)} items here; "
                f"{len([s for s in states if s in ('failed', 'error')])} failed, {states.count('no room')} no room")
    index()


def index():
    with jobs.Job("index") as job:
        r = documents.build(log=job.say, progress=lambda n, t, title: job.step(title, n, t))
        job.say(f"documents: {r['files']} ({r['read']} read, {r['dropped']} dropped, {len(r['failed'])} unreadable)")
        c = courses.build(log=job.say)
        job.say(f"courses: {c['channels']} channels indexed")


def remove_files(it: library.Item):
    for f in it.files():
        if f.is_dir():
            shutil.rmtree(f)
        else:
            f.unlink(missing_ok=True)
    if it.kind == "book" and it.book_dir().is_dir():
        shutil.rmtree(it.book_dir())
