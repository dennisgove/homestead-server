"""The library manager: add and remove things, start downloads. It listens only on this
computer (127.0.0.1), so it needs no password: use it on the server's own screen at
http://localhost:8701, or from another computer through SSH (ssh -L 8701:localhost:8701 ...).
The guest account is blocked from it by the firewall.
"""
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import fetch, jobs, library, settings

HERE = Path(__file__).parent
app = FastAPI(title="Homestead library manager", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["human"] = jobs.human
templates.env.filters["when"] = lambda t: "never" if not t else __import__("time").strftime("%b %d, %H:%M", __import__("time").localtime(t))
UNITS = {"fetch": "homestead-fetch.service", "index": "homestead-index.service", "maps": "homestead-maps.service"}


def page(request: Request, name: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name=name, context={
        "request": request, "site": settings.load()["site"], "topics": library.topics(), "path": request.url.path,
        "manager": True} | ctx)


def start(job: str) -> bool:
    return subprocess.run(["systemctl", "start", "--no-block", UNITS[job]], capture_output=True).returncode == 0


def rows() -> list[dict]:
    st = (jobs.read("fetch") or {}).get("items", {})
    out = []
    removed = set(library.changes()["removed"])
    for it in library.items(include_removed=True):
        files = it.files()
        out.append({"it": it, "here": bool(files), "size": sum(f.stat().st_size for f in files if f.is_file()),
                    "state": st.get(it.id, {}).get("state", ""), "note": st.get(it.id, {}).get("note", ""),
                    "removed": it.id in removed})
    return out


@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    disks = {}
    for name, p in (("Internal disk", settings.path("core")), ("USB library drive", settings.path("library"))):
        try:
            u = shutil.disk_usage(p)
            disks[name] = {"total": u.total, "used": u.used, "free": u.free}
        except OSError:
            disks[name] = None
    r = rows()
    return page(request, "manage_home.html", disks=disks, jobs={j: jobs.read(j) for j in jobs.JOBS},
                job_names=jobs.JOBS, here=sum(1 for x in r if x["here"] and not x["removed"]),
                total=sum(1 for x in r if not x["removed"]), drive=settings.library_drive_ok())


@app.post("/run/{job}")
def run(job: str):
    if job not in UNITS:
        raise HTTPException(404)
    start(job)
    return RedirectResponse("/", 303)


@app.get("/items", response_class=HTMLResponse)
def items(request: Request, t: str = ""):
    r = [x for x in rows() if not t or x["it"].topic == t]
    return page(request, "manage_items.html", rows=r, t=t)


@app.post("/items/{item_id}/remove")
def remove(item_id: str, delete: str = Form("")):
    it = library.get(item_id)
    if not it:
        raise HTTPException(404)
    if delete:
        fetch.remove_files(it)
    library.remove(item_id)
    start("index")
    return RedirectResponse("/items", 303)


@app.post("/items/{item_id}/restore")
def restore(item_id: str):
    c = library.changes()
    c["removed"] = [i for i in c["removed"] if i != item_id]
    library.save_changes(c)
    return RedirectResponse("/items", 303)


@app.get("/add", response_class=HTMLResponse)
def add_page(request: Request, q: str = ""):
    results, error = [], ""
    if q.strip():
        try:
            have = {i.id for i in library.items(include_removed=True)}
            results = [r | {"have": r["name"] in have} for r in fetch.find(q)]
        except OSError as e:
            error = f"Kiwix's catalog isn't reachable (no internet?): {e}"
    return page(request, "manage_add.html", q=q, results=results, error=error)


@app.post("/add/zim")
def add_zim(name: str = Form(...), topic: str = Form(...), essential: str = Form(""), title: str = Form("")):
    raw = {"zim": name, "topic": topic}
    if essential:
        raw["essential"] = True
    if title:
        raw["title"] = title
    library.add(raw)
    return RedirectResponse("/items?t=" + urllib.parse.quote(topic), 303)


@app.post("/add/link")
def add_link(url: str = Form(...), title: str = Form(...), topic: str = Form(...), kind: str = Form("pdf"),
             match: str = Form(""), print_: str = Form("", alias="print")):
    if kind not in ("pdf", "epub", "book"):
        raise HTTPException(400, "kind")
    raw = {kind: url.strip(), "title": title.strip(), "topic": topic}
    if match.strip():
        raw["match"] = match.strip()
    if print_:
        raw["print"] = True
    library.add(raw)
    return RedirectResponse("/items?t=" + urllib.parse.quote(topic), 303)


@app.post("/add/upload")
async def upload(file: UploadFile = File(...), topic: str = Form(...)):
    if topic not in library.topics():
        raise HTTPException(400, "topic")
    name = re.sub(r"[^\w.\- ]+", "", Path(file.filename or "upload").name).strip() or "upload"
    if Path(name).suffix.lower() not in (".pdf", ".epub", ".txt", ".md"):
        raise HTTPException(400, "Only PDF, EPUB, text or Markdown files.")
    dest = settings.path("docs") / topic / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    dest.chmod(0o644)
    start("index")
    return RedirectResponse("/items?t=" + urllib.parse.quote(topic), 303)
