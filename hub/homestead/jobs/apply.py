"""Apply the catalog to the disks (homestead-catalog-apply.service).

- deletes the files of items removed in the Library manager (when asked to)
- rebuilds the Kiwix library (one library.xml for both disks; newest release of
  each ZIM, essentials copy preferred) so the library server shows exactly what's on disk
- then starts the books import and the AI knowledge-base sync
"""
import shutil
import subprocess
from pathlib import Path

from .. import catalog, config
from .common import Job, start_unit


def delete_removed(job: Job):
    for it in catalog.merged(include_removed=True)["items"]:
        rm = it.get("removed")
        if not rm:
            continue
        if rm.get("delete"):
            for f in catalog.item_files(it):
                job.log(f"deleting {f}")
                if f.is_dir():
                    shutil.rmtree(f)
                else:
                    f.unlink(missing_ok=True)
            if it["type"] == "docpage":
                d = catalog.docs_dir(it["category"]) / it["folder"]
                if d.is_dir():
                    shutil.rmtree(d)
        catalog.forget_removed(it["id"])
        job.item(it["id"], state="removed")


def library_zims() -> list[tuple[str, Path]]:
    """(container path, host path) for every finished ZIM, one release per name."""
    best: dict[str, tuple[str, Path]] = {}
    for disk, mount in (("core", "/data/core"), ("library", "/data/library")):
        d = catalog.zim_dir(disk)
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.zim")):
            m = catalog.ZIM_FILE.match(f.name)
            if not m or Path(str(f) + ".aria2").exists():
                continue
            key = m["name"]
            cand = (f"{mount}/{f.name}", f)
            cur = best.get(key)
            # newest release wins; on a tie the essentials copy wins
            if cur is None or f.name > cur[1].name or (f.name == cur[1].name and disk == "core"):
                best[key] = cand
    return sorted(best.values())


def rebuild_kiwix_library(job: Job):
    cfg = config.load()
    container = cfg["kiwix"]["container"]
    zims = library_zims()
    job.log(f"rebuilding the library index: {len(zims)} ZIMs")
    # Build a fresh file next to the live one, then swap it in; kiwix-serve
    # (--monitorLibrary) picks up the change by itself.
    tmp_in_container = "/library/library.xml.new"
    subprocess.run(["docker", "exec", container, "rm", "-f", tmp_in_container], check=False)
    ok = 0
    for cpath, _host in zims:
        r = subprocess.run(["docker", "exec", container, "kiwix-manage", tmp_in_container, "add", cpath],
                           capture_output=True, text=True)
        if r.returncode == 0:
            ok += 1
        else:
            job.log(f"couldn't add {cpath}: {r.stderr.strip()[:200]}")
    subprocess.run(["docker", "exec", container, "mv", "-f", tmp_in_container, "/library/library.xml"], check=True)
    job.item("kiwix-library", state="done", zims=ok)


def main(argv=None):
    with Job("catalog-apply") as job:
        delete_removed(job)
        rebuild_kiwix_library(job)
        job.log("applied")
    start_unit("homestead-books.service")
    start_unit("homestead-kb-sync.service")


if __name__ == "__main__":
    main()
