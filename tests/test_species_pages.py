"""Species-table pages: detection, names, GBIF confirmation, location (GBIF mocked)."""

import pytest

from tigerfish import species_pages as sp

TABLE = ("Table 3.12 List of mammals. Zoological name Family Status "
         "Macaca fascicularis Cercopithecidae VU Sus scrofa Suidae LC "
         "Tupaia nicobarica Tupaiidae EN Crocidura hispida Soricidae VU")
PROSE = ("The island has dense forest. The project area lies near the coast. Some birds "
         "were seen during the survey and Several reptiles were noted.")


def test_detects_species_pages():
    assert sp.is_species_page(TABLE)
    assert not sp.is_species_page(PROSE)
    assert not sp.is_species_page("परियोजना Macaca fascicularis Sus scrofa Zoological name")


def test_candidate_names_skip_english_words():
    names = sp.candidate_names(TABLE + " " + PROSE)
    assert names[:4] == ["Macaca fascicularis", "Sus scrofa", "Tupaia nicobarica",
                         "Crocidura hispida"]
    assert not any(n.split()[0] in ("The", "Some", "Several", "Table") for n in names)


def test_trinomials_kept():
    assert "Sus scrofa andamanensis" in sp.candidate_names("Wild pig Sus scrofa andamanensis Suidae")


@pytest.mark.parametrize("match, ok", [
    ({"usageKey": 1, "confidence": 99, "rank": "SPECIES", "kingdom": "Animalia",
      "canonicalName": "Macaca fascicularis", "matchType": "EXACT"}, True),
    ({"usageKey": 1, "confidence": 80, "rank": "SPECIES", "kingdom": "Animalia",
      "canonicalName": "Macaca fascicularis"}, False),                       # low confidence
    ({"usageKey": 1, "confidence": 99, "rank": "GENUS", "kingdom": "Animalia",
      "canonicalName": "Macaca"}, False),                                     # genus only
    ({"usageKey": 1, "confidence": 99, "rank": "SPECIES", "kingdom": "Animalia",
      "canonicalName": "Mucuna fascicularis"}, False),                        # other genus
    (None, False),
])
def test_confirm(monkeypatch, match, ok):
    monkeypatch.setattr(sp.species, "match_name", lambda name: match)
    assert (sp.confirm("Macaca fascicularis") is not None) is ok


def test_location_from_text_and_default():
    texts = {10: "Survey near Galathea Bay. Galathea river.", 11: TABLE, 20: TABLE}
    lat, lon, label, reason = sp.location_for(11, texts)
    assert (lat, lon, label) == (6.82, 93.88, "Galathea") and "named 2 time(s)" in reason
    assert sp.location_for(20, texts)[2] == "island centre"


def test_table_continuation_shares_location():
    texts = {9: "Campbell Bay forest plots.", 10: TABLE, 11: TABLE, 12: TABLE, 30: TABLE}
    locs = sp.table_locations([10, 11, 12, 30], texts)
    assert locs[11][2] == locs[12][2] == "Campbell Bay"
    assert locs[12][3].startswith("continues the table from p.10")
    assert locs[30][2] == "island centre"                                   # a new table


def test_check_pages_one_check_per_name_and_site(monkeypatch):
    monkeypatch.setattr(sp, "confirm", lambda n: {"ok": True})
    calls = []

    def check(name, lat, lon, archipelago_gadm=None):
        calls.append(name)
        return {"matched_name": name, "name_note": None, "grade": "ORANGE", "local_count": 0,
                "regional_count": 0, "far_count": 3, "global_count": 9, "class_name": "Mammalia",
                "evidence": "e", "gbif_links": {}}

    monkeypatch.setattr(sp.species, "check_species", check)
    pages = [{"page": 10, "text": TABLE, "reasons": []}, {"page": 11, "text": TABLE, "reasons": []}]
    out = sp.check_pages(pages, use_vision=False)
    assert out["table_pages"] == [10, 11]
    assert len(calls) == 4 and len(out["rows"]) == 4        # page 11 repeats page 10's names


def test_hyphenated_epithets_and_non_species():
    names = sp.candidate_names("Shoe flower Hibiscus rosa-sinensis Malvaceae; Citrus hybrid; Ficus sp.")
    assert "Hibiscus rosa-sinensis" in names
    assert not any(n.startswith("Citrus") or n.startswith("Ficus") for n in names)


def test_profile_sets_location_and_turns_off_the_archipelago_rule(monkeypatch):
    """A mainland report (Cuddalore) uses its own site and never the A&N archipelago rule."""
    from tigerfish import sites
    monkeypatch.setattr(sp, "confirm", lambda n: {"ok": True})
    seen = []

    def check(name, lat, lon, archipelago_gadm="unset"):
        seen.append((lat, lon, archipelago_gadm))
        return {"matched_name": name, "name_note": None, "grade": None, "local_count": 5,
                "regional_count": 5, "far_count": None, "global_count": 9,
                "class_name": "Mammalia", "evidence": "e", "gbif_links": {}}

    monkeypatch.setattr(sp.species, "check_species", check)
    prof = sites.profile(sites.CUDDALORE)
    out = sp.check_pages([{"page": 10, "text": TABLE, "reasons": []}], use_vision=False,
                         profile=prof)
    assert seen and all(s == (*prof["site"], None) for s in seen)
    assert out["archipelago_rule"] is None
    assert {r["location"] for r in out["rows"]} == {prof["centre_label"]}
    # Great Nicobar (no profile passed) keeps the A&N rule
    seen.clear()
    sp.check_pages([{"page": 10, "text": TABLE, "reasons": []}], use_vision=False)
    assert all(s[2] == sp.species.ANDAMAN_NICOBAR_GADM for s in seen)
