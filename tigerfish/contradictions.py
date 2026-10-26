"""Contradiction check over a claims ledger.

Step 1  candidate_pairs(claims)        deterministic pairing, no LLM:
          numeric      same kind of number, compatible unit, similar subject, values
                       differ by more than MIN_DIFFERENCE (pages must differ)
          statement    "no X" / "not found" on one page vs "X exists/found" on another
          recycled     the same figure, with the same breakdown, used for different
                       subjects on different pages ("330 species" for two parks and
                       the whole island) -> finding type "recycled_figure"
Step 2  explanation_hits(...)          deterministic search for explanation words
                                       around both quotes and in the rest of both pages
Step 3  verdict(...)                   ULTRA (thinking on), one cached call per candidate:
                                       answers same_subject / same_place / same_scope /
                                       incompatible / explained (+ reason, explanation_quote);
                                       the grade RED | ORANGE | NONE is computed in code
                                       (compute_grade), never taken from the model
Step 4  evaluate(...)                  compare findings with data/known_issues.json

Findings are saved to cache/findings/<pdf_stem>/contradictions.jsonl.
Wording is neutral: "Inconsistency flagged, verify."
"""

import json
import logging
import re
from itertools import combinations
from pathlib import Path

from tigerfish import claims as claims_mod
from tigerfish import llm

ROOT = Path(__file__).resolve().parent.parent
FINDINGS_DIR = ROOT / "cache" / "findings"

MAX_CANDIDATES = 30          # Ultra calls per run at most; extra candidates are dropped (logged)
MAX_COST_USD = 0.50
MIN_DIFFERENCE = 0.05        # numeric values must differ by more than 5%
MIN_SUBJECT_SIMILARITY = 0.75
MIN_BREAKDOWN = 3            # recycled figure: at least this many other non-trivial figures shared
TRIVIAL_MAX = 25             # recycled figure: values up to this (e.g. "20 locations") are too common
EXPLANATION_WINDOW = 600     # characters either side of a quote
MAX_HITS = 12                # explanation hits passed to the model
MAX_PAGE_CHARS = 8000        # each full page sent to Ultra
VERDICT_MAX_TOKENS = 6000    # Ultra reasons first (reasoning_content), then answers
EST_OUTPUT_TOKENS = 2000     # for cost estimates
NEUTRAL = "Inconsistency flagged, verify."
GRADES = ("RED", "ORANGE", "NONE")

TOTAL_WORDS = re.compile(r"\b(total|overall|entire|whole|in all|altogether|combined|aggregate)\b",
                         re.IGNORECASE)
NOT_SCORED = {"under_review", "candidate_new_finding"}   # known issues printed, not scored

EXPLANATION_WORDS = ["before", "after", "earlier", "original", "originally", "revised",
                     "proposed", "existing", "phase", "tsunami", "reduced", "increased",
                     "excluding", "including", "total", "of which"]
# Accusatory wording. Plain "lie/lies/lying" is not banned: "Sumatra lies farther south".
BANNED_WORDS = re.compile(r"\b(liar\w*|lied|fraud\w*|fake\w*|fabricat\w*|deceiv\w*|deceptive|"
                          r"dishonest\w*|cheat\w*)\b|\b(lie|lies|lying)\s+(about|to)\b|"
                          r"\bis\s+lying\b", re.IGNORECASE)

# Words that say nothing about what a number is about.
STOP_WORDS = set("""a an the of in on at to from for and or with by as is are was were be been
    this that these those its it their there here which who about into within during per total
    species number numbers recorded reported found area areas region great nicobar island islands
    gni project proposed site national park percentage percent value count amount""".split())
# Generic words only (place names kept): used to decide whether two subjects differ.
GENERIC_WORDS = set("""a an the of in on at to from for and or with by as is are was were be
    this that its it which about into within during species number recorded reported found
    total value count amount""".split())
NEGATION = re.compile(r"\b(no|not|none|nil|absent|absence|devoid|never|without|nowhere)\b",
                      re.IGNORECASE)
# An absence claim: the negation is about something existing or being found.
ABSENCE = re.compile(r"\b(no|none|nil)\b|\bdevoid of\b|\babsen(t|ce)\b|\bwithout any\b|"
                     r"\bnot\s+(?:be\s+|been\s+)?(?:found|observed|recorded|reported|seen|"
                     r"noticed|sighted|present|exist\w*)\b", re.IGNORECASE)
# Words right after these introduce the thing that is absent ("no coral", "devoid of reefs").
ABSENT_THING = re.compile(r"\b(?:no|none of|devoid of(?: any)?|absence of|without any)\s+",
                          re.IGNORECASE)
PRESENCE = re.compile(r"\b(exist\w*|found|present|presence|observed|recorded|reported|occur\w*|"
                      r"sighted|seen|noticed|nest\w*|available)\b", re.IGNORECASE)
# Not the absent thing X itself: place names and words about presence/absence.
# ("not found in Andaman Islands" is about some species, not about Andaman.)
TOPIC_IGNORE = set("""andaman galathea campbell bay katchal indira point reserve biosphere coast
    coastal india iba location village distribution presence absence absent occurrence status
    some few any record sighting observed""".split())

log = logging.getLogger(__name__)
last_run = {}

UNITS = {  # unit -> (dimension, factor to the base unit)
    "ha": ("area", 1.0), "hectare": ("area", 1.0), "hectares": ("area", 1.0),
    "sq km": ("area", 100.0), "sq.km": ("area", 100.0), "sqkm": ("area", 100.0),
    "km2": ("area", 100.0), "km²": ("area", 100.0), "sq. km": ("area", 100.0),
    "acre": ("area", 0.404686), "acres": ("area", 0.404686),
    "km": ("length", 1000.0), "m": ("length", 1.0), "metre": ("length", 1.0),
    "meter": ("length", 1.0), "metres": ("length", 1.0), "meters": ("length", 1.0),
    "%": ("percent", 1.0), "percent": ("percent", 1.0),
}


# ---------- small helpers ----------

def number(value):
    """Claim value as a float, or None if it isn't a single number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    nums = claims_mod.NUMBER.findall(str(value or ""))
    if len(nums) == 1 and re.fullmatch(r"[\s\d,.]*", str(value)):
        return float(nums[0].replace(",", ""))
    return None


def unit_key(unit):
    """(dimension, factor) for a unit; unknown units compare by their own name.

    Money in rupees compares across wordings: "INR Lacs/ Yr", "Rs. lakh", "crore".
    """
    u = claims_mod.normalize(str(unit or "")).lower().rstrip(".")
    if u in UNITS:
        return UNITS[u]
    if re.search(r"\b(lacs?|lakhs?)\b", u):
        return ("currency", 1e5)
    if re.search(r"\bcrores?\b", u):
        return ("currency", 1e7)
    if re.search(r"\b(inr|rs|rupees?)\b", u):
        return ("currency", 1.0)
    return (u, 1.0)


def keywords(text):
    """Content words of a subject, crudely singularised."""
    words = re.findall(r"[a-z]{3,}", str(text or "").lower())
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w
            for w in words if w not in STOP_WORDS}


def subject_overlap(a, b):
    """How alike two subjects are, 0..1: key-word Jaccard, or fuzzy match on key words.

    Fuzzy matching runs on the key words only: the model writes subjects from a
    template ("X species recorded from Y"), so whole-string similarity is misleading.
    """
    ka, kb = keywords(a), keywords(b)
    if not ka or not kb:
        return 0.0
    jaccard = len(ka & kb) / len(ka | kb)
    fuzzy = claims_mod.similar(" ".join(sorted(ka)), " ".join(sorted(kb)))
    return max(jaccard, fuzzy if fuzzy >= MIN_SUBJECT_SIMILARITY else 0.0)


def similar_subject(a, b):
    """At least one shared key word, or key words that fuzzy-match.

    A subject made only of stop words ("Great Nicobar Island") has no key words; then
    the full words (place names included) must overlap by at least half.
    """
    ka, kb = keywords(a), keywords(b)
    if not ka or not kb:
        wa = set(re.findall(r"[a-z]{2,}", str(a or "").lower())) - GENERIC_WORDS
        wb = set(re.findall(r"[a-z]{2,}", str(b or "").lower())) - GENERIC_WORDS
        return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5
    return bool(ka & kb) or subject_overlap(a, b) > 0


def different_subject(a, b):
    """True when each subject has words the other lacks (e.g. two parks, or a park vs GNI).

    Place names count here, so only generic words are ignored.
    """
    wa = set(re.findall(r"[a-z]{2,}", str(a or "").lower())) - GENERIC_WORDS
    wb = set(re.findall(r"[a-z]{2,}", str(b or "").lower())) - GENERIC_WORDS
    return bool(wa - wb) and bool(wb - wa)


def numeric(claim):
    """A claim with a single number. A statement counts too when it has a number AND a
    unit (the model sometimes types "the figure is 95.55 %" as a statement)."""
    if number(claim["value"]) is None:
        return False
    if claim["type"] in ("quantity", "count", "area", "distance"):
        return True
    return claim["type"] == "statement" and bool(str(claim.get("unit") or "").strip())


def base_value(claim):
    _, factor = unit_key(claim["unit"])
    return number(claim["value"]) * factor


def kind(claim):
    """count and quantity are the same kind when counting things (e.g. 'species');
    a numeric statement is an amount too."""
    return "amount" if claim["type"] in ("quantity", "count", "statement") else claim["type"]


# ---------- step 1: candidates ----------

def numeric_pairs(claims):
    out = []
    usable = [c for c in claims if numeric(c) and c.get("verified")]
    for a, b in combinations(usable, 2):
        if a["page"] == b["page"] or kind(a) != kind(b):
            continue
        if unit_key(a["unit"])[0] != unit_key(b["unit"])[0]:
            continue
        if not similar_subject(a["subject"], b["subject"]):
            continue
        va, vb = base_value(a), base_value(b)
        if max(abs(va), abs(vb)) == 0 or abs(va - vb) / max(abs(va), abs(vb)) <= MIN_DIFFERENCE:
            continue
        out.append({"kind": "numeric", "claims": [a, b],
                    "overlap": subject_overlap(a["subject"], b["subject"]),
                    "part_total": part_vs_total(a, b)})
    # Most alike subjects first, so the candidate cap keeps the best pairs.
    return sorted(out, key=lambda c: -c["overlap"])


def part_vs_total(a, b):
    """True when exactly one quote states a total and that one has the larger value.

    e.g. "The total reclaimed land will be 194 ha" vs "needs to reclaim ... 71 Ha ...
    airport": the smaller figure is probably a component of the total, not a contradiction.
    """
    ta = bool(TOTAL_WORDS.search(claims_mod.normalize(a["quote"])))
    tb = bool(TOTAL_WORDS.search(claims_mod.normalize(b["quote"])))
    if ta == tb:
        return False
    total, part = (a, b) if ta else (b, a)
    return base_value(total) > base_value(part)


def covered_by_recycled(cand, recycled):
    """A numeric pair whose figures all belong to one recycled-figure group (redundant)."""
    for r in recycled:
        pages = {c["page"] for c in r["claims"]}
        values = {r["value"], *r["breakdown"]}
        if all(c["page"] in pages and number(c["value"]) in values for c in cand["claims"]):
            return True
    return False


def quote_sentences(quote):
    return [s for s in re.split(r"(?<=[.!?;])\s+", claims_mod.normalize(quote)) if s]


def absence_sentence(claim):
    """The sentence of the quote that states the absence, or None."""
    return next((s for s in quote_sentences(claim["quote"]) if ABSENCE.search(s)), None)


def absence_topic(claim):
    """Key words of the thing X said to be absent, or None if the claim is not an absence.

    Place names and presence/absence words are not X (TOPIC_IGNORE).
    """
    text = absence_sentence(claim)
    if not text:
        return None
    m = ABSENT_THING.search(text)
    if m:   # "no coral exists in" -> coral
        after = " ".join(re.findall(r"[A-Za-z]+", text[m.end():])[:3])
        topic = {w for w in keywords(after) if not PRESENCE.fullmatch(w)} - TOPIC_IGNORE
        if topic:
            return topic
    return (keywords(claim["subject"]) - keywords("presence absence") - TOPIC_IGNORE) or None


def trimmed(claim, sentence):
    """The claim with its quote cut to one sentence (still verbatim page text)."""
    if sentence == claims_mod.normalize(claim["quote"]):
        return claim
    return {**claim, "quote": sentence, "quote_trimmed": True}


def statement_pairs(claims):
    """"No X" on one page vs "X exists/found" on another.

    The presence sentence must name ALL of X's key words (a shared place word is not
    enough), and both quotes are trimmed to the sentence that says it.
    """
    out = []
    usable = [c for c in claims if c.get("verified")]
    for a in usable:
        if a["type"] != "statement":
            continue
        topic = absence_topic(a)
        if not topic:
            continue
        a_short = trimmed(a, absence_sentence(a))
        for b in usable:
            if b["page"] == a["page"] or b["type"] not in ("statement", "species"):
                continue
            s = next((s for s in quote_sentences(b["quote"])
                      if not NEGATION.search(s) and PRESENCE.search(s)
                      and topic <= keywords(s)), None)
            if s:
                out.append({"kind": "statement", "claims": [a_short, trimmed(b, s)]})
    return out


def tor_location_counts(tor_pdf):
    """Numbers of sampling locations the ToR asks for (e.g. {6, 20}). Regex only, free."""
    from tigerfish import pdf_reader, promises   # local: promises imports agent, copycheck
    pages = pdf_reader.read_pdf(tor_pdf, render=False)
    return {float(i["value"]) for i in promises.tor_items(pages) if i["kind"] == "locations"}


def recycled_figures(claims, tor_counts=()):
    """The same figure + same breakdown on different pages for different subjects.

    Groups sharing the same set of pages are merged; the largest figure is the headline
    and the other shared figures are its breakdown. Headline figures <= TRIVIAL_MAX or equal
    to a ToR location count (every survey uses "20 locations") are skipped, and at least
    MIN_BREAKDOWN shared figures above TRIVIAL_MAX are needed.
    """
    tor_counts = {float(v) for v in tor_counts}
    usable = [c for c in claims if numeric(c) and c.get("verified") and kind(c) == "amount"]
    by_value = {}
    for c in usable:
        by_value.setdefault((number(c["value"]), unit_key(c["unit"])), []).append(c)

    page_values = {}
    for c in usable:
        page_values.setdefault(c["page"], set()).add(number(c["value"]))

    groups = {}
    for (value, _), group in by_value.items():
        if value <= TRIVIAL_MAX or value in tor_counts:
            continue
        first_per_page = {}
        for c in group:
            first_per_page.setdefault(c["page"], c)
        members = list(first_per_page.values())
        if len(members) < 2:
            continue
        if not all(different_subject(a["subject"], b["subject"])
                   for a, b in combinations(members, 2)):
            continue
        pages = frozenset(first_per_page)
        shared = {v for v in set.intersection(*(page_values[p] for p in pages)) - {value}
                  if v > TRIVIAL_MAX}
        if len(shared) < MIN_BREAKDOWN:
            continue
        best = groups.get(pages)
        if best is None or value > best["value"]:
            groups[pages] = {"kind": "recycled", "value": value, "claims": members,
                             "breakdown": sorted(shared)}
    return list(groups.values())


def candidate_pairs(claims, max_candidates=MAX_CANDIDATES, tor_counts=(), keyed=False):
    """All candidates (recycled first, then statements, then numeric), capped.

    Numeric pairs already covered by a recycled-figure group are suppressed (counted
    in last_run["candidates_suppressed"]). tor_counts: see recycled_figures.
    keyed: numeric pairs by LIGHTNING subject key, repeats collapsed and capped per group
    (tigerfish/pairing.py; needed for long reports). False: every numeric claim against
    every other with a similar subject (deterministic, no LLM; small page sets and tests).
    """
    recycled = recycled_figures(claims, tor_counts)
    if keyed:
        from tigerfish import pairing   # local: pairing imports this module
        numeric_iter = pairing.keyed_numeric_pairs(claims, pairing.subject_keys(claims))
    else:
        numeric_iter = numeric_pairs(claims)
    kept_numeric, suppressed = [], 0
    for c in numeric_iter:          # streamed: the all-pairs list is never built
        if covered_by_recycled(c, recycled):
            suppressed += 1
        else:
            kept_numeric.append(c)
    kept_numeric.sort(key=lambda c: -c["overlap"])
    last_run["candidates_suppressed"] = suppressed
    found = recycled + statement_pairs(claims) + kept_numeric
    seen, unique = set(), []
    for cand in found:
        key = (cand["kind"], tuple(sorted(c["id"] for c in cand["claims"])))
        if key not in seen:
            seen.add(key)
            unique.append(cand)
    dropped = max(0, len(unique) - max_candidates)
    if dropped:
        log.warning("%d candidates found; %d dropped by MAX_CANDIDATES=%d",
                    len(unique), dropped, max_candidates)
    last_run["candidates_found"] = len(unique)
    last_run["candidates_dropped"] = dropped
    return unique[:max_candidates]


# ---------- step 2: explanation words ----------

EXPLAIN_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in EXPLANATION_WORDS) + r")\b",
                        re.IGNORECASE)


def explanation_hits(cand, pages):
    """Explanation words near each quote (+-EXPLANATION_WINDOW chars) and elsewhere on the page.

    pages: {page number: page text}. Hits near a quote come first.
    """
    hits = []
    for c in cand["claims"]:
        text = claims_mod.normalize(pages.get(c["page"], ""))
        q = claims_mod.normalize(c["quote"])
        at = text.find(q)
        lo, hi = (at - EXPLANATION_WINDOW, at + len(q) + EXPLANATION_WINDOW) if at >= 0 else (0, 0)
        for m in EXPLAIN_RE.finditer(text):
            near = lo <= m.start() <= hi
            snippet = text[max(0, m.start() - 80):m.end() + 80]
            hits.append({"page": c["page"], "word": m.group(1).lower(), "near_quote": near,
                         "snippet": snippet})
    unique = {}
    for h in sorted(hits, key=lambda h: not h["near_quote"]):
        unique.setdefault((h["page"], h["snippet"]), h)
    return list(unique.values())


# ---------- step 3: verdict ----------

# FROZEN (2026-10-27): VERDICT_PROMPT, RECYCLED_PROMPT, PART_TOTAL_RULE and the statement
# text built in verdict_messages() are frozen: no further wording changes before submission.
# Validated on results/eval.json (gn-001 ORANGE; gn-003/004/005 RED; negative control NONE;
# planted 10/10 with 0/5 explained flagged). Any change re-keys every cached Ultra verdict
# and needs a full evaluation re-run. Grading rules live in compute_grade().

VERDICT_PROMPT = """You check an Indian Environmental Impact Assessment (EIA) report for \
internal inconsistencies. You are a neutral accuracy checker: never accuse anyone, never \
use words like "lie", "fraud" or "fake".

Answer each question about the statements. Do not give a grade: it is computed from your answers.
Return JSON only:
{"same_subject": true/false,
 "same_place": true/false/"unclear",
 "same_scope": true/false/"unclear",
 "incompatible": true/false,
 "explained": true/false,
 "reason": "1-2 neutral sentences",
 "explanation_quote": "verbatim sentence from one of the pages that explains the difference, or null",
 "explanation_page": page number of that quote, or null}

Questions (answer each one on its own):
- same_subject: are both statements about the same kind of fact (e.g. both the number of
  fauna species, both whether coral is present, both the coral area lost)? Judge the kind
  of fact only; differences of place belong in same_place. Different groups (mammals vs
  mangroves, flora vs fauna) are different subjects.
- same_place: the same place? false only if they are clearly different places that do not
  overlap (e.g. two different parks); "unclear" if one may lie inside the other (a port site
  in a bay) or the pages do not say; true if the same place.
- same_scope: false ONLY if the pages state that the figures cover different extents: a named
  part vs the whole, a subset vs a total, or before vs after a dated event or a stated
  revision. A different source, survey, census, method or report section is NOT a different
  scope: a report should give consistent figures for the same thing wherever they come from.
  Differences of place belong in same_place, not in same_scope (a bay vs a site in it).
  "unclear" only if the pages give a concrete reason the extents might differ, and name
  that reason in reason; true otherwise.
- incompatible: can the two statements NOT both be right? Different numbers for the same
  count, or "no X" vs "X exists", are incompatible. (Restoring more area than is lost is
  normal practice: not incompatible.)
- explained: does the report itself explain the difference (e.g. before/after an event,
  revised figures, a subset vs a total)? If true, give explanation_quote.
explanation_quote must be copied character for character from the page text, or null."""

RECYCLED_PROMPT = """You check an Indian Environmental Impact Assessment (EIA) report for \
recycled figures: the same number with the same breakdown given for DIFFERENT places or \
subjects, which suggests text was copied rather than measured. You are a neutral accuracy \
checker: never accuse anyone, never use words like "lie", "fraud" or "fake".

Answer each question. Do not give a grade: it is computed from your answers.
Return JSON only:
{"different_subjects": true/false/"unclear",
 "explained": true/false,
 "reason": "1-2 neutral sentences",
 "explanation_quote": "verbatim sentence that explains why the figures are identical, or null",
 "explanation_page": page number of that quote, or null}

Questions:
- different_subjects: are the figures given for clearly different places or subjects (e.g.
  two different parks, or one park and the whole island)? false if they are the same
  subject; "unclear" if the subjects might overlap or the report may cite one common source.
- explained: does the report explain it (e.g. says the figure is for the whole area in
  each place, or names one common source for all)? If true, give explanation_quote.
explanation_quote must be copied character for character from the page text, or null."""


PART_TOTAL_RULE = """

Part-vs-total rule (applies here: one statement gives a total, the other a smaller figure):
a smaller value for a component (e.g. "the airport needs 71 ha") is NOT inconsistent with
a larger total (e.g. "total reclaimed land 194 ha") unless the report says the component
IS the total. In that case set same_scope to false and say which figure is the part and
which the total. Set same_scope true only if the report presents the smaller figure as the
whole amount."""


def tri(value):
    """true / false / "unclear" from a model answer (missing or odd values are "unclear")."""
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    return True if v == "true" else False if v == "false" else "unclear"


def compute_grade(kind, v):
    """The grade from the model's answers (never the model's own grade).

    pairs:    RED    same subject, same place, same scope, incompatible, not explained
              ORANGE same subject, incompatible, not explained, place or scope unclear
              NONE   otherwise
    recycled: RED    clearly different subjects, not explained; ORANGE unclear; NONE otherwise
    statement pairs ("no X" vs "X exists") are incompatible by construction (statement_pairs
    only pairs opposite claims about the same X), so the model's incompatible answer is not
    used for them: whether the places differ is already asked in same_place.
    """
    if v["explained"] is True:
        return "NONE"
    if kind == "recycled":
        return {True: "RED", "unclear": "ORANGE"}.get(v["different_subjects"], "NONE")
    incompatible = True if kind == "statement" else v["incompatible"]
    if v["same_subject"] is not True or incompatible is not True:
        return "NONE"
    if v["same_place"] is True and v["same_scope"] is True:
        return "RED"
    if False in (v["same_place"], v["same_scope"]):
        return "NONE"
    return "ORANGE"


# A sentence ends at . ! ? before a capital or digit ("sq.km" or "No.15" do not end one),
# or at a bullet glyph from Word/PDF lists.
SENTENCE_END = re.compile(r"[.!?](?=\s+(?:[^\w\s]\s+)?[\"'(]?[A-Z0-9])|[\uf0b7\uf0a7\uf0d8\u2022\u25aa\u25cf]\s*")
MAX_SENTENCE_CHARS = 800     # tables run together have no sentence ends: cap the window


def full_sentences(quote, page_text):
    """The complete sentence(s) of the page that contain the quote, never a fragment.

    "...in the range of 18 to 16300 mg/l" -> "The chlorides and sulphates were found to be in
    the range of 18 to 16300 mg/l and 4.8 to 2150 mg/l respectively." Falls back to the quote
    if it is not on the page. Text with no sentence ends is cut at word boundaries around
    the quote (MAX_SENTENCE_CHARS).
    """
    q, page = claims_mod.normalize(quote), claims_mod.normalize(page_text)
    i = page.find(q) if q else -1
    if i == -1:
        exact, _ = claims_mod.repair_quote(q, page)
        i = page.find(exact) if exact else -1
        if i == -1:
            return q
        q = exact
    j = i + len(q)
    ends = [m.end() for m in SENTENCE_END.finditer(page)]
    start = max([e for e in ends if e <= i], default=0)
    end = min([e for e in ends if e >= j], default=len(page))
    spare = max(0, (MAX_SENTENCE_CHARS - len(q)) // 2)
    start, end = max(start, i - spare), min(end, j + spare)
    if start > 0 and page[start - 1] != " " and start != i:     # cut window: whole words only
        start = page.find(" ", start) + 1 or start
    if end < len(page) and page[end - 1] not in ".!?" and end != j:
        end = page.rfind(" ", j, end) if page.rfind(" ", j, end) > 0 else end
    return page[start:end].strip()


def verdict_messages(cand, pages, hits):
    lines = []
    for i, c in enumerate(cand["claims"], 1):
        text = full_sentences(c["quote"], pages.get(c["page"], "")) if pages.get(c["page"]) else c["quote"]
        lines.append(f'Statement {i} (page {c["page"]}, subject: {c["subject"]}): "{text}"')
    if cand["kind"] == "recycled":
        lines.append(f"Other figures shared by all these pages: {cand['breakdown']}")
    hit_lines = [f'- p.{h["page"]} {"near quote" if h["near_quote"] else "elsewhere"}, '
                 f'"{h["word"]}": ...{h["snippet"]}...' for h in hits[:MAX_HITS]]
    page_blocks = [f"=== Page {p} full text ===\n{pages.get(p, '')[:MAX_PAGE_CHARS]}"
                   for p in sorted({c["page"] for c in cand["claims"]})]
    user = "\n".join(lines) + "\n\nPossible explanation words found:\n" + \
        ("\n".join(hit_lines) or "- none") + "\n\n" + "\n\n".join(page_blocks)
    system = RECYCLED_PROMPT if cand["kind"] == "recycled" else VERDICT_PROMPT
    if cand.get("part_total"):
        # Added only for part-vs-total pairs, so cached verdicts for other pairs stay valid.
        system += PART_TOTAL_RULE
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_verdict(raw, cand, pages):
    """Validate the model's verdict; verify explanation_quote; enforce neutral wording."""
    if not isinstance(raw, dict):
        return None
    needed = (("different_subjects", "explained") if cand["kind"] == "recycled" else
              ("same_subject", "same_place", "same_scope", "incompatible", "explained"))
    if any(k not in raw for k in needed):
        return None
    answers = {k: tri(raw[k]) for k in needed}
    grade = compute_grade(cand["kind"], answers)
    reason = claims_mod.normalize(str(raw.get("reason") or ""))
    if not reason or BANNED_WORDS.search(reason):
        reason = "The two statements give different information; see quotes."
    expl, expl_page = raw.get("explanation_quote"), None
    if expl:
        expl, expl_page = verify_explanation(str(expl), raw.get("explanation_page"), cand, pages)
    return {"grade": grade, "reason": reason, "explanation_quote": expl,
            "explanation_page": expl_page,
            "same_subject": answers.get("same_subject",
                                        None if cand["kind"] != "recycled"
                                        else tri_not(answers["different_subjects"])),
            "same_place": answers.get("same_place"), "same_scope": answers.get("same_scope"),
            "incompatible": answers.get("incompatible"), "explained": answers["explained"]}


def tri_not(value):
    return value if value == "unclear" else not value


def verify_explanation(quote, page_hint, cand, pages):
    """Exact (or repaired >= 0.90) page text for the explanation quote, else (None, None)."""
    order = [page_hint] if page_hint in pages else []
    order += [c["page"] for c in cand["claims"] if c["page"] not in order]
    for p in order:
        text = pages.get(p, "")
        if claims_mod.quote_on_page(quote, text):
            return claims_mod.normalize(quote), p
        exact, _ = claims_mod.repair_quote(quote, text)
        if exact:
            return exact, p
    log.info("explanation quote not found on the pages; ignored: %s", quote[:80])
    return None, None


def estimate_cost(cands, pages):
    total, uncached = 0.0, 0
    for cand in cands:
        messages = verdict_messages(cand, pages, explanation_hits(cand, pages))
        if llm.is_cached(llm.ULTRA, messages, thinking=None, max_tokens=VERDICT_MAX_TOKENS,
                         temperature=0):
            continue
        chars = sum(len(m["content"]) for m in messages)
        total += llm.cost_usd(llm.ULTRA, chars // claims_mod.CHARS_PER_TOKEN,
                              EST_OUTPUT_TOKENS) or 0.0
        uncached += 1
    return total, uncached


def finding(cand, v, hits, n):
    kind_ = "recycled_figure" if cand["kind"] == "recycled" else "contradiction"
    return {
        "id": f"{'rf' if kind_ == 'recycled_figure' else 'ct'}-{n:03d}", "type": kind_,
        "candidate": cand["kind"], "grade": v["grade"],
        "message": NEUTRAL if v["grade"] in ("RED", "ORANGE") else "Explained or normal; not a finding.",
        "reason": v["reason"], "pages": sorted({c["page"] for c in cand["claims"]}),
        "quotes": [{"page": c["page"], "text": c["quote"], "claim_id": c["id"],
                    "subject": c["subject"], "value": c["value"], "unit": c["unit"],
                    **({"also_on": c["also_on"]} if c.get("also_on") else {})}
                   for c in cand["claims"]],
        "breakdown": cand.get("breakdown"),
        "explanation_quote": v["explanation_quote"], "explanation_page": v["explanation_page"],
        "explanation_hits": len(hits),
        "same_subject": v["same_subject"], "same_place": v.get("same_place"),
        "same_scope": v.get("same_scope"), "incompatible": v["incompatible"],
        "explained": v["explained"], "part_total": cand.get("part_total", False),
        "model": llm.ULTRA,
    }


def sentence_with(number_, text):
    """First sentence of the (normalised) page text that contains the number, or None."""
    for sentence in re.split(r"(?<=[.;])\s+", claims_mod.normalize(text)):
        if number_ in claims_mod._numbers(sentence):
            return sentence
    return None


def align_evidence(f, pages, ledger=()):
    """Make each shown quote contain a figure the reason talks about.

    For each quote: the reason's numbers that are claim VALUES on that page are the
    figures the reason means there (any digit in the page text is not enough: a "4" in
    a page header like "Chapter-4(B)" is not the "4 ha" the reason talks about). Without
    a ledger, numbers in the page text are used instead. If the quote has none of them,
    use a verified ledger claim on that page with that value, else the page sentence
    with it (exact page text). If nothing fits, a RED finding drops to ORANGE with a
    note. Deterministic, no LLM.
    """
    # Numbers in labels ("Statement 2", "page 851", "p.940") are not figures.
    reason = re.sub(r"\b(?:statements?|pages?|p\.)\s*\d+(?:\s*(?:and|,|&)\s*\d+)*", " ",
                    f["reason"], flags=re.IGNORECASE)
    wanted = claims_mod._numbers(reason)
    for q in f["quotes"]:
        page_text = pages.get(q["page"], "")
        if ledger:
            values = {number(c["value"]) for c in ledger
                      if c["page"] == q["page"] and c.get("verified")}
            on_page = wanted & values
        else:
            on_page = wanted & claims_mod._numbers(page_text)
        if not on_page or claims_mod._numbers(q["text"]) & on_page:
            continue
        match = next((c for c in ledger if c["page"] == q["page"] and c.get("verified")
                      and number(c["value"]) in on_page), None)
        if match is None:
            match = next((c for c in ledger if c["page"] == q["page"] and c.get("verified")
                          and claims_mod._numbers(c["quote"]) & on_page), None)
        if match is not None:
            new = {"text": match["quote"], "claim_id": match["id"], "subject": match["subject"],
                   "value": match["value"], "unit": match["unit"]}
        else:
            sentence = next((s for n in sorted(on_page) if (s := sentence_with(n, page_text))),
                            None)
            new = {"text": sentence, "claim_id": None} if sentence else None
        if new and claims_mod.quote_on_page(new["text"], page_text):
            q.update(new, reselected=True)
        else:
            if f["grade"] == "RED":
                f["grade"] = "ORANGE"
            f["evidence_note"] = (f"p.{q['page']}: no quote found with the figure the reason "
                                  f"refers to; verify.")
    return f


TRIAGE = True          # LIGHTNING screens candidate pairs before any Ultra verdict
TRIAGE_BATCH = 2       # pairs per LIGHTNING call; with ~1,500 chars of context per
                       # quote, larger batches dropped a real ORANGE (validated)
TRIAGE_ANSWERS = ("yes", "no", "unsure")
TRIAGE_PROMPT = """You screen pairs of statements from one Indian Environmental Impact \
Assessment report before a slower, expensive check. For each numbered pair, decide whether \
the two quotes COULD be about the same subject, place and scope while giving incompatible \
values or statements.

Answer "no" when they are clearly about different things or clearly compatible, for example:
different groups (birds vs flora, mammals vs reptiles), a subset vs a total (endemic species \
vs all species, one part vs the whole, with the part not larger than the whole), two \
different parks or areas with no part-whole relation, distances to different places.
Answer "yes" when they look directly incompatible. Use "unsure" only when the text leaves \
it genuinely open.

Return JSON only: {"answers": [{"pair": 1, "answer": "yes" | "no" | "unsure"}, ...]}"""


TRIAGE_CONTEXT_CHARS = 1500   # page text shown around each quote


def quote_context(claim, pages, chars=TRIAGE_CONTEXT_CHARS):
    """About `chars` characters of the claim's page around its quote ("" if no page text)."""
    text = claims_mod.normalize((pages or {}).get(claim["page"], ""))
    if not text:
        return ""
    q = claims_mod.normalize(claim["quote"])
    at = text.find(q)
    if at < 0:
        return text[:chars]
    half = max(0, (chars - len(q)) // 2)
    start = max(0, at - half)
    end = min(len(text), at + len(q) + half)
    return ("..." if start else "") + text[start:end] + ("..." if end < len(text) else "")


def triage_messages(batch, pages=None):
    lines = []
    for i, cand in enumerate(batch, 1):
        a, b = cand["claims"][:2]
        lines.append(f'{i}. A (page {a["page"]}, subject: {a["subject"]}): "{a["quote"]}"\n'
                     f'   B (page {b["page"]}, subject: {b["subject"]}): "{b["quote"]}"')
        if pages:
            lines.append(f"   Context of A: {quote_context(a, pages)}\n"
                         f"   Context of B: {quote_context(b, pages)}")
    return [{"role": "system", "content": TRIAGE_PROMPT + (TRIAGE_CONTEXT_NOTE if pages else "")},
            {"role": "user", "content": "\n".join(lines)}]


TRIAGE_CONTEXT_NOTE = """

Each pair also shows page text around both quotes. Use it:
- a nearby sentence may show that a figure refers to something else (e.g. one part of a
  total), which makes the pair compatible: "no";
- if one place is part of the other (e.g. a national park inside the island), check the
  figures for the same kind of thing near both quotes: a figure for the part that is LARGER
  than the figure for the whole is incompatible: "yes";
- if the two pages describe the same thing with different numbers: "yes"."""


TRIAGE_QUOTE_BATCH = 8   # pairs per call in the quotes-only view
TRIAGE_MODE = "safe"     # safe: two views (quotes, quotes + context); fast: quotes only


def triage(cands, pages=None):
    """yes / no / unsure per candidate (same order), from batched, cached LIGHTNING calls.

    With pages ({page: text}) two views are asked and combined conservatively:
      quotes only (TRIAGE_QUOTE_BATCH pairs per call) and quotes with ~TRIAGE_CONTEXT_CHARS
      of page context each (TRIAGE_BATCH pairs per call).
    A candidate is dropped ("no") only if BOTH views say "no"; "yes" if either says "yes";
    otherwise "unsure". Validation showed each view alone drops a different real finding.
    Recycled-figure candidates are not triaged ("yes"). A missing or unclear answer is
    "unsure", so a candidate is only skipped when the model clearly says "no".
    """
    if not pages:
        return _triage_pass(cands, None, TRIAGE_QUOTE_BATCH)
    quotes_only = _triage_pass(cands, None, TRIAGE_QUOTE_BATCH)
    with_context = _triage_pass(cands, pages, TRIAGE_BATCH)
    return [combine_triage(a, b) for a, b in zip(quotes_only, with_context)]


def combine_triage(a, b):
    """Conservative ensemble: no only if both no; yes if either yes; else unsure."""
    if a == "no" and b == "no":
        return "no"
    if "yes" in (a, b):
        return "yes"
    return "unsure"


def _triage_pass(cands, pages, batch_size):
    answers = ["yes" if c["kind"] == "recycled" else None for c in cands]
    todo = [i for i, a in enumerate(answers) if a is None]
    batches = [todo[s:s + batch_size] for s in range(0, len(todo), batch_size)]
    raws, _ = llm.run_parallel(
        lambda idx: claims_mod.chat_json(
            llm.LIGHTNING, triage_messages([cands[i] for i in idx], pages), max_tokens=600),
        batches)
    for idx, raw in zip(batches, raws):
        got = {}
        for item in (raw or {}).get("answers", []) if isinstance(raw, dict) else []:
            try:
                n, ans = int(item.get("pair")), str(item.get("answer", "")).lower().strip()
            except (TypeError, ValueError, AttributeError):
                continue
            if ans in TRIAGE_ANSWERS:
                got[n] = ans
        for k, i in enumerate(idx, 1):
            answers[i] = got.get(k, "unsure")
    return answers


CHUNK = 400   # candidates triaged + judged per round (multiple of both triage batch sizes)


def check(cands, pages, max_cost_usd=MAX_COST_USD, pdf_stem=None, ledger=(), use_triage=None):
    """Run the Ultra verdict on each candidate. Returns findings (all grades, incl. NONE).

    ledger: the claims, used to re-select evidence quotes (align_evidence).
    use_triage: LIGHTNING screens the candidates first and those it answers "no" are not
    sent to Ultra (default TRIAGE). last_run["triage"] counts the answers.
    Candidates go through in rounds of CHUNK (triage, then verdicts), so memory stays
    small on long reports; with pdf_stem, findings are written after every round, so an
    interrupted run keeps what it has (and resumes from the cache).
    """
    start = llm.session_cost_usd
    findings, stopped, failed = [], None, 0
    do_triage = use_triage if use_triage is not None else TRIAGE
    all_answers, triaged_out = [], []
    path = None
    if pdf_stem:
        path = FINDINGS_DIR / pdf_stem / "contradictions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def ask(item):   # runs on the thread pool; results are used in candidate order
        _, cand = item
        hits = explanation_hits(cand, pages)
        raw = claims_mod.chat_json(llm.ULTRA, verdict_messages(cand, pages, hits),
                                   VERDICT_MAX_TOKENS, thinking=None)
        return hits, raw

    for lo in range(0, len(cands), CHUNK):
        chunk = cands[lo:lo + CHUNK]
        # Finding ids follow the position in the full candidate list, so skipping a
        # candidate (triage, failure) never renumbers the others.
        numbered = list(enumerate(chunk, lo + 1))
        if do_triage:
            answers = triage(chunk, pages if TRIAGE_MODE == "safe" else None)
            all_answers += answers
            triaged_out += [[c["id"] for c in cand["claims"]]
                            for cand, a in zip(chunk, answers) if a == "no"]
            numbered = [(n, cand) for (n, cand), a in zip(numbered, answers) if a != "no"]
        # The cap counts triage spend too (start is taken before triage).
        left = max_cost_usd - (llm.session_cost_usd - start)
        replies, stop = llm.run_parallel(
            ask, numbered, estimate=lambda item: estimate_cost([item[1]], pages)[0],
            max_cost_usd=left)
        if stop is not None:
            not_run = len(numbered) - stop + len(cands) - (lo + len(chunk))
            stopped = (f"cost cap ${max_cost_usd:.2f} reached "
                       f"(spent ${llm.session_cost_usd - start:.4f}); "
                       f"stopped at candidate {numbered[stop][0] if stop < len(numbered) else lo + len(chunk)} "
                       f"of {len(cands)}; about {not_run} candidates not judged")
            log.warning(stopped)
            numbered = numbered[:stop]
        new = []
        for (n, cand), (hits, raw) in zip(numbered, replies):
            v = parse_verdict(raw, cand, pages)
            if v is None:
                failed += 1
                log.warning("no valid verdict for candidate %s",
                            [c["id"] for c in cand["claims"]])
                continue
            new.append(align_evidence(finding(cand, v, hits, n), pages, ledger))
        findings += new
        if path:
            with path.open("a", encoding="utf-8") as f:
                for x in new:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
        if stopped:
            break

    if do_triage:
        last_run["triage"] = {a: all_answers.count(a) for a in TRIAGE_ANSWERS}
        last_run["triage_answers"] = all_answers
        last_run["triaged_out"] = triaged_out
    else:
        last_run["triage"], last_run["triage_answers"], last_run["triaged_out"] = None, None, []
    last_run.update(stopped=stopped, failed=failed, verdicts=len(findings),
                    cost_usd=llm.session_cost_usd - start)
    return findings


def save_findings(pdf_stem, findings):
    path = FINDINGS_DIR / pdf_stem / "contradictions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for x in findings:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    return path


# ---------- step 4: evaluation ----------

def grade_ok(issue, grade):
    """Same rule as tests/test_known_issues.py: acceptable_grades if given, else expected."""
    return grade in issue.get("acceptable_grades", [issue["expected_grade"]])


def quotes_match(a, b):
    """Same passage: one quote contains the other, or they share >= 60% of the shorter's words."""
    a, b = claims_mod.normalize(a).lower(), claims_mod.normalize(b).lower()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    wa, wb = set(a.split()), set(b.split())
    return len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def covers_issue(f, issue):
    """Every page of the issue has a finding quote matching an issue quote on that page."""
    for page in issue["pages"]:
        known = [q["text"] for q in issue["quotes"] if q["page"] == page]
        found = [q["text"] for q in f["quotes"] if q["page"] == page]
        if not any(quotes_match(k, x) for k in known for x in found):
            return False
    return True


def match_issue(issue, findings):
    """The finding about this known issue (same pages AND matching quotes), or None.

    Matching on pages alone is not enough: two pages can hold several unrelated
    candidate pairs (e.g. p.444/751 has both coral 2 vs 4 ha and runway 194 vs 71 ha).
    """
    wanted = set(issue["pages"])
    want_type = "recycled_figure" if issue["type"] == "recycled_figure" else "contradiction"
    best = None
    for f in findings:
        if not wanted <= set(f["pages"]):
            continue
        if issue["type"] != "negative_control" and f["type"] != want_type:
            continue
        if not covers_issue(f, issue):
            continue
        rank = {"RED": 0, "ORANGE": 1, "NONE": 2}[f["grade"]]
        if best is None or rank < {"RED": 0, "ORANGE": 1, "NONE": 2}[best["grade"]]:
            best = f
    return best


def evaluate(findings, known_issues):
    """Per known issue: found?, grade, ok?. Negative controls pass when not flagged.

    Issues whose status is in NOT_SCORED (under_review, candidate_new_finding) are
    reported with scored=False and left out of score().
    """
    rows = []
    for issue in known_issues:
        f = match_issue(issue, findings)
        grade = f["grade"] if f else "NONE"
        flagged = grade in ("RED", "ORANGE")
        if issue["expected_grade"] == "NONE":
            ok = not flagged
        else:
            ok = f is not None and grade_ok(issue, grade)
        rows.append({"id": issue["id"], "type": issue["type"], "pages": issue["pages"],
                     "expected": issue.get("acceptable_grades", [issue["expected_grade"]]),
                     "found": f is not None, "grade": grade if f else None,
                     "finding_id": f["id"] if f else None, "ok": ok,
                     "status": issue.get("status"),
                     "scored": issue.get("status") not in NOT_SCORED})
    return rows


def score(rows):
    """(passed, scored) over the scored rows only."""
    scored = [r for r in rows if r["scored"]]
    return sum(r["ok"] for r in scored), len(scored)


def control_candidate(issue):
    """A candidate built straight from a known issue's quotes (for the negative control)."""
    cl = [{"id": f"{issue['id']}-q{i}", "page": q["page"], "type": "area", "quote": q["text"],
           "subject": issue["summary"], "value": None, "unit": None}
          for i, q in enumerate(issue["quotes"], 1)]
    return {"kind": "numeric", "claims": cl}
