"""Omissions check: name matching and grading (offline), plus a live sanity check."""

import json
from pathlib import Path

import pytest

from tigerfish import omissions as om

ROOT = Path(__file__).resolve().parent.parent


def pages_with(*texts):
    return {i: om.search_text(t) for i, t in enumerate(texts, 1)}


def mentioned(accepted, texts, synonyms=(), common=()):
    return om.find_mentions(om.mention_patterns(accepted, list(synonyms), list(common)), texts)


# ---------- name matching ----------

@pytest.mark.parametrize("text", [
    "Nesting by Dermochelys coriacea was recorded.",
    "DERMOCHELYS CORIACEA (Vandelli, 1761)",
    "Leatherbacks (D. coriacea) nest here.",
    "Turtles: Dermochelys\n  coriacea, Chelonia mydas",                  # line break
    "the species Dermo- chelys coriacea is",                             # hyphenated break
    "OCR lost the space: Dermochelyscoriacea nests",
])
def test_scientific_name_variants(text):
    assert mentioned("Dermochelys coriacea", pages_with(text))


def test_synonym_counts_as_mention():
    texts = pages_with("Pompadour green pigeon Treron pompadora was seen.")
    hits = mentioned("Treron chloropterus", texts, synonyms=["Treron pompadora"])
    assert hits == {1: ["scientific: treron pompadora"]}


def test_common_name_counts_as_mention():
    texts = pages_with("A Nicobar Megapode mound was found near the shore.")
    assert mentioned("Megapodius nicobariensis", texts, common=["Nicobar Megapode"])


def test_common_name_with_hyphen_or_space_variants():
    texts = pages_with("Great Nicobar serpent-eagle seen")
    assert mentioned("Spilornis klossi", texts, common=["Great Nicobar Serpent Eagle"])


@pytest.mark.parametrize("text", [
    "Curlew Sandpiper on the mudflat.",          # 'Curlew' alone is not searched
    "Dermochelysx coriacea",                     # no partial-word matches
    "Chelonia mydas only.",
])
def test_no_false_mentions(text):
    common = om.sensible_common(["Curlew", "Eurasian Curlew"])
    assert not mentioned("Numenius arquata", pages_with(text), common=common)
    assert not mentioned("Dermochelys coriacea", pages_with(text))


def test_sensible_common_names():
    names = om.sensible_common(["Turtle", "Green Turtle", "Curlew", "Leatherback",
                                "Sea Turtle", "Red", "Nicobar Megapode"])
    assert names == ["Green Turtle", "Leatherback", "Nicobar Megapode"]


def test_pages_without_text_are_reported():
    pages = [{"page": 1, "text": "x"}, {"page": 2, "text": "A full page. " * 30},
             {"page": 3, "text": ""}]
    ledger = [{"page": 3, "model": "nvidia/Nemotron-3.5-Super-VL", "quote": "Dermochelys coriacea"}]
    texts, empty = om.report_texts(pages, ledger)
    assert empty == [1]                                   # page 3 has Super-VL text
    assert mentioned("Dermochelys coriacea", texts) == {3: ["scientific: dermochelys coriacea"]}


# ---------- grading ----------

@pytest.mark.parametrize("cat, recent, mentioned_, latest, grade", [
    ("CR", 3, False, 2024, "RED"), ("EN", 5, False, 2010, "RED"),
    ("EN", 2, False, 2022, "ORANGE"),                    # too few recent nearby records
    ("VU", 50, False, 2025, "ORANGE"),                   # VU is never RED
    ("VU", 0, False, 1901, "INFO"),                      # only old records
    ("EN", 0, False, None, "INFO"),                      # undated records only
    ("VU", 0, False, 2000, "ORANGE"),                    # 2000 counts as recent
    ("NT", 99, False, 2025, "INFO"),
    ("CR", 99, True, 2025, None), ("NT", 1, True, 2025, None),   # mentioned: not a finding
])
def test_grade(cat, recent, mentioned_, latest, grade):
    assert om.grade(cat, recent, mentioned_, latest) == grade


def test_group_names_do_not_count():
    names = om.sensible_common(["Bent-toed Gecko", "Nicobar Bent-toed Gecko", "Turnstone",
                                "Ruddy Turnstone", "Leatherback", "Leatherback Sea Turtle"])
    assert sorted(names) == ["Leatherback", "Leatherback Sea Turtle", "Nicobar Bent-toed Gecko",
                             "Ruddy Turnstone"]
    texts = pages_with("Two Bent-toed Geckos were found under bark.")
    assert not mentioned("Cyrtodactylus adleri", texts, common=names)
    assert mentioned("Cyrtodactylus adleri", pages_with("the Nicobar Bent-toed Gecko"), common=names)


def test_check_end_to_end(monkeypatch):
    def gbif_get(path, **p):
        if path == "/occurrence/search" and p.get("facet") == "speciesKey":
            if p["iucnRedListCategory"] == "EN":
                return {"facets": [{"counts": [{"name": "1", "count": 9}, {"name": "2", "count": 4}]}]}
            return {"facets": []}
        if path == "/occurrence/search" and p.get("facet") == "year":
            return {"count": 9, "facets": [{"counts": [{"name": "2019", "count": 3}, {"name": "2024", "count": 1}]}]}
        if path == "/occurrence/search":
            return {"count": 4}
        key = path.split("/")[2]
        if path.endswith("/synonyms"):
            return {"results": []}
        if path.endswith("/vernacularNames"):
            return {"results": [{"language": "eng", "vernacularName": "Nicobar Testbird"}]}
        return {"canonicalName": {"1": "Testus absentus", "2": "Testus presentus"}[key]}

    monkeypatch.setattr(om.species, "gbif_get", gbif_get)
    pages = [{"page": 5, "text": "Birds seen: Testus presentus. " * 10}]
    out = om.check(pages)
    rows = {r["name"]: r for r in out["rows"]}
    assert rows["Testus absentus"]["grade"] == "RED"            # EN, 4 recent records, not mentioned
    assert rows["Testus absentus"]["latest_year"] == 2024
    assert rows["Testus presentus"]["grade"] is None and rows["Testus presentus"]["mentioned_pages"] == [5]
    assert rows["Testus absentus"]["message"] == om.MESSAGE


# ---------- live sanity check (from cache) ----------

OMISSIONS = ROOT / "cache" / "findings" / "great_nicobar_2021_draft_eia" / "omissions.json"


@pytest.mark.live
@pytest.mark.skipif(not OMISSIONS.exists(), reason="run scripts/check_omissions.py first")
def test_leatherback_is_mentioned_not_flagged():
    rows = {r["name"]: r for r in json.loads(OMISSIONS.read_text(encoding="utf-8"))["rows"]}
    leatherback = rows["Dermochelys coriacea"]
    assert leatherback["grade"] is None and leatherback["mentioned_pages"]


def test_place_named_endings_stay_specific():
    names = om.sensible_common(["Nicobar Megapode", "Great Nicobar Megapode"])
    assert sorted(names) == ["Great Nicobar Megapode", "Nicobar Megapode"]
    assert mentioned("Megapodius nicobariensis", pages_with("a Nicobar Megapode mound"), common=names)
