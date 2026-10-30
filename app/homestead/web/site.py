"""The website (port 80 through Caddy). Every page and every file is served from this one
address, with links relative to it, so it works by whatever name or IP it's reached.
Nothing here asks for a login.
"""
import html
import json
import time
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import ask, courses, documents, jobs, library, maps, search, settings, zims

HERE = Path(__file__).parent
app = FastAPI(title="Homestead library", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["human"] = jobs.human
templates.env.filters["when"] = lambda t: "never" if not t else time.strftime("%b %d, %H:%M", time.localtime(t))
templates.env.globals["quote"] = lambda s: urllib.parse.quote(s)


FILE_AREAS = ("docs", "courses", "video", "maps", "share")


@app.get("/files/{area}/{rel:path}")
def files(area: str, rel: str):
    """The library's own files (with byte ranges, for video seeking and map tiles). In production
    Caddy serves /files/ itself; this is the same thing, for running the site without Caddy."""
    if area not in FILE_AREAS:
        raise HTTPException(404, "No such file.")
    p = settings.inside(settings.path(area), rel)
    if p is None:
        raise HTTPException(404, "No such file.")
    return FileResponse(p)


def page(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
    s = settings.load()
    base = {"request": request, "site": s["site"], "topics": library.topics(), "path": request.url.path}
    return templates.TemplateResponse(request=request, name=name, context=base | ctx, status_code=status)


def topic_or_404(tid: str) -> dict:
    t = library.topics().get(tid)
    if not t:
        raise HTTPException(404, "There's no such topic.")
    return t


@app.exception_handler(HTTPException)
def not_found(request: Request, exc: HTTPException):
    return page(request, "error.html", status=exc.status_code, message=exc.detail)


# --- home, topics, books ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    shelves = []
    for tid, t in library.topics().items():
        n_docs = len(documents.shelf(tid)) + len(documents.loose(tid))
        n_books = len(zims.books(tid))
        n_courses = len(courses.channels(tid))
        if n_docs or n_books or n_courses or tid == "family":
            shelves.append(t | {"docs": n_docs, "books": n_books, "courses": n_courses})
    return page(request, "home.html", shelves=shelves)


@app.get("/t/{tid}", response_class=HTMLResponse)
def topic(request: Request, tid: str):
    t = topic_or_404(tid)
    return page(request, "topic.html", t=t, docs=documents.shelf(tid), loose=documents.loose(tid),
                books=zims.books(tid), channels=courses.channels(tid))


@app.get("/book/{item_id}", response_class=HTMLResponse)
def book(request: Request, item_id: str):
    d = next((d for d in documents.shelf() if d["item"] == item_id), None)
    if not d:
        raise HTTPException(404, "That book isn't here (yet).")
    it = library.get(item_id)
    return page(request, "book.html", d=d, t=library.topics().get(it.topic, {}))


@app.get("/read/{rel:path}", response_class=HTMLResponse)
def read(request: Request, rel: str):
    f = documents.file_for(rel)
    if not f:
        raise HTTPException(404, "That document isn't here.")
    info = documents.info([rel]).get(rel, {})
    owner = next((i for i in library.items() if i.kind in ("pdf", "epub", "book") and f in i.files()), None)
    title = info.get("title") or (owner.title if owner else f.stem)
    book_title = owner.title if owner and owner.kind == "book" else ""
    t = library.topics().get(rel.split("/", 1)[0], {})
    if f.suffix.lower() == ".epub":
        etitle, chapters = documents.epub(f)
        return page(request, "read_epub.html", title=title or etitle, chapters=chapters, t=t,
                    file=f"/files/docs/{settings.url_path(rel)}")
    nav = None
    if owner and owner.kind == "book":
        d = next((d for d in documents.shelf(owner.topic) if d["item"] == owner.id), None)
        if d:
            urls = [p["url"] for p in d["parts"]]
            here = f"/read/{settings.url_path(rel)}"
            i = urls.index(here) if here in urls else -1
            nav = {"book": d, "prev": d["parts"][i - 1] if i > 0 else None,
                   "next": d["parts"][i + 1] if 0 <= i < len(urls) - 1 else None}
    return page(request, "read_pdf.html", title=title, label=info.get("label", ""), book_title=book_title,
                t=t, nav=nav, file=f"/files/docs/{urllib.parse.quote(rel)}", pages=info.get("pages"))


# --- encyclopedias ----------------------------------------------------------------------------

BAR = """<div id="hs-bar"><style>
#hs-bar{all:initial;display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;padding:8px 14px;
background:#24382a;color:#fff;font:15px/1.3 system-ui,-apple-system,"Segoe UI",Roboto,Ubuntu,sans-serif;
position:sticky;top:0;z-index:2147483647;box-sizing:border-box;width:100%}
#hs-bar *{all:revert;font:inherit;color:inherit;box-sizing:border-box}
#hs-bar a{color:#fff;text-decoration:none}#hs-bar a:hover{text-decoration:underline}
#hs-bar b{font-weight:700}#hs-bar .hs-c{opacity:.8}
#hs-bar form{display:flex;gap:4px;margin:0 0 0 auto;flex:1;min-width:200px;max-width:420px}
#hs-bar input{flex:1;min-width:0;padding:5px 9px;border:0;border-radius:6px;color:#111;background:#fff}
#hs-bar button{padding:5px 10px;border:0;border-radius:6px;background:#e9b949;color:#111;font-weight:700;cursor:pointer}
@media print{#hs-bar{display:none}}</style>
<a href="/"><b>🏡 Library</b></a><span class="hs-c">›</span><a href="/t/{topic}">{topic_name}</a><span class="hs-c">›</span>
<a href="/wiki/{book}/">{title}</a>
<form action="/wiki-search/{book}"><input name="q" type="search" placeholder="Search {title}" aria-label="Search this book">
<button>Search</button></form><a href="/search">Search everything</a></div>"""


def book_or_404(book_id: str) -> zims.Book:
    b = zims.get_book(book_id)
    if not b:
        raise HTTPException(404, "That encyclopedia isn't here (yet).")
    return b


@app.get("/wiki/{book_id}/{zpath:path}")
def wiki(request: Request, book_id: str, zpath: str = ""):
    b = book_or_404(book_id)
    if not zpath:
        return RedirectResponse(f"/wiki/{book_id}/{settings.url_path(zims.main_path(b))}", 302)
    kind, val = zims.entry(b, zpath)
    if kind == "missing":
        raise HTTPException(404, f"That page isn't in {b.title}.")
    if kind == "redirect":
        return RedirectResponse(f"/wiki/{book_id}/{settings.url_path(val)}", 302)
    mime, content, _title = val
    headers = {"Cache-Control": "public, max-age=86400"}
    if mime.startswith("text/html"):
        t = library.topics().get(b.topic, {})
        bar = (BAR.replace("{topic}", b.topic).replace("{topic_name}", html.escape(t.get("name", b.topic)))
               .replace("{book}", html.escape(book_id)).replace("{title}", html.escape(b.title)))
        content = zims.wrap_page(content, bar)
        headers = {"Cache-Control": "no-cache"}
    return Response(content, media_type=mime, headers=headers)


@app.get("/wiki/{book_id}")
def wiki_root(book_id: str):
    return RedirectResponse(f"/wiki/{book_id}/", 302)


@app.get("/wiki-search/{book_id}", response_class=HTMLResponse)
def wiki_search(request: Request, book_id: str, q: str = "", start: int = 0):
    b = book_or_404(book_id)
    res = zims.search_book(b, q, start=start, count=20) if q.strip() else None
    titles = zims.titles(b, q, 5) if q.strip() and start == 0 else []
    return page(request, "wiki_search.html", b=b, q=q, res=res, titles=titles, start=start,
                t=library.topics().get(b.topic, {}))


@app.get("/wiki-icon/{book_id}.png")
def wiki_icon(book_id: str):
    b = book_or_404(book_id)
    data = zims.icon(b)
    if not data:
        raise HTTPException(404, "no icon")
    return Response(data, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})


# --- courses, videos, maps ----------------------------------------------------------------

@app.get("/learn", response_class=HTMLResponse)
def learn(request: Request):
    chans = courses.channels()
    if len(chans) == 1:
        return RedirectResponse(f"/learn/{chans[0].id}", 302)
    return page(request, "learn.html", channels=chans)


@app.get("/learn/{channel}", response_class=HTMLResponse)
@app.get("/learn/{channel}/{node_id}", response_class=HTMLResponse)
def lesson(request: Request, channel: str, node_id: str | None = None):
    if not any(c.id == channel for c in courses.channels()):
        raise HTTPException(404, "That course isn't here.")
    n = courses.node(channel, node_id)
    if not n:
        raise HTTPException(404, "That lesson isn't here.")
    title = next(c.title for c in courses.channels() if c.id == channel)
    return page(request, "lesson.html", n=n, channel_title=title)


VIDEO_EXTS = (".mp4", ".m4v", ".webm", ".mkv", ".mov", ".ogv", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav")


@app.get("/videos", response_class=HTMLResponse)
def videos(request: Request, play: str = ""):
    root = settings.path("video")
    groups: dict[str, list] = {}
    for f in sorted(root.rglob("*")) if root.is_dir() else []:
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS and not f.name.startswith("."):
            rel = f.relative_to(root)
            groups.setdefault(str(rel.parent) if str(rel.parent) != "." else "Videos", []).append(
                {"title": f.stem.replace("_", " ").replace(".", " "), "rel": str(rel), "size": f.stat().st_size,
                 "audio": f.suffix.lower() in (".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav")})
    current = next((v for vs in groups.values() for v in vs if v["rel"] == play), None)
    video_books = [b for b in zims.books() if any(w in b.id for w in ("ted_", "crashcourse", "prepper", "modern-rogue",
                                                                       "crosstalk", "lrnselfreliance"))]
    return page(request, "videos.html", groups=groups, current=current, video_books=video_books)


@app.get("/maps", response_class=HTMLResponse)
def maps_page(request: Request):
    return page(request, "maps.html", info=maps.info(), layers=maps.layers())


# --- search and ask -----------------------------------------------------------------------

@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", t: str = ""):
    tid = t if t in library.topics() else None
    res = search.everything(q, tid) if q.strip() else None
    return page(request, "search.html", q=q, tid=tid, res=res)


@app.get("/ask", response_class=HTMLResponse)
def ask_page(request: Request, q: str = ""):
    return page(request, "ask.html", q=q)


@app.post("/api/ask")
async def api_ask(request: Request):
    body = await request.json()
    q = str(body.get("question", "")).strip()[:2000]
    if not q:
        raise HTTPException(400, "Ask a question.")
    hist = body.get("history") if isinstance(body.get("history"), list) else []
    return StreamingResponse(ask.answer(q, hist), media_type="application/x-ndjson")


@app.get("/api/places")
def api_places(q: str = "", limit: int = 10):
    return maps.places(q, min(limit, 50))


# --- emergency, print, tools, status ------------------------------------------------------

EMERGENCY = [
    ("🩸", "Severe bleeding", "Tourniquet, packing, pressure", "tourniquet hemorrhage"),
    ("❤️", "CPR", "Not breathing, no pulse", "cardiopulmonary resuscitation"),
    ("😮", "Choking", "Abdominal thrusts, babies", "choking"),
    ("🔥", "Burns", "Cool, cover, fluids", "burns"),
    ("🦴", "Broken bones", "Splints, sprains", "fracture splint"),
    ("🥶", "Shock, cold", "Keep warm, lay flat", "shock"),
    ("💧", "Dehydration, diarrhea", "Oral rehydration", "oral rehydration"),
    ("🐍", "Bites and stings", "Snakes, spiders, allergy", "snakebite"),
    ("🤒", "Infection, fever", "Wounds, sepsis", "wound infection"),
    ("🤰", "Childbirth", "Emergency delivery", "childbirth"),
    ("💊", "Medicines", "Doses", "dosage"),
    ("🦷", "Teeth", "Toothache, abscess", "toothache"),
]


@app.get("/emergency", response_class=HTMLResponse)
def emergency(request: Request):
    return page(request, "emergency.html", cards=EMERGENCY, docs=documents.shelf("medical"),
                books=[b for b in zims.books("medical") if b.essential])


@app.get("/print", response_class=HTMLResponse)
def print_page(request: Request):
    docs = [d for d in documents.shelf() if d["print"]]
    return page(request, "print.html", docs=docs, wifi_sign=(settings.path("share") / "print" / "wifi-sign.html").is_file())


@app.get("/tools", response_class=HTMLResponse)
def tools(request: Request):
    host = request.url.hostname or settings.load()["site"]["lan_name"]
    tl = [t | {"url": f"{t.get('scheme', 'http')}://{host}:{t['port']}{t.get('path', '/')}"}
          for t in settings.load().get("tools", [])]
    return page(request, "tools.html", tools=tl, apps=library.phone_apps(), share=_share_files())


def _share_files() -> list[dict]:
    d = settings.path("share")
    out = []
    for f in sorted(d.rglob("*")) if d.is_dir() else []:
        if f.is_file() and not f.name.startswith("."):
            r = str(f.relative_to(d))
            out.append({"name": r, "url": "/files/share/" + urllib.parse.quote(r), "size": f.stat().st_size})
    return out


@app.get("/status", response_class=HTMLResponse)
def status(request: Request):
    disks = {}
    for name, p in (("Internal disk (essentials)", settings.path("core")), ("USB library drive", settings.path("library"))):
        try:
            import shutil
            u = shutil.disk_usage(p)
            disks[name] = {"total": u.total, "used": u.used, "free": u.free,
                           "ok": name.startswith("Internal") or settings.library_drive_ok()}
        except OSError:
            disks[name] = None
    fetch = jobs.read("fetch") or {}
    items = []
    for it in library.items():
        st = fetch.get("items", {}).get(it.id, {})
        items.append({"title": it.title or it.id, "kind": it.kind, "topic": it.topic,
                      "here": it.on_disk(), "state": st.get("state", ""), "note": st.get("note", "")})
    return page(request, "status.html", disks=disks, jobs={j: jobs.read(j) for j in jobs.JOBS}, job_names=jobs.JOBS,
                items=items, power=_power(), backup=_backup(), drive=settings.library_drive_ok(), by_hand=library.by_hand(),
                missing=[i for i in items if not i["here"]])


@app.get("/strip", response_class=HTMLResponse)
def strip(request: Request):
    return page(request, "_strip.html", power=_power(), backup=_backup(), drive=settings.library_drive_ok())


def _power() -> dict | None:
    try:
        p = json.loads(settings.path("power").read_text())
        return p if time.time() - p.get("time", 0) < 600 else None
    except (OSError, ValueError):
        return None


def _backup() -> int | None:
    try:
        return int(settings.path("last_backup").stat().st_mtime)
    except OSError:
        return None
