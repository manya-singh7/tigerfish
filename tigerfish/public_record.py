"""Public record: what the official record says happened to the project, and what came after.

1. timeline    ONE Tavily Research call (model "mini") restricted to official sites, asking
               for a dated timeline of the project's clearance milestones with citations, in a
               structured output schema {date, event, source, quote}. Every event's quote is
               then checked against the Tavily-extracted text of its source; an event whose
               source is not an official site, or whose quote is not in the source text, is
               dropped.
2. next        "What happened next": one Tavily news search per verified finding topic
               (topic="news", start_date = the day after the report date). Shown as links for
               context; not checked against the report.
3. local news  Tavily search in Hindi / Tamil (language + filter_by_language) for local-language
               coverage of each project's public hearing. Shown as links.

All calls are cached in cache/tavily/ and counted against a credit cap. Research credits are
known only when the task finishes, so the research call needs RESEARCH_RESERVE credits free
before it starts.
"""

import json
import re
import time
from datetime import timedelta
from pathlib import Path

from tigerfish import claims as claims_mod
from tigerfish import copycheck, knowable
from tigerfish.official_record import _on, host, source_label

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

TIMELINE_DOMAINS = ["parivesh.nic.in", "environmentclearance.nic.in", "moef.gov.in", "pib.gov.in",
                    "greentribunal.gov.in", "sansad.in"]
RESEARCH_RESERVE = 110      # most a "mini" research task can cost (Tavily pricing page)
RESEARCH_POLL_S = 15
RESEARCH_TIMEOUT_S = 900
MAX_CREDITS = 150
NEWS_RESULTS = 5
LOCAL_RESULTS = 5

EVENT_SCHEMA = {
    "properties": {
        "events": {
            "type": "array",
            "description": "Clearance milestones of the project, oldest first.",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date of the event, YYYY-MM-DD (or YYYY-MM)."},
                    "event": {"type": "string", "description": "What happened, one sentence."},
                    "source": {"type": "string", "description": "URL of the official page or document stating it."},
                    "quote": {"type": "string", "description": "A short sentence copied verbatim from that source."},
                },
            },
        },
    },
    "required": ["events"],
}

PROJECTS = {
    "great_nicobar_2021_draft": {
        "name": "Great Nicobar Island holistic development project",
        "research": ("Dated timeline of the environmental and forest clearance milestones of the "
                     "'Holistic Development of Great Nicobar Island' project in Andaman and Nicobar "
                     "Islands (ANIIDCO; international container transshipment terminal, airport, "
                     "township and power plant): Terms of Reference, draft EIA, public hearing, "
                     "Expert Appraisal Committee meetings, Stage-I forest clearance, environmental "
                     "and CRZ clearance, National Green Tribunal orders, and questions in "
                     "Parliament. For each milestone give its date, a one-line description, the "
                     "official source URL and a short verbatim quote from that source. Use only "
                     "official Government of India sources."),
        "news_topics": {   # finding ids -> one news query (shared queries are searched once)
            "coral": (["ct-031", "ct-071"], "Great Nicobar Galathea Bay coral reefs"),
            "species": (["rf-009", "rf-010", "ct-403", "ct-979"],
                        "Great Nicobar project biodiversity species survey"),
            "rainfall": (["ct-239"], "Great Nicobar project EIA errors rainfall"),
            "lobster": (["sp-p954-001"], "Great Nicobar EIA species errors"),
            "consultant": (["ac-01"], "Great Nicobar EIA consultant Vimta Labs accreditation"),
            "baseline": (["pr-06"], "Great Nicobar EIA baseline survey season"),
        },
        "local": {"hi": "ग्रेट निकोबार परियोजना जन सुनवाई",
                  "ta": "கிரேட் நிக்கோபார் திட்டம் பொதுமக்கள் கருத்துக் கேட்பு"},
    },
    "indira_point_table_3_16": {
        "name": "Indira Point project, Great Nicobar",
        "research": None,
        "news_topics": {
            "species": (["sp-01", "sp-02", "sp-03", "sp-04", "sp-05", "st-06", "st-07"],
                        "Indira Point REIA mammals species list"),
        },
        "local": {"hi": "इंदिरा पॉइंट परियोजना जन सुनवाई"},
    },
}
LANGUAGE_NAMES = {"hi": "Hindi", "ta": "Tamil"}
# A link is kept only if its title or snippet names the project area (any script).
PROJECT_TERMS = ["nicobar", "galathea", "campbell bay", "indira point", "निकोबार", "நிக்கோபார்",
                 "நிகோபார்"]
SOCIAL = ["facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com", "linkedin.com"]


def relevant(item):
    """Names the project area and is not a social-media post."""
    text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
    return (any(t in text for t in PROJECT_TERMS)
            and not any(item["host"] == d or item["host"].endswith("." + d) for d in SOCIAL))


# ---------- Tavily research (cached) ----------

def research(query, budget, poll_s=RESEARCH_POLL_S, timeout_s=RESEARCH_TIMEOUT_S, sleep=time.sleep):
    """Cached Tavily research task. Returns (result dict, params actually sent).

    Tries include_domains + output_length first; if the API rejects them, retries with the
    domains named in the question only (recorded in "params_sent")."""
    attempts = [{"include_domains": TIMELINE_DOMAINS, "output_length": "short"}, {}]
    for extra in attempts:
        params = {"input": query, "model": "mini", "output_schema": EVENT_SCHEMA,
                  "citation_format": "numbered", **extra}
        path = copycheck._cache_path("research", params)
        if path.exists():
            budget.cached += 1
            return json.loads(path.read_text(encoding="utf-8"))["data"], params
        budget.check(RESEARCH_RESERVE)
        try:
            task = copycheck.client().research(**params)
        except Exception as e:   # noqa: BLE001 (unsupported parameter: try the next form)
            if extra:
                print(f"[public_record] research rejected {sorted(extra)}: {e}; retrying without")
                continue
            raise
        rid = task.get("request_id")
        waited, data = 0, task
        while data.get("status") not in ("completed", "failed") and waited < timeout_s:
            sleep(poll_s)
            waited += poll_s
            data = copycheck.client().get_research(rid, include_usage=True)
        credits = (data.get("usage") or {}).get("credits")
        budget.add(credits if isinstance(credits, (int, float)) else RESEARCH_RESERVE)
        if data.get("status") != "completed":
            raise RuntimeError(f"research task {rid} did not complete: {data.get('status')}")
        copycheck.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"endpoint": "research", "params": params, "data": data},
                                   ensure_ascii=False), encoding="utf-8")
        return data, params
    raise RuntimeError("research failed")


def events_of(data):
    """Events from the structured output (a dict, or a JSON string)."""
    content = data.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return []
    events = (content or {}).get("events") if isinstance(content, dict) else None
    return [e for e in events or [] if isinstance(e, dict)]


def is_timeline_source(url):
    """The research call is restricted to TIMELINE_DOMAINS; an event is also kept when its
    source is another government site (e.g. the A&N Pollution Control Committee), labelled so."""
    return _on(host(url), TIMELINE_DOMAINS) or source_label(url) in ("official source",
                                                                       "government website")


SNIPPET_DATE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}\s*[—-]\s*")   # "Nov 25, 2024 — "


def extract_texts(urls, budget, stats=None):
    """{url: plain text}; pages basic extraction cannot read are retried once with
    extract_depth="advanced" (dynamic pages, tables)."""
    texts = {}
    for depth in ("basic", "advanced"):
        todo = [u for u in urls if not texts.get(u)]
        for i in range(0, len(todo), 5):
            data = knowable.counted_call(stats if stats is not None else {}, "extract", budget,
                                         1 if depth == "basic" else 2, urls=todo[i:i + 5],
                                         extract_depth=depth)
            texts.update({r["url"]: knowable.plain_text(r.get("raw_content") or "")
                          for r in data.get("results", []) if r.get("raw_content")})
    return texts


def verify_events(events, budget, stats=None):
    """(kept, dropped). Kept: official / government source, quote found in its
    Tavily-extracted text (a leading search-snippet date like "Nov 25, 2024 — " is ignored)."""
    urls = sorted({e.get("source") for e in events
                   if isinstance(e.get("source"), str) and is_timeline_source(e["source"])})
    texts = extract_texts(urls, budget, stats)
    kept, dropped = [], []
    for e in events:
        url = str(e.get("source") or "")
        quote = SNIPPET_DATE.sub("", str(e.get("quote") or "").strip())
        if not is_timeline_source(url):
            dropped.append({**e, "why": "source is not an official or government site"})
            continue
        text = texts.get(url)
        if not text:
            dropped.append({**e, "why": "source text could not be extracted"})
            continue
        exact = knowable.verified_quote(quote, text)
        if not exact:
            dropped.append({**e, "why": "quote not found in the extracted source text"})
            continue
        kept.append({"date": str(e.get("date") or ""), "event": str(e.get("event") or ""),
                     "source": url, "host": host(url), "label": source_label(url), "quote": exact,
                     "quote_check": "exact text of the Tavily-extracted source"})
    kept.sort(key=lambda e: e["date"])
    return kept, dropped


# ---------- news ----------

def news_after(query, report_date, budget, stats=None):
    data = knowable.counted_call(
        stats if stats is not None else {}, "search", budget, 1, query=query, topic="news", search_depth="basic",
        max_results=NEWS_RESULTS, start_date=(report_date + timedelta(days=1)).isoformat())
    items = [{"title": r.get("title") or host(r["url"]), "url": r["url"], "host": host(r["url"]),
             "date": r.get("published_date"), "snippet": claims_mod.normalize(r.get("content"))[:300]}
            for r in data.get("results", [])]
    return [i for i in items if relevant(i)]


def local_news(query, language, budget, stats=None):
    data = knowable.counted_call(
        stats if stats is not None else {}, "search", budget, 1, query=query, search_depth="basic", max_results=LOCAL_RESULTS,
        language=language, filter_by_language=True)
    items = [{"title": r.get("title") or host(r["url"]), "url": r["url"], "host": host(r["url"]),
              "language": language, "snippet": claims_mod.normalize(r.get("content"))[:300]}
             for r in data.get("results", [])]
    return [i for i in items if relevant(i)]


# ---------- run ----------

def run(report_id, budget=None, verified_ids=None):
    """The public record for one report. verified_ids: finding ids that may get news (those in
    knowable.verified_findings); None means every id listed in news_topics."""
    project = PROJECTS[report_id]
    report_date = knowable.REPORT_DATES[report_id]
    budget = budget or copycheck.Budget(MAX_CREDITS)
    start, stopped = budget.used, None
    stats = {"credits": 0}
    out = {"report_id": report_id, "project": project["name"],
           "report_date": report_date.isoformat(), "timeline": [], "timeline_dropped": [],
           "research": None, "next": [], "local": []}
    try:
        if project["research"]:
            data, params = research(project["research"], budget)
            stats["credits"] += knowable.credits_of(data, RESEARCH_RESERVE)
            kept, dropped = verify_events(events_of(data), budget, stats)
            out.update(timeline=kept, timeline_dropped=dropped,
                       research={"params_sent": {k: v for k, v in params.items() if k != "output_schema"},
                                 "structured_output": True, "events_returned": len(kept) + len(dropped),
                                 "credits": (data.get("usage") or {}).get("credits"),
                                 "sources": [s.get("url") for s in data.get("sources") or []
                                             if isinstance(s, dict)]})
        for key, (ids, query) in project["news_topics"].items():
            ids = [i for i in ids if verified_ids is None or i in verified_ids]
            if ids:
                out["next"].append({"topic": key, "finding_ids": ids, "query": query,
                                    "items": news_after(query, report_date, budget, stats)})
        for lang, query in project["local"].items():
            out["local"].append({"language": lang, "language_name": LANGUAGE_NAMES[lang],
                                 "query": query, "items": local_news(query, lang, budget, stats)})
    except copycheck.CreditCapReached as e:
        stopped = str(e)
    out["stopped"] = stopped
    out["tavily"] = {"credits": stats["credits"], "credits_spent_this_run": budget.used - start, "cached_calls": budget.cached,
                     "features": ["research (structured output)", "extract", "news + start_date",
                                  "language + filter_by_language"]}
    return out


def path(report_id):
    return RESULTS / f"public_record_{report_id}.json"


def load(report_id):
    p = path(report_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
