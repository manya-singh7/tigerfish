"""Knowable at the time: was the point of a verified finding already in public sources
dated BEFORE the report?

For each human-verified finding (data/known_issues.json, via the finding's known_issue id)
and each species flag:
1. search   Tavily search with end_date = the report date, official and scientific domains
            preferred (include_domains_mode="prefer"; other sites can still appear).
2. extract  Tavily extract of the top results (full text).
3. date     the source's publish date: Tavily's published_date, else a date stated in the
            source (header, title block, "Published ..." line, URL path). A source with no
            date, or dated on/after the report date, is dropped.
4. support  LIGHTNING picks one sentence that states the point (copied verbatim); the
            sentence must be found in the extracted text (whitespace collapsed); then ULTRA
            confirms the sentence alone states the point. Anything else is dropped.

Output (results/knowable_<report id>.json) is shown on a card only when a source passed every
step: "Public sources before this report already described: [quote] ([source], [date])."
No source: nothing is shown (no badge). Every Tavily and model call is cached and capped.
"""

import json
import re
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

from tigerfish import claims as claims_mod
from tigerfish import copycheck, llm
from tigerfish.official_record import (MONTH_NAMES, MONTHS, OFFICIAL_DOMAINS, OTHER_OFFICIAL_DOMAINS,
                                       _mk, _parse, document_date, host, source_label)

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

REPORT_DATES = {   # the report's own date: sources must be dated strictly before it
    "great_nicobar_2021_draft": date(2021, 12, 27),   # draft EIA released for public hearing
    "indira_point_table_3_16": date(2026, 4, 1),      # REIA dated April 2026: before the month
}
SCIENTIFIC_DOMAINS = ["gbif.org", "iucnredlist.org", "zsi.gov.in", "bsi.gov.in", "wii.gov.in",
                      "fao.org", "sealifebase.se", "fishbase.se", "threatenedtaxa.org",
                      "currentscience.ac.in", "ncbi.nlm.nih.gov", "biotaxa.org", "niscpr.res.in"]
PREFERRED_DOMAINS = OFFICIAL_DOMAINS + OTHER_OFFICIAL_DOMAINS + ["prsindia.org"] + SCIENTIFIC_DOMAINS
MAX_RESULTS = 5
EXTRACT_TOP = 3            # top results per search whose text is extracted
KEEP_PER_FINDING = 2       # supported sources kept per finding
PASSAGE_CHARS = 6000       # text given to LIGHTNING per source (best paragraphs)
MAX_CREDITS = 70
MAX_NEBIUS_USD = 0.25
CARD_TEXT = "Public sources before this report already described:"

# finding id -> what a public source would have to state, and the search query.
TOPICS = {
    "great_nicobar_2021_draft": {
        "ct-031": ("Coral reefs are present in Galathea Bay, Great Nicobar Island.",
                   "Galathea Bay Great Nicobar coral reef"),
        "ct-071": ("Coral reefs are present in Galathea Bay, Great Nicobar Island.",
                   "Galathea Bay Great Nicobar coral reef"),
        "ct-979": ("A count of the plant species (flora) of Great Nicobar Island or the Great "
                   "Nicobar Biosphere Reserve.",
                   "Great Nicobar Biosphere Reserve flora number of plant species"),
        "ct-403": ("A count of the animal species (fauna) of Great Nicobar Island or the Great "
                   "Nicobar Biosphere Reserve.",
                   "Great Nicobar Biosphere Reserve fauna number of animal species"),
        "rf-009": ("A count of the plant species of Campbell Bay National Park or of Galathea "
                   "National Park.",
                   "Campbell Bay National Park Galathea National Park flora species"),
        "rf-010": ("A count of the animal species of Campbell Bay National Park or of Galathea "
                   "National Park.",
                   "Campbell Bay National Park Galathea National Park fauna species"),
        "ct-239": ("The annual rainfall of Great Nicobar Island or the Nicobar Islands, with "
                   "its amount.",
                   "Great Nicobar Island annual rainfall mm"),
        "sp-p954-001": ("Panulirus interruptus (California spiny lobster) is found in the "
                        "eastern Pacific (California and Mexico).",
                        "Panulirus interruptus California spiny lobster distribution"),
        "ac-01": ("Vimta Labs' NABET accreditation as an EIA consultant, with its sectors or "
                  "categories.",
                  "Vimta Labs NABET accredited EIA consultant organization sectors category"),
        "pr-06": ("EIA baseline data, including ecology, is to be collected over one season "
                  "or three months.",
                  "EIA baseline data collection one season three months ecology MoEF"),
    },
    "indira_point_table_3_16": {
        "sp-01": ("Axis axis (chital) is not native to the Nicobar Islands: it is absent there, "
                  "or recorded there only as introduced.",
                  "Axis axis chital spotted deer Andaman Nicobar Islands introduced"),
        "sp-02": ("Rusa unicolor (Cervus unicolor, sambar) is not native to the Nicobar Islands: "
                  "it is absent there, or recorded there only as introduced.",
                  "Rusa unicolor sambar distribution Andaman Nicobar"),
        "sp-03": ("Felis chaus (jungle cat) is not native to the Nicobar Islands: it is absent "
                  "there, or recorded there only as introduced.",
                  "Felis chaus jungle cat distribution India Andaman Nicobar"),
        "sp-04": ("Funambulus pennantii (northern palm squirrel) is not native to the Nicobar "
                  "Islands: it is absent there, or recorded there only as introduced.",
                  "Funambulus pennantii palm squirrel Andaman Nicobar"),
        "sp-05": ("Muntiacus muntjak (barking deer) is not native to the Nicobar Islands: it is "
                  "absent there, or recorded there only as introduced.",
                  "Muntiacus muntjak barking deer distribution Andaman Nicobar"),
        "st-06": ("Macaca fascicularis (long-tailed macaque) is assessed as Endangered on the "
                  "IUCN Red List.",
                  "Macaca fascicularis long-tailed macaque IUCN Red List Endangered"),
        "st-07": ("The Wild Life (Protection) Amendment Act, 2022 reduced the schedules to four "
                  "(the vermin schedule, Schedule V, was removed).",
                  "Wild Life (Protection) Amendment Act 2022 schedules reduced to four vermin"),
    },
}

SUPPORT_PROMPT = """You check whether a source text states a given point.
Point: {point}
Copy ONE sentence (or two adjacent sentences) from the source text that states the point \
directly, exactly as written, character for character. Do not paraphrase, fix or shorten it. \
If no sentence states the point directly, answer supports=false.
Return JSON only: {{"supports": true or false, "quote": "the copied sentence or empty"}}"""

CONFIRM_PROMPT = """Point: {point}
Quote from a public source: "{quote}"
Does the quote, read on its own, directly state the point (not merely mention the same \
place or species)? Return JSON only: {{"states_point": "yes" or "no", "why": "one short sentence"}}"""


# ---------- which findings ----------

def verified_findings(report):
    """Findings with a human verification (not explained / negative controls) plus every
    species flag, in report order: [(finding, point, query)] for those with a topic."""
    topics = TOPICS.get(report["id"], {})
    out = []
    for f in report["findings"]:
        human = bool(f.get("verification")) and \
            (f["verification"].get("outcome") or "confirmed") != "explained"
        species = f["check"] in ("species_range", "iucn_status", "legal_schedule")
        if (human or species) and f["id"] in topics:
            out.append((f, *topics[f["id"]]))
    return out


# ---------- dates ----------

LABEL = r"(?:Published(?: online)?|Date of publication|Publication date|Date assessed|Assessment date|Posted on)"
PUBLISHED_PATTERNS = [   # (regex, kind) for official_record._parse, plus "ymd" and "year"
    (rf"{LABEL}\s*[:\-]?\s*(\d{{1,2}})\s+({MONTH_NAMES})\s*,?\s*(\d{{4}})", "dmy"),
    (rf"{LABEL}\s*[:\-]?\s*({MONTH_NAMES})\s+(\d{{1,2}}),\s*(\d{{4}})", "mdy"),
    (rf"{LABEL}\s*[:\-]?\s*({MONTH_NAMES})\s*,?\s*(\d{{4}})", "my"),          # ZSI: Published : March, 2008
    (rf"{LABEL}\s*[:\-]?\s*(\d{{4}})-(\d{{2}})-(\d{{2}})", "ymd"),
    (r"Published(?: online)?:?\s+(\d{4})\s+([A-Z][a-z]{2})\s+(\d{1,2})\b", "pmc"),   # PMC: 2020 Aug 20
    (rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_NAMES}),?\s*(\d{{4}})\s+and is hereby published", "dmy"),  # Gazette
    (r"(?:Year published|Date assessed|Assessment year)\s*[:\-]?\s*(\d{4})\b", "year"),
]


def parse_tavily_date(value):
    """Tavily's published_date (ISO or RFC 2822) as a date, or None."""
    if not value:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if m:
        return _mk(*m.groups())
    try:
        return parsedate_to_datetime(str(value)).date()
    except (TypeError, ValueError, IndexError):
        return None


def _parse_kind(groups, kind):
    if kind == "ymd":
        return _mk(*groups)
    if kind == "pmc":
        return _mk(groups[0], MONTHS.get(groups[1][:3].lower(), 0), groups[2])
    if kind == "year":
        return _mk(groups[0], 12, 31)          # year only: counted as its last day
    return _parse(groups, kind)


def publish_date(result, text):
    """(date, the text it was read from) or (None, ""): Tavily's published_date, else a date
    the source states about itself (header, title block, URL path, imprint)."""
    d = parse_tavily_date(result.get("published_date"))
    if d:
        return d, f"Tavily published_date {result['published_date']}"
    d, quote = document_date(text, result.get("url", ""))
    if d:
        return d, quote
    flat = " ".join((text or "").split())[:20000]
    for pattern, kind in PUBLISHED_PATTERNS:
        m = re.search(pattern, flat, re.IGNORECASE)
        d = _parse_kind(m.groups(), kind) if m else None
        if d:
            return d, m.group(0)
    return None, ""


# ---------- support ----------

PARA_CHARS = 900   # long paragraphs (PDF text often has no line breaks) are cut into pieces


def plain_text(text):
    """Extracted markdown as plain text: [label](url) -> label, images and emphasis marks
    dropped. Quotes are copied from, and verified against, this text."""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text or "")
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    return re.sub(r"(\*\*|\*|__)(?=\S)|(?<=\S)(\*\*|\*|__)", "", t)


def paragraphs(text):
    out = []
    for p in re.split(r"\n", text or ""):
        p = p.strip()
        while len(p) > PARA_CHARS:
            cut = p.rfind(". ", 0, PARA_CHARS)
            cut = cut + 1 if cut > PARA_CHARS // 3 else PARA_CHARS
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if len(p) > 30:
            out.append(p)
    return out


def best_passages(text, point, limit=PASSAGE_CHARS):
    """The paragraphs of a source sharing the most words with the point, in source order."""
    words = {w for w in re.findall(r"[a-z]{4,}", point.lower())}
    paras = paragraphs(text)
    scored = sorted(range(len(paras)),
                    key=lambda i: -len(words & set(re.findall(r"[a-z]{4,}", paras[i].lower()))))
    keep, size = [], 0
    for i in scored:
        if size + len(paras[i]) > limit:
            continue
        keep.append(i)
        size += len(paras[i])
    return "\n\n".join(paras[i] for i in sorted(keep))


def verified_quote(quote, text):
    """The quote as it appears in the extracted text (exact after whitespace collapse), or None."""
    if not quote or len(quote.split()) < 4:
        return None
    if claims_mod.quote_on_page(quote, text):
        return claims_mod.normalize(quote)
    fixed, _ = claims_mod.repair_quote(quote, text, min_similarity=0.97)
    return fixed


def supporting_quote(point, text):
    """(quote, why) if a sentence of the text states the point, else (None, reason)."""
    text = plain_text(text)
    passages = best_passages(text, point)
    if not passages:
        return None, "no text"
    raw = claims_mod.chat_json(llm.LIGHTNING, [
        {"role": "system", "content": SUPPORT_PROMPT.format(point=point)},
        {"role": "user", "content": f"Source text:\n{passages}"}], max_tokens=600)
    if not isinstance(raw, dict) or not raw.get("supports"):
        return None, "no sentence states the point"
    quote = verified_quote(str(raw.get("quote") or ""), text)
    if not quote:
        return None, "quote not found in the extracted text"
    ok = claims_mod.chat_json(llm.ULTRA, [
        {"role": "user", "content": CONFIRM_PROMPT.format(point=point, quote=quote)}],
        max_tokens=3000, thinking=False)
    if not isinstance(ok, dict) or str(ok.get("states_point", "")).lower() != "yes":
        return None, "Ultra: the quote does not state the point"
    return quote, str(ok.get("why") or "")


# ---------- Tavily ----------

def search(query, report_date, budget):
    return copycheck.tavily_call(
        "search", budget, 1, query=query, search_depth="basic", max_results=MAX_RESULTS,
        end_date=report_date.isoformat(), include_domains=PREFERRED_DOMAINS,
        include_domains_mode="prefer")


def credits_of(data, estimate):
    c = (data.get("usage") or {}).get("credits")
    return c if isinstance(c, (int, float)) else estimate


def counted_call(stats, endpoint, budget, est, **params):
    """copycheck.tavily_call, adding the credits Tavily reported for the response (also for a
    cached replay) to stats["credits"], so saved totals do not depend on the cache."""
    data = copycheck.tavily_call(endpoint, budget, est, **params)
    stats["credits"] = stats.get("credits", 0) + credits_of(data, est)
    return data


# ---------- run ----------

def check_finding(finding, point, query, report_date, budget, stats):
    data = search(query, report_date, budget)
    stats["searches"] += 1
    stats["credits"] += credits_of(data, 1)
    results = data.get("results", [])[:EXTRACT_TOP]
    texts = {}
    if results:
        urls = sorted(r["url"] for r in results)
        ex = copycheck.tavily_call("extract", budget, 1, urls=urls, extract_depth="basic")
        stats["extracts"] += 1
        stats["credits"] += credits_of(ex, 1)
        texts = {r["url"]: r.get("raw_content") or "" for r in ex.get("results", [])}
    sources, dropped = [], []
    for r in results:
        url, text = r["url"], texts.get(r["url"]) or ""
        d, how = publish_date(r, text)
        if d is None:
            dropped.append({"url": url, "why": "publish date not found"})
            continue
        if d >= report_date:
            dropped.append({"url": url, "why": f"dated {d.isoformat()}, not before the report"})
            continue
        quote, why = supporting_quote(point, text)
        if not quote:
            dropped.append({"url": url, "why": why})
            continue
        sources.append({"url": url, "title": r.get("title") or host(url), "host": host(url),
                        "label": source_label(url), "date": d.isoformat(), "date_found": how,
                        "quote": quote, "why": why,
                        "quote_check": "exact text of the Tavily-extracted source"})
        if len(sources) >= KEEP_PER_FINDING:
            break
    return {"finding_id": finding["id"], "title": finding["title"], "point": point,
            "query": query, "sources": sources, "dropped": dropped}


def run(report, budget=None, max_usd=MAX_NEBIUS_USD):
    """The check for one saved report dict. Returns the results dict."""
    report_date = REPORT_DATES[report["id"]]
    budget = budget or copycheck.Budget(MAX_CREDITS)
    stats = {"searches": 0, "extracts": 0, "credits": 0}
    start = llm.session_cost_usd
    out, stopped = [], None
    for f, point, query in verified_findings(report):
        if llm.session_cost_usd - start > max_usd:
            stopped = f"Nebius cost cap ${max_usd} reached"
            break
        try:
            out.append(check_finding(f, point, query, report_date, budget, stats))
        except copycheck.CreditCapReached as e:
            stopped = str(e)
            break
    return {"report_id": report["id"], "report_date": report_date.isoformat(),
            "card_text": CARD_TEXT, "findings": out, "stopped": stopped,
            "tavily": {**stats, "credits_spent_this_run": budget.used,
                       "features": ["search end_date", "include_domains_mode=prefer", "extract"]},
            "cost": {"nebius_usd_spent_this_run": round(llm.session_cost_usd - start, 4)},
            "method": {"preferred_domains": PREFERRED_DOMAINS, "extract_top": EXTRACT_TOP}}


def path(report_id):
    return RESULTS / f"knowable_{report_id}.json"


def load(report_id):
    p = path(report_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def card_lines(report_id, finding_id, data=None):
    """[(quote, source, date)] to show on a finding card; [] means show nothing."""
    data = data if data is not None else load(report_id)
    for f in (data or {}).get("findings", []):
        if f["finding_id"] == finding_id:
            return [(s["quote"], s["title"] or s["host"], s["date"], s["url"]) for s in f["sources"]]
    return []
