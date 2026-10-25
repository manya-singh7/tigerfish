"""Export saved results for the app's replay mode into results/ (committed, unlike cache/).

Usage: python scripts/export_results.py

Runs each report's pipeline from cache (no new API calls are expected; any that are
needed stay under the usual caps) and writes:
  results/index.json                      list of reports
  results/<report>.json                   summary + findings in one shape for the UI
  results/pages/<report>_p<NNNN>.png      only pages that have findings, quotes highlighted
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
from tigerfish import claims, copycheck, llm, pdf_reader, status, trace  # noqa: E402
from tigerfish.report import (attach_images, contradiction_findings, finding,  # noqa: E402
                              highlight_pages)

RESULTS = ROOT / "results"
PAGES_OUT = RESULTS / "pages"
PAGE_DPI = 110
MAX_GAP_S = 300          # cache files written further apart than this were separate runs

GN_PDF = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"
GN_PAGES = [234, 392, 444, 751, 818, 851, 940, 978, 1141, 1168]
TABLE_IMAGE = ROOT / "data" / "demo" / "indira_point_table_3_16_mammals.png"
INDIRA_POINT = (6.75, 93.83)

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


def species_pages_read():
    """Pages the species-table check read (empty set if it has not been run)."""
    if not SPECIES_PAGES.exists():
        return set()
    data = json.loads(SPECIES_PAGES.read_text(encoding="utf-8"))
    return set(data["table_pages"]) | set(data["vision_pages"])


def fmt_count(n):
    return "-" if n is None else f"{n:,}"


def great_nicobar():
    report_id = "great_nicobar_2021_draft"
    pages = set(GN_PAGES)
    trace.reset()
    started = time.time()
    page_dicts = [p for p in pdf_reader.read_pdf(GN_PDF) if p["page"] in pages]
    claims.extract_claims(page_dicts)                      # from cache: counts extraction cost
    con = check_contradictions.run(GN_PDF, pages)
    cp = check_copypaste.run(GN_PDF, pages)
    known = {r["finding_id"]: r["id"] for r in con["evaluation"] if r["finding_id"]}

    findings = contradiction_findings(con["findings"], known)

    for r in cp["results"]:
        for h in r["hits"]:
            if h["grade"] in ("RED", "ORANGE"):
                findings.append(finding(
                    f"cp-p{r['page']}-{len(findings)}", "copy_paste", h["grade"],
                    f"Page {r['page']} text found in another document", h["message"],
                    [{"page": r["page"], "text": r["passage"]}],
                    [{"label": "Matching document", "value": h["title"] or h["url"], "url": h["url"]},
                     {"label": "Matching text", "value": h["snippet"]},
                     {"label": "Overlap", "value": f"longest run {h['longest_run']} words, "
                                                   f"8-gram overlap {h['ngram']:.0%}"}],
                    h["why"]))
        for b in r["borrowed"]:
            findings.append(finding(
                f"bt-p{b['page']}", "borrowed_text", "INFO",
                f"Page {b['page']} uses uncited text from {b['url'].split('/')[2]}", b["message"],
                [{"page": b["page"], "text": b["quote"]}],
                [{"label": "Source", "value": b["title"] or b["url"], "url": b["url"]},
                 {"label": "Verbatim run", "value": f"{b['longest_run']} words"},
                 {"label": "Source text", "value": display_snippet(b["source_snippet"])}],
                f"{b['longest_run']} consecutive words match a generic external source, and "
                f"page {b['page']} does not cite it."))

    # One image set per finding, so each page shows only that finding's quotes highlighted.
    for old in PAGES_OUT.glob(f"{report_id}_*.png"):
        old.unlink()
    for f in findings:
        quotes_by_page = {}
        for q in f["quotes"]:
            quotes_by_page.setdefault(q["page"], []).append(q["text"])
        images = highlight_pages(GN_PDF, quotes_by_page, PAGES_OUT, f"{report_id}_{f['id']}",
                                 dpi=PAGE_DPI)
        attach_images([f], images, relative_to=RESULTS)

    species_findings = species_table_findings(report_id)
    findings += species_findings
    usd, credits, gbif, seconds = run_cost(trace.used)
    return report_id, {
        "id": report_id, "title": "Great Nicobar EIA (2021 draft)",
        "source": "Draft EIA by Vimta Labs for ANIIDCO, December 2021",
        "pages_read": len(pages | species_pages_read()), "pages_total": 1213,
        "checks": ["Claim extraction (Nemotron Lightning / Super-VL)",
                   "Internal contradictions and recycled figures (Nemotron Ultra)",
                   "Copied text (Tavily)", "Borrowed text (Tavily)",
                   "Species tables in the report (GBIF)"],
        "cost": {"nebius_usd": usd, "tavily_credits": credits, "gbif_calls": gbif,
                 "approx_seconds": seconds},
        "known_issue_score": dict(zip(("passed", "scored"),
                                      check_contradictions.ct.score(con["evaluation"]))),
        "findings": findings, "exported_in_s": round(time.time() - started, 1),
    }


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
