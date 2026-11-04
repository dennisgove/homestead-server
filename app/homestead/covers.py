"""The binder covers: one page per binder for its clear front sleeve, saying what's in it.

Kept as PDFs in the documents (reference/binder-covers, which the website can write to), so each binder's
list starts with its cover and prints it like anything else: Quick print, the print form, PDF. A cover is
made again only when what's on it changes, and that new file is what marks it "print again".
"""
import hashlib
import html
import json
import os
import re
from pathlib import Path

from . import settings

FOLDER = "reference/binder-covers"
WEB = Path(__file__).parent / "web"
PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>'
        '<style>@page {{ size: letter; margin: .5in; }} body {{ margin: 0; font-family: "DejaVu Sans", Arial, sans-serif; }}</style>'
        '</head><body>{body}</body></html>')


EXTRA = ""


def name(b: dict) -> str:
    """The cover's file, named for its binder ("Maps: routes" makes "Maps - routes cover.pdf")."""
    return re.sub(r'\s*[\\/:*?"<>|]+\s*', " - ", b.get("binder", "")).strip(" -") + " cover.pdf"


def rel(b: dict) -> str:
    return f"{FOLDER}/{name(b)}"


def wanted(b: dict) -> bool:
    """Binders that go in a binder get a cover (not the full-size sheets, not the leftovers list)."""
    return bool(b.get("sheets")) and not b.get("extra")


def print_css() -> str:
    """The site's print styles (where the cover's look is), without the screen ones WeasyPrint has no use for."""
    css = (WEB / "static" / "site.css").read_text()
    colours = "\n".join(line for line in css.splitlines() if line.startswith(".spine-"))   # the label colours
    start = css.index("@media print {")
    i, depth = css.index("{", start), 0
    for j in range(i, len(css)):
        depth += {"{": 1, "}": -1}.get(css[j], 0)
        if depth == 0:
            return colours + "\n" + css[i + 1:j] + EXTRA
    return colours + "\n" + css[i + 1:] + EXTRA


def make(binders: list[dict], log=lambda m: None) -> list[str]:
    """Bring the covers up to date with the binder list; returns the names made. Quietly does nothing
    if the folder isn't there or can't be written (the rows then say the cover isn't made yet)."""
    out = settings.path("docs") / FOLDER
    if not out.is_dir() or not os.access(out, os.W_OK):
        return []
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    env = Environment(loader=FileSystemLoader(WEB / "templates"), autoescape=select_autoescape(["html"]))
    css = print_css()
    stamp_file = out / ".covers.json"
    try:
        stamps = json.loads(stamp_file.read_text())
    except (OSError, ValueError):
        stamps = {}
    new, made = {}, []
    for b in binders:
        if not wanted(b):
            continue
        page = PAGE.format(title=html.escape(name(b).removesuffix(".pdf")),
                           body=env.get_template("binder_cover.html").render(b=b))
        digest = hashlib.sha256((css + page).encode()).hexdigest()
        pdf = out / name(b)
        new[pdf.name] = digest
        if stamps.get(pdf.name) == digest and pdf.is_file():
            continue
        import weasyprint
        tmp = out / f".{pdf.name}.{os.getpid()}.part"
        try:
            weasyprint.HTML(string=page, base_url=str(WEB)).write_pdf(tmp, stylesheets=[weasyprint.CSS(string=css)])
            tmp.chmod(0o644)
            tmp.replace(pdf)
            made.append(pdf.name)
            log(f"made {pdf.name}")
        except Exception as e:                      # keep the old one and try again next time
            tmp.unlink(missing_ok=True)
            log(f"couldn't make {pdf.name}: {e}")
            new[pdf.name] = stamps.get(pdf.name, "")
    for f in out.glob("*.pdf"):                     # binders that aren't there any more (the folder is only covers)
        if f.name not in new:
            f.unlink(missing_ok=True)
    stamp_file.write_text(json.dumps(new, indent=1))
    return made
