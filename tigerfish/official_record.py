"""Does it match the official record? Key project facts in the EIA vs official public sources.

1. report_facts      Nemotron LIGHTNING reads the project-description / executive-summary pages
                     and returns key facts (area, forest diversion, trees, cost, port / airport /
                     power capacity, township population, water demand, displacement), each with
                     a verbatim quote that must be found on its page (claims.repair_quote).
2. gather_sources    Tavily basic search restricted to official domains first, then extract of
                     the top pages (cached in cache/tavily, credit-capped). The open web is used
                     only for facts with no official figure, and is labelled. Tavily's research
                     endpoint exists in tavily-python but is not used: its credit cost is set per
                     request and known only after it finishes, so it cannot be kept under a cap.
3. official_figures  Regex finds each quantity in the extracted text, only in sentences that name
                     the topic; the quote is the exact sentence from the extracted text.
4. compare / grade   Pure code: units normalised, same quantity only, more than 5% apart ->
                     candidate. ORANGE = same quantity, comparable dates, differs, no explanation;
                     INFO = the source is dated after the EIA (a later revision) or explains the
                     change; NONE = matches; GREY = the source's date is unknown (never shown).

Neutral wording: "The report states X (p.N); [source, date] states Y. Verify which applies."
"""

import json
import re
from datetime import date
from urllib.parse import urlsplit

from tigerfish import claims as claims_mod
from tigerfish import copycheck, llm

EIA_DATE = date(2021, 12, 1)           # "December 2021" on the report's cover (p.5)
EIA_DATE_TEXT = "December 2021"
MIN_DIFFERENCE = 0.05                  # relative difference that makes a candidate
COMPARABLE_AFTER_DAYS = 183            # a source up to ~6 months after the EIA is comparable
PROJECT_START = date(2020, 1, 1)       # NITI Aayog's GNI plan dates from 2020: older sources
                                       # describe other proposals and are not compared
MAX_TAVILY_CREDITS = 60
MAX_NEBIUS_USD = 0.30
EXTRACT_PER_SEARCH = 3                 # top results of each search that get extracted
MAX_OFFICIAL_PER_FACT = 2              # comparisons kept per fact

OFFICIAL_DOMAINS = ["pib.gov.in", "parivesh.nic.in", "environmentclearance.nic.in", "moef.gov.in",
                    "greentribunal.gov.in", "sansad.in", "niti.gov.in", "andaman.gov.in",
                    "indiacode.nic.in"]
GOVERNMENT_SUFFIXES = (".gov.in", ".nic.in")
# Labelled official but not searched here: QCI runs the statutory NABET accreditation used by
# the accreditation check (eiameeting.qci.org.in, nabet.qci.org.in).
# The Gazette of India is the official publication of Acts and notifications.
OTHER_OFFICIAL_DOMAINS = ["qci.org.in", "egazette.gov.in"]
# Reputable but not government: PRS Legislative Research (an independent non-profit) summarises
# Bills and hosts copies of Bill / Act texts. Never labelled official.
AUTHORITATIVE_DOMAINS = ["prsindia.org"]
AUTHORITATIVE_LABEL = "authoritative, non-government"
OPEN_WEB_LABEL = "open web (not an official source)"

# Report pages the facts are read from: Chapter 1 (project description, size, cost, land),
# the executive summary, and the pages that state forest diversion / population.
REPORT_PAGES = list(range(1141, 1161)) + [1164, 1165, 23, 24, 28, 159, 518]
MIN_QUOTE_WORDS = 3                    # shorter quotes are fragments (often the running header)
NOT_A_FIGURE = {"township_population": r"employ|\bjobs?\b|workers?|work trips"}
PREFER = {   # a headline quote should say this (e.g. diversion, not just "under forest")
    "forest_diversion": r"divers|divert", "trees_felled": r"fell|cut",
    "township_population": r"population|resident"}

# ---------- the facts ----------
# dimension: area (ha) | count | money (INR crore) | teu | pax_peak_hour | pax_annual |
#            power_mw | power_mva | water_mld
FACTS = {
    # need: all must appear near the number; also: one more pattern near the number;
    # avoid: none may appear near it; whole: the report figure covers the whole project, so a
    # component figure (port only, one phase) is not the same quantity; qualifier: if the
    # report's quote has it (e.g. potable), the official text must have it too.
    "total_project_area": {
        "label": "Total project area", "dimensions": ["area"], "whole": True,
        "need": [r"project|development"],
        "also": r"total|entire|overall|admeasur|project area|development area|spanning|township",
        "avoid": r"little andaman|forest|national park|biosphere|tribal|notif|phase|geographical|"
                 r"island (?:is|has|area)|area of (?:the )?island|agricultur",
        "queries": ["Great Nicobar holistic development project area sq km"]},
    "forest_diversion": {
        "label": "Forest land to be diverted", "dimensions": ["area"], "whole": True,
        "need": [r"forest"], "also": r"diver(?:sion|ted|t)\b",
        "avoid": r"little andaman|compensatory|afforestation|haryana|tree cover|forest cover",
        "queries": ["Great Nicobar forest land diversion hectares"]},
    "trees_felled": {
        "label": "Trees to be felled", "dimensions": ["count"],
        "need": [r"trees?"], "also": r"fell|cut|felling|removed",
        "queries": ["Great Nicobar trees to be felled"]},
    "project_cost": {
        "label": "Project cost", "dimensions": ["money"], "whole": True,
        "need": [r"cost|invest|worth|outlay|estimated"],
        "avoid": r"little andaman|compensatory|afforestation|per (?:sq|ha|unit)",
        "queries": ["Great Nicobar project cost crore"]},
    "port_capacity": {
        "label": "Port capacity", "dimensions": ["teu"], "need": [r"TEU"],
        "avoid": r"little andaman",
        "queries": ["Great Nicobar transshipment port capacity TEU"]},
    "airport_capacity": {
        "label": "Airport capacity", "dimensions": ["pax_peak_hour", "pax_annual"],
        "need": [r"airport|passenger"], "avoid": r"little andaman",
        "queries": ["Great Nicobar international airport passengers capacity"]},
    "power_capacity": {
        "label": "Power plant capacity", "dimensions": ["power_mw", "power_mva"],
        "need": [r"power|plant|gas|solar"], "avoid": r"little andaman|demand",
        "queries": ["Great Nicobar power plant gas solar MVA"]},
    "township_population": {
        "label": "Township population", "dimensions": ["count"],
        "need": [r"population|resident"],
        "also": r"design|plann|project(?:ed|ion)|propos|envisag|township|by 20\d\d",
        "avoid": r"little andaman|tribal|shompen|nicobarese|census|existing|villages?|only around|"
                 r"present|currently|lpcd|employ|fewer than|increase from",
        "queries": ["Great Nicobar township population lakh"]},
    "water_demand": {
        "label": "Water demand", "dimensions": ["water_mld"], "need": [r"water"],
        "avoid": r"little andaman|waste ?water|sewage",
        "qualifier": r"(?<![Nn]on)(?<![Nn]on-)(?<![Nn]on )(?<![Nn]on- )\b[Pp]otable\b",
        "queries": ["Great Nicobar water demand MLD"]},
    "displacement": {
        "label": "Displacement / relocation", "dimensions": ["count"],
        "need": [r"displac|relocat|resettle|rehabilitat"], "avoid": r"little andaman",
        "queries": ["Great Nicobar displacement relocation tribal families"]},
}
COMPONENT = (r"\bICT[TP]\b|trans-?s?hipment|terminal|\bport\b|airport|township|power plant|"
             r"phases?\b|berths?\b")
WHOLE_PROJECT = (r"total project|total area|entire project|whole project|overall|holistic|"
                 r"integrated (?:development|project)|great nicobar (?:island )?(?:development )?project")
CTX_BEFORE, CTX_AFTER = 160, 80        # characters around a number that must name the topic
AVOID_AFTER = 25                       # 'avoid' words count only this far past the number
SCOPE_BEFORE, SCOPE_AFTER = 300, 100   # wider window for the component / whole-project check
MAX_QUOTE_CHARS = 350


GENERAL_QUERIES = ["Great Nicobar Island holistic development project",
                   "Great Nicobar project forest clearance trees Rajya Sabha",
                   "Great Nicobar transshipment port airport township power plant"]
EXPLANATION_WORDS = r"revis|modif|reduc|increas|amend|phase|initial|ultimate|first stage|subsequently|now"

# ---------- numbers and units ----------

MULTIPLIERS = {"thousand": 1e3, "lakh": 1e5, "lac": 1e5, "lakhs": 1e5, "million": 1e6,
               "crore": 1e7, "crores": 1e7, "billion": 1e9}
NUM = r"\d[\d,]*(?:\.\d+)?"


def to_number(text):
    """'3.3 lakh' -> 330000.0, '72,000' -> 72000.0; None if there is no number."""
    m = re.search(NUM, text or "")
    if not m:
        return None
    value = float(m.group().replace(",", ""))
    rest = (text[m.end():] or "").strip().lower()
    word = re.match(r"(thousand|lakhs?|lac|million|crores?|billion)\b", rest)
    if word:
        value *= MULTIPLIERS[word.group(1)]
    return value


def normalize(value, unit):
    """(number in base units, dimension) or (None, None).

    area -> ha; money -> INR crore; teu -> TEU; pax_* -> passengers; power -> MW or MVA (kept
    apart: MVA is apparent power, not comparable without a power factor); water -> MLD;
    count -> plain number (lakh / million / crore multipliers applied)."""
    if value is None:
        return None, None
    u = " ".join((unit or "").lower().replace(".", " ").split())
    v = float(value)
    mult = 1.0
    for word, factor in MULTIPLIERS.items():
        if re.search(rf"\b{word}\b", u):
            mult = factor
            break
    if re.search(r"\bteu\b|mteu", u):
        return v * (1e6 if "mteu" in u else mult), "teu"
    if re.search(r"crore|\brs\b|inr|₹|rupee", u):
        if re.search(r"lakh crore|lac crore", u):
            return v * 1e5, "money"
        if "crore" in u:
            return v, "money"
        return v * mult / 1e7, "money"                     # rupees -> crore
    if re.search(r"sq km|sqkm|km2|km²|square kilomet", u):
        return v * 100.0, "area"
    if re.search(r"\bha\b|hectare", u):
        return v * mult, "area"
    if re.search(r"\bacres?\b", u):
        return v * 0.404686, "area"
    if re.search(r"peak hour|\bphp\b|phph", u):
        return v * mult, "pax_peak_hour"
    if re.search(r"passengers? per (annum|year)|mppa|million passengers|pax per annum|annual", u):
        return v * (1e6 if "mppa" in u else mult), "pax_annual"
    if re.search(r"\bmva\b", u):
        return v * mult, "power_mva"
    if re.search(r"\bmw\b|megawatt", u):
        return v * mult, "power_mw"
    if re.search(r"\bgw\b", u):
        return v * 1000.0, "power_mw"
    if re.search(r"\bmld\b|million lit", u):
        return v * mult, "water_mld"
    if re.search(r"\bkld\b|kilolit", u):
        return v / 1000.0, "water_mld"
    if re.search(r"m3 ?/ ?d|cubic met", u):
        return v / 1000.0, "water_mld"
    return v * mult, "count"


def relative_difference(a, b):
    if a == b:
        return 0.0
    return abs(a - b) / max(abs(a), abs(b))


# ---------- dates ----------

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                      "sep", "oct", "nov", "dec"], 1)}
MONTH_NAMES = (r"January|February|March|April|May|June|July|August|September|October|"
               r"November|December")
HEADER_PATTERNS = [   # (regex, kind): explicit document dates, anywhere in the first part
    (r"Posted On:\s*(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", "dmy"),
    (r"ANSWERED ON\s*[:\-]?\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})", "dnum"),
    (r"\bdated\s*[:\-]?\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})", "dnum"),
]
OPENING_PATTERNS = [  # dates in the opening lines (title block) of a document
    (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_NAMES})\s*,?\s*(\d{{4}})", "dmy"),
    (rf"\b({MONTH_NAMES})\s+(\d{{1,2}})\s*,\s*(\d{{4}})", "mdy"),
    (rf"\b({MONTH_NAMES})\s*,?\s+(\d{{4}})\b", "my"),
]
HEADER_CHARS, OPENING_CHARS = 4000, 300


def _mk(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _parse(groups, kind):
    if kind == "dnum":
        a, b, c = groups
        return _mk(c, b, a)
    if kind == "dmy":
        a, b, c = groups
        return _mk(c, MONTHS.get(b[:3].lower(), 0), a)
    if kind == "mdy":
        a, b, c = groups
        return _mk(c, MONTHS.get(a[:3].lower(), 0), b)
    a, b = groups
    return _mk(b, MONTHS.get(a[:3].lower(), 0), 1)


def document_date(text, url=""):
    """(date, the text it was read from) for a source document, or (None, "").

    Only strong signals: an explicit header ("Posted On", "Answered on", "dated ..."), a date
    in the opening lines (the title block), or a year/month in the URL path. Dates inside the
    body (e.g. "received clearance on 11 November 2022") are never used: they describe events,
    not the document."""
    flat = " ".join((text or "").split())
    for patterns, part in ((HEADER_PATTERNS, flat[:HEADER_CHARS]), (OPENING_PATTERNS, flat[:OPENING_CHARS])):
        for pattern, kind in patterns:
            m = re.search(pattern, part, re.IGNORECASE)
            if m:
                d = _parse(m.groups(), kind)
                if d and date(1990, 1, 1) <= d <= date(2030, 12, 31):
                    return d, m.group(0)
    m = re.search(r"/(20\d{2})[/-](\d{1,2})(?:[/-](\d{1,2}))?/", url or "")
    if m:
        d = _mk(m.group(1), m.group(2), m.group(3) or 1)
        if d:
            return d, f"URL path {m.group(0)}"
    return None, ""


def date_relation(source_date, eia_date=EIA_DATE):
    """"unknown" | "before_project" (older than the project itself: about something else) |
    "comparable" (up to ~6 months after the EIA) | "later" (a revision after the EIA)."""
    if source_date is None:
        return "unknown"
    if source_date < PROJECT_START:
        return "before_project"
    return "later" if (source_date - eia_date).days > COMPARABLE_AFTER_DAYS else "comparable"


# ---------- sources ----------

def host(url):
    return (urlsplit(url or "").hostname or "").lower().removeprefix("www.")


def _on(h, domains):
    return any(h == d or h.endswith("." + d) for d in domains)


def is_official(url):
    """True only for official / government sites (not for authoritative non-government ones)."""
    return source_label(url) in ("official source", "government website")


def source_label(url):
    """"official source" | "government website" | AUTHORITATIVE_LABEL | OPEN_WEB_LABEL."""
    h = host(url)
    if _on(h, OFFICIAL_DOMAINS + OTHER_OFFICIAL_DOMAINS):
        return "official source"
    if h.endswith(GOVERNMENT_SUFFIXES):
        return "government website"
    if _on(h, AUTHORITATIVE_DOMAINS):
        return AUTHORITATIVE_LABEL
    return OPEN_WEB_LABEL


def rank_results(results):
    """Search results with official domains first (then government sites, then the rest),
    keeping Tavily's order within each group."""
    def tier(r):
        lab = source_label(r.get("url"))
        return {"official source": 0, "government website": 1, AUTHORITATIVE_LABEL: 2}.get(lab, 3)
    return sorted(results, key=tier)


# ---------- official figures in extracted text ----------

UNIT_PATTERNS = {   # dimension -> regex with groups (number, unit text)
    "area": rf"({NUM})\s*(sq\.?\s*km|sqkm|km2|km²|square kilomet\w*|hectares?|ha\b|acres?)",
    "count": rf"({NUM})\s*(lakhs?|lac|million|crores?|thousand)?",
    "money": rf"(?:Rs\.?|INR|₹)\s*({NUM})\s*(lakh\s+crores?|crores?|Cr\b)",
    "teu": rf"({NUM})\s*(million\s+TEUs?|lakh\s+TEUs?|MTEU|TEUs?)\b",
    "pax_peak_hour": rf"({NUM})\s*(peak[- ]hour passengers|PHPH?\b|PHP\b)",
    "pax_annual": rf"({NUM})\s*(million passengers(?: per annum| per year)?|MPPA)",
    "power_mw": rf"({NUM})\s*(MW|GW)\b",
    "power_mva": rf"({NUM})\s*(MVA)\b",
    "water_mld": rf"({NUM})\s*(MLD|KLD)\b",
}
COUNT_CONTEXT = {   # what a bare count must be about
    "trees_felled": r"\s*(?:lakhs?|lac|million|crores?|thousand)?\s+(?:trees|standing trees)",
    "township_population": r"\s*(?:lakhs?|lac|million|thousand)?\s+(?:people|persons|population|residents)",
    "displacement": r"\s*(?:lakhs?|thousand)?\s+(?:families|persons|people|households|individuals)",
}


EXTRA_PATTERNS = {  # (number, multiplier) right after the verb, e.g. "felled is 7.11 lakh"
    "trees_felled": [rf"(?:fell(?:ed|ing)?|cut)\b[^.\d]{{0,40}}?({NUM})\s*(lakhs?|lac|million|thousand)\b"],
}
ZERO_PATTERNS = {   # explicit statements of none
    "displacement": r"no (?:displacement|relocation)\b[^.]{0,80}|\b(?:not|never) (?:be )?displaced\b",
}
GNI = r"great nicobar|\bGNI\b|galathea|campbell bay"
NEAR_GNI = 1500                        # chars: in a many-project document, GNI named this close


def about_great_nicobar(flat):
    """True for a document about Great Nicobar (named in the opening part and at least 3 times)."""
    hits = [m.start() for m in re.finditer(GNI, flat, re.IGNORECASE)]
    return len(hits) >= 3 and hits[0] < 2000


ABBREVIATIONS = {"sq", "no", "nos", "rs", "km", "ha", "approx", "viz", "etc", "dt", "mr", "dr",
                 "st", "vol", "fig", "sr"}
BREAK = re.compile(r"[.;]\s+|●\s*")


def sentence_breaks(flat, start=0, end=None):
    """Sentence breaks in flat[start:end] (match objects), skipping "sq. km", "Rs. 10", ..."""
    for m in BREAK.finditer(flat, start, len(flat) if end is None else end):
        word = re.search(r"([A-Za-z]+)$", flat[max(0, m.start() - 8):m.start()])
        if m.group().startswith(".") and word and word.group(1).lower() in ABBREVIATIONS:
            continue
        yield m


def quote_for(flat, start, end):
    """The sentence around flat[start:end] if it is short, else a word-aligned window; always an
    exact substring of flat."""
    ends = [m.end() for m in sentence_breaks(flat, 0, start)]
    s0 = ends[-1] if ends else 0
    m = next(sentence_breaks(flat, end), None)
    s1 = m.start() + 1 if m else len(flat)
    if s1 - s0 <= MAX_QUOTE_CHARS:
        return flat[s0:s1].strip()
    a = flat.rfind(" ", 0, max(0, start - CTX_BEFORE)) + 1
    b = flat.find(" ", min(len(flat), end + CTX_AFTER))
    return flat[a:b if b > 0 else len(flat)].strip()


def official_figures(key, text, url, report_quote=""):
    """[{value, unit, normalized, dimension, quote}] for one fact in one extracted text.

    A number counts only if the topic is named within CTX_BEFORE / CTX_AFTER characters of it
    and nothing in `avoid` is; for whole-project facts, a figure whose wider context names a
    component (port, one phase) and not the whole project is skipped. The quote is an exact
    substring of the extracted text (whitespace collapsed)."""
    spec = FACTS[key]
    flat = " ".join((text or "").split())
    about_gni = about_great_nicobar(flat)
    if not about_gni and not re.search(GNI, flat, re.IGNORECASE):
        return []
    qualifier = spec.get("qualifier")
    need_qualifier = bool(qualifier and re.search(qualifier, report_quote or "", re.IGNORECASE))
    out = []
    patterns = []
    for dim in spec["dimensions"]:
        if dim == "count":
            ctx_word = COUNT_CONTEXT.get(key)
            if ctx_word:
                patterns.append((rf"({NUM})(?={ctx_word})(\s*(?:lakhs?|lac|million|crores?|thousand)?)", dim))
        else:
            patterns.append((UNIT_PATTERNS[dim], dim))
    patterns += [(p, "count") for p in EXTRA_PATTERNS.get(key, [])]
    if key in ZERO_PATTERNS:                 # "no relocation is proposed" -> 0
        for m in re.finditer(ZERO_PATTERNS[key], flat, re.IGNORECASE):
            out.append({"value": 0.0, "unit": "persons (none, as stated)", "normalized": 0.0,
                        "dimension": "count", "quote": quote_for(flat, m.start(), m.end())})
    for pattern, dim in patterns:
        for m in re.finditer(pattern, flat, re.IGNORECASE):
            ctx = flat[max(0, m.start() - CTX_BEFORE): m.end() + CTX_AFTER]
            near = flat[max(0, m.start() - NEAR_GNI): m.end() + NEAR_GNI // 4]
            if not about_gni and not re.search(GNI, near, re.IGNORECASE):
                continue                        # a many-project document: GNI must be named nearby
            if not all(re.search(p, ctx, re.IGNORECASE) for p in spec["need"]):
                continue
            if spec.get("also") and not re.search(spec["also"], ctx, re.IGNORECASE):
                continue
            local = flat[max(0, m.start() - CTX_BEFORE): m.end() + AVOID_AFTER]
            if spec.get("avoid") and re.search(spec["avoid"], local, re.IGNORECASE):
                continue
            sentence = quote_for(flat, m.start(), m.end())
            if need_qualifier and not re.search(qualifier, sentence, re.IGNORECASE):
                continue
            if spec.get("whole") and is_component(sentence, flat[max(0, m.start() - SCOPE_BEFORE): m.end() + SCOPE_AFTER]):
                continue
            raw, unit = m.group(1), (m.group(2) or "").strip()
            if dim == "money" and unit.lower() == "cr":
                unit = "crore"
            if dim == "count":
                unit = (unit + " " + {"trees_felled": "trees", "township_population": "persons",
                                      "displacement": "persons"}[key]).strip()
            number = float(raw.replace(",", ""))
            if number == 0 or (dim == "count" and number < 10
                               and not re.search(r"lakh|lac|million|crore|thousand", unit, re.I)):
                continue
            norm, d = normalize(number, unit + " rs" if dim == "money" else unit)
            if d != dim:
                continue
            out.append({"value": number, "unit": unit, "normalized": norm, "dimension": d,
                        "quote": sentence})
    return out


def is_component(sentence, wide):
    """True if a figure is for one component (the port, one phase), not the whole project: the
    figure's own sentence decides when it names either; otherwise the wider context does."""
    comp, whole = (re.search(COMPONENT, sentence, re.IGNORECASE),
                   re.search(WHOLE_PROJECT, sentence, re.IGNORECASE))
    if comp or whole:
        return bool(comp) and not whole
    return bool(re.search(COMPONENT, wide, re.IGNORECASE)) and not re.search(WHOLE_PROJECT, wide, re.IGNORECASE)


# ---------- report facts (LIGHTNING) ----------

EXTRACT_PROMPT = """You read one page of an Environmental Impact Assessment report and list the \
key project facts stated on it. Facts (use these keys only):
- total_project_area: total area of the project / development (not the island, not forest)
- forest_diversion: forest land to be diverted
- trees_felled: number of trees to be felled or cut
- project_cost: total project cost or investment (or the cost of one component; say which)
- port_capacity: container port / transshipment terminal capacity
- airport_capacity: airport capacity (peak hour passengers or passengers per year)
- power_capacity: power plant capacity
- township_population: planned township / resident population
- water_demand: water demand or requirement
- displacement: people or families to be displaced or relocated (0 if the page says none)
Return JSON only: {"facts": [{"key": ..., "value": number, "unit": "...", "scope": "what the \
figure covers, e.g. 'whole project', 'ICTT only', 'final phase'", "quote": "exact words copied \
from the page that contain the number"}]}. Copy the quote verbatim from the page, including the \
number. Use the number exactly as written (e.g. 3.3 with unit "lakh persons"). If a fact is not \
on this page, leave it out. If none are, return {"facts": []}."""
MAX_PAGE_CHARS = 9000


def _page_messages(page_text):
    return [{"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": " ".join(page_text.split())[:MAX_PAGE_CHARS]}]


def estimate_usd(page_text):
    price_in, price_out = llm.PRICES[llm.LIGHTNING]
    return (len(page_text) / 3.5 + 600) * price_in / 1e6 + 1500 * price_out / 1e6


def value_in_quote(value, quote):
    """True if the number (as written, or with thousands separators) is in the quote."""
    nums = {float(n.replace(",", "")) for n in re.findall(NUM, quote or "")}
    return float(value) in nums


def report_facts_from_page(page_no, page_text, raw):
    """Verified facts from one LIGHTNING reply: known key, number in the quote, and the quote
    found on the page (verbatim or repaired to the closest page substring)."""
    out = []
    for f in (raw or {}).get("facts") or []:
        if not isinstance(f, dict) or f.get("key") not in FACTS:
            continue
        try:
            value = float(str(f.get("value")).replace(",", ""))
        except ValueError:
            continue
        quote = str(f.get("quote") or "")
        if claims_mod.quote_on_page(quote, page_text):
            verified, how = quote, "verbatim on the page"
        else:
            verified, sim = claims_mod.repair_quote(quote, page_text)
            how = f"closest page text ({sim:.0%} similar)"
        if not verified or not value_in_quote(value, verified):
            continue
        if len(verified.split()) < MIN_QUOTE_WORDS or re.search(r"not stated", str(f.get("scope")), re.I):
            continue
        if value == 0 and not (f["key"] == "displacement" and re.search(r"\bno\b|\bnot\b|\bnil\b", verified, re.I)):
            continue
        bad = NOT_A_FIGURE.get(f["key"])
        if bad and re.search(bad, f"{f.get('unit')} {f.get('scope')} {verified}", re.IGNORECASE):
            continue
        norm, dim = normalize(value, str(f.get("unit") or ""))
        if dim not in FACTS[f["key"]]["dimensions"]:
            continue
        out.append({"key": f["key"], "value": value, "unit": str(f.get("unit") or ""),
                    "scope": str(f.get("scope") or ""), "normalized": norm, "dimension": dim,
                    "page": page_no, "quote": verified, "quote_check": how})
    return out


SCOPE_WHOLE = re.compile(r"whole|entire|total|overall|integrated|holistic|project", re.IGNORECASE)
SCOPE_PART = re.compile(r"\bICTT\b|airport|township|power|port only|phase|initial|component", re.IGNORECASE)


def pick_report_fact(candidates):
    """The headline figure for one fact: whole-project scope before component figures, then
    the executive summary / Chapter 1 pages in REPORT_PAGES order. Others are kept as 'also'."""
    order = {p: i for i, p in enumerate(REPORT_PAGES)}

    def rank(f):
        part = bool(SCOPE_PART.search(f["scope"])) and not SCOPE_WHOLE.search(f["scope"])
        prefer = PREFER.get(f["key"])
        off_topic = bool(prefer) and not re.search(prefer, f["quote"], re.IGNORECASE)
        return (part, off_topic, order.get(f["page"], 999))
    ranked = sorted(candidates, key=rank)
    head = ranked[0]
    same = sorted({f["page"] for f in ranked if relative_difference(f["normalized"], head["normalized"]) <= MIN_DIFFERENCE})
    also, seen = [], set()
    for f in ranked[1:]:                      # one entry per distinct other value
        k = round(f["normalized"], 6)
        if relative_difference(f["normalized"], head["normalized"]) <= MIN_DIFFERENCE or k in seen:
            continue
        seen.add(k)
        also.append({x: f[x] for x in ("value", "unit", "scope", "page", "quote")})
    return {**head, "pages_with_same_value": same, "also": also}


def facts_cost_usd(pages, page_numbers=REPORT_PAGES):
    """What the LIGHTNING replies behind the facts cost, from the token usage saved with each
    cached reply (so a re-run from the cache still reports the real cost)."""
    total = 0.0
    for n in page_numbers:
        text = pages.get(n, "")
        if len(text.strip()) < 100:
            continue
        msgs = _page_messages(text)
        kwargs = llm._with_thinking(llm.LIGHTNING, False, {"max_tokens": 1500, "temperature": 0})
        data = llm._read_cache(llm.CACHE_DIR / f"{llm._cache_key(llm.LIGHTNING, msgs, kwargs)}.json")
        usage = (data or {}).get("usage") or {}
        total += llm.cost_usd(llm.LIGHTNING, usage.get("prompt_tokens", 0),
                              usage.get("completion_tokens", 0)) or 0.0
    return total


def report_facts(pages, page_numbers=REPORT_PAGES, max_usd=MAX_NEBIUS_USD):
    """{key: fact} from the report pages. Stops before the Nebius cap would be passed."""
    by_key, start = {}, llm.session_cost_usd
    calls = 0
    for n in page_numbers:
        text = pages.get(n, "")
        if len(text.strip()) < 100:
            continue
        msgs = _page_messages(text)
        if not llm.is_cached(llm.LIGHTNING, msgs, thinking=False, max_tokens=1500, temperature=0) \
                and llm.session_cost_usd - start + estimate_usd(text) > max_usd:
            break
        raw = claims_mod.chat_json(llm.LIGHTNING, msgs, max_tokens=1500)
        calls += 1
        for f in report_facts_from_page(n, text, raw):
            by_key.setdefault(f["key"], []).append(f)
    return {k: pick_report_fact(v) for k, v in by_key.items()}, calls


# ---------- Tavily ----------

def search(query, budget, official=True):
    params = {"query": query, "search_depth": "basic", "max_results": 5}
    if official:
        params["include_domains"] = OFFICIAL_DOMAINS
    data = copycheck.tavily_call("search", budget, 1, **params)
    return rank_results(data.get("results", [])), _credits(data, 1)


def extract(urls, budget):
    """({url: full text}, credits). Failed URLs cost nothing; quotes are checked against the
    full text."""
    if not urls:
        return {}, 0
    est = -(-len(urls) // 5)
    data = copycheck.tavily_call("extract", budget, est, urls=sorted(urls), extract_depth="basic")
    return {r["url"]: r.get("raw_content") or "" for r in data.get("results", [])}, _credits(data, est)


def _credits(data, estimate):
    """Credits Tavily reported for this response (kept in the cache), else the estimate."""
    c = (data.get("usage") or {}).get("credits")
    return c if isinstance(c, (int, float)) else estimate


class Log:
    """What Tavily was asked, for the stats panel and the results file."""

    def __init__(self):
        self.searches, self.extracts = [], []

    def stats(self, budget, sources):
        n = len(sources)
        official = sum(1 for s in sources if s["official"])
        calls = self.searches + self.extracts
        return {"searches": len(self.searches), "extracts": len(self.extracts),
                "credits": sum(c.get("credits", 0) for c in calls),
                "credits_spent_this_run": budget.used, "cached_calls": budget.cached,
                "sources": n, "official_sources": official,
                "official_share": round(official / n, 3) if n else None,
                "queries": self.searches}


def gather_sources(budget, log, facts_wanted, texts=None, quotes=None, official_only_facts=()):
    """{url: {"text", "title", "query", "official"}}: official searches first, then per-fact
    official searches, then the open web only for report facts still without a figure.
    official_only_facts (facts the report pages do not state) get official searches only."""
    texts = {} if texts is None else texts
    quotes = quotes or {}

    def run(query, official, fact=None):
        try:
            results, credits = search(query, budget, official)
        except copycheck.CreditCapReached:
            return
        log.searches.append({"query": query, "official_only": official, "fact": fact,
                             "results": [r.get("url") for r in results], "credits": credits})
        urls = [r["url"] for r in results if r.get("url") and r["url"] not in texts][:EXTRACT_PER_SEARCH]
        if not urls:
            return
        try:
            got, credits = extract(urls, budget)
        except copycheck.CreditCapReached:
            return
        log.extracts.append({"urls": urls, "extracted": sorted(u for u, t in got.items() if t),
                             "credits": credits})
        titles = {r["url"]: r.get("title", "") for r in results}
        for u, t in got.items():
            if t:
                texts[u] = {"text": t, "title": titles.get(u, ""), "query": query,
                            "official": is_official(u), "fact": fact}

    for q in GENERAL_QUERIES:
        run(q, True)
    for key in list(facts_wanted) + list(official_only_facts):
        if not any(official_figures(key, s["text"], u, quotes.get(key, "")) for u, s in texts.items() if s["official"]):
            for q in FACTS[key]["queries"]:
                run(q, True, key)
    for key in facts_wanted:
        if not any(official_figures(key, s["text"], u, quotes.get(key, "")) for u, s in texts.items()):
            for q in FACTS[key]["queries"]:
                run(q, False, key)
    return texts


# ---------- comparison ----------

def grade(report_fact, official, eia_date=EIA_DATE):
    """(grade, relative difference or None, relation). Same dimension only."""
    if report_fact["dimension"] != official["dimension"]:
        return "NOT_COMPARABLE", None, None
    diff = relative_difference(report_fact["normalized"], official["normalized"])
    relation = date_relation(official.get("date"), eia_date)
    if diff <= MIN_DIFFERENCE:
        return "NONE", diff, relation
    if relation == "unknown":
        return "GREY", diff, relation
    if relation == "later" or re.search(EXPLANATION_WORDS, official["quote"], re.IGNORECASE):
        return "INFO", diff, relation
    return "ORANGE", diff, relation


def fmt_value(value, unit):
    if value == 0 and "none" in (unit or ""):
        return "that none is proposed"
    v = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{v} {unit}".strip()


def message(report_fact, official, g):
    src = official["title"] or host(official["url"])
    when = official["date"].strftime("%d %B %Y") if official.get("date") else "date not found"
    base = (f"The report states {fmt_value(report_fact['value'], report_fact['unit'])} "
            f"(p.{report_fact['page']}); {src} ({host(official['url'])}, {when}) states "
            f"{fmt_value(official['value'], official['unit'])}. Verify which applies.")
    if g == "INFO" and date_relation(official.get("date")) == "later":
        base += f" The source is dated after the EIA ({EIA_DATE_TEXT}): changed after the EIA, dated {when}."
    elif g == "INFO":
        base += " The source's wording suggests a revision or a different phase."
    elif g == "GREY":
        base += " The source's date could not be found, so it is not compared."
    return base


def prefer_official(candidates):
    """Official sources first (listed domains, then other government sites), dated before
    undated. Open-web figures are kept only when no official one exists."""
    ranked = sorted(candidates, key=lambda f: (not f["official"], f["label"] != "official source",
                                               f["date"] is None))
    if any(f["official"] for f in ranked):
        ranked = [f for f in ranked if f["official"]]
    return ranked


def figures_in_sources(key, texts, report_quote="", official_only=False):
    """All dated-or-undated figures for one fact across the extracted sources, one per source
    (the first found), skipping sources older than the project."""
    out = {}
    for url, s in texts.items():
        if official_only and not s["official"]:
            continue
        d, d_quote = document_date(s["text"], url)
        if date_relation(d) == "before_project":
            continue
        for fig in official_figures(key, s["text"], url, report_quote):
            out.setdefault(url, {**fig, "url": url, "title": s["title"], "official": s["official"],
                                 "label": source_label(url), "date": d, "date_quote": d_quote,
                                 "quote_check": "exact sentence from the Tavily-extracted text"})
    return list(out.values())


def official_only(missing, texts):
    """Facts the report pages did not state, as found in official sources (no grade: a note
    for the reviewer, since the report may state them on pages not read)."""
    rows = []
    for key in missing:
        for f in prefer_official(figures_in_sources(key, texts, official_only=True))[:MAX_OFFICIAL_PER_FACT]:
            when = f["date"].strftime("%d %B %Y") if f["date"] else "date not found"
            rows.append({"fact": key, "label": FACTS[key]["label"],
                         "official": {**{k: f[k] for k in ("value", "unit", "normalized", "dimension",
                                                           "quote", "url", "title", "official",
                                                           "label", "date_quote", "quote_check")},
                                      "date": f["date"].isoformat() if f["date"] else None},
                         "message": f"{f['title'] or host(f['url'])} ({host(f['url'])}, {when}) states "
                                    f"{fmt_value(f['value'], f['unit'])}; the report pages read do not "
                                    f"state this figure. Verify whether the report states it elsewhere."})
    return rows


def compare(facts, texts):
    """Comparison rows: for each report fact, up to MAX_OFFICIAL_PER_FACT sources (official
    first, then dated, then by Tavily order), each graded."""
    rows = []
    for key, rf in facts.items():
        found = []
        for url, s in texts.items():
            d, d_quote = document_date(s["text"], url)
            for fig in official_figures(key, s["text"], url, rf["quote"]):
                if fig["dimension"] != rf["dimension"]:
                    continue
                if date_relation(d) == "before_project":
                    continue
                found.append({**fig, "url": url, "title": s["title"], "official": s["official"],
                              "label": source_label(url), "date": d, "date_quote": d_quote,
                              "quote_check": "exact sentence from the Tavily-extracted text"})
        # one figure per source: the closest to the report's figure
        best = {}
        for f in found:
            cur = best.get(f["url"])
            if cur is None or relative_difference(f["normalized"], rf["normalized"]) < \
                    relative_difference(cur["normalized"], rf["normalized"]):
                best[f["url"]] = f
        ranked = prefer_official(best.values())
        for off in ranked[:MAX_OFFICIAL_PER_FACT]:
            g, diff, relation = grade(rf, off)
            rows.append({"fact": key, "label": FACTS[key]["label"], "grade": g,
                         "difference": None if diff is None else round(diff, 4),
                         "date_relation": relation,
                         "report": {k: rf[k] for k in ("value", "unit", "scope", "normalized",
                                                       "dimension", "page", "quote", "quote_check")},
                         "official": {**{k: off[k] for k in ("value", "unit", "normalized", "dimension",
                                                             "quote", "url", "title", "official",
                                                             "label", "date_quote", "quote_check")},
                                      "date": off["date"].isoformat() if off["date"] else None},
                         "message": message(rf, off, g)})
    return rows


def run(pages, budget=None, log=None, max_usd=MAX_NEBIUS_USD):
    """The whole check. pages: {page number: text}."""
    budget = budget or copycheck.Budget(MAX_TAVILY_CREDITS)
    log = log or Log()
    start = llm.session_cost_usd
    facts, calls = report_facts(pages, max_usd=max_usd)
    missing = [k for k in FACTS if k not in facts]
    texts = gather_sources(budget, log, list(facts), quotes={k: f["quote"] for k, f in facts.items()},
                           official_only_facts=missing)
    rows = compare(facts, texts)
    sources = []
    for u, s in texts.items():
        d, d_quote = document_date(s["text"], u)
        sources.append({"url": u, "title": s["title"], "host": host(u), "official": s["official"],
                        "label": source_label(u), "query": s["query"],
                        "date": d.isoformat() if d else None, "date_quote": d_quote})
    return {
        "eia_date": EIA_DATE_TEXT, "facts": facts,
        "not_found_in_report": missing,
        "comparisons": rows, "official_only": official_only(missing, texts),
        "sources": sources, "tavily": log.stats(budget, sources),
        "research_endpoint": {
            "available": hasattr(__import__("tavily").TavilyClient, "research"),
            "used": False,
            "why": "Tavily research sets its credit cost per request and reports it only when "
                   "finished, so it cannot be kept under the run's credit cap; search + extract "
                   "(1 credit per search, 1 per 5 extracted pages) were used instead."},
        "cost": {"nebius_usd": round(facts_cost_usd(pages), 4),
                 "nebius_usd_spent_this_run": round(llm.session_cost_usd - start, 4),
                 "lightning_calls": calls, "tavily_credits": log.stats(budget, sources)["credits"],
                 "tavily_credits_spent_this_run": budget.used},
        "method": {"min_difference": MIN_DIFFERENCE, "comparable_after_days": COMPARABLE_AFTER_DAYS,
                   "official_domains": OFFICIAL_DOMAINS, "report_pages": REPORT_PAGES},
    }


def dumps(result):
    return json.dumps(result, ensure_ascii=False, indent=1, default=str)
