"""Species check on a report's own species tables.

1. species_table_pages: pages with a list header ("Zoological / Scientific / Botanical name")
   or several family names (-idae / -aceae) next to many Latin binomials.
2. Names: on pages with a text layer, binomials are pulled with a regex and each is
   confirmed with GBIF's name matcher (free, cached; no LLM). Scanned pages next to a
   species table (no usable text) are read by SUPER_VL, capped at max_vision pages.
3. Location per table from the page's (and the previous page's) text: the site most
   often named; the island centre if none. The reason is recorded.
4. species.check_species on every name (cached).
"""

import re
from collections import Counter

from tigerfish import claims, species

HEAD = re.compile(r"zoological name|scientific name|botanical name|species name", re.IGNORECASE)
FAMILY = re.compile(r"\b[A-Z][a-z]+(?:idae|aceae)\b")
# Epithets may be hyphenated ("rosa-sinensis"); "hybrid", "sp", "spp" are not species.
BINOMIAL = re.compile(r"\b([A-Z][a-z]{2,})\s(?!hybrid\b|spp?\b)([a-z]{3,}(?:-[a-z]{3,})?)"
                      r"(?:\s(?!var\b|sp\b|ssp\b)([a-z]{4,}))?\b")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
MIN_BINOMIALS_WITH_HEAD = 3
MIN_BINOMIALS_WITH_FAMILIES = 8
MIN_FAMILIES = 3
MIN_CONFIDENCE = 90

# Capitalised English words that the regex would otherwise read as a genus.
NOT_GENERA = set("""The This These Those That There Their Table Figure Fig Source Total Great Nicobar
    Andaman Island Islands India Indian National Park Campbell Galathea Indira Point Bay Port
    Project Area Areas Sanctuary Reserve Biosphere Forest Forests Species Family Common Name
    Status Schedule Category Order Class Annexure Chapter Section Page Report Study Survey
    Similarly However Among About After Before During Since With Without From Into Other
    Some Many Most Several Each Such Also Further Mangrove Mangroves Coral Corals Endemic
    Zoological Scientific Botanical Local Vernacular English Hindi""".split())

SITES = {   # name in text -> (lat, lon)
    "Galathea": (6.82, 93.88), "Campbell Bay": (7.0, 93.93), "Indira Point": (6.75, 93.83),
}
ISLAND_CENTRE = (7.0, 93.85)


def is_species_page(text):
    if not text or DEVANAGARI.search(text):
        return False
    binomials = len(BINOMIAL.findall(text))
    if HEAD.search(text) and binomials >= MIN_BINOMIALS_WITH_HEAD:
        return True
    return len(FAMILY.findall(text)) >= MIN_FAMILIES and binomials >= MIN_BINOMIALS_WITH_FAMILIES


def species_table_pages(pages):
    return [p["page"] for p in pages if is_species_page(p.get("text", ""))]


def scanned_neighbours(pages, table_pages):
    """Scanned pages (little text) right next to a species table: likely its continuation."""
    by = {p["page"]: p for p in pages}
    near = {n + d for n in table_pages for d in (-1, 1)}
    return sorted(n for n in near if n in by and n not in table_pages
                  and "little_text" in (by[n].get("reasons") or [])
                  and by[n].get("image_path"))


def candidate_names(text):
    """Unique 'Genus species' (or trinomial) strings as printed, in order of appearance."""
    out = []
    for g, s, ssp in BINOMIAL.findall(claims.normalize(text)):
        if g in NOT_GENERA:
            continue
        name = f"{g} {s}" + (f" {ssp}" if ssp else "")
        if name not in out:
            out.append(name)
    return out


def confirm(name):
    """GBIF match if it is a real species-level name with the same genus, else None."""
    m = species.match_name(name)
    if m is None or m.get("confidence", 0) < MIN_CONFIDENCE:
        return None
    if m.get("rank") not in ("SPECIES", "SUBSPECIES", "VARIETY", "FORM"):
        return None
    if m.get("kingdom") not in ("Animalia", "Plantae", "Fungi"):
        return None
    genus = (m.get("canonicalName") or "").split(" ")[0].lower()
    if genus != name.split(" ")[0].lower():
        return None
    return m


def location_for(page_no, texts, sites=None, centre=None, centre_label="island centre"):
    """(lat, lon, label, reason) from the site most often named on the page and the page before.
    sites / centre default to the Great Nicobar ones (SITES, ISLAND_CENTRE); other reports
    pass their own (tigerfish/sites.py)."""
    sites = sites or SITES
    centre = centre or ISLAND_CENTRE
    text = " ".join(texts.get(n, "") for n in (page_no - 1, page_no))
    counts = Counter({site: len(re.findall(re.escape(site), text, re.IGNORECASE)) for site in sites})
    site, n = counts.most_common(1)[0]
    if n == 0:
        return (*centre, centre_label, "no site named on this or the previous page")
    others = ", ".join(f"{s} {c}" for s, c in counts.items() if c and s != site)
    reason = f"'{site}' named {n} time(s) on p.{page_no - 1}-{page_no}" + (f" (also: {others})" if others else "")
    return (*sites[site], site, reason)


def table_locations(table_pages, texts, **where):
    """{page: (lat, lon, label, reason)}. Consecutive table pages are one table: they share
    the location found from the table's first page (and the page before it)."""
    out, run_start, run_loc = {}, None, None
    for n in sorted(table_pages):
        if run_start is None or n != prev + 1:              # a new table starts here
            run_start, run_loc = n, location_for(n, texts, **where)
            out[n] = run_loc
        else:
            lat, lon, label, reason = run_loc
            out[n] = (lat, lon, label, f"continues the table from p.{run_start} ({reason})")
        prev = n
    return out


def names_from_vision(page):
    """Species names read by SUPER_VL from a scanned page (cached). [] if no table."""
    table = claims.extract_table_from_image(page["image_path"])
    if not table:
        return []
    return [c["value"] for c in claims.species_claims_from_table(table, source=page["image_path"])]


GBIF_WORKERS = 4    # parallel GBIF requests (each still waits species.REQUEST_DELAY)


def _parallel(fn, items, workers=GBIF_WORKERS):
    """{item: fn(item)} using a few threads; GBIF answers are cached per URL."""
    from concurrent.futures import ThreadPoolExecutor
    items = list(dict.fromkeys(items))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(items, pool.map(fn, items)))


def check_pages(pages, max_vision=10, use_vision=True, workers=GBIF_WORKERS, profile=None):
    """Rows: {page, name, gbif_name, grade, local, regional, far, global, location, reason, via}.
    profile: the report's site profile (tigerfish/sites.py); None = the Great Nicobar defaults."""
    where = ({"sites": profile["sites"], "centre": profile["centre"],
              "centre_label": profile["centre_label"]} if profile else {})
    gadm = profile["archipelago_gadm"] if profile else species.ANDAMAN_NICOBAR_GADM
    texts = {p["page"]: p.get("text", "") for p in pages}
    by = {p["page"]: p for p in pages}
    table_pages = species_table_pages(pages)
    vision_pages = scanned_neighbours(pages, table_pages)[:max_vision] if use_vision else []
    locations = table_locations(table_pages + vision_pages, texts, **where)

    # 1. names per page (GBIF name matching in parallel)
    raw = {n: candidate_names(texts[n]) for n in table_pages}
    confirmed = _parallel(confirm, [name for names in raw.values() for name in names], workers)
    names_by_page = {n: [x for x in raw[n] if confirmed.get(x)] for n in table_pages}
    names_by_page.update({n: names_from_vision(by[n]) for n in vision_pages})

    # 2. one species check per (name, site), in parallel
    jobs = []
    for page_no in sorted(table_pages + vision_pages):
        lat, lon, site, _ = locations[page_no]
        jobs += [(name, lat, lon) for name in names_by_page[page_no]]
    results = _parallel(lambda job: species.check_species(*job, archipelago_gadm=gadm), jobs,
                        workers)

    rows, seen = [], set()
    for page_no in sorted(table_pages + vision_pages):
        lat, lon, site, reason = locations[page_no]
        via = "Super-VL" if page_no in vision_pages else "text + GBIF match"
        for name in names_by_page[page_no]:
            if (name, site) in seen:      # same name at the same site: checked once
                continue
            seen.add((name, site))
            r = results[(name, lat, lon)]
            rows.append({"page": page_no, "name": name, "gbif_name": r["matched_name"],
                         "name_note": r["name_note"], "grade": r["grade"],
                         "local": r["local_count"], "regional": r["regional_count"],
                         "far": r["far_count"], "global": r["global_count"],
                         "class": r["class_name"], "evidence": r["evidence"],
                         "archipelago": r.get("archipelago_count"),
                         "lookup_failed": r.get("lookup_failed", False),
                         "mobile_region": r.get("mobile_region", False),
                         "links": r["gbif_links"], "location": site, "lat": lat, "lon": lon,
                         "reason": reason, "via": via})
    return {"table_pages": table_pages, "vision_pages": vision_pages, "rows": rows,
            "archipelago_rule": gadm}
