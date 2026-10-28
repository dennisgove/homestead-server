"""Download or resume everything in the catalog (homestead-fetch.service).

    python3 -m homestead.jobs.fetch [--tier N] [--only ID ...] [--plan]

--plan checks sizes and newer releases without downloading (homestead-fetch-plan.service);
the Library manager's space planner and update list read the result.

Resumable and checksum-verified: ZIMs come from Kiwix's metalinks via aria2,
into a hidden .homestead-partial folder beside their destination, and are moved
into place only once complete.
"""
import argparse
import html.parser
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from .. import catalog, config, kiwix
from .common import Job, free_bytes, human, is_mounted, start_unit

UA = {"User-Agent": "homestead-fetch/2.0 (offline preparedness library)"}
RESERVE = 2 * 1024**3  # leave this much free on each disk


def get(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def safe_url(u: str) -> str:
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit(p._replace(path=urllib.parse.quote(urllib.parse.unquote(p.path))))


def aria2(url: str, dest: Path, out: str | None = None) -> bool:
    cmd = ["aria2c", "--dir", str(dest), "--continue=true", "--max-connection-per-server=4", "--split=4",
           "--min-split-size=20M", "--file-allocation=falloc", "--check-integrity=true",
           "--follow-metalink=mem", "--auto-file-renaming=false", "--summary-interval=60",
           "--console-log-level=warn"]
    if out:
        cmd += ["--out", out]
    return subprocess.run(cmd + [url]).returncode == 0


def partial_dir(dest: Path) -> Path:
    """Sibling of dest, same filesystem (the final move is a rename), never scanned by Kiwix."""
    return dest.parent / ".homestead-partial" / dest.name


class PdfLinks(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.lower().split("?")[0].endswith(".pdf"):
                self.links.append(href)


def _queue_path() -> Path:
    return config.path("hub_state") / "fetch-queue.json"


def queue(ids: list[str]):
    """Ask for these items next (the Library manager's add and fetch buttons)."""
    import json
    p = _queue_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        cur = json.loads(p.read_text())
    except (OSError, ValueError):
        cur = []
    p.write_text(json.dumps(sorted(set(cur) | set(ids))))


def take_queue() -> list[str]:
    import json
    p = _queue_path()
    try:
        ids = json.loads(p.read_text())
    except (OSError, ValueError):
        return []
    p.unlink(missing_ok=True)
    return ids


def disk_ready(disk: str) -> bool:
    return disk == "core" or is_mounted(config.path("library"))


# --- ZIMs ---------------------------------------------------------------------

def plan_zim(it: dict) -> dict:
    have = catalog.zim_files(it["name"])
    try:
        rel = kiwix.latest(it["name"])
    except OSError as e:
        return {"state": "offline" if have else "error", "error": str(e), "have": [p.name for p in have]}
    if rel is None:
        return {"state": "missing-upstream" if not have else "done", "have": [p.name for p in have]}
    fn = rel["url"].rsplit("/", 1)[-1].removesuffix(".meta4")
    up_to_date = any(p.name == fn for p in have)
    st = {"latest": fn, "size": rel["size"], "have": [p.name for p in have], "url": rel["url"]}
    if up_to_date:
        st["state"] = "done"
    elif have and not it.get("update", True):
        st["state"] = "done"  # pinned to the release we have
    elif have:
        st["state"] = "update"
    else:
        st["state"] = "pending"
    return st


def fetch_zim(job: Job, it: dict, st: dict):
    dest = catalog.zim_dir(it["disk"])
    if not disk_ready(it["disk"]):
        job.item(it["id"], state="waiting", error="LIBRARY drive not mounted")
        return
    fn = st["latest"]
    need = st.get("size", 0)
    if need and need > free_bytes(dest) - RESERVE:
        job.item(it["id"], state="no-space", error=f"needs {human(need)}, {human(free_bytes(dest))} free")
        return
    stage = partial_dir(dest)
    stage.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)
    job.item(it["id"], state="downloading", file=fn, size=need)
    job.status["current"] = it.get("title") or fn
    job.log(f"downloading {fn} ({human(need)})")
    if not aria2(st["url"], stage) or (stage / (fn + ".aria2")).exists():
        job.item(it["id"], state="failed", error="download failed; it resumes next run")
        return
    os.replace(stage / fn, dest / fn)
    for old in catalog.zim_files(it["name"]):
        if old.name != fn:
            old.unlink()
            job.log(f"removed older {old.name}")
    for f in stage.glob(f"{it['name']}_*"):  # partials of older releases
        f.unlink()
    job.item(it["id"], state="done", file=fn, error="")


# --- documents ----------------------------------------------------------------

def fetch_doc(job: Job, it: dict):
    folder = catalog.docs_dir(it["category"])
    target = folder / it["file"]
    if target.exists():
        job.item(it["id"], state="done", file=it["file"], error="")
        return
    folder.mkdir(parents=True, exist_ok=True)
    job.status["current"] = it["title"]
    job.log(f"downloading {it['title']}")
    ok = aria2(safe_url(it["url"]), folder, it["file"])
    job.item(it["id"], state="done" if ok else "failed", file=it["file"], error="" if ok else "download failed")


def fetch_docpage(job: Job, it: dict, plan_only: bool):
    sub = catalog.docs_dir(it["category"]) / it["folder"]
    try:
        p = PdfLinks()
        p.feed(get(it["page"]))
    except OSError as e:
        job.item(it["id"], state="offline" if sub.is_dir() else "error", error=f"couldn't read page: {e}")
        return
    links = sorted({urllib.parse.urljoin(it["page"], h) for h in p.links})
    if it.get("match"):
        links = [u for u in links if re.search(it["match"], u)]
    rename = it.get("file_names") or {}
    names = {u: os.path.basename(urllib.parse.unquote(urllib.parse.urlsplit(u).path)) for u in links}
    names = {u: rename.get(n, n) for u, n in names.items()}
    todo = [u for u in links if not (sub / names[u]).exists()]
    if plan_only:
        job.item(it["id"], state="pending" if todo else "done", files=len(links), missing=len(todo))
        return
    sub.mkdir(parents=True, exist_ok=True)
    (sub / ".title").write_text(it["title"])
    failed = 0
    for i, u in enumerate(todo, 1):
        job.status["current"] = f"{it['title']} ({i}/{len(todo)})"
        job.save()
        if not aria2(safe_url(u), sub, names[u]):
            failed += 1
    job.item(it["id"], state="failed" if failed else "done", files=len(links),
             missing=failed, error=f"{failed} files failed" if failed else "")


# --- Kolibri ------------------------------------------------------------------

def fetch_kolibri(job: Job, it: dict, plan_only: bool):
    container = config.load().get("kolibri_container", "homestead-kolibri")
    if plan_only:
        job.item(it["id"], state=job.status["items"].get(it["id"], {}).get("state", "pending"))
        return
    if not disk_ready(it["disk"]):
        job.item(it["id"], state="waiting", error="LIBRARY drive not mounted")
        return
    job.status["current"] = it["title"]
    job.log(f"importing Kolibri channel {it['title']}")
    for step in ("importchannel", "importcontent"):
        r = subprocess.run(["docker", "exec", container, "kolibri", "manage", step, "network", it["channel"]])
        if r.returncode != 0:
            job.item(it["id"], state="failed", error=f"kolibri {step} failed")
            return
    job.item(it["id"], state="done", error="")


# --- main -----------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", type=int, default=config.load().get("content_tier", 3))
    ap.add_argument("--only", nargs="*", help="only these item ids")
    ap.add_argument("--plan", action="store_true", help="check sizes and releases; download nothing")
    args = ap.parse_args(argv)

    name = "fetch-plan" if args.plan else "fetch"
    with Job(name) as job:
        queued = [] if args.plan else take_queue()
        only = (args.only or []) + queued
        run(job, args, only)
        while not args.plan and (more := take_queue()):  # added while we were busy
            run(job, args, more)
    if not args.plan:
        start_unit("homestead-catalog-apply.service")


def run(job: Job, args, only: list[str]):
    items = catalog.items(tier=None if only else args.tier)
    if only:
        items = [i for i in items if i["id"] in only]
    # Critical first, then essentials before bulk.
    items.sort(key=lambda i: (i["tier"], i["disk"] != "core"))
    job.status["total"] = len(items)
    job.log(f"{'checking' if args.plan else 'fetching'} {len(items)} items" + (f" (tier ≤ {args.tier})" if not only else ""))
    for n, it in enumerate(items, 1):
        job.status["done"] = n - 1
        try:
            if it["type"] == "zim":
                st = plan_zim(it)
                job.item(it["id"], **st)
                if not args.plan and st["state"] in ("pending", "update"):
                    fetch_zim(job, it, st)
            elif it["type"] == "doc" and not it.get("url"):
                job.item(it["id"], state="done" if catalog.item_files(it) else "missing", error="")
            elif it["type"] == "doc":
                if args.plan:
                    job.item(it["id"], state="done" if catalog.item_files(it) else "pending")
                else:
                    fetch_doc(job, it)
            elif it["type"] == "docpage":
                fetch_docpage(job, it, args.plan)
            elif it["type"] == "kolibri":
                fetch_kolibri(job, it, args.plan)
        except Exception as e:  # one bad item mustn't stop the rest
            job.item(it["id"], state="failed", error=f"{type(e).__name__}: {e}")
    job.status["done"] = len(items)
    job.log("finished")


if __name__ == "__main__":
    main()
