"""The whole report as one Nemotron Ultra prompt: page text, quote checks, prices and a spend cap.

Shared by memo.py (reviewer's memo) and ask.py (questions about the report).

- report_text(): every in-scope page as "[p.N] <text>", in page order. Skipped, and said so:
  pages with no text layer (scans / photographs; Super-VL reads those elsewhere) and Hindi
  pages (the Hindi summary and Gazette notifications). The text is whitespace-collapsed, the
  same rule the quote check uses.
- messages(): ONE fixed system message (instructions + the report) then the task. The system
  message is byte-identical for every memo / ask call, so Token Factory's prompt cache serves
  it at the cached-input price after the first call.
- verify(): a quote counts only if it is on the cited page after whitespace / quote-mark /
  dash normalisation ("..." may join parts that appear in order). A quote found on another
  page is kept with the page corrected (and the correction recorded).
- Prices come from the Token Factory models API (GET /v1/models?verbose=true, Oct 27 2026):
  Ultra $1.00 / 1M input, $0.12 / 1M cached input, $3.00 / 1M output; 1,048,576-token context.
- Spend: every real Ultra call made through call() is appended to logs/ultra_spend.jsonl;
  a call whose worst-case estimate would pass SPEND_CAP_USD is refused before it is sent.
"""

import json
import re
import time
from pathlib import Path

import openai

from tigerfish import claims, llm

ROOT = Path(__file__).resolve().parent.parent
PDF_STEM = "great_nicobar_2021_draft_eia"
SPEND_LOG = ROOT / "logs" / "ultra_spend.jsonl"
SPEND_CAP_USD = 3.00

PRICE_IN, PRICE_CACHED, PRICE_OUT = 1.00, 0.12, 3.00     # USD per 1M tokens (Ultra)
CONTEXT_TOKENS = 1_048_576
CHARS_PER_TOKEN = 3.77          # measured on this report by the context test (results/ultra_context_test.json)
MIN_TEXT_CHARS = 50             # fewer non-space characters: no usable text layer
HINDI_SHARE = 0.2               # share of Devanagari letters that makes a page "Hindi"
LONG_TIMEOUT_S = 1800           # one long-context call may take many minutes
RATE_LIMIT_WAITS = (30, 60, 90, 120)   # waits before re-sending after HTTP 429 (not billed)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")

PREFIX = """You are a senior reviewer of Environmental Impact Assessment (EIA) reports in India.
Below is the full text of one EIA report. Each page starts with its page marker [p.N].
Rules for everything you write about it:
- Cite the page numbers you rely on, from the [p.N] markers.
- Quotes must be copied character for character from the page text, including typos.
  Keep each quote short (one sentence or phrase, at most 300 characters) and from ONE page.
- Neutral, factual wording: describe what the report states and what a reviewer should verify.
  Never accuse anyone; never speculate about intent.
- Use only this report. If the report does not say something, say so.

=== REPORT TEXT START ===
"""
SUFFIX = "\n=== REPORT TEXT END ==="


# ---------- pages ----------

def load_pages(cache_dir):
    """Page dicts from <cache_dir>/pages/<pdf>/pages.jsonl (written by pdf_reader.read_pdf)."""
    path = Path(cache_dir) / "pages" / PDF_STEM / "pages.jsonl"
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def skip_reason(text):
    """Why a page is left out of the prompt, or None to include it."""
    letters = "".join(text.split())
    if len(letters) < MIN_TEXT_CHARS:
        return "no text layer (scanned or photographed page)"
    if len(DEVANAGARI.findall(letters)) > HINDI_SHARE * len(letters):
        return "Hindi page"
    return None


def report_text(pages, max_chars=None):
    """{"text", "pages" (included page numbers), "skipped" {reason: [pages]}, "chars"}.

    max_chars stops adding pages once the text would pass it (the context test)."""
    parts, included, skipped, size = [], [], {}, 0
    for p in pages:
        reason = skip_reason(p.get("text") or "")
        if reason:
            skipped.setdefault(reason, []).append(p["page"])
            continue
        part = f"[p.{p['page']}] {claims.normalize(p['text'])}\n"
        if max_chars and size + len(part) > max_chars:
            break
        parts.append(part)
        included.append(p["page"])
        size += len(part)
    text = "".join(parts)
    return {"text": text, "pages": included, "skipped": skipped, "chars": len(text)}


def system_message(text):
    return {"role": "system", "content": PREFIX + text + SUFFIX}


def messages(text, task):
    """[fixed system message with the report, task]. The task is always last."""
    return [system_message(text), {"role": "user", "content": task}]


# ---------- quote checks ----------

QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                             "–": "-", "—": "-", " ": " ", "…": "..."})


def match_form(text):
    return claims.normalize(str(text or "").translate(QUOTE_CHARS))


def on_page(quote, page_text):
    """True if the quote is on the page (parts joined by '...' must appear in order)."""
    parts = [p.strip(" .") for p in match_form(quote).split("...")]
    parts = [p for p in parts if p]
    if not parts or sum(len(p) for p in parts) < 8:
        return False
    page, at = match_form(page_text), 0
    for part in parts:
        at = page.find(part, at)
        if at < 0:
            return False
        at += len(part)
    return True


MAX_PAGE_SHIFT = 3     # a quote found this many pages from the cited page is accepted, page corrected


STRING_CITE = re.compile(r'^\s*[\[(]?\s*p(?:age)?\.?\s*(\d+)\s*[\])]?\s*[:,\-]?\s*(.+)$', re.DOTALL)


def as_citation(c):
    """{"page", "quote"} from a dict, or from a string like '[p.12] quoted words'."""
    if isinstance(c, dict):
        return c
    m = STRING_CITE.match(str(c or ""))
    if m:
        return {"page": int(m.group(1)), "quote": m.group(2).strip().strip('"“”')}
    return {"page": None, "quote": str(c or "")}


def verify(citation, texts, max_shift=MAX_PAGE_SHIFT):
    """Citation {"page", "quote"} -> same dict + "verified" (bool).

    Verified: the quote is on the cited page, or on a page at most max_shift away (then "page"
    is corrected and "cited_page" kept; long-context models often cite a neighbouring page).
    A quote found only further away is NOT verified ("found_on" lists where it is)."""
    citation = as_citation(citation)
    quote = str(citation.get("quote") or "")
    try:
        page = int(str(citation.get("page")).strip().lstrip("p.").strip())
    except (TypeError, ValueError):
        page = None
    out = {"page": page, "quote": quote}
    if page in texts and on_page(quote, texts[page]):
        return {**out, "verified": True}
    found = [n for n, t in texts.items() if on_page(quote, t)]
    near = [n for n in found if page is not None and abs(n - page) <= max_shift]
    if near:
        return {**out, "page": min(near, key=lambda n: abs(n - page)), "cited_page": page,
                "verified": True}
    return {**out, "verified": False, **({"found_on": sorted(found)} if found else {})}


def page_texts(pages):
    return {p["page"]: p.get("text") or "" for p in pages}


# ---------- prices and the spend cap ----------

def cost(usage):
    """USD for one call, with cached input at the cached price. Returns (cost, detail)."""
    prompt = usage.get("prompt_tokens") or 0
    cached = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    out = usage.get("completion_tokens") or 0
    usd = ((prompt - cached) * PRICE_IN + cached * PRICE_CACHED + out * PRICE_OUT) / 1e6
    uncached_usd = (prompt * PRICE_IN + out * PRICE_OUT) / 1e6
    return round(usd, 6), {"prompt_tokens": prompt, "cached_tokens": cached,
                           "uncached_tokens": prompt - cached, "completion_tokens": out,
                           "cost_usd": round(usd, 6), "cost_if_uncached_usd": round(uncached_usd, 6),
                           "saving_usd": round(uncached_usd - usd, 6)}


def estimate_tokens(msgs):
    return int(sum(len(m["content"]) for m in msgs) / CHARS_PER_TOKEN)


def estimate(msgs, max_tokens, cached_share=0.0):
    """Estimated USD: (with the expected cache share, worst case with no cache hit)."""
    prompt = estimate_tokens(msgs)
    worst = (prompt * PRICE_IN + max_tokens * PRICE_OUT) / 1e6
    cached = int(prompt * cached_share)
    expected = ((prompt - cached) * PRICE_IN + cached * PRICE_CACHED + max_tokens * PRICE_OUT) / 1e6
    return {"prompt_tokens": prompt, "max_tokens": max_tokens,
            "expected_usd": round(expected, 4), "worst_usd": round(worst, 4)}


def spent():
    """USD of real Ultra calls logged so far (all processes)."""
    if not SPEND_LOG.exists():
        return 0.0
    with SPEND_LOG.open(encoding="utf-8") as f:
        return round(sum(json.loads(line)["cost_usd"] for line in f if line.strip()), 6)


class CapReached(RuntimeError):
    pass


def check_cap(est, cap=SPEND_CAP_USD):
    """Refuse a call whose worst case would take total spend past the cap."""
    if spent() + est["worst_usd"] > cap:
        raise CapReached(f"spend cap ${cap:.2f}: ${spent():.4f} spent, this call could cost up to "
                         f"${est['worst_usd']:.4f}")


def _record(label, detail, seconds):
    SPEND_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SPEND_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": label,
                            "seconds": seconds, **detail}) + "\n")


def call(msgs, max_tokens, label, thinking=None, cached_share=0.0, cap=SPEND_CAP_USD,
         log=print):
    """One Ultra call through llm.chat_message (cached locally like every call).

    Prints the estimate first and refuses it if the worst case would pass the cap. No retry on
    timeouts or 5xx (a long call may already be billed); HTTP 429 is re-sent after a wait.
    Returns llm.chat_message's dict plus "cost" (detail from cost()) and "estimate"."""
    est = estimate(msgs, max_tokens, cached_share)
    local = llm.is_cached(llm.ULTRA, msgs, thinking=thinking, max_tokens=max_tokens, temperature=0)
    log(f"[{label}] estimate: ~{est['prompt_tokens']:,} input tokens, up to {max_tokens:,} output; "
        f"~${est['expected_usd']:.4f} expected, ${est['worst_usd']:.4f} worst case"
        + (" (answered from the local cache: $0)" if local else f"; spent so far ${spent():.4f}"))
    if not local:
        check_cap(est, cap)
    # No retries and a long timeout for this call only (context-local: other app sessions and
    # threads keep their own settings and key).
    with llm.request_options(timeout=LONG_TIMEOUT_S, max_retries=0):
        for wait in (*RATE_LIMIT_WAITS, None):
            try:
                reply = llm.chat_message(llm.ULTRA, msgs, thinking=thinking, max_tokens=max_tokens,
                                         temperature=0)
                break
            except openai.RateLimitError:
                if wait is None:
                    raise
                log(f"[{label}] rate limited (HTTP 429, not billed); waiting {wait}s")
                time.sleep(wait)
    usd, detail = cost(reply["usage"])
    if not reply["cached"]:
        _record(label, detail, reply.get("seconds"))
    else:
        detail = {**detail, "replayed_from_local_cache": True}
    log(f"[{label}] {detail['prompt_tokens']:,} input ({detail['cached_tokens']:,} cached) + "
        f"{detail['completion_tokens']:,} output tokens: ${usd:.4f}"
        + (f" (${detail['saving_usd']:.4f} saved by the prompt cache)" if detail["cached_tokens"] else "")
        + (f", {reply['seconds']:.0f}s" if reply.get("seconds") else ""))
    return {**reply, "cost": detail, "estimate": est}


def parse_json(text):
    return claims.parse_json(text)
