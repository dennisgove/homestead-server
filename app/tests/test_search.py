import json
import os

import numpy as np
import pytest

from homestead import documents, fetch, search, semantic, settings, terms, zims


def test_synonyms_make_one_query():
    assert terms.fts("canning green beans") == '("canning" OR "bottling") ("green beans" OR "snap beans" OR "string beans")'
    assert terms.fts("splint arm") == '"splint" "arm"*'
    assert terms.fts("tq", any_word=True) == '("tq" OR "tourniquet")'
    assert terms.variants("splint arm") == ["splint arm"]      # no synonyms: exactly as typed
    assert terms.variants("broken bone splint") == ["broken bone splint", "fracture splint"]
    assert terms.variants("canning snap beans") == ["canning snap beans", "bottling snap beans", "canning green beans"]
    assert "tourniquet" in terms.every_word("tq")


def test_synonym_list_is_sound():
    for phrase, group in terms.groups().items():
        assert phrase and phrase in group and all(w not in terms.STOP for w in phrase)


def test_synonyms_find_documents_and_encyclopedia_pages(indexed):
    assert {d["path"] for d in documents.search("tq")} == {"medical/stop-the-bleed.pdf", "medical/field-doctor/en_fd_gloss.pdf"}
    groups = zims.search_all("fracture")      # the page says "broken bone"
    assert groups and groups[0]["hits"][0]["path"] == "Splints"


def test_fuse_puts_pages_both_lists_agree_on_first():
    assert search.fuse(["a", "b", "c"], ["c", "d"])[0] == "c"
    assert set(search.fuse(["a"], ["b"])) == {"a", "b"}


CONCEPTS = {"bone": ["bone", "splint", "limb", "break", "fractur", "immobiliz"], "burn": ["burn", "scald"],
            "bleed": ["bleed", "tourniquet", "band"], "math": ["fraction", "subtract", "arithmetic", "sum"],
            "home": ["oak", "house", "meet"]}


def fake_embed(texts, timeout=600, threads=None):
    """Numbers that stand for which of a few ideas a text is about, like a real model's."""
    rows = []
    for t in texts:
        low = t.split("text:", 1)[-1].lower() if "text:" in t else t.lower()
        rows.append([sum(low.count(s) for s in stems) for stems in CONCEPTS.values()] + [0.05])
    v = np.asarray(rows, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


@pytest.fixture
def meaning(site, monkeypatch):
    path = os.environ["HOMESTEAD_SETTINGS"]
    cfg = json.loads(open(path).read())
    cfg["ai"]["embed"] = "embeddinggemma"
    open(path, "w").write(json.dumps(cfg))
    settings.reset()
    monkeypatch.setattr(semantic, "embed", fake_embed)
    monkeypatch.setattr(semantic, "MIN_TEXT", 10)     # the test pages are short
    semantic.reset()
    fetch.index()
    yield site
    semantic.reset()


def test_meaning_finds_pages_without_the_words(meaning):
    res = search.everything("how do I immobilize an injured leg")
    assert res["documents"] and res["documents"][0]["path"] == "medical/field-doctor/en_fd_02.pdf"
    assert not res["loose"]
    assert search.everything("arithmetic")["lessons"][0]["title"].endswith("fractions")


def test_meaning_index_only_does_new_work(meaning, monkeypatch):
    calls = []
    monkeypatch.setattr(semantic, "embed", lambda texts, **k: calls.append(texts) or fake_embed(texts))
    assert semantic.build(log=lambda m: None) == {"pages": 0, "lessons": 0}
    assert calls == []
    # a changed document is done again; the rest isn't
    (meaning["core"] / "docs" / "family" / "our-plan.txt").write_text("Meet at the house on the hill.")
    documents.build(log=lambda m: None)
    assert semantic.build(log=lambda m: None)["pages"] == 1
    assert len(calls) == 1 and "hill" in calls[0][0]


def test_search_carries_on_when_the_ai_engine_is_off(meaning, monkeypatch):
    def off(*a, **k):
        raise ConnectionRefusedError
    monkeypatch.setattr(semantic, "embed", off)
    res = search.everything("splint limb")
    assert res["documents"][0]["path"] == "medical/field-doctor/en_fd_02.pdf"
    assert search.everything("how do I immobilize an injured leg")["documents"] == []
