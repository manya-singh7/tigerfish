""""Impossible species" world map: a pin at the project site and an arc from it to each country
where a flagged species is recorded in GBIF (country facet -> approximate country centroid).

Replay data only: the flagged species, their grades and their GBIF counts come from the saved
report in results/; the per-country counts come from data/gbif_country_facets.json (written by
scripts/species_map.py from cached GBIF calls). Nothing here calls a model or Tavily.
"""

import json
import math
import re
from pathlib import Path

from tigerfish import geo

ROOT = Path(__file__).resolve().parents[2]
FACETS_FILE = ROOT / "data" / "gbif_country_facets.json"
TOP_COUNTRIES = 8
SPECIES_CHECKS = ("species_range",)

# Muted field-notebook inks (docs/DESIGN.md: no rainbow accents), fixed order, never cycled;
# each species also has its own legend entry and hover label.
SERIES = ["#0D4242", "#A86B12", "#8E3B2A", "#3E6178", "#5F6E26", "#7A5C48"]
SITE_COLOR = "#17302F"
PAPER, PAPER_2, RULE = "#FAF6EC", "#F2ECDF", "#CFC6B3"
FONT = "Schibsted Grotesk, sans-serif"
GRADE_LABEL = {"RED": "RED (strong)", "ORANGE": "ORANGE (likely)"}

_LATLON = re.compile(r"\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)")
_GEO_DISTANCE = re.compile(r"geo_distance=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
_TAXON = re.compile(r"gbif\.org/species/(\d+)")


def _ev(finding, label_start):
    return next((e for e in finding["evidence"] if e["label"].startswith(label_start)), None)


def site_of(finding, default=None):
    """(lat, lon) the species was checked at: 'Checked at ... (7.0, 93.93)', else a GBIF
    geo_distance link, else `default`."""
    e = _ev(finding, "Checked at")
    if e and (m := _LATLON.search(str(e.get("value", "")))):
        return float(m.group(1)), float(m.group(2))
    for e in finding["evidence"]:
        if m := _GEO_DISTANCE.search(e.get("url") or ""):
            return float(m.group(1)), float(m.group(2))
    return default


def flagged_species(report, default_site=None):
    """[{finding_id, name, accepted, taxon_key, grade, gbif_counts, site, place}] for the report's
    species-out-of-range findings that have a GBIF taxon key."""
    out = []
    for f in report["findings"]:
        if f["check"] not in SPECIES_CHECKS:
            continue
        page = _ev(f, "GBIF species page")
        m = _TAXON.search((page or {}).get("url") or "")
        if not m:
            continue
        counts = _ev(f, "GBIF records of this species")
        quote = f["quotes"][0]
        place = f["title"].split(" at ", 1)[1] if " at " in f["title"] else ""
        place = re.sub(r"\s*\(p\.\d+\)$", "", place)          # "Campbell Bay (p.954)" -> "Campbell Bay"
        out.append({"finding_id": f["id"], "name": quote["text"], "accepted": page["value"],
                    "taxon_key": int(m.group(1)), "grade": f["grade"],
                    "gbif_counts": counts["value"] if counts else "",
                    "site": site_of(f, default_site), "place": place})
    return out


def load_facets(path=FACETS_FILE):
    """{taxon_key (str): {"total": n, "countries": [[iso2, n], ...]}} from the snapshot."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def fetch_facets(taxon_key, n=TOP_COUNTRIES):
    """GBIF country facet for one taxon (cached under cache/gbif by species.gbif_get)."""
    from tigerfish import species
    d = species.gbif_get("/occurrence/search", taxonKey=taxon_key, limit=0, facet="country",
                         facetLimit=n)
    return {"total": d.get("count", 0),
            "countries": [[c["name"], c["count"]] for f in d.get("facets", []) for c in f["counts"]][:n]}


def arcs(species_list, facets):
    """One row per (species, country) with a known centroid, and the countries left off the map.
    Row: {species, accepted, grade, gbif_counts, iso2, country, count, lat, lon, site}."""
    rows, unmapped = [], []
    for s in species_list:
        fc = facets.get(str(s["taxon_key"])) or {}
        for iso2, n in fc.get("countries", [])[:TOP_COUNTRIES]:
            c = geo.centroid(iso2)
            if c is None:
                unmapped.append((s["accepted"], iso2, n))
                continue
            rows.append({"species": s["name"], "accepted": s["accepted"], "grade": s["grade"],
                         "gbif_counts": s["gbif_counts"], "iso2": iso2, "country": c[0],
                         "count": n, "lat": c[1], "lon": c[2], "site": s["site"]})
    return rows, unmapped


def arc_points(start, end, n=40, bend=0.18):
    """A curved path from start to end, (lats, lons), as a quadratic Bezier in lat/lon space.
    Short steps keep Plotly's great-circle segments straight, so arcs never wrap off the map."""
    (y0, x0), (y2, x2) = start, end
    dx, dy = x2 - x0, y2 - y0
    cx, cy = (x0 + x2) / 2 - dy * bend, (y0 + y2) / 2 + dx * bend    # bend to the left
    ts = [i / (n - 1) for i in range(n)]
    lats = [(1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y2 for t in ts]
    lons = [(1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x2 for t in ts]
    return [max(-89.0, min(89.0, y)) for y in lats], lons


def _width(n):
    return round(1 + 1.2 * math.log10(max(n, 1)), 2)        # 1 record -> 1px, 100k -> 7px


def figure(species_list, facets, title=None, height=430):
    """Plotly geo figure: site pin(s), arcs to recorded countries, hover with species, grade,
    GBIF counts. Colour follows the species (fixed order)."""
    import plotly.graph_objects as go

    rows, _ = arcs(species_list, facets)
    fig = go.Figure()
    color = {}
    for s in species_list:
        color.setdefault(s["accepted"], SERIES[len(color) % len(SERIES)] if len(color) < len(SERIES)
                         else "#59625F")      # more than six species fold into grey
    for r in rows:
        lats, lons = arc_points(r["site"], (r["lat"], r["lon"]))
        fig.add_trace(go.Scattergeo(
            lat=lats, lon=lons, mode="lines",
            line={"width": _width(r["count"]), "color": color[r["accepted"]]}, opacity=0.75,
            legendgroup=r["accepted"], showlegend=False, hoverinfo="skip"))
    for s in species_list:
        mine = [r for r in rows if r["accepted"] == s["accepted"]]
        if not mine:
            continue
        name = s["accepted"] if s["accepted"] == s["name"] else f"{s['name']} ({s['accepted']})"
        fig.add_trace(go.Scattergeo(
            lat=[r["lat"] for r in mine], lon=[r["lon"] for r in mine], mode="markers",
            marker={"size": [8 + 2 * math.log10(max(r["count"], 1)) for r in mine],
                    "color": color[s["accepted"]], "line": {"width": 2, "color": PAPER}},
            name=f"{name} · {s['grade']}", legendgroup=s["accepted"],
            customdata=[[name, GRADE_LABEL.get(s["grade"], s["grade"]), r["country"],
                         f"{r['count']:,}", s["gbif_counts"]] for r in mine],
            hovertemplate=("<b>%{customdata[0]}</b><br>Grade: %{customdata[1]}<br>"
                           "GBIF records in %{customdata[2]}: %{customdata[3]}<br>"
                           "Near the site: %{customdata[4]}<extra></extra>")))
    sites = {s["site"]: s["place"] for s in species_list if s["site"]}
    fig.add_trace(go.Scattergeo(
        lat=[p[0] for p in sites], lon=[p[1] for p in sites], mode="markers+text",
        marker={"size": 15, "symbol": "star", "color": SITE_COLOR, "line": {"width": 2, "color": PAPER}},
        text=[f"Project site: {name}" if name else "Project site" for name in sites.values()],
        textposition="bottom center", textfont={"color": SITE_COLOR, "size": 13},
        name="Project site", hovertemplate="%{text}<br>%{lat:.2f}, %{lon:.2f}<extra></extra>"))
    fig.update_geos(projection_type="natural earth", showcountries=True, countrycolor=RULE,
                    showland=True, landcolor=PAPER_2, showocean=True, oceancolor=PAPER,
                    coastlinecolor=RULE, showframe=False, bgcolor=PAPER)
    fig.update_layout(height=height, margin={"l": 0, "r": 0, "t": 40 if title else 10, "b": 0},
                      title={"text": title, "x": 0.01, "font": {"size": 16, "color": SITE_COLOR}} if title else None,
                      legend={"orientation": "h", "y": -0.02, "font": {"color": SITE_COLOR}},
                      paper_bgcolor=PAPER, font={"family": FONT, "color": SITE_COLOR},
                      hoverlabel={"font": {"family": FONT}})
    return fig


def render(report, default_site=None):
    """Streamlit section for the species findings. Returns True if a map was drawn."""
    import streamlit as st
    species_list = flagged_species(report, default_site)
    if not species_list:
        return False
    facets = load_facets()
    rows, unmapped = arcs(species_list, facets)
    st.markdown("#### Where the flagged species are actually recorded")
    if not rows:
        st.caption("No GBIF country data saved for these species (run scripts/species_map.py).")
        return False
    st.plotly_chart(figure(species_list, facets), width="stretch", theme=None,
                    config={"displayModeBar": False})
    note = (f"Arcs go from the project site to the {TOP_COUNTRIES} countries with the most GBIF "
            "records of each species (country centre, approximate). Line width grows with the "
            "number of records. GBIF records include introduced and captive populations, and "
            "absence of records is not proof of absence.")
    if unmapped:
        note += " Not drawn: " + ", ".join(
            f"{a}, {n:,} record(s) " + ("with no country recorded" if c == "ZZ" else f"in {c}")
            for a, c, n in unmapped) + "."
    st.caption(note)
    return True
