"""Consultant accreditation check: was the EIA consultant NABET (QCI) accredited for every
project sector and the project's category at the report date?

1. extract_details: LIGHTNING reads only the pages that mention NABET / accreditation /
   QCI / certificate / declaration (one batched call, cached) and returns each field with
   a verbatim quote + page; quotes are verified (or repaired) like claim quotes.
2. official_entry: Tavily (cached, credit-capped) on official QCI/NABET domains first,
   then the open web labelled "non-official source". The consultant's entry is located in
   the source text and its sector rows (number, name, category, schedule item) are parsed
   from that text: nothing about sectors is hardcoded.
   dated_records: official NABET records dated nearer the report (Accreditation Committee
   minutes naming the consultant). The record closest to the report date is compared.
3. compare: per project sector, the accredited sector whose source name matches it, and
   whether its category covers the project's category (an A accreditation covers A and B).
   ORANGE  an official record dated within 12 months of the report date shows a sector or
           category gap, or the accreditation had expired at the report date
   INFO    a gap shown only by an older (or non-official) record
   NONE    valid and covered; GREY if no entry is found or validity cannot be established.
Wording: "Accreditation could not be confirmed for [sector] at the report date. Verify."
"""

import re
from datetime import date
from urllib.parse import quote, urljoin, urlsplit

from tigerfish import claims as claims_mod
from tigerfish import copycheck, llm

KEYWORDS = re.compile(r"NABET|Accreditation|\bQCI\b|Certificate No|EIA Consultant|"
                      r"Declaration by Experts|Quality Council", re.IGNORECASE)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
OFFICIAL_DOMAINS = ["qcin.org", "nabet.qci.org.in", "qci.org.in", "eiameeting.qci.org.in"]
NON_OFFICIAL = "non-official source"
MAX_CREDITS = 15
ENTRY_CHARS = 6000             # how far an entry can run in the source text
MESSAGE = "Accreditation could not be confirmed for {sector} at the report date. Verify."
OLD_MESSAGE = ("Latest official list found ({source}) shows Category {category} for {sector}; "
               "status at the report date could not be confirmed.")
RECENT_DAYS = 365              # a gap counts (ORANGE) only in a record this close to the report

FIELDS = ("consultant_name", "certificate_number", "certificate_validity", "accredited_sectors",
          "accreditation_category", "report_date", "project_sectors", "project_category")
EXTRACT_PROMPT = """From these pages of an Indian EIA report, extract the EIA consultant's \
accreditation details and the project's own sectors and category. Return JSON only:
{"consultant_name": F, "certificate_number": F, "certificate_validity": F,
 "accredited_sectors": F, "accreditation_category": F, "report_date": F,
 "project_sectors": F, "project_category": F}
where each F is {"value": ..., "quote": "...", "page": N} or null if not stated.
- quote: copied character for character from the page text, one sentence or phrase.
- project_sectors value: a list of the project's components, e.g. ["port", "airport",
  "township", "power plant"]. project_category: "A" or "B" if stated.
- report_date: the date or month/year the report was issued (e.g. "December 2021").
Do not guess: use null when a field is not on these pages."""

# Words linking a project component to an accredited sector name in the source.
SECTOR_TERMS = {
    "port": ("port", "harbour", "harbor", "dredging"),
    "airport": ("airport", "air port", "aerodrome"),
    "township": ("township", "area development", "building and construction"),
    "power plant": ("power plant", "thermal power", "power"),
    "industrial estate": ("industrial estate", "special economic zone", "sez"),
}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}


# ---------- 1. details from the report ----------

def candidate_pages(pages):
    return [p for p in pages if KEYWORDS.search(p.get("text") or "")
            and not DEVANAGARI.search(p.get("text") or "")]


def extract_details(pages):
    """{field: {value, quote, page, verified, quote_repaired}} (fields not found are None)."""
    cands = candidate_pages(pages)
    body = "\n\n".join(f"=== Page {p['page']} ===\n{p['text'][:claims_mod.MAX_PAGE_CHARS]}"
                       for p in cands)
    raw = claims_mod.chat_json(llm.LIGHTNING, [{"role": "system", "content": EXTRACT_PROMPT},
                                               {"role": "user", "content": body}],
                               max_tokens=1500)
    texts = {p["page"]: p["text"] for p in cands}
    return parse_details(raw, texts), [p["page"] for p in cands]


# A field's quote must say what the field claims (the model sometimes fills
# "accredited_sectors" with the project's own schedule items).
FIELD_MUST_MENTION = {
    "accredited_sectors": re.compile(r"accredit|nabet", re.IGNORECASE),
    "accreditation_category": re.compile(r"accredit|nabet", re.IGNORECASE),
    "certificate_validity": re.compile(r"valid|expir", re.IGNORECASE),
}
CATEGORY_VALUE = re.compile(r"^\s*(?:category\s*)?['‘\"]?([AB])['’\"]?\s*$", re.IGNORECASE)


def locate(quote, page, texts):
    """(exact quote, page, repaired) on the stated page, else on any other searched page."""
    order = [page] + [p for p in texts if p != page]
    for p in order:
        text = texts.get(p, "")
        if claims_mod.quote_on_page(quote, text):
            return claims_mod.normalize(quote), p, False
        exact, _ = claims_mod.repair_quote(quote, text) if quote else (None, 0)
        if exact:
            return exact, p, True
    return None, page, False


def parse_details(raw, texts):
    """Validate the model's JSON: each field needs a quote found on a searched page, and the
    quote must support the field (see FIELD_MUST_MENTION / CATEGORY_VALUE)."""
    out = {}
    for field in FIELDS:
        item = (raw or {}).get(field) if isinstance(raw, dict) else None
        if not isinstance(item, dict) or item.get("value") in (None, "", []):
            out[field] = None
            continue
        quote, page = str(item.get("quote") or ""), item.get("page")
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = None
        exact, page, repaired = locate(quote, page, texts)
        value = item["value"]
        if field in FIELD_MUST_MENTION and not FIELD_MUST_MENTION[field].search(exact or quote):
            out[field] = None                     # quote does not support this field
            continue
        if field in ("project_category", "accreditation_category"):
            m = CATEGORY_VALUE.match(str(value))
            if not m:
                out[field] = None
                continue
            value = m.group(1).upper()
        out[field] = {"value": value, "quote": exact or claims_mod.normalize(quote), "page": page,
                      "verified": exact is not None, "quote_repaired": repaired}
    return out


COMPONENT_KEYS = (("airport", r"airport|air port|aerodrome"),      # before "port"
                  ("port", r"(?<!air)(?<!air )port\b|harbou?r|transs?hipment|terminal|jetty|berth"),
                  ("township", r"township|area development|housing"),
                  ("power plant", r"power plant|power station|\bmva\b|\bmw\b"))


def component_key(component):
    """'International Container Transshipment Terminal' -> 'port' (or the text itself)."""
    low = str(component).lower()
    for key, pattern in COMPONENT_KEYS:
        if re.search(pattern, low):
            return key
    return low.strip()


CERTIFICATE = re.compile(r"NABET/EIA/[\w\-]+/[A-Z]{2,4}\s?\d{3,4}")


def certificate_numbers(pages):
    """Distinct NABET certificate numbers stated in the report's text, in page order:
    [{number, page, quote, also_on}]. Spacing and hyphens are ignored when comparing
    ("23-26" = "2326"), so only numbers that really differ count as distinct."""
    found = {}
    for p in pages:
        text = claims_mod.normalize(p.get("text") or "")
        if DEVANAGARI.search(text):
            continue
        for m in CERTIFICATE.finditer(text):
            key = re.sub(r"[^A-Z0-9]", "", m.group(0).upper())
            if key in found:
                if p["page"] != found[key]["page"] and p["page"] not in found[key]["also_on"]:
                    found[key]["also_on"].append(p["page"])
                continue
            start = max(text.rfind(". ", 0, m.start()) + 2, m.start() - 100, 0)
            if start > 0 and text[start - 1] != " ":      # start on a whole word
                start = text.find(" ", start) + 1
            end = text.find(".", m.end())
            end = min(end + 1 if end != -1 else len(text), m.end() + 80)
            found[key] = {"number": m.group(0), "page": p["page"],
                          "quote": text[start:end].strip(), "also_on": []}
    return list(found.values())


# ---------- 2. official entry ----------

def find_entry(text, consultant):
    """The consultant's entry in a list of accredited organisations (normalised text), or ''."""
    t = claims_mod.normalize(text)
    words = [w for w in re.findall(r"[A-Za-z]+", consultant or "") if len(w) > 2][:2]
    if not words:
        return ""
    m = re.search(r"\b" + r"\W+".join(map(re.escape, words)), t, re.IGNORECASE)
    if not m:
        return ""
    # an entry starts at its serial number ("154 Vimta Labs ...") and ends at the next one
    start = max(t.rfind(" ", 0, max(0, m.start() - 1)), 0)
    rest = t[m.end():m.end() + ENTRY_CHARS]
    nxt = re.search(r"\s\d{1,3}\s[A-Z][\w.&,\- ]{2,80}?Address:", rest)
    return t[start:m.end() + (nxt.start() if nxt else len(rest))].strip()


SECTOR_ROW = re.compile(r"(?<!\()\b(\d{1,2})\s+([A-Z][^()]*?(?:\([^)]*\)[^()]*?)*?)\s+([AB])\s+"
                        r"(\d{1,2}\s*\([a-z]\)(?:\s*\([ivx]+\))?)")
PAGE_HEADER = re.compile(r"Scheme for Accreditation.*?Sector Number Name of Sector Category\s*")


def parse_sectors(entry):
    """[{number, name, category, schedule, quote}] parsed from the entry text."""
    clean = PAGE_HEADER.sub(" ", entry)
    clean = re.sub(r"^.*?Conditions apply\s*", "", clean, count=1)
    rows = []
    for m in SECTOR_ROW.finditer(clean):
        rows.append({"number": int(m.group(1)), "name": m.group(2).strip(),
                     "category": m.group(3), "schedule": " ".join(m.group(4).split()),
                     "quote": " ".join(m.group(0).split())})
    return rows


def source_revision(text):
    m = re.search(r"Rev\.\s*\d+,\s*([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    return m.group(0) if m else None


def queries(consultant, certificate=None):
    """Search wordings, most specific first. In testing, the official list PDF was found with
    the full company form ("Limited", not "Ltd") and the certificate's first three parts
    ("NABET/EIA/1720", not ".../SA 088")."""
    name = full_name(consultant)
    out = []
    if certificate:
        prefix = "/".join(str(certificate).split("/")[:3]).strip()
        out.append(f"{name} {prefix} accreditation validity sectors")
    out.append(f"List of Accredited EIA Consultant Organizations {name}")
    return list(dict.fromkeys(out))


def _entry_from(results, texts, consultant, query, label_of):
    for r in results:
        text = texts.get(r["url"]) or ""
        entry = find_entry(text, consultant)
        sectors = parse_sectors(entry) if entry else []
        if sectors:
            return {"url": r["url"], "label": label_of(r["url"]), "entry": entry, "sectors": sectors,
                    "revision": source_revision(text), "validity": validity_in(entry),
                    "query": query}
    return None


def is_official_url(url):
    h = (urlsplit(url or "").hostname or "").lower()
    return any(h == d or h.endswith("." + d) for d in OFFICIAL_DOMAINS)


def legacy_cached(consultant, certificate=None):
    """True if this consultant was checked with the old two-step search (official domains,
    then the open web) and that run is in the cache: it is replayed as it was."""
    return copycheck.is_cached("search", query=queries(consultant, certificate)[0],
                               search_depth="basic", max_results=copycheck.SEARCH_RESULTS,
                               exact_match=False, include_domains=list(OFFICIAL_DOMAINS))


def official_entry(consultant, budget, certificate=None):
    """The consultant's entry in the official list. Entry dict or None.

    One search per wording with the official QCI/NABET domains preferred
    (include_domains_mode="prefer"), official results first; the list PDFs are read with
    extract_depth="advanced" (sector tables). Runs cached with the old two-step search are
    replayed with it (no new credits, same result)."""
    if legacy_cached(consultant, certificate):
        return _official_entry_two_step(consultant, budget, certificate)
    label_of = lambda u: "official source" if is_official_url(u) else NON_OFFICIAL   # noqa: E731
    for query in queries(consultant, certificate):
        results = copycheck.search(query, budget, exact=False, include_domains=OFFICIAL_DOMAINS,
                                   include_domains_mode="prefer").get("results", [])
        results = sorted(results[:5], key=lambda r: not is_official_url(r["url"]))
        texts = copycheck.extract([r["url"] for r in results], budget, max_chars=None,
                                  depth="advanced")
        found = _entry_from(results, texts, consultant, query, label_of)
        if found:
            return found
    return None


def _official_entry_two_step(consultant, budget, certificate=None):
    """Old method (kept for cached replays): official domains (each wording), then the open web."""
    for domains, label in ((OFFICIAL_DOMAINS, "official source"), (None, NON_OFFICIAL)):
        for query in queries(consultant, certificate):
            results = copycheck.search(query, budget, exact=False,
                                       include_domains=domains).get("results", [])
            texts = copycheck.extract([r["url"] for r in results[:5]], budget, max_chars=None)
            found = _entry_from(results, texts, consultant, query, lambda u, lab=label: lab)
            if found:
                return found
    return None


def consultant_words(consultant):
    return [w for w in re.findall(r"[A-Za-z]+", consultant or "") if len(w) > 2][:2]


def full_name(consultant):
    name = re.sub(r"\bLtd\b\.?", "Limited", consultant or "")
    return re.sub(r"\bPvt\b\.?", "Private", name)


# Accreditation Committee minutes: "accredited for sectors 2(A), 4(A), ... and 39(B)"
COMPACT_SECTORS = re.compile(r"accredited for sectors?\s+((?:\d{1,2}\s*\([AB]\)[,\s]*(?:and\s+)?)+)")
# Minutes scope table: "13. 33 Ports, harbours, break waters and dredging B 7 (e)"
SCOPE_ROW = re.compile(r"\b\d{1,2}\.\s+(\d{1,2})\s+([A-Z][^()]*?(?:\([^)]*\)[^()]*?)*?)\s+([AB])\s+"
                       r"(\d{1,2}\s*\([a-z]\)|-)")
MEETING_DATE = re.compile(r"held\b[^.]{0,80}?\b([A-Z][a-z]+ \d{1,2}, \d{4})")
MEETING_LINK = re.compile(r"\[(\d+) / (\d{4}) : (\d{2}-\d{2}-\d{4})\]\((meetings/.+?\.pdf)\)")


def record_sectors(text, consultant, names=None):
    """Sector rows for the consultant in Accreditation Committee minutes: the compact list
    ("33(B)") or the scope table. Names for compact rows come from `names` (number -> name,
    taken from the accredited list), never from a hardcoded table."""
    t = claims_mod.normalize(text)
    words = consultant_words(consultant)
    m = re.search(r"\b" + r"\W+".join(map(re.escape, words)), t, re.IGNORECASE) if words else None
    if not m:
        return []
    seg = t[m.start():m.start() + ENTRY_CHARS]
    rows = {}
    c = COMPACT_SECTORS.search(seg)
    if c:
        for n, cat in re.findall(r"(\d{1,2})\s*\(([AB])\)", c.group(1)):
            rows.setdefault(int(n), {"number": int(n), "name": (names or {}).get(int(n), f"sector {n}"),
                                     "category": cat, "schedule": "", "quote": c.group(0).strip()})
    elif "Scope of Accreditation" in seg:
        scope = seg[seg.find("Scope of Accreditation"):].split("Functional Areas (FA)")[0]
        for r in SCOPE_ROW.finditer(scope):
            rows.setdefault(int(r.group(1)), {"number": int(r.group(1)), "name": r.group(2).strip(),
                                              "category": r.group(3), "schedule": " ".join(r.group(4).split()),
                                              "quote": " ".join(r.group(0).split())})
    return sorted(rows.values(), key=lambda r: r["number"])


def meeting_links(listing_text, listing_url, consultant):
    """[(date, title, url)] of minutes in a NABET meetings listing that name the consultant."""
    words = consultant_words(consultant)
    out = []
    for block in re.split(r"\n\s*\* (?=\[)", listing_text):
        m = MEETING_LINK.search(block)
        if not m or not words or not all(w.lower() in block.lower() for w in words):
            continue
        d, mo, y = m.group(3).split("-")
        parts = urlsplit(urljoin(listing_url, m.group(4)))
        url = f"{parts.scheme}://{parts.netloc}{quote(parts.path, safe='/._-')}"
        out.append((date(int(y), int(mo), int(d)), f"AC meeting {m.group(1)}/{m.group(2)}", url))
    return out


def fmt_date(d):
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def dated_records(consultant, report_d, budget, names=None):
    """Official records for the consultant dated near the report: [{url, label, kind, date,
    revision, sectors, validity}]. Official domains only."""
    if not report_d:
        return []
    query = f"List of Accredited EIA Consultant Organizations Rev. {report_d.year} {full_name(consultant)}"
    results = copycheck.search(query, budget, exact=False,
                               include_domains=OFFICIAL_DOMAINS).get("results", [])[:5]
    texts = copycheck.extract([r["url"] for r in results], budget, max_chars=None)
    records, links = [], []
    for r in results:
        text = texts.get(r["url"]) or ""
        if "meeting_list" in r["url"]:
            links += meeting_links(text, r["url"], consultant)
            continue
        md = MEETING_DATE.search(claims_mod.normalize(text))
        sectors = record_sectors(text, consultant, names)
        if md and sectors:
            d = to_date(md.group(1))
            records.append({"url": r["url"], "label": "official source", "kind": "Accreditation Committee minutes",
                            "date": d, "revision": f"AC meeting, {fmt_date(d)}", "sectors": sectors,
                            "validity": None, "query": query})
    # follow only the listed meeting closest to the report date (one extract)
    seen = {r["date"] for r in records}
    links = sorted({l for l in links if l[0] not in seen}, key=lambda l: abs((l[0] - report_d).days))
    for d, title, url in links[:1]:
        for u in dict.fromkeys((url, url.replace("https://", "http://", 1))):   # some PDFs only fetch over http
            text = copycheck.extract([u], budget, max_chars=None).get(u) or ""
            sectors = record_sectors(text, consultant, names)
            if sectors:
                records.append({"url": u, "label": "official source", "kind": "Accreditation Committee minutes",
                                "date": d, "revision": f"{title}, {fmt_date(d)}", "sectors": sectors,
                                "validity": None, "query": query})
                break
    return records


def closest_record(records, report_d):
    """The record dated closest to the report date (the earlier one wins a tie)."""
    dated = [r for r in records if r.get("date")]
    if not dated or not report_d:
        return records[0] if records else None
    return min(dated, key=lambda r: (abs((r["date"] - report_d).days), r["date"] > report_d))


def validity_in(entry):
    """A validity / expiry date stated in the entry, or None."""
    m = re.search(r"valid(?:ity)?\s*(?:up\s*to|till|until)?\s*:?\s*([0-3]?\d[./-][01]?\d[./-]\d{4}|"
                  r"[A-Z][a-z]+ \d{1,2}, \d{4})", entry, re.IGNORECASE)
    return m.group(1) if m else None


# ---------- 3. compare ----------

def to_date(text):
    """Best-effort date from '10.07.2019', 'July 10, 2019' or 'December 2021' (first of month)."""
    if not text:
        return None
    s = str(text)
    m = re.search(r"([0-3]?\d)[./-]([01]?\d)[./-](\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m.group(1).lower() in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
    m = re.search(r"([A-Za-z]+)[ ,]+(\d{4})", s)
    if m and m.group(1).lower() in MONTHS:
        return date(int(m.group(2)), MONTHS[m.group(1).lower()], 1)
    return None


def matching_sector(component, sectors):
    """The accredited sector whose source name matches a component key. Terms are tried in
    priority order ("township" before "building and construction"); "port" never matches
    "Air ports"."""
    terms = SECTOR_TERMS.get(component.lower().strip(), (component.lower(),))
    for t in terms:
        for s in sectors:
            name = s["name"].lower()
            if not re.search(r"\b" + re.escape(t) + r"\w*", name):
                continue
            if component == "port" and re.search(r"\bair\s*ports?\b", name):
                continue
            return s
    return None


def compare(details, entry):
    """{grade, rows: per sector, validity note, message(s)}."""
    if entry is None:
        return {"grade": "GREY", "rows": [], "validity": "official accreditation entry not found",
                "messages": []}
    project = (details.get("project_sectors") or {}).get("value") or []
    if isinstance(project, str):
        project = [p.strip() for p in re.split(r",|;| and ", project) if p.strip()]
    pcat = str(((details.get("project_category") or {}).get("value")) or "").upper().strip()
    pcat = "A" if pcat.startswith("A") or "CATEGORY A" in pcat else "B" if pcat.startswith("B") else ""
    rows, problems = [], []
    for comp in project:
        key = component_key(comp)
        s = matching_sector(key, entry["sectors"])
        covered = bool(s) and (s["category"] == "A" or pcat in ("B", ""))
        rows.append({"component": comp, "key": key, "sector": s,
                     "project_category": pcat or "not stated", "covered": covered,
                     "why": ("no accredited sector matches" if not s else
                             f"accredited for Category {s['category']} only; project is Category {pcat}"
                             if not covered else "covered")})
        if not covered:
            problems.append(f"{comp} ({key})")
    report_d = to_date(((details.get("report_date") or {}).get("value")))
    valid_d = to_date(entry.get("validity"))
    rev_d = to_date(entry.get("revision"))
    if valid_d and report_d and valid_d < report_d:
        validity = f"expired on {valid_d.isoformat()}, before the report date {report_d.isoformat()}"
        problems.append("all sectors (accreditation expired)")
    elif valid_d:
        validity = f"valid until {valid_d.isoformat()}"
    elif rev_d and report_d and rev_d < report_d:
        validity = (f"the source states no validity date; the source ({entry['revision']}) "
                    f"predates the report date ({report_d.strftime('%B %Y')}), so status at the "
                    f"report date could differ")
    else:
        validity = "the source states no validity date"
    src_d = entry.get("date") or rev_d
    recent = bool(entry.get("label") == "official source" and src_d and report_d
                  and abs((src_d - report_d).days) <= RECENT_DAYS)
    expired = bool(valid_d and report_d and valid_d < report_d)
    if problems and not recent and not expired:
        # the gap is only in an older (or non-official) record: not a finding at the report date
        source = ", ".join(x for x in (entry.get("revision") or (fmt_date(src_d) if src_d else "undated"),
                                       entry.get("label") if entry.get("label") != "official source" else None)
                           if x)
        return {"grade": "INFO", "rows": rows, "validity": validity, "recent": False,
                "messages": [OLD_MESSAGE.format(source=source,
                                                category=r["sector"]["category"] if r["sector"] else "none",
                                                sector=f"{r['component']} ({r['key']})")
                             for r in rows if not r["covered"]]}
    if problems:
        grade = "ORANGE"
    elif valid_d:
        grade = "NONE"
    else:
        grade = "GREY"            # covered per the source, but validity at report date unknown
    return {"grade": grade, "rows": rows, "validity": validity, "recent": recent,
            "messages": [MESSAGE.format(sector=p) for p in problems]}


def check(pages, max_credits=MAX_CREDITS):
    details, searched = extract_details(pages)
    name = (details.get("consultant_name") or {}).get("value")
    cert = (details.get("certificate_number") or {}).get("value")
    report_d = to_date((details.get("report_date") or {}).get("value"))
    budget = copycheck.Budget(max_credits)
    records = []
    try:
        entry = official_entry(name, budget, cert) if name else None
        if entry:
            records = [{**entry, "kind": "accredited list", "date": to_date(entry.get("revision"))}]
            names = {s["number"]: s["name"] for s in entry["sectors"]}
            if entry["label"] == "official source":
                records += dated_records(name, report_d, budget, names)
    except copycheck.CreditCapReached:
        pass
    used = closest_record(records, report_d)
    result = compare(details, used)
    return {"details": details, "pages_searched": searched, "entry": used, "records": records,
            **result, "tavily_credits": budget.used}
