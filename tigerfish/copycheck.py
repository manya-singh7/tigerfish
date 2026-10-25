"""Copy-paste check: is "site-specific" text in this EIA also found in documents about
OTHER places? Pattern follows the cookbook's deep-research agents (plan -> Tavily
search -> extract -> analyse with a Token Factory model -> report), but the analysis
is mostly deterministic so results are reproducible and cheap.

1. select_passages   sentences around verified ledger claims that should be unique to
                     this site; boilerplate dropped by phrase list + one LIGHTNING yes/no
                     call (batched); capped at MAX_PASSAGES
2. search_passage    Tavily exact-phrase search on the distinctive part, then Tavily
                     extract for the top hits; this report's own hosts and news coverage
                     (Scroll etc.) are excluded
3. overlap           longest common word run + word 8-gram overlap
4. grade_hit         RED   site-specific numbers/species also in a document about a
                           DIFFERENT place
                     ORANGE near-identical description, place names changed
                     NONE  generic text, or the same project / coverage of it
   borrowed_text     INFO (own section, never RED/ORANGE): >= BORROWED_RUN verbatim
                     words from generic external guidance, with no citation of that
                     source (domain name or title) anywhere on our page
5. hunt_species_source  Tavily searches for combinations of a table's unusual names

Every Tavily response is cached in cache/tavily/ (cached calls cost no credits).
A run stops before Tavily credits would pass MAX_TAVILY_CREDITS.
Wording is neutral: "Text closely matches <URL>, which describes <place>. Verify."
"""

import hashlib
import json
import logging
import math
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from tigerfish import claims as claims_mod
from tigerfish import llm, trace

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "tavily"

MAX_PASSAGES = 15
MAX_TAVILY_CREDITS = 100
SEARCH_RESULTS = 5            # results per Tavily search
EXTRACT_TOP = 3               # top hits per passage whose full text is extracted
PHRASE_WORDS = 12             # length of the exact phrase searched for
MIN_PASSAGE_WORDS = 10
NGRAM = 8
MIN_RUN = 8                   # a match needs a common run of >= 8 words...
MIN_NGRAM = 0.20              # ...or >= 20% of the passage's 8-grams in the hit
ORANGE_NGRAM = 0.50           # near-identical text
BORROWED_RUN = 20             # verbatim words from generic guidance, uncited -> INFO
MAX_HIT_CHARS = 200_000       # extracted page text kept per hit
HUNT_QUERIES = 4              # species source hunt: searches per table
HUNT_NAMES_PER_QUERY = 3
NEUTRAL = "Text closely matches {url}, which describes {place}. Verify."

# This report's own copies and coverage of it: never evidence of copying.
EXCLUDE_DOMAINS = ["scroll.in", "environmentclearance.nic.in", "parivesh.nic.in",
                   "eqmagpro.com"]
# A hit mentioning any of these is about the same project (report, mirror or news).
SITE_NAMES = ["Great Nicobar", "Galathea", "Campbell Bay", "Indira Point", "ANIIDCO",
              "Shompen"]

BOILERPLATE = re.compile(
    r"\b(CPCB|MoEF|MoEFCC|Environment \(Protection\) Act|Wildlife \(Protection\) Act|"
    r"Forest \(Conservation\) Act|Notification|IS[: ]\s?\d{3,}|APHA|standard method|"
    r"as per (the )?(guidelines|norms|standards)|permissible limit|prescribed|"
    r"Terms of Reference|ToR|EIA Notification|CRZ|National Ambient Air Quality|NAAQS|"
    r"\bAct,?\s+(19|20)\d\d\b|"
    r"sampling (was|were|has been) (carried out|done) (as per|following))",
    re.IGNORECASE)

log = logging.getLogger(__name__)
load_dotenv(ROOT / ".env")


# ---------- Tavily access: cache + credit budget ----------

class CreditCapReached(RuntimeError):
    pass


class Budget:
    """Counts Tavily credits used in a run; refuses a call that would pass the cap."""

    def __init__(self, cap=MAX_TAVILY_CREDITS):
        self.cap, self.used, self.calls, self.cached = cap, 0, 0, 0

    def check(self, cost):
        if self.used + cost > self.cap:
            raise CreditCapReached(f"Tavily credit cap {self.cap} reached ({self.used} used)")

    def add(self, cost):
        self.used += cost
        self.calls += 1


_client = None


def client():
    global _client
    if _client is None:
        from tavily import TavilyClient
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            raise RuntimeError("TAVILY_API_KEY is missing; add it to .env")
        _client = TavilyClient(api_key=key)
    return _client


def _cache_path(endpoint, params):
    key = json.dumps({"endpoint": endpoint, "params": params}, sort_keys=True)
    return CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()}.json"


def tavily_call(endpoint, budget, est_credits, **params):
    """Cached Tavily search/extract. Credits come from the response's usage when given."""
    path = _cache_path(endpoint, params)
    trace.record("tavily", path)
    if path.exists():
        budget.cached += 1
        return json.loads(path.read_text(encoding="utf-8"))["data"]
    budget.check(est_credits)
    fn = client().search if endpoint == "search" else client().extract
    data = fn(include_usage=True, **params)
    credits = (data.get("usage") or {}).get("credits")
    budget.add(credits if isinstance(credits, (int, float)) else est_credits)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"endpoint": endpoint, "params": params, "data": data},
                               ensure_ascii=False), encoding="utf-8")
    return data


def search(query, budget, exact=True, include_domains=None):
    """Tavily basic search (1 credit). include_domains restricts results to those sites
    (then this report's own hosts need no excluding)."""
    if include_domains:
        return tavily_call("search", budget, 1, query=query, search_depth="basic",
                           max_results=SEARCH_RESULTS, exact_match=exact,
                           include_domains=list(include_domains))
    return tavily_call("search", budget, 1, query=query, search_depth="basic",
                       max_results=SEARCH_RESULTS, exact_match=exact,
                       exclude_domains=EXCLUDE_DOMAINS)


def extract(urls, budget, max_chars=MAX_HIT_CHARS):
    """{url: text} for the URLs Tavily could extract (failed URLs cost nothing).

    Text is cut to max_chars (None = full text; the cache always keeps the full text).
    """
    if not urls:
        return {}
    data = tavily_call("extract", budget, math.ceil(len(urls) / 5), urls=sorted(urls),
                       extract_depth="basic")
    return {r["url"]: (r.get("raw_content") or "")[:max_chars]
            for r in data.get("results", [])}


# ---------- 1. passages ----------

def sentences(text):
    """Split normalised page text into sentences."""
    return [s for s in re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9\"(])", claims_mod.normalize(text)) if s]


def sentence_for(quote, text):
    """The page sentence(s) containing a claim quote, or the quote itself."""
    q = claims_mod.normalize(quote)
    for s in sentences(text):
        if q[:60] in s:
            return s if len(s) >= len(q) else q
    return q


def site_score(passage, species_names=()):
    """Rough 'should be unique to this site' score; 0 means generic or boilerplate."""
    words = passage.split()
    if len(words) < MIN_PASSAGE_WORDS or BOILERPLATE.search(passage):
        return 0
    score = 0
    score += 2 * min(3, len(significant_numbers(passage)))
    score += 2 * sum(1 for n in species_names if n.lower() in passage.lower())
    score += 1 if any(p.lower() in passage.lower() for p in SITE_NAMES) else 0
    return score


def significant_numbers(text):
    """Numbers that identify data (>= 10 or with decimals); small counts are too common."""
    return {n for n in claims_mod._numbers(text) if n >= 10 or n != int(n)}


SITE_SPECIFIC_PROMPT = """Each numbered passage comes from an Indian Environmental Impact \
Assessment (EIA) report. Decide for each whether it is SITE-SPECIFIC: it describes this \
particular site (its baseline data, species recorded, monitoring results, local ecology, \
areas or distances of this project). GENERIC passages (laws, standards, standard methods, \
textbook descriptions that could appear in any report) are not site-specific.
Return JSON only: {"site_specific": [numbers of the site-specific passages]}"""


def lightning_site_specific(passages):
    """Indices (0-based) LIGHTNING calls site-specific; one batched call. None on failure."""
    if not passages:
        return set()
    listing = "\n".join(f"{i}. {p}" for i, p in enumerate(passages, 1))
    raw = claims_mod.chat_json(llm.LIGHTNING, [
        {"role": "system", "content": SITE_SPECIFIC_PROMPT},
        {"role": "user", "content": listing}], max_tokens=500)
    if not isinstance(raw, dict) or not isinstance(raw.get("site_specific"), list):
        return None
    return {int(i) - 1 for i in raw["site_specific"] if str(i).isdigit()}


def select_passages(ledger, pages, max_passages=MAX_PASSAGES, use_llm=True):
    """Site-specific passages from verified claims, best first, capped.

    Returns [{"page", "text", "claim_ids", "score"}].
    """
    species_names = {str(c["value"]) for c in ledger
                     if c["type"] == "species" and c.get("verified") and c["value"]}
    by_text = {}
    for c in ledger:
        if not c.get("verified") or c["page"] not in pages:
            continue
        text = sentence_for(c["quote"], pages[c["page"]])
        p = by_text.setdefault((c["page"], text), {"page": c["page"], "text": text,
                                                   "claim_ids": [], "score": 0})
        p["claim_ids"].append(c["id"])
    candidates = []
    for p in by_text.values():
        p["score"] = site_score(p["text"], species_names)
        if p["score"] > 0:
            candidates.append(p)
    candidates.sort(key=lambda p: (-p["score"], p["page"]))
    candidates = candidates[:max_passages * 2]          # LLM check on a short list only
    if use_llm:
        keep = lightning_site_specific([p["text"] for p in candidates])
        if keep is not None:
            candidates = [p for i, p in enumerate(candidates) if i in keep]
    return candidates[:max_passages]


def distinctive_phrase(passage, words=PHRASE_WORDS):
    """A run of `words` consecutive words from the passage, centred on its first data point."""
    tokens = passage.split()
    if len(tokens) <= words:
        return passage
    anchor = next((i for i, t in enumerate(tokens) if significant_numbers(t)), len(tokens) // 2)
    start = max(0, min(anchor - words // 2, len(tokens) - words))
    return " ".join(tokens[start:start + words]).strip(" ,;:")


# ---------- 3. overlap ----------

def tokens(text):
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", str(text).lower())


def overlap(passage, text):
    """{"longest_run": words, "ngram": share of the passage's 8-grams found in text}."""
    p, t = tokens(passage), tokens(text)
    if not p or not t:
        return {"longest_run": 0, "ngram": 0.0, "run_start": None}
    m = SequenceMatcher(None, p, t, autojunk=False).find_longest_match(0, len(p), 0, len(t))
    n = min(NGRAM, len(p))
    grams = {tuple(p[i:i + n]) for i in range(len(p) - n + 1)}
    doc = {tuple(t[i:i + n]) for i in range(len(t) - n + 1)}
    return {"longest_run": m.size, "ngram": len(grams & doc) / len(grams),
            "run_start": m.b if m.size else None, "run_words": p[m.a:m.a + m.size]}


def matching_snippet(run_words, text, context=150):
    """The original text around the longest common run (for evidence)."""
    if not run_words:
        return ""
    pattern = r"\W+".join(re.escape(w) for w in run_words)
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return " ".join(run_words)
    return claims_mod.normalize(text[max(0, m.start() - context):m.end() + context])


# ---------- 4. grading ----------

def same_project(url, text):
    if any(d in url for d in EXCLUDE_DOMAINS):
        return True
    low = text.lower()
    return any(name.lower() in low for name in SITE_NAMES)


def grade_hit(passage, hit_text, ov, is_same_project, species_names=()):
    """(grade or None, why). None = not a match at all."""
    if is_same_project:
        return "NONE", "same project or coverage of it"
    if ov["longest_run"] < MIN_RUN and ov["ngram"] < MIN_NGRAM:
        return None, "no real overlap"
    nums = significant_numbers(passage)
    shared_nums = nums & significant_numbers(hit_text)
    low = hit_text.lower()
    shared_species = [n for n in species_names if n.lower() in passage.lower() and n.lower() in low]
    data_match = (len(shared_nums) >= min(2, len(nums)) and nums) or len(shared_species) >= 2
    if data_match and ov["longest_run"] >= MIN_RUN:
        return "RED", (f"site-specific data also in the other document "
                       f"(numbers {sorted(shared_nums)}; species {shared_species})")
    if ov["ngram"] >= ORANGE_NGRAM:
        return "ORANGE", "near-identical description with different details"
    return "NONE", "partial overlap of generic wording"


PLACE_PROMPT = """Which place does this document describe (the project site or study area)? \
Answer with the place name and its district/state/country if given. Return JSON only: \
{"place": "..."}"""


def describe_place(url, text):
    raw = claims_mod.chat_json(llm.LIGHTNING, [
        {"role": "system", "content": PLACE_PROMPT},
        {"role": "user", "content": f"URL: {url}\n\n{text[:4000]}"}], max_tokens=200)
    place = (raw or {}).get("place") if isinstance(raw, dict) else None
    return str(place).strip() if place else "another place (not identified)"


# ---------- 2 + 4: run over passages ----------

# ---------- borrowed text (INFO) ----------

DOMAIN_NOISE = {"www", "gov", "org", "com", "net", "in", "nic", "dot", "edu", "ac", "co", "uk",
                "int", "res", "gc", "ca", "au", "us"}


def citation_terms(url, title=None):
    """Names a page might use to cite a source: distinctive domain labels and the title."""
    labels = [w for w in re.split(r"[.\-]", urlparse(url).netloc.lower())
              if len(w) >= 3 and w not in DOMAIN_NOISE]
    terms = labels + ([claims_mod.normalize(title)] if title and len(title) > 10 else [])
    return terms


def cited_on_page(url, title, page_text):
    """The first citation term found on the page, or None."""
    low = claims_mod.normalize(page_text).lower()
    return next((t for t in citation_terms(url, title) if t.lower() in low), None)


def borrowed_text(passage, page_text, hit, run_words):
    """INFO finding for a long verbatim run from a generic external source, uncited on the page.

    Only for hits graded NONE as generic wording (never RED/ORANGE, never same project).
    """
    if hit["grade"] != "NONE" or hit["why"] != "partial overlap of generic wording":
        return None
    if hit["longest_run"] < BORROWED_RUN or cited_on_page(hit["url"], hit["title"], page_text):
        return None
    ours = matching_snippet(run_words, passage["text"], context=0)
    return {"type": "borrowed_text", "grade": "INFO", "page": passage["page"], "quote": ours,
            "url": hit["url"], "title": hit["title"], "longest_run": hit["longest_run"],
            "source_snippet": hit["snippet"],
            "message": (f"{hit['longest_run']} consecutive words match {hit['url']} verbatim; "
                        f"no citation to this source found on p.{passage['page']}. "
                        f"Consider citing it.")}


def check_passage(passage, budget, species_names=(), page_text=None):
    """Search, extract, score and grade one passage. Returns graded hits and borrowed text.

    page_text (the passage's full page) is needed for the borrowed-text citation check.
    """
    phrase = distinctive_phrase(passage["text"])
    results = search(f'"{phrase}"', budget).get("results", [])
    top = [r["url"] for r in results if not same_project(r["url"], r.get("content", ""))]
    texts = extract(top[:EXTRACT_TOP], budget)
    hits, borrowed = [], []
    for r in results:
        url = r["url"]
        text = texts.get(url) or r.get("content", "")
        ov = overlap(passage["text"], text)
        grade, why = grade_hit(passage["text"], text, ov, same_project(url, text), species_names)
        if grade is None:
            continue
        hit = {"url": url, "title": r.get("title"), "grade": grade, "why": why,
               "longest_run": ov["longest_run"], "ngram": round(ov["ngram"], 3),
               "snippet": matching_snippet(ov.get("run_words"), text), "place": None,
               "message": None}
        if grade in ("RED", "ORANGE"):
            hit["place"] = describe_place(url, text)
            hit["message"] = NEUTRAL.format(url=url, place=hit["place"])
        hits.append(hit)
        b = borrowed_text(passage, page_text or passage["text"], hit, ov.get("run_words"))
        if b and not any(x["url"] == b["url"] for x in borrowed):
            borrowed.append(b)
    return {"page": passage["page"], "passage": passage["text"], "phrase": phrase,
            "claim_ids": passage["claim_ids"], "results": len(results), "hits": hits,
            "borrowed": borrowed}


def check_passages(passages, budget, species_names=(), pages=None):
    """Run check_passage over all passages; stops cleanly at the credit cap.

    pages: {page number: text}, for the borrowed-text citation check.
    """
    out, stopped = [], None
    for p in passages:
        try:
            out.append(check_passage(p, budget, species_names, (pages or {}).get(p["page"])))
        except CreditCapReached as e:
            stopped = str(e)
            log.warning(stopped)
            break
    return out, stopped


# ---------- 5. species-list source hunt ----------

def binomial(name):
    """'Taupaia nicobarica nicobarica' -> 'Taupaia nicobarica' (genus + species)."""
    return " ".join(claims_mod.normalize(name).split()[:2])


def name_overlap(names, text):
    """Table names found in a text (by genus + species, case-insensitive)."""
    low = text.lower()
    return [n for n in names if binomial(n).lower() in low]


def hunt_queries(names, unusual_first, flagged=(), n_queries=HUNT_QUERIES,
                 per_query=HUNT_NAMES_PER_QUERY):
    """Quoted-name combinations for finding where a species list came from.

    unusual_first: names, rarest first. flagged: names the species check flagged as
    out of place at this site; they are the best clues to a source list from elsewhere,
    so they come first. The last query mixes the two rarest flagged names with the two
    rarest local ones (e.g. "Felis chaus" "Funambulus pennantii" "Tupaia nicobarica" ...).
    """
    order = [n for n in unusual_first if n in names] or list(names)
    out_of_place = [binomial(n) for n in order if n in flagged]
    local = [binomial(n) for n in order if n not in flagged]
    pool = out_of_place + local
    windows = max(1, n_queries - (1 if out_of_place and local else 0))
    combos = [pool[i:i + per_query] for i in range(0, min(windows, max(1, len(pool) - per_query + 1)))]
    if out_of_place and local:
        combos.append(out_of_place[:2] + local[:2])
    seen, queries = set(), []
    for combo in combos:
        q = " ".join(f'"{n}"' for n in combo)
        if q not in seen:
            seen.add(q)
            queries.append(q)
    return queries[:n_queries]


def hunt_species_source(names, budget, unusual_first=(), flagged=()):
    """Where might this species list come from? Report-only: matches with name overlap."""
    matches, stopped = {}, None
    try:
        for q in hunt_queries(names, unusual_first or names, flagged):
            results = search(q, budget, exact=False).get("results", [])
            texts = extract([r["url"] for r in results[:EXTRACT_TOP]], budget)
            for r in results:
                text = texts.get(r["url"]) or r.get("content", "")
                found = name_overlap(names, text)
                prev = matches.get(r["url"])
                if prev is None or len(found) > len(prev["names"]):
                    matches[r["url"]] = {"url": r["url"], "title": r.get("title"), "query": q,
                                         "names": found,
                                         "same_project": same_project(r["url"], text)}
    except CreditCapReached as e:
        stopped = str(e)
        log.warning(stopped)
    ranked = sorted(matches.values(), key=lambda m: (-len(m["names"]), m["url"]))
    return ranked, stopped
