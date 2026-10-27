"""Model badges: which model or tool produced each piece of a finding.

Worked out from saved data only (no model calls):
- "Read by Lightning" / "Read by Super-VL": which model extracted the claims on each quoted
  page, from results/page_readers_<report>.json (scripts/export_page_readers.py). Without that
  file, the pages in the Super-VL inspector (results/inspector/index.json) count as Super-VL.
  A report that is one table image (unit "table") was read by Super-VL.
- "Screened by Lightning": the Lightning triage (contradictions) or first pass (ToR promises).
- "Judged by Ultra": the finding's evidence says Nemotron Ultra checked it.
- "Found via Tavily" / "GBIF records": the check's evidence came from Tavily or GBIF.
"""

import json
from functools import lru_cache
from pathlib import Path

from tigerfish.ui.style import esc

RESULTS = Path(__file__).resolve().parents[2] / "results"

READ_LIGHTNING = "Read by Lightning"
READ_SUPER_VL = "Read by Super-VL"
SCREENED_LIGHTNING = "Screened by Lightning"
JUDGED_ULTRA = "Judged by Ultra"
ANSWERED_ULTRA = "Answered by Ultra"
TAVILY = "Found via Tavily"
GBIF = "GBIF records"

# label: (style kind, hover text)
INFO = {
    READ_LIGHTNING: ("nemotron", "Nemotron 3.5 Lightning extracted the claims from the page text."),
    READ_SUPER_VL: ("nemotron", "Nemotron 3.5 Super-VL read the page image (scanned page or table)."),
    SCREENED_LIGHTNING: ("nemotron", "Nemotron 3.5 Lightning screened this before Ultra was asked."),
    JUDGED_ULTRA: ("nemotron", "Nemotron 3 Ultra read the pages and gave the verdict."),
    ANSWERED_ULTRA: ("nemotron", "Nemotron 3 Ultra read the whole report and answered. Only the "
                                 "quotes are checked."),
    TAVILY: ("tavily", "The linked source was found with Tavily web search."),
    GBIF: ("gbif", "Occurrence records or IUCN status from GBIF (gbif.org)."),
}
MODEL_READERS = {"super_vl": READ_SUPER_VL, "lightning": READ_LIGHTNING}

CLAIM_CHECKS = ("contradiction", "recycled_figure")       # built on extracted claims
SCREENED_CHECKS = ("contradiction", "promise")            # recycled figures skip the triage
TAVILY_CHECKS = ("copy_paste", "borrowed_text", "accreditation", "legal_schedule")
GBIF_CHECKS = ("species_range", "omission", "iucn_status")
TABLE_CHECKS = ("species_range", "iucn_status", "legal_schedule")   # rows of a table image
LIGHTNING_READ_CHECKS = ("accreditation",)                # Lightning reads the NABET pages


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@lru_cache(maxsize=16)
def readers(report_id, results=RESULTS):
    """{"pages": {page: label}, "table": label or None} for one saved report."""
    pages = {}
    saved = _load(results / f"page_readers_{report_id}.json")
    if saved:
        for key, label in MODEL_READERS.items():
            pages.update({int(p): label for p in saved.get(key, [])})
    else:
        inspector = _load(results / "inspector" / "index.json") or {}
        if inspector.get("report_id") == report_id:
            pages = {int(p["page"]): READ_SUPER_VL for p in inspector.get("pages", [])}
    report = _load(results / f"{report_id}.json") or {}
    table = (READ_SUPER_VL if report.get("unit") == "table"
             and any("Super-VL" in c for c in report.get("checks", [])) else None)
    return {"pages": pages, "table": table}


def _pages(pages):
    return ("p." if len(pages) == 1 else "pp.") + ", ".join(str(p) for p in sorted(pages))


def finding_badges(f, rd=None):
    """[(label, detail)] in pipeline order: read, screened, judged, then outside sources."""
    rd = rd or {"pages": {}, "table": None}
    check = f.get("check")
    quote_pages = list(dict.fromkeys(q["page"] for q in f.get("quotes", []) if q.get("page")))
    out = []
    if check in CLAIM_CHECKS:
        by_reader = {}
        for p in quote_pages:
            if p in rd["pages"]:
                by_reader.setdefault(rd["pages"][p], []).append(p)
        out += [(label, _pages(ps)) for label, ps in by_reader.items()]
    elif check in LIGHTNING_READ_CHECKS and quote_pages:
        out.append((READ_LIGHTNING, _pages(quote_pages)))
    if check in TABLE_CHECKS and rd.get("table") and not quote_pages:
        out.append((rd["table"], "table image"))
    if check in SCREENED_CHECKS:
        out.append((SCREENED_LIGHTNING, ""))
    if any("Nemotron Ultra" in str(e.get("value", "")) for e in f.get("evidence", [])):
        out.append((JUDGED_ULTRA, ""))
    if check in TAVILY_CHECKS and any(e.get("url") for e in f.get("evidence", [])):
        out.append((TAVILY, ""))
    if check in GBIF_CHECKS:
        out.append((GBIF, ""))
    return out


def memo_badges(m=None):
    """The reviewer's memo: Ultra read the whole report and judged each issue."""
    pages = f"{m['pages_included']:,} pages, one call" if m and m.get("pages_included") else ""
    return [(JUDGED_ULTRA, pages)]


def ask_badges(a=None):
    return [(ANSWERED_ULTRA, "whole report")]


def html(badges):
    """A row of plain-text badges, or "" when there are none."""
    if not badges:
        return ""
    items = []
    for label, detail in badges:
        kind, tip = INFO.get(label, ("nemotron", ""))
        extra = f' <span class="tf-model-detail">{esc(detail)}</span>' if detail else ""
        items.append(f'<span class="tf-model tf-model-{kind}" title="{esc(tip)}">'
                     f'{esc(label)}{extra}</span>')
    return f'<div class="tf-models">{"".join(items)}</div>'
