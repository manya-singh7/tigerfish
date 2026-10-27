"""Ask the report: one question about the whole report, answered by Nemotron Ultra with page
citations and quotes, every quote checked against the page text.

The prompt is fulltext.messages(report_text, task): the system message (instructions + the full
report) is byte-identical for every question and for the memo, and the question comes last,
so Token Factory serves the long prefix at the cached-input price after the first call. Each
answer records cached vs uncached input tokens and its cost.

No verified quote -> the answer is "The report does not say." (the model's own text is kept,
labelled unverified, for transparency).
"""

import re
import time

from tigerfish import fulltext, llm

DOES_NOT_SAY = "The report does not say."
MAX_TOKENS = 8_000            # reasoning + a short JSON answer
LONG_MAX_TOKENS = 24_000      # re-ask with this when reasoning used up MAX_TOKENS (cut off)
RETRY_MSG = ("Your reply was cut off or was not valid JSON. Send the complete JSON again: your "
             "answer to the question, and 1 to 4 citations, each the page number from the [p.N] "
             "marker and a quote copied exactly from that page.")
SESSION_LIMIT = 3             # live questions per app session
MAX_QUESTION_CHARS = 400

TASK = """Question about this report: {question}

Answer from the report only. Return JSON only:
{{"answer": "2-5 neutral sentences answering the question",
  "citations": [{{"page": 123, "quote": "exact words from p.123"}}],
  "report_says": true}}
Give 1 to 4 citations that support the answer. If the report does not address the question,
return {{"answer": "The report does not say.", "citations": [], "report_says": false}}."""


def task(question):
    q = " ".join(str(question or "").split())[:MAX_QUESTION_CHARS]
    if not q:
        raise ValueError("empty question")
    return TASK.format(question=q)


def request(report_text, question):
    """The exact messages sent for a question: identical prefix, question last."""
    return fulltext.messages(report_text, task(question))


def check(raw, texts):
    """Verified answer dict from the model's JSON."""
    cites = [fulltext.verify(c, texts) for c in (raw.get("citations") or [])]
    ok = [c for c in cites if c["verified"]]
    model_answer = str(raw.get("answer") or "").strip()
    says = bool(raw.get("report_says", True)) and bool(ok)
    out = {"answer": model_answer if says else DOES_NOT_SAY, "report_says": says,
           "citations": ok if says else [], "unverified_citations": [c for c in cites if not c["verified"]]}
    if not says and model_answer and model_answer != DOES_NOT_SAY:
        out["model_answer_unverified"] = model_answer
    return out


def ask(question, pages, report=None, log=print, cap=fulltext.SPEND_CAP_USD):
    """Answer one question. report: a prebuilt fulltext.report_text(pages) (reuse it)."""
    report = report or fulltext.report_text(pages)
    msgs = request(report["text"], question)
    started = time.time()
    reply = fulltext.call(msgs, MAX_TOKENS, "ask", cached_share=1.0, log=log, cap=cap)
    costs, seconds = [reply["cost"]], [reply.get("seconds") or 0]
    if reply.get("finish_reason") == "length":     # reasoning used the whole budget: no answer yet
        log(f"[ask] reply cut off at {MAX_TOKENS:,} tokens; asking again with {LONG_MAX_TOKENS:,}")
        reply = fulltext.call(msgs, LONG_MAX_TOKENS, "ask (long)", cached_share=1.0, log=log, cap=cap)
        costs.append(reply["cost"])
        seconds.append(reply.get("seconds") or 0)
    texts = fulltext.page_texts(pages)
    raw = parse(reply["content"])
    if raw is None or (raw.get("salvaged") and not check(raw, texts)["report_says"]):
        # Not valid JSON and nothing verifiable in it: ask once more (same prefix, cached).
        log("[ask] reply was not valid JSON with a verifiable quote; asking once more")
        retry = msgs + [{"role": "assistant", "content": reply["content"]},
                        {"role": "user", "content": RETRY_MSG}]
        again = fulltext.call(retry, MAX_TOKENS, "ask (json retry)", cached_share=1.0, log=log, cap=cap)
        costs.append(again["cost"])
        seconds.append(again.get("seconds") or 0)
        raw = parse(again["content"]) or raw
    raw = raw or {"answer": "", "citations": [], "report_says": False}
    return {"question": " ".join(question.split()), **check(raw, fulltext.page_texts(pages)),
            "salvaged_from_invalid_json": bool(raw.get("salvaged")),
            "model": llm.ULTRA, "cost": add_costs(costs), "calls": len(costs),
            "finish_reason": reply.get("finish_reason"),
            "latency_s": round(sum(seconds) or time.time() - started, 1)}


# Prose: a quoted passage ("..." or “...”) followed, within the same sentence, by [p.N] / (p.N).
CITED_QUOTE = re.compile(r'["“]([^"“”]{8,})["”][^"“\[(]{0,200}?'
                         r'[\[(]\s*p(?:age)?\.?\s*(\d+)\s*[\])]')
JSON_CITE = re.compile(r'"page"\s*:\s*"?p?\.?(\d+)"?\s*,\s*"quote"\s*:\s*"((?:[^"\\]|\\.)*)"')
JSON_ANSWER = re.compile(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"')


def salvage(text):
    """Answer and citations from a reply that is not valid JSON (cut off, or prose with
    "quote" [p.N]). Quotes are verified afterwards like any other."""
    text = text or ""
    cites = [{"page": int(p), "quote": q} for p, q in JSON_CITE.findall(text)]
    cites += [{"page": int(p), "quote": q} for q, p in CITED_QUOTE.findall(text)]
    m = JSON_ANSWER.search(text)
    answer = m.group(1) if m else " ".join(text.split())
    if not cites and not m:
        return None
    return {"answer": answer.replace('\\"', '"'), "citations": cites, "report_says": bool(cites),
            "salvaged": True}


def parse(text):
    """The model's JSON, else what salvage() recovers from prose / cut-off JSON, else None."""
    try:
        return fulltext.parse_json(text)
    except ValueError:
        return salvage(text)


def add_costs(costs):
    """One cost detail for a question answered in one or more calls."""
    keys = ("prompt_tokens", "cached_tokens", "uncached_tokens", "completion_tokens", "cost_usd",
            "cost_if_uncached_usd", "saving_usd")
    return {k: round(sum(c.get(k, 0) for c in costs), 6) for k in keys}


def estimate(question, report):
    """Cost estimate shown before sending. expected: warm prompt cache, one call; worst: no cache
    hit and a cut-off first reply re-asked with LONG_MAX_TOKENS."""
    msgs = request(report["text"], question)
    first = fulltext.estimate(msgs, MAX_TOKENS, cached_share=1.0)
    long = fulltext.estimate(msgs, LONG_MAX_TOKENS, cached_share=1.0)
    return {**first, "worst_usd": round(first["worst_usd"] + long["worst_usd"], 4)}


def totals(answers):
    """Cached vs uncached input tokens and cost over recorded answers."""
    keys = ("prompt_tokens", "cached_tokens", "uncached_tokens", "completion_tokens", "cost_usd",
            "cost_if_uncached_usd", "saving_usd")
    t = {k: round(sum(a["cost"].get(k, 0) for a in answers), 6) for k in keys}
    t["cached_share"] = round(t["cached_tokens"] / t["prompt_tokens"], 4) if t["prompt_tokens"] else 0
    return t
