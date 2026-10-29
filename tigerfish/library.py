"""The report library (home screen): every report under results/, with live totals.

Three kinds of report:
  Full audit   results/<id>.json, listed in results/index.json (scripts/export_results.py).
               Library details (project, state, sector, year, consultant) come from
               results/library.json, because the export rewrites index.json.
  Single-table check  the same, for a report of which only one table was available
               ("unit": "table"), e.g. Indira Point's Table 3.16.
  Quick check  results/batch/<id>.json, listed in results/batch/index.json: free checks
               only, one small JSON per report (format in docs/REPORT_FORMAT.md).

Nothing here is hard-coded per report: totals, counts and filters are computed from the files.
"""

import json
import os
from pathlib import Path

from tigerfish.report import sort_findings
from tigerfish import batch_results

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FORMAT = "tigerfish-report/1"
FULL, QUICK, TABLE = "Full audit", "Quick check", "Single-table check"
AUDIT_TYPES = {"full": FULL, "quick": QUICK, "table": TABLE}
TABLE_NOTE = ("Only one table of this report was available, so only the checks that read a "
              "species table ran on it (species range and IUCN status vs GBIF).")
GRADES = ("RED", "ORANGE", "INFO")
REVIEWED = {"real", "false_alarm", "unsure", "disputed"}
QUICK_NOTICE = "Quick check: free checks only; full audit not run."
# Checks a quick check may contain (all free: no Nebius call, no Tavily credit)
QUICK_CHECKS = {"number_pair", "species_range", "iucn_status", "omission"}
SECTORS = ["Ports and harbours", "Airports", "Highways and roads", "Railways", "Mining",
           "Thermal power", "Hydro power", "River valley and irrigation",
           "Industrial projects", "Infrastructure and townships", "Nuclear", "Other"]


def batch_dir(results=None):
    """Quick checks live in results/batch/. TIGERFISH_BATCH_DIR points elsewhere (tests and
    the UI check use tests/fixtures/library/batch)."""
    env = os.getenv("TIGERFISH_BATCH_DIR", "").strip()
    if env and results is None:
        return Path(env) if Path(env).is_absolute() else ROOT / env
    return Path(results or RESULTS) / "batch"


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def counts(findings):
    return {g: sum(f.get("grade") == g for f in findings) for g in GRADES}


def review_counts(findings, queue=None, reviews=None):
    """(reviewed, flagged) over RED/ORANGE findings: a hand verification on the finding, or a
    decision in the review queue. None if nothing has been reviewed and there is no queue."""
    flagged = [f for f in findings if f.get("grade") in ("RED", "ORANGE")]
    verdicts = {}
    if queue:
        from tigerfish import review
        for i in queue.get("items", []):
            v = review.verdict(i, reviews or {})
            verdicts[i["flag_id"]] = v
            if i.get("finding_id") and v in REVIEWED:      # a flag of a merged finding
                verdicts[i["finding_id"]] = v
    done = sum(1 for f in flagged if f.get("verification") or verdicts.get(f["id"]) in REVIEWED)
    if not done and not queue:
        return None
    return done, len(flagged)


def _entry(report, meta, kind, path, queue=None, reviews=None):
    findings = report.get("findings") or []
    unit = report.get("unit", "page")
    audit = report.get("audit_type") or ("quick" if kind == "batch" else
                                         "table" if unit == "table" else "full")
    hr = report.get("human_reviewed")
    if isinstance(hr, dict) and "reviewed" in hr:
        reviewed = (int(hr["reviewed"]), int(hr.get("of", 0)))
    else:
        reviewed = review_counts(findings, queue, reviews)
    get = lambda k: report.get(k) if report.get(k) not in (None, "") else meta.get(k)
    return {
        "id": report["id"],
        "title": report.get("title") or report["id"],
        "project": get("project") or report.get("title") or report["id"],
        "state": get("state"),
        "sector": get("sector"),
        "year": get("year"),
        "consultant": get("consultant"),
        "pages": int(report.get("pages_read") or 0),
        "pages_total": int(report.get("pages_total") or 0),
        "unit": unit,
        "audit_type": AUDIT_TYPES.get(audit, FULL),
        "grades": counts(findings),
        "reviewed": reviewed,
        "kind": kind,
        "path": str(path),
        "full_run": report.get("full_run") or None,
        "verified": sum(1 for f in findings if f.get("verification")),
        "screening": batch_results.summary(report),
    }


def entries(results=None, queue=None, reviews=None):
    """Every report: the saved full audits (results/index.json) then the quick checks
    (results/batch/index.json). queue/reviews: the human review queue (tigerfish/review.py)."""
    results = Path(results or RESULTS)
    meta = _read(results / "library.json") or {}
    per_report = queue is None and results == RESULTS     # each report's own queue and reviews
    if per_report:
        from tigerfish import review
    out = []
    for item in _read(results / "index.json") or []:
        path = results / item["file"]
        report = _read(path)
        if not report:
            continue
        if per_report:
            q, r = review.queue_for(report), review.load_reviews(report_id=report["id"])
        else:
            q = queue if queue and queue.get("report_id") == report["id"] else None
            r = reviews
        out.append(_entry(report, meta.get(report["id"], {}), "saved", path, q, r))
    bdir = batch_dir(None if results == RESULTS else results)
    index = _read(bdir / "index.json") or {}
    for item in index.get("reports", []) if isinstance(index, dict) else []:
        path = bdir / item["file"]
        report = _read(path)
        if report and not validate(report):
            out.append(_entry(report, {}, "batch", path))
    return out


def totals(items):
    """{"reports", "pages", "flags", "red", "orange", "info", "full", "quick"} from the entries."""
    return {"reports": len(items), "pages": sum(e["pages"] for e in items),
            "flags": sum(e["grades"]["RED"] + e["grades"]["ORANGE"] for e in items),
            "red": sum(e["grades"]["RED"] for e in items),
            "orange": sum(e["grades"]["ORANGE"] for e in items),
            "info": sum(e["grades"]["INFO"] for e in items),
            "full": sum(e["audit_type"] == FULL for e in items),
            "quick": sum(e["audit_type"] == QUICK for e in items),
            "table": sum(e["audit_type"] == TABLE for e in items)}


def totals_line(t):
    eia = "EIA" if t["reports"] == 1 else "EIAs"
    return (f"{t['reports']:,} {eia} checked, {t['pages']:,} pages read, {t['flags']:,} flags "
            f"({t['red']:,} RED, {t['orange']:,} ORANGE) and {t['info']:,} INFO leads")


def _about_pages(n):
    """~360, ~1,200: two significant figures."""
    if n < 100:
        return f"~{n}"
    step = 10 ** (len(str(n)) - 2)
    return f"~{round(n / step) * step:,}"


def _usd(x):
    return f"${x:.0f}" if x >= 10 else f"${x:.2f}"


def full_runs(items):
    """[(report length in pages, Nebius USD)] of the saved full runs, shortest first."""
    out = []
    for e in items:
        run = e.get("full_run") or {}
        if run.get("cost_usd") and e.get("pages_total"):
            out.append((e["pages_total"], float(run["cost_usd"])))
    return sorted(out)


def price_line(items, dollar="$"):
    """"Full audit: about $2.40 for ~370 pages to $16 for ~1,200 pages (measured)", from the
    saved full runs (None if there are none). dollar: "\\$" for Streamlit markdown."""
    runs = full_runs(items)
    if not runs:
        return None
    usd = lambda x: _usd(x).replace("$", dollar)
    (n0, c0), (n1, c1) = runs[0], runs[-1]
    if len(runs) == 1:
        return f"Full audit: about {usd(c0)} for {_about_pages(n0)} pages (measured, 1 run)"
    return (f"Full audit: about {usd(c0)} for {_about_pages(n0)} pages to {usd(c1)} for "
            f"{_about_pages(n1)} pages (measured, {len(runs)} runs)")


def options(items, key):
    """Sorted distinct values of a field (for a filter), without blanks."""
    vals = {e.get(key) for e in items if e.get(key) not in (None, "")}
    return sorted(vals, key=lambda v: (isinstance(v, str), v), reverse=key == "year")


def filter_entries(items, query="", states=(), sectors=(), years=(), audit_types=(),
                   has_red=False, has_verified=False):
    q = " ".join(str(query or "").lower().split())
    out = []
    for e in items:
        text = f"{e['project']} {e['title']}".lower()
        if q and not all(w in text for w in q.split()):
            continue
        if states and e.get("state") not in states:
            continue
        if sectors and e.get("sector") not in sectors:
            continue
        if years and e.get("year") not in years:
            continue
        if audit_types and e["audit_type"] not in audit_types:
            continue
        if has_red and not e["grades"]["RED"]:
            continue
        if has_verified and not e.get("verified"):
            continue
        out.append(e)
    return out


def load(entry):
    """The full report dict for an entry, findings sorted."""
    data = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))
    data["findings"] = sort_findings(data.get("findings") or [])
    data.setdefault("checks", [c["name"] for c in data.get("checks_run", []) if c.get("status") == "ran"])
    return data


def find(items, report_id):
    return next((e for e in items if e["id"] == report_id), None)


# ---------- the quick-check format (docs/REPORT_FORMAT.md) ----------

REQUIRED = {"format": str, "id": str, "audit_type": str, "title": str, "project": str,
            "state": (str, type(None)), "sector": (str, type(None)), "year": (int, type(None)),
            "pages_total": int, "pages_read": int, "checks_run": list, "findings": list}
FINDING_REQUIRED = ("id", "check", "check_name", "grade", "title", "message", "quotes",
                    "evidence", "why")
CHECK_STATES = {"ran", "not_available", "failed"}
MAX_BYTES = 200_000


def validate(report, raw_bytes=None):
    """Problems with a quick-check report ([] = valid)."""
    problems = []
    for key, typ in REQUIRED.items():
        if key not in report:
            problems.append(f"missing {key}")
        elif not isinstance(report[key], typ):
            problems.append(f"{key} has the wrong type")
    if problems:
        return problems
    if report["format"] != FORMAT:
        problems.append(f"format must be {FORMAT}")
    if report["audit_type"] != "quick":
        problems.append("audit_type must be \"quick\"")
    if report["pages_read"] > report["pages_total"]:
        problems.append("pages_read is more than pages_total")
    for c in report["checks_run"]:
        if c.get("check") not in QUICK_CHECKS:
            problems.append(f"check {c.get('check')!r} is not a free check")
        if c.get("status") not in CHECK_STATES:
            problems.append(f"check {c.get('check')!r}: status must be one of {sorted(CHECK_STATES)}")
        if c.get("status") != "ran" and not c.get("reason"):
            problems.append(f"check {c.get('check')!r}: a check that did not run needs a reason")
    ran = {c["check"] for c in report["checks_run"] if c.get("status") == "ran"}
    for f in report["findings"]:
        missing = [k for k in FINDING_REQUIRED if k not in f]
        if missing:
            problems.append(f"finding {f.get('id')}: missing {', '.join(missing)}")
            continue
        if f["grade"] not in GRADES:
            problems.append(f"finding {f['id']}: grade must be RED, ORANGE or INFO")
        if f["check"] not in ran:
            problems.append(f"finding {f['id']}: its check {f['check']!r} is not listed as ran")
        if f["check"] == "number_pair" and f["grade"] != "INFO":
            problems.append(f"finding {f['id']}: number pairs are not judged by a model, so INFO only")
    size = len(raw_bytes) if raw_bytes is not None else len(json.dumps(report, ensure_ascii=False).encode())
    if size > MAX_BYTES:
        problems.append(f"file is {size:,} bytes; keep it under {MAX_BYTES:,}")
    return problems
