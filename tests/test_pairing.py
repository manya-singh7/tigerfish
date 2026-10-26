"""Keyed pairing (tigerfish/pairing.py): keys are given directly, no model calls."""

from tigerfish import pairing


def claim(cid, page, value, subject, unit="species", ctype="count", source="page"):
    return {"id": cid, "page": page, "type": ctype, "value": value, "unit": unit,
            "subject": subject, "quote": f"{value} {unit} {subject}", "verified": True,
            "source": source}


def key(measure, place="", reading=False, station=""):
    return {"measure": measure, "place": place, "reading": reading, "station": station}


def pairs(claims, keys):
    return list(pairing.keyed_numeric_pairs(claims, keys))


def ids(cands):
    return {frozenset(c["id"] for c in cand["claims"]) for cand in cands}


FAUNA = "fauna species recorded from gni"


def test_repeats_collapse_to_one_representative_with_also_on():
    cl = [claim("a", 10, 330, FAUNA), claim("b", 20, 330, FAUNA), claim("c", 30, 330, FAUNA),
          claim("d", 40, 695, FAUNA)]
    keys = {FAUNA: key("fauna species count", "great nicobar island")}
    [cand] = pairs(cl, keys)
    rep = next(c for c in cand["claims"] if c["value"] == 330)
    assert rep["id"] == "a" and rep["also_on"] == [20, 30]       # earliest page kept


def test_model_claim_preferred_over_rule_claim():
    cl = [claim("r", 5, 330, FAUNA, source="rule"), claim("m", 9, 330, FAUNA),
          claim("x", 12, 695, FAUNA)]
    [cand] = pairs(cl, {FAUNA: key("fauna species count", "great nicobar island")})
    assert {c["id"] for c in cand["claims"]} == {"m", "x"}


def test_different_keys_are_not_paired():
    cl = [claim("a", 1, 330, "fauna species"), claim("b", 2, 97, "bird species")]
    keys = {"fauna species": key("fauna species count", "great nicobar island"),
            "bird species": key("bird species count", "great nicobar island")}
    assert pairs(cl, keys) == []


def test_values_within_five_percent_are_the_same_value():
    cl = [claim("a", 1, 100, FAUNA), claim("b", 2, 103, FAUNA)]
    assert pairs(cl, {FAUNA: key("fauna species count")}) == []


def test_readings_pair_only_same_parameter_and_station():
    s1, s2, s3 = "pm10 at aaq1", "pm10 at aaq1 again", "pm10 at aaq2"
    cl = [claim("a", 1, 40, s1, unit="µg/m3", ctype="quantity"),
          claim("b", 2, 60, s2, unit="µg/m3", ctype="quantity"),
          claim("c", 3, 90, s3, unit="µg/m3", ctype="quantity")]
    keys = {s1: key("pm10 concentration", reading=True, station="aaq1"),
            s2: key("pm10 concentration", reading=True, station="aaq1"),
            s3: key("pm10 concentration", reading=True, station="aaq2")}
    assert ids(pairs(cl, keys)) == {frozenset({"a", "b"})}


def test_reading_without_station_is_not_paired():
    s = "noise level"
    cl = [claim("a", 1, 40, s, unit="dB", ctype="quantity"),
          claim("b", 2, 60, s, unit="dB", ctype="quantity")]
    assert pairs(cl, {s: key("noise level", reading=True)}) == []
    assert pairing.last_stats["readings_without_station"] == 2


def test_part_larger_than_whole_is_paired_but_smaller_part_is_not():
    park, island = "flora species galathea np", "flora species gni"
    keys = {park: key("flora species count", "galathea national park"),
            island: key("flora species count", "great nicobar island")}
    big_part = [claim("p", 851, 648, park), claim("w", 940, 600, island)]
    assert ids(pairs(big_part, keys)) == {frozenset({"p", "w"})}
    small_part = [claim("p", 851, 300, park), claim("w", 940, 600, island)]
    assert pairs(small_part, keys) == []


def test_cap_per_group_keeps_most_alike_and_counts_dropped(monkeypatch):
    monkeypatch.setattr(pairing, "MAX_PAIRS_PER_GROUP", 3)
    cl = [claim(f"c{i}", i, 100 * (i + 1), FAUNA) for i in range(5)]   # 10 pairs
    got = pairs(cl, {FAUNA: key("fauna species count")})
    assert len(got) == 3 and pairing.last_stats["dropped_by_cap"] == 7


def test_missing_key_falls_back_to_subject_words():
    cl = [claim("a", 1, 330, FAUNA), claim("b", 2, 695, FAUNA)]
    assert len(pairs(cl, {})) == 1


def test_place_names_are_normalised():
    assert pairing.norm_place("GNI") == "great nicobar island"
    assert pairing.norm_place("Galathea NP") == "galathea national park"
    assert pairing.norm_measure("Fauna Species Counts") == "fauna species count"


def test_measures_with_an_extra_plain_word_are_compatible_but_not_qualifiers():
    assert pairing.measures_compatible("runway reclamation area", "airport runway reclamation area")
    assert not pairing.measures_compatible("flora species count", "endemic flora species count")
    assert not pairing.measures_compatible("species count", "bird species count")   # generic


def test_project_site_and_island_figures_are_compared():
    a, b = "runway reclamation", "airport runway reclamation"
    cl = [claim("a", 751, 71, a, unit="ha", ctype="area"),
          claim("b", 657, 106, b, unit="ha", ctype="area")]
    keys = {a: key("runway reclamation area", "project site"),
            b: key("airport runway reclamation area", "great nicobar island")}
    assert ids(pairs(cl, keys)) == {frozenset({"a", "b"})}


def test_two_named_places_are_never_paired():
    a, b = "fauna galathea", "fauna campbell"
    cl = [claim("a", 1, 330, a), claim("b", 2, 400, b)]
    keys = {a: key("fauna species count", "galathea national park"),
            b: key("fauna species count", "campbell bay national park")}
    assert pairs(cl, keys) == []


def test_collapse_never_loses_a_cross_page_pair():
    # 23 on p.1117 and p.1168, 34 only on p.1117: the pair must use 23 from p.1168.
    cl = [claim("old", 1117, 23, FAUNA), claim("new", 1117, 34, FAUNA),
          claim("src", 1168, 23, FAUNA)]
    [cand] = pairs(cl, {FAUNA: key("fauna species count", "great nicobar island")})
    assert {c["id"] for c in cand["claims"]} == {"new", "src"}


def test_a_different_quantity_noun_in_the_same_unit_bucket_still_matches():
    # Same bucket (both INR), so "cost" vs "area" is a keying slip.
    assert pairing.measures_compatible("coral restoration cost", "coral restoration area")
    assert not pairing.measures_compatible("e wind frequency", "wnw wind frequency")


def test_census_figure_marked_as_reading_is_still_paired():
    s = "male literacy percentage in study area"
    cl = [claim("a", 1, 63.7, s, unit="%", ctype="quantity"),
          claim("b", 2, 95.55, s, unit="%", ctype="quantity")]
    assert len(pairs(cl, {s: key("male literacy percentage", "study area", reading=True)})) == 1
