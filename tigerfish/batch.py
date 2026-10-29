"""Resumable corpus discovery and no-model checks for a batch of Indian EIAs.

This module deliberately does not import :mod:`tigerfish.llm` and never calls a
Nebius/NVIDIA model.  Discovery is Tavily Map/Crawl, occurrence lookups reuse
the existing cached GBIF implementation, and the PDF checks are regular
expressions over the report's text layer.

The public result shape is intentionally small and boring.  Local PDF paths
belong only in ``data/eias/batch/index.json``; the copy in ``results/batch`` is
safe to commit and contains URLs, metadata, quotes, pages and grades only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

import requests

from tigerfish import species

ROOT = Path(__file__).resolve().parents[1]
BATCH_DATA = ROOT / "data" / "eias" / "batch"
BATCH_RESULTS = ROOT / "results" / "batch"
CORPUS_INDEX = BATCH_DATA / "index.json"
PUBLIC_CORPUS_INDEX = BATCH_RESULTS / "corpus_index.json"
SUMMARY_JSON = BATCH_RESULTS / "batch_summary.json"
SUMMARY_MD = BATCH_RESULTS / "batch_summary.md"
QUICK_INDEX = BATCH_RESULTS / "index.json"
REPORT_RESULTS = BATCH_RESULTS
TAVILY_CACHE = ROOT / "cache" / "tavily"

MAX_TAVILY_CREDITS = 400
MAX_PDF_BYTES = 60 * 1024 * 1024
DOWNLOAD_DELAY = 2.0
DOWNLOAD_TIMEOUT = 60
MAX_CONSECUTIVE_DOWNLOAD_ERRORS = 3
DEFAULT_MAX_REPORTS = 90

SEEDS = (
    {"state": "Maharashtra", "url": "https://www.mpcb.gov.in/en/public-hearing-conducted?field_hearing_year_target_id=All"},
    {"state": "Maharashtra", "url": "https://www.mpcb.gov.in/index.php/en/public-hearing-upcoming"},
    {"state": "Odisha", "url": "https://ospcboard.odisha.gov.in/divisions/consent-management-division/public-hearing-2/"},
    {"state": "Haryana", "url": "http://hspcb.gov.in/page/public-hearing"},
    {"state": "Jharkhand", "url": "https://jspcb.org.in/"},
    {"state": "Goa", "url": "https://goaspcb.gov.in/category/public_hearing_conducted/"},
    {"state": "Tamil Nadu", "url": "https://tnpcb.gov.in"},
)

# Approximate state centres are only a fallback for the free species range
# check.  If a report's site is named, the named site wins.  The location used
# is always shown in the report result so a reviewer can replace it.
STATE_CENTRES = {
    "andaman and nicobar islands": (11.74, 92.66),
    "andaman & nicobar islands": (11.74, 92.66),
    "andhra pradesh": (16.51, 80.64),
    "arunachal pradesh": (27.08, 93.61),
    "assam": (26.14, 91.79),
    "bihar": (25.61, 85.14),
    "chhattisgarh": (21.25, 81.63),
    "goa": (15.49, 73.83),
    "gujarat": (23.02, 72.57),
    "haryana": (30.73, 76.78),
    "himachal pradesh": (31.10, 77.17),
    "jharkhand": (23.34, 85.31),
    "karnataka": (12.97, 77.59),
    "kerala": (8.52, 76.94),
    "madhya pradesh": (23.26, 77.41),
    "maharashtra": (19.08, 72.88),
    "manipur": (24.82, 93.94),
    "meghalaya": (25.58, 91.89),
    "mizoram": (23.73, 92.72),
    "nagaland": (25.67, 94.11),
    "odisha": (20.30, 85.82),
    "punjab": (30.90, 75.86),
    "rajasthan": (26.91, 75.79),
    "sikkim": (27.34, 88.61),
    "tamil nadu": (13.08, 80.27),
    "telangana": (17.39, 78.49),
    "tripura": (23.83, 91.28),
    "uttar pradesh": (26.85, 80.95),
    "uttarakhand": (30.32, 78.03),
    "west bengal": (22.57, 88.36),
    "delhi": (28.61, 77.21),
    "puducherry": (11.94, 79.81),
}

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
MONTH_WORDS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _clean_url(url: str) -> str:
    url = urldefrag(str(url or "").strip())[0]
    if not url.lower().startswith(("http://", "https://")):
        return ""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                       parts.query, ""))


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _quote(text: str, start: int, end: int, limit: int = 500) -> str:
    """Return a readable, page-local quote around a regex match."""
    text = str(text or "")
    left = max(text.rfind(".", 0, start) + 1, text.rfind("\n", 0, start) + 1, start - 180)
    right_candidates = [x for x in (text.find(".", end), text.find("\n", end)) if x >= 0]
    right = min(right_candidates, default=end + 220)
    out = _compact(text[left:right])
    if len(out) > limit:
        centre = max(0, min(len(out) - limit, start - left - limit // 3))
        out = out[centre:centre + limit].strip()
        if centre:
            out = "…" + out
        if centre + limit < len(_compact(text[left:right])):
            out += "…"
    return out


# ---------------------------------------------------------------------------
# Dates and the three free checks


def _year(value: str) -> int:
    n = int(value)
    return 2000 + n if n < 100 else n


def _safe_date(year: int, month: int, day: int = 1) -> date | None:
    try:
        if not 1990 <= year <= 2100 or not 1 <= month <= 12:
            return None
        return date(year, month, min(day, monthrange(year, month)[1]))
    except ValueError:
        return None


def parse_date_token(token: str) -> tuple[date, str] | None:
    """Parse common Indian report date forms, returning (date, precision).

    ``precision`` is ``day`` for a full date, ``month`` for Month/Year and
    ``year`` for a bare year.  Bare years are intentionally only accepted by
    this public helper; the scanner below uses them sparingly to avoid treating
    page numbers as dates.
    """
    raw = _compact(token).strip(" ,;:()[]")
    raw = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", raw, flags=re.I)
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        out = _safe_date(y, mo, d)
        return (out, "day") if out else None
    m = re.fullmatch(r"(\d{4})[./-](\d{1,2})(?:[./-](\d{1,2}))?", raw)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
        out = _safe_date(y, mo, d)
        return (out, "day" if m.group(3) else "month") if out else None
    m = re.fullmatch(rf"({MONTH_WORDS})[ ,./-]+(\d{{4}})", raw, re.I)
    if m:
        out = _safe_date(int(m.group(2)), MONTHS[m.group(1).lower()])
        return (out, "month") if out else None
    m = re.fullmatch(rf"(\d{{1,2}})[ ,./-]+({MONTH_WORDS})[ ,./-]+(\d{{2,4}})", raw, re.I)
    if m:
        out = _safe_date(_year(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        return (out, "day") if out else None
    m = re.fullmatch(rf"({MONTH_WORDS})[ ,./-]+(\d{{1,2}})[, ]+(\d{{2,4}})", raw, re.I)
    if m:
        out = _safe_date(_year(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
        return (out, "day") if out else None
    m = re.fullmatch(r"(\d{4})", raw)
    if m:
        out = _safe_date(int(m.group(1)), 1)
        return (out, "year") if out else None
    return None


def date_tokens(text: str, allow_year: bool = False) -> list[dict[str, Any]]:
    """Find dates in text in source order, preserving exact token and offsets."""
    text = str(text or "")
    patterns = [
        r"\b\d{1,2}(?:st|nd|rd|th)?[./-]\d{1,2}[./-]\d{2,4}\b",
        r"\b\d{4}[./-]\d{1,2}(?:[./-]\d{1,2})?\b",
        rf"\b{MONTH_WORDS}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,|\s)+\d{{4}}\b",
        rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH_WORDS}(?:,|\s)+\d{{2,4}}\b",
        rf"\b{MONTH_WORDS}[, ]+\d{{4}}\b",
    ]
    found: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            if any(match.start() < b and match.end() > a for a, b in occupied):
                continue
            parsed = parse_date_token(match.group(0))
            if not parsed:
                continue
            value, precision = parsed
            found.append({"date": value, "precision": precision, "text": match.group(0),
                          "start": match.start(), "end": match.end()})
            occupied.append((match.start(), match.end()))
    if allow_year:
        for match in re.finditer(r"\b(?:19|20)\d{2}\b", text):
            if any(match.start() < b and match.end() > a for a, b in occupied):
                continue
            parsed = parse_date_token(match.group(0))
            if parsed:
                found.append({"date": parsed[0], "precision": "year", "text": match.group(0),
                              "start": match.start(), "end": match.end()})
                occupied.append((match.start(), match.end()))
    return sorted(found, key=lambda x: x["start"])


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year, month = value.year + month // 12, month % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def period_months(start: date, end: date, precision: str = "day") -> float:
    if end < start:
        start, end = end, start
    if precision == "month":
        return round((end.year - start.year) * 12 + end.month - start.month + 1, 2)
    return round((end - start).days / 30.4375 + 1 / 30.4375, 2)


def _result(check: str, grade: str, message: str, quotes: Iterable[dict[str, Any]] = (),
            evidence: Iterable[dict[str, Any]] = (), **extra: Any) -> dict[str, Any]:
    return {"check": check, "grade": grade, "message": message,
            "quotes": list(quotes), "evidence": list(evidence), **extra}


CERTIFICATE_RE = re.compile(
    r"\bNABET\s*/\s*EIA\s*/\s*[A-Z0-9][A-Z0-9 -]{1,15}?\s*/\s*[A-Z]{1,6}\s*[- ]?\s*\d{2,5}\b",
    re.I,
)
VALID_RE = re.compile(
    rf"\bvalid\s+(?:till|until|upto|up\s+to|through)\s*[:\-]?\s*"
    rf"((?:\d{{1,2}}(?:st|nd|rd|th)?[./-]\d{{1,2}}[./-]\d{{2,4}})|"
    rf"(?:\d{{4}}[./-]\d{{1,2}}(?:[./-]\d{{1,2}})?)|"
    rf"(?:{MONTH_WORDS}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,|\s)+\d{{4}})|"
    rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH_WORDS}(?:,|\s)+\d{{2,4}})|"
    rf"(?:{MONTH_WORDS}[, ]+\d{{4}}))",
    re.I,
)


def _page_texts(pages: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return list(pages)


def _report_date(pages: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    first = pages[:4]
    labelled = re.compile(r"\b(?:report\s+date|date\s+of\s+(?:report|submission)|dated|issued|revision\s+date)\b",
                          re.I)
    choices: list[tuple[int, Mapping[str, Any], dict[str, Any]]] = []
    for p in first:
        text = str(p.get("text") or "")
        for token in date_tokens(text, allow_year=False):
            context = text[max(0, token["start"] - 100):token["end"] + 100]
            score = (100 if labelled.search(context) else 0) + (20 if p.get("page") == 1 else 0)
            choices.append((score, p, token))
    if not choices:
        return None
    _, page, token = sorted(choices, key=lambda x: (-x[0], x[1].get("page", 0), x[2]["start"]))[0]
    return {"date": token["date"], "precision": token["precision"], "page": page.get("page"),
            "text": _quote(str(page.get("text") or ""), token["start"], token["end"])}


def accreditation_check(pages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    pages = _page_texts(pages)
    report = _report_date(pages)
    certificate = None
    valid = None
    for p in pages:
        text = str(p.get("text") or "")
        match = CERTIFICATE_RE.search(text)
        if not match:
            continue
        certificate = {"value": _compact(match.group(0)), "page": p.get("page"),
                       "text": _quote(text, match.start(), match.end())}
        # Pair the validity date with the certificate when possible.  A nearby
        # date on the same page is preferable to one on a later cover page.
        window_start, window_end = max(0, match.start() - 180), min(len(text), match.end() + 420)
        window = text[window_start:window_end]
        vm = VALID_RE.search(window)
        if vm:
            parsed = parse_date_token(vm.group(1))
            if parsed:
                start = window_start + vm.start()
                end = window_start + vm.end()
                valid = {"date": parsed[0], "precision": parsed[1], "page": p.get("page"),
                         "text": _quote(text, start, end)}
        if valid:
            break
    quotes = []
    if certificate:
        quotes.append({"page": certificate["page"], "text": certificate["text"], "label": "NABET certificate"})
    if valid:
        quotes.append({"page": valid["page"], "text": valid["text"], "label": "Validity date"})
    if report:
        quotes.append({"page": report["page"], "text": report["text"], "label": "Report date"})
    if not certificate or not valid or not report:
        return _result(
            "accreditation", "GREY",
            "Accreditation validity could not be confirmed from readable dates; verify.",
            quotes,
            [{"label": "Method", "value": "NABET certificate, validity date and report date regex; no model call"}],
            certificate=certificate["value"] if certificate else None,
            valid_until=valid["date"].isoformat() if valid else None,
            report_date=report["date"].isoformat() if report else None,
        )
    report_date = report["date"]
    expiry = valid["date"]
    if expiry < report_date:
        grade = "ORANGE"
        message = "The certificate appears to expire before the report date; verify the applicable accreditation record."
    elif expiry <= add_months(report_date, 3):
        grade = "INFO"
        message = "The certificate appears to expire within three months of the report date; verify the applicable accreditation record."
    else:
        grade = "OK"
        message = "The readable certificate validity extends beyond three months after the report date."
    return _result(
        "accreditation", grade, message, quotes,
        [{"label": "Method", "value": "NABET certificate, validity date and report date regex; no model call"}],
        certificate=certificate["value"], valid_until=expiry.isoformat(),
        report_date=report_date.isoformat(),
    )


BASELINE_RE = re.compile(r"\b(?:baseline|monitoring|sampling|study)\b", re.I)
MONTH_DURATION_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(months?|month|seasons?)\b", re.I)


def baseline_check(pages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    pages = _page_texts(pages)
    best_unknown = None
    for p in pages:
        text = str(p.get("text") or "")
        for match in BASELINE_RE.finditer(text):
            start, end = max(0, match.start() - 120), min(len(text), match.end() + 520)
            context = text[start:end]
            tokens = date_tokens(context, allow_year=False)
            if len(tokens) >= 2:
                a, b = tokens[0], tokens[1]
                duration = period_months(a["date"], b["date"],
                                         "month" if a["precision"] == b["precision"] == "month" else "day")
                quote = _quote(text, start, end, limit=700)
                quotes = [{"page": p.get("page"), "text": quote, "label": "Baseline/monitoring period"}]
                if duration < 3:
                    return _result("baseline_season", "INFO",
                                   f"The readable baseline/monitoring period is about {duration:g} months, shorter than three months; verify.",
                                   quotes,
                                   [{"label": "Start", "value": a["date"].isoformat()},
                                    {"label": "End", "value": b["date"].isoformat()},
                                    {"label": "Method", "value": "date-range regex; no model call"}],
                                   start_date=a["date"].isoformat(), end_date=b["date"].isoformat(),
                                   duration_months=duration)
                return _result("baseline_season", "OK",
                               f"The readable baseline/monitoring period is about {duration:g} months.",
                               quotes,
                               [{"label": "Start", "value": a["date"].isoformat()},
                                {"label": "End", "value": b["date"].isoformat()},
                                {"label": "Method", "value": "date-range regex; no model call"}],
                               start_date=a["date"].isoformat(), end_date=b["date"].isoformat(),
                               duration_months=duration)
            duration_match = MONTH_DURATION_RE.search(context)
            if duration_match:
                duration = float(duration_match.group(1))
                quote = _quote(text, start, end, limit=700)
                quotes = [{"page": p.get("page"), "text": quote, "label": "Baseline/monitoring period"}]
                grade = "INFO" if duration < 3 else "OK"
                message = (f"The readable baseline/monitoring period is {duration:g} months, shorter than three months; verify."
                           if grade == "INFO" else f"The readable baseline/monitoring period is {duration:g} months.")
                return _result("baseline_season", grade, message, quotes,
                               [{"label": "Method", "value": "duration regex; no model call"}],
                               duration_months=duration)
            if best_unknown is None:
                best_unknown = (p, start, end)
    if best_unknown:
        p, start, end = best_unknown
        text = str(p.get("text") or "")
        return _result("baseline_season", "GREY",
                       "A baseline or monitoring period was mentioned, but its readable dates could not be confirmed; verify.",
                       [{"page": p.get("page"), "text": _quote(text, start, end, limit=700),
                         "label": "Baseline/monitoring context"}],
                       [{"label": "Method", "value": "date-range and duration regex; no model call"}])
    return _result("baseline_season", "GREY",
                   "A baseline or monitoring period could not be located in the readable text; verify.",
                   [], [{"label": "Method", "value": "date-range and duration regex; no model call"}])


BINOMIAL_STATUS_RE = re.compile(r"\b(?:CR|EN|VU|NT|LC|DD|EW|EX|Critically Endangered|Endangered|Vulnerable|Near Threatened|Least Concern|Data Deficient)\b", re.I)
STATUS_CODES = {"critically endangered": "CR", "endangered": "EN", "vulnerable": "VU",
                "near threatened": "NT", "least concern": "LC", "data deficient": "DD",
                "extinct in the wild": "EW", "extinct": "EX"}


def _status_near(text: str, name: str) -> tuple[str | None, str | None]:
    m = re.search(re.escape(name), text, re.I)
    if not m:
        return None, None
    snippet = text[max(0, m.start() - 30):m.end() + 150]
    status = BINOMIAL_STATUS_RE.search(snippet)
    if not status:
        return None, None
    value = status.group(0).upper()
    value = STATUS_CODES.get(status.group(0).lower(), value)
    return value, snippet


def infer_location(pages: Iterable[Mapping[str, Any]], state: str = "") -> dict[str, Any] | None:
    text = " ".join(str(p.get("text") or "") for p in pages)
    for site, point in {
        "Galathea Bay": (6.82, 93.88), "Campbell Bay": (7.00, 93.93),
        "Indira Point": (6.75, 93.83), "Great Nicobar": (7.00, 93.85),
        "Paradip": (20.27, 86.68), "Dhamra": (20.78, 86.95),
        "Ennore": (13.24, 80.32), "Tuticorin": (8.80, 78.14),
        "Mormugao": (15.42, 73.80), "Panipat": (29.39, 76.96),
    }.items():
        if re.search(re.escape(site), text, re.I):
            return {"lat": point[0], "lon": point[1], "label": site, "source": "named site"}
    centre = STATE_CENTRES.get(str(state or "").strip().lower())
    if centre:
        return {"lat": centre[0], "lon": centre[1], "label": f"{state} approximate centre",
                "source": "state-centre fallback; verify"}
    return None


def _gbif_iucn(name: str) -> str | None:
    try:
        match = species.match_name(name) or {}
    except Exception:
        return None
    value = match.get("iucnRedListCategory") or match.get("iucnCategory")
    if not value:
        return None
    value = str(value).upper().replace(" ", "_")
    return {"CRITICALLY_ENDANGERED": "CR", "ENDANGERED": "EN", "VULNERABLE": "VU",
            "NEAR_THREATENED": "NT", "LEAST_CONCERN": "LC", "DATA_DEFICIENT": "DD",
            "EXTINCT_IN_THE_WILD": "EW", "EXTINCT": "EX"}.get(value, value)


def species_check(pages: Iterable[Mapping[str, Any]], state: str = "", max_species: int = 40,
                  checker: Callable[..., dict[str, Any]] | None = None,
                  matcher: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """Run the existing GBIF grading idea on binomials, not prose guesses."""
    # species_pages imports the model-backed claims module.  Keep it lazy so
    # accreditation/baseline regex tests and the keyless app never import or
    # initialize any model client.
    from tigerfish.species_pages import NOT_GENERA, candidate_names, confirm

    pages = _page_texts(pages)
    location = infer_location(pages, state)
    if not location:
        return {"check": "species_iucn", "status": "GREY", "location": None, "rows": [], "flags": [],
                "message": "A report location could not be inferred; species range/status was not graded."}
    checker = checker or species.check_species
    matcher = matcher or confirm
    names: list[tuple[int, str, str | None, str | None]] = []
    seen: set[str] = set()
    for p in pages:
        text = str(p.get("text") or "")
        for name in candidate_names(text):
            if name in seen or len(seen) >= max_species or name.split()[0] in NOT_GENERA:
                continue
            seen.add(name)
            report_status, _ = _status_near(text, name)
            names.append((int(p.get("page") or 0), name, report_status, text))
    rows, flags = [], []
    for page, name, report_status, page_text in names:
        try:
            if matcher(name) is None:
                continue
            archipelago = (species.ANDAMAN_NICOBAR_GADM
                           if "nicobar" in state.lower() or "andaman" in state.lower() else None)
            try:
                result = checker(name, location["lat"], location["lon"],
                                 archipelago_gadm=archipelago)
            except TypeError as error:
                if "archipelago_gadm" not in str(error):
                    raise
                result = checker(name, location["lat"], location["lon"])
        except Exception as error:
            rows.append({"page": page, "name": name, "grade": "GREY", "error": str(error)[:120]})
            continue
        current_status = _gbif_iucn(name)
        range_grade = result.get("grade") if result.get("grade") in ("RED", "ORANGE") else None
        status_grade = "ORANGE" if report_status and current_status and report_status != current_status else None
        grade = "RED" if range_grade == "RED" else ("ORANGE" if range_grade == "ORANGE" or status_grade else None)
        row = {"page": page, "name": name, "matched_name": result.get("matched_name"),
               "grade": grade or "OK", "range_grade": range_grade, "report_iucn": report_status,
               "gbif_iucn": current_status, "gbif": {k: result.get(k) for k in
                   ("local_count", "regional_count", "global_count", "effort_count", "far_count")},
               "evidence": result.get("evidence", ""), "location": location}
        rows.append(row)
        if grade:
            quote_text = _quote(page_text, page_text.lower().find(name.lower()),
                                page_text.lower().find(name.lower()) + len(name))
            if status_grade and report_status and current_status:
                message = (f"The report gives {name} status {report_status}, while the cached GBIF match gives "
                           f"{current_status}; verify the assessment and date.")
            else:
                message = result.get("evidence") or f"GBIF range check for {name}; possible inconsistency flagged, verify."
            flag = {"check": "species_iucn", "grade": grade, "name": name, "page": page,
                    "title": f"{name} (p.{page})", "message": message,
                    "quotes": [{"page": page, "text": quote_text, "label": "Report species name"}],
                    "evidence": [{"label": "Checked at", "value": f"{location['label']} ({location['lat']}, {location['lon']})"},
                                 {"label": "GBIF", "value": result.get("evidence", "cached GBIF occurrence counts")},
                                 {"label": "Report / GBIF IUCN", "value": f"{report_status or 'not readable'} / {current_status or 'not available'}"}],
                    "neutral": True}
            flags.append(flag)
    return {"check": "species_iucn", "status": "OK" if rows else "GREY", "location": location,
            "rows": rows, "flags": flags,
            "message": f"Checked {len(rows)} readable binomial name(s) with cached GBIF data." if rows
                       else "No readable binomial names were confirmed with GBIF."}


def analyze_pages(pages: Iterable[Mapping[str, Any]], metadata: Mapping[str, Any] | None = None,
                  **species_kwargs: Any) -> dict[str, Any]:
    metadata = dict(metadata or {})
    # All three checks receive the same materialized page list.  This matters
    # to callers that pass read_pdf's generator rather than a list.
    page_list = _page_texts(pages)
    accreditation = accreditation_check(page_list)
    baseline = baseline_check(page_list)
    species_result = species_check(page_list, state=str(metadata.get("state") or ""), **species_kwargs)
    checks = {"accreditation": accreditation, "baseline_season": baseline,
              "species_iucn": species_result}
    flags = []
    for item in (accreditation, baseline):
        if item.get("grade") in ("RED", "ORANGE", "INFO"):
            flags.append(item)
    flags.extend(species_result.get("flags", []))
    return {"id": metadata.get("id") or metadata.get("document_id"),
            "state": metadata.get("state", ""), "project_name": metadata.get("project_name", ""),
            "url": metadata.get("url", ""), "source_page": metadata.get("source_page", ""),
            "pages": len(page_list), "checks": checks, "flags": flags,
            "status": "complete"}


def analyze_pdf(pdf_path: str | Path, metadata: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    from tigerfish.pdf_reader import read_pdf
    return analyze_pages(read_pdf(pdf_path, render=False), metadata, **kwargs)


# ---------------------------------------------------------------------------
# Tavily discovery and polite downloading


class CreditCapReached(RuntimeError):
    pass


class TavilyStats:
    def __init__(self, cap: int = MAX_TAVILY_CREDITS):
        self.cap = cap
        self.credits = 0.0
        self.cached = 0
        self.by_endpoint = {name: {"calls": 0, "cached": 0, "credits": 0.0}
                            for name in ("map", "crawl", "search", "extract")}

    @property
    def calls(self) -> int:
        return sum(v["calls"] for v in self.by_endpoint.values())

    def check(self, estimate: float) -> None:
        if self.credits + estimate > self.cap:
            raise CreditCapReached(f"Tavily cap {self.cap} credits reached ({self.credits:g} used)")

    def fresh(self, endpoint: str, credits: float) -> None:
        self.credits += credits
        self.by_endpoint[endpoint]["calls"] += 1
        self.by_endpoint[endpoint]["credits"] += credits

    def cached_call(self, endpoint: str) -> None:
        self.cached += 1
        self.by_endpoint[endpoint]["cached"] += 1

    def as_dict(self) -> dict[str, Any]:
        out = {"cap": self.cap, "calls": self.calls, "cached": self.cached,
               "credits": self.credits, "by_endpoint": self.by_endpoint}
        for endpoint, values in self.by_endpoint.items():
            out[f"{endpoint}_calls"] = values["calls"]
            out[f"{endpoint}_cached"] = values["cached"]
            out[f"{endpoint}_credits"] = values["credits"]
        return out


def _usage_credits(response: Mapping[str, Any], fallback: float) -> float:
    usage = response.get("usage") if isinstance(response, Mapping) else None
    value = usage.get("credits") if isinstance(usage, Mapping) else None
    if value is None and isinstance(response, Mapping):
        value = response.get("credits")
    return float(value) if isinstance(value, (int, float)) else fallback


def _tavily_path(endpoint: str, params: Mapping[str, Any]) -> Path:
    key = json.dumps({"endpoint": endpoint, "params": params}, sort_keys=True, default=str)
    return TAVILY_CACHE / f"batch-{hashlib.sha256(key.encode()).hexdigest()}.json"


def tavily_call(client: Any, endpoint: str, stats: TavilyStats, estimate: float = 1.0,
                **params: Any) -> dict[str, Any]:
    path = _tavily_path(endpoint, params)
    try:
        from tigerfish import trace
        trace.record("tavily", path)
    except Exception:
        pass
    if path.exists():
        stats.cached_call(endpoint)
        return json.loads(path.read_text(encoding="utf-8"))["data"]
    stats.check(estimate)
    method = getattr(client, endpoint)
    try:
        data = method(include_usage=True, **params)
    except TypeError as error:
        # Older tavily-python builds did not expose include_usage.  Retry only
        # the client-side signature failure; do not mask a remote API error.
        if "include_usage" not in str(error):
            raise
        data = method(**params)
    if not isinstance(data, dict):
        data = {"results": data}
    used = _usage_credits(data, estimate)
    stats.fresh(endpoint, used)
    _json_dump(path, {"endpoint": endpoint, "params": params, "data": data})
    return data


PDF_URL_RE = re.compile(r"https?://[^\s\"'<>\]\[()]+?\.pdf(?:\?[^\s\"'<>\]\[()]+)?", re.I)


def _is_pdf_url(url: str) -> bool:
    return urlsplit(str(url or "")).path.lower().endswith(".pdf")


def _items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [{"url": x} if isinstance(x, str) else dict(x) for x in data]
    if not isinstance(data, dict):
        return []
    values = data.get("results") or data.get("urls") or data.get("data") or []
    if isinstance(values, dict):
        values = [values]
    return [{"url": x} if isinstance(x, str) else dict(x) for x in values if isinstance(x, (str, dict))]


def _date_from_text(text: str) -> str | None:
    tokens = date_tokens(text, allow_year=False)
    return tokens[0]["date"].isoformat() if tokens else None


def _candidate_from(item: Mapping[str, Any], seed: Mapping[str, Any], source_page: str) -> dict[str, Any]:
    url = _clean_url(str(item.get("url") or item.get("link") or ""))
    title = _compact(str(item.get("title") or item.get("name") or ""))
    text = _compact(str(item.get("content") or item.get("raw_content") or item.get("markdown") or ""))
    filename = Path(urlsplit(url).path).stem.replace("_", " ").replace("-", " ")
    project = title or next((line.strip(" #-") for line in text.split(".")
                             if re.search(r"executive summary|draft EIA|environmental impact", line, re.I)), "")
    project = project[:240] or filename[:240] or "Indian EIA executive summary"
    hearing_context = text[max(0, text.lower().find("hearing") - 80):]
    return {"url": url, "state": seed.get("state", ""), "project_name": project,
            "hearing_date": _date_from_text(hearing_context) or _date_from_text(text),
            "source_page": source_page, "language": "English preferred"}


def discover_candidates(seeds: Iterable[Mapping[str, Any]] = SEEDS, max_credits: int = MAX_TAVILY_CREDITS,
                        client: Any | None = None) -> tuple[list[dict[str, Any]], TavilyStats]:
    """Discover candidate PDFs via Tavily Map and Crawl, never by scraping seeds."""
    if client is None:
        from tavily import TavilyClient
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            raise RuntimeError("TAVILY_API_KEY is missing; add it to .env for discovery")
        client = TavilyClient(api_key=key, project_id="tigerfish")
    stats = TavilyStats(max_credits)
    candidates: dict[str, dict[str, Any]] = {}
    for seed in seeds:
        seed_url = _clean_url(str(seed.get("url") or ""))
        if not seed_url:
            continue
        try:
            mapped = tavily_call(client, "map", stats, url=seed_url, max_depth=2,
                                 max_breadth=40, limit=100)
            crawled = tavily_call(client, "crawl", stats, url=seed_url, max_depth=2,
                                  max_breadth=20, limit=60,
                                  instructions="Find official public-hearing pages and PDF links for English EIA executive summaries or draft EIAs.")
        except CreditCapReached:
            break
        items = _items(mapped) + _items(crawled)
        for item in items:
            item_url = _clean_url(str(item.get("url") or item.get("link") or ""))
            content = " ".join(str(item.get(k) or "") for k in ("content", "raw_content", "markdown"))
            urls = [item_url] if _is_pdf_url(item_url) else []
            urls.extend(PDF_URL_RE.findall(content))
            for pdf_url in urls:
                pdf_url = _clean_url(urljoin(item_url or seed_url, pdf_url))
                if not pdf_url or not _is_pdf_url(pdf_url):
                    continue
                candidates.setdefault(pdf_url, _candidate_from({**item, "url": pdf_url}, seed,
                                                                 item_url or seed_url))
    return list(candidates.values()), stats


class RobotsPolicy:
    """Small robots.txt cache used by the sequential downloader."""
    def __init__(self, user_agent: str = "TigerFishBatch/1.0", request_get: Callable[..., Any] | None = None):
        self.user_agent = user_agent
        self.request_get = request_get or requests.get
        self._rules: dict[str, Any] = {}

    def allowed(self, url: str) -> bool:
        host = _host(url)
        if host in self._rules:
            return self._rules[host]
        parts = urlsplit(url)
        robots = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            response = self.request_get(robots, headers={"User-Agent": self.user_agent}, timeout=20)
            if getattr(response, "status_code", 0) in (401, 403):
                self._rules[host] = False
                return False
            if getattr(response, "status_code", 0) >= 400:
                self._rules[host] = True
                return True
            from urllib.robotparser import RobotFileParser
            parser = RobotFileParser(robots)
            parser.parse(str(getattr(response, "text", "")).splitlines())
            value = parser.can_fetch(self.user_agent, url)
        except Exception:
            # A temporarily unavailable robots file is not evidence of a
            # prohibition.  The downloader remains sequential and slow.
            value = True
        self._rules[host] = value
        return value


def _english_pdf(path: Path) -> bool:
    try:
        import pymupdf
        with pymupdf.open(path) as doc:
            text = " ".join(doc.load_page(i).get_text() for i in range(min(3, doc.page_count)))
    except Exception:
        return True
    latin = len(re.findall(r"[A-Za-z]", text))
    non_latin = len(re.findall(r"[\u0900-\u0dff\u0f00-\u0fff]", text))
    return latin >= 80 and latin >= non_latin


def _safe_stem(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value[:90] or "eia"


def download_candidates(candidates: Iterable[Mapping[str, Any]], limit: int = DEFAULT_MAX_REPORTS,
                        delay: float = DOWNLOAD_DELAY, max_bytes: int = MAX_PDF_BYTES,
                        session: requests.Session | Any | None = None,
                        robots: RobotsPolicy | None = None,
                        sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Download sequentially, respecting robots, a 60 MB limit and duplicates."""
    BATCH_DATA.mkdir(parents=True, exist_ok=True)
    old = load_index(CORPUS_INDEX)
    documents = list(old.get("documents", []))
    seen_urls = {_clean_url(d.get("url", "")) for d in documents}
    seen_hashes = {d.get("sha256") for d in documents if d.get("sha256")}
    session = session or requests.Session()
    robots = robots or RobotsPolicy()
    last_request: dict[str, float] = {}
    errors = 0
    skipped = []
    consecutive_errors = 0
    for candidate in candidates:
        if len(documents) >= limit:
            break
        url = _clean_url(str(candidate.get("url") or ""))
        if not url or url in seen_urls:
            continue
        if not robots.allowed(url):
            skipped.append({"url": url, "reason": "robots.txt disallows fetching"})
            continue
        host = _host(url)
        elapsed = time.monotonic() - last_request.get(host, 0.0)
        if elapsed < delay:
            sleep(delay - elapsed)
        last_request[host] = time.monotonic()
        temp = BATCH_DATA / ("." + hashlib.sha256(url.encode()).hexdigest() + ".part")
        try:
            response = session.get(url, headers={"User-Agent": "TigerFishBatch/1.0"},
                                   stream=True, timeout=DOWNLOAD_TIMEOUT)
            status = int(getattr(response, "status_code", 0))
            if status >= 400:
                raise IOError(f"HTTP {status}")
            announced = getattr(response, "headers", {}).get("Content-Length")
            if announced and int(announced) > max_bytes:
                skipped.append({"url": url, "reason": "PDF exceeds 60 MB"})
                continue
            total = 0
            digest = hashlib.sha256()
            with temp.open("wb") as out:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("PDF exceeds 60 MB")
                    digest.update(chunk)
                    out.write(chunk)
            if not temp.read_bytes()[:5] == b"%PDF-":
                raise ValueError("response is not a PDF")
            sha = digest.hexdigest()
            if sha in seen_hashes:
                skipped.append({"url": url, "reason": "duplicate PDF content"})
                continue
            if not _english_pdf(temp):
                skipped.append({"url": url, "reason": "non-English PDF preferred duplicate"})
                continue
            stem = _safe_stem(str(candidate.get("project_name") or Path(urlsplit(url).path).stem))
            target = BATCH_DATA / f"{stem}-{sha[:10]}.pdf"
            temp.replace(target)
            entry = {**dict(candidate), "url": url,
                     "document_id": sha[:16], "filename": target.name,
                     "local_path": str(target.relative_to(ROOT)), "sha256": sha, "bytes": total}
            documents.append(entry)
            seen_urls.add(url)
            seen_hashes.add(sha)
            consecutive_errors = 0
        except Exception as error:
            errors += 1
            consecutive_errors += 1
            skipped.append({"url": url, "reason": str(error)[:200]})
            if temp.exists():
                temp.unlink()
            if consecutive_errors >= MAX_CONSECUTIVE_DOWNLOAD_ERRORS:
                break
    index = {"version": 1, "documents": documents, "skipped": skipped,
             "downloaded": len(documents), "max_bytes": max_bytes}
    _json_dump(CORPUS_INDEX, index)
    _json_dump(PUBLIC_CORPUS_INDEX, public_index(index))
    return index


def load_index(path: str | Path = CORPUS_INDEX) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"version": 1, "documents": [], "skipped": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 1, "documents": [], "skipped": []}
    except (OSError, ValueError):
        return {"version": 1, "documents": [], "skipped": []}


def public_index(index: Mapping[str, Any]) -> dict[str, Any]:
    public_docs = []
    for doc in index.get("documents", []):
        public_docs.append({k: v for k, v in dict(doc).items() if k not in ("local_path", "filename")})
    return {"version": index.get("version", 1), "documents": public_docs,
            "downloaded": len(public_docs), "notes": "Local PDF paths are intentionally omitted."}


# ---------------------------------------------------------------------------
# Batch orchestration and reporting


def _state_counts(reports: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        state = str(report.get("state") or "Unknown")
        counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def _flag_counts(flags: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {grade: 0 for grade in ("RED", "ORANGE", "INFO", "GREY", "OK")}
    for flag in flags:
        grade = str(flag.get("grade") or "GREY")
        counts[grade] = counts.get(grade, 0) + 1
    return {k: v for k, v in counts.items() if v or k in ("RED", "ORANGE", "INFO")}


def _tool_version() -> str:
    """Return the source revision without making the batch depend on git."""
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        value = result.stdout.strip()
        if value:
            return value
    except (OSError, subprocess.SubprocessError):
        pass
    return "batch-free-checks"


def _sector_for(project: str) -> str:
    text = str(project or "").lower()
    choices = (
        ("Ports and harbours", ("port", "jetty", "harbour", "harbor", "berth")),
        ("Airports", ("airport", "air strip", "aerodrome")),
        ("Highways and roads", ("highway", "road", "corridor")),
        ("Railways", ("railway", "rail line", "metro")),
        ("Mining", ("mine", "mining", "quarry")),
        ("Thermal power", ("thermal power", "power plant")),
        ("Hydro power", ("hydro power", "hydroelectric")),
        ("Industrial projects", ("industrial", "manufacturing", "steel plant")),
    )
    for sector, words in choices:
        if any(word in text for word in words):
            return sector
    return "Other"


def _year_from_report(report: Mapping[str, Any]) -> int | None:
    for value in (report.get("hearing_date"), report.get("checks", {}).get("accreditation", {}).get("report_date")):
        match = re.search(r"(?:19|20)\d{2}", str(value or ""))
        if match:
            return int(match.group(0))
    return None


def _quick_check(check: str, name: str, status: str, count: int | None = None,
                 reason: str | None = None) -> dict[str, Any]:
    item = {"check": check, "name": name, "status": status}
    if count is not None:
        item["count"] = count
    if reason:
        item["reason"] = reason
    return item


def _quick_findings(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Map the batch species flags into the library's four-check vocabulary.

    Accreditation and baseline are deliberately retained in ``batch_flags`` and the
    aggregate summary.  They are local batch checks, not one of the library's four
    standard upload checks, so putting them in ``findings`` would make the report
    invalid and hide the whole report from the library.
    """
    findings = []
    flags = [f for f in report.get("flags", []) if f.get("check") == "species_iucn"]
    if not flags:
        flags = list((report.get("checks", {}).get("species_iucn") or {}).get("flags", []))
    for number, original in enumerate(flags, 1):
        if original.get("check") != "species_iucn" or original.get("grade") not in ("RED", "ORANGE"):
            continue
        check = "iucn_status" if original.get("report_iucn") and original.get("gbif_iucn") \
            and original.get("report_iucn") != original.get("gbif_iucn") else "species_range"
        fid = str(original.get("id") or f"{check[:2]}-{number:03d}")
        quotes = [{"page": q.get("page"), "text": q.get("text", "")}
                  for q in original.get("quotes", [])]
        evidence = list(original.get("evidence") or [])
        findings.append({
            "id": fid,
            "check": check,
            "check_name": "IUCN status" if check == "iucn_status" else "Species out of range",
            "grade": original["grade"],
            "title": original.get("title") or str(original.get("name") or "Species check"),
            "message": original.get("message") or "A possible species inconsistency was flagged; verify.",
            "quotes": quotes,
            "evidence": evidence,
            "why": original.get("message") or "The free GBIF check found a possible inconsistency; verify.",
            "clear": "A dated local record or the report's cited assessment that resolves the difference.",
            "known_issue": None,
            "images": [],
        })
    return findings


def _quick_report(report: Mapping[str, Any], generated: str | None = None) -> dict[str, Any]:
    """Build a library-compatible report and retain the batch-only evidence fields."""
    checks = dict(report.get("checks") or {})
    species_result = checks.get("species_iucn") or {}
    species_ran = species_result.get("status") == "OK" and bool(species_result.get("rows"))
    species_flags = _quick_findings(report)
    iucn_count = sum(1 for row in species_result.get("rows", []) if row.get("report_iucn"))
    location = species_result.get("location")
    site = None
    if location:
        site = {"lat": location.get("lat"), "lon": location.get("lon"),
                "how": location.get("source", "text search"), "page": None, "quote": None}
    generated = generated or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    batch_checks = {}
    for name, value in checks.items():
        # Page text is never stored in a result.  The compact rows and the quoted flags
        # are enough for replay and review while keeping each report below 200 KB.
        batch_checks[name] = {k: v for k, v in value.items() if k != "flags"}
    report_id = str(report.get("id") or "eia")
    quick = {
        "format": "tigerfish-report/1",
        "id": report_id,
        "audit_type": "quick",
        "title": report.get("project_name") or report_id,
        "project": report.get("project_name") or report_id,
        "state": report.get("state") or None,
        "sector": _sector_for(str(report.get("project_name") or "")),
        "year": _year_from_report(report),
        "consultant": None,
        "source": {"url": report.get("url") or None, "portal": report.get("source_page") or None,
                   "proposal_no": None},
        "pages_total": int(report.get("pages") or 0),
        "pages_read": int(report.get("pages") or 0),
        "site": site,
        "checks_run": [
            _quick_check("number_pair", "Number pairs (rule, free)", "not_available",
                         reason="This batch run was scoped to accreditation, baseline and species checks."),
            _quick_check("species_range", "Species in the report's tables vs GBIF (free)",
                         "ran" if species_ran else "not_available",
                         count=len(species_result.get("rows", [])) if species_ran else None,
                         reason=None if species_ran else species_result.get("message", "No readable binomial names were confirmed.")),
            _quick_check("iucn_status", "IUCN categories vs GBIF (free)",
                         "ran" if species_ran else "not_available", count=iucn_count if species_ran else None,
                         reason=None if species_ran else species_result.get("message", "No readable binomial names were confirmed.")),
            _quick_check("omission", "Threatened species near the site not mentioned (GBIF, free)",
                         "not_available", reason="Omission checks were outside this batch run's scope."),
        ],
        "findings": species_flags,
        "cost": {"nebius_usd": 0, "tavily_credits": 0,
                 "gbif_calls": len(species_result.get("rows", [])), "approx_seconds": 0},
        "generated": generated,
        "tool_version": _tool_version(),
        # These fields are ignored by the library validator but are used by the
        # batch summary and keep the requested accreditation/baseline evidence public.
        "batch_checks": batch_checks,
        "batch_flags": list(report.get("flags", [])),
        "project_name": report.get("project_name", ""),
        "url": report.get("url", ""),
        "source_page": report.get("source_page", ""),
        "checks": batch_checks,
        "flags": list(report.get("flags", [])),
    }
    return quick


def make_summary(reports: Iterable[Mapping[str, Any]], tavily: Mapping[str, Any] | None = None) -> dict[str, Any]:
    reports = list(reports)
    flags = []
    check_counts: dict[str, dict[str, int]] = {}
    for report in reports:
        for name, result in (report.get("checks") or {}).items():
            check_counts.setdefault(name, {})[result.get("grade", result.get("status", "GREY"))] = \
                check_counts.setdefault(name, {}).get(result.get("grade", result.get("status", "GREY")), 0) + 1
        for flag in report.get("flags", []):
            flags.append({"report_id": report.get("id"), "state": report.get("state"),
                          "project_name": report.get("project_name"), **dict(flag)})
    return {"version": 1, "status": "complete", "reports_processed": len(reports),
            "reports_requested": DEFAULT_MAX_REPORTS, "per_check_counts": check_counts,
            "per_state_counts": _state_counts(reports), "flag_counts": _flag_counts(flags),
            "tavily": dict(tavily or {"cap": MAX_TAVILY_CREDITS, "calls": 0, "cached": 0,
                                      "credits": 0, "by_endpoint": {}}),
            "flags": flags,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "neutral_note": "Flags are leads for verification; they are not conclusions about intent or compliance."}


def summary_markdown(summary: Mapping[str, Any]) -> str:
    lines = ["# TigerFish batch summary", "",
             "Free, no-model checks over Indian EIA executive summaries. Flags are neutral leads for verification.", "",
             f"Reports processed: **{summary.get('reports_processed', 0)}**", "",
             "## Checks", "", "| Check | Grade/status counts |", "|---|---|"]
    for check, counts in sorted((summary.get("per_check_counts") or {}).items()):
        lines.append(f"| {check} | " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) + " |")
    lines += ["", "## States", "", "| State | Reports |", "|---|---:|"]
    for state, count in (summary.get("per_state_counts") or {}).items():
        lines.append(f"| {state} | {count} |")
    lines += ["", "## Tavily", "",
              f"Calls: {summary.get('tavily', {}).get('calls', 0)}; "
              f"cached calls: {summary.get('tavily', {}).get('cached', 0)}; "
              f"credits: {summary.get('tavily', {}).get('credits', 0)} / {summary.get('tavily', {}).get('cap', MAX_TAVILY_CREDITS)}.", "",
              "| Grade | State | Project | Check | Page | Quote | Message |", "|---|---|---|---|---:|---|---|"]
    for flag in summary.get("flags", []):
        quotes = flag.get("quotes") or []
        quote = "<br>".join(f"p.{q.get('page')}: {_compact(q.get('text'))}" for q in quotes)
        lines.append("| {grade} | {state} | {project} | {check} | {page} | {quote} | {message} |".format(
            grade=flag.get("grade", ""), state=_compact(flag.get("state")),
            project=_compact(flag.get("project_name")), check=flag.get("check", ""),
            page=", ".join(str(q.get("page")) for q in quotes if q.get("page")),
            quote=quote.replace("|", "\\|"), message=_compact(flag.get("message"))))
    if not summary.get("flags"):
        lines.append("| — | — | No flags yet | — | — | — | Run the batch command with a Tavily key and downloaded corpus. |")
    return "\n".join(lines) + "\n"


def run_batch(index: Mapping[str, Any] | None = None, max_reports: int = DEFAULT_MAX_REPORTS,
              tavily: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    index = dict(index or load_index())
    reports = []
    report_items = []
    for doc in index.get("documents", [])[:max_reports]:
        local_path = doc.get("local_path")
        path = ROOT / local_path if local_path and not Path(local_path).is_absolute() else Path(local_path or "")
        if not path.exists() or path.suffix.lower() != ".pdf":
            continue
        report_id = str(doc.get("document_id") or hashlib.sha256(str(path).encode()).hexdigest()[:16])
        cached = REPORT_RESULTS / f"{report_id}.json"
        if cached.exists():
            try:
                quick = json.loads(cached.read_text(encoding="utf-8"))
                # The extra batch fields make a cached public report sufficient to
                # regenerate the aggregate summary without reopening the PDF.
                report = {"id": quick.get("id", report_id),
                          "state": quick.get("state", ""),
                          "project_name": quick.get("project_name") or quick.get("project", ""),
                          "checks": quick.get("batch_checks") or quick.get("checks", {}),
                          "flags": quick.get("batch_flags") or quick.get("flags", [])}
                reports.append(report)
                report_items.append({"id": quick.get("id", report_id), "file": cached.name})
                continue
            except (OSError, ValueError):
                pass
        report = analyze_pdf(path, {**doc, "id": report_id}, **kwargs)
        quick = _quick_report(report)
        _json_dump(cached, quick)
        reports.append(report)
        report_items.append({"id": report_id, "file": cached.name})
    summary = make_summary(reports, tavily=tavily)
    summary["reports_requested"] = max_reports
    _json_dump(SUMMARY_JSON, summary)
    SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_MD.write_text(summary_markdown(summary), encoding="utf-8")
    _json_dump(PUBLIC_CORPUS_INDEX, public_index(index))
    _json_dump(QUICK_INDEX, {"format": "tigerfish-report/1",
                             "generated": summary["generated_at"],
                             "tool_version": _tool_version(), "reports": report_items})
    return summary


def initialize_public_results() -> None:
    """Create keyless, empty schemas for replay mode and the report library."""
    if not PUBLIC_CORPUS_INDEX.exists():
        _json_dump(PUBLIC_CORPUS_INDEX, public_index({"version": 1, "documents": []}))
    if not SUMMARY_JSON.exists():
        summary = make_summary([], tavily={"cap": MAX_TAVILY_CREDITS, "calls": 0, "cached": 0,
                                           "credits": 0, "by_endpoint": {name: {"calls": 0, "cached": 0, "credits": 0}
                                                                            for name in ("map", "crawl", "search", "extract")}})
        summary["status"] = "not_run"
        summary["neutral_note"] = "No corpus run is committed. Run scripts/build_corpus.py with the Tavily credential set."
        _json_dump(SUMMARY_JSON, summary)
        SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_MD.write_text(summary_markdown(summary), encoding="utf-8")
    if not QUICK_INDEX.exists():
        _json_dump(QUICK_INDEX, {"format": "tigerfish-report/1",
                                 "generated": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                                 "tool_version": _tool_version(), "reports": []})
