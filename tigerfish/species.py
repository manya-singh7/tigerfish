"""Species plausibility check against GBIF occurrence records (free API, no key).

check_species("Hydrocynus vittatus", 6.75, 93.83) asks GBIF:
  local    = records of this species within LOCAL_KM of the site
  regional = records of this species within REGIONAL_KM
  effort   = records of the whole taxonomic class within LOCAL_KM (is the area surveyed at all?)
  regional effort = records of the class within REGIONAL_KM (only asked when effort is low)
  global   = records of this species anywhere
  far      = records of this species within FAR_KM (only asked when local and regional are 0)
and grades the claim RED / ORANGE / GREY / None (None = plausible, not a finding).

Names are resolved with the GBIF backbone: synonyms go to the accepted species
(Cervus unicolor -> Rusa unicolor), subspecies are checked at species level, and
an unambiguous one-letter-style typo is corrected (Taupaia -> Tupaia). Any such
change is explained in result["name_note"].

Every GBIF response is cached in cache/gbif/, keyed by URL, so no URL is fetched twice.
"""

import difflib
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from tigerfish import trace

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "gbif"
API = "https://api.gbif.org/v1"
CHORDATA_KEY = 44

# Thresholds: tune here.
LOCAL_KM = 100
REGIONAL_KM = 500
MIN_EFFORT = 500            # class records within LOCAL_KM needed before absence means anything
MIN_REGIONAL_EFFORT = 500   # fallback when local effort is low: class records within REGIONAL_KM
FAR_KM = 3000               # no records within this distance = wrong continent/ocean basin...
MIN_GLOBAL_FAR = 100        # ...if the species is well recorded elsewhere: RED even when local
                            # effort is low. Set FAR_KM = None to turn this rule off.
MIN_NAME_SIMILARITY = 0.85  # accept a GBIF fuzzy name correction only if this similar
TOP_COUNTRIES = 3           # countries named in the evidence sentence

REQUEST_DELAY = 0.3         # seconds before each uncached request (be polite to GBIF)
RETRY_DELAY = 2.0
TIMEOUT = 30


# ---------- GBIF access (cached) ----------

def gbif_get(path, **params):
    """GET {API}{path}?params as JSON. Cached by URL; one retry on error."""
    url = f"{API}{path}?{urlencode(sorted(params.items()))}"
    cache = CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
    trace.record("gbif", cache)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["data"]

    for attempt in (1, 2):
        time.sleep(REQUEST_DELAY)
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            break
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
            time.sleep(RETRY_DELAY)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"url": url, "data": data}, ensure_ascii=False), encoding="utf-8")
    return data


def match_name(scientific_name):
    """GBIF backbone match, or None if GBIF does not know the name."""
    m = gbif_get("/species/match", name=scientific_name)
    if m.get("matchType") == "NONE" or "usageKey" not in m:
        return None
    return m


def fuzzy_candidate(scientific_name):
    """A single close spelling GBIF suggests for an unmatched name, else None.

    Only accepted when there is exactly one species-level suggestion, the epithet
    after the genus is identical, and the whole name is MIN_NAME_SIMILARITY similar.
    """
    m = gbif_get("/species/match", name=scientific_name, verbose="true")
    epithet = scientific_name.split()[1:]
    names = {a["canonicalName"] for a in m.get("alternatives", [])
             if a.get("canonicalName") and a.get("rank") in ("SPECIES", "SUBSPECIES")
             and a["canonicalName"].split()[1:] == epithet
             and difflib.SequenceMatcher(None, a["canonicalName"].lower(),
                                         scientific_name.lower()).ratio() >= MIN_NAME_SIMILARITY}
    return names.pop() if len(names) == 1 else None


def resolve_name(scientific_name):
    """Match a name to an accepted GBIF species.

    Returns (match dict, species key, accepted species name, note) or None.
    note is None when the name was used as given, else a plain-English explanation.
    """
    notes = []
    m = match_name(scientific_name)
    if m is None:
        corrected = fuzzy_candidate(scientific_name)
        if corrected is None:
            return None
        m = match_name(corrected)
        if m is None:
            return None
        notes.append(f'"{scientific_name}" is not in GBIF; read as "{corrected}" '
                     f"(close spelling, verify)")
    key = m.get("speciesKey")
    if key is None:  # matched above species level, e.g. genus only: too vague to check
        return None
    accepted = m.get("species") or m.get("canonicalName")
    if m.get("status") == "SYNONYM":
        notes.append(f'"{m.get("canonicalName")}" is a synonym; GBIF accepted name is {accepted}')
    if m.get("matchType") == "HIGHERRANK" or m.get("rank") not in (None, "SPECIES"):
        notes.append(f'"{scientific_name}" checked at species level as {accepted}')
    return m, key, accepted, "; ".join(notes) or None


def count(taxon_key, lat=None, lon=None, km=None):
    """Number of georeferenced occurrence records for a taxon (optionally near a point)."""
    params = {"taxonKey": taxon_key, "limit": 0, "hasCoordinate": "true",
              "hasGeospatialIssue": "false"}
    if km is not None:
        params["geoDistance"] = f"{lat},{lon},{km}km"
    return gbif_get("/occurrence/search", **params)["count"]


def effort_count(m, lat, lon, km=LOCAL_KM):
    """Sampling effort near the site: records of the species' class within km.

    GBIF's backbone has no class for ray-finned fish (their orders sit directly
    under Chordata). For those, effort = Chordata records with no class, i.e.
    Chordata total minus every classed group (birds, mammals, ...). Using all
    Chordata would mostly count bird records and overstate fish surveys.
    Returns (count, label for the evidence sentence).
    """
    if "classKey" in m:
        return count(m["classKey"], lat, lon, km), m.get("class", "the same class")
    if m.get("phylumKey") == CHORDATA_KEY:
        data = gbif_get("/occurrence/search", taxonKey=CHORDATA_KEY, limit=0,
                        hasCoordinate="true", hasGeospatialIssue="false",
                        geoDistance=f"{lat},{lon},{km}km", facet="classKey", facetLimit=200)
        classed = sum(c["count"] for f in data.get("facets", []) for c in f["counts"])
        return data["count"] - classed, "ray-finned fish"
    if "phylumKey" in m:
        return count(m["phylumKey"], lat, lon, km), m.get("phylum", "the same phylum")
    return 0, "the same group"


def top_countries(taxon_key, n=TOP_COUNTRIES):
    """Names of the countries with the most records of this taxon."""
    data = gbif_get("/occurrence/search", taxonKey=taxon_key, limit=0, hasCoordinate="true",
                    facet="country", facetLimit=n)
    codes = [c["name"] for f in data.get("facets", []) for c in f["counts"]][:n]
    names = {c["iso2"]: plain_country(c["title"]) for c in gbif_get("/enumeration/country")}
    return [names.get(code, code) for code in codes]


def plain_country(title):
    """'Congo, Democratic Republic of the' -> 'Democratic Republic of the Congo'."""
    if ", " in title:
        name, prefix = title.split(", ", 1)
        return f"{prefix} {name}"
    return title


def gbif_links(taxon_key, lat, lon):
    base = "https://www.gbif.org/occurrence/search"
    return {
        "species": f"https://www.gbif.org/species/{taxon_key}",
        "local": f"{base}?taxon_key={taxon_key}&geo_distance={lat},{lon},{LOCAL_KM}km",
        "regional": f"{base}?taxon_key={taxon_key}&geo_distance={lat},{lon},{REGIONAL_KM}km",
        "global_map": f"{base}?taxon_key={taxon_key}&view=MAP",
    }


# ---------- grading (pure, no network) ----------

def far_absent(far, global_count):
    """True when a well-recorded species has no records anywhere within FAR_KM."""
    return FAR_KM is not None and far == 0 and global_count >= MIN_GLOBAL_FAR


def regional_absent(regional, global_count, regional_effort):
    """True when local data is thin but the wider region is surveyed and has no records."""
    return (regional == 0 and global_count > 0 and regional_effort is not None
            and regional_effort >= MIN_REGIONAL_EFFORT)


def grade(matched, local, regional, effort, global_count, far=None, regional_effort=None):
    """Grade from counts. Order matters:
    unmatched -> GREY; seen locally -> None;
    none within FAR_KM but well recorded elsewhere -> RED (local effort irrelevant);
    area surveyed (effort >= MIN_EFFORT):
        seen in region but not locally -> ORANGE; seen elsewhere in world only -> RED;
    area barely surveyed:
        wider region surveyed and has no records -> ORANGE; otherwise -> GREY;
    no records anywhere -> GREY.
    """
    if not matched:
        return "GREY"
    if local > 0:
        return None
    if far_absent(far, global_count):
        return "RED"
    if effort >= MIN_EFFORT:
        if regional > 0:
            return "ORANGE"
        return "RED" if global_count > 0 else "GREY"
    if regional_absent(regional, global_count, regional_effort):
        return "ORANGE"
    return "GREY"


def evidence(result, countries=()):
    """Plain-English, neutral sentence explaining the grade."""
    r = result
    name, cls = r["matched_name"] or r["name"], r.get("class_name") or "the same class"
    g = r["grade"]
    if r["gbif_key"] is None:
        return f'"{r["name"]}" was not found in the GBIF taxonomy; not enough data to assess.'
    if g is None:
        return f"{r['local_count']:,} GBIF records of {name} within {LOCAL_KM} km; plausible."
    low_effort = r["effort_count"] < MIN_EFFORT
    if g == "GREY" and low_effort:
        return (f"0 GBIF records of {name} within {LOCAL_KM} km, but only "
                f"{r['effort_count']:,} records of any {cls} within {LOCAL_KM} km, so the area "
                f"is too little surveyed to judge.")
    if g == "GREY":
        return f"No georeferenced GBIF records of {name} anywhere; not enough data to assess."
    if g == "ORANGE" and low_effort:
        return (f"0 GBIF records of {name} within {REGIONAL_KM} km. Local survey data is thin "
                f"({r['effort_count']:,} {cls} records within {LOCAL_KM} km), but the wider "
                f"{REGIONAL_KM} km region is surveyed ({r['regional_effort_count']:,} {cls} "
                f"records) and has no records of this species. "
                f"Possible range inconsistency flagged, verify.")
    surveyed = (f"{r['effort_count']:,} records of other {cls} within {LOCAL_KM} km, "
                f"so the area is surveyed.")
    if g == "ORANGE":
        return (f"0 GBIF records of {name} within {LOCAL_KM} km, but {r['regional_count']:,} "
                f"within {REGIONAL_KM} km. {surveyed} Possible range inconsistency flagged, verify.")
    if far_absent(r.get("far_count"), r["global_count"]) and low_effort:
        where = (f"; its {r['global_count']:,} records worldwide are mostly from "
                 f"{', '.join(countries)}") if countries else ""
        return (f"0 GBIF records of {name} within {FAR_KM:,} km{where}. Local survey effort is "
                f"low ({r['effort_count']:,} {cls} records within {LOCAL_KM} km), but the "
                f"species is not recorded anywhere in this region. Inconsistency flagged, verify.")
    where = (f"; most of its {r['global_count']:,} records worldwide are from "
             f"{', '.join(countries)}") if countries else ""
    return (f"0 GBIF records of {name} within {REGIONAL_KM} km{where}. {surveyed} "
            f"Inconsistency flagged, verify.")


# ---------- main entry point ----------

def check_species(scientific_name, lat, lon):
    """Check whether a species is plausible at (lat, lon). See module docstring."""
    result = {"name": scientific_name, "gbif_key": None, "matched_name": None,
              "name_note": None, "class_name": None, "grade": "GREY",
              "local_count": None, "regional_count": None, "effort_count": None,
              "regional_effort_count": None, "global_count": None, "far_count": None,
              "evidence": "", "gbif_links": {}}

    resolved = resolve_name(scientific_name)
    if resolved is None:
        result["evidence"] = evidence(result)
        return result

    m, key, accepted, note = resolved
    result.update(gbif_key=key, matched_name=accepted, name_note=note,
                  gbif_links=gbif_links(key, lat, lon))
    result["local_count"] = count(key, lat, lon, LOCAL_KM)
    result["regional_count"] = count(key, lat, lon, REGIONAL_KM)
    result["effort_count"], result["class_name"] = effort_count(m, lat, lon)
    result["global_count"] = count(key)
    if result["local_count"] == 0:
        if FAR_KM is not None and result["regional_count"] == 0:
            result["far_count"] = count(key, lat, lon, FAR_KM)
        if result["effort_count"] < MIN_EFFORT:
            result["regional_effort_count"] = effort_count(m, lat, lon, REGIONAL_KM)[0]
    result["grade"] = grade(True, result["local_count"], result["regional_count"],
                            result["effort_count"], result["global_count"],
                            result["far_count"], result["regional_effort_count"])
    countries = top_countries(key) if result["grade"] == "RED" else ()
    result["evidence"] = evidence(result, countries)
    return result
