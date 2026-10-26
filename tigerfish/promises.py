"""Promises check: did the EIA do what its Terms of Reference (ToR) promised?

1. promises     Regex finds every measurable value in the ToR sentences (durations, location
                counts, depths, frequencies); LIGHTNING (one call) says which are commitments,
                names the topic and words each one {id, topic, commitment, measure, quote, page}.
                A duration over a list ("air, water, soil, flora & fauna ... 3 months") becomes
                one promise per attribute. Every quote is verified against the ToR page text.
2. evidence     For each promise: BM25 over the EIA page texts (agent.bm25, the same search as
                the agent's search_report) for its topic, then regex on the top pages, only in
                sentences that name the topic (marine water never matches river water): date
                ranges and durations, counts of locations/stations, depths, sampling frequency.
                When regex finds several different values, LIGHTNING picks the sentence.
3. verdict      met / partly met / not met / not found. LIGHTNING first pass (one batched
                call); ULTRA re-reads the pages for "partly met"/"not met" candidates
                (max MAX_ULTRA calls). Grades: ORANGE = the report's own text shows the
                measure was not met (verified quotes from both documents); INFO = not found
                in the report text; NONE = met.
4. timeline     Every field-survey date range in the EIA (coral, turtle, flora/fauna, marine,
                air, ...) as bars, with the stated 3-month baseline window behind them.

Wording: "The ToR commits to X (ToR p.N); the report describes Y (EIA p.M). Verify."
All model calls are cached (llm.chat), so a re-run costs nothing.
"""

import calendar
import json
import re
from datetime import date
from pathlib import Path

from tigerfish import agent, claims as claims_mod, llm

ROOT = Path(__file__).resolve().parent.parent
TOR_PDF = ROOT / "data" / "eias" / "great_nicobar_tor_2021.pdf"
EIA_PDF = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"
# Public mirror of the draft EIA (data/eias/SOURCES.md); #page=N opens the cited page.
EIA_URL = "https://www.eqmagpro.com/wp-content/uploads/2021/12/143-Combined-EIA-1-15_compressed.pdf"

BUDGET_USD = 0.08
MAX_ULTRA = 6
SEARCH_PAGES = 15         # EIA pages searched per promise
MAX_CANDIDATES = 8        # sentences shown to LIGHTNING when regex finds several values
PAGE_CHARS = 4000         # per page sent to ULTRA
QUOTE_WINDOW = 140        # characters either side of a regex hit when its sentence is long
MET_RATIO = 0.9           # found >= 90% of the promised measure counts as met
PARTLY_RATIO = 0.5        # 50-90%: partly met; below: not met
EST_OUT = {"tor": 3000, "pick": 80, "first": 2500, "ultra": 700}   # output tokens, for estimates

VERDICTS = ("met", "partly met", "not met", "not found")
TOPICS = ["air", "met", "water", "soil", "noise", "land use", "terrestrial ecology",
          "marine ecology", "corals", "turtles", "crocodiles", "socio-economic", "baseline", "other"]
KINDS = ("duration", "locations", "depth", "frequency")

# ---------- numbers in words ----------

WORD_NUMBERS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
WORD_NUMBERS.update({"thirty": 30, "forty": 40, "fifty": 50, "a": 1, "an": 1, "single": 1})
NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(WORD_NUMBERS, key=len, reverse=True)) + r")"


def to_number(token):
    """'16' -> 16, 'sixteen' -> 16, 'Eight' -> 8; None if not a number."""
    t = (token or "").strip().lower()
    if t in WORD_NUMBERS:
        return WORD_NUMBERS[t]
    try:
        return float(t) if "." in t else int(t)
    except ValueError:
        return None


# ---------- dates ----------

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
YEAR = r"((?:19|20)\d{2})"
SEP = r"\s*(?:to|till|until|through|-|–|—|and)\s*"
OF = r"(?:\s+of)?\s+"
YR = r",?\s*"


def _last_day(y, m):
    return calendar.monthrange(y, m)[1]


def _year(y):
    y = int(y)
    return y + 2000 if y < 100 else y


def _range(start, end):
    """(start, end) as dates if valid and in order, else None. Inputs are (y, m, d)."""
    try:
        s, e = date(*start), date(*end)
    except (TypeError, ValueError):
        return None
    return (s, e) if s <= e else None


def _start_year(end_year, start_month, end_month):
    """'December to February 2021': the start is in the year before."""
    return end_year - 1 if start_month > end_month else end_year


DATE_PATTERNS = [
    # 15.12.2020 - 22.12.2020, 15/12/20 to 22/12/20
    ("numeric", rf"\b(\d{{1,2}})[./-](\d{{1,2}})[./-](\d{{2,4}}){SEP}(\d{{1,2}})[./-](\d{{1,2}})[./-](\d{{2,4}})\b"),
    # 1st December 2020 to 28th February 2021
    ("dmy_dmy", rf"\b{DAY}{OF}{MON}{YR}{YEAR}{SEP}{DAY}{OF}{MON}{YR}{YEAR}\b"),
    # 14 December to 2 January 2021
    ("dm_dmy", rf"\b{DAY}{OF}{MON}{SEP}{DAY}{OF}{MON}(?:{YR}{YEAR})?\b"),
    # (from) 14 to 22 December 2020, 14th – 19th April, 2021, 15-16 April, from 4th to 11th January
    ("dd_my", rf"\b{DAY}{SEP}{DAY}{OF}{MON}(?:{YR}{YEAR})?\b"),
    # December 2020 to February 2021, January 2021 and February 2021
    ("my_my", rf"\b{MON}{YR}{YEAR}{SEP}{MON}{YR}{YEAR}\b"),
    # February-March 2021, December to February 2021
    ("m_my", rf"\b{MON}{SEP}{MON}{YR}{YEAR}\b"),
    # during March 2021 (a whole month)
    ("during_my", rf"\b(?:during|in)\s+(?:the\s+month\s+of\s+)?{MON}{YR}{YEAR}\b"),
]


def parse_date_ranges(text, default_year=None):
    """Date ranges in text: [{start, end, days, text, pos}], in text order.

    Day-month formats without a year use default_year (skipped if None). A month without
    a day means the whole month. Each character belongs to at most one range.
    """
    found, masked = [], text
    for kind, pattern in DATE_PATTERNS:
        for m in re.finditer(pattern, masked, re.IGNORECASE):
            g = m.groups()
            r = None
            if kind == "numeric":
                r = _range((_year(g[2]), int(g[1]), int(g[0])), (_year(g[5]), int(g[4]), int(g[3])))
            elif kind == "dmy_dmy":
                r = _range((int(g[2]), MONTHS_of(g[1]), int(g[0])), (int(g[5]), MONTHS_of(g[4]), int(g[3])))
            elif kind == "dm_dmy":
                ey = int(g[4]) if g[4] else default_year
                if ey:
                    sm, em = MONTHS_of(g[1]), MONTHS_of(g[3])
                    r = _range((_start_year(ey, sm, em), sm, int(g[0])), (ey, em, int(g[2])))
            elif kind == "dd_my":
                y = int(g[3]) if g[3] else default_year
                if y:
                    r = _range((y, MONTHS_of(g[2]), int(g[0])), (y, MONTHS_of(g[2]), int(g[1])))
            elif kind == "my_my":
                sm, em = MONTHS_of(g[0]), MONTHS_of(g[2])
                r = _range((int(g[1]), sm, 1), (int(g[3]), em, _last_day(int(g[3]), em)))
            elif kind == "m_my":
                sm, em, ey = MONTHS_of(g[0]), MONTHS_of(g[1]), int(g[2])
                sy = _start_year(ey, sm, em)
                r = _range((sy, sm, 1), (ey, em, _last_day(ey, em)))
            elif kind == "during_my":
                mo, y = MONTHS_of(g[0]), int(g[1])
                r = _range((y, mo, 1), (y, mo, _last_day(y, mo)))
            if not r:
                continue
            found.append({"start": r[0], "end": r[1], "days": days_between(*r),
                          "text": m.group(0), "pos": m.start(), "kind": kind})
            masked = masked[:m.start()] + " " * (m.end() - m.start()) + masked[m.end():]
    return sorted(found, key=lambda x: x["pos"])


def MONTHS_of(name):
    """Month number from a name or abbreviation ('Dec', 'December', 'Sept.')."""
    key = name.lower().rstrip(".")
    return MONTHS.get(key) or MONTHS[key[:3]]


def days_between(start, end):
    """Inclusive day count: 1 Dec 2020 - 28 Feb 2021 is 90 days."""
    return (end - start).days + 1


def months(days):
    return round(days / 30.4, 1)


# ---------- durations, counts, depths, frequency ----------

UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "season": 90, "year": 365}


def parse_durations(text):
    """[(days, matched text)] for '8 days', 'three months', 'a period of 3 months', '2 weeks'.
    Not a frequency ('twice a week', 'two days per week') and not a unit ('mg C/m3 day')."""
    out = []
    rx = r"(?<![\w/.])" + NUM + r"\s*\(?\d*\)?\s*(day|week|month|year)s?\b(?!\s*(?:per|a|in\s+a)\s+week)"
    for m in re.finditer(rx, text, re.IGNORECASE):
        before = text[max(0, m.start() - 12):m.start()].lower()
        if m.group(1).lower() in ("a", "an") and re.search(r"(once|twice|thrice|times|per|in)\s*$", before):
            continue
        if re.search(r"(once in|every|each|per|after)\s*$", before):    # "once in 6 months"
            continue
        n = to_number(m.group(1))
        if n:
            out.append((round(n * UNIT_DAYS[m.group(2).lower()]), m.group(0)))
    return out


PLACE_WORDS = r"(?:locations?|stations?|sites?|sampling\s+points?|points?|samples?|sources?)"


def count_locations(text):
    """[(count, matched text)]: '20 locations', 'sixteen locations', 'Eight ground water
    sources', '10 numbers of samples', '6 appropriate locations', and station code runs in
    tables ('S11 S12 ... S20' -> 20, 'AAQ1 ... AAQ6' -> 6)."""
    out = []
    rx = re.compile(r"\b" + NUM + r"\s+(?:nos?\.?\s+|numbers?\s+of\s+)?(?:[a-z]+\s+){0,2}?" + PLACE_WORDS + r"\b",
                    re.IGNORECASE)
    for m in rx.finditer(text):
        n = to_number(m.group(1))
        if re.search(r"hour|hr|day|time|minute", m.group(0), re.I):   # "24 hourly sample"
            continue
        if n and n == int(n) and m.group(1).lower() not in ("a", "an", "single"):
            out.append((int(n), m.group(0)))
    # a run of three or more station codes with the same prefix, in a table header
    for m in re.finditer(r"\b([A-Z]{1,4})\s?(\d{1,2})(?:\s+\1\s?\d{1,2}){2,}\b", text):
        nums = [int(x) for x in re.findall(re.escape(m.group(1)) + r"\s?(\d{1,2})", m.group(0))]
        if nums == list(range(nums[0], nums[0] + len(nums))):       # consecutive codes only
            out.append((max(nums), m.group(0)))
    return out


DEPTH_CONTEXT = re.compile(r"depth|deep|reef|transect|dive|diving|scuba|below the surface", re.I)


def parse_depths(text):
    """[(deepest metres, matched text)] for '40 m', '16-30m', 'upto 6 m', '90 cm', in a depth
    context (the word depth/deep/reef/transect/dive within 60 characters before)."""
    out = []
    rx = re.compile(r"(\d+(?:\.\d+)?)\s*(?:(?:-|–|to)\s*(\d+(?:\.\d+)?))?\s*(m|metres?|meters?|cm)\b", re.I)
    for m in rx.finditer(text):
        if not DEPTH_CONTEXT.search(text[max(0, m.start() - 60):m.start()]):
            continue
        if re.match(r"\s*[×x*]\s*\d", text[m.end():]) or re.search(r"[×x*]\s*$", text[:m.start()]):
            continue                                   # a plot size, "100m × 100m", not a depth
        value = float(m.group(2) or m.group(1))
        if m.group(3).lower() == "cm":
            value /= 100
        out.append((round(value, 2), m.group(0)))
    return out


FREQ_WORDS = {"once": 1, "twice": 2, "thrice": 3}


def parse_frequency(text):
    """[(times per week, matched text)]: 'twice a week', 'two days per week', '2 days a week'."""
    out = []
    for m in re.finditer(r"\b(once|twice|thrice|" + NUM[1:-1] + r")\s*(?:times|days|samples)?\s*"
                         r"(?:a|per|in\s+a|each)\s+week\b", text, re.IGNORECASE):
        t = m.group(1).lower()
        n = FREQ_WORDS.get(t) or to_number(t)
        if n:
            out.append((n, m.group(0)))
    return out


def parse_measure(kind, measure):
    """The promised value as a number: duration -> days, locations -> count,
    depth -> metres, frequency -> times per week. None if the text has none."""
    measure = measure or ""
    if kind == "duration":
        hits = parse_durations(measure)
    elif kind == "locations":
        hits = count_locations(measure)
        if not hits and len(measure.split()) == 1:        # a bare number: "20", "twenty"
            n = to_number(measure)
            hits = [(n, measure)] if n and n == int(n) else []
    elif kind == "depth":
        hits = parse_depths("depth " + measure)
    elif kind == "frequency":
        hits = parse_frequency(measure)
    else:
        return None
    return hits[0][0] if hits else None


def extract_values(kind, text, default_year=None):
    """[(value, matched text)] of this kind in a text (the report side of the comparison)."""
    if kind == "duration":
        out = [(r["days"], r["text"]) for r in parse_date_ranges(text, default_year)]
        return out + parse_durations(text)
    return {"locations": count_locations, "depth": parse_depths,
            "frequency": parse_frequency}.get(kind, lambda t: [])(text)


# ---------- comparing and grading ----------

def compare(promised, found):
    """Rule verdict from numbers alone: met / partly met / not met / not found."""
    if found is None:
        return "not found"
    if not promised:
        return "met"
    ratio = found / promised
    if ratio >= MET_RATIO:
        return "met"
    return "partly met" if ratio >= PARTLY_RATIO else "not met"


def resolve(rule, first, ultra):
    """(final verdict, who decided). ULTRA wins when it ran. Without it, a shortfall only
    LIGHTNING sees while the report's own number meets the promise counts as met."""
    if ultra in VERDICTS:
        return ultra, "ultra"
    if first in VERDICTS:
        if rule == "met" and first in ("partly met", "not met"):
            return "met", "regex"
        return first, "lightning"
    return rule, "regex"


def grade(verdict, tor_quote_ok, eia_quote_ok, confirmed=True):
    """ORANGE: the report's own (verified) text shows the measure was not met, confirmed by
    ULTRA. INFO: not found in the report text, no verified report quote, or a shortfall only
    the first pass saw. NONE: met."""
    if verdict == "met":
        return "NONE"
    if verdict in ("partly met", "not met") and tor_quote_ok and eia_quote_ok and confirmed:
        return "ORANGE"
    return "INFO"


def message(p):
    """Neutral wording for a finding."""
    return (f"The ToR commits to {p['commitment'].rstrip('.')} (ToR p.{p['page']}); "
            f"the report describes {p['report_describes'].rstrip('.')} (EIA p.{p['eia_page']}). Verify.")


# ---------- text helpers ----------

ABBREV = re.compile(r"(?:\b(?:Mr|Mrs|Ms|Dr|Prof|No|Nos|Fig|Sr|St|al|viz|Vol|i\.e|e\.g)\.|\b[A-Z]\.)$")


def sentences(text):
    """Normalised page text split into sentences / bullet items ('Prof. K.B Reddy' stays whole)."""
    t = claims_mod.normalize(text)
    t = re.sub(r"\s*[\uf0b7\uf0a7\uf0d8•▪●]\s*", " • ", t)       # Word/PDF bullet glyphs
    parts = [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z0-9(])|\s?•\s", t) if s.strip()]
    out = []
    for part in parts:
        if out and ABBREV.search(out[-1]):
            out[-1] += " " + part
        else:
            out.append(part)
    return out


def quote_around(sentence, piece):
    """The sentence, or a word-trimmed window around `piece` if the sentence is long."""
    if len(sentence) <= 2 * QUOTE_WINDOW + 60:
        return sentence.strip()
    i = max(sentence.find(piece), 0)
    a, b = max(0, i - QUOTE_WINDOW), min(len(sentence), i + len(piece) + QUOTE_WINDOW)
    while a > 0 and sentence[a - 1] != " ":
        a += 1
    while b < len(sentence) and sentence[b] != " ":
        b -= 1
    return sentence[a:b].strip()


def page_num(value):
    """Page number from a model's answer: 270, "270", "p.270", "EIA p. 270" -> 270 (0 if none)."""
    m = re.search(r"\d+", str(value or ""))
    return int(m.group(0)) if m else 0


def verify(quote, pages_text, page):
    """Exact quote text if it is on `page` (or a neighbour, for quotes across a page break)."""
    order = [page, page + 1, page - 1] if page in pages_text else sorted(pages_text)
    for n in order:     # no or wrong page from the model: try every page
        if n in pages_text:
            exact = agent.verify_quote(quote, pages_text[n])
            if exact:
                return exact, n
    return None, page


# ---------- 1. promises from the ToR ----------

TOR_EXTRACT = {"duration": parse_durations, "locations": count_locations,
               "depth": parse_depths, "frequency": parse_frequency}


def tor_items(tor_pages):
    """Every measurable value in the ToR, by regex: one item per (sentence, kind, value).
    [{i, page, kind, value, measure, quote, context}]; quote is the whole ToR sentence."""
    items, seen = [], set()
    for p in tor_pages:
        prev = ""
        for s in sentences(p.get("text") or ""):
            for kind, fn in TOR_EXTRACT.items():
                for value, hit in fn(s):
                    key = (kind, value, s)
                    if key not in seen:
                        seen.add(key)
                        items.append({"i": len(items), "page": p["page"], "kind": kind, "value": value,
                                      "measure": hit, "quote": s, "context": prev[-300:]})
            prev = s
    return items


LABEL_SYSTEM = (
    "Each numbered item below is one number found in a sentence of the Terms of Reference (ToR) "
    "of an Indian Environmental Impact Assessment. For each item decide whether it is a "
    "commitment about how the EIA's studies will be done (how long, how many locations, how "
    "deep, how often). Project sizes, distances and areas are not commitments.\n"
    "Return JSON only: {\"items\": [{\"i\": item number, \"keep\": true or false, \"topic\": one of "
    + json.dumps(TOPICS) + " (flora & fauna = terrestrial ecology; plankton, benthos and sea water "
    "= marine ecology), \"commitment\": plain words naming the action and only this item's number, "
    "e.g. \"monitor ambient air quality at 6 locations\", \"applies_to\": for a duration that covers "
    "a list of attributes named in the sentence or its context (e.g. \"baseline data on air, "
    "water, soil, flora & fauna ... for 3 months\"), the list of topics it covers; otherwise []}]}")


def label_messages(items):
    lines = [f"[{it['i']}] ToR p.{it['page']} | {it['kind']}: \"{it['measure']}\" | sentence: "
             f"{it['quote']}" + (f" | context before: {it['context']}" if it["context"] else "")
             for it in items]
    return [{"role": "system", "content": LABEL_SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def extract_promises(tor_pages):
    """Verified, measurable promises from the ToR. Regex finds the numbers; LIGHTNING (one
    cached call) says which are commitments, names the topic and words the commitment."""
    items = tor_items(tor_pages)
    data = claims_mod.chat_json(llm.LIGHTNING, label_messages(items), EST_OUT["tor"]) or {}
    labels = {page_num(x.get("i")): x for x in data.get("items", []) if isinstance(x, dict)}
    texts = {p["page"]: p["text"] for p in tor_pages}
    out, dropped = [], []
    for it in items:
        lab = labels.get(it["i"])
        exact, page = verify(it["quote"], texts, it["page"])
        if not lab or not lab.get("keep") or not exact:
            dropped.append({**it, "why": "not verified on the ToR page" if not exact
                            else "not a commitment (Lightning)" if lab else "not labelled"})
            continue
        base = {"measure": it["measure"], "kind": it["kind"], "value": it["value"], "quote": exact,
                "page": page}
        # The ToR text must name each topic (Lightning sometimes adds one, e.g. land use).
        cut = it["quote"].find(it["measure"]) + len(it["measure"])     # words after the number
        support = it["context"] + " " + it["quote"][:cut]              # belong to the next item
        # A duration over a list: Lightning says it covers several attributes; which ones is
        # read from the ToR text itself (the model's own list sometimes adds or drops one).
        topics = [t for t in TOPIC_ORDER if lab.get("applies_to") and on_topic(t, support)]
        if it["kind"] == "duration" and lab.get("topic") in ("other", "baseline"):
            lab = {**lab, "topic": "baseline"}         # "EIA based on three months baseline study"
        if it["kind"] == "duration" and topics:
            out.append({**base, "topic": "baseline", "commitment": lab.get("commitment", "")})
            out += [{**base, "topic": t, "commitment": f"collect {t} baseline data for {it['measure']}"}
                    for t in topics]
        else:
            topic = lab.get("topic") if lab.get("topic") in TOPICS else "other"
            if topic != "baseline" and not on_topic(topic, support):
                topic = infer_topic(it["quote"], it["context"])
            out.append({**base, "topic": topic, "commitment": lab.get("commitment") or it["quote"]})
    return dedupe_promises(out), dropped


def dedupe_promises(promises):
    """Drop repeats of the same topic + kind + value (the ToR says '3 months' several times)."""
    seen, out = set(), []
    for p in promises:
        key = (p["topic"], p["kind"], p["value"])
        if key not in seen:
            seen.add(key)
            out.append({"id": f"P{len(out) + 1:02d}", **{k: v for k, v in p.items() if k != "id"}})
    return out


# ---------- 2. evidence in the EIA ----------

KIND_WORDS = {"duration": "study period survey conducted monitoring months",
              "locations": "locations stations samples collected",
              "depth": "depth transect diving reef m",
              "frequency": "frequency twice week sampling"}
TOPIC_QUERY = {"terrestrial ecology": "flora fauna ecology biodiversity primary survey",
               "marine ecology": "marine intertidal subtidal baseline survey zsi",
               "corals": "coral reef scuba transect", "air": "ambient air quality monitoring",
               "met": "meteorological weather station", "socio-economic": "social survey households",
               "water": "surface ground water quality sampling", "soil": "soil samples analysis",
               "noise": "noise monitoring levels", "baseline": "baseline environmental studies winter"}
# Future monitoring plans (EMP, post-project) are not evidence of the baseline study.
NOT_BASELINE = re.compile(r"post[- ]project|monitoring plan|during (?:construction|operation)|"
                          r"on (?:a )?monthly basis|\bEMP\b|will be (?:monitored|carried|collected)|periodical", re.I)


def search_query(p):
    """Topic words + kind words (the commitment's own words, 'collect ... data', add noise)."""
    return f"{p['topic']} {TOPIC_QUERY.get(p['topic'], '')} {p['measure']} {KIND_WORDS[p['kind']]}"


TOPIC_WORDS = {   # an EIA sentence (or the one before it) must name the promise's topic
    "air": r"\bair\b|AAQ|ambient|PM10",
    "met": r"meteorolog|weather|\bwind|rainfall|humidity",
    "water": r"water",
    "soil": r"\bsoil",
    "noise": r"noise",
    "land use": r"land ?use|LULC|satellite",
    "terrestrial ecology": r"flora|fauna|ecolog|biodiversity|vegetation|avifauna|mammal",
    "marine ecology": r"marine|sea ?water|intertidal|sub-?tidal|plankton|benth|coastal water",
    "corals": r"coral|reef",
    "turtles": r"turtle",
    "crocodiles": r"crocodile",
    "socio-economic": r"socio|social|household|tribal",
    "baseline": r"baseline|study period",
}


def on_topic(topic, sentence, previous=""):
    rx = TOPIC_WORDS.get(topic)
    return not rx or bool(re.search(rx, sentence + " " + previous, re.I))


TOPIC_ORDER = ["corals", "turtles", "crocodiles", "marine ecology", "soil", "noise", "air", "met",
               "water", "land use", "terrestrial ecology", "socio-economic"]


def infer_topic(sentence, previous=""):
    """First topic named in the sentence, else in the one before it (most specific first)."""
    for text in (sentence, previous):
        for t in TOPIC_ORDER:
            if re.search(TOPIC_WORDS[t], text, re.I):
                return t
    return "other"


STUDY_OF_TOPIC = {"air": "Air quality", "met": "Meteorology", "water": "Surface & ground water",
                  "soil": "Soil", "noise": "Noise", "terrestrial ecology": "Flora & fauna (ecology)",
                  "marine ecology": "Marine sampling (ZSI)", "corals": "Corals", "turtles": "Turtles",
                  "socio-economic": "Socio-economic survey"}


def timeline_candidates(p, bars, window=None):
    """For a duration promise: the dated field studies of its topic from the timeline."""
    if p["kind"] != "duration":
        return []
    if p["topic"] == "baseline" and window:
        bars = [{**window, "study": "baseline"}]
    else:
        bars = [b for b in bars if b["study"] == STUDY_OF_TOPIC.get(p["topic"])]
    return [{"page": b["page"], "value": b["days"], "quote": b["quote"],
             "hit": f"{b['start']} to {b['end']}", "in_sentence": True} for b in bars]


def candidates(p, ctx, default_year=2021, bars=(), window=None):
    """Regex hits of the promise's kind on the top BM25 pages, in sentences about its topic
    and not about future monitoring: [{page, value, quote, hit, in_sentence}]. For durations,
    the dated field studies of that topic (from the timeline) come first; then hits whose own
    sentence names the topic (the sentence before is only a fallback)."""
    ranked, _, _ = agent.bm25(ctx, search_query(p))
    from_timeline = timeline_candidates(p, bars, window)
    out, seen = [], {(c["page"], c["value"]) for c in from_timeline}
    for page, _score in ranked[:SEARCH_PAGES]:
        prev = ""
        for s in sentences(ctx.pages[page]):
            if on_topic(p["topic"], s, prev) and not NOT_BASELINE.search(s):
                for value, hit in extract_values(p["kind"], s, default_year):
                    if (page, value) not in seen:
                        seen.add((page, value))
                        out.append({"page": page, "value": value, "quote": quote_around(s, hit),
                                    "hit": hit, "in_sentence": on_topic(p["topic"], s)})
            prev = s
    out.sort(key=lambda c: not c["in_sentence"])         # stable: page rank kept within groups
    if from_timeline:                                     # dated field studies decide durations
        out = from_timeline
    return out, [c["page"] for c in from_timeline] + [pg for pg, _ in ranked[:SEARCH_PAGES]]


PICK_SYSTEM = ("You match a commitment from an EIA's Terms of Reference with the sentence in the "
               "EIA report that describes how that same item was actually done. Return JSON only: "
               "{\"index\": number of the best sentence, or -1 if none is about this item}.")


def pick_messages(p, cands):
    lines = "\n".join(f"[{i}] p.{c['page']}: {c['quote']}" for i, c in enumerate(cands))
    return [{"role": "system", "content": PICK_SYSTEM},
            {"role": "user", "content": f"Commitment ({p['topic']}): {p['commitment']} "
                                        f"(measure: {p['measure']})\n\nSentences:\n{lines}"}]


def choose(p, cands):
    """The best candidate: the only value found, or LIGHTNING's pick among several."""
    cands = cands[:MAX_CANDIDATES]
    if not cands:
        return None, "none"
    if len({c["value"] for c in cands}) == 1:
        return cands[0], "regex"
    data = claims_mod.chat_json(llm.LIGHTNING, pick_messages(p, cands), 200) or {}
    i = data.get("index")
    if isinstance(i, int) and 0 <= i < len(cands):
        return cands[i], "lightning"
    return None, "lightning: none"


# ---------- 3. verdicts ----------

VERDICT_RULES = (
    "Verdicts: \"met\" = the report shows the measure was reached (or exceeded, or an "
    "equivalent wording); \"partly met\" = the report's own text shows less than promised "
    "(fewer locations, shorter period, shallower depth) but some of it was done; \"not met\" = "
    "the report's own text shows far less, or a different method; \"not found\" = the given "
    "text does not say how this item was done. Judge only from the text given, never from "
    "outside knowledge. Quote the report exactly (max 40 words, copied character for "
    "character). Neutral words only.")

FIRST_SYSTEM = (
    "You compare commitments in the Terms of Reference (ToR) of an EIA with evidence from the "
    "EIA report. " + VERDICT_RULES + "\nReturn JSON only: {\"results\": [{\"id\", \"verdict\", "
    "\"report_describes\": what the report says was done, in plain words, e.g. \"water samples "
    "from sixteen locations\", \"eia_page\", \"eia_quote\"}]}")


def first_messages(items):
    blocks = []
    for p, ev in items:
        lines = [f"{p['id']} [{p['topic']}] ToR p.{p['page']}: {p['commitment']} (measure: {p['measure']})"]
        if ev["chosen"]:
            c = ev["chosen"]
            lines.append(f"  regex evidence p.{c['page']} (value {c['value']}): {c['quote']}")
        for s in ev["snippets"]:
            lines.append(f"  search hit p.{s['page']}: {s['snippet']}")
        blocks.append("\n".join(lines))
    return [{"role": "system", "content": FIRST_SYSTEM}, {"role": "user", "content": "\n\n".join(blocks)}]


ULTRA_SYSTEM = (
    "You check whether an Environmental Impact Assessment report did what its Terms of "
    "Reference (ToR) committed to, for one commitment, reading the report pages given. "
    + VERDICT_RULES + " A ToR item that says 'once during the study period' is met by one "
    "round of sampling. Only the baseline study counts: monitoring planned for construction or "
    "operation (EMP, post-project monitoring) is not evidence either way. "
    "For \"partly met\" or \"not met\", eia_quote must be the report text that "
    "shows the shortfall; if another page says the measure was reached, give that as "
    "supporting_quote. Return JSON only: {\"verdict\", \"report_describes\": a short phrase (max "
    "15 words) saying only what the report says was done, without comparing it to the ToR, e.g. "
    "\"water samples from sixteen locations\", \"eia_page\": number, \"eia_quote\", "
    "\"supporting_page\": number or null, \"supporting_quote\": text or null, \"reason\": one "
    "sentence}.")


def ultra_messages(p, pages_text, page_numbers):
    body = "\n\n".join(f"=== EIA page {n} ===\n{claims_mod.normalize(pages_text[n])[:PAGE_CHARS]}"
                       for n in page_numbers)
    return [{"role": "system", "content": ULTRA_SYSTEM},
            {"role": "user", "content": f"ToR commitment (ToR p.{p['page']}, topic {p['topic']}): "
                                        f"{p['commitment']} (measure: {p['measure']}).\nToR text: "
                                        f"\"{p['quote']}\"\n\n{body}"}]


def ultra_pages(p, ev):
    """The chosen evidence page first, then the best other search pages (max 2)."""
    first = [ev["chosen"]["page"]] if ev["chosen"] else []
    return list(dict.fromkeys(first + ev["search_pages"]))[:2]


def estimate(model, messages, out_tokens):
    """(USD, cached?) for one call; cached calls are free."""
    # same arguments as claims_mod.chat_json, so the cache key matches
    if llm.is_cached(model, messages, thinking=False, max_tokens=out_tokens, temperature=0):
        return 0.0, True
    chars = sum(len(m["content"]) for m in messages)
    return llm.cost_usd(model, chars // claims_mod.CHARS_PER_TOKEN, out_tokens), False


def check(tor_pages, eia_pages, budget=BUDGET_USD, max_ultra=MAX_ULTRA, say=print):
    """Run the whole check. Returns {promises, dropped, timeline, window, cost}."""
    eia_text = {p["page"]: p.get("text") or "" for p in eia_pages}
    ctx = agent.Context(eia_pages)
    spent = lambda: llm.session_cost_usd - start_cost   # noqa: E731
    start_cost = llm.session_cost_usd

    # Estimate before running: the ToR call is exact; later calls use worst-case sizes.
    est_tor, _ = estimate(llm.LIGHTNING, label_messages(tor_items(tor_pages)), EST_OUT["tor"])
    est_rest = (llm.cost_usd(llm.LIGHTNING, 20 * 600, 20 * EST_OUT["pick"])          # picks
                + llm.cost_usd(llm.LIGHTNING, 6000, EST_OUT["first"])                 # first pass
                + max_ultra * llm.cost_usd(llm.ULTRA, (2 * PAGE_CHARS + 1500) // 4, EST_OUT["ultra"]))
    say(f"Estimated cost (upper bound, before cache): ToR extraction ${est_tor:.4f}; "
        f"picks + first pass + {max_ultra} Ultra calls <= ${est_rest:.4f}; budget ${budget:.2f}")
    if est_tor + est_rest > budget:
        raise RuntimeError("estimated cost is over the budget; lower max_ultra")

    promises, dropped = extract_promises(tor_pages)
    say(f"{len(promises)} measurable promises (dropped {len(dropped)}).")
    if not promises:
        raise RuntimeError("no verified promises from the ToR; see the cached Lightning reply")

    # evidence (the timeline's dated field studies are the evidence for durations)
    window, bars = timeline(eia_pages)
    evidence = {}
    for p in promises:
        cands, search_pages = candidates(p, ctx, bars=bars, window=window)
        chosen, how = choose(p, cands)
        ranked, terms, df = agent.bm25(ctx, search_query(p))
        snippets = [{"page": pg, "snippet": agent.snippet(eia_text[pg], terms, df)} for pg, _ in ranked[:2]]
        evidence[p["id"]] = {"chosen": chosen, "how": how, "n_candidates": len(cands),
                             "search_pages": search_pages, "snippets": snippets,
                             "rule": compare(p["value"], chosen["value"] if chosen else None)}

    # first pass, LIGHTNING, one call
    first = claims_mod.chat_json(llm.LIGHTNING, first_messages([(p, evidence[p["id"]]) for p in promises]),
                                 EST_OUT["first"]) or {}
    first_by = {r.get("id"): r for r in first.get("results", []) if isinstance(r, dict)}

    # ULTRA for partly/not met candidates, biggest shortfall first
    def shortfall(p):
        c = evidence[p["id"]]["chosen"]
        return c["value"] / p["value"] if c and p["value"] else 1.0
    todo = [p for p in promises
            if first_by.get(p["id"], {}).get("verdict") in ("partly met", "not met")
            or evidence[p["id"]]["rule"] in ("partly met", "not met")]
    agree = lambda p: not (first_by.get(p["id"], {}).get("verdict") in ("partly met", "not met")  # noqa: E731
                           and evidence[p["id"]]["rule"] in ("partly met", "not met"))
    todo.sort(key=lambda p: (agree(p), shortfall(p)))     # both passes see a shortfall: first
    ultra_by = {}
    for p in todo[:max_ultra]:
        msgs = ultra_messages(p, eia_text, ultra_pages(p, evidence[p["id"]]))
        cost, _ = estimate(llm.ULTRA, msgs, EST_OUT["ultra"])
        if spent() + cost > budget:
            say(f"{p['id']}: skipped Ultra (budget)")
            continue
        ultra_by[p["id"]] = claims_mod.chat_json(llm.ULTRA, msgs, EST_OUT["ultra"]) or {}

    rows = []
    for p in promises:
        ev, f, u = evidence[p["id"]], first_by.get(p["id"], {}), ultra_by.get(p["id"])
        verdict, by = resolve(ev["rule"], f.get("verdict"), (u or {}).get("verdict"))
        src = u if by == "ultra" else f if by == "lightning" else None
        quote_src = src or {}
        eia_quote, eia_page, quote_ok = None, None, False
        if quote_src.get("eia_quote"):
            eia_quote, eia_page = verify(quote_src["eia_quote"], eia_text, page_num(quote_src.get("eia_page")))
            quote_ok = bool(eia_quote)
        if not eia_quote and ev["chosen"]:                       # fall back to the regex sentence
            eia_quote, eia_page = ev["chosen"]["quote"], ev["chosen"]["page"]
            quote_ok = ev["rule"] in ("partly met", "not met")   # only if its own number shows it
        if eia_quote is None:
            eia_page = None
        describes = quote_src.get("report_describes") or (eia_quote or "nothing about this item")
        row = {**p, "verdict": verdict, "verdict_by": by, "rule_verdict": ev["rule"],
               "found_value": ev["chosen"]["value"] if ev["chosen"] else None,
               "evidence_how": ev["how"], "n_candidates": ev["n_candidates"],
               "search_pages": ev["search_pages"], "eia_page": eia_page, "eia_quote": eia_quote,
               "report_describes": describes, "first_pass": f.get("verdict"),
               "ultra": u.get("verdict") if u else None, "reason": (u or {}).get("reason"),
               "supporting_quote": None, "supporting_page": None}
        if u and u.get("supporting_quote"):
            sq, sp = verify(u["supporting_quote"], eia_text, page_num(u.get("supporting_page")))
            row["supporting_quote"], row["supporting_page"] = (sq, sp) if sq else (None, None)
        row["grade"] = grade(verdict, True, quote_ok, confirmed=by == "ultra")
        if row["grade"] == "ORANGE":
            row["message"] = message(row)
        elif row["grade"] == "INFO" and verdict in ("partly met", "not met") and eia_page:
            row["message"] = message(row).replace(" Verify.", " A possible shortfall, not "
                                                  "confirmed by the second reading. Verify.")
        elif row["grade"] == "INFO":
            row["message"] = (f"The ToR commits to {p['commitment'].rstrip('.')} (ToR p.{p['page']}); "
                              f"the report text searched does not show how this was done. Verify.")
        else:
            row["message"] = None
        rows.append(row)

    return {"promises": rows, "dropped": dropped, "timeline": bars, "window": window,
            "new_spend_usd": round(spent(), 5), "ultra_calls": len(ultra_by)}


# ---------- 4. survey timeline ----------

STUDIES = [   # (label, keywords in the sentence), first match wins
    ("Bathymetry & oceanography", r"bathymetr|geophysical|side scan|oceanograph"),
    ("Corals", r"coral"),
    ("Turtles", r"turtle"),
    ("Birds", r"avifauna|\bbirds?\b"),
    ("Mammals", r"mammal"),
    ("Crocodiles", r"crocodile"),
    ("Flora & fauna (ecology)", r"ecology|biodiversity|\bflora\b"),
    ("Marine sampling (ZSI)", r"marine|intertidal|sub-?tidal|benth|plankton"),

    ("Air quality", r"air quality|ambient air|\bAAQ\b|PM10|PM2\.5"),
    ("Meteorology", r"wind|weather|meteorolog|rainfall|humidity"),
    ("Surface & ground water", r"water quality|surface water|ground ?water"),
    ("Soil", r"\bsoil"),
    ("Noise", r"\bnoise"),
    ("Socio-economic survey", r"social survey|socio|tribal|household"),
    ("Baseline (stated)", r"baseline"),
]
FIELD_WORDS = re.compile(r"survey|monitor|stud(?:y|ies)|sampl|conducted|carried out|collected|"
                         r"observ|results|period|baseline|nest", re.I)
NOT_FIELD = re.compile(r"health data|meeting|letter|dated|notification|census|annexure", re.I)
TIMELINE_YEARS = (2020, 2021)
MAX_SURVEY_DAYS = 200


def study_label(sentence):
    for label, rx in STUDIES:
        if re.search(rx, sentence, re.I):
            return label
    return None


INHERIT = {"Corals", "Turtles", "Birds", "Mammals", "Crocodiles", "Marine sampling (ZSI)",
           "Bathymetry & oceanography"}


def timeline(eia_pages):
    """(stated baseline window, [bars]). A bar: {study, start, end, days, page, pages, quote, url}.

    A sentence that only says "the baseline study" or "the survey" takes the study of the
    sentence before it when that one names a specific field study (marine, coral, bathymetry).
    A whole-month bar ("during February 2021") is dropped when a more precise bar of the same
    study overlaps it.
    """
    bars = {}
    for p in eia_pages:
        prev = None
        for s in sentences(p.get("text") or ""):
            label = study_label(s)
            if label in (None, "Baseline (stated)") and prev in INHERIT:
                label = prev
            prev = study_label(s)
            if not label or not FIELD_WORDS.search(s) or NOT_FIELD.search(s):
                continue
            for r in parse_date_ranges(s, default_year=None):
                if r["start"].year not in TIMELINE_YEARS or r["days"] > MAX_SURVEY_DAYS:
                    continue
                key = (label, r["start"], r["end"])
                if key in bars:
                    bars[key]["pages"].append(p["page"])
                    continue
                bars[key] = {"study": label, "start": r["start"].isoformat(), "end": r["end"].isoformat(),
                             "days": r["days"], "months": months(r["days"]), "page": p["page"],
                             "pages": [p["page"]], "quote": quote_around(s, r["text"]),
                             "url": f"{EIA_URL}#page={p['page']}", "whole_month": r["kind"] == "during_my"}
    rows = list(bars.values())
    rows = [b for b in rows if not (b["whole_month"] and any(
        o is not b and o["study"] == b["study"] and o["start"] <= b["end"] and b["start"] <= o["end"]
        and not o["whole_month"] for o in rows))]
    for b in rows:
        b["pages"] = sorted(set(b["pages"]))
    rows.sort(key=lambda b: (b["start"], b["study"]))
    stated = [b for b in rows if b["study"] == "Baseline (stated)"]
    window = None
    if stated:
        w = max(stated, key=lambda b: len(b["pages"]))
        window = {"start": w["start"], "end": w["end"], "days": w["days"], "page": w["page"],
                  "pages": w["pages"], "quote": w["quote"], "url": w["url"],
                  "label": f"Stated baseline window ({w['days']} days; ToR: 3 months)"}
    return window, [b for b in rows if b["study"] != "Baseline (stated)"]
