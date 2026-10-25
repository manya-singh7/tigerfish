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
                                       grade RED | ORANGE | NONE, reason, explanation_quote
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
MIN_BREAKDOWN = 3            # recycled figure: at least this many other figures shared too
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


def absence_topic(claim):
    """Key words of the thing said to be absent, or None if the claim is not an absence."""
    text = claims_mod.normalize(claim["quote"])
    if not ABSENCE.search(text):
        return None
    m = ABSENT_THING.search(text)
    if m:   # "no coral exists in" -> coral
        after = " ".join(re.findall(r"[A-Za-z]+", text[m.end():])[:3])
        topic = {w for w in keywords(after) if not PRESENCE.fullmatch(w)}
        if topic:
            return topic
    return keywords(claim["subject"]) - keywords("presence absence")


def statement_pairs(claims):
    out = []
    usable = [c for c in claims if c.get("verified")]
    for a in usable:
        if a["type"] != "statement":
            continue
        topic = absence_topic(a)
        if not topic:
            continue
        for b in usable:
            if b["page"] == a["page"] or b["type"] not in ("statement", "species"):
                continue
            q = claims_mod.normalize(b["quote"])
            if NEGATION.search(q) or not PRESENCE.search(q):
                continue
            if topic & keywords(q):
                out.append({"kind": "statement", "claims": [a, b]})
    return out


def recycled_figures(claims):
    """The same figure + same breakdown on different pages for different subjects.

    Groups sharing the same set of pages are merged; the largest figure is the headline
    and the other shared figures are its breakdown.
    """
    usable = [c for c in claims if numeric(c) and c.get("verified") and kind(c) == "amount"]
    by_value = {}
    for c in usable:
        by_value.setdefault((number(c["value"]), unit_key(c["unit"])), []).append(c)

    page_values = {}
    for c in usable:
        page_values.setdefault(c["page"], set()).add(number(c["value"]))

    groups = {}
    for (value, _), group in by_value.items():
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
        shared = set.intersection(*(page_values[p] for p in pages)) - {value}
        if len(shared) < MIN_BREAKDOWN:
            continue
        best = groups.get(pages)
        if best is None or value > best["value"]:
            groups[pages] = {"kind": "recycled", "value": value, "claims": members,
                             "breakdown": sorted(shared)}
    return list(groups.values())


def candidate_pairs(claims, max_candidates=MAX_CANDIDATES):
    """All candidates (recycled first, then statements, then numeric), capped.

    Numeric pairs already covered by a recycled-figure group are suppressed (counted
    in last_run["candidates_suppressed"]).
    """
    recycled = recycled_figures(claims)
    numeric_ = numeric_pairs(claims)
    kept_numeric = [c for c in numeric_ if not covered_by_recycled(c, recycled)]
    last_run["candidates_suppressed"] = len(numeric_) - len(kept_numeric)
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

VERDICT_PROMPT = """You check an Indian Environmental Impact Assessment (EIA) report for \
internal inconsistencies. You are a neutral accuracy checker: never accuse anyone, never \
use words like "lie", "fraud" or "fake".

Return JSON only:
{"same_subject": true/false, "incompatible": true/false, "explained": true/false,
 "grade": "RED" | "ORANGE" | "NONE",
 "reason": "1-2 neutral sentences",
 "explanation_quote": "verbatim sentence from one of the pages that explains the difference, or null",
 "explanation_page": page number of that quote, or null}

Grades:
- RED: same subject, place and scope; the statements are directly incompatible; the report
  does not explain the difference anywhere on these pages.
- ORANGE: likely inconsistent, but the scope is ambiguous (e.g. different survey areas or
  dates might be meant).
- NONE: the report explains the difference (e.g. before/after an event, revised figures,
  a subset vs a total), the scopes clearly differ, or it is normal practice (e.g. restoring
  more area than is lost).
explanation_quote must be copied character for character from the page text, or null."""

RECYCLED_PROMPT = """You check an Indian Environmental Impact Assessment (EIA) report for \
recycled figures: the same number with the same breakdown given for DIFFERENT places or \
subjects, which suggests text was copied rather than measured. You are a neutral accuracy \
checker: never accuse anyone, never use words like "lie", "fraud" or "fake".

Return JSON only:
{"same_subject": true/false, "incompatible": true/false, "explained": true/false,
 "grade": "RED" | "ORANGE" | "NONE",
 "reason": "1-2 neutral sentences",
 "explanation_quote": "verbatim sentence that explains why the figures are identical, or null",
 "explanation_page": page number of that quote, or null}

Grades:
- RED: clearly different subjects (e.g. two different parks, or one park and the whole
  island) share an identical figure and breakdown, with no explanation.
- ORANGE: identical figures, but the subjects might overlap or the report may cite one
  common source.
- NONE: the report explains it (e.g. the figure is explicitly for the whole area in each
  place), or the subjects are actually the same.
explanation_quote must be copied character for character from the page text, or null."""


PART_TOTAL_RULE = """

Part-vs-total rule (applies here: one statement gives a total, the other a smaller figure):
a smaller value for a component (e.g. "the airport needs 71 ha") is NOT inconsistent with
a larger total (e.g. "total reclaimed land 194 ha") unless the report says the component
IS the total. In that case grade NONE and say which figure is the part and which the total.
Grade RED or ORANGE only if the report presents the smaller figure as the whole amount."""


def verdict_messages(cand, pages, hits):
    lines = []
    for i, c in enumerate(cand["claims"], 1):
        lines.append(f'Statement {i} (page {c["page"]}, subject: {c["subject"]}): "{c["quote"]}"')
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
    grade = str(raw.get("grade", "")).upper()
    if grade not in GRADES:
        return None
    reason = claims_mod.normalize(str(raw.get("reason") or ""))
    if not reason or BANNED_WORDS.search(reason):
        reason = "The two statements give different information; see quotes."
    expl, expl_page = raw.get("explanation_quote"), None
    if expl:
        expl, expl_page = verify_explanation(str(expl), raw.get("explanation_page"), cand, pages)
    return {"grade": grade, "reason": reason, "explanation_quote": expl,
            "explanation_page": expl_page,
            "same_subject": raw.get("same_subject"), "incompatible": raw.get("incompatible"),
            "explained": raw.get("explained")}


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
                    "subject": c["subject"], "value": c["value"], "unit": c["unit"]}
                   for c in cand["claims"]],
        "breakdown": cand.get("breakdown"),
        "explanation_quote": v["explanation_quote"], "explanation_page": v["explanation_page"],
        "explanation_hits": len(hits),
        "same_subject": v["same_subject"], "incompatible": v["incompatible"],
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
TRIAGE_BATCH = 8       # pairs per LIGHTNING call
TRIAGE_ANSWERS = ("yes", "no", "unsure")
TRIAGE_PROMPT = """You screen pairs of statements from one Indian Environmental Impact \
Assessment report before a slower, expensive check. For each numbered pair, decide whether \
the two quotes COULD be about the same subject, place and scope while giving incompatible \
values or statements.

Answer "no" only when they are clearly about different things (different subjects, places \
or scopes, or one figure is clearly a part of the other) or clearly compatible. Answer "yes" \
when they look directly incompatible. If in any doubt, answer "unsure".

Return JSON only: {"answers": [{"pair": 1, "answer": "yes" | "no" | "unsure"}, ...]}"""


def triage_messages(batch):
    lines = []
    for i, cand in enumerate(batch, 1):
        a, b = cand["claims"][:2]
        lines.append(f'{i}. A (page {a["page"]}, subject: {a["subject"]}): "{a["quote"]}"\n'
                     f'   B (page {b["page"]}, subject: {b["subject"]}): "{b["quote"]}"')
    return [{"role": "system", "content": TRIAGE_PROMPT},
            {"role": "user", "content": "\n".join(lines)}]


def triage(cands):
    """yes / no / unsure per candidate (same order), from batched, cached LIGHTNING calls.

    Recycled-figure candidates are not triaged ("yes": the question of incompatible
    values does not fit identical figures). A missing or unclear answer is "unsure",
    so a candidate is only skipped when the model clearly says "no".
    """
    answers = ["yes" if c["kind"] == "recycled" else None for c in cands]
    todo = [i for i, a in enumerate(answers) if a is None]
    for start in range(0, len(todo), TRIAGE_BATCH):
        idx = todo[start:start + TRIAGE_BATCH]
        raw = claims_mod.chat_json(llm.LIGHTNING, triage_messages([cands[i] for i in idx]),
                                   max_tokens=600)
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


def check(cands, pages, max_cost_usd=MAX_COST_USD, pdf_stem=None, ledger=(), use_triage=None):
    """Run the Ultra verdict on each candidate. Returns findings (all grades, incl. NONE).

    ledger: the claims, used to re-select evidence quotes (align_evidence).
    use_triage: LIGHTNING screens the candidates first and those it answers "no" are not
    sent to Ultra (default TRIAGE). last_run["triage"] counts the answers.
    """
    start = llm.session_cost_usd
    findings, stopped, failed = [], None, 0
    # Finding ids follow the position in the full candidate list, so skipping a candidate
    # (triage, failure) never renumbers the others.
    numbered = list(enumerate(cands, 1))
    if use_triage if use_triage is not None else TRIAGE:
        answers = triage(cands)
        last_run["triage"] = {a: answers.count(a) for a in TRIAGE_ANSWERS}
        last_run["triage_answers"] = answers
        last_run["triaged_out"] = [[c["id"] for c in cand["claims"]]
                                   for cand, a in zip(cands, answers) if a == "no"]
        numbered = [(n, cand) for (n, cand), a in zip(numbered, answers) if a != "no"]
    else:
        last_run["triage"], last_run["triage_answers"], last_run["triaged_out"] = None, None, []
    for n, cand in numbered:
        hits = explanation_hits(cand, pages)
        messages = verdict_messages(cand, pages, hits)
        est, _ = estimate_cost([cand], pages)
        spent = llm.session_cost_usd - start
        if spent + est > max_cost_usd:
            stopped = f"cost cap ${max_cost_usd:.2f} reached (spent ${spent:.4f})"
            log.warning(stopped)
            break
        raw = claims_mod.chat_json(llm.ULTRA, messages, VERDICT_MAX_TOKENS, thinking=None)
        v = parse_verdict(raw, cand, pages)
        if v is None:
            failed += 1
            log.warning("no valid verdict for candidate %s",
                        [c["id"] for c in cand["claims"]])
            continue
        findings.append(align_evidence(finding(cand, v, hits, n), pages, ledger))
    last_run.update(stopped=stopped, failed=failed, verdicts=len(findings),
                    cost_usd=llm.session_cost_usd - start)
    if pdf_stem:
        save_findings(pdf_stem, findings)
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
