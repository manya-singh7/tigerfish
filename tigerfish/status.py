"""Status check for species tables: are the conservation and legal statuses current?

1. IUCN: for each species with an IUCN category in the table, GBIF's current IUCN Red
   List category (/v1/species/{key}/iucnRedListCategory, cached like all GBIF calls).
   Different from the report -> ORANGE "status may be outdated".
2. WPA schedule: the current schedule structure of the Wild Life (Protection) Act is
   read from sources retrieved with Tavily (cached, counted against the credit cap),
   NOT hardcoded. A schedule number above the current count (e.g. Sch-V after the 2022
   amendment) -> ORANGE, with the source URL and the quoted source sentence.

Grades: ORANGE (verify), NONE (consistent), GREY (not enough data; never shown as a finding).
"""

import re
from collections import Counter

import requests

from tigerfish import claims as claims_mod
from tigerfish import copycheck, species

IUCN_CODES = {"EX", "EW", "CR", "EN", "VU", "NT", "LC", "DD", "NE"}
IUCN_WORDS = {"extinct in the wild": "EW", "extinct": "EX", "critically endangered": "CR",
              "endangered": "EN", "vulnerable": "VU", "near threatened": "NT",
              "least concern": "LC", "data deficient": "DD", "not evaluated": "NE"}
WPA_QUERY = "Wild Life (Protection) Amendment Act 2022 number of schedules"
WPA_SOURCES = 3     # top search results whose text is extracted
OFFICIAL_DOMAINS = ("gov.in", "nic.in", "indiacode", "prsindia.org", "egazette", "sansad.in")
# Searched first (Tavily include_domains); the open web is only a fallback.
OFFICIAL_SEARCH_DOMAINS = ["indiacode.nic.in", "egazette.gov.in", "prsindia.org",
                           "moef.gov.in", "pib.gov.in", "sansad.in"]
NON_OFFICIAL_LABEL = "non-official source"
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10}
ROMAN = {"I": 1, "V": 5, "X": 10}


# ---------- table columns ----------

def find_column(table, pattern):
    return next((c for c in table["columns"] if re.search(pattern, c, re.IGNORECASE)), None)


# ---------- IUCN ----------

def iucn_code(value):
    """'VU', 'Vulnerable', 'vu ' -> 'VU'; anything else -> None."""
    v = claims_mod.normalize(str(value or "")).strip(" .")
    if v.upper() in IUCN_CODES:
        return v.upper()
    return IUCN_WORDS.get(v.lower())


def iucn_current(name):
    """GBIF's current IUCN category for a name, or None. Uses the species check's name
    resolution (synonyms -> accepted species, typos, subspecies -> species)."""
    resolved = species.resolve_name(name)
    if resolved is None:
        return None
    _, key, accepted, note = resolved
    try:
        data = species.gbif_get(f"/species/{key}/iucnRedListCategory")
    except requests.HTTPError:
        return None
    if not isinstance(data, dict) or iucn_code(data.get("code")) is None:
        return None
    return {"code": iucn_code(data["code"]), "category": data.get("category"), "gbif_key": key,
            "accepted": accepted, "name_note": note,
            "url": f"https://www.gbif.org/species/{key}",
            "iucn_url": f"https://www.iucnredlist.org/search?query={accepted.replace(' ', '%20')}"}


def check_iucn(name, report_value, current):
    """Compare the report's IUCN category with the current one (from iucn_current)."""
    reported = iucn_code(report_value)
    base = {"name": name, "check": "iucn", "report_value": report_value}
    if reported is None:
        return {**base, "grade": "GREY", "evidence": "No IUCN category in the report row."}
    if current is None:
        return {**base, "grade": "GREY",
                "evidence": "No IUCN Red List category found in GBIF for this name."}
    note = current["name_note"]
    out = {**base, "current_value": current["code"], "gbif_name": current["accepted"],
           "url": current["url"], "iucn_url": current["iucn_url"], "name_note": note}
    if reported == current["code"]:
        return {**out, "grade": "NONE",
                "evidence": f"Report says {reported}; GBIF/IUCN says {current['code']}."}
    if note:
        # The name only matched via a synonym, typo fix or species-level fallback: the
        # difference may come from taxonomy (a split or lump), not an outdated status.
        return {**out, "grade": "GREY",
                "evidence": (f"Report says {reported}; GBIF/IUCN says {current['code']} for "
                             f"{current['accepted']}, but the name needed correcting ({note}), "
                             f"so the categories may refer to different taxa. Check by hand.")}
    return {**out, "grade": "ORANGE", "message": "IUCN status may be outdated. Verify.",
            "evidence": (f"Report says {reported}; GBIF/IUCN Red List says {current['code']} "
                         f"({current['category']}) for {current['accepted']}: {current['url']}")}


# ---------- WPA schedules ----------

def schedule_number(value):
    """'Sch-II' -> 2, 'Schedule IV' -> 4, 'Sch-V' -> 5, '-' -> None."""
    m = re.search(r"\b(?:sch(?:edule)?)?[\s.\-]*([IVX]+|\d+)\b", str(value or ""), re.IGNORECASE)
    if not m:
        return None
    token = m.group(1).upper()
    if token.isdigit():
        return int(token)
    total, prev = 0, 0
    for ch in reversed(token):
        v = ROMAN[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def _num(word):
    w = word.lower()
    return int(w) if w.isdigit() else NUMBER_WORDS.get(w)


SCHEDULE_PATTERNS = [
    # "reduces the number of schedules from six to four", "Schedules from present six to four".
    # Not "Schedules for protected animal species from four to two": a "for ..." qualifier
    # between "schedules" and "from" means a sub-count, not the total.
    re.compile(r"schedules?\b(?:(?!\bfor\b)[^.]){0,60}?\bfrom\s+(?:the\s+)?"
               r"(?:present|existing|current)?\s*(\w+)\s+to\s+(\w+)", re.IGNORECASE),
    # "from six schedules to four", "six schedules to four schedules"
    re.compile(r"\b(?:from\s+)?(\w+)\s+schedules?\s+(?:to|into)\s+(\w+)", re.IGNORECASE),
]
# "The Bill reduces the total number of schedules to four" (target count only)
REDUCED_TO_PATTERN = re.compile(r"\b(?:reduc\w*|cut\w*|rationalis\w*|rationaliz\w*)\b[^.]{0,40}?"
                                r"\bschedules?\s+to\s+(\w+)\b", re.IGNORECASE)
NOW_PATTERN = re.compile(r"\b(?:now|currently|only)\s+(?:has\s+|have\s+|contains?\s+)?(\w+)\s+"
                         r"schedules\b", re.IGNORECASE)


def visible_text(text):
    """Source text without markdown markup (#, *, _, `, >), whitespace normalised.

    Quotes are taken from this, i.e. the text as a reader sees it on the page.
    """
    return claims_mod.normalize(re.sub(r"[#*_`>|]+", " ", str(text or "")))


def schedule_count_from_text(text):
    """[(current schedule count, exact sentence)] stated in a source text."""
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+", visible_text(text)):
        if "schedule" not in sentence.lower():
            continue
        for pat in SCHEDULE_PATTERNS:
            m = pat.search(sentence)
            if m and _num(m.group(1)) and _num(m.group(2)) and _num(m.group(2)) < _num(m.group(1)):
                found.append((_num(m.group(2)), sentence))
                break
        else:
            m = REDUCED_TO_PATTERN.search(sentence) or NOW_PATTERN.search(sentence)
            if m and _num(m.group(1)):
                found.append((_num(m.group(1)), sentence))
    return found


def schedule_votes(budget, include_domains=None):
    """[(count, sentence, url)] from one Tavily search (+ extract of the top hits)."""
    results = copycheck.search(WPA_QUERY, budget, exact=False,
                               include_domains=include_domains).get("results", [])
    # Full text: in a Bill, the sentence saying how many schedules remain is often in the
    # Statement of Objects at the very end.
    texts = copycheck.extract([r["url"] for r in results[:WPA_SOURCES]], budget, max_chars=None)
    votes = []
    for r in results:
        text = texts.get(r["url"]) or r.get("content", "")
        votes += [(count, sentence, r["url"]) for count, sentence in schedule_count_from_text(text)]
    return votes


def current_schedules(budget):
    """Current number of WPA schedules from retrieved sources, with the quoted evidence.

    Official sites are searched first (OFFICIAL_SEARCH_DOMAINS); the open web only if
    they give no usable sentence, and then the result is labelled NON_OFFICIAL_LABEL.
    Returns {"count", "quote", "url", "support", "sources", "official", "label"} or None.
    """
    votes = schedule_votes(budget, OFFICIAL_SEARCH_DOMAINS)
    official = bool(votes)
    if not votes:
        votes = schedule_votes(budget)
    if not votes:
        return None
    result = _best_vote(votes)
    result.update(official=official, label="official source" if official else NON_OFFICIAL_LABEL)
    return result


def _best_vote(votes):
    count, support = Counter(v[0] for v in votes).most_common(1)[0]
    agreeing = [v for v in votes if v[0] == count]
    _, quote, url = max(agreeing, key=lambda v: quote_rank(v[1], v[2]))
    sources = sorted({v[2] for v in agreeing})
    return {"count": count, "quote": quote, "url": url, "support": support, "sources": sources}


def quote_rank(sentence, url):
    """Prefer official sources, then sentences that name the 2022 amendment, then shorter."""
    official = any(d in url for d in OFFICIAL_DOMAINS)
    names_act = bool(re.search(r"amendment|2022", sentence, re.IGNORECASE))
    return (official, names_act, -len(sentence))


def check_schedule(name, report_value, current):
    """Flag a schedule number that no longer exists, citing the retrieved source."""
    n = schedule_number(report_value)
    base = {"name": name, "check": "wpa_schedule", "report_value": report_value}
    if n is None:
        return {**base, "grade": "GREY", "evidence": "No schedule given in the report row."}
    if current is None:
        return {**base, "grade": "GREY",
                "evidence": "Could not determine the current schedule structure from sources."}
    out = {**base, "current_value": f"{current['count']} schedules", "url": current["url"],
           "quote": current["quote"]}
    if n > current["count"]:
        label = "" if current.get("official", True) else f" ({NON_OFFICIAL_LABEL})"
        return {**out, "grade": "ORANGE", "source_label": current.get("label"),
                "message": "Legal schedule may be outdated. Verify.",
                "evidence": (f"Report lists Schedule {report_value}; {current['url']}{label} "
                             f"says: \"{current['quote']}\"")}
    return {**out, "grade": "NONE",
            "evidence": (f"Schedule {n} still exists ({current['count']} schedules now); its "
                         f"contents may have changed in the amendment.")}


# ---------- run on a table ----------

def check_table(table, budget):
    """IUCN and schedule checks for every row of a species table (from claims.extract_table_from_image)."""
    name_col = claims_mod.name_column(table)
    iucn_col = find_column(table, r"IUCN")
    wpa_col = find_column(table, r"WPA|Schedule|Wild ?life")
    results, wpa, stopped = [], None, None
    if wpa_col and any(schedule_number(r.get(wpa_col)) for r in table["rows"]):
        try:
            wpa = current_schedules(budget)
        except copycheck.CreditCapReached as e:
            stopped = str(e)
    for row in table["rows"]:
        name = claims_mod.normalize(row.get(name_col, "")) if name_col else ""
        if not name:
            continue
        if iucn_col:
            results.append(check_iucn(name, row.get(iucn_col), iucn_current(name)))
        if wpa_col:
            results.append(check_schedule(name, row.get(wpa_col), wpa))
    return {"results": results, "wpa_source": wpa, "columns": (name_col, iucn_col, wpa_col),
            "stopped": stopped}
