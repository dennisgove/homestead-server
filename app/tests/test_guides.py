"""The server's guides (the repo's docs/*.md) made into PDFs for the website and the binder."""
import shutil
from pathlib import Path

from conftest import make_pdf


def fake_render(tmp_path, monkeypatch, works=True):
    """A stand-in for WeasyPrint: keeps the pages it was given, and writes a real one-page PDF."""
    from homestead import guides
    seen = []
    make_pdf(tmp_path / "one.pdf", [(24, "A guide")])

    def render(html_text, out):
        if not works:
            raise OSError("no fonts")
        seen.append(html_text)
        shutil.copy(tmp_path / "one.pdf", out)
    monkeypatch.setattr(guides, "render", render)
    return seen


def test_guides_become_pdfs_in_the_library(site, tmp_path, monkeypatch):
    from homestead import documents, guides
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# The server\n\nWhat it is.")
    (repo / "docs" / "RESTORE.md").write_text("# Restore\n\n| If | Do |\n|---|---|\n| disk died | `borg extract` |\n\n"
                                              "1. Boot it.\n2. Restore:\n   ```bash\n   sudo restore\n   sudo reboot\n   ```\n")
    seen = fake_render(tmp_path, monkeypatch)
    r = guides.make(repo / "docs", log=lambda *a: None)
    out = site["core"] / "docs" / "reference" / "server"
    assert sorted(r["made"]) == ["About this server.pdf", "Backup and restore guide.pdf"]
    pages = " ".join(seen)
    assert "<table>" in pages and "<code>borg extract</code>" in pages
    assert "sudo restore\nsudo reboot" in pages                  # a code block inside a list keeps its lines
    assert any(d["rel"] == "reference/server/Backup and restore guide.pdf" for d in documents.loose())   # on the website
    assert not any(d["rel"].split("/")[-1].startswith(".") for d in documents.loose())

    r = guides.make(repo / "docs", log=lambda *a: None)           # nothing changed: nothing made again
    assert r["made"] == [] and r["kept"] == 2

    (repo / "docs" / "RESTORE.md").write_text("# Restore\n\nChanged.")
    fake_render(tmp_path, monkeypatch, works=False)             # can't make it this time: the old one stays
    r = guides.make(repo / "docs", log=lambda *a: None)
    assert r["made"] == [] and (out / "Backup and restore guide.pdf").is_file()
    fake_render(tmp_path, monkeypatch)
    assert guides.make(repo / "docs", log=lambda *a: None)["made"] == ["Backup and restore guide.pdf"]   # and is made next time

    (repo / "docs" / "RESTORE.md").unlink()                     # taken out of the repo: out of the library
    r = guides.make(repo / "docs", log=lambda *a: None)
    assert r["removed"] == ["Backup and restore guide.pdf"] and not (out / "Backup and restore guide.pdf").exists()
    assert (out / "About this server.pdf").is_file()


def test_every_repo_guide_has_a_name():
    from homestead import guides
    docs = Path(__file__).parents[2] / "docs"
    assert {f.name for f in docs.glob("*.md")} <= set(guides.NAMES)


def test_each_guide_is_headed_with_its_title():
    """The heading on a guide's first page is its title: what the binder list, its cover and its page numbers say."""
    from homestead.guides import titled
    assert titled("# Comms\n\nText\n", "Radio and communications guide") == "# Radio and communications guide\n\nText\n"
    assert titled("\nNo heading\n", "Power and batteries").startswith("# Power and batteries\n\n")
