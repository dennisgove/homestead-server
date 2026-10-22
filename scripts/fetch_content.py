#!/usr/bin/env python3
"""Download the offline library described in content/manifest.yaml.

    sudo scripts/fetch_content.py --list              show what would be fetched, with sizes
    sudo scripts/fetch_content.py --tier 1            critical content (do this first)
    sudo scripts/fetch_content.py --tier 3            everything
    sudo scripts/fetch_content.py --tier 3 --update   also replace ZIMs that have a newer release
    sudo scripts/fetch_content.py --docs-index        just rebuild the portal's guide list

Resumable: run it again after an interruption. ZIMs are checksum-verified by
aria2c from the Kiwix metalink. Run it inside tmux; tier 3 is several TB.
"""
import argparse
import html.parser
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "..", "content", "manifest.yaml")
KIWIX = "https://download.kiwix.org/zim"
CORE_ZIM = "/srv/core/zim"
CORE_DOCS = "/srv/core/docs"
LIBRARY_ZIM = "/opt/project-nomad/storage/zim"
PORTAL_DOCS = "/srv/portal/data/docs.json"
UA = {"User-Agent": "homestead-fetch/1.0 (offline preparedness library)"}
_listing_cache = {}


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024


def latest_zim(spec):
    """'other/wikem_en_all_maxi' -> ('wikem_en_all_maxi_2026-07.zim', url)."""
    folder, name = spec.split("/", 1)
    if folder not in _listing_cache:
        _listing_cache[folder] = re.findall(r'href="([^"/]+\.zim)"', get(f"{KIWIX}/{folder}/"))
    pat = re.compile(re.escape(name) + r"_(\d{4}-\d{2}[a-z]?)\.zim$")
    hits = sorted((m.group(1), f) for f in _listing_cache[folder] if (m := pat.match(f)))
    if not hits:
        return None, None
    fn = hits[-1][1]
    return fn, f"{KIWIX}/{folder}/{fn}"


def meta4_size(url):
    try:
        m = re.search(r"<size>(\d+)</size>", get(url + ".meta4"))
        return int(m.group(1)) if m else None
    except OSError:
        return None


def free_space(path):
    while not os.path.exists(path):
        path = os.path.dirname(path)
    return shutil.disk_usage(path).free


def existing(dest, name):
    pat = re.compile(re.escape(name) + r"_\d{4}-\d{2}[a-z]?\.zim$")
    return sorted(f for f in os.listdir(dest) if pat.match(f)) if os.path.isdir(dest) else []


def aria2(url, dest, out=None):
    cmd = ["aria2c", "--dir", dest, "--continue=true", "--max-connection-per-server=4", "--split=4",
           "--min-split-size=20M", "--file-allocation=falloc", "--check-integrity=true",
           "--follow-metalink=mem", "--auto-file-renaming=false", "--summary-interval=60",
           "--console-log-level=warn"]
    if out:
        cmd += ["--out", out]
    return subprocess.run(cmd + [url]).returncode == 0


def register_with_nomad(fn):
    """Add a ZIM to NOMAD's Kiwix library.xml (kiwix-serve watches the file)."""
    args = ["kiwix-manage", "/data/kiwix-library.xml", "add", f"/data/{fn}"]
    if subprocess.run(["docker", "exec", "nomad_kiwix_server", *args], capture_output=True).returncode == 0:
        return
    r = subprocess.run(["docker", "run", "--rm", "-v", f"{LIBRARY_ZIM}:/data", "ghcr.io/kiwix/kiwix-tools:3.8.1", *args],
                       capture_output=True)
    if r.returncode != 0:
        print(f"  ! couldn't register {fn} with NOMAD; use Command Center > Settings > Information Library to rescan")


def fetch_zims(items, update, dry):
    plan = []
    for z in items:
        dest = CORE_ZIM if z["target"] == "core" else LIBRARY_ZIM
        name = z["kiwix"].split("/", 1)[1]
        have = existing(dest, name)
        fn, url = latest_zim(z["kiwix"])
        if fn is None:
            print(f"  ? {z['kiwix']}: not found on the mirror (renamed?)")
            continue
        if have and (not update or fn in have):
            continue
        if z["target"] == "library" and not dry and not os.path.ismount(os.path.dirname(LIBRARY_ZIM)):
            print(f"  - {fn}: LIBRARY drive not mounted, skipping")
            continue
        plan.append((z, dest, fn, url, have, meta4_size(url) or 0))

    by_dest = {}
    for p in plan:
        by_dest[p[1]] = by_dest.get(p[1], 0) + p[5]
    for d, need in by_dest.items():
        if not dry:
            os.makedirs(d, exist_ok=True)
        free = free_space(d)
        print(f"{d}: {len([p for p in plan if p[1] == d])} files, {human(need)} to download, {human(free)} free")
        if need > free * 0.95:
            print(f"  ! not enough space in {d}; lower --tier or free space. Later items will fail.")
    for z, dest, fn, url, have, size in plan:
        print(f"  T{z['tier']} {z['cat']:<9} {human(size):>10}  {fn}")
    if dry:
        return

    core_changed = False
    for z, dest, fn, url, have, size in plan:
        free = shutil.disk_usage(dest).free
        if size and size > free - 2 * 1024**3:
            print(f"  ! skipping {fn}: needs {human(size)}, {human(free)} free")
            continue
        print(f"\n==> {fn} ({human(size)})")
        if not aria2(url + ".meta4", dest):
            print(f"  ! download failed: {fn} (re-run to resume)")
            continue
        for old in have:
            if old != fn:
                os.remove(os.path.join(dest, old))
                print(f"  removed older {old}")
        if dest == CORE_ZIM:
            core_changed = True
        else:
            register_with_nomad(fn)
    if core_changed:
        subprocess.run(["docker", "restart", "homestead-kiwix-core"], capture_output=True)


class PdfLinks(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.lower().split("?")[0].endswith(".pdf"):
                self.links.append(href)


def safe_url(u):
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit(p._replace(path=urllib.parse.quote(urllib.parse.unquote(p.path))))


def fetch_docs(items, dry):
    for d in items:
        folder = os.path.join(CORE_DOCS, d["cat"])
        if "url" in d:
            target = os.path.join(folder, d["file"])
            if os.path.exists(target):
                continue
            print(f"  doc  {d['title']}")
            if not dry:
                os.makedirs(folder, exist_ok=True)
                aria2(safe_url(d["url"]), folder, d["file"]) or print(f"  ! failed: {d['url']}")
        elif "page" in d:
            sub = os.path.join(folder, d["folder"])
            try:
                parser = PdfLinks()
                parser.feed(get(d["page"]))
            except OSError as e:
                print(f"  ! couldn't read {d['page']}: {e}")
                continue
            links = sorted({urllib.parse.urljoin(d["page"], h) for h in parser.links})
            todo = [u for u in links if not os.path.exists(os.path.join(sub, os.path.basename(urllib.parse.unquote(urllib.parse.urlsplit(u).path))))]
            if todo:
                print(f"  docs {d['title']}: {len(todo)} PDFs")
            if dry:
                continue
            os.makedirs(sub, exist_ok=True)
            with open(os.path.join(sub, ".title"), "w") as f:
                f.write(d["title"])
            for u in todo:
                out = os.path.basename(urllib.parse.unquote(urllib.parse.urlsplit(u).path))
                aria2(safe_url(u), sub, out) or print(f"  ! failed: {u}")


def docs_index(manifest):
    """Write the portal's list of guides from what's actually on disk."""
    titles = {d["file"]: d["title"] for d in manifest.get("docs", []) if "file" in d}
    out = []
    for root, _, files in os.walk(CORE_DOCS):
        rel_root = os.path.relpath(root, CORE_DOCS)
        cat = rel_root.split(os.sep)[0]
        if cat == ".":
            continue
        group = None
        if os.path.exists(os.path.join(root, ".title")):
            with open(os.path.join(root, ".title")) as f:
                group = f.read().strip()
        for fn in files:
            if fn.startswith(".") or not fn.lower().endswith((".pdf", ".epub", ".txt", ".html", ".md", ".docx", ".odt")):
                continue
            base = os.path.splitext(fn)[0].replace("_", " ").replace("-", " ")
            title = titles.get(fn) or (f"{group}: {base}" if group else base)
            out.append({"category": cat, "title": title,
                        "path": urllib.parse.quote(os.path.join(rel_root, fn).replace(os.sep, "/"))})
    os.makedirs(os.path.dirname(PORTAL_DOCS), exist_ok=True)
    with open(PORTAL_DOCS + ".tmp", "w") as f:
        json.dump(out, f)
    os.replace(PORTAL_DOCS + ".tmp", PORTAL_DOCS)
    print(f"portal guide list: {len(out)} documents")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", type=int, default=1, help="fetch tiers 1..N (default 1)")
    ap.add_argument("--target", choices=["core", "library"], help="only this destination")
    ap.add_argument("--update", action="store_true", help="replace ZIMs that have a newer release")
    ap.add_argument("--list", action="store_true", help="show the plan without downloading")
    ap.add_argument("--docs-index", action="store_true", help="only rebuild the portal guide list")
    args = ap.parse_args()

    with open(MANIFEST) as f:
        manifest = yaml.safe_load(f)
    if args.docs_index:
        docs_index(manifest)
        return
    if os.geteuid() != 0 and not args.list:
        sys.exit("run with sudo")
    if shutil.which("aria2c") is None and not args.list:
        sys.exit("aria2c not installed (sudo apt install aria2)")

    zims = [z for z in manifest["zims"] if z["tier"] <= args.tier and (not args.target or z["target"] == args.target)]
    docs = [d for d in manifest.get("docs", []) if d["tier"] <= args.tier]
    print(f"== ZIM archives (tiers 1-{args.tier})")
    fetch_zims(zims, args.update, args.list)
    print("\n== Documents")
    fetch_docs(docs, args.list)
    if not args.list:
        docs_index(manifest)
    print("\n== Get these by hand (no stable direct link), into /srv/core/docs/<category>/:")
    for m in manifest.get("manual", []):
        print(f"  [{m['cat']}] {m['title']}  <- {m['where']}")


if __name__ == "__main__":
    main()
