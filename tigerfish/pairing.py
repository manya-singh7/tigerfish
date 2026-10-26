"""Numeric candidate pairs by subject key (replaces all-against-all pairing on long reports).

1. subject_keys(claims)   LIGHTNING, batched and cached: one key per distinct subject,
                          {"measure", "place", "reading", "station"}, e.g.
                          "flora species count" | "galathea national park".
                          A subject the model leaves out gets a word-based key instead.
2. keyed_numeric_pairs(claims, keys)
   - cells: claims with the same (measure, place) in one bucket (value/reading, unit
     dimension, kind); monitoring readings (station-wise air/water/noise/soil results)
     use (parameter, station) instead and are never paired without a station
   - collapse repeats: within a cell, one cluster per distinct value (within
     MIN_DIFFERENCE); a candidate takes the preferred claim of each cluster (model claims
     before rule-pass claims, then the earliest page, never both on one page) and lists
     the cluster's other pages as "also_on"
   - pairs within a cell, and between cells whose measures are compatible (equal, or one
     a subset of the other without a qualifier such as "endemic" or "total") and whose
     places are compatible: the same place, or blank / "project site" / the island (the
     model labels project figures either way); a place inside another (a national park
     inside the island) only when the part's figure is LARGER than the whole's (counts
     and areas only); different named places never
   - at most MAX_PAIRS_PER_GROUP pairs per cell pair, most alike subjects first; the rest
     are counted in last_stats["dropped_by_cap"] and logged
Yields candidates one by one (no all-pairs list in memory).
The Ultra verdict prompt is not touched: it sees each claim's page, subject and quote only.
"""

import logging
import re
from itertools import combinations

from tigerfish import claims as claims_mod
from tigerfish import contradictions as ct
from tigerfish import llm

log = logging.getLogger(__name__)

KEY_BATCH = 40               # distinct subjects per LIGHTNING call
KEY_MAX_TOKENS = 4000
MAX_PAIRS_PER_GROUP = 8      # candidate pairs per subject group at most

PLACES = ["great nicobar island", "galathea national park", "campbell bay national park",
          "galathea bay", "project site", "andaman and nicobar islands", "study area"]
# place -> places inside it (for the part-larger-than-whole pairs)
INSIDE = {
    "great nicobar island": {"galathea national park", "campbell bay national park",
                             "galathea bay"},
    "andaman and nicobar islands": {"great nicobar island", "galathea national park",
                                    "campbell bay national park", "galathea bay",
                                    "project site"},
}

KEY_PROMPT = f"""You normalise the subjects of numbers taken from one Indian Environmental \
Impact Assessment report (a project on Great Nicobar Island), so that numbers about the same \
thing get the same key. For each numbered item return:
- measure: what is measured or counted, 2-6 plain lowercase words, WITHOUT the place, e.g.
  "fauna species count", "flora species count", "endemic flora species count",
  "bird species count", "island area", "coral area lost", "coral restoration area",
  "runway reclamation area", "power plant capacity", "project land area",
  "pm10 concentration". A distance names what it is measured to, e.g. "distance to port
  blair", "distance to biosphere reserve core zone". Same thing -> same words. Different groups or parts (birds vs
  fauna, endemic vs all, one component vs the total) -> different words.
- place: the place the number is about, lowercase. Use these exact forms when they apply:
  {", ".join(f'"{p}"' for p in PLACES)} ("GNI" and "Great Nicobar" are
  "great nicobar island"; the proposed port, airport, township or project area is
  "project site"). Otherwise a short name, or "" if no place is given.
- reading: true if the number is ONE measurement from a monitoring or lab results table
  (ambient air, water, noise, soil, sediment or marine sampling at a station, sample point
  or location), false otherwise. Census, demographic, design and summary figures are not
  readings.
- station: for a reading, the station, sample or location code or name (e.g. "AAQ1",
  "SW3", "Campbell Bay"); "" otherwise.
Return JSON only: {{"items": [{{"n": 1, "measure": "...", "place": "...", "reading": false, \
"station": ""}}, ...]}}"""

last_stats = {}


def norm(text):
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def subject_id(claim):
    return norm(claim["subject"])


def norm_measure(text):
    words = norm(text).split()
    return " ".join(w[:-1] if w.endswith("s") and len(w) > 4 and not w.endswith(("ss", "ies", "species"))
                    else w for w in words)


def norm_place(text):
    p = norm(text)
    if not p:
        return ""
    if "galathea" in p and ("national park" in p or p.endswith(" np") or " np " in p):
        return "galathea national park"
    if "campbell" in p and ("national park" in p or p.endswith(" np") or " np " in p):
        return "campbell bay national park"
    if "galathea bay" in p:
        return "galathea bay"
    if "andaman" in p:
        return "andaman and nicobar islands"
    if p in ("gni", "great nicobar", "great nicobar islands") or "great nicobar island" in p:
        return "great nicobar island"
    return p


def fallback_key(claim):
    """Word-based key when the model gave none: the subject's key words, no place."""
    return {"measure": " ".join(sorted(ct.keywords(claim["subject"]))) or subject_id(claim),
            "place": "", "reading": False, "station": "", "source": "fallback"}


def key_messages(batch):
    lines = []
    for i, c in enumerate(batch, 1):
        quote = claims_mod.normalize(c["quote"])[:200]
        lines.append(f'{i}. subject: {c["subject"]} | value: {c["value"]} {c.get("unit") or ""} '
                     f'| context: {c.get("context") or ""} | quote: "{quote}"')
    return [{"role": "system", "content": KEY_PROMPT},
            {"role": "user", "content": "\n".join(lines)}]


def subject_keys(claims):
    """{subject id: key} for the numeric, verified claims. One example claim per distinct
    subject (earliest page), sorted by subject so similar subjects share a batch."""
    first = {}
    for c in sorted(claims, key=lambda c: (c["page"], c["id"])):
        if ct.numeric(c) and c.get("verified"):
            first.setdefault(subject_id(c), c)
    items = [first[s] for s in sorted(first)]
    batches = [items[i:i + KEY_BATCH] for i in range(0, len(items), KEY_BATCH)]
    raws, _ = llm.run_parallel(
        lambda b: claims_mod.chat_json(llm.LIGHTNING, key_messages(b), KEY_MAX_TOKENS), batches)
    keys, missing = {}, 0
    for batch, raw in zip(batches, raws):
        got = {}
        for item in (raw or {}).get("items", []) if isinstance(raw, dict) else []:
            try:
                got[int(item.get("n"))] = item
            except (TypeError, ValueError, AttributeError):
                continue
        for n, c in enumerate(batch, 1):
            item = got.get(n)
            if not item or not norm_measure(item.get("measure")):
                keys[subject_id(c)] = fallback_key(c)
                missing += 1
                continue
            keys[subject_id(c)] = {
                "measure": norm_measure(item.get("measure")),
                "place": norm_place(item.get("place")),
                "reading": item.get("reading") is True
                           or str(item.get("reading")).lower() == "true",
                "station": norm(item.get("station")), "source": "model"}
    last_stats.update(subjects=len(items), key_calls=len(batches), keys_missing=missing)
    return keys


# Extra words that make a measure a different quantity ("endemic flora species count" is
# not "flora species count"), and words too generic to anchor a measure on their own.
QUALIFIERS = set("""endemic rare endangered threatened vulnerable total overall maximum max minimum
    min average mean median annual daily monthly hourly peak additional existing proposed phase
    new old non migratory marine terrestrial freshwater residential percentage per""".split())
GENERIC = set("""count number area length distance species specie capacity value rate size cost
    percentage total height depth width population requirement""".split())
# Places the model cannot tell apart reliably for project figures: compatible with each other.
SAME_PLACE = {"", "project site", "great nicobar island"}


# Environmental monitoring parameters: a claim is a station reading only if the model says so
# AND it names one of these (the model also marks census tables as readings).
PARAMETER = re.compile(
    r"\b(pm ?10|pm ?2\.?5|spm|rspm|so2|no2|nox|co|o3|ozone|nh3|benzene|noise|leq|ldn|db|ph|"
    r"turbidity|bod|cod|do|dissolved|tds|tss|conductivity|salinity|chlorides?|sulphates?|"
    r"sulfates?|nitrates?|nitrites?|phosphates?|silicates?|fluorides?|iron|lead|mercury|arsenic|"
    r"cadmium|chromium|zinc|copper|nickel|manganese|hardness|alkalinity|coliforms?|"
    r"temperature|humidity|wind|sodium|potassium|calcium|magnesium|nitrogen|phosphorus|"
    r"organic carbon|sand|silt|clay|porosity|permeability|chlorophyll|plankton|"
    r"concentration)\b", re.IGNORECASE)


def is_reading(claim, key):
    return bool(key["reading"]) and bool(PARAMETER.search(f'{key["measure"]} {claim["subject"]}'))


def cell_of(claim, key):
    """(bucket, measure, place-or-station), or None for a reading without a station.
    Claims are paired only within one bucket: same reading/value type, unit dimension, kind."""
    reading = is_reading(claim, key)
    bucket = ("reading" if reading else "value", ct.unit_key(claim["unit"])[0], ct.kind(claim))
    if reading:
        return (bucket, key["measure"], key["station"]) if key["station"] else None
    # Blank, "project site" and the island are one place for pairing, so their repeats
    # collapse together and share one cap.
    place = "great nicobar island" if key["place"] in SAME_PLACE else key["place"]
    return (bucket, key["measure"], place)


def measures_compatible(m1, m2):
    """Equal, or one's words a subset of the other's with no qualifier among the extra
    words, and the shorter one not generic ("runway reclamation area" ~ "airport runway
    reclamation area"; "flora species count" !~ "endemic flora species count"), or the
    same words apart from generic quantity nouns."""
    if m1 == m2:
        return True
    w1, w2 = set(m1.split()), set(m2.split())
    # Same bucket = same unit dimension, so a different quantity noun is a keying slip:
    # "coral restoration cost" (INR) ~ "coral restoration area" (INR).
    if (w1 - GENERIC) and (w1 - GENERIC) == (w2 - GENERIC):
        return True
    small, big = (w1, w2) if len(w1) <= len(w2) else (w2, w1)
    if len(small) < 2 or not small < big or not (small - GENERIC):
        return False
    return not ((big - small) & QUALIFIERS)


def place_relation(p1, p2):
    """"any": figures should agree; "nested": one place inside the other (pair only a part
    LARGER than the whole); None: different places, never paired."""
    if p1 == p2 or (p1 in SAME_PLACE and p2 in SAME_PLACE):
        return "any"
    if p2 in INSIDE.get(p1, ()) or p1 in INSIDE.get(p2, ()):
        return "nested"
    return None


def same_value(a, b):
    top = max(abs(a), abs(b))
    return top == 0 or abs(a - b) / top <= ct.MIN_DIFFERENCE


def value_clusters(members):
    """Claims grouped by value (within MIN_DIFFERENCE = same value), each cluster in order
    of preference: model claims before rule-pass claims, then the earliest page."""
    out, cur = [], []
    for c in sorted(members, key=ct.base_value):
        if cur and not same_value(ct.base_value(cur[0]), ct.base_value(c)):
            out.append(cur)
            cur = []
        cur.append(c)
    if cur:
        out.append(cur)
    return [sorted(cl, key=lambda c: (c.get("source") == "rule", c["page"], c["id"]))
            for cl in out]


def with_also(claim, cluster):
    also = sorted({c["page"] for c in cluster} - {claim["page"]})
    return {**claim, "also_on": also} if also else claim


def cluster_pair(a_cl, b_cl):
    """One candidate for two values: the preferred claim of each, on different pages
    (the next preferred one if they share a page). The other pages go to "also_on"."""
    for a in a_cl:
        for b in b_cl:
            if a["page"] != b["page"]:
                return pair(with_also(a, a_cl), with_also(b, b_cl))
    return None


def pair(a, b):
    return {"kind": "numeric", "claims": [a, b],
            "overlap": ct.subject_overlap(a["subject"], b["subject"]),
            "part_total": ct.part_vs_total(a, b)}


def capped(label, pairs):
    """Most alike subjects first; at most MAX_PAIRS_PER_GROUP."""
    pairs.sort(key=lambda p: (-p["overlap"], [c["page"] for c in p["claims"]]))
    if len(pairs) > MAX_PAIRS_PER_GROUP:
        n = len(pairs) - MAX_PAIRS_PER_GROUP
        last_stats["dropped_by_cap"] += n
        last_stats["dropped_groups"].append([label, n])
        log.info("pairing: %d pairs dropped by MAX_PAIRS_PER_GROUP in %s", n, label)
    return pairs[:MAX_PAIRS_PER_GROUP]


def cell_pairs(c1, cl1, c2, cl2):
    """Candidates between two cells (or within one when c1 == c2)."""
    if c1 == c2:
        return [p for a, b in combinations(cl1, 2) if (p := cluster_pair(a, b))]
    relation = "any" if c1[0][0] == "reading" else place_relation(c1[2], c2[2])
    out = []
    for a in cl1:
        for b in cl2:
            va, vb = ct.base_value(a[0]), ct.base_value(b[0])
            if same_value(va, vb):
                continue
            if relation == "nested":
                if c1[0][1] == "percent" or c1[0][2] not in ("amount", "area"):
                    continue
                inner_first = c1[2] in INSIDE.get(c2[2], ())
                part_v, whole_v = (va, vb) if inner_first else (vb, va)
                if part_v <= whole_v:
                    continue
            p = cluster_pair(a, b)
            if p:
                out.append(p)
    return out


def related(c1, c2):
    """May two different cells of one bucket be paired? Compatible measures, and the same
    station (readings) or compatible places (values)."""
    if not measures_compatible(c1[1], c2[1]):
        return False
    if c1[0][0] == "reading":
        return c1[2] == c2[2]
    return place_relation(c1[2], c2[2]) is not None


def keyed_numeric_pairs(claims, keys):
    """Yield numeric candidates (see the module docstring). Stats go to last_stats."""
    usable = [c for c in claims if ct.numeric(c) and c.get("verified")]
    cells, readings_unpaired = {}, 0
    for c in usable:
        cell = cell_of(c, keys.get(subject_id(c)) or fallback_key(c))
        if cell is None:
            readings_unpaired += 1
            continue
        cells.setdefault(cell, []).append(c)
    clusters = {cell: value_clusters(m) for cell, m in cells.items()}
    last_stats.update(numeric_claims=len(usable), groups=len(cells),
                      representatives=sum(len(v) for v in clusters.values()),
                      readings_without_station=readings_unpaired, dropped_by_cap=0,
                      dropped_groups=[], pairs_same_key=0, pairs_related_key=0,
                      pairs_part_whole=0)

    by_bucket = {}
    for cell in sorted(clusters):
        by_bucket.setdefault(cell[0], []).append(cell)
    for cs in by_bucket.values():
        for i, c1 in enumerate(cs):
            for c2 in cs[i:]:
                if c1 != c2 and not related(c1, c2):
                    continue
                found = cell_pairs(c1, clusters[c1], c2, clusters[c2])
                if not found:
                    continue
                label = (f"{c1[1]} | {c1[2]}" if c1 == c2
                         else f"{c1[1]} | {c1[2]}  ~  {c2[1]} | {c2[2]}")
                stat = ("pairs_same_key" if c1 == c2 else
                        "pairs_part_whole" if c1[0][0] == "value"
                        and place_relation(c1[2], c2[2]) == "nested" else "pairs_related_key")
                for p in capped(label, found):
                    last_stats[stat] += 1
                    yield p
