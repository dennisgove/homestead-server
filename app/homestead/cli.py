"""The `homestead` command (on the server; most of it needs sudo).

    homestead status                    what's here, what isn't, disk space
    homestead fetch [--priority N] [ID…] download and update (needs internet), then index
    homestead index                     update the search index (after copying documents in)
    homestead maps                      build the offline maps (needs internet)
    homestead find WORDS                look for encyclopedias in Kiwix's catalog
    homestead add zim NAME --topic T [--essential]
    homestead add pdf|epub|book URL --title "…" --topic T [--match REGEX] [--print]
    homestead remove ID [--delete]      take it out of the library (and delete its files)
    homestead topics                    the topic names to use with --topic
"""
import argparse
import shutil
import sys

from . import fetch, jobs, library, maps, settings


def status(_):
    for name, p in (("internal disk", settings.path("core")), ("library drive", settings.path("library"))):
        try:
            u = shutil.disk_usage(p)
            print(f"{name}: {jobs.human(u.used)} used, {jobs.human(u.free)} free")
        except OSError:
            print(f"{name}: not available")
    if not settings.library_drive_ok():
        print("the USB library drive is NOT plugged in")
    st = (jobs.read("fetch") or {}).get("items", {})
    here = missing = 0
    for it in library.items():
        if it.on_disk():
            here += 1
        else:
            missing += 1
            s = st.get(it.id, {})
            print(f"  missing: {it.id} ({it.kind}, {it.topic}) {s.get('state', '')} {s.get('note', '')}".rstrip())
    print(f"{here} items here, {missing} missing")
    for j in jobs.JOBS:
        s = jobs.read(j)
        if s:
            print(f"{j}: {s['state']}{' · ' + s['log'][-1] if s.get('log') else ''}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="homestead", description="The homestead library.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    f = sub.add_parser("fetch")
    f.add_argument("--priority", type=int, default=settings.load().get("fetch_priority", 3))
    f.add_argument("ids", nargs="*")
    sub.add_parser("index")
    sub.add_parser("maps")
    sub.add_parser("topics")
    fd = sub.add_parser("find")
    fd.add_argument("words", nargs="+")
    a = sub.add_parser("add")
    a.add_argument("kind", choices=library.KINDS)
    a.add_argument("source")
    a.add_argument("--topic", required=True)
    a.add_argument("--title", default="")
    a.add_argument("--match", default="")
    a.add_argument("--essential", action="store_true")
    a.add_argument("--print", action="store_true")
    r = sub.add_parser("remove")
    r.add_argument("id")
    r.add_argument("--delete", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        status(args)
    elif args.cmd == "fetch":
        fetch.run(args.priority, args.ids or None)
    elif args.cmd == "index":
        fetch.index()
    elif args.cmd == "maps":
        with jobs.Job("maps") as job:
            maps.build(settings.load()["site"]["region"], log=job.say)
    elif args.cmd == "topics":
        for k, t in library.topics().items():
            print(f"{k:10} {t['name']}")
    elif args.cmd == "find":
        for e in fetch.find(" ".join(args.words)):
            print(f"{e['name']:50} {jobs.human(e['size']):>9}  {e['title']}")
    elif args.cmd == "add":
        raw = {args.kind: args.source, "topic": args.topic}
        for k in ("title", "match"):
            if getattr(args, k):
                raw[k] = getattr(args, k)
        if args.essential:
            raw["essential"] = True
        if args.print:
            raw["print"] = True
        it = library.add(raw)
        print(f"added {it.id}; it downloads with the next `homestead fetch`")
    elif args.cmd == "remove":
        it = library.get(args.id)
        if not it:
            sys.exit(f"no item {args.id!r} (see `homestead status`)")
        if args.delete:
            fetch.remove_files(it)
        library.remove(args.id)
        fetch.index()
        print(f"removed {args.id}")


if __name__ == "__main__":
    main()
