"""Export saved results for the app's replay mode into results/ (committed, unlike cache/).

Usage: python scripts/export_results.py

Runs each report's pipeline from cache (no new API calls are expected; any that are
needed stay under the usual caps) and writes:
  results/index.json                      list of reports
  results/<report>.json                   summary + findings in one shape for the UI
  results/pages/<report>_p<NNNN>.png      only pages that have findings, quotes highlighted
  (results/<report>_promises.json, the ToR table + timeline, is written by check_promises.py)
No PDFs, no source images (the Scroll table image stays local), no API keys.
"""

import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_contradictions  # noqa: E402
import check_copypaste  # noqa: E402
import demo_table  # noqa: E402
from tigerfish import claims, copycheck, llm, pdf_reader, promises, scope, status, trace  # noqa: E402
from tigerfish import contradictions as ct  # noqa: E402
from tigerfish.report import (GRADE_ORDER, attach_images, contradiction_findings,  # noqa: E402
                              finding, highlight_pages, sort_findings)

RESULTS = ROOT / "results"
PAGES_OUT = RESULTS / "pages"
PAGE_DPI = 110
MAX_GAP_S = 300          # cache files written further apart than this were separate runs

GN_PDF = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"
GN_PAGES = [234, 392, 444, 751, 818, 851, 940, 978, 1141, 1168]
TABLE_IMAGE = ROOT / "data" / "demo" / "indira_point_table_3_16_mammals.png"
INDIRA_POINT = (6.75, 93.83)
# Full audit (scripts/audit.py without --pages). Its contradiction findings are kept under
# full_run/ because the 10-page evaluation rewrites contradictions.jsonl in the same folder.
FULL_RUN = RESULTS / f"audit_{GN_PDF.stem}.json"
FULL_FINDINGS = ROOT / "cache" / "findings" / GN_PDF.stem / "full_run" / "contradictions.jsonl"

# ---------- cost and time from the cache files a run used ----------

def gaps_by_dir():
    """For every cache file: seconds since the previous file in its folder was written."""
    out = {}
    for kind in ("llm", "tavily", "gbif"):
        files = sorted((ROOT / "cache" / kind).glob("*.json"), key=lambda p: p.stat().st_mtime)
        times = [p.stat().st_mtime for p in files]
        gaps = [b - a for a, b in zip(times, times[1:]) if 0 < b - a <= MAX_GAP_S]
        typical = statistics.median(gaps) if gaps else 1.0
        for i, p in enumerate(files):
            g = times[i] - times[i - 1] if i else MAX_GAP_S + 1
            out[p] = g if 0 < g <= MAX_GAP_S else typical
    return out


def run_cost(used):
    """(llm_usd, tavily_credits, gbif_calls, approx_seconds) for the cache files used."""
    gaps = gaps_by_dir()
    usd, credits, gbif, seconds = 0.0, 0, 0, 0.0
    for kind, path in dict.fromkeys(used):            # unique, in order
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        seconds += gaps.get(path, 0)
        if kind == "llm":
            u = data.get("usage") or {}
            usd += llm.cost_usd(data.get("model"), u.get("prompt_tokens", 0),
                                u.get("completion_tokens", 0)) or 0
        elif kind == "tavily":
            c = (data["data"].get("usage") or {}).get("credits")
            est = 1 if data["endpoint"] == "search" else math.ceil(len(data["params"]["urls"]) / 5)
            credits += c if isinstance(c, (int, float)) else est
        else:
            gbif += 1
    return round(usd, 4), credits, gbif, round(seconds)


# ---------- findings in one shape ----------

def display_snippet(text):
    """Snippet for display: markdown markup removed, cut to whole words, with ellipses."""
    words = status.visible_text(text).split(" ")
    if len(words) > 2:
        words = words[1:-1]           # first and last words may be cut mid-word
    return "..." + " ".join(words) + "..."


SPECIES_PAGES = ROOT / "cache" / "findings" / GN_PDF.stem / "species_pages.json"
# Plants: GBIF has few digitised plant records for Great Nicobar but many within 500 km
# (Sumatra, Andamans), so the "region surveyed, species absent" rule flags most plant names
# (206 of 334 in the first run). Those stay in species_pages.json but are not app findings.
EXPORT_PLANT_FLAGS = False
PLANT_CLASSES = {"Magnoliopsida", "Liliopsida", "Polypodiopsida", "Cycadopsida", "Pinopsida",
                 "Gnetopsida", "Lycopodiopsida", "Bryopsida"}


def species_table_findings(report_id):
    """RED/ORANGE results of scripts/check_species_pages.py as findings (one shared,
    highlighted image per page, so many flagged names don't mean many images)."""
    if not SPECIES_PAGES.exists():
        return []
    rows = [r for r in json.loads(SPECIES_PAGES.read_text(encoding="utf-8"))["rows"]
            if r["grade"] in ("RED", "ORANGE")
            and (EXPORT_PLANT_FLAGS or r["class"] not in PLANT_CLASSES)]
    out = []
    for i, r in enumerate(rows, 1):
        ev = [{"label": "Checked at", "value": f"{r['location']} ({r['lat']}, {r['lon']}): {r['reason']}"},
              {"label": "GBIF records of this species",
               "value": f"{fmt_count(r['local'])} within 100 km, {fmt_count(r['regional'])} within "
                        f"500 km, {fmt_count(r['global'])} worldwide"},
              {"label": "GBIF species page", "value": r["gbif_name"],
               "url": (r.get("links") or {}).get("species")}]
        if r.get("name_note"):
            ev.insert(0, {"label": "Name", "value": r["name_note"]})
        out.append(finding(f"sp-p{r['page']}-{i:03d}", "species_range", r["grade"],
                           f"{r['name']} at {r['location']} (p.{r['page']})", r["evidence"],
                           [{"page": r["page"], "text": r["name"]}], ev, r["evidence"]))
    by_page = {}
    for f in out:
        by_page.setdefault(f["quotes"][0]["page"], []).append(f["quotes"][0]["text"])
    images = highlight_pages(GN_PDF, by_page, PAGES_OUT, f"{report_id}_species", dpi=PAGE_DPI)
    attach_images(out, images, relative_to=RESULTS)
    return out


OMISSIONS = ROOT / "cache" / "findings" / GN_PDF.stem / "omissions.json"


def omission_findings():
    """RED/ORANGE/INFO results of scripts/check_omissions.py as findings."""
    if not OMISSIONS.exists():
        return []
    data = json.loads(OMISSIONS.read_text(encoding="utf-8"))
    n_pages, n_empty = data["pages_searched"], len(data["pages_without_text"])
    out = []
    for i, r in enumerate([r for r in data["rows"] if r["grade"]], 1):
        latest = r["latest_year"] or "unknown"
        names = [s.split(": ", 1)[1] for s in r["searched_for"]]
        ev = [{"label": "GBIF records (IUCN " + r["category"] + ")",
               "value": f"{r['near']} within 10 km ({r['near_since_2000']} since 2000), "
                        f"{r['wide']} within 25 km; latest {latest}"},
              {"label": "Names searched for", "value": ", ".join(dict.fromkeys(names))},
              {"label": "Pages searched", "value": f"{n_pages - n_empty} of {n_pages} with usable "
                                                   f"text ({n_empty} scanned pages not searched)"},
              {"label": "GBIF map of these records", "value": r["name"], "url": r["map"]}]
        out.append(finding(f"om-{i:02d}", "omission", r["grade"],
                           f"{r['name']} (IUCN {r['category']}) not mentioned", r["message"],
                           [{"page": None, "where": "GBIF, near the site",
                             "text": f"{r['name']}: {r['wide']} record(s) within 25 km of Galathea Bay, "
                                     f"latest {latest}"}],
                           ev, f"GBIF has {r['wide']} record(s) of this IUCN {r['category']} species "
                               f"within 25 km of the site; no page of the report names it."))
    return out


ACCREDITATION = ROOT / "cache" / "findings" / GN_PDF.stem / "accreditation.json"


def accreditation_findings():
    """The accreditation check as one finding (any grade except GREY)."""
    if not ACCREDITATION.exists():
        return []
    a = json.loads(ACCREDITATION.read_text(encoding="utf-8"))
    if a["grade"] in ("GREY", "NONE") or not a.get("entry"):
        return []
    d, e = a["details"], a["entry"]
    quotes = [{"page": d[f]["page"], "text": d[f]["quote"]}
              for f in ("certificate_number", "project_category", "report_date")
              if d.get(f) and d[f]["verified"]]
    compact = next((s["quote"] for s in e["sectors"] if not s.get("schedule")), None)
    ev = [{"label": f"Closest {e.get('label', 'official source')} to the report date: "
                    f"{e.get('kind', 'accredited list')}, {e['revision'] or 'undated'}",
           "value": "; ".join(f"sector {r['sector']['number']} {r['sector']['name']}: "
                              f"Category {r['sector']['category']}" for r in a["rows"] if r["sector"])
                    + (f'. Source text: "{compact}"' if compact else ""),
           "url": e["url"]}]
    ev += [{"label": f"Also found: {r['kind']}, {r['revision']}",
            "value": "; ".join(f"sector {s['number']}: Category {s['category']}" for s in r["sectors"]
                               if s["number"] in {x["sector"]["number"] for x in a["rows"] if x["sector"]}),
            "url": r["url"]} for r in a.get("records", []) if r["url"] != e["url"]]
    ev += [{"label": "Project category (report)", "value": d["project_category"]["value"]
            if d.get("project_category") else "not stated"},
           {"label": "Validity", "value": a["validity"]}]
    not_covered = [r for r in a["rows"] if not r["covered"]]
    why = "; ".join(f"{r['component']}: {r['why']}" for r in not_covered)
    return [finding("ac-01", "accreditation", a["grade"],
                    f"{d['consultant_name']['value']}: accreditation scope", " ".join(a["messages"]),
                    quotes, ev, why or a["validity"])]


PROMISES = ROOT / "cache" / "findings" / GN_PDF.stem / "promises.json"


def promise_findings(report_id):
    """ORANGE/INFO results of scripts/check_promises.py (ToR vs EIA) as findings, check "promise".
    Quotes: the ToR sentence (trimmed around the number), the report's text, and any other
    report page that says otherwise. Report pages get highlighted images."""
    if not PROMISES.exists():
        return []
    data = json.loads(PROMISES.read_text(encoding="utf-8"))
    out = []
    for p in [p for p in data["promises"] if p["grade"] in ("ORANGE", "INFO")]:
        quotes = [{"page": None, "where": f"Terms of Reference p.{p['page']}",
                   "text": promises.quote_around(p["quote"], p["measure"])}]
        if p.get("eia_quote"):
            quotes.append({"page": p["eia_page"], "text": p["eia_quote"]})
        if p.get("supporting_quote"):
            quotes.append({"page": p["supporting_page"], "text": p["supporting_quote"]})
        by = ("Nemotron Ultra, reading the cited report pages" if p["verdict_by"] == "ultra"
              else "Nemotron Lightning (first pass only; not confirmed by Ultra)"
              if p["verdict_by"] == "lightning" else "regex only")
        ev = [{"label": f"ToR commitment (p.{p['page']})", "value": f"{p['commitment']} ({p['measure']})"},
              {"label": "Report describes" + (f" (p.{p['eia_page']})" if p.get("eia_page") else ""),
               "value": p["report_describes"]},
              {"label": "Verdict", "value": f"{p['verdict']}, checked by {by}"}]
        if p.get("supporting_quote"):
            ev.append({"label": f"Also in the report (p.{p['supporting_page']})", "value": p["supporting_quote"]})
        if p.get("eia_page"):
            ev.append({"label": "Report page", "value": f"EIA p.{p['eia_page']}",
                       "url": f"{promises.EIA_URL}#page={p['eia_page']}"})
        out.append(finding(f"pr-{p['id'][1:]}", "promise", p["grade"],
                           f"{p['topic'].capitalize()}: {p['measure']} in the Terms of Reference",
                           p["message"], quotes, ev, p.get("reason") or p["message"]))
    for f in out:
        by_page = {}
        for q in f["quotes"]:
            if q.get("page"):
                by_page.setdefault(q["page"], []).append(q["text"])
        images = highlight_pages(GN_PDF, by_page, PAGES_OUT, f"{report_id}_{f['id']}", dpi=PAGE_DPI)
        attach_images([f], images, relative_to=RESULTS)
    return out


def species_pages_read():
    """Pages the species-table check read (empty set if it has not been run)."""
    if not SPECIES_PAGES.exists():
        return set()
    data = json.loads(SPECIES_PAGES.read_text(encoding="utf-8"))
    return set(data["table_pages"]) | set(data["vision_pages"])


def fmt_count(n):
    return "-" if n is None else f"{n:,}"


def copy_findings(results):
    """Copied-text (one per passage) and borrowed-text findings from copycheck results."""
    out = []
    for r in results:
        grade, hits = copycheck.flagged_hits(r)
        if grade:
            h = hits[0]
            evidence = [{"label": "Matching document" + (f" {i}" if len(hits) > 1 else ""),
                         "value": x["title"] or x["url"], "url": x["url"]}
                        for i, x in enumerate(hits, 1)]
            evidence += [{"label": "Matching text", "value": h["snippet"]},
                         {"label": "Overlap", "value": f"longest run {h['longest_run']} words, "
                                                       f"8-gram overlap {h['ngram']:.0%}"}]
            out.append(finding(
                f"cp-p{r['page']}-{len(out)}", "copy_paste", grade,
                f"Page {r['page']} text found in "
                + ("another document" if len(hits) == 1 else f"{len(hits)} other documents"),
                h["message"], [{"page": r["page"], "text": r["passage"]}], evidence, h["why"]))
        for b in r["borrowed"]:
            out.append(finding(
                f"bt-p{b['page']}-{len(out)}", "borrowed_text", "INFO",
                f"Page {b['page']} uses uncited text from {b['url'].split('/')[2]}", b["message"],
                [{"page": b["page"], "text": b["quote"]}],
                [{"label": "Source", "value": b["title"] or b["url"], "url": b["url"]},
                 {"label": "Verbatim run", "value": f"{b['longest_run']} words"},
                 {"label": "Source text", "value": display_snippet(b["source_snippet"])}],
                f"{b['longest_run']} consecutive words match a generic external source, and "
                f"page {b['page']} does not cite it."))
    return out


def same_finding(a, b):
    """Same check, same pages, and every quote of a matches a quote of b on the same page."""
    if a["check"] != b["check"]:
        return False
    if {q.get("page") for q in a["quotes"]} != {q.get("page") for q in b["quotes"]}:
        return False
    return all(any(q.get("page") == r.get("page") and ct.quotes_match(q["text"], r["text"])
                   for r in b["quotes"]) for q in a["quotes"])


def dedupe(findings):
    """RED/ORANGE/INFO only, duplicates removed (the higher grade is kept), sorted by
    grade then check."""
    out = []
    for f in sort_findings([f for f in findings if f["grade"] in GRADE_ORDER]):
        if not any(same_finding(f, g) for g in out):
            out.append(f)
    return sort_findings(out)


def page_images(prefix, findings, shared):
    """Highlighted page images. shared=False: one image set per finding (only its quotes
    highlighted). shared=True (full run, many findings): one image per page with every
    finding's quotes on it, so the image count is bounded by the pages."""
    if shared:
        by_page = {}
        for f in findings:
            for q in f["quotes"]:
                if q.get("page"):
                    by_page.setdefault(q["page"], []).append(q["text"])
        images = highlight_pages(GN_PDF, by_page, PAGES_OUT, prefix, dpi=PAGE_DPI)
        attach_images(findings, images, relative_to=RESULTS)
        return
    for f in findings:
        quotes_by_page = {}
        for q in f["quotes"]:
            quotes_by_page.setdefault(q["page"], []).append(q["text"])
        images = highlight_pages(GN_PDF, quotes_by_page, PAGES_OUT, f"{prefix}_{f['id']}",
                                 dpi=PAGE_DPI)
        attach_images([f], images, relative_to=RESULTS)


SKIP_LABELS = {"hindi": "Hindi", "lab_report": "lab sheets", "annexure": "forms",
               "error": "unreadable"}


def full_run_core():
    """Contradiction and copy-paste findings of the full audit (scripts/audit.py without
    --pages), rebuilt from cache. (findings, known-issue rows, extras) or None."""
    if not (FULL_RUN.exists() and FULL_FINDINGS.exists()):
        return None
    run = json.loads(FULL_RUN.read_text(encoding="utf-8"))
    kept, skipped = scope.select_pages(pdf_reader.read_pdf(GN_PDF))
    texts = {p["page"]: p["text"] for p in kept}
    con = [json.loads(line) for line in FULL_FINDINGS.read_text(encoding="utf-8").splitlines()
           if line.strip()]
    rows = ct.evaluate(con, check_contradictions.known_issues_for(GN_PDF))
    known = {r["finding_id"]: r["id"] for r in rows if r["finding_id"]}
    ledger = [c for c in claims.load_ledger(GN_PDF.stem) if c["page"] in texts]
    budget = copycheck.Budget(max(run["tavily"]["credits"], 1))  # cached: no new credits
    passages = copycheck.select_passages(ledger, texts, max_passages=run["copy_passages"])
    copy, stopped = copycheck.check_passages(passages, budget, pages=texts)
    if stopped:
        print(f"WARNING copy-paste export stopped: {stopped}")
    findings = contradiction_findings(con, known) + copy_findings(copy)
    return findings, rows, {"run": run, "kept": {p["page"] for p in kept}, "skipped": skipped}


def great_nicobar():
    report_id = "great_nicobar_2021_draft"
    trace.reset()
    started = time.time()
    for old in PAGES_OUT.glob(f"{report_id}_*.png"):
        old.unlink()
    full = full_run_core()
    if full:
        findings, rows, extra = full
        pages = extra["kept"]
    else:                     # no full run yet: the 10 known-issue pages
        pages = set(GN_PAGES)
        page_dicts = [p for p in pdf_reader.read_pdf(GN_PDF) if p["page"] in pages]
        claims.extract_claims(page_dicts)                  # from cache: counts extraction cost
        con = check_contradictions.run(GN_PDF, pages)
        cp = check_copypaste.run(GN_PDF, pages)
        rows = con["evaluation"]
        known = {r["finding_id"]: r["id"] for r in rows if r["finding_id"]}
        findings = contradiction_findings(con["findings"], known) + copy_findings(cp["results"])
        page_images(report_id, findings, shared=False)

    findings += species_table_findings(report_id)
    findings += omission_findings()
    findings += accreditation_findings()
    findings += promise_findings(report_id)
    findings = dedupe(findings)
    if full:   # species/ToR images are made above; the rest share one image per page
        page_images(f"{report_id}_full", [f for f in findings if not f["images"]], shared=True)

    usd, credits, gbif, seconds = run_cost(trace.used)
    promises_usd = (json.loads(PROMISES.read_text(encoding="utf-8")).get("cost_usd", 0)
                    if PROMISES.exists() else 0)   # its calls ran in scripts/check_promises.py
    pages_read = pages | species_pages_read()
    out = {
        "id": report_id, "title": "Great Nicobar EIA (2021 draft)",
        "source": "Draft EIA by Vimta Labs for ANIIDCO, December 2021",
        "pages_read": len(pages_read), "pages_total": 1213,
        "checks": ["Claim extraction (Nemotron Lightning / Super-VL)",
                   "Internal contradictions and recycled figures (Nemotron Ultra)",
                   "Copied text (Tavily)", "Borrowed text (Tavily)",
                   "Species tables in the report (GBIF)",
                   "Threatened species not mentioned (GBIF)",
                   "Consultant accreditation (NABET, official list)",
                   "Terms of Reference promises (Nemotron Lightning / Ultra)"],
        "cost": {"nebius_usd": round(usd + promises_usd, 4), "tavily_credits": credits,
                 "gbif_calls": gbif, "approx_seconds": seconds},
        "known_issue_score": dict(zip(("passed", "scored"), ct.score(rows))),
        "findings": findings, "exported_in_s": round(time.time() - started, 1),
    }
    if full:
        run, skipped = extra["run"], extra["skipped"]
        n_skipped = 1213 - len(pages_read)
        kinds = [SKIP_LABELS.get(k, k) for k, v in sorted(skipped.items(), key=lambda kv: -len(kv[1]))
                 if set(v) - pages_read]
        out["pages_skipped"] = n_skipped
        out["pages_note"] = (f"pages audited; {n_skipped} skipped: {'/'.join(kinds)}"
                             if n_skipped else "pages audited")
        # The full audit's own cost, credits and wall clock, plus the separate ToR run.
        out["cost"] = {"nebius_usd": round(run["cost_usd"] + promises_usd, 4),
                       "tavily_credits": run["tavily"]["credits"], "gbif_calls": gbif,
                       "approx_seconds": run["wall_clock_s"],
                       "time_note": "wall clock, full audit, 6 parallel calls"}
        out["full_run"] = {"file": FULL_RUN.name, "cost_usd": run["cost_usd"],
                           "wall_clock_s": run["wall_clock_s"],
                           "pages_audited": run["pages_audited"]}
    return report_id, out


def indira_point_table():
    report_id = "indira_point_table_3_16"
    trace.reset()
    started = time.time()
    table, results = demo_table.run(str(TABLE_IMAGE), *INDIRA_POINT)
    st = status.check_table(table, copycheck.Budget(copycheck.MAX_TAVILY_CREDITS))
    findings = []
    for c, r in results:
        if r["grade"] not in ("RED", "ORANGE"):
            continue
        ev = [{"label": "GBIF records of this species",
               "value": f"{r['local_count']:,} within 100 km, {r['regional_count']:,} within "
                        f"500 km, {r['global_count']:,} worldwide"},
              {"label": f"Survey effort ({r['class_name']})",
               "value": f"{r['effort_count']:,} records within 100 km"
                        + (f", {r['regional_effort_count']:,} within 500 km"
                           if r.get("regional_effort_count") is not None else "")},
              {"label": "GBIF species page", "value": r["matched_name"],
               "url": r["gbif_links"].get("species")},
              {"label": "GBIF records near the site", "value": "map of records within 500 km",
               "url": r["gbif_links"].get("regional")}]
        if r["name_note"]:
            ev.insert(0, {"label": "Name", "value": r["name_note"]})
        findings.append(finding(
            f"sp-{len(findings) + 1:02d}", "species_range", r["grade"],
            f"{c['value']} at Indira Point", r["evidence"],
            [{"page": None, "where": "Table 3.16", "text": c["value"]}], ev, r["evidence"]))

    for s in st["results"]:
        if s["grade"] != "ORANGE":
            continue
        check = "iucn_status" if s["check"] == "iucn" else "legal_schedule"
        ev = [{"label": "Report says", "value": str(s["report_value"])},
              {"label": "Current", "value": str(s.get("current_value"))}]
        if check == "iucn_status":
            ev.append({"label": "GBIF / IUCN Red List", "value": s.get("gbif_name"), "url": s.get("url")})
        else:
            ev.append({"label": f"Source ({s.get('source_label') or 'source'})",
                       "value": s.get("quote"), "url": s.get("url")})
        findings.append(finding(
            f"st-{len(findings) + 1:02d}", check, "ORANGE",
            f"{s['name']}: {'IUCN category' if check == 'iucn_status' else 'WPA schedule'} "
            f"{s['report_value']}", s["message"],
            [{"page": None, "where": "Table 3.16", "text": f"{s['name']} | {s['report_value']}"}],
            ev, s["evidence"]))

    usd, credits, gbif, seconds = run_cost(trace.used)
    return report_id, {
        "id": report_id, "title": "Indira Point REIA, Table 3.16 (as published by Scroll.in)",
        "source": "Table 3.16 of the WAPCOS Indira Point REIA (Apr 2026), as published by "
                  "Scroll.in, 31 Aug 2026",
        "pages_read": 1, "pages_total": 1, "unit": "table",
        "checks": ["Table reading (Nemotron Super-VL)", "Species range (GBIF)",
                   "IUCN status (GBIF / IUCN Red List)", "WPA schedule (Tavily, official sources)"],
        "cost": {"nebius_usd": usd, "tavily_credits": credits, "gbif_calls": gbif,
                 "approx_seconds": seconds},
        "findings": findings, "exported_in_s": round(time.time() - started, 1),
    }


def no_secrets_in(folder):
    keys = [v for k, v in os.environ.items() if k.endswith("_API_KEY") and v and len(v) > 12]
    for p in folder.rglob("*.json"):
        text = p.read_text(encoding="utf-8")
        assert not any(k in text for k in keys), f"API key found in {p}"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    RESULTS.mkdir(exist_ok=True)
    index = []
    for build in (great_nicobar, indira_point_table):
        report_id, data = build()
        (RESULTS / f"{report_id}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        grades = {g: sum(f["grade"] == g for f in data["findings"]) for g in ("RED", "ORANGE", "INFO")}
        index.append({"id": report_id, "title": data["title"], "file": f"{report_id}.json"})
        print(f"{report_id}: {len(data['findings'])} findings {grades}; cost {data['cost']}")
    (RESULTS / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    no_secrets_in(RESULTS)
    print(f"Wrote {RESULTS} ({sum(1 for _ in PAGES_OUT.glob('*.png'))} page images). "
          f"New API spend: ${llm.session_cost_usd:.4f}")


if __name__ == "__main__":
    main()
