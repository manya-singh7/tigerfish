"""Impossible-species map: flagged species from saved results, GBIF country facets (mocked or
from the committed snapshot), arcs to country centroids. No network."""

import json

from tigerfish import geo, species
from tigerfish.ui import data, species_map

FINDING = {
    "id": "sp-x", "check": "species_range", "grade": "RED",
    "title": "Panulirus interruptus at Campbell Bay (p.954)",
    "quotes": [{"page": 954, "text": "Panulirus interruptus"}],
    "evidence": [
        {"label": "Checked at", "value": "Campbell Bay (7.0, 93.93): continues the table"},
        {"label": "GBIF records of this species", "value": "0 within 100 km, 0 within 500 km, 294,577 worldwide"},
        {"label": "GBIF species page", "value": "Panulirus interruptus", "url": "https://www.gbif.org/species/2221647"}],
}
FACETS = {"2221647": {"total": 294907, "countries": [["US", 293868], ["MX", 761], ["ZZ", 1]]}}


def test_flagged_species_reads_site_grade_and_counts():
    report = {"findings": [FINDING, {**FINDING, "id": "ct-1", "check": "contradiction"}]}
    [s] = species_map.flagged_species(report)
    assert s["taxon_key"] == 2221647 and s["grade"] == "RED" and s["site"] == (7.0, 93.93)
    assert s["place"] == "Campbell Bay" and "294,577 worldwide" in s["gbif_counts"]


def test_site_falls_back_to_geo_distance_link_then_default():
    f = {"evidence": [{"label": "GBIF records near the site", "value": "map",
                       "url": "https://www.gbif.org/occurrence/search?taxon_key=1&geo_distance=6.75,93.83,500km"}]}
    assert species_map.site_of(f) == (6.75, 93.83)
    assert species_map.site_of({"evidence": []}, default=(1.0, 2.0)) == (1.0, 2.0)


def test_arcs_use_centroids_and_list_unknown_countries():
    s = species_map.flagged_species({"findings": [FINDING]})
    rows, unmapped = species_map.arcs(s, FACETS)
    assert [r["iso2"] for r in rows] == ["US", "MX"]
    assert rows[0]["country"] == "United States" and rows[0]["count"] == 293868
    assert unmapped == [("Panulirus interruptus", "ZZ", 1)]


def test_arc_points_start_and_end_on_the_points_and_bend():
    lats, lons = species_map.arc_points((7.0, 93.9), (39.8, -98.6), n=21)
    assert (lats[0], lons[0]) == (7.0, 93.9) and (round(lats[-1], 6), round(lons[-1], 6)) == (39.8, -98.6)
    straight_mid = (7.0 + 39.8) / 2
    assert abs(lats[10] - straight_mid) > 5                  # curved, not a straight line
    assert all(-89 <= y <= 89 for y in lats)


def test_figure_has_site_pin_arcs_and_tooltips():
    s = species_map.flagged_species({"findings": [FINDING]})
    fig = species_map.figure(s, FACETS)
    names = [t.name for t in fig.data]
    assert "Project site" in names
    marker = next(t for t in fig.data if t.name and t.name.startswith("Panulirus"))
    hover = marker.hovertemplate
    assert "Grade" in hover and "GBIF records in" in hover
    assert marker.customdata[0][1].startswith("RED") and marker.customdata[0][3] == "293,868"
    assert sum(1 for t in fig.data if t.mode == "lines") == 2


def test_fetch_facets_uses_gbif_country_facet(monkeypatch):
    calls = []

    def fake(path, **params):
        calls.append((path, params))
        return {"count": 10, "facets": [{"field": "COUNTRY", "counts": [{"name": "IN", "count": 9},
                                                                        {"name": "LK", "count": 1}]}]}
    monkeypatch.setattr(species, "gbif_get", fake)
    assert species_map.fetch_facets(42) == {"total": 10, "countries": [["IN", 9], ["LK", 1]]}
    assert calls[0][0] == "/occurrence/search" and calls[0][1]["facet"] == "country"
    assert calls[0][1]["limit"] == 0


def test_snapshot_covers_every_flagged_species_in_saved_results():
    facets = species_map.load_facets()
    for r in data.reports():
        for s in species_map.flagged_species(data.load(r["id"]), (0.0, 0.0)):
            fc = facets.get(str(s["taxon_key"]))
            assert fc and fc["countries"], s["accepted"]
            assert all(geo.centroid(c) or c == "ZZ" for c, _ in fc["countries"]), s["accepted"]


def test_snapshot_is_plain_json():
    text = species_map.FACETS_FILE.read_text(encoding="utf-8")
    assert "API_KEY" not in text
    assert isinstance(json.loads(text), dict)
