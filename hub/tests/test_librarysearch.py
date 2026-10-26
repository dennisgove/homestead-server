from homestead import librarysearch


def test_keywords_simple():
    assert librarysearch.keywords_simple("How do I make water safe to drink?") == "water safe drink"


def test_best_passage_prefers_terms():
    text = ("filler " * 400) + "boil water one minute " + ("filler " * 400)
    p = librarysearch.best_passage(text, ["boil", "water"], size=200)
    assert "boil water" in p


def test_context_falls_back_and_handles_no_server(site):
    out = librarysearch.context("how to treat a burn")
    assert out["sources"] == [] and out["context"] == ""
