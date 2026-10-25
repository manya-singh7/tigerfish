"""Claim extraction: turn EIA pages (or table images) into a ledger of checkable claims.

Each claim: {id, page, type, subject, value, unit, quote, context, model, source, verified}
  type     quantity | distance | area | species | count | statement
  quote    verbatim from the page; verified=True only if it appears in the page text
           after whitespace normalisation (same rule as tests/test_known_issues.py).
           If the model's quote is slightly off (it "fixed" a typo), the closest page
           substring with similarity >= MIN_QUOTE_SIMILARITY replaces it and
           quote_repaired=True (the model's version is kept as model_quote).
           Unverified claims (verified=False) must never be shown as evidence.
  Junk filter: claims whose value is not in their quote are dropped, and near-duplicates
  on a page (same type and subject, similar quotes) are merged.
           Claims read from a standalone image have no text layer: verified=None.

Text pages go to LIGHTNING (thinking off), one page per call. Pages flagged
needs_vision go to SUPER_VL with the page image plus its text layer.
Broken JSON gets one retry, then the page is skipped and logged.
A cost cap (MAX_COST_USD) stops the run before it would be exceeded.
The ledger is saved to cache/claims/<pdf_stem>/claims.jsonl.
"""

import difflib
import json
import logging
import re
from pathlib import Path

from tigerfish import llm

ROOT = Path(__file__).resolve().parent.parent
LEDGER_DIR = ROOT / "cache" / "claims"

CLAIM_TYPES = ("quantity", "distance", "area", "species", "count", "statement")
MAX_COST_USD = 0.50          # stop a run before real API spend would pass this
MAX_PAGE_CHARS = 12000       # page text sent to the model (EIA pages are ~2-6k)
TEXT_MAX_TOKENS = 3000       # reply budget per page
VISION_MAX_TOKENS = 4000
EST_OUTPUT_TOKENS = 1500     # used only for cost estimates
EST_IMAGE_TOKENS = 3000      # rough token cost of one 150-dpi page image, for estimates
CHARS_PER_TOKEN = 4
MIN_QUOTE_SIMILARITY = 0.90      # fuzzy quote repair: accept the closest page text at/above this
MIN_DUPLICATE_SIMILARITY = 0.85  # same page+type+subject and quotes this similar = duplicate
REPAIR_CANDIDATES = 5            # quote repair: word windows refined at character level
REPAIR_SLACK = 3                 # ...each nudged by up to this many words at either end

log = logging.getLogger(__name__)
last_run = {}                # stats of the most recent extract_claims() call

CLAIM_PROMPT = """You extract factual, checkable claims from one page of an Indian \
Environmental Impact Assessment (EIA) report. Return JSON only, no prose, in this shape:
{"claims": [{"type": "...", "subject": "...", "value": ..., "unit": "...", "quote": "...", "context": "..."}]}

Rules:
- type is one of: quantity, distance, area, species, count, statement.
  quantity = a measured amount (e.g. 45 KLD water, 1.2 million TPA, 4 ha restored)
  distance = how far something is from something else
  area = a land or sea area (ha, sq km)
  species = a named species reported from the area (one claim per species)
  count = a number of species or items recorded (e.g. 330 species of fauna)
  statement = a checkable presence/absence or factual statement (e.g. "no coral exists in the bay")
- Only claims a reviewer could check against other pages or outside data. Skip opinions,
  plans without numbers, generic descriptions, headings, references and contents lists.
- quote: copy the exact words from the page text, character for character, keeping typos
  and odd spacing. One sentence or phrase, at most 300 characters, containing the value.
- value: a number when numeric (e.g. 330, 1.5), otherwise short text. unit: e.g. "ha",
  "km", "sq km", "species", or null.
- subject: what the claim is about, in a few words (e.g. "Galathea National Park fauna").
- context: a few words on where the number comes from (e.g. "ZSI survey", "executive summary").
- If nothing qualifies, return {"claims": []}."""

VISION_NOTE = """
The page image is attached. Use it to read tables and figures. Quotes must still be
copied from the page text below when the text is there."""

TABLE_PROMPT = """Transcribe the table in this image exactly as printed. Return JSON only:
{"title": "table title or null",
 "columns": ["column header", ...],
 "rows": [["cell", ...], ...],
 "scientific_name_column": "the header of the column holding scientific (Latin) names, or null"}

Rules:
- One entry in rows per table row; each row has one cell per column, in column order.
- Copy every cell character by character exactly as printed, INCLUDING misspellings.
  Never correct spelling, even when you know the right name. This is an audit: a
  misspelled species name (for example "Taupaia" instead of "Tupaia") is evidence and
  must be preserved exactly.
- A cell printed over two lines is one cell: join the lines with a single space.
- Use "" for empty cells. Flatten grouped headers (e.g. "Status IUCN Category")."""

RETRY_MSG = "That was not valid JSON. Return valid JSON only, in the requested shape, nothing else."


# ---------- helpers ----------

def normalize(text):
    """Collapse all whitespace to single spaces (the quote-matching rule)."""
    return " ".join((text or "").split())


def quote_on_page(quote, page_text):
    """True if the quote appears verbatim on the page after whitespace normalisation."""
    q = normalize(quote)
    return bool(q) and q in normalize(page_text)


def parse_json(reply):
    """Parse a model reply as a JSON object, tolerating ```json fences and stray prose."""
    text = (reply or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in reply")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON is not an object")
    return data


def chat_json(model, messages, max_tokens, thinking=False):
    """chat() and parse JSON; on failure retry once with RETRY_MSG. None if still broken."""
    reply = llm.chat(model, messages, thinking=thinking, max_tokens=max_tokens, temperature=0)
    try:
        return parse_json(reply)
    except ValueError as e:
        log.info("broken JSON from %s (%s); retrying once", model, e)
    retry = messages + [{"role": "assistant", "content": reply},
                        {"role": "user", "content": RETRY_MSG}]
    reply = llm.chat(model, retry, thinking=thinking, max_tokens=max_tokens, temperature=0)
    try:
        return parse_json(reply)
    except ValueError as e:
        log.warning("broken JSON from %s after retry (%s); skipping", model, e)
        return None


# ---------- pages -> claims ----------

def page_request(page):
    """(model, messages, max_tokens) for one page; vision pages get the PNG too."""
    text = page["text"][:MAX_PAGE_CHARS]
    if page.get("needs_vision") and page.get("image_path") and Path(page["image_path"]).exists():
        content = [{"type": "text", "text": f"{CLAIM_PROMPT}\n{VISION_NOTE}\n\n"
                                            f"Page {page['page']} text:\n\n{text}"},
                   llm.image_part(page["image_path"])]
        return llm.SUPER_VL, [{"role": "user", "content": content}], VISION_MAX_TOKENS
    messages = [{"role": "system", "content": CLAIM_PROMPT},
                {"role": "user", "content": f"Page {page['page']}:\n\n{text}"}]
    return llm.LIGHTNING, messages, TEXT_MAX_TOKENS


def estimate_page_cost(page):
    """Estimated USD for one page; 0 if the reply is already cached."""
    model, messages, max_tokens = page_request(page)
    if llm.is_cached(model, messages, thinking=False, max_tokens=max_tokens, temperature=0):
        return 0.0
    chars = sum(len(p.get("text", "")) if isinstance(p, dict) else len(p)
                for m in messages for p in (m["content"] if isinstance(m["content"], list)
                                            else [m["content"]]))
    tokens_in = chars // CHARS_PER_TOKEN + (EST_IMAGE_TOKENS if model == llm.SUPER_VL else 0)
    return llm.cost_usd(model, tokens_in, EST_OUTPUT_TOKENS) or 0.0


def estimate_cost(pages):
    """(estimated USD, number of pages that need a real call)."""
    costs = [estimate_page_cost(p) for p in pages if p.get("text") or p.get("image_path")]
    return sum(costs), sum(1 for c in costs if c > 0)


def repair_quote(quote, page_text, min_similarity=MIN_QUOTE_SIMILARITY):
    """Closest substring of the (whitespace-normalised) page to a model's quote.

    Models sometimes "fix" the report's text (Tusnami -> Tsunami). Returns
    (exact page substring, similarity) if similarity >= min_similarity, else (None, best).

    Two passes, so a 6,000-character page takes milliseconds:
    1. word overlap: score every window of the quote's word count, keep the best few;
    2. character similarity (difflib) on spans around those windows, nudging the
       start and end by a few words. Spans always start and end on word boundaries.
    """
    q, page = normalize(quote), normalize(page_text)
    if not q or not page:
        return None, 0.0
    words = page.split(" ")
    starts, pos = [], 0
    for w in words:
        starts.append(pos)
        pos += len(w) + 1
    qwords = q.lower().split(" ")
    n, qset = len(qwords), set(qwords)
    lowered = [w.lower() for w in words]
    overlap = [sum(w in qset for w in lowered[i:i + n]) for i in range(max(1, len(words) - n + 1))]
    candidates = sorted(range(len(overlap)), key=overlap.__getitem__, reverse=True)[:REPAIR_CANDIDATES]

    best, best_ratio = None, 0.0
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(q)
    for i in candidates:
        for a in range(max(0, i - REPAIR_SLACK), min(len(words), i + REPAIR_SLACK + 1)):
            for b in range(max(a + 1, i + n - REPAIR_SLACK), min(len(words), i + n + REPAIR_SLACK) + 1):
                span = page[starts[a]:starts[b - 1] + len(words[b - 1])]
                matcher.set_seq1(span)
                if matcher.quick_ratio() <= best_ratio:
                    continue
                ratio = matcher.ratio()
                if ratio > best_ratio:
                    best, best_ratio = span, ratio
    return (best, best_ratio) if best_ratio >= min_similarity else (None, best_ratio)


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text):
    out = set()
    for n in NUMBER.findall(str(text)):
        try:
            out.add(float(n.replace(",", "")))
        except ValueError:
            pass
    return out


def value_in_quote(value, quote):
    """Does the claim's value actually appear in its quote?

    Numbers: every number in the value must appear as a number in the quote
    (1,045 == 1045; 4 matches "4ha"). Text: the value appears in the quote, or at
    least 80% of its words (4+ letters) do. Empty values pass (nothing to check).
    """
    if value is None or str(value).strip() == "":
        return True
    if isinstance(value, bool):
        return True
    numbers = _numbers(value) if isinstance(value, (int, float, str)) else set()
    if numbers:
        return numbers <= _numbers(quote)
    v, q = normalize(str(value)).lower(), normalize(quote).lower()
    if v in q:
        return True
    words = [w for w in re.findall(r"[a-z]{4,}", v)]
    return bool(words) and sum(w in q for w in words) / len(words) >= 0.8


def similar(a, b):
    return difflib.SequenceMatcher(None, normalize(a).lower(), normalize(b).lower()).ratio()


def dedupe(claims):
    """Merge near-duplicates on a page: same type and subject, quote similarity >= threshold.

    The first claim is kept, unless a later duplicate is verified and it is not.
    """
    kept = []
    for c in claims:
        subject = normalize(str(c["subject"] or "")).lower()
        dup = next((k for k in kept if k["page"] == c["page"] and k["type"] == c["type"]
                    and normalize(str(k["subject"] or "")).lower() == subject
                    and similar(k["quote"], c["quote"]) >= MIN_DUPLICATE_SIMILARITY), None)
        if dup is None:
            kept.append(c)
        elif c["verified"] and not dup["verified"]:
            kept[kept.index(dup)] = c
    return kept


def to_claims(raw, page_no, page_text, model, source="page", stats=None):
    """Clean the model's claims: verify (or repair) quotes, drop junk, merge duplicates.

    stats (a dict, optional) gets counters added: repaired, dropped_value, dropped_duplicate.
    """
    stats = stats if stats is not None else {}
    claims = []
    for item in raw.get("claims", []) if isinstance(raw, dict) else []:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        ctype = item.get("type") if item.get("type") in CLAIM_TYPES else "statement"
        claim = {"page": page_no, "type": ctype, "subject": item.get("subject"),
                 "value": item.get("value"), "unit": item.get("unit"), "quote": quote,
                 "context": item.get("context"), "model": model, "source": source,
                 "verified": quote_on_page(quote, page_text), "quote_repaired": False}
        if not claim["verified"] and quote:
            exact, ratio = repair_quote(quote, page_text)
            if exact is not None:
                claim.update(quote=exact, model_quote=quote, verified=True, quote_repaired=True,
                             quote_similarity=round(ratio, 3))
        if not value_in_quote(claim["value"], claim["quote"]):
            stats["dropped_value"] = stats.get("dropped_value", 0) + 1
            continue
        claims.append(claim)

    kept = dedupe(claims)
    stats["dropped_duplicate"] = stats.get("dropped_duplicate", 0) + len(claims) - len(kept)
    stats["repaired"] = stats.get("repaired", 0) + sum(c["quote_repaired"] for c in kept)
    for i, c in enumerate(kept, 1):
        c["id"] = f"p{page_no}-{i:02d}"
    return [{"id": c.pop("id"), **c} for c in kept]


def extract_claims(pages, max_cost_usd=MAX_COST_USD, pdf_stem=None):
    """Extract claims from pdf_reader page dicts. Saves the ledger if pdf_stem is given.

    Stops before real spend in this run would pass max_cost_usd. Stats of the run
    (pages done/skipped, stop reason, cost, verified rate) are left in last_run.
    """
    start_cost = llm.session_cost_usd
    claims, done, skipped, stopped = [], [], [], None
    cleaning = {"repaired": 0, "dropped_value": 0, "dropped_duplicate": 0}
    for page in pages:
        if page.get("error") or not (page.get("text", "").strip() or page.get("image_path")):
            skipped.append(page["page"])
            continue
        spent = llm.session_cost_usd - start_cost
        if spent + estimate_page_cost(page) > max_cost_usd:
            stopped = (f"cost cap ${max_cost_usd:.2f} reached at page {page['page']} "
                       f"(spent ${spent:.4f})")
            log.warning(stopped)
            break
        model, messages, max_tokens = page_request(page)
        raw = chat_json(model, messages, max_tokens)
        if raw is None:
            log.warning("page %d skipped: no valid JSON", page["page"])
            skipped.append(page["page"])
            continue
        claims.extend(to_claims(raw, page["page"], page["text"], model, stats=cleaning))
        done.append(page["page"])

    last_run.clear()
    last_run.update(pages_done=done, pages_skipped=skipped, stopped=stopped, **cleaning,
                    cost_usd=llm.session_cost_usd - start_cost, **verified_stats(claims))
    if pdf_stem:
        save_ledger(pdf_stem, claims, done)
    return claims


def verified_stats(claims):
    checkable = [c for c in claims if c["verified"] is not None]
    ok = sum(1 for c in checkable if c["verified"])
    return {"claims": len(claims), "verified": ok,
            "verified_rate": ok / len(checkable) if checkable else None}


# ---------- ledger ----------

def ledger_path(pdf_stem):
    return LEDGER_DIR / pdf_stem / "claims.jsonl"


def load_ledger(pdf_stem):
    path = ledger_path(pdf_stem)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_ledger(pdf_stem, claims, pages_done):
    """Merge into the ledger: claims of re-run pages replace the old ones."""
    redone = set(pages_done)
    merged = [c for c in load_ledger(pdf_stem) if c["page"] not in redone] + claims
    merged.sort(key=lambda c: (c["page"] or 0, c["id"]))
    path = ledger_path(pdf_stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in merged:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return path


# ---------- standalone images (tables) ----------

def extract_table_from_image(path):
    """Super-VL transcribes the table in an image.

    Returns {"title", "columns", "rows": [{column: cell}], "scientific_name_column"},
    or None if no valid JSON came back.
    """
    messages = [{"role": "user", "content": [{"type": "text", "text": TABLE_PROMPT},
                                             llm.image_part(path)]}]
    raw = chat_json(llm.SUPER_VL, messages, VISION_MAX_TOKENS)
    if raw is None:
        return None
    columns = [str(c) for c in raw.get("columns") or []]
    rows = []
    for row in raw.get("rows") or []:
        if isinstance(row, dict):
            rows.append({str(k): str(v) for k, v in row.items()})
        elif isinstance(row, list):
            rows.append({col: str(cell) for col, cell in zip(columns, row)})
    return {"title": raw.get("title"), "columns": columns, "rows": rows,
            "scientific_name_column": raw.get("scientific_name_column")}


def name_column(table):
    """The column holding scientific names: the model's pick, else a header guess."""
    pick = table.get("scientific_name_column")
    if pick in table["columns"]:
        return pick
    for col in table["columns"]:
        if re.search(r"zoological|scientific|botanical|latin|species", col, re.IGNORECASE):
            return col
    return None


def species_claims_from_table(table, source):
    """One species claim per table row. verified=None: there is no text layer to check."""
    col = name_column(table)
    if col is None:
        return []
    claims = []
    for row in table["rows"]:
        name = normalize(row.get(col, ""))
        if not name or name == "-":
            continue
        claims.append({
            "id": f"img-{len(claims) + 1:02d}", "page": None, "type": "species",
            "subject": name, "value": name, "unit": None, "quote": name,
            "context": "; ".join(f"{k}: {v}" for k, v in row.items() if k != col and v),
            "model": llm.SUPER_VL, "source": str(source), "verified": None,
        })
    return claims
