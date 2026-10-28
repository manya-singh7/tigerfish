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
import threading
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

# Archipelago rule: mobile taxa (birds, marine species, plants) disperse between islands, so
# a record anywhere in the Andaman & Nicobar Islands clears a RED/ORANGE. Terrestrial
# mammals, amphibians and land reptiles keep the strict distance rule (islands isolate them).
ANDAMAN_NICOBAR_GADM = "IND.1_1"   # GBIF GADM id, "Andaman and Nicobar" (verified)
MOBILE_CLASSES = {"Aves", "Actinopterygii", "Elasmobranchii", "Holocephali", "Malacostraca",
                  "Maxillopoda", "Hexanauplia", "Bivalvia", "Gastropoda", "Cephalopoda",
                  "Polyplacophora", "Anthozoa", "Hydrozoa", "Scyphozoa", "Holothuroidea",
                  "Echinoidea", "Asteroidea", "Ophiuroidea", "Crinoidea", "Polychaeta"}
MOBILE_ORDERS = {"Cetacea", "Sirenia"}                         # whales, dolphins, dugong
MOBILE_FAMILIES = {"Cheloniidae", "Dermochelyidae", "Crocodylidae", "Hydrophiidae"}
MOBILE_KINGDOMS = {"Plantae"}

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
    # Write then rename, so a parallel reader never sees a half-written file.
    tmp = cache.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps({"url": url, "data": data}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache)
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


class LookupFailed(RuntimeError):
    """A GBIF lookup failed or returned no usable count. Never treat it as zero."""


def checked_count(data):
    """The 'count' of a GBIF search reply, or LookupFailed if it is missing or invalid."""
    c = data.get("count") if isinstance(data, dict) else None
    if isinstance(c, bool) or not isinstance(c, int) or c < 0:
        raise LookupFailed(f"GBIF reply without a valid count: {str(data)[:120]}")
    return c


def count(taxon_key, lat=None, lon=None, km=None, gadm=None):
    """Number of georeferenced occurrence records for a taxon, optionally within km of a
    point or inside a GADM area. Raises LookupFailed instead of ever returning a guess."""
    params = {"taxonKey": taxon_key, "limit": 0, "hasCoordinate": "true",
              "hasGeospatialIssue": "false"}
    if km is not None:
        params["geoDistance"] = f"{lat},{lon},{km}km"
    if gadm is not None:
        params["gadmGid"] = gadm
    try:
        data = gbif_get("/occurrence/search", **params)
    except (requests.RequestException, ValueError) as e:
        raise LookupFailed(str(e)) from e
    return checked_count(data)


def is_mobile(m, class_label=None):
    """Birds, marine species and plants: taxa the archipelago rule applies to."""
    return (m.get("class") in MOBILE_CLASSES or class_label == "ray-finned fish"
            or m.get("order") in MOBILE_ORDERS or m.get("family") in MOBILE_FAMILIES
            or m.get("kingdom") in MOBILE_KINGDOMS)


def apply_archipelago(grade_, mobile, archipelago):
    """Clear a RED/ORANGE for a mobile taxon recorded anywhere in the A&N Islands."""
    if grade_ in ("RED", "ORANGE") and mobile and archipelago:
        return None
    return grade_


MOBILE_REGION_NOTE = ("mobile species recorded in the wider region; local absence likely "
                      "reflects survey gaps")


def apply_mobile_region(grade_, mobile, regional, far):
    """A mobile taxon with any record within FAR_KM is GREY, not RED/ORANGE: GBIF coverage
    of the Nicobar Islands is sparse, so only absence from the whole region is flagged."""
    in_region = bool(regional) or bool(far)
    if grade_ in ("RED", "ORANGE") and mobile and in_region:
        return "GREY"
    return grade_


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
        try:
            data = gbif_get("/occurrence/search", taxonKey=CHORDATA_KEY, limit=0,
                            hasCoordinate="true", hasGeospatialIssue="false",
                            geoDistance=f"{lat},{lon},{km}km", facet="classKey", facetLimit=200)
        except (requests.RequestException, ValueError) as e:
            raise LookupFailed(str(e)) from e
        classed = sum(c["count"] for f in data.get("facets", []) for c in f["counts"])
        return checked_count(data) - classed, "ray-finned fish"
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

def check_species(scientific_name, lat, lon, archipelago_gadm=ANDAMAN_NICOBAR_GADM,
                  region_gadm=None, region_label=None):
    """Check whether a species is plausible at (lat, lon). See module docstring.

    archipelago_gadm: GBIF GADM region for the archipelago rule (default: the Andaman &
    Nicobar Islands); None turns the rule off (mainland sites, see tigerfish/sites.py).
    region_gadm: the statewide-list rule (a report whose species tables list a whole state):
    a RED/ORANGE for any taxon with GBIF records in that GADM region is cleared. None (the
    default) turns it off.
    The mobile-taxa rule (apply_mobile_region) applies either way."""
    result = {"name": scientific_name, "gbif_key": None, "matched_name": None,
              "name_note": None, "class_name": None, "grade": "GREY",
              "local_count": None, "regional_count": None, "effort_count": None,
              "regional_effort_count": None, "global_count": None, "far_count": None,
              "archipelago_count": None, "lookup_failed": False,
              "evidence": "", "gbif_links": {}}

    try:
        resolved = resolve_name(scientific_name)
    except (requests.RequestException, ValueError) as e:
        return _lookup_failed(result, e)
    if resolved is None:
        result["evidence"] = evidence(result)
        return result

    m, key, accepted, note = resolved
    result.update(gbif_key=key, matched_name=accepted, name_note=note,
                  gbif_links=gbif_links(key, lat, lon))
    try:
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
        mobile = is_mobile(m, result["class_name"])
        if result["grade"] in ("RED", "ORANGE") and mobile and archipelago_gadm:
            result["archipelago_count"] = count(key, gadm=archipelago_gadm)
            result["grade"] = apply_archipelago(result["grade"], mobile, result["archipelago_count"])
        if result["grade"] in ("RED", "ORANGE") and region_gadm:
            result["region_count"] = count(key, gadm=region_gadm)
            if result["region_count"]:
                result["grade"] = None
        if result["grade"] in ("RED", "ORANGE") and mobile:
            if result["regional_count"] == 0 and result["far_count"] is None:
                result["far_count"] = count(key, lat, lon, FAR_KM)
            flagged = result["grade"]
            result["grade"] = apply_mobile_region(flagged, mobile, result["regional_count"],
                                                  result["far_count"])
            result["mobile_region"] = result["grade"] != flagged
        countries = top_countries(key) if result["grade"] == "RED" else ()
    except (LookupFailed, requests.RequestException, ValueError) as e:
        return _lookup_failed(result, e)
    if result.get("mobile_region"):
        within = result["regional_count"] or result["far_count"]
        km = REGIONAL_KM if result["regional_count"] else FAR_KM
        where = (" or in the Andaman & Nicobar Islands"
                 if archipelago_gadm == ANDAMAN_NICOBAR_GADM else
                 f" or in GADM region {archipelago_gadm}" if archipelago_gadm else "")
        result["evidence"] = (f"0 GBIF records of {accepted} within {LOCAL_KM} km{where}, "
                              f"but {within:,} within {km:,} km: "
                              f"{MOBILE_REGION_NOTE}. Not graded.")
    elif result.get("region_count") and result["grade"] is None:
        result["evidence"] = (f"0 GBIF records of {accepted} within {LOCAL_KM} km of the point "
                              f"used, but {result['region_count']:,} in {region_label or region_gadm}, "
                              f"the area the report's list covers, so not flagged.")
    elif result["archipelago_count"] and result["grade"] is None:
        result["evidence"] = (f"0 GBIF records of {accepted} within {LOCAL_KM} km, but "
                              f"{result['archipelago_count']:,} elsewhere in the Andaman & Nicobar "
                              f"Islands: recorded elsewhere in the Andaman & Nicobar Islands, "
                              f"so not flagged.")
    else:
        result["evidence"] = evidence(result, countries)
    return result


def _lookup_failed(result, error):
    """GREY with the note "lookup failed": a failed lookup is never turned into a count."""
    result.update(grade="GREY", lookup_failed=True,
                  evidence=f"lookup failed: GBIF did not return a usable answer ({str(error)[:80]}); "
                           f"not graded.")
    return result
