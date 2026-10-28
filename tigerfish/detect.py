"""Detect a report's basic facts from its own text: project name, state, site, consultant,
year and letter language. Used for uploads the app has never seen: nothing here is per report.

1. text_search(pages): plain text rules, free, no key needed.
   state      the Indian state / UT named most often on the first pages
   site       the first latitude + longitude written in degrees (decimal or deg-min-sec);
              "between 11.5° N and 18.5° N ... between 74° E and 78.5° E" gives the midpoint
              of the range (a statewide or district-wide report has no single site)
   project    the title line on the first pages that names a project / EIA
   consultant "Prepared by X", "EIA consultant: X", or a "... Pvt. Ltd." / "Labs" line near
              "consultant" / "NABET"
   year       the most recent "Month YYYY" on the first pages
2. model_detect(pages): one cheap Lightning call on the first pages (needs a key). Each
   value must come with a quote that is found on the page it cites, or it is dropped.
3. detect(pages, use_model): text search first, the model fills gaps (never guesses: a
   field with no evidence is None).

Each field is {"value", "page", "how", "quote"} or None. The app shows
"detected: <value> (page N), check this" and lets the visitor edit every field.
"""

import re
from collections import Counter

FIRST_PAGES = 30           # pages searched for the facts
MODEL_PAGES = 6            # pages sent to the model
MODEL_CHARS = 2500         # characters per page sent to the model
EST_OUT_TOKENS = 600

STATES = [
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka",
    "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
]
STATE_ALIASES = {"Andaman & Nicobar": "Andaman and Nicobar Islands",
                 "Andaman and Nicobar": "Andaman and Nicobar Islands",
                 "Great Nicobar": "Andaman and Nicobar Islands", "Orissa": "Odisha",
                 "Pondicherry": "Puducherry", "NCT of Delhi": "Delhi",
                 "Jammu & Kashmir": "Jammu and Kashmir"}
# Main language of each state, for the letter. Only some have a letter translation today
# (tigerfish/ui/letter.py: Tamil, Kannada); Hindi and English are always offered.
STATE_LANGUAGE = {
    "Tamil Nadu": "Tamil", "Puducherry": "Tamil", "Karnataka": "Kannada", "Kerala": "Malayalam",
    "Lakshadweep": "Malayalam", "Andhra Pradesh": "Telugu", "Telangana": "Telugu",
    "Maharashtra": "Marathi", "Goa": "Konkani", "Gujarat": "Gujarati", "West Bengal": "Bengali",
    "Tripura": "Bengali", "Odisha": "Odia", "Assam": "Assamese", "Punjab": "Punjabi",
    "Manipur": "Manipuri",
}
LETTER_TRANSLATED = {"Tamil", "Kannada"}

def _state_pattern(alias):
    words = [re.escape(w) for w in alias.split()]
    body = r"\s+".join("(?:and|&)" if w in ("and", "&") else w for w in words)
    return re.compile(r"\b" + body + r"\b", re.IGNORECASE)


_STATE_PATTERNS = [(name, _state_pattern(alias))
                   for alias, name in [(s, s) for s in STATES] + list(STATE_ALIASES.items())]

MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|"
          "December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
MONTH_YEAR = re.compile(rf"\b(?:{MONTHS})\.?,?\s+((?:19|20)\d\d)\b")

# 11°42'22.43" N | 11.7062° N | 11° 42' N | N 11°42' ; the text layer may use º, o or ˚
DEG = r"[°º˚]"
_COORD = (rf"(\d{{1,3}}(?:\.\d+)?)\s*{DEG}\s*(?:(\d{{1,2}}(?:\.\d+)?)\s*['′’]\s*)?"
          rf"(?:(\d{{1,2}}(?:\.\d+)?)\s*(?:\"|″|''|”)\s*)?")
LAT = re.compile(_COORD + r"([NS])\b")
LON = re.compile(_COORD + r"([EW])\b")
# a range: "between 11.5° N and 18.5° N", "between 6°45' and 7°15'N", "74° E to 78.5° E"
_C = (rf"(\d{{1,3}}(?:\.\d+)?)\s*{DEG}\s*(?:(\d{{1,2}}(?:\.\d+)?)\s*['′’]\s*)?"
      rf"(?:(\d{{1,2}}(?:\.\d+)?)\s*(?:\"|″|''|”)\s*)?")
LAT_RANGE = re.compile(_C + r"(?:[NS]\s*)?(?:latitudes?\s*)?(?:and|to|-|–)\s*" + _C + r"([NS])\b")
LON_RANGE = re.compile(_C + r"(?:[EW]\s*)?(?:longitudes?\s*)?(?:and|to|-|–)\s*" + _C + r"([EW])\b")
DECIMAL_PAIR = re.compile(r"(?:lat(?:itude)?)\s*[:=]?\s*(-?\d{1,2}\.\d{2,})\s*[,;/ ]+\s*"
                          r"(?:lon(?:g(?:itude)?)?)\s*[:=]?\s*(-?\d{1,3}\.\d{2,})", re.IGNORECASE)

PREPARED_BY = re.compile(r"(?:prepared|submitted)\s+by\s*[:\-]?\s*(?:M/s\.?\s*)?"
                         r"([A-Z][^\n;]{3,120}?)(?:\s+for\s+the\b|\s+for\b|\s*\n|\.\s*$|;|$)",
                         re.IGNORECASE)
# "EIA Consultant\n\nVimta Labs Ltd," / "Name of the EIA Consultant Organization: Falcon ..."
CONSULTANT_LABEL = re.compile(r"EIA\s+consultant(?:\s+organi[sz]ation)?\s*[:\-]?\s*"
                              r"(?:M/s\.?\s*)?([A-Z][^\n,;]{3,100})", re.IGNORECASE)
GENERIC = re.compile(r"accredit|^QCI|^NABET|^the\b|^name\b|^certificate|^organi[sz]ation",
                     re.IGNORECASE)
FIRM = re.compile(r"\b((?:M/s\.?\s*)?[A-Z][A-Za-z&\- ]{2,60}?\s(?:(?:Pvt\.?|Private)\s*\.?\s*)?"
                  r"(?:Ltd\.?|Limited)|[A-Z][A-Za-z&\- ]{2,60}\s(?:Labs|Laboratories)"
                  r"(?:\s(?:Pvt\.?|Private)?\s*(?:Ltd\.?|Limited))?)")
PROJECT_LINE = re.compile(r"\b(project|expansion|port|terminal|airport|highway|road|mine|"
                          r"mining|plant|power|township|development|corridor|dam|harbour|"
                          r"jetty|refinery|industrial|railway|irrigation)\b", re.IGNORECASE)
NOT_TITLE = re.compile(r"\.{4,}|^\s*(table|figure|fig\.|chapter|contents|page|annexure|annex)\b|"
                       r"currency|abbreviation|proponent|^project\s*:?$", re.IGNORECASE)

FIELDS = ("project", "state", "site", "consultant", "year")


def field(value, page, how, quote=""):
    return {"value": value, "page": page, "how": how, "quote": " ".join(str(quote).split())[:200]}


def _texts(pages, n=FIRST_PAGES):
    return [(p["page"], p.get("text") or "") for p in pages[:n] if (p.get("text") or "").strip()]


def find_state(pages):
    counts, first = Counter(), {}
    for no, text in _texts(pages):
        for name, pat in _STATE_PATTERNS:
            hits = pat.findall(text)
            if hits:
                counts[name] += len(hits)
                first.setdefault(name, no)
    if not counts:
        return None
    name, n = counts.most_common(1)[0]
    return field(name, first[name], "text search", f"“{name}” named {n} times on the first pages")


def _deg(d, m, s, hemi):
    v = float(d) + float(m or 0) / 60 + float(s or 0) / 3600
    return -v if hemi in "SW" else v


def find_site(pages):
    """(lat, lon) as a field, or None. A latitude and a longitude on the same page."""
    for no, text in _texts(pages, len(pages)):
        flat = " ".join(text.split())
        lr, gr = LAT_RANGE.search(flat), LON_RANGE.search(flat)
        if lr and gr and abs(lr.start() - gr.start()) < 300:
            g, h = lr.groups(), gr.groups()
            lat = round((_deg(*g[:3], g[6]) + _deg(*g[3:6], g[6])) / 2, 4)
            lon = round((_deg(*h[:3], h[6]) + _deg(*h[3:6], h[6])) / 2, 4)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                a, b = sorted((lr, gr), key=lambda m: m.start())
                return field((lat, lon), no, "text search (midpoint of the stated range)",
                             flat[a.start():b.end()])
        dp = DECIMAL_PAIR.search(flat)
        if dp:
            lat, lon = float(dp.group(1)), float(dp.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return field((lat, lon), no, "text search", dp.group(0))
        la, lo = LAT.search(flat), LON.search(flat)
        if la and lo:
            lat, lon = _deg(*la.groups()), _deg(*lo.groups())
            if -90 <= lat <= 90 and -180 <= lon <= 180 and abs(la.start() - lo.start()) < 300:
                a, b = sorted((la, lo), key=lambda m: m.start())
                return field((round(lat, 4), round(lon, 4)), no, "text search",
                             flat[a.start():b.end()])
    return None


def _clean_name(s):
    s = " ".join(str(s).split()).strip(" ,:-–")
    return re.sub(r"^(?:M/s\.?\s*)", "", s)


def _good_name(s):
    s = _clean_name(s)
    return s if len(s) > 3 and not GENERIC.search(s) else None


def find_consultant(pages):
    """The EIA consultant: an "EIA consultant (organisation)" label, then "Prepared /
    Submitted by", then a firm name (Ltd / Labs) on a page about the consultant or NABET."""
    for pat in (CONSULTANT_LABEL, PREPARED_BY):
        for no, text in _texts(pages):
            for m in pat.finditer(text):
                name = _good_name(m.group(1))
                if name:
                    return field(name, no, "text search", m.group(0))
    for no, text in _texts(pages):
        if re.search(r"consultant|NABET|QCI", text, re.IGNORECASE):
            for m in FIRM.finditer(text):
                name = _good_name(m.group(1))
                if name and not re.search(r"\bport\b|\bauthority\b", name, re.IGNORECASE):
                    return field(name, no, "text search", m.group(0))
    return None


def find_project(pages):
    for no, text in _texts(pages)[:6]:
        lines = [" ".join(l.split()) for l in text.splitlines()]
        good = [l for l in lines if 12 <= len(l) <= 160 and PROJECT_LINE.search(l)
                and not NOT_TITLE.search(l) and sum(c.isalpha() for c in l) > len(l) * 0.6
                # an address ("PB No. 180, Port Blair") is not a title
                and (re.search(r"\bproject\b", l, re.I) or not re.search(r"\d|\bNo\.", l))]
        if good:
            best = max(good, key=lambda l: (bool(re.search(r"\bproject\b", l, re.I)), -len(l)))
            name = re.sub(r"^(?:India|Annex \d+ to)\s*:?\s*", "", best).strip()
            return field(name, no, "text search", best)
    return None


def find_year(pages):
    for no, text in _texts(pages)[:6]:
        hits = list(MONTH_YEAR.finditer(text))
        if hits:
            best = max(hits, key=lambda m: int(m.group(1)))
            return field(int(best.group(1)), no, "text search", best.group(0))
    return None


def letter_language(state_value):
    """{"value": "English, Hindi, Kannada", "regional": "Kannada", "translated": True} or
    the plain English + Hindi offer when the state's language has no letter yet."""
    lang = STATE_LANGUAGE.get(state_value or "")
    langs = ["English", "Hindi"] + ([lang] if lang and lang in LETTER_TRANSLATED else [])
    return {"value": ", ".join(langs), "regional": lang,
            "translated": bool(lang and lang in LETTER_TRANSLATED)}


def text_search(pages):
    return {"project": find_project(pages), "state": find_state(pages),
            "site": find_site(pages), "consultant": find_consultant(pages),
            "year": find_year(pages)}


# ---------- one Lightning call ----------

MODEL_PROMPT = (
    "You read the first pages of an Indian Environmental Impact Assessment report. Return "
    "JSON only: {\"project\": F, \"state\": F, \"consultant\": F, \"site\": F, \"year\": F} "
    "where each F is {\"value\": ..., \"page\": <page number>, \"quote\": <exact words copied "
    "from that page that show the value>} or null when the pages do not say it. project: the "
    "project's name as written. state: the Indian state or union territory. consultant: the "
    "firm or body that prepared the EIA. site: {\"lat\": <decimal degrees>, \"lon\": <decimal "
    "degrees>} only if the pages give coordinates. year: the report's year (4 digits). Never "
    "guess: null if the text does not state it.")


def _quote_on_page(quote, text):
    norm = lambda s: re.sub(r"\W+", " ", str(s)).lower().strip()
    q = norm(quote)
    return len(q) >= 4 and q in norm(text)


def model_detect(pages):
    """One Lightning call on the first pages. Fields whose quote is not on the cited page are
    dropped. Needs a key (llm raises otherwise)."""
    from tigerfish import claims, llm
    texts = dict(_texts(pages, MODEL_PAGES))
    body = "\n\n".join(f"[page {no}]\n{t[:MODEL_CHARS]}" for no, t in texts.items())
    raw = claims.chat_json(llm.LIGHTNING, [{"role": "system", "content": MODEL_PROMPT},
                                           {"role": "user", "content": body}], EST_OUT_TOKENS) or {}
    out = {}
    for name in FIELDS:
        f = raw.get(name) if isinstance(raw, dict) else None
        if not isinstance(f, dict) or f.get("value") in (None, "", {}):
            out[name] = None
            continue
        try:
            page = int(f.get("page"))
        except (TypeError, ValueError):
            out[name] = None
            continue
        if not _quote_on_page(f.get("quote", ""), texts.get(page, "")):
            out[name] = None
            continue
        value = f["value"]
        if name == "site":
            try:
                value = (float(value["lat"]), float(value["lon"]))
            except (TypeError, KeyError, ValueError):
                out[name] = None
                continue
        if name == "year":
            m = re.search(r"(19|20)\d\d", str(value))
            value = int(m.group(0)) if m else None
        if name == "state":
            value = STATE_ALIASES.get(value, value)
            if value not in STATES:
                out[name] = None
                continue
        out[name] = field(value, page, "model (Lightning), quote checked on the page",
                          f.get("quote", "")) if value not in (None, "") else None
    return out


def detect(pages, use_model=False):
    """{field: {"value", "page", "how", "quote"} | None, ..., "letter_language": {...},
    "model_error": str | None}. Text search first; the model (if used) fills the gaps and
    replaces the text-search project / consultant (it reads titles better)."""
    found = text_search(pages)
    error = None
    if use_model:
        try:
            got = model_detect(pages)
        except Exception as e:          # no key, network, budget: keep the text search
            got, error = {}, f"{type(e).__name__}: {e}"[:200]
        for name in FIELDS:
            if got.get(name) and (found.get(name) is None or name in ("project", "consultant")):
                found[name] = got[name]
    state = (found.get("state") or {}).get("value")
    return {**found, "letter_language": letter_language(state), "model_error": error}
