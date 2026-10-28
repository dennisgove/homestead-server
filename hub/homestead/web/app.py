"""Homestead Hub web app.

Public pages: portal, emergency, guides, maps, binder, status.
Admin pages (behind the admin password at Caddy): the Library manager.
API: /api/... for pages, the AI filter, and future apps.

Run: uvicorn homestead.web.app:app (homestead-hub.service)
"""
import os
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import catalog, config, kiwix, librarysearch, status
from ..jobs.common import human, read_status

HERE = Path(__file__).parent
JOB_UNITS = {"fetch": "homestead-fetch", "fetch-plan": "homestead-fetch-plan", "catalog-apply": "homestead-catalog-apply",
             "books": "homestead-books", "maps": "homestead-maps", "kb-sync": "homestead-kb-sync"}
JOB_LABELS = {"fetch": "Download library", "fetch-plan": "Check sizes & updates", "catalog-apply": "Apply catalog",
              "books": "Update books library", "maps": "Build maps", "kb-sync": "Update AI knowledge"}

app = FastAPI(title="Homestead Hub", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

# Hub modules: each folder in web/modules/ with an __init__.py that defines
# `router` (a FastAPI APIRouter) becomes part of the Hub. Optional: `menu =
# {"label": ..., "href": ...}` for the top bar, and a templates/ folder.
import importlib
import pkgutil

from . import modules as _modules

MODULES = []
_template_dirs = [HERE / "templates"]
for _m in pkgutil.iter_modules(_modules.__path__):
    mod = importlib.import_module(f"{_modules.__name__}.{_m.name}")
    if getattr(mod, "enabled", True) and hasattr(mod, "router"):
        MODULES.append(mod)
        if (Path(mod.__file__).parent / "templates").is_dir():
            _template_dirs.append(Path(mod.__file__).parent / "templates")
templates = Jinja2Templates(directory=[str(d) for d in _template_dirs])
templates.env.filters["human"] = human
templates.env.filters["ago"] = lambda t: "never" if not t else time.strftime("%b %d %H:%M", time.localtime(t))


def portal_data() -> dict:
    with open(HERE / "portal.yaml") as f:
        return yaml.safe_load(f)


def app_url(request: Request, a: dict) -> str:
    """Link to an app on whatever name the visitor used (homestead.local, library.lan, an IP)."""
    if a.get("href"):
        return a["href"]
    host = request.url.hostname or config.load()["site"]["lan_name"]
    if a.get("access") == "local":
        host = "localhost"
    return f"{a.get('scheme', 'http')}://{host}:{a['port']}{a.get('path', '/')}"


def ctx(request: Request, **kw) -> dict:
    cfg = config.load()
    return {"request": request, "site": cfg["site"], "cfg": cfg, "app_url": lambda a: app_url(request, a),
            "apps": cfg["apps"], "cats": catalog.merged().get("categories", {}),
            "module_menu": [m.menu for m in MODULES if getattr(m, "menu", None)], **kw}


def page(request: Request, name: str, **kw) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name=name, context=ctx(request, **kw))


def require_admin(request: Request):
    """Caddy adds the admin header after checking the admin password; nothing else can."""
    secret = config.load().get("admin_header", "")
    if secret and request.headers.get("x-homestead-admin") != secret:
        raise HTTPException(403, "admin only")


def core_search_url(request: Request, q: str) -> str:
    cfg = config.load()
    a = next(x for x in cfg["apps"] if x["id"] == cfg["kiwix"]["core_app"])
    return app_url(request, {**a, "path": "/search?" + "pattern=" + q.replace(" ", "+")})


# --- documents on disk -------------------------------------------------------------

def guides(category: str | None = None) -> dict[str, list[dict]]:
    docs = config.path("docs")
    titles = catalog.doc_titles()
    out: dict[str, list[dict]] = {}
    if not docs.is_dir():
        return out
    for f in sorted(docs.rglob("*")):
        if not f.is_file() or f.name.startswith(".") or "/.homestead-partial" in str(f):
            continue
        rel = f.relative_to(docs)
        cat = rel.parts[0]
        if category and cat != category:
            continue
        out.setdefault(cat, []).append({"title": catalog.doc_title(f, titles), "path": "/docs/" + str(rel)})
    for v in out.values():
        v.sort(key=lambda d: d["title"].lower())
    return out


# --- public pages --------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def portal(request: Request):
    p = portal_data()
    return page(request, "portal.html", p=p, guides=guides(), search=lambda q: core_search_url(request, q))


@app.get("/emergency", response_class=HTMLResponse)
def emergency(request: Request):
    return page(request, "emergency.html", p=portal_data(), guides=guides("medical"),
                search=lambda q: core_search_url(request, q))


@app.get("/search")
def search(request: Request, q: str = ""):
    return RedirectResponse(core_search_url(request, q) if q else "/")


@app.get("/maps", response_class=HTMLResponse)
def maps(request: Request):
    import json
    try:
        info = json.loads((config.path("maps") / "maps.json").read_text())
    except (OSError, ValueError):
        info = None
    layers = {n: (config.path("maps") / f"{n}.pmtiles").exists() for n in ("detailed", "wide", "world")}
    return page(request, "maps.html", info=info, layers=layers)


VIDEO_EXTS = (".mp4", ".m4v", ".webm", ".mkv", ".mov", ".ogv", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav")


def videos_on_disk() -> dict[str, list[dict]]:
    root = config.path("video")
    out: dict[str, list[dict]] = {}
    if not root.is_dir():
        return out
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS and not f.name.startswith("."):
            rel = f.relative_to(root)
            group = str(rel.parent) if rel.parent != Path(".") else "Videos"
            out.setdefault(group, []).append({"title": re.sub(r"[_.-]+", " ", f.stem).strip(), "rel": str(rel),
                                              "audio": f.suffix.lower() in (".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav"),
                                              "size": f.stat().st_size})
    return out


@app.get("/videos", response_class=HTMLResponse)
def videos(request: Request, play: str = ""):
    groups = videos_on_disk()
    current = None
    if play:
        current = next((v for vs in groups.values() for v in vs if v["rel"] == play), None)
    return page(request, "videos.html", groups=groups, current=current)


@app.get("/binder", response_class=HTMLResponse)
def binder(request: Request):
    items = [i for i in catalog.items() if i.get("binder")]
    have = {i["id"]: catalog.item_files(i) for i in items}
    return page(request, "binder.html", items=items, have=have, docs_root=config.path("docs"))


@app.get("/status", response_class=HTMLResponse)
def status_page(request: Request):
    return page(request, "status.html", s=status.full(), job_labels=JOB_LABELS)


@app.get("/partials/strip", response_class=HTMLResponse)
def strip(request: Request):
    return page(request, "_strip.html", s=status.strip())


# --- API -------------------------------------------------------------------------------

@app.get("/api/apps")
def api_apps(request: Request):
    return [{**a, "url": app_url(request, a)} for a in config.load()["apps"]]


@app.get("/api/status")
def api_status():
    return status.full()


@app.get("/api/catalog")
def api_catalog():
    return catalog.merged()


@app.get("/api/places")
def api_places(q: str, limit: int = 10):
    db = config.path("maps") / "places.sqlite"
    if not db.exists() or not q.strip():
        return []
    terms = " ".join(f'"{w}"*' for w in re.findall(r"\w+", q))
    if not terms:
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT name, kind, admin, lat, lon FROM places WHERE places MATCH ? "
                           "ORDER BY CAST(score AS INTEGER) DESC LIMIT ?", (terms, limit)).fetchall()
    finally:
        con.close()
    return [{"name": r[0], "kind": r[1], "admin": r[2], "lat": r[3], "lon": r[4]} for r in rows]


@app.get("/api/library/search")
def api_library_search(q: str, count: int = 10):
    return kiwix.search_local(config.load()["kiwix"]["search_url"], q, count=count)


@app.get("/api/library/context")
def api_library_context(q: str, articles: int = 3):
    """Passages from the library for an AI prompt (used by the Open WebUI library-search filter)."""
    return librarysearch.context(q, max_articles=articles)


# --- Library manager (admin) ----------------------------------------------------------------

def item_rows() -> list[dict]:
    fetch = (read_status("fetch") or {}).get("items", {})
    plan = (read_status("fetch-plan") or {}).get("items", {})
    rows = []
    for it in catalog.merged(include_removed=True)["items"]:
        files = catalog.item_files(it)
        st = {**plan.get(it["id"], {}), **fetch.get(it["id"], {})}
        on_disk = sum(f.stat().st_size for f in files if f.is_file())
        state = "removed" if it.get("removed") else ("on disk" if files else st.get("state", "not downloaded"))
        if files and st.get("state") == "update":
            state = "update available"
        rows.append({**it, "files": files, "on_disk": on_disk, "state": state, "status": st})
    return rows


def health() -> dict:
    cfg = config.load()
    tier = cfg.get("content_tier", 3)
    rows = item_rows()
    names = {r["name"] for r in rows if r["type"] == "zim"}
    missing = [r for r in rows if not r.get("removed") and not r["files"] and r["tier"] <= tier and r["type"] != "kolibri"]
    dupes = []
    for r in rows:
        if r["type"] == "zim" and len(r["files"]) > 1:
            dupes.append(r)
    orphans = []
    for disk in ("core", "library"):
        d = catalog.zim_dir(disk)
        for f in sorted(d.glob("*.zim")) if d.is_dir() else []:
            m = catalog.ZIM_FILE.match(f.name)
            if m and m["name"] not in names:
                orphans.append({"kind": "zim", "name": m["name"], "file": f, "disk": disk, "size": f.stat().st_size})
    owned = set()
    for r in rows:
        owned.update(str(f) for f in r["files"])
    docs = config.path("docs")
    for f in sorted(docs.rglob("*")) if docs.is_dir() else []:
        if (f.is_file() and not f.name.startswith(".") and str(f) not in owned
                and ".homestead-partial" not in str(f)):
            rel = f.relative_to(docs)
            orphans.append({"kind": "doc", "name": f.name, "file": f, "category": rel.parts[0],
                            "folder": str(Path(*rel.parts[1:-1])) if len(rel.parts) > 2 else "",
                            "size": f.stat().st_size})
    partial = []
    for disk in ("core", "library"):
        p = catalog.zim_dir(disk).parent / ".homestead-partial" / "zim"
        for f in sorted(p.glob("*")) if p.is_dir() else []:
            if not f.name.endswith(".aria2"):
                partial.append({"file": f, "size": f.stat().st_size})
    return {"missing": missing, "dupes": dupes, "orphans": orphans, "partial": partial}


def space_plan() -> dict:
    plan = (read_status("fetch-plan") or {}).get("items", {})
    out = {}
    for disk in ("core", "library"):
        d = status.disk(catalog.zim_dir(disk).parent if catalog.zim_dir(disk).parent.exists() else config.path(disk))
        need = sum(v.get("size", 0) for k, v in plan.items()
                   if v.get("state") in ("pending", "update") and (catalog.get(k) or {}).get("disk") == disk)
        out[disk] = {"disk": d, "need": need}
    return out


@app.get("/library", response_class=HTMLResponse)
def library_home(request: Request):
    require_admin(request)
    rows = item_rows()
    jobs = {j: read_status(j) for j in JOB_UNITS}
    counts = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return page(request, "library/home.html", jobs=jobs, job_labels=JOB_LABELS, counts=counts,
                space=space_plan(), h=health())


@app.get("/library/items", response_class=HTMLResponse)
def library_items(request: Request, category: str = "", type: str = "", state: str = "", q: str = ""):
    require_admin(request)
    rows = item_rows()
    if category:
        rows = [r for r in rows if r["category"] == category]
    if type:
        rows = [r for r in rows if r["type"] == type]
    if state:
        rows = [r for r in rows if r["state"] == state]
    if q:
        rows = [r for r in rows if q.lower() in (r["title"] + " " + r["id"]).lower()]
    return page(request, "library/items.html", rows=rows, f={"category": category, "type": type, "state": state, "q": q},
                states=sorted({r["state"] for r in item_rows()}))


@app.post("/library/items/{item_id}")
def library_change(request: Request, item_id: str, field: str = Form(...), value: str = Form(...)):
    require_admin(request)
    v: object = value
    if field in ("ai", "binder", "update"):
        v = value in ("1", "true", "on", "yes")
    elif field == "tier":
        v = int(value)
    catalog.change(item_id, **{field: v})
    return RedirectResponse(request.headers.get("referer", "/library/items"), status_code=303)


@app.post("/library/items/{item_id}/remove")
def library_remove(request: Request, item_id: str, delete: str = Form("")):
    require_admin(request)
    catalog.remove(item_id, delete_files=bool(delete))
    run_job("catalog-apply")
    return RedirectResponse(request.headers.get("referer", "/library/items"), status_code=303)


@app.post("/library/items/{item_id}/restore")
def library_restore(request: Request, item_id: str):
    require_admin(request)
    catalog.restore(item_id)
    return RedirectResponse(request.headers.get("referer", "/library/items"), status_code=303)


@app.post("/library/items/{item_id}/fetch")
def library_fetch_one(request: Request, item_id: str):
    require_admin(request)
    run_job("fetch", "--only", item_id)
    return RedirectResponse(request.headers.get("referer", "/library"), status_code=303)


@app.get("/library/add", response_class=HTMLResponse)
def library_add(request: Request, q: str = "", lang: str = "eng", start: int = 0):
    require_admin(request)
    results, total, error = [], 0, ""
    if q or start:
        try:
            total, results = kiwix.search_catalog(q, lang=lang, count=30, start=start)
        except OSError as e:
            error = f"Couldn't reach the Kiwix catalog (no internet?): {e}"
    have = {i["name"] for i in catalog.merged(include_removed=True)["items"] if i["type"] == "zim"}
    return page(request, "library/add.html", q=q, lang=lang, start=start, total=total, results=results,
                have=have, error=error)


@app.post("/library/add/zim")
def library_add_zim(request: Request, name: str = Form(...), title: str = Form(""), category: str = Form("reference"),
                    tier: int = Form(2), disk: str = Form("library")):
    require_admin(request)
    catalog.add({"id": name, "type": "zim", "name": name, "title": title or name, "category": category,
                 "tier": tier, "disk": disk})
    run_job("fetch", "--only", name)
    return RedirectResponse("/library/items?q=" + name, status_code=303)


@app.post("/library/add/doc")
def library_add_doc(request: Request, url: str = Form(...), title: str = Form(...), category: str = Form(...),
                    ai: str = Form(""), binder: str = Form("")):
    require_admin(request)
    fn = Path(url.split("?")[0]).name or "document.pdf"
    if "." not in fn:
        fn += ".pdf"
    item_id = catalog.slug(title)
    catalog.add({"id": item_id, "type": "doc", "url": url, "file": catalog.slug(Path(fn).stem) + Path(fn).suffix.lower(),
                 "title": title, "category": category, "tier": 1, "ai": bool(ai), "binder": bool(binder)})
    run_job("fetch", "--only", item_id)
    return RedirectResponse("/library/items?q=" + item_id, status_code=303)


@app.post("/library/upload")
async def library_upload(request: Request, file: UploadFile = File(...), title: str = Form(""),
                         category: str = Form(...), ai: str = Form(""), binder: str = Form("")):
    require_admin(request)
    if category not in catalog.merged().get("categories", {}):
        raise HTTPException(400, "unknown category")
    name = catalog.slug(Path(file.filename or "upload").stem) + Path(file.filename or "").suffix.lower()
    dest = catalog.docs_dir(category) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    item_id = catalog.slug(title or Path(name).stem)
    if not catalog.get(item_id):
        catalog.add({"id": item_id, "type": "doc", "url": None, "file": name, "title": title or Path(name).stem,
                     "category": category, "tier": 1, "ai": bool(ai), "binder": bool(binder)})
    run_job("catalog-apply")
    return RedirectResponse("/library/items?q=" + item_id, status_code=303)


@app.post("/library/adopt")
def library_adopt(request: Request, kind: str = Form(...), name: str = Form(...), disk: str = Form("library"),
                  category: str = Form("reference"), folder: str = Form("")):
    """Add something already on disk to the catalog."""
    require_admin(request)
    if kind == "zim":
        catalog.add({"id": name, "type": "zim", "name": name, "title": name, "category": category, "tier": 3, "disk": disk})
    else:
        f = name if not folder else f"{folder}/{name}"
        catalog.add({"id": catalog.slug(Path(name).stem), "type": "doc", "url": None, "file": f,
                     "title": re.sub(r"[_-]+", " ", Path(name).stem), "category": category, "tier": 1, "ai": True})
    return RedirectResponse("/library/health", status_code=303)


@app.get("/library/health", response_class=HTMLResponse)
def library_health(request: Request):
    require_admin(request)
    return page(request, "library/health.html", h=health(), manual=catalog.merged().get("manual", []))


@app.get("/library/updates", response_class=HTMLResponse)
def library_updates(request: Request):
    require_admin(request)
    rows = [r for r in item_rows() if r["status"].get("state") == "update"]
    plan = read_status("fetch-plan")
    return page(request, "library/updates.html", rows=rows, plan=plan)


@app.get("/library/export")
def library_export(request: Request):
    require_admin(request)
    return PlainTextResponse(catalog.export_patch(), headers={"Content-Disposition": "attachment; filename=catalog-edits.yaml"})


def run_job(job: str, *args: str) -> bool:
    """Start a library job through systemd (the Hub never runs them itself).

    `run_job("fetch", "--only", id)` queues that item: the fetch job picks up
    queued items when it starts, or when it finishes what it's doing."""
    if job == "fetch" and args[:1] == ("--only",):
        from ..jobs.fetch import queue
        queue(list(args[1:]))
    r = subprocess.run(["systemctl", "start", "--no-block", f"{JOB_UNITS[job]}.service"], capture_output=True, text=True)
    return r.returncode == 0


@app.post("/library/jobs/{job}")
def library_job(request: Request, job: str):
    require_admin(request)
    if job not in JOB_UNITS:
        raise HTTPException(404)
    run_job(job)
    return RedirectResponse(request.headers.get("referer", "/library"), status_code=303)


@app.get("/library/partials/jobs", response_class=HTMLResponse)
def library_jobs_partial(request: Request):
    require_admin(request)
    return page(request, "library/_jobs.html", jobs={j: read_status(j) for j in JOB_UNITS}, job_labels=JOB_LABELS)


# Modules last, so they can use page() and the helpers above.
for _mod in MODULES:
    app.include_router(_mod.router)
