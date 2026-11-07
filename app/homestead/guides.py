"""The server's own guides (the repo's docs/*.md: restore, grid-down runbook, power, radio...) as PDFs in
the library, so the website shows them, the Print page prints them and the binder list includes them.

Made with markdown-it and WeasyPrint (HTML and CSS to PDF, no browser needed). Only guides that changed
are made again; ones taken out of the repo are taken out of the library too.
"""
import hashlib
import html
import json
from datetime import date
from pathlib import Path

from . import settings

FOLDER = "reference/server"            # under the documents: the Reference shelf
NAMES = {                              # file in the repo -> the name it has in the library
    "README.md": "About this server",
    "RESTORE.md": "Backup and restore guide",
    "GRID-DOWN-RUNBOOK.md": "Grid-down runbook",
    "POWER.md": "Power and batteries",
    "COMMS.md": "Radio and communications guide",
    "SDR-ANTENNA.md": "Radio receiver antenna",
    "INSTALL.md": "Installing the server from scratch",
    "PRINT-BINDER.md": "The printed binder checklist",
}
STYLE = """
@page { size: letter; margin: 0.7in 0.75in 0.8in;
  @bottom-right { content: string(guide) ", page " counter(page) " of " counter(pages); font: 8.5pt "DejaVu Sans", Arial, sans-serif; color: #555; } }
.made { string-set: guide attr(data-guide); }
body { font: 11pt/1.45 "DejaVu Sans", Arial, sans-serif; color: #000; }
h1 { font-size: 20pt; margin: 0 0 4pt; } h2 { font-size: 14pt; margin: 16pt 0 4pt; border-bottom: 1px solid #999; }
h3 { font-size: 12pt; margin: 12pt 0 3pt; } h2, h3 { break-after: avoid; }
.made { color: #555; font-size: 9pt; margin: 0 0 12pt; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: 6pt 0; break-inside: auto; }
th, td { border: 1px solid #999; padding: 3pt 5pt; text-align: left; vertical-align: top; } th { background: #eee; }
tr { break-inside: avoid; }
code { font: 9.5pt "DejaVu Sans Mono", monospace; background: #f2f2f2; padding: 0 2pt; overflow-wrap: anywhere; }
pre { background: #f2f2f2; padding: 6pt 8pt; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; }
pre code { background: none; padding: 0; }
a { color: #000; }
"""


def render(html_text: str, out: Path):
    """One HTML page to a PDF file."""
    import weasyprint
    weasyprint.HTML(string=html_text).write_pdf(out)


def titled(md: str, title: str) -> str:
    """The guide's own first heading becomes its title, so the page says what the binder list, its cover and its
    page numbers call it."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if line.strip():
            if line.startswith("# "):
                lines[i] = f"# {title}"
                return "\n".join(lines) + "\n"
            break
    return f"# {title}\n\n{md}"


def page(md: str, title: str) -> str:
    from markdown_it import MarkdownIt       # CommonMark, as GitHub shows the guides: code blocks inside lists work
    md = titled(md, title)
    body = MarkdownIt("commonmark").enable("table").render(md)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{STYLE}</style></head><body>"
            f'<p class="made" data-guide="{html.escape(title)}">{html.escape(title)} · from the server\'s guides, {date.today():%B %d, %Y}</p>{body}</body></html>')


def make(src: Path | None = None, log=print) -> dict:
    """Bring the guide PDFs up to date. {made: [...], kept: n, removed: [...]}"""
    src = src or settings.path("repo") / "docs"
    out = settings.path("docs") / FOLDER
    out.mkdir(parents=True, exist_ok=True)
    stamp_file = out / ".guides.json"
    try:
        stamps = json.loads(stamp_file.read_text())
    except (OSError, ValueError):
        stamps = {}
    sources = sorted(src.glob("*.md")) + ([src.parent / "README.md"] if (src.parent / "README.md").is_file() else [])
    done = {"made": [], "kept": 0, "removed": []}
    new = {}
    for f in sources:
        name = NAMES.get(f.name, f.stem.replace("-", " ").replace("_", " ").capitalize())
        pdf = out / f"{name}.pdf"
        digest = hashlib.sha256((STYLE + titled(f.read_text(), name)).encode()).hexdigest()
        new[pdf.name] = digest
        if stamps.get(pdf.name) == digest and pdf.is_file():
            done["kept"] += 1
            continue
        tmp = pdf.with_name(f".{pdf.name}.part")
        try:
            render(page(f.read_text(), name), tmp)
        except Exception as e:                     # can't make it this time: keep the one it had, try again next time
            tmp.unlink(missing_ok=True)
            log(f"couldn't make {pdf.name}: {e}")
            if pdf.is_file() and pdf.name in stamps:
                new[pdf.name] = "stale"
            else:
                new.pop(pdf.name)
            continue
        tmp.chmod(0o644)
        tmp.replace(pdf)
        done["made"].append(pdf.name)
        log(f"made {pdf.name}")
    for gone in set(stamps) - set(new):              # taken out of the repo
        (out / gone).unlink(missing_ok=True)
        done["removed"].append(gone)
        log(f"removed {gone}")
    stamp_file.write_text(json.dumps(new, indent=1))
    return done
