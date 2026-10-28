"""Export saved results for the app's replay mode into results/ (committed, unlike cache/).

Usage: python scripts/export_results.py                  (every report)
       python scripts/export_results.py --only cuddalore  (one report; the others are kept)
       python scripts/export_results.py --only karnataka  (after its audit has run)

Runs each report's pipeline from cache (no new API calls are expected; any that are
needed stay under the usual caps) and writes:
  results/index.json                      list of reports
  results/<report>.json                   summary + findings in one shape for the UI
  results/pages/<report>_p<NNNN>.png      only pages that have findings, quotes highlighted
  (results/<report>_promises.json, the ToR table + timeline, is written by check_promises.py)
No PDFs, no source images (the Scroll table image stays local), no API keys.
"""

import argparse
import json
import math
import os
import re
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
from tigerfish import (accreditation, claims, copycheck, llm, pdf_reader, promises,  # noqa: E402
                       scope, sites, status, trace)
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
CUD_PDF = ROOT / "data" / "eias" / "cuddalore_port_2026_draft_eia.pdf"
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


def findings_file(pdf, name):
    """cache/findings/<pdf stem>/<name>: a check's saved results for one report."""
    return ROOT / "cache" / "findings" / pdf.stem / name


# Plants: GBIF has few digitised plant records for Great Nicobar but many within 500 km
# (Sumatra, Andamans), so the "region surveyed, species absent" rule flags most plant names
# (206 of 334 in the first run). Those stay in species_pages.json but are not app findings.
EXPORT_PLANT_FLAGS = False
PLANT_CLASSES = {"Magnoliopsida", "Liliopsida", "Polypodiopsida", "Cycadopsida", "Pinopsida",
                 "Gnetopsida", "Lycopodiopsida", "Bryopsida"}


def species_table_findings(report_id, pdf=GN_PDF):
    """RED/ORANGE results of scripts/check_species_pages.py as findings (one shared,
    highlighted image per page, so many flagged names don't mean many images)."""
    path = findings_file(pdf, "species_pages.json")
    if not path.exists():
        return []
    rows = [r for r in json.loads(path.read_text(encoding="utf-8"))["rows"]
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
    images = highlight_pages(pdf, by_page, PAGES_OUT, f"{report_id}_species", dpi=PAGE_DPI)
    attach_images(out, images, relative_to=RESULTS)
    return out


def omission_findings(pdf=GN_PDF, site_label="Galathea Bay"):
    """RED/ORANGE/INFO results of scripts/check_omissions.py as findings."""
    path = findings_file(pdf, "omissions.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("not_applicable"):
        return []
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
                             "text": f"{r['name']}: {r['wide']} record(s) within 25 km of {site_label}, "
                                     f"latest {latest}"}],
                           ev, f"GBIF has {r['wide']} record(s) of this IUCN {r['category']} species "
                               f"within 25 km of the site; no page of the report names it."))
    return out


def accreditation_findings(pdf=GN_PDF):
    """The accreditation check as one finding (any grade except GREY)."""
    path = findings_file(pdf, "accreditation.json")
    if not path.exists():
        return []
    a = json.loads(path.read_text(encoding="utf-8"))
    if a.get("not_applicable") or a["grade"] in ("GREY", "NONE") or not a.get("entry"):
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


def species_pages_read(pdf=GN_PDF):
    """Pages the species-table check read (empty set if it has not been run)."""
    path = findings_file(pdf, "species_pages.json")
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
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
    return all(any(same_quote(q, r) for r in b["quotes"]) for q in a["quotes"])


def same_quote(q, r):
    """Report quotes match loosely (ct.quotes_match) on the same page. A quote with no page is
    our own summary line (e.g. an omission's GBIF line): those differ only in the species name
    and numbers, so they must match exactly, or every omission collapses into one."""
    if q.get("page") is None or r.get("page") is None:
        return q.get("page") == r.get("page") and q["text"] == r["text"]
    return q["page"] == r["page"] and ct.quotes_match(q["text"], r["text"])


def dedupe(findings):
    """RED/ORANGE/INFO only, duplicates removed (the higher grade is kept), sorted by
    grade then check."""
    out = []
    for f in sort_findings([f for f in findings if f["grade"] in GRADE_ORDER]):
        if not any(same_finding(f, g) for g in out):
            out.append(f)
    return sort_findings(out)


def page_images(prefix, findings, shared, pdf=GN_PDF):
    """Highlighted page images. shared=False: one image set per finding (only its quotes
    highlighted). shared=True (full run, many findings): one image per page with every
    finding's quotes on it, so the image count is bounded by the pages."""
    if shared:
        by_page = {}
        for f in findings:
            for q in f["quotes"]:
                if q.get("page"):
                    by_page.setdefault(q["page"], []).append(q["text"])
        images = highlight_pages(pdf, by_page, PAGES_OUT, prefix, dpi=PAGE_DPI)
        attach_images(findings, images, relative_to=RESULTS)
        return
    for f in findings:
        quotes_by_page = {}
        for q in f["quotes"]:
            quotes_by_page.setdefault(q["page"], []).append(q["text"])
        images = highlight_pages(pdf, quotes_by_page, PAGES_OUT, f"{prefix}_{f['id']}",
                                 dpi=PAGE_DPI)
        attach_images([f], images, relative_to=RESULTS)


# results/investigations/ were recorded on the 10-page export, where gn-001 was ct-003; the
# full run numbers findings differently (gn-001 is ct-031), so link them by known issue.
RECORDED_FOR_ISSUE = {"gn-001": "ct-003"}

def apply_verification(findings, issues, rows):
    """Mark the findings a person verified by hand (data/known_issues.json): the known issue,
    who verified it and when, the note, and the reviewed wording (title and summary) for the
    card. Supporting sources added by hand go into the evidence, marked manual (not Tavily).
    Returns the ids of the verified findings."""
    by_row = {r["id"]: r for r in rows}
    by_id = {f["id"]: f for f in findings}
    done = []
    for issue in issues:
        if not issue.get("verified_by"):
            continue
        fid = (by_row.get(issue["id"]) or {}).get("finding_id")
        f = by_id.get(fid) or next((g for g in findings if g.get("known_issue") == issue["id"]), None)
        if not f:       # negative controls and explained issues have no card
            continue
        f["known_issue"] = issue["id"]
        f["verification"] = {"by": issue["verified_by"], "on": issue["verified_on"],
                             "outcome": issue.get("verification_outcome", "confirmed"),
                             "note": issue["verification_note"],
                             "wording": issue.get("verified_wording")}
        if issue.get("verified_title"):
            f["title"] = issue["verified_title"]
        for src in issue.get("external_sources", []):
            if src.get("supporting_only") and not any(e.get("url") == src.get("url")
                                                      for e in f["evidence"]):
                f["evidence"].append({"label": f"Supporting, added by hand: {src['what']}",
                                      "value": src["text"], "url": src.get("url"), "manual": True})
        done.append(f["id"])
    return done


SKIP_LABELS = {"hindi": "Hindi", "lab_report": "lab sheets", "annexure": "forms",
               "error": "unreadable"}


def full_run_core(pdf=GN_PDF):
    """Contradiction and copy-paste findings of the full audit (scripts/audit.py without
    --pages), rebuilt from cache. (findings, known-issue rows, extras) or None."""
    run_file = RESULTS / f"audit_{pdf.stem}.json"
    findings_jsonl = findings_file(pdf, "full_run/contradictions.jsonl")
    if not (run_file.exists() and findings_jsonl.exists()):
        return None
    run = json.loads(run_file.read_text(encoding="utf-8"))
    kept, skipped = scope.select_pages(pdf_reader.read_pdf(pdf))
    texts = {p["page"]: p["text"] for p in kept}
    con = [json.loads(line) for line in findings_jsonl.read_text(encoding="utf-8").splitlines()
           if line.strip()]
    rows = ct.evaluate(con, check_contradictions.known_issues_for(pdf))
    known = {r["finding_id"]: r["id"] for r in rows if r["finding_id"]}
    ledger = [c for c in claims.load_ledger(pdf.stem) if c["page"] in texts]
    budget = copycheck.Budget(max(run["tavily"]["credits"], 1))  # cached: no new credits
    if run.get("copy_passage_list"):     # the passages the run checked, as it saved them
        passages = [{"page": p["page"], "text": p["text"], "claim_ids": p.get("claim_ids", []),
                     "score": p.get("score")} for p in run["copy_passage_list"]]
    else:
        # Older runs did not save their passages. In the Oct 27 full run the Lightning
        # site-specific filter failed (reply cut off), so the run checked the top passages
        # by score without it: use_llm=False reproduces that exactly, with no new calls.
        passages = copycheck.select_passages(ledger, texts, max_passages=run["copy_passages"],
                                             use_llm=False)
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
    issues = check_contradictions.known_issues_for(GN_PDF)
    rows = rows + ct.evaluate_other_checks(findings, issues)
    verified = apply_verification(findings, issues, rows)
    print(f"Human-verified findings: {', '.join(verified)}")
    for f in findings:   # recorded investigations keep the id they were recorded under
        rec = RECORDED_FOR_ISSUE.get(f.get("known_issue"))
        if rec and rec != f["id"]:
            f["investigation_id"] = rec
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
        "known_issues": [{k: r[k] for k in ("id", "type", "expected", "grade", "finding_id",
                                            "ok", "scored", "status")} for r in rows],
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
        # run_totals (when present) covers every run the audit took, not just the last one.
        tot = run.get("run_totals") or {"cost_usd": run["cost_usd"],
                                        "tavily_credits": run["tavily"]["credits"],
                                        "wall_clock_s": run["wall_clock_s"]}
        out["cost"] = {"nebius_usd": round(tot["cost_usd"] + promises_usd, 4),
                       "tavily_credits": tot["tavily_credits"], "gbif_calls": gbif,
                       "approx_seconds": tot["wall_clock_s"],
                       "time_note": "wall clock, full audit, 6 parallel calls",
                       "note": (f"Nebius models: full audit ${tot['cost_usd']:.2f} + ToR check "
                                f"${promises_usd:.2f}")}
        out["full_run"] = {"file": FULL_RUN.name, "cost_usd": tot["cost_usd"],
                           "wall_clock_s": tot["wall_clock_s"],
                           "pages_audited": run["pages_audited"]}
    return report_id, out


WPA_CHECK_NAME = "WPA schedule (Tavily: India Code / Gazette first, then official sites and PRS)"


def tier_note(tier):
    """Evidence line for a WPA source tier that was searched but gave no usable sentence."""
    where = ", ".join(tier["domains"] or ["the open web"])
    return (f"Searched first (Tavily, restricted to {where}); the results read do not state "
            f"the number of schedules, so the next tier was used.")


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
            ev += [{"label": t["tier"], "value": tier_note(t)}
                   for t in s.get("source_tiers") or [] if not t["found"]]
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
                   "IUCN status (GBIF / IUCN Red List)", WPA_CHECK_NAME],
        "cost": {"nebius_usd": usd, "tavily_credits": credits, "gbif_calls": gbif,
                 "approx_seconds": seconds},
        "findings": findings, "exported_in_s": round(time.time() - started, 1),
    }


# ---------- Cuddalore Port expansion (2026 draft EIA) ----------

STOPPED_AT = re.compile(r"stopped at candidate (\d+) of (\d+)")


def audit_status(run):
    """How much of the audit's candidate list was judged, from the run report. It updates by
    itself after a resume: a run that was not stopped judged every candidate."""
    total = run["candidates"]
    m = STOPPED_AT.search(run.get("stopped") or "")
    if m:
        judged, total = int(m.group(1)), int(m.group(2))
        return {"complete": False, "judged": judged, "candidates": total,
                "label": f"Audit partial: {judged:,} of {total:,} candidate pairs judged"}
    return {"complete": True, "judged": total, "candidates": total,
            "label": f"Audit complete: all {total:,} candidate pairs judged"}


def status_table_findings(report_id, pdf):
    """ORANGE results of scripts/check_status_pages.py (IUCN / WPA in the report's own
    tables) as findings. The same name, check and printed value on several pages is one
    finding citing every page."""
    path = findings_file(pdf, "status_pages.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = {}
    for r in data["results"]:
        if r["grade"] == "ORANGE":
            groups.setdefault((r["check"], r["name"], str(r["report_value"])), []).append(r)
    out = []
    for (chk, name, value), rs in groups.items():
        s, pages = rs[0], sorted({r["page"] for r in rs})
        check = "iucn_status" if chk == "iucn" else "legal_schedule"
        ev = [{"label": "Report says", "value": value},
              {"label": "Current", "value": str(s.get("current_value"))}]
        if check == "iucn_status":
            ev.append({"label": "GBIF / IUCN Red List", "value": s.get("gbif_name"), "url": s.get("url")})
        else:
            ev.append({"label": f"Source ({s.get('source_label') or 'source'})",
                       "value": s.get("quote"), "url": s.get("url")})
            ev += [{"label": t["tier"], "value": tier_note(t)}
                   for t in s.get("source_tiers") or [] if not t["found"]]
        where = ", ".join(f"p.{n}" for n in pages)
        what = "IUCN category" if check == "iucn_status" else "WPA schedule"
        out.append(finding(f"st-{len(out) + 1:02d}", check, "ORANGE",
                           f"{name}: {what} {value} ({where})", s["message"],
                           [{"page": n, "text": name} for n in pages], ev, s["evidence"]))
    by_page = {}
    for f in out:
        for q in f["quotes"]:
            by_page.setdefault(q["page"], []).append(q["text"])
    images = highlight_pages(pdf, by_page, PAGES_OUT, f"{report_id}_status", dpi=PAGE_DPI)
    attach_images(out, images, relative_to=RESULTS)
    return out


def certificate_findings(pages):
    """INFO: the report states more than one NABET certificate number (read from the
    report's own text; nothing is looked up). One quote per distinct number."""
    found = accreditation.certificate_numbers(pages)
    if len(found) < 2:
        return []
    listed = "; ".join(f"{c['number']} (p.{c['page']}"
                       + (f", also pp. {', '.join(map(str, c['also_on']))}" if c["also_on"] else "")
                       + ")" for c in found)
    return [finding("ac-02", "accreditation", "INFO",
                    f"The report gives {len(found)} different NABET certificate numbers",
                    "The report states more than one NABET certificate number for its consultant. "
                    "Flagged, verify which certificate covers this report.",
                    [{"page": c["page"], "text": c["quote"]} for c in found],
                    [{"label": "Certificate numbers in the report", "value": listed}],
                    f"Different certificate numbers appear in the report: {listed}.")]


def cuddalore():
    report_id = "cuddalore_port_2026_draft"
    prof = sites.profile(CUD_PDF.stem)
    trace.reset()
    started = time.time()
    for old in PAGES_OUT.glob(f"{report_id}_*.png"):
        old.unlink()
    full = full_run_core(CUD_PDF)
    if not full:
        sys.exit(f"No audit run for {CUD_PDF.name}: run scripts/audit.py first.")
    findings, _, extra = full
    run, kept, skipped = extra["run"], extra["kept"], extra["skipped"]
    all_pages = pdf_reader.read_pdf(CUD_PDF)
    findings += species_table_findings(report_id, CUD_PDF)
    findings += omission_findings(CUD_PDF, prof["site_label"])
    findings += status_table_findings(report_id, CUD_PDF)
    findings += accreditation_findings(CUD_PDF)
    findings += certificate_findings(all_pages)
    findings = dedupe(findings)
    page_images(f"{report_id}_full", [f for f in findings if not f["images"]], shared=True,
                pdf=CUD_PDF)

    audit = audit_status(run)
    pages_read = kept | species_pages_read(CUD_PDF)
    n_total = len(all_pages)
    n_skipped = n_total - len(pages_read)
    kinds = [SKIP_LABELS.get(k, k) for k, v in sorted(skipped.items(), key=lambda kv: -len(kv[1]))
             if set(v) - pages_read]
    tot = run.get("run_totals") or {"cost_usd": run["cost_usd"],
                                    "tavily_credits": run["tavily"]["credits"],
                                    "wall_clock_s": run["wall_clock_s"]}
    acc = findings_file(CUD_PDF, "accreditation.json")
    acc_credits = json.loads(acc.read_text(encoding="utf-8")).get("tavily_credits", 0) if acc.exists() else 0
    _, _, gbif, _ = run_cost(trace.used)
    notices = [audit["label"] + ("" if audit["complete"]
                                 else "; the pairs not yet judged may hold more flags."),
               "Flags not yet human-reviewed: each one is flagged for checking; verify it "
               "against the report before relying on it."]
    out = {
        "id": report_id, "title": "Cuddalore Port expansion EIA (2026 draft)",
        "source": "Draft EIA/EMP report by Falcon Resilient Infra Consultants for Mahathi "
                  "Cuddalore Port and Maritime Private Limited (MCPMPL), May 2026",
        "state": prof["state"],
        "site": {"lat": prof["site"][0], "lon": prof["site"][1], "label": prof["site_label"],
                 "source": prof["site_source"]},
        "audit_status": audit, "human_reviewed": False, "notices": notices,
        "pages_read": len(pages_read), "pages_total": n_total, "pages_skipped": n_skipped,
        "pages_note": (f"pages audited; {n_skipped} skipped: {'/'.join(kinds)}"
                       if n_skipped else "pages audited"),
        "checks": ["Claim extraction (Nemotron Lightning / Super-VL)",
                   "Internal contradictions and recycled figures (Nemotron Ultra)",
                   "Copied text (Tavily)",
                   "Species tables in the report (GBIF)",
                   "Threatened species not mentioned (GBIF)",
                   "IUCN status and WPA schedules in the report's tables (GBIF, Tavily)",
                   "Consultant accreditation (NABET, official list)"],
        "cost": {"nebius_usd": round(tot["cost_usd"], 4),
                 "tavily_credits": tot["tavily_credits"] + acc_credits, "gbif_calls": gbif,
                 "approx_seconds": tot["wall_clock_s"],
                 "time_note": "wall clock, full audit, 6 parallel calls",
                 "note": (f"Nebius models: full audit ${tot['cost_usd']:.2f} "
                          f"({audit['label'][0].lower() + audit['label'][1:]}); Tavily: audit "
                          f"{tot['tavily_credits']} + accreditation {acc_credits} credits")},
        "full_run": {"file": f"audit_{CUD_PDF.stem}.json", "cost_usd": tot["cost_usd"],
                     "wall_clock_s": tot["wall_clock_s"], "pages_audited": run["pages_audited"]},
        "known_issues": [],
        "findings": findings, "exported_in_s": round(time.time() - started, 1),
    }
    return report_id, out


# ---------- Karnataka Rural Roads Improvement Project (ADB EIA, July 2026) ----------

KA_PDF = ROOT / "data" / "eias" / "karnataka_rural_roads_2026_adb_eia.pdf"
CHECK_NAMES = {"omission": "Threatened species not mentioned (GBIF)",
               "accreditation": "Consultant accreditation (NABET, official list)",
               "promise": "Terms of Reference vs report",
               "public_consultation": "Public hearing comments (EIA Notification, 2006)"}


def not_applicable_notices(prof):
    """One notice per check that does not fit the report (tigerfish/sites.py), with why."""
    return [f"{CHECK_NAMES.get(k, k)}: {sites.NOT_APPLICABLE}. {why}"
            for k, why in (prof.get("not_applicable") or {}).items()]


def karnataka():
    """None until scripts/audit.py has run on the report (the other reports still export)."""
    report_id = "karnataka_rural_roads_2026_adb"
    prof = sites.profile(KA_PDF.stem)
    if not (RESULTS / f"audit_{KA_PDF.stem}.json").exists():
        print(f"{report_id}: skipped, no audit run yet (scripts/audit.py {KA_PDF.name} ...)")
        return None
    trace.reset()
    started = time.time()
    for old in PAGES_OUT.glob(f"{report_id}_*.png"):
        old.unlink()
    full = full_run_core(KA_PDF)
    if not full:
        sys.exit(f"No full-run findings for {KA_PDF.name}: run scripts/audit.py first.")
    findings, _, extra = full
    run, kept, skipped = extra["run"], extra["kept"], extra["skipped"]
    all_pages = pdf_reader.read_pdf(KA_PDF)
    findings += species_table_findings(report_id, KA_PDF)
    findings += status_table_findings(report_id, KA_PDF)
    na = prof.get("not_applicable") or {}
    if "omission" not in na:
        findings += omission_findings(KA_PDF, prof["site_label"])
    if "accreditation" not in na:
        findings += accreditation_findings(KA_PDF) + certificate_findings(all_pages)
    findings = dedupe(findings)
    page_images(f"{report_id}_full", [f for f in findings if not f["images"]], shared=True,
                pdf=KA_PDF)

    audit = audit_status(run)
    pages_read = kept | species_pages_read(KA_PDF)
    n_total = len(all_pages)
    n_skipped = n_total - len(pages_read)
    kinds = [SKIP_LABELS.get(k, k) for k, v in sorted(skipped.items(), key=lambda kv: -len(kv[1]))
             if set(v) - pages_read]
    tot = run.get("run_totals") or {"cost_usd": run["cost_usd"],
                                    "tavily_credits": run["tavily"]["credits"],
                                    "wall_clock_s": run["wall_clock_s"]}
    _, _, gbif, _ = run_cost(trace.used)
    notices = [audit["label"] + ("" if audit["complete"]
                                 else "; the pairs not yet judged may hold more flags."),
               "Flags not yet human-reviewed: each one is flagged for checking; verify it "
               "against the report before relying on it."] + not_applicable_notices(prof)
    checks = ["Claim extraction (Nemotron Lightning / Super-VL)",
              "Internal contradictions and recycled figures (Nemotron Ultra)",
              "Copied text (Tavily)",
              "Species tables in the report (GBIF)",
              "IUCN status and WPA schedules in the report's tables (GBIF, Tavily)"]
    out = {
        "id": report_id, "title": "Karnataka Rural Roads Improvement Project EIA (ADB, July 2026)",
        "source": "Environmental Impact Assessment, Part 1 of 4 (Main Report), prepared by the "
                  "Karnataka Rural Roads Development Agency, Government of Karnataka, for the "
                  "Asian Development Bank, July 2026",
        "state": prof["state"],
        "site": {"lat": prof["site"][0], "lon": prof["site"][1], "label": prof["site_label"],
                 "source": prof["site_source"]},
        "letter_addressee": prof.get("letter_addressee", "committee"),
        "letter_to": prof.get("letter_to"),
        "not_applicable": {k: f"{sites.NOT_APPLICABLE}: {why}" for k, why in na.items()},
        "audit_status": audit, "human_reviewed": False, "notices": notices,
        "pages_read": len(pages_read), "pages_total": n_total, "pages_skipped": n_skipped,
        "pages_note": (f"pages audited; {n_skipped} skipped: {'/'.join(kinds)}"
                       if n_skipped else "pages audited"),
        "checks": checks,
        "cost": {"nebius_usd": round(tot["cost_usd"], 4),
                 "tavily_credits": tot["tavily_credits"], "gbif_calls": gbif,
                 "approx_seconds": tot["wall_clock_s"],
                 "time_note": "wall clock, full audit, 6 parallel calls",
                 "note": (f"Nebius models: full audit ${tot['cost_usd']:.2f} "
                          f"({audit['label'][0].lower() + audit['label'][1:]}); Tavily: audit "
                          f"{tot['tavily_credits']} credits")},
        "full_run": {"file": f"audit_{KA_PDF.stem}.json", "cost_usd": tot["cost_usd"],
                     "wall_clock_s": tot["wall_clock_s"], "pages_audited": run["pages_audited"]},
        "known_issues": [],
        "findings": findings, "exported_in_s": round(time.time() - started, 1),
    }
    return report_id, out


def no_secrets_in(folder):
    keys = [v for k, v in os.environ.items() if k.endswith("_API_KEY") and v and len(v) > 12]
    for p in folder.rglob("*.json"):
        text = p.read_text(encoding="utf-8")
        assert not any(k in text for k in keys), f"API key found in {p}"


# --only name -> (builder, report id); this order is the report picker's order
BUILDERS = {"great_nicobar": (great_nicobar, "great_nicobar_2021_draft"),
            "cuddalore": (cuddalore, "cuddalore_port_2026_draft"),
            "karnataka": (karnataka, "karnataka_rural_roads_2026_adb"),
            "indira_point": (indira_point_table, "indira_point_table_3_16")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=list(BUILDERS),
                        help="export one report; the others in results/index.json are kept")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    RESULTS.mkdir(exist_ok=True)
    index_path = RESULTS / "index.json"
    earlier = ({e["id"]: e for e in json.loads(index_path.read_text(encoding="utf-8"))}
               if index_path.exists() else {})
    index = []
    for key, (build, rid) in BUILDERS.items():
        if args.only and key != args.only:
            if rid in earlier:            # not rebuilt this time: keep its earlier entry
                index.append(earlier[rid])
            continue
        built = build()
        if built is None:                 # not ready yet (e.g. no audit run): keep any earlier entry
            if rid in earlier:
                index.append(earlier[rid])
            continue
        report_id, data = built
        (RESULTS / f"{report_id}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        grades = {g: sum(f["grade"] == g for f in data["findings"]) for g in ("RED", "ORANGE", "INFO")}
        index.append({"id": report_id, "title": data["title"], "file": f"{report_id}.json"})
        print(f"{report_id}: {len(data['findings'])} findings {grades}; cost {data['cost']}")
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    no_secrets_in(RESULTS)
    print(f"Wrote {RESULTS} ({sum(1 for _ in PAGES_OUT.glob('*.png'))} page images). "
          f"New API spend: ${llm.session_cost_usd:.4f}")


if __name__ == "__main__":
    main()
