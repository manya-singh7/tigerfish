"""Investigate agent: for one finding, ULTRA gathers more evidence with tools and writes a
short evidence memo. It never changes a grade; the reviewer decides.

Tools (plain Python, all cached):
  search_report(query)          top pages + snippets (BM25 over page texts)
  read_page(n)                  page text (truncated)
  check_species(name, lat, lon) our GBIF species check
  web_search(query, official_only)  Tavily search (counts toward the credit cap)
  read_url(url)                 Tavily extract (truncated for the model; full text kept)
  finish(...)                   ends the run with the memo

Loop: OpenAI-style tool calling when Token Factory supports it for ULTRA (supports_tools(),
one tiny cached probe call), otherwise a JSON action loop ({"tool", "args"}) with strict
parsing and one retry. Limits per investigation: MAX_STEPS model calls, MAX_COST_USD,
MAX_CREDITS Tavily credits; at the last step only finish() is offered.

The memo: what was checked, evidence, and a conclusion ("strengthens", "weakens" or
"inconclusive") with one-line reasons. Every report quote is verified against the page
text and every URL quote against the extracted text of a URL the agent read; unverified
quotes are dropped. Each step of the trace records a short reason, the tool, args, a result
summary, tokens, cost and time.
"""

import json
import math
import re
import time
from collections import Counter
from pathlib import Path

from tigerfish import claims as claims_mod
from tigerfish import copycheck, llm, species

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "investigations"
MODEL = llm.ULTRA
MAX_STEPS = 8
MAX_COST_USD = 0.10
MAX_CREDITS = 5
MAX_TOKENS = 1500              # per model reply (includes reasoning)
RETRY_MAX_TOKENS = 4000        # one retry when a reply is cut off at MAX_TOKENS (e.g. a long finish)
PAGE_CHARS = 3500              # page text the model sees per read_page
URL_CHARS = 3500               # URL text the model sees per read_url
SNIPPET_CHARS = 240
SEARCH_HITS = 5
CHARS_PER_TOKEN = 4
OFFICIAL_DOMAINS = ["gov.in", "nic.in", "qcin.org", "qci.org.in", "iucnredlist.org", "gbif.org"]
CONCLUSIONS = ("strengthens", "weakens", "inconclusive")

SYSTEM = """You are an evidence investigator for TigerFish, a neutral accuracy checker for \
Indian Environmental Impact Assessment (EIA) reports. You get one finding. Gather evidence \
that would STRENGTHEN or WEAKEN it, using the tools, then call finish.

Rules:
- You never change the finding's grade; a human reviewer decides.
- Look for both sides: an explanation in the report (different area, date, scope, a \
correction) weakens a finding; an independent source agreeing with it strengthens it.
- Quotes must be copied character for character: report quotes from a page you read with \
read_page, URL quotes from a URL you read with read_url. Anything else is discarded.
- Neutral wording only (e.g. "the two passages describe different areas"); never accuse \
anyone of intent.
- Every tool call needs a one-sentence "reason".
- You have at most {steps} steps; finish early when the evidence is clear. Web searches are \
limited, prefer the report first."""

JSON_ACTIONS = """
Tool calling is not available. Reply with ONE JSON object only, no other text:
{"reason": "...", "tool": "<name>", "args": {...}}
Tools and their args:
"""

RETRY_MSG = ("That was not a valid action. Reply with exactly one tool call "
             '(or, without tool calling, one JSON object {"reason", "tool", "args"}).')
FINISH_NOW = "Step or cost limit reached. Call finish now with the evidence you have."


def _tool(name, description, props, required):
    props = {"reason": {"type": "string", "description": "one sentence: why this step"}, **props}
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props, "required": ["reason", *required]}}}


TOOL_SPECS = [
    _tool("search_report", "Keyword search over every page of the report; returns the best pages "
          "with snippets.", {"query": {"type": "string"}}, ["query"]),
    _tool("read_page", "Read one page of the report (text, truncated).",
          {"n": {"type": "integer", "description": "page number"}}, ["n"]),
    _tool("check_species", "GBIF occurrence check of a species at a location: records nearby, "
          "regionally and worldwide.", {"name": {"type": "string"}, "lat": {"type": "number"},
                                        "lon": {"type": "number"}}, ["name", "lat", "lon"]),
    _tool("web_search", "Web search (Tavily). official_only=true restricts to government and "
          "official sources. Limited credits.",
          {"query": {"type": "string"}, "official_only": {"type": "boolean"}}, ["query"]),
    _tool("read_url", "Read a web page or PDF found by web_search (text, truncated).",
          {"url": {"type": "string"}}, ["url"]),
    {"type": "function", "function": {
        "name": "finish", "description": "End the investigation with the evidence memo.",
        "parameters": {"type": "object", "required": ["checked", "evidence", "conclusion", "reasons"],
                       "properties": {
                           "checked": {"type": "array", "items": {"type": "string"},
                                       "description": "what was checked, one line each"},
                           "evidence": {"type": "array", "items": {"type": "object", "properties": {
                               "page": {"type": "integer", "description": "report page (report quotes)"},
                               "url": {"type": "string", "description": "URL (web quotes)"},
                               "quote": {"type": "string", "description": "exact quote"},
                               "note": {"type": "string", "description": "what it shows, one line"}},
                               "required": ["quote", "note"]}},
                           "conclusion": {"type": "string", "enum": list(CONCLUSIONS)},
                           "reasons": {"type": "array", "items": {"type": "string"},
                                       "description": "one-line reasons for the conclusion"}}}}},
]
TOOL_NAMES = [t["function"]["name"] for t in TOOL_SPECS]
FINISH_ONLY = [t for t in TOOL_SPECS if t["function"]["name"] == "finish"]


class StopRun(Exception):
    pass


# ---------- context ----------

class Context:
    """What the tools can see: page texts, site, Tavily budget, texts read so far."""

    def __init__(self, pages, site=None, max_credits=MAX_CREDITS):
        self.pages = {p["page"]: p.get("text") or "" for p in pages}
        self.site = site
        self.budget = copycheck.Budget(max_credits)
        self.read_pages = set()
        self.sources = {}          # url -> full extracted text
        self.data = []             # results of our own checks (GBIF), attached to the memo as data
        self._index = None

    # BM25 over page texts, built on first search
    def index(self):
        if self._index is None:
            docs = {n: Counter(tokens(t)) for n, t in self.pages.items()}
            df = Counter(w for c in docs.values() for w in c)
            avg = sum(sum(c.values()) for c in docs.values()) / max(len(docs), 1)
            self._index = (docs, df, avg)
        return self._index


def tokens(text):
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", (text or "").lower())


def bm25(ctx, query, k1=1.5, b=0.75):
    docs, df, avg = ctx.index()
    terms = set(tokens(query))
    n = len(docs)
    scores = {}
    for page, c in docs.items():
        length = sum(c.values()) or 1
        s = 0.0
        for t in terms:
            if c[t]:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * c[t] * (k1 + 1) / (c[t] + k1 * (1 - b + b * length / avg))
        if s:
            scores[page] = s
    return sorted(scores.items(), key=lambda x: -x[1]), terms, df


def snippet(text, terms, df):
    """Text around the rarest query term found on the page."""
    t = claims_mod.normalize(text)
    low = t.lower()
    for term in sorted(terms, key=lambda w: df.get(w, 0)):
        i = low.find(term)
        if i >= 0:
            start = max(0, i - SNIPPET_CHARS // 2)
            return ("..." if start else "") + t[start:start + SNIPPET_CHARS] + "..."
    return t[:SNIPPET_CHARS]


# ---------- tools: each returns (result for the model, one-line summary) ----------

def search_report(ctx, query):
    ranked, terms, df = bm25(ctx, query)
    hits = [{"page": p, "score": round(s, 2), "snippet": snippet(ctx.pages[p], terms, df)}
            for p, s in ranked[:SEARCH_HITS]]
    summary = (f"{len(ranked)} pages matched; top: " + ", ".join(f"p.{h['page']}" for h in hits)
               if hits else "no pages matched")
    return {"hits": hits}, summary


def read_page(ctx, n):
    n = int(n)
    if n not in ctx.pages:
        return {"error": f"page {n} does not exist (pages 1-{max(ctx.pages, default=0)})"}, f"p.{n}: no such page"
    text = claims_mod.normalize(ctx.pages[n])
    ctx.read_pages.add(n)
    cut = len(text) > PAGE_CHARS
    return ({"page": n, "text": text[:PAGE_CHARS], "truncated": cut},
            f"read p.{n} ({len(text):,} chars{', truncated' if cut else ''})")


def check_species(ctx, name, lat, lon):
    r = species.check_species(str(name), float(lat), float(lon))
    keep = {k: r.get(k) for k in ("name", "matched_name", "name_note", "class_name", "grade",
                                  "local_count", "regional_count", "far_count", "archipelago_count",
                                  "global_count", "effort_count", "lookup_failed", "evidence")}
    keep["gbif_page"] = (r.get("gbif_links") or {}).get("species")
    ctx.data.append({"source": "GBIF (TigerFish species check)", "about": f"{name} at {lat}, {lon}",
                     "value": r.get("evidence") or f"grade {r['grade']}", "url": keep["gbif_page"]})
    return keep, (f"{r.get('matched_name') or name}: grade {r['grade']}, {r.get('local_count')} within "
                  f"{species.LOCAL_KM} km, {r.get('global_count')} worldwide")


def web_search(ctx, query, official_only=False):
    data = copycheck.search(str(query), ctx.budget, exact=False,
                            include_domains=OFFICIAL_DOMAINS if official_only else None)
    hits = [{"url": r["url"], "title": r.get("title"), "snippet": (r.get("content") or "")[:300]}
            for r in data.get("results", [])[:5]]
    return ({"results": hits, "note": "snippets are not quotable; read_url first"},
            f"{len(hits)} results{' (official only)' if official_only else ''}")


def read_url(ctx, url):
    url = str(url)
    text = copycheck.extract([url], ctx.budget, max_chars=None).get(url) or ""
    if not text:
        return {"error": "could not extract this URL"}, "extract failed"
    text = claims_mod.normalize(text)
    ctx.sources[url] = text
    cut = len(text) > URL_CHARS
    return ({"url": url, "text": text[:URL_CHARS], "truncated": cut},
            f"read {len(text):,} chars{', truncated' if cut else ''}")


TOOLS = {"search_report": search_report, "read_page": read_page, "check_species": check_species,
         "web_search": web_search, "read_url": read_url}


def dispatch(ctx, name, args):
    """Run one tool. Returns (result dict, summary). Errors become results, never crashes."""
    if name not in TOOLS:
        return {"error": f"unknown tool {name!r}; tools: {', '.join(TOOL_NAMES)}"}, f"unknown tool {name}"
    if not isinstance(args, dict):
        return {"error": "args must be an object"}, "bad args"
    spec = next(t["function"]["parameters"] for t in TOOL_SPECS if t["function"]["name"] == name)
    allowed = set(spec["properties"]) - {"reason"}
    clean = {k: v for k, v in args.items() if k in allowed}
    missing = [k for k in spec["required"] if k != "reason" and k not in clean]
    if missing:
        return {"error": f"missing args: {', '.join(missing)}"}, f"missing args {missing}"
    try:
        return TOOLS[name](ctx, **clean)
    except copycheck.CreditCapReached:
        return {"error": "web credit limit reached; use the report instead"}, "credit cap reached"
    except (ValueError, TypeError) as e:
        return {"error": f"bad arguments: {e}"}, "bad arguments"
    except Exception as e:                      # network etc.: report, don't crash the run
        return {"error": f"tool failed: {str(e)[:120]}"}, "tool failed"


# ---------- memo ----------

def verify_quote(quote, text):
    """The exact text of `quote` in `text` (normalised or repaired), or None."""
    if not quote or not text:
        return None
    if claims_mod.quote_on_page(quote, text):
        return claims_mod.normalize(quote)
    exact, _ = claims_mod.repair_quote(quote, text)
    return exact


def lines(value):
    """A list of one-line strings from a list, or from one string with bullets/newlines."""
    if isinstance(value, str):
        value = re.split(r"\n+|(?:^|\s)-\s(?=[A-Z])", value)
    if not isinstance(value, list):
        return []
    return [s for s in (re.sub(r"^\s*[-*•]\s*", "", str(v)).strip() for v in value) if s]


def build_memo(ctx, args, stopped=None):
    """Validate finish() arguments: keep only verified quotes, a known conclusion."""
    args = args if isinstance(args, dict) else {}
    kept, dropped = [], []
    for e in args.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        quote, url, page = str(e.get("quote") or ""), e.get("url"), e.get("page")
        exact, where = None, None
        if url:
            exact = verify_quote(quote, ctx.sources.get(url))
            where = {"url": url}
        else:
            try:
                page = int(page)
            except (TypeError, ValueError):
                page = None
            for p in [page] + sorted(ctx.read_pages - {page}):
                if p in ctx.pages and (exact := verify_quote(quote, ctx.pages[p])):
                    where = {"page": p}
                    break
        if exact:
            kept.append({**where, "quote": exact, "note": str(e.get("note") or "")})
        else:
            dropped.append({"page": page, "url": url, "quote": quote[:200]})
    conclusion = str(args.get("conclusion") or "").lower().strip()
    if conclusion not in CONCLUSIONS:
        conclusion = "inconclusive"
    reasons = lines(args.get("reasons"))
    if stopped and not reasons:
        reasons = [f"Stopped before a conclusion ({stopped})."]
    return {"conclusion": conclusion, "reasons": reasons, "checked": lines(args.get("checked")),
            "evidence": kept, "data": list(ctx.data), "dropped_quotes": dropped, "stopped": stopped}


# ---------- model calls ----------

PROBE_MESSAGES = [{"role": "user", "content": "Use the read_page tool to read page 3."}]
PROBE_TOOLS = [{"type": "function", "function": {
    "name": "read_page", "description": "Read one page of the report.",
    "parameters": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}}}]


def supports_tools(model=MODEL):
    """One tiny (cached) call: does Token Factory return OpenAI tool_calls for this model?"""
    try:
        r = llm.chat_message(model, PROBE_MESSAGES, tools=PROBE_TOOLS, tool_choice="auto", max_tokens=300)
    except Exception:
        return False
    return any(c["name"] == "read_page" for c in r["tool_calls"])


def estimate_cost(messages, model=MODEL, known=None):
    """Upper estimate of the next call: prompt tokens (the last reply's real prompt_tokens
    plus the text added since, when known) and a full MAX_TOKENS reply."""
    price_in, price_out = llm.PRICES.get(model, (0, 0))
    if known:
        tokens_so_far, n_messages = known
        tokens = tokens_so_far + len(json.dumps(messages[n_messages:], ensure_ascii=False)) / CHARS_PER_TOKEN
    else:
        tokens = len(json.dumps(messages, ensure_ascii=False)) / CHARS_PER_TOKEN
    return (tokens * price_in + MAX_TOKENS * price_out) / 1_000_000


def reply_cost(model, reply):
    u = reply["usage"]
    return llm.cost_usd(model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0)) or 0.0


def parse_action(text):
    """A JSON action {"tool", "args", "reason"} from reply text, or None (strict)."""
    try:
        a = claims_mod.parse_json(text)
    except Exception:
        return None
    if not isinstance(a, dict) or a.get("tool") not in TOOL_NAMES or not isinstance(a.get("args", {}), dict):
        return None
    return {"name": a["tool"], "args": {**a.get("args", {}), "reason": a.get("reason", "")}, "id": None}


def finding_brief(finding):
    keep = {k: finding.get(k) for k in ("id", "check_name", "grade", "title", "message", "quotes",
                                        "evidence", "why", "clear")}
    return json.dumps(keep, ensure_ascii=False, indent=1)


def tool_list_text():
    return "\n".join(f"- {t['function']['name']}: {t['function']['description']} args: "
                     f"{', '.join(k for k in t['function']['parameters']['properties'] if k != 'reason')}"
                     for t in TOOL_SPECS)


# ---------- the loop ----------

def investigate(finding, pages, site=None, report_name="", use_tools=None, max_steps=MAX_STEPS,
                max_cost=MAX_COST_USD, max_credits=MAX_CREDITS, model=MODEL):
    """Run the agent on one finding. Returns {memo, trace, totals, mode, ...}."""
    ctx = Context(pages, site, max_credits)
    use_tools = supports_tools(model) if use_tools is None else use_tools
    system = SYSTEM.format(steps=max_steps)
    if not use_tools:
        system += JSON_ACTIONS + tool_list_text()
    where = f" Project site: lat {site[0]}, lon {site[1]}." if site else ""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": f"Report: {report_name} ({len(ctx.pages)} pages).{where}\n"
                                            f"Finding to investigate:\n{finding_brief(finding)}"}]
    trace, spent, memo, retried, started = [], 0.0, None, False, time.perf_counter()
    stopped, known = None, None
    for step in range(1, max_steps + 1):
        est = estimate_cost(messages + [{"role": "user", "content": FINISH_NOW}], model, known)
        if spent + est > max_cost:              # not even a finish() call fits
            stopped = f"cost cap ${max_cost:.2f}"
            break
        last = step == max_steps or spent + 2 * est > max_cost
        if last:
            messages.append({"role": "user", "content": FINISH_NOW})
        kwargs = {"tools": FINISH_ONLY if last else TOOL_SPECS, "tool_choice": "auto"} if use_tools else {}
        replies = [llm.chat_message(model, messages, max_tokens=MAX_TOKENS, **kwargs)]
        retry_extra = (RETRY_MAX_TOKENS - MAX_TOKENS) * llm.PRICES.get(model, (0, 0))[1] / 1_000_000
        # Ultra reports a tool call cut off at max_tokens as "tool_calls", so check the count too
        cut_off = (replies[0]["finish_reason"] == "length"
                   or replies[0]["usage"].get("completion_tokens", 0) >= MAX_TOKENS)
        if cut_off and spent + reply_cost(model, replies[0]) + est + retry_extra <= max_cost:
            # cut off mid reply (often a long finish call): one retry with more room
            replies.append(llm.chat_message(model, messages, max_tokens=RETRY_MAX_TOKENS, **kwargs))
        reply = replies[-1]
        cost = sum(reply_cost(model, r) for r in replies)
        spent += cost
        # the next prompt = this prompt (real token count) + whatever is appended from here on
        known = (reply["usage"]["prompt_tokens"], len(messages)) if reply["usage"].get("prompt_tokens") else None
        row = {"step": step, "tokens_in": sum(r["usage"].get("prompt_tokens", 0) for r in replies),
               "tokens_out": sum(r["usage"].get("completion_tokens", 0) for r in replies),
               "cost_usd": round(cost, 6), "cached": all(r["cached"] for r in replies),
               "model_seconds": round(sum(r["seconds"] or 0 for r in replies), 3),
               "retried_cut_off": len(replies) > 1}
        calls = reply["tool_calls"] if use_tools else []
        if not calls:
            action = parse_action(reply["content"])
            if action is None:
                trace.append({**row, "reason": "", "tool": None, "args": {},
                              "result": "no valid tool call", "tool_seconds": 0})
                if retried:
                    stopped = "no valid action after one retry"
                    break
                retried = True
                messages += [{"role": "assistant", "content": reply["content"] or ""},
                             {"role": "user", "content": RETRY_MSG}]
                continue
            calls, json_mode = [action], True
        else:
            json_mode = False
            messages.append({"role": "assistant", "content": reply["content"] or "",
                             "tool_calls": [{"id": c["id"], "type": "function",
                                             "function": {"name": c["name"], "arguments": c["arguments"]}}
                                            for c in calls]})
        for i, c in enumerate(calls):
            args = c["args"] if json_mode else _loads(c["arguments"])
            reason = str((args or {}).get("reason") or "")[:300] if isinstance(args, dict) else ""
            t0 = time.perf_counter()
            if c["name"] == "finish":
                memo = build_memo(ctx, args)
                result, summary = {"ok": True}, (f"memo: {memo['conclusion']}, {len(memo['evidence'])} "
                                                 f"verified quote(s), {len(memo['dropped_quotes'])} dropped")
            else:
                result, summary = dispatch(ctx, c["name"], args)
            entry = {**row, "reason": reason, "tool": c["name"],
                     "args": {k: v for k, v in (args or {}).items() if k != "reason"} if c["name"] != "finish" else {},
                     "result": summary, "tool_seconds": round(time.perf_counter() - t0, 3)}
            if i:                                           # model cost is counted once per reply
                entry.update(tokens_in=0, tokens_out=0, cost_usd=0.0)
            trace.append(entry)
            content = json.dumps(result, ensure_ascii=False)
            if json_mode:
                messages += [{"role": "assistant", "content": reply["content"]},
                             {"role": "user", "content": f"Result of {c['name']}: {content}"}]
            else:
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": content})
        if memo:
            break
    else:
        stopped = stopped or f"step cap {max_steps}"
    if memo is None:
        memo = build_memo(ctx, {}, stopped=stopped or f"step cap {max_steps}")
    totals = {"steps": len({t["step"] for t in trace}), "tool_calls": sum(1 for t in trace if t["tool"]),
              "tokens_in": sum(t["tokens_in"] for t in trace), "tokens_out": sum(t["tokens_out"] for t in trace),
              "cost_usd": round(spent, 4), "tavily_credits": ctx.budget.used,
              "seconds": round(sum((t["model_seconds"] or 0) + t["tool_seconds"] for t in trace), 1),
              "wall_seconds": round(time.perf_counter() - started, 1)}
    return {"finding_id": finding.get("id"), "finding_title": finding.get("title"), "model": model,
            "mode": "tool calling" if use_tools else "JSON actions", "memo": memo, "trace": trace,
            "totals": totals, "limits": {"steps": max_steps, "cost_usd": max_cost, "tavily_credits": max_credits},
            "created": time.strftime("%Y-%m-%d %H:%M")}


def _loads(arguments):
    try:
        a = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError:
        return {}
    return a if isinstance(a, dict) else {}


# ---------- saved investigations ----------

def path_for(report_id, finding_id):
    return OUT_DIR / f"{report_id}__{finding_id}.json"


def save(report_id, result):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = path_for(report_id, result["finding_id"])
    p.write_text(json.dumps({"report_id": report_id, **result}, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def load(report_id, finding_id):
    p = path_for(report_id, finding_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
