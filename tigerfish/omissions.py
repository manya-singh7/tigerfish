"""Omissions check: threatened species recorded near the project site that the report
never mentions. Free (GBIF + text search), no LLM; every GBIF answer is cached.

1. recorded_nearby: GBIF occurrence search, facet=speciesKey, around the site at NEAR_KM and
   WIDE_KM, per IUCN category (CR, EN, VU; NT as a lower tier), occurrenceStatus PRESENT,
   no geospatial issues. Per species: records within NEAR_KM since SINCE_YEAR and the latest
   record year (year facet).
2. mentioned: search every page text (and Super-VL table text) for the accepted name, GBIF
   synonyms, genus+species variants (abbreviated genus, joined words, hyphenation) and
   sensible English common names. Records which pages were searched and which had no text.
3. grade: RED  CR/EN with >= RED_MIN_RECORDS records within NEAR_KM since SINCE_YEAR, never mentioned
          ORANGE other CR/EN/VU within WIDE_KM with a record since SINCE_YEAR, never mentioned
          INFO NT, or CR/EN/VU known only from older or undated records, never mentioned
          None  mentioned somewhere in the report
Wording: "Recorded near the project site (GBIF) but not mentioned in the report. Verify
whether it was assessed."
"""

import re

from tigerfish import claims as claims_mod
from tigerfish import species
from tigerfish.species_pages import _parallel

SITE = (6.83, 93.87)            # Galathea Bay
NEAR_KM, WIDE_KM = 10, 25
THREATENED = ("CR", "EN", "VU")
LOWER_TIER = ("NT",)
RED_MIN_RECORDS = 3
SINCE_YEAR = 2000
MIN_TEXT_CHARS = 200            # a page with less text than this counts as "no usable text"
MESSAGE = ("Recorded near the project site (GBIF) but not mentioned in the report. "
           "Verify whether it was assessed.")

# Common names too generic to search for on their own.
GENERIC_COMMON = set("""turtle tortoise frog toad fish shark ray crab shrimp prawn lobster snail
    bird eagle hawk owl gull tern heron egret dove pigeon parrot crow snake lizard gecko skink
    bat rat mouse shrew squirrel deer pig monkey whale dolphin coral tree palm fern orchid
    grass sea marine common""".split())
# Colours are not generic: "Green Turtle" and "Black Kite" name one species each.
MIN_COMMON_CHARS = 6
MIN_SINGLE_WORD_CHARS = 9     # "Curlew" also matches "Curlew Sandpiper" (another bird);
                              # one-word names must be long and specific ("Leatherback")


# ---------- 1. recorded nearby ----------

def _search(**params):
    base = {"limit": 0, "hasCoordinate": "true", "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT"}
    data = species.gbif_get("/occurrence/search", **{**base, **params})
    return data


def species_near(lat, lon, km, category):
    """{speciesKey: record count} of species in an IUCN category within km of a point."""
    data = _search(geoDistance=f"{lat},{lon},{km}km", iucnRedListCategory=category,
                   facet="speciesKey", facetLimit=1000)
    return {int(c["name"]): c["count"] for f in data.get("facets", []) for c in f["counts"]}


def recent_and_latest(key, lat, lon):
    """(records within NEAR_KM since SINCE_YEAR, latest record year within WIDE_KM or None)."""
    recent = _search(taxonKey=key, geoDistance=f"{lat},{lon},{NEAR_KM}km",
                     year=f"{SINCE_YEAR},2100")
    years = _search(taxonKey=key, geoDistance=f"{lat},{lon},{WIDE_KM}km",
                    facet="year", facetLimit=300)
    ys = [int(c["name"]) for f in years.get("facets", []) for c in f["counts"]
          if str(c["name"]).isdigit()]
    return species.checked_count(recent), (max(ys) if ys else None)


def taxon_names(key):
    """(accepted canonical name, [synonym canonical names], [English common names])."""
    info = species.gbif_get(f"/species/{key}")
    syn = species.gbif_get(f"/species/{key}/synonyms", limit=100)
    vern = species.gbif_get(f"/species/{key}/vernacularNames", limit=200)
    synonyms = sorted({s.get("canonicalName") for s in syn.get("results", [])
                       if s.get("canonicalName") and s.get("rank") in ("SPECIES", "SUBSPECIES", None)}
                      - {info.get("canonicalName")})
    common = sorted({v["vernacularName"].strip() for v in vern.get("results", [])
                     if v.get("language") in ("eng", "en") and v.get("vernacularName")})
    return info.get("canonicalName") or info.get("scientificName"), synonyms, sensible_common(common)


def sensible_common(names):
    """Common names specific enough to search for (not 'Turtle', not single colour words)."""
    out = []
    for n in names:
        words = re.findall(r"[a-z]+", n.lower())
        if len(n) < MIN_COMMON_CHARS or not words:
            continue
        if all(w in GENERIC_COMMON for w in words):
            continue
        if len(n.split()) == 1 and len(n) < MIN_SINGLE_WORD_CHARS:
            continue
        out.append(n)
    return [n for n in out if not is_group_name(n, out)]


PLACE_WORDS = set("""nicobar nicobarese andaman andamanese great indian india asian malayan
    malaysian sumatran burmese bengal ceylon oriental""".split())


def is_group_name(name, names):
    """True if `name` is the ending of a longer name of the same species: "Bent-toed Gecko"
    vs "Nicobar Bent-toed Gecko". Such group names fit many species, so they don't count.
    An ending that names a place stays specific: "Nicobar Megapode" (vs "Great Nicobar
    Megapode") still identifies one species."""
    words = name.lower().split()
    if PLACE_WORDS & set(re.findall(r"[a-z]+", name.lower())):
        return False
    return any(len(o.split()) > len(words) and o.lower().split()[-len(words):] == words
               for o in names)


def recorded_nearby(lat=SITE[0], lon=SITE[1]):
    """Species records near the site: [{key, category, near, wide}] (one row per species)."""
    rows = {}
    for cat in THREATENED + LOWER_TIER:
        wide = species_near(lat, lon, WIDE_KM, cat)
        near = species_near(lat, lon, NEAR_KM, cat)
        for key, n in wide.items():
            rows.setdefault(key, {"key": key, "category": cat, "near": near.get(key, 0),
                                  "wide": n})
    return list(rows.values())


# ---------- 2. mentioned in the report? ----------

def search_text(text):
    """Text prepared for name search: lower case, hyphenated line breaks joined, single spaces."""
    t = re.sub(r"(\w)-\s+(\w)", r"\1\2", text or "")
    return " " + " ".join(t.lower().split()) + " "


def name_variants(scientific):
    """Search patterns for a Latin name: full, abbreviated genus, joined, OCR spacing."""
    parts = scientific.lower().split()
    if len(parts) < 2:
        return [scientific.lower()]
    genus, epithet = parts[0], parts[1]
    return list(dict.fromkeys([
        f"{genus} {epithet}",            # Dermochelys coriacea
        f"{genus[0]}. {epithet}",        # D. coriacea
        f"{genus[0]}.{epithet}",         # D.coriacea
        f"{genus}{epithet}",             # Dermochelyscoriacea (OCR lost the space)
        f"{genus} {epithet[:1]} {epithet[1:]}" if len(epithet) > 4 else f"{genus} {epithet}",
    ]))


def mention_patterns(accepted, synonyms, common):
    """[(label, compiled regex)] for everything we search for."""
    pats = []
    for name in [accepted, *synonyms]:
        for v in name_variants(name):
            pats.append((f"scientific: {v}", re.compile(r"(?<![a-z])" + re.escape(v) + r"(?![a-z])")))
    for c in common:
        words = [re.escape(w) for w in c.lower().split()]
        pats.append((f"common: {c}", re.compile(r"(?<![a-z])" + r"[\s-]*".join(words) + r"(?![a-z])")))
    return pats


def find_mentions(patterns, texts):
    """{page: [labels that matched]} over prepared page texts {page: search_text(...)}."""
    hits = {}
    for page, t in texts.items():
        found = [label for label, rx in patterns if rx.search(t)]
        if found:
            hits[page] = found
    return hits


def report_texts(pages, ledger=()):
    """Prepared texts per page (page text + Super-VL claim quotes) and pages with no usable text."""
    vision = {}
    for c in ledger:
        if c.get("model") == "nvidia/Nemotron-3.5-Super-VL":
            vision.setdefault(c["page"], []).append(c["quote"])
    texts, empty = {}, []
    for p in pages:
        raw = (p.get("text") or "") + " " + " ".join(vision.get(p["page"], []))
        if len(claims_mod.normalize(p.get("text") or "")) < MIN_TEXT_CHARS and p["page"] not in vision:
            empty.append(p["page"])
        texts[p["page"]] = search_text(raw)
    return texts, empty


# ---------- 3. grade ----------

def grade(category, near_recent, mentioned, latest_year=None):
    """RED: CR/EN with enough recent records within NEAR_KM. ORANGE: other CR/EN/VU with at
    least one record since SINCE_YEAR within WIDE_KM. Older or undated only -> INFO."""
    if mentioned:
        return None
    if category in ("CR", "EN") and near_recent >= RED_MIN_RECORDS:
        return "RED"
    if category in THREATENED:
        return "ORANGE" if latest_year and latest_year >= SINCE_YEAR else "INFO"
    if category in LOWER_TIER:
        return "INFO"
    return None


def gbif_map_link(key, lat=SITE[0], lon=SITE[1], km=WIDE_KM):
    return (f"https://www.gbif.org/occurrence/search?taxon_key={key}"
            f"&geo_distance={lat},{lon},{km}km&occurrence_status=present")


def check(pages, ledger=(), lat=SITE[0], lon=SITE[1]):
    """Rows for every threatened/NT species recorded near the site, graded."""
    texts, empty = report_texts(pages, ledger)
    near = recorded_nearby(lat, lon)
    details = _parallel(lambda key: (taxon_names(key), recent_and_latest(key, lat, lon)),
                        [r["key"] for r in near])
    rows = []
    for r in near:
        (accepted, synonyms, common), (recent, latest) = details[r["key"]]
        pats = mention_patterns(accepted, synonyms, common)
        hits = find_mentions(pats, texts)
        g = grade(r["category"], recent, bool(hits), latest)
        rows.append({**r, "name": accepted, "synonyms": synonyms, "common": common,
                     "near_since_2000": recent, "latest_year": latest,
                     "mentioned_pages": sorted(hits), "matched": sorted({l for v in hits.values() for l in v}),
                     "searched_for": [label for label, _ in pats], "grade": g,
                     "map": gbif_map_link(r["key"], lat, lon),
                     "message": MESSAGE if g else None})
    order = {"RED": 0, "ORANGE": 1, "INFO": 2, None: 3}
    rows.sort(key=lambda x: (order[x["grade"]], {"CR": 0, "EN": 1, "VU": 2, "NT": 3}[x["category"]],
                             -x["wide"]))
    return {"rows": rows, "pages_searched": len(texts), "pages_without_text": empty,
            "site": (lat, lon)}
