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


# ---------- failed lookups are never counts ----------

@pytest.mark.parametrize("reply", [{"count": None}, {}, {"error": "timeout"}, {"count": -1},
                                   {"count": "12"}, None, []])
def test_checked_count_rejects_bad_replies(reply):
    with pytest.raises(species.LookupFailed):
        species.checked_count(reply)


def test_failed_lookup_is_grey_not_zero(monkeypatch):
    def gbif_get(path, **params):
        if path == "/species/match":
            return MATCH
        if params.get("geoDistance", "").endswith(",500km"):
            raise species.requests.ConnectionError("timed out")      # the 500 km count fails
        return {"count": 0 if "geoDistance" in params else 900}

    monkeypatch.setattr(species, "gbif_get", gbif_get)
    r = species.check_species("Testus fakeus", 7.0, 93.85)
    assert r["grade"] == "GREY" and r["lookup_failed"]
    assert r["evidence"].startswith("lookup failed")
    assert r["regional_count"] is None                                 # never filled with 0


def test_error_reply_is_grey(monkeypatch):
    def gbif_get(path, **params):
        return MATCH if path == "/species/match" else {"error": "service unavailable"}
    monkeypatch.setattr(species, "gbif_get", gbif_get)
    assert species.check_species("Testus fakeus", 7.0, 93.85)["grade"] == "GREY"


# ---------- archipelago rule ----------

BIRD = {**MATCH, "class": "Aves", "classKey": 212, "canonicalName": "Testus fakeus"}


def bird_gbif(archipelago):
    def gbif_get(path, **params):
        if path == "/species/match":
            return BIRD
        if path == "/enumeration/country":
            return []
        if params.get("facet") == "country":
            return {"count": 0, "facets": []}
        if params.get("gadmGid") == species.ANDAMAN_NICOBAR_GADM:
            return {"count": archipelago}
        if params["taxonKey"] == 212:
            return {"count": 23000}                       # birds well surveyed
        return {"count": 0 if "geoDistance" in params else 5000}
    return gbif_get


def test_bird_recorded_in_archipelago_is_not_flagged(monkeypatch):
    monkeypatch.setattr(species, "gbif_get", bird_gbif(archipelago=14))
    r = species.check_species("Testus fakeus", 7.0, 93.85)
    assert r["grade"] is None and r["archipelago_count"] == 14
    assert "recorded elsewhere in the Andaman & Nicobar Islands" in r["evidence"]


def test_bird_absent_from_archipelago_stays_flagged(monkeypatch):
    monkeypatch.setattr(species, "gbif_get", bird_gbif(archipelago=0))
    r = species.check_species("Testus fakeus", 7.0, 93.85)
    assert r["grade"] in ("RED", "ORANGE") and r["archipelago_count"] == 0


def test_mammals_keep_the_strict_rule(monkeypatch):
    asked = []

    def gbif_get(path, **params):
        if params.get("gadmGid"):
            asked.append(params)
        return bird_gbif(archipelago=99)(path, **params)

    monkeypatch.setattr(species, "gbif_get", lambda path, **p: (
        {**BIRD, "class": "Mammalia", "classKey": 212} if path == "/species/match" else gbif_get(path, **p)))
    r = species.check_species("Testus fakeus", 7.0, 93.85)
    assert r["grade"] in ("RED", "ORANGE") and not asked          # archipelago never consulted


@pytest.mark.parametrize("m, label, mobile", [
    ({"class": "Aves"}, "Aves", True),
    ({"phylumKey": 44}, "ray-finned fish", True),
    ({"class": "Malacostraca"}, "Malacostraca", True),
    ({"class": "Mammalia", "order": "Cetacea"}, "Mammalia", True),
    ({"class": "Testudines", "family": "Cheloniidae"}, "Testudines", True),
    ({"kingdom": "Plantae", "class": "Magnoliopsida"}, "Magnoliopsida", True),
    ({"class": "Mammalia", "order": "Artiodactyla"}, "Mammalia", False),
    ({"class": "Amphibia"}, "Amphibia", False),
    ({"class": "Squamata", "family": "Agamidae"}, "Squamata", False),
])
def test_is_mobile(m, label, mobile):
    assert species.is_mobile(m, label) is mobile


def test_apply_archipelago():
    assert species.apply_archipelago("RED", True, 3) is None
    assert species.apply_archipelago("ORANGE", True, 0) == "ORANGE"
    assert species.apply_archipelago("RED", False, 3) == "RED"
    assert species.apply_archipelago("GREY", True, 3) == "GREY"


# ---------- mobile species: only absence from the whole region is flagged ----------

@pytest.mark.parametrize("grade_, mobile, regional, far, out", [
    ("ORANGE", True, 3, None, "GREY"),        # records within 500 km
    ("RED", True, 0, 73, "GREY"),             # records within 3,000 km
    ("RED", True, 0, 0, "RED"),               # absent from the whole region: stays RED
    ("RED", False, 0, 73, "RED"),             # mammals etc. keep the strict rule
    ("ORANGE", False, 3, None, "ORANGE"),
    (None, True, 3, 9, None),
])
def test_apply_mobile_region(grade_, mobile, regional, far, out):
    assert species.apply_mobile_region(grade_, mobile, regional, far) == out


def test_mobile_bird_in_wider_region_is_grey(monkeypatch):
    def gbif_get(path, **params):
        if params.get("geoDistance", "").endswith(",3000km"):
            return {"count": 73}
        return bird_gbif(archipelago=0)(path, **params)
    monkeypatch.setattr(species, "gbif_get", gbif_get)
    r = species.check_species("Testus fakeus", 7.0, 93.85)
    assert r["grade"] == "GREY" and r["mobile_region"]
    assert species.MOBILE_REGION_NOTE in r["evidence"]


def test_mobile_bird_absent_from_region_stays_red(monkeypatch):
    monkeypatch.setattr(species, "gbif_get", bird_gbif(archipelago=0))   # 0 within 3,000 km
    assert species.check_species("Testus fakeus", 7.0, 93.85)["grade"] == "RED"


def test_archipelago_rule_off_for_mainland_sites(monkeypatch):
    """archipelago_gadm=None (e.g. Cuddalore): no A&N lookup; the mobile-taxa rule still
    applies, and the evidence does not mention the islands."""
    asked = []
    inner = bird_gbif(archipelago=14)

    def gbif_get(path, **params):
        asked.append(params.get("gadmGid"))
        return inner(path, **params)

    monkeypatch.setattr(species, "gbif_get", gbif_get)
    r = species.check_species("Testus fakeus", 11.7, 79.78, archipelago_gadm=None)
    assert species.ANDAMAN_NICOBAR_GADM not in asked
    assert r["archipelago_count"] is None
    assert "Andaman" not in r["evidence"]
