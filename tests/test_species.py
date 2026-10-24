"""Grading logic for tigerfish.species, with GBIF mocked (no network)."""

import pytest

from tigerfish import species
from tigerfish.species import grade


# ---------- grade(): pure function ----------

@pytest.mark.parametrize("args, expected", [
    # matched, local, regional, effort, global, far
    ((False, 0, 0, 0, 0, None), "GREY"),             # name not in GBIF
    ((True, 5, 50, 10, 1000, None), None),           # seen locally: plausible, even with low effort
    ((True, 0, 0, 2000, 900, 50), "RED"),            # surveyed area, none in region, known elsewhere
    ((True, 0, 12, 2000, 900, None), "ORANGE"),      # none locally, some in region
    ((True, 0, 0, 499, 900, 50), "GREY"),            # area barely surveyed
    ((True, 0, 12, 100, 900, None), "GREY"),         # in region, but local effort too low to judge
    ((True, 0, 0, 2000, 0, 0), "GREY"),              # no records anywhere
    ((True, 0, 0, 214, 1342, 0), "RED"),             # none within FAR_KM, well recorded elsewhere
    ((True, 0, 0, 214, 40, 0), "GREY"),              # far-absent but too few global records
    # regional-effort fallback (local effort < MIN_EFFORT):     ..., far, regional_effort
    ((True, 0, 0, 85, 900, 40, 600), "ORANGE"),      # wider region surveyed, no records there
    ((True, 0, 0, 85, 900, 40, 499), "GREY"),        # wider region thin too
    ((True, 0, 0, 85, 900, 40, None), "GREY"),       # regional effort not looked up
    ((True, 0, 3, 85, 900, None, 600), "GREY"),      # species is in the region: not a finding
    ((True, 0, 0, 85, 0, 0, 600), "GREY"),           # no records anywhere
    ((True, 0, 0, 85, 1342, 0, 600), "RED"),         # far rule still wins
])
def test_grade(args, expected):
    assert grade(*args) == expected


def test_effort_threshold_is_inclusive():
    assert grade(True, 0, 0, species.MIN_EFFORT, 900, 50) == "RED"
    assert grade(True, 0, 0, species.MIN_EFFORT - 1, 900, 50) == "GREY"


def test_far_rule_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(species, "FAR_KM", None)
    assert grade(True, 0, 0, 214, 1342, 0) == "GREY"


# ---------- check_species() with GBIF mocked ----------

MATCH = {"usageKey": 111, "canonicalName": "Testus fakeus", "matchType": "EXACT",
         "status": "ACCEPTED", "rank": "SPECIES", "speciesKey": 111, "species": "Testus fakeus",
         "classKey": 359, "class": "Mammalia", "phylumKey": 44}


def fake_gbif(counts, match=MATCH, countries=("ZA", "MZ")):
    """Build a gbif_get replacement. counts maps (taxonKey, km or None) -> count."""
    calls = []

    def gbif_get(path, **params):
        calls.append((path, params))
        if path == "/species/match":
            return match
        if path == "/enumeration/country":
            return [{"iso2": "ZA", "title": "South Africa"}, {"iso2": "MZ", "title": "Mozambique"}]
        if params.get("facet") == "country":
            return {"count": 0, "facets": [{"counts": [{"name": c} for c in countries]}]}
        km = int(params["geoDistance"].split(",")[2][:-2]) if "geoDistance" in params else None
        return {"count": counts[(params["taxonKey"], km)]}

    return gbif_get, calls


def test_check_species_red_with_evidence(monkeypatch):
    gbif_get, _ = fake_gbif({(111, 100): 0, (111, 500): 0, (359, 100): 2341,
                             (111, None): 900, (111, 3000): 40})
    monkeypatch.setattr(species, "gbif_get", gbif_get)
    r = species.check_species("Testus fakeus", 6.75, 93.83)
    assert r["grade"] == "RED"
    assert (r["local_count"], r["regional_count"], r["effort_count"], r["global_count"]) == \
        (0, 0, 2341, 900)
    assert "0 GBIF records of Testus fakeus within 500 km" in r["evidence"]
    assert "South Africa, Mozambique" in r["evidence"]
    assert "2,341 records of other Mammalia within 100 km" in r["evidence"]
    assert r["evidence"].endswith("Inconsistency flagged, verify.")
    assert r["gbif_links"]["species"] == "https://www.gbif.org/species/111"


def test_check_species_plausible_skips_far_lookup(monkeypatch):
    gbif_get, calls = fake_gbif({(111, 100): 7, (111, 500): 30, (359, 100): 50, (111, None): 900})
    monkeypatch.setattr(species, "gbif_get", gbif_get)
    r = species.check_species("Testus fakeus", 0, 0)
    assert r["grade"] is None and r["far_count"] is None
    assert not any("3000km" in p.get("geoDistance", "") for _, p in calls)


def test_check_species_unmatched_is_grey(monkeypatch):
    gbif_get, _ = fake_gbif({}, match={"matchType": "NONE"})
    monkeypatch.setattr(species, "gbif_get", gbif_get)
    r = species.check_species("Nonexistus nowhere", 0, 0)
    assert r["grade"] == "GREY" and r["gbif_key"] is None
    assert "not found" in r["evidence"]


def test_fish_effort_excludes_classed_records(monkeypatch):
    """Ray-finned fish have no class in GBIF: effort = Chordata minus classed groups."""
    fish = {k: v for k, v in MATCH.items() if k not in ("classKey", "class")}

    def gbif_get(path, **params):
        assert params["taxonKey"] == species.CHORDATA_KEY and params["facet"] == "classKey"
        return {"count": 23584, "facets": [{"counts": [{"name": "212", "count": 23118},
                                                       {"name": "359", "count": 252}]}]}

    monkeypatch.setattr(species, "gbif_get", gbif_get)
    assert species.effort_count(fish, 6.75, 93.83)[0] == 214


def test_gbif_get_caches_and_retries_once(monkeypatch, tmp_path):
    monkeypatch.setattr(species, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(species, "REQUEST_DELAY", 0)
    monkeypatch.setattr(species, "RETRY_DELAY", 0)
    attempts = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"count": 3}

    def get(url, timeout):
        attempts.append(url)
        if len(attempts) == 1:
            raise species.requests.ConnectionError("flaky")
        return Resp()

    monkeypatch.setattr(species.requests, "get", get)
    assert species.gbif_get("/occurrence/search", taxonKey=1)["count"] == 3
    assert species.gbif_get("/occurrence/search", taxonKey=1)["count"] == 3   # from cache
    assert len(attempts) == 2 and len(list(tmp_path.glob("*.json"))) == 1


@pytest.mark.parametrize("title, plain", [
    ("Congo, Democratic Republic of the", "Democratic Republic of the Congo"),
    ("Korea, Republic of", "Republic of Korea"),
    ("India", "India"),
])
def test_plain_country(title, plain):
    assert species.plain_country(title) == plain


def test_regional_effort_threshold_is_inclusive():
    assert grade(True, 0, 0, 85, 900, 40, species.MIN_REGIONAL_EFFORT) == "ORANGE"
    assert grade(True, 0, 0, 85, 900, 40, species.MIN_REGIONAL_EFFORT - 1) == "GREY"


def test_check_species_regional_effort_orange(monkeypatch):
    gbif_get, calls = fake_gbif({(111, 100): 0, (111, 500): 0, (359, 100): 85, (359, 500): 2600,
                                 (111, None): 900, (111, 3000): 40})
    monkeypatch.setattr(species, "gbif_get", gbif_get)
    r = species.check_species("Testus fakeus", 6.75, 93.83)
    assert r["grade"] == "ORANGE"
    assert (r["effort_count"], r["regional_effort_count"]) == (85, 2600)
    assert "Local survey data is thin (85 Mammalia records within 100 km)" in r["evidence"]
    assert "wider 500 km region is surveyed (2,600 Mammalia records)" in r["evidence"]
    assert r["evidence"].endswith("Possible range inconsistency flagged, verify.")


def test_regional_effort_only_fetched_when_local_effort_low(monkeypatch):
    gbif_get, calls = fake_gbif({(111, 100): 0, (111, 500): 4, (359, 100): 2000, (111, None): 900})
    monkeypatch.setattr(species, "gbif_get", gbif_get)
    r = species.check_species("Testus fakeus", 0, 0)
    assert r["grade"] == "ORANGE" and r["regional_effort_count"] is None
    assert not any(p.get("taxonKey") == 359 and "500km" in p.get("geoDistance", "")
                   for _, p in calls)


# ---------- name resolution ----------

def fake_match(responses):
    """gbif_get replacement for /species/match: responses maps (name, verbose) -> dict."""
    def gbif_get(path, **params):
        assert path == "/species/match"
        return responses.get((params["name"], params.get("verbose")), {"matchType": "NONE"})
    return gbif_get


def test_synonym_resolves_to_accepted_species(monkeypatch):
    monkeypatch.setattr(species, "gbif_get", fake_match({("Cervus unicolor", None): {
        "usageKey": 2440949, "matchType": "EXACT", "status": "SYNONYM", "rank": "SPECIES",
        "canonicalName": "Cervus unicolor", "species": "Rusa unicolor", "speciesKey": 7261386}}))
    m, key, accepted, note = species.resolve_name("Cervus unicolor")
    assert (key, accepted) == (7261386, "Rusa unicolor")
    assert "synonym" in note and "Rusa unicolor" in note


def test_typo_corrected_when_unambiguous(monkeypatch):
    tupaia = {"usageKey": 2436112, "matchType": "EXACT", "status": "ACCEPTED", "rank": "SPECIES",
              "canonicalName": "Tupaia nicobarica", "species": "Tupaia nicobarica",
              "speciesKey": 2436112}
    monkeypatch.setattr(species, "gbif_get", fake_match({
        ("Taupaia nicobarica", "true"): {"matchType": "NONE", "alternatives": [
            {"canonicalName": "Tupaia nicobarica", "rank": "SPECIES", "matchType": "FUZZY"}]},
        ("Tupaia nicobarica", None): tupaia}))
    m, key, accepted, note = species.resolve_name("Taupaia nicobarica")
    assert accepted == "Tupaia nicobarica"
    assert 'read as "Tupaia nicobarica"' in note


@pytest.mark.parametrize("alternatives", [
    [{"canonicalName": "Tupaia nicobarica", "rank": "SPECIES"},       # two different candidates
     {"canonicalName": "Tapaia nicobarica", "rank": "SPECIES"}],
    [{"canonicalName": "Tupaia javanica", "rank": "SPECIES"}],        # different epithet
    [{"canonicalName": "Xylophaga nicobarica", "rank": "SPECIES"}],   # too different
    [{"canonicalName": "Tupaia", "rank": "GENUS"}],                   # genus only
])
def test_typo_not_corrected_when_unsafe(monkeypatch, alternatives):
    monkeypatch.setattr(species, "gbif_get", fake_match({
        ("Taupaia nicobarica", "true"): {"matchType": "NONE", "alternatives": alternatives},
        ("Tupaia nicobarica", None): {"usageKey": 1, "speciesKey": 1, "matchType": "EXACT"}}))
    assert species.resolve_name("Taupaia nicobarica") is None


def test_subspecies_checked_at_species_level(monkeypatch):
    monkeypatch.setattr(species, "gbif_get", fake_match({("Sus scrofa andamanensis", None): {
        "usageKey": 7705930, "matchType": "HIGHERRANK", "status": "ACCEPTED", "rank": "SPECIES",
        "canonicalName": "Sus scrofa", "species": "Sus scrofa", "speciesKey": 7705930}}))
    _, key, accepted, note = species.resolve_name("Sus scrofa andamanensis")
    assert (key, accepted) == (7705930, "Sus scrofa")
    assert "species level" in note


def test_genus_only_match_is_not_checked(monkeypatch):
    monkeypatch.setattr(species, "gbif_get", fake_match({("Tupaia sp.", None): {
        "usageKey": 2436100, "matchType": "HIGHERRANK", "rank": "GENUS",
        "canonicalName": "Tupaia"}}))
    assert species.resolve_name("Tupaia sp.") is None


def test_exact_accepted_name_has_no_note(monkeypatch):
    monkeypatch.setattr(species, "gbif_get", fake_match({("Testus fakeus", None): MATCH}))
    assert species.resolve_name("Testus fakeus")[3] is None
