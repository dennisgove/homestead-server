"""Keep the Calibre library in step with the documents (homestead-books.service).

Every PDF/EPUB under paths.docs (by category) and paths.books_incoming (your own
books) is added to the Calibre library that Calibre-Web serves, tagged with its
category; files that disappear are removed again. Needs calibredb (apt: calibre)
and the LIBRARY drive (the Calibre library lives on it).
"""
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from .. import catalog, config
from .common import Job, is_mounted

EXTS = (".pdf", ".epub", ".mobi", ".azw3", ".djvu", ".txt", ".docx", ".odt")


CALIBRE_WEB_UID = 1000  # Calibre-Web runs as this user and must be able to write the library


def calibreweb_unconfigured() -> bool:
    app = next((a for a in config.load()["apps"] if a["id"] == "books"), None)
    if not app or not app.get("health"):
        return False
    try:
        r = urllib.request.urlopen(app["health"].rsplit("/", 1)[0] + "/", timeout=10)
        return "dbconfig" in urllib.parse.unquote(r.url)
    except OSError:
        return False


def calibredb(lib: Path, *args) -> subprocess.CompletedProcess:
    # As Calibre-Web's user: a root-owned metadata.db makes Calibre-Web refuse the library.
    return subprocess.run(["calibredb", *args, "--library-path", str(lib)], capture_output=True, text=True,
                          user=CALIBRE_WEB_UID, group=CALIBRE_WEB_UID, env={**os.environ, "HOME": str(lib)})


def sources() -> list[tuple[Path, str, str]]:
    """(file, title, tag) for every document we want in Calibre."""
    cats = catalog.merged().get("categories", {})
    titles = catalog.doc_titles()
    out = []
    docs = config.path("docs")
    for f in sorted(docs.rglob("*")) if docs.is_dir() else []:
        if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in EXTS:
            continue
        rel = f.relative_to(docs)
        tag = cats.get(rel.parts[0], rel.parts[0])
        out.append((f, catalog.doc_title(f, titles), tag))
    inc = config.path("books_incoming")
    for f in sorted(inc.rglob("*")) if inc.is_dir() else []:
        if f.is_file() and f.suffix.lower() in EXTS:
            out.append((f, re.sub(r"[_-]+", " ", f.stem).strip(), "Our own books"))
    return out


def main(argv=None):
    lib = config.path("books")
    with Job("books") as job:
        if shutil.which("calibredb") is None:
            job.log("calibredb isn't installed (apt install calibre)")
            job.status["state"] = "failed"
            return
        if not is_mounted(config.path("library")):
            job.log("LIBRARY drive not mounted; books wait for it")
            return
        lib.mkdir(parents=True, exist_ok=True)
        fresh = not (lib / "metadata.db").exists()
        for p in [lib, *lib.rglob("*")]:  # earlier runs (as root) left root-owned files
            try:
                os.chown(p, CALIBRE_WEB_UID, CALIBRE_WEB_UID)
            except OSError:
                pass
        known = job.status["items"]  # path -> {"id": calibre id, "mtime": ...}
        want = sources()
        job.status["total"] = len(want)
        seen = set()
        for n, (f, title, tag) in enumerate(want, 1):
            key = str(f)
            seen.add(key)
            mtime = int(f.stat().st_mtime)
            cur = known.get(key)
            if cur and cur.get("mtime") == mtime and cur.get("id"):
                continue
            job.status["current"], job.status["done"] = title, n
            if cur and cur.get("id"):  # changed file: replace the old copy
                calibredb(lib, "remove", str(cur["id"]))
            r = calibredb(lib, "add", "--duplicates", "--title", title, "--tags", tag, str(f))
            m = re.search(r"Added book ids: ([\d, ]+)", r.stdout)
            if m:
                job.item(key, id=int(m.group(1).split(",")[0]), mtime=mtime, title=title, state="done")
            else:
                job.item(key, state="failed", error=(r.stderr or r.stdout).strip()[-300:])
        gone = [k for k in list(known) if k not in seen and known[k].get("id")]
        if gone:
            calibredb(lib, "remove", ",".join(str(known[k]["id"]) for k in gone))
            for k in gone:
                del job.status["items"][k]
        # Calibre-Web only looks for its library when it starts: restart it if
        # the library is new, or if it's still showing its "no library" setup page.
        if fresh or calibreweb_unconfigured():
            subprocess.run(["docker", "restart", "homestead-calibreweb"], capture_output=True)
        job.status["done"] = len(want)
        job.log(f"{len(want)} documents in the books library ({len(gone)} removed)")


if __name__ == "__main__":
    main()
