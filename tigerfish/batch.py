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
from datetime import date, datetime, timedelta, timezone
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
        return date(year, month, day)
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
    # Inclusive end: Feb 1-Apr 30 is three calendar months, not 89/30.4375.
    stop = end + timedelta(days=1)
    whole = (stop.year - start.year) * 12 + stop.month - start.month
    if add_months(start, whole) > stop:
        whole -= 1
    anniversary = add_months(start, whole)
    next_anniversary = add_months(start, whole + 1)
    return round(
        whole + (stop - anniversary).days / (next_anniversary - anniversary).days, 2
    )


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
_MONTH_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
MONTH_DURATION_RE = re.compile(
    r"\b(?:for|over|during|of|lasting)\s+(?:a\s+(?:period|duration)\s+of\s+)?"
    r"(?P<n>\d+(?:\.\d+)?|" + "|".join(_MONTH_NUMBERS) + r")\s+months?\b",
    re.I,
)
_DATE_ATOM = (
    rf"(?:\d{{4}}[./-]\d{{1,2}}[./-]\d{{1,2}}|"
    rf"\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{2,4}}|"
    rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH_WORDS}[, ]+\d{{4}}|"
    rf"{MONTH_WORDS}\s+\d{{1,2}}(?:st|nd|rd|th)?[, ]+\d{{4}}|"
    rf"{MONTH_WORDS}\s+\d{{4}})"
)
_RANGE_SEP = r"\s*(?:to|until|through|[-–—])\s*"
_FULL_RANGE = re.compile(
    rf"(?<![\w/])(?P<a>{_DATE_ATOM}){_RANGE_SEP}(?P<b>{_DATE_ATOM})(?![\w/])", re.I
)
_MONTH_RANGE = re.compile(
    rf"\b(?P<sm>{MONTH_WORDS})(?:\s+(?P<sy>\d{{4}}))?{_RANGE_SEP}"
    rf"(?P<em>{MONTH_WORDS})\s+(?P<ey>\d{{4}})\b",
    re.I,
)
_DAY_RANGE = re.compile(
    rf"\b(?P<sd>\d{{1,2}})(?:st|nd|rd|th)?{_RANGE_SEP}"
    rf"(?P<ed>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<m>{MONTH_WORDS})\s+(?P<y>\d{{4}})\b",
    re.I,
)
_FIELDWORK = re.compile(
    r"\b(?:baseline|monitoring|sampling|study\s+period|field\s+(?:survey|studies)|ecolog\w*)\b",
    re.I,
)
_NOT_BASELINE = re.compile(
    r"\b(?:traffic|vehicul\w*|application|applied|submitted|submission|EAC|SEAC|committee|"
    r"ToR|terms of reference|grant(?:ed)?|certificate|validity|hearing|report\s+(?:date|no\.?|number))\b",
    re.I,
)
_FUTURE = re.compile(
    r"\b(?:will|shall)\b|\b(?:proposed|planned)\s+(?:monitoring|sampling|study)", re.I
)
_FREQUENCY = re.compile(r"\b(?:every|frequency|intervals?|once\s+(?:in|per))\b", re.I)


def _baseline_ranges(text: str) -> list[dict[str, Any]]:
    """Explicit ranges only. Dates in report IDs or unrelated sentences are not paired."""
    out = []
    occupied = []
    for pattern in (_FULL_RANGE, _MONTH_RANGE, _DAY_RANGE):
        for match in pattern.finditer(text):
            if any(match.start() < b and match.end() > a for a, b in occupied):
                continue
            occupied.append(match.span())
            if pattern is _FULL_RANGE:
                a, b = parse_date_token(match["a"]), parse_date_token(match["b"])
                if not a or not b or a[1] != b[1]:
                    continue
                start, end, precision = a[0], b[0], a[1]
            elif pattern is _MONTH_RANGE:
                sm, em, ey = (
                    MONTHS[match["sm"].lower()],
                    MONTHS[match["em"].lower()],
                    int(match["ey"]),
                )
                sy = int(match["sy"]) if match["sy"] else ey - int(sm > em)
                start, end, precision = _safe_date(sy, sm), _safe_date(ey, em), "month"
            else:
                y, m = int(match["y"]), MONTHS[match["m"].lower()]
                start, end, precision = (
                    _safe_date(y, m, int(match["sd"])),
                    _safe_date(y, m, int(match["ed"])),
                    "day",
                )
            if start is None or end is None or end < start:
                continue
            out.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "precision": precision,
                    "duration_months": period_months(start, end, precision),
                }
            )
    return sorted(out, key=lambda x: x["start"])


def _baseline_context(text: str, start: int, end: int) -> tuple[str, str]:
    # Keep PDF line wraps, but do not borrow a keyword from the preceding sentence.
    before = re.split(r"[.;!?]\s+", text[max(0, start - 220) : start])[-1]
    after = re.split(r"[.;!?]\s+", text[end : end + 120])[0]
    return before, _compact(before + text[start:end] + after)


def _baseline_topic(text: str) -> str:
    for topic, pattern in (
        ("terrestrial ecology", r"terrestrial|flora|fauna|biodiversity"),
        ("marine ecology", r"marine|coral|turtle"),
        ("air", r"\bair\b|meteorolog"),
        ("water", r"\bwater\b"),
        ("soil", r"\bsoil\b"),
        ("noise", r"\bnoise\b"),
    ):
        if re.search(pattern, text, re.I):
            return topic
    return "baseline"


def baseline_check(pages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Screen stated fieldwork periods, not compliance with an assumed universal ToR."""
    periods, unknown = [], None
    for p in pages:
        text = _compact(str(p.get("text") or ""))
        ranges = _baseline_ranges(text)
        candidates = list(ranges)
        for match in MONTH_DURATION_RE.finditer(text):
            n = match["n"].lower()
            duration = _MONTH_NUMBERS[n] if n in _MONTH_NUMBERS else float(n)
            candidates.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "duration_months": duration,
                    "precision": "stated months",
                }
            )
        for candidate in sorted(candidates, key=lambda x: x["start"]):
            before, quote = _baseline_context(
                text, candidate["start"], candidate["end"]
            )
            if (
                not _FIELDWORK.search(before)
                or _NOT_BASELINE.search(before)
                or _FUTURE.search(before)
            ):
                continue
            if _FREQUENCY.search(before):
                continue
            periods.append(
                {k: v for k, v in candidate.items() if k not in ("start", "end")}
                | {
                    "page": p.get("page"),
                    "quote": quote,
                    "topic": _baseline_topic(before),
                }
            )
        if unknown is None and (match := BASELINE_RE.search(text)):
            unknown = {
                "page": p.get("page"),
                "text": _quote(text, match.start(), match.end()),
                "label": "Baseline/monitoring context",
            }
    # Repeated evidence remains quotable, but must not create a false conflict.
    unique = {
        (
            p["topic"],
            p.get("start_date"),
            p.get("end_date"),
            p["duration_months"],
            p["page"],
        ): p
        for p in periods
    }
    periods = list(unique.values())
    quotes = [
        {"page": p["page"], "text": p["quote"], "label": f"{p['topic']}: stated period"}
        for p in periods
    ]
    method = [
        {
            "label": "Method",
            "value": "explicit fieldwork ranges and calendar months; no model call",
        },
        {
            "label": "Reference",
            "value": "Three months is a screening reference, not a verified project requirement.",
        },
    ]
    extra = {"periods": periods, "reference_months": 3, "requirement_verified": False}
    if not periods:
        return _result(
            "baseline_season",
            "GREY",
            "A baseline fieldwork period could not be established from readable text; verify.",
            [unknown] if unknown else [],
            method,
            **extra,
        )
    topics = {p["topic"] for p in periods}
    if any(
        len({p["duration_months"] for p in periods if p["topic"] == topic}) > 1
        for topic in topics
    ):
        return _result(
            "baseline_season",
            "GREY",
            "Different periods are stated for the same baseline topic; their relationship needs review.",
            quotes,
            method,
            **extra,
        )
    shortest = min(periods, key=lambda p: p["duration_months"])
    duration = shortest["duration_months"]
    grade = "INFO" if duration < 3 else "OK"
    message = (
        f"The stated {shortest['topic']} period is {duration:g} calendar months, below the three-month screening reference. Compare with the applicable ToR; no requirement was verified."
        if grade == "INFO"
        else "The extracted baseline periods meet the three-month screening reference. This does not establish compliance or complete study coverage."
    )
    return _result(
        "baseline_season",
        grade,
        message,
        quotes,
        method,
        **{k: shortest[k] for k in ("start_date", "end_date") if k in shortest},
        duration_months=duration,
        **extra,
    )




PROPOSAL_NO_RE = re.compile(r'(?:IA|SIA)/[A-Z]{2}/[A-Z0-9/_-]+')
COURT_DOMAINS = ('greentribunal.gov.in', 'ecourts.gov.in', 'sci.gov.in')
GENERIC_PROJECT_NAMES = {
    'executive summary', 'draft eia', 'draft eia report', 'environmental impact assessment',
    'executive summary (english)', 'executive summary report', 'resubmission',
    'maharashtra pollution control board', 'the hazardous and other wastes',
    'the noise pollution regulation and control rules 2000'
}


def _clean_project_name(name: str) -> str:
    cleaned = _compact(name).strip(' -:#\n\r')
    if cleaned.lower() in GENERIC_PROJECT_NAMES or cleaned.lower().startswith('executive summary of environmental impact'):
        return ''
    cleaned = re.sub(r'^(?:executive summary\s*(?:of|for)?\s*)+', '', cleaned, flags=re.I).strip(' -:#')
    return cleaned[:120]


def extract_proposal_and_project(pages: Iterable[Mapping[str, Any]],
                                metadata: Mapping[str, Any] | None = None) -> tuple[str | None, str, int, str]:
    """Extract (proposal_no, project_name, page_no, quote_text) from the first 3 pages."""
    proposal_no = None
    proposal_page = 1
    quote_text = ''
    pages_list = list(pages)
    first_pages = [p for p in pages_list if int(p.get('page', 0) or 0) <= 3]
    if not first_pages and pages_list:
        first_pages = pages_list[:3]

    for p in first_pages:
        text = str(p.get('text') or '')
        match = PROPOSAL_NO_RE.search(text)
        if match:
            proposal_no = match.group(0).strip('.,;:()')
            proposal_page = int(p.get('page', 1) or 1)
            quote_text = _quote(text, match.start(), match.end())
            break

    meta = dict(metadata or {})
    if not proposal_no:
        for q in meta.get('batch_checks', {}).get('accreditation', {}).get('quotes', []):
            m = PROPOSAL_NO_RE.search(q.get('text', ''))
            if m:
                proposal_no = m.group(0).strip('.,;:()')
                proposal_page = int(q.get('page', 1) or 1)
                quote_text = q.get('text', '')
                break

    project_name = _clean_project_name(str(meta.get('project_name') or meta.get('title') or meta.get('project') or ''))
    if not project_name:
        for p in first_pages:
            text = str(p.get('text') or '')
            m = re.search(r'(?:M/s\.?|Project Proponent\s*:?|Proposed\s+)([A-Z0-9\s,&.-]{4,80})', text, re.I)
            if m:
                candidate = _clean_project_name(m.group(0))
                if candidate:
                    project_name = candidate
                    if not quote_text:
                        proposal_page = int(p.get('page', 1) or 1)
                        quote_text = _quote(text, m.start(), m.end())
                    break

    if not quote_text:
        if proposal_no:
            quote_text = f'Proposal number: {proposal_no}'
        elif project_name:
            quote_text = f'Project: {project_name}'
        else:
            quote_text = 'Project reference'

    return proposal_no, project_name, proposal_page, quote_text


def _is_court_docket_url(url: str, title: str = '', content: str = '') -> bool:
    u = url.lower()
    t = (title + ' ' + content).lower()
    if any(dom in u for dom in COURT_DOMAINS):
        return True
    if 'indiankanoon.org' in u and any(kw in t for kw in ('green tribunal', 'ngt', 'tribunal', 'court', 'order', 'judgment')):
        return True
    return False


def public_record_check(pages: Iterable[Mapping[str, Any]],
                        metadata: Mapping[str, Any] | None = None,
                        client: Any | None = None,
                        stats: TavilyStats | None = None) -> dict[str, Any]:
    """Public record / litigation check via Tavily search for NGT / court dockets."""
    pages = _page_texts(pages)
    proposal_no, project_name, exact_page, quote_text = extract_proposal_and_project(pages, metadata)

    if proposal_no and project_name:
        query = f'"{proposal_no}" OR "{project_name}" site:greentribunal.gov.in OR "National Green Tribunal" OR "stay order" OR penalty'
    elif proposal_no:
        query = f'"{proposal_no}" site:greentribunal.gov.in OR "National Green Tribunal" OR "stay order" OR penalty'
    elif project_name:
        query = f'"{project_name}" site:greentribunal.gov.in OR "National Green Tribunal" OR "stay order" OR penalty'
    else:
        return _result('public_record', 'GREY', 'No proposal number or project name available to search.',
                       quotes=[], evidence=[], proposal_no=None, project_name='')

    if stats is None:
        stats = TavilyStats()

    data = None
    params = {'query': query, 'max_results': 5}
    path = _tavily_path('search', params)
    if path.exists():
        data = tavily_call(client, 'search', stats, **params)
    else:
        if client is None:
            key = os.getenv('TAVILY_API_KEY')
            if key:
                try:
                    from tavily import TavilyClient
                    client = TavilyClient(api_key=key)
                except Exception:
                    pass
        if client is not None:
            try:
                data = tavily_call(client, 'search', stats, **params)
            except Exception as e:
                return _result('public_record', 'GREY', f'Tavily search error: {str(e)[:120]}',
                               quotes=[{'page': exact_page, 'text': quote_text, 'label': 'Proposal / project reference'}],
                               evidence=[{'label': 'Method', 'value': 'Tavily search over tribunal and court dockets; no model call'}],
                               proposal_no=proposal_no, project_name=project_name, page=exact_page)
        else:
            return _result('public_record', 'GREY', 'Tavily search skipped: no cache and TAVILY_API_KEY not set.',
                           quotes=[{'page': exact_page, 'text': quote_text, 'label': 'Proposal / project reference'}],
                           evidence=[{'label': 'Method', 'value': 'Tavily search over tribunal and court dockets; no model call'}],
                           proposal_no=proposal_no, project_name=project_name, page=exact_page)

    results = (data or {}).get('results') or []
    matched_item = None
    for item in results:
        url = str(item.get('url') or item.get('link') or '')
        title = str(item.get('title') or '')
        content = str(item.get('content') or '')
        if _is_court_docket_url(url, title, content):
            matched_item = item
            break

    quotes = [{'page': exact_page, 'text': quote_text, 'label': 'Proposal / project reference'}]
    if matched_item:
        court_url = matched_item.get('url') or matched_item.get('link')
        evidence = [
            {'label': 'Matched court URL', 'value': court_url, 'url': court_url},
            {'label': 'Method', 'value': 'Tavily search over tribunal and court dockets; no model call'},
        ]
        return _result('public_record', 'INFO', 'Prior tribunal docket indexed; verify status.',
                       quotes=quotes, evidence=evidence,
                       proposal_no=proposal_no, project_name=project_name, page=exact_page,
                       court_url=court_url, docket_title=matched_item.get('title', ''))

    evidence = [
        {'label': 'Method', 'value': 'Tavily search over tribunal and court dockets; no model call'},
    ]
    return _result('public_record', 'OK', 'No prior tribunal or court dockets indexed.',
                   quotes=quotes, evidence=evidence,
                   proposal_no=proposal_no, project_name=project_name, page=exact_page)


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
                  client: Any | None = None, stats: TavilyStats | None = None,
                  **species_kwargs: Any) -> dict[str, Any]:
    metadata = dict(metadata or {})
    # All four checks receive the same materialized page list.  This matters
    # to callers that pass read_pdf's generator rather than a list.
    page_list = _page_texts(pages)
    accreditation = accreditation_check(page_list)
    baseline = baseline_check(page_list)
    species_result = species_check(page_list, state=str(metadata.get("state") or ""), **species_kwargs)
    public_rec = public_record_check(page_list, metadata=metadata, client=client, stats=stats)
    checks = {"accreditation": accreditation, "baseline_season": baseline,
              "species_iucn": species_result, "public_record": public_rec}
    flags = []
    for item in (accreditation, baseline, public_rec):
        if item.get("grade") in ("RED", "ORANGE", "INFO"):
            flags.append(item)
    flags.extend(species_result.get("flags", []))
    return {"id": metadata.get("id") or metadata.get("document_id"),
            "state": metadata.get("state", ""), "project_name": metadata.get("project_name", ""),
            "url": metadata.get("url", ""), "source_page": metadata.get("source_page", ""),
            "pages": len(page_list), "checks": checks, "flags": flags,
            "status": "complete"}


def analyze_pdf(pdf_path: str | Path, metadata: Mapping[str, Any] | None = None,
                client: Any | None = None, stats: TavilyStats | None = None,
                **kwargs: Any) -> dict[str, Any]:
    from tigerfish.pdf_reader import read_pdf
    return analyze_pages(read_pdf(pdf_path, render=False), metadata, client=client, stats=stats, **kwargs)


# ---------------------------------------------------------------------------
# Deterministic cross-state consultant overlap and credential sharing checks
# ---------------------------------------------------------------------------

CONSULTANT_PATTERNS = [
    re.compile(
        r"(?:EIA\s+Consultant|Prepared\s+by|Environmental\s+Consultant|Name\s+of\s+(?:the\s+)?Consultant|Consultant\s*:|M/s\.?\s+Consultant)\s*[:\-–]?\s*"
        r"(?:Name\s*[:\-–]?\s*)?"
        r"([A-Za-z0-9\., &\'\(\)\-]{3,70})",
        re.I,
    ),
    re.compile(r"([A-Za-z0-9\., &\'\-]{3,60})\s*\((?:NABET|QCI)", re.I),
    re.compile(
        r"(?:M/s\.?)\s*([A-Za-z0-9\., &\'\-]{3,60}?(?:Enviro|Consultant|Services|Solutions|Tech|Laboratories|Laboratory|Research|Engineers|Private Limited|Pvt\.?\s*Ltd\.?))",
        re.I,
    ),
    re.compile(r"NABET.*?QCI[^\n]*\n\s*([A-Za-z0-9\., &\'\-]{3,60})", re.I),
]

DISTRICT_RE = re.compile(
    r"\b(?:District|Dist\.?|Taluka|Tahsil|Tehsil)\s*[:\-–]?\s*([A-Za-z]{3,25})",
    re.I,
)

CLEAN_CONSULTANT_STOP = (
    "environmental", "impact", "assessment", "executive", "summary", "report",
    "table", "chapter", "draft", "project", "proponent", "mining", "tor", "date"
)


def _clean_consultant(val: str) -> str | None:
    val = val.strip(" \t\n\r,.:;-")
    low = val.lower()
    if len(val) >= 4 and not any(low.startswith(w) for w in CLEAN_CONSULTANT_STOP):
        val = re.sub(r"\s+(?:dated|valid|certificate|accredited|qci|nabet).*$", "", val, flags=re.I).strip(" ,.:;-")
        if len(val) >= 4:
            return val
    return None


def extract_consultant_name(text: str) -> str | None:
    for pat in CONSULTANT_PATTERNS:
        for m in pat.finditer(text):
            cleaned = _clean_consultant(m.group(1))
            if cleaned:
                return cleaned
    return None


def _norm_cert(cert: str | None) -> str | None:
    if not cert:
        return None
    c = cert.strip().upper()
    c = re.sub(r"\s*/\s*", "/", c)
    c = re.sub(r"\s*-\s*", "-", c)
    c = re.sub(r"\s+", "", c)
    return c if len(c) >= 5 else None


def _norm_consultant(name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip().upper()
    n = re.sub(r"^(?:M/S\.?|NAME\s+OF\s+(?:THE\s+)?CONSULTANT\s*:?|PREPARED\s+BY\s*:?|CONSULTANT\s*:?)\s*", "", n)
    n = re.sub(
        r"\b(PRIVATE LIMITED|PVT\.?\s*LTD\.?|LIMITED|LTD\.?|INC\.?|LLC|CORP\.?|CO\.?|SERVICES|LABORATORIES|LABORATORY|CONSULTANCY|CONSULTANTS|SOLUTIONS|ENGINEERS|ENVIRO|TECH|PROJECTS)\b",
        "",
        n,
    )
    n = re.sub(r"\b(BHUBANESWAR|BBSR|MUMBAI|PUNE|DELHI|CHENNAI|KOLKATA|HYDERABAD|NAGPUR|VADODARA|GUJARAT)\b", "", n)
    n = re.sub(r"[^A-Z0-9]", "", n)
    return n if len(n) >= 3 else None


def _extract_district(text: str) -> str | None:
    m = DISTRICT_RE.search(text)
    if m:
        dist = m.group(1).strip(" ,.:;-")
        if len(dist) >= 3 and dist.lower() not in ("the", "and", "for", "proposed", "area"):
            return dist.title()
    return None


def _parse_dates(start_val: Any, end_val: Any) -> tuple[date | None, date | None]:
    if not start_val or not end_val:
        return None, None
    try:
        if isinstance(start_val, str):
            d1 = date.fromisoformat(start_val)
        elif isinstance(start_val, date):
            d1 = start_val
        else:
            return None, None
        if isinstance(end_val, str):
            d2 = date.fromisoformat(end_val)
        elif isinstance(end_val, date):
            d2 = end_val
        else:
            return None, None
        return min(d1, d2), max(d1, d2)
    except (ValueError, TypeError):
        return None, None


def check_cross_state_consultant_overlap(batch_reports: list[dict] | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic, zero-token check for cross-state consultant timeline overlaps and credential sharing."""
    items = []
    for rep in batch_reports:
        rep_id = str(rep.get("id") or rep.get("document_id") or "")
        state = str(rep.get("state") or "").strip()
        proj = str(rep.get("project_name") or rep.get("project") or rep.get("title") or rep_id).strip()
        checks = rep.get("batch_checks") or rep.get("checks") or {}
        acc = checks.get("accreditation") or {}
        base = checks.get("baseline_season") or {}

        cert = acc.get("certificate")
        consultant = rep.get("consultant")

        # Collect quotes text for extraction fallback
        all_quotes = []
        for c_val in checks.values():
            if isinstance(c_val, dict):
                for q in c_val.get("quotes", []):
                    all_quotes.append(q)
        quotes_text = " ".join(str(q.get("text") or "") for q in all_quotes)

        if not cert:
            cm = CERTIFICATE_RE.search(quotes_text)
            if cm:
                cert = cm.group(0).strip()

        if not consultant:
            consultant = extract_consultant_name(quotes_text)

        district = rep.get("district") or (rep.get("site") or {}).get("district")
        if not district:
            district = _extract_district(quotes_text + " " + proj)

        s_date, e_date = _parse_dates(base.get("start_date"), base.get("end_date"))
        if not s_date or not e_date:
            for q in base.get("quotes", []):
                tokens = date_tokens(q.get("text", ""), allow_year=False)
                if len(tokens) >= 2:
                    d1, d2 = tokens[0]["date"], tokens[1]["date"]
                    s_date, e_date = min(d1, d2), max(d1, d2)
                    break

        items.append({
            "id": rep_id,
            "state": state,
            "district": district,
            "project_name": proj,
            "cert": cert,
            "norm_cert": _norm_cert(cert),
            "consultant": consultant,
            "norm_consultant": _norm_consultant(consultant),
            "start_date": s_date,
            "end_date": e_date,
            "acc_quotes": acc.get("quotes", []),
            "base_quotes": base.get("quotes", []),
        })

    flags = []
    seen_overlap_pairs = set()
    seen_sharing_pairs = set()

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            r1 = items[i]
            r2 = items[j]

            if not r1["id"] or not r2["id"] or r1["id"] == r2["id"]:
                continue

            pair_key = tuple(sorted([r1["id"], r2["id"]]))

            # 1. ORANGE consultant_overlap:
            # Different states, same consultant or same cert, overlapping baseline sampling dates
            if r1["state"] and r2["state"] and r1["state"].lower() != r2["state"].lower():
                same_entity = False
                shared_ident = ""
                if r1["norm_cert"] and r2["norm_cert"] and r1["norm_cert"] == r2["norm_cert"]:
                    same_entity = True
                    shared_ident = f"Certificate: {r1['cert']}"
                elif r1["norm_consultant"] and r2["norm_consultant"] and r1["norm_consultant"] == r2["norm_consultant"]:
                    same_entity = True
                    shared_ident = f"Consultant: {r1['consultant']}"

                if same_entity and r1["start_date"] and r1["end_date"] and r2["start_date"] and r2["end_date"]:
                    if max(r1["start_date"], r2["start_date"]) <= min(r1["end_date"], r2["end_date"]):
                        if pair_key not in seen_overlap_pairs:
                            seen_overlap_pairs.add(pair_key)
                            overlap_start = max(r1["start_date"], r2["start_date"]).isoformat()
                            overlap_end = min(r1["end_date"], r2["end_date"]).isoformat()
                            r1_dates = f"{r1['start_date'].isoformat()} to {r1['end_date'].isoformat()}"
                            r2_dates = f"{r2['start_date'].isoformat()} to {r2['end_date'].isoformat()}"

                            quotes = []
                            for q in r1["base_quotes"]:
                                quotes.append({"page": q.get("page"), "text": f"[{r1['project_name']} - {r1['state']}] {q.get('text', '')}"})
                            for q in r2["base_quotes"]:
                                quotes.append({"page": q.get("page"), "text": f"[{r2['project_name']} - {r2['state']}] {q.get('text', '')}"})

                            evidence = [
                                {"label": "Project 1", "value": f"{r1['project_name']} ({r1['state']})" + (f", District: {r1['district']}" if r1['district'] else "")},
                                {"label": "Project 2", "value": f"{r2['project_name']} ({r2['state']})" + (f", District: {r2['district']}" if r2['district'] else "")},
                                {"label": "Entity / Credential", "value": shared_ident},
                                {"label": "Monitoring Window 1", "value": r1_dates},
                                {"label": "Monitoring Window 2", "value": r2_dates},
                                {"label": "Overlap Period", "value": f"{overlap_start} to {overlap_end}"},
                                {"label": "Method", "value": "Deterministic cross-filing timeline and accreditation reconciliation; no model call"},
                            ]

                            flags.append({
                                "check": "consultant_overlap",
                                "grade": "ORANGE",
                                "message": "Concurrent baseline sampling flagged across states; verify team capacity and physical monitoring deployment.",
                                "report_id": r1["id"],
                                "conflicting_report_id": r2["id"],
                                "project_name": f"{r1['project_name']} / {r2['project_name']}",
                                "state": f"{r1['state']} / {r2['state']}",
                                "quotes": quotes,
                                "evidence": evidence,
                            })

            # 2. INFO credential_sharing:
            # Same cert, differing consultant entity names
            if r1["norm_cert"] and r2["norm_cert"] and r1["norm_cert"] == r2["norm_cert"]:
                if r1["norm_consultant"] and r2["norm_consultant"]:
                    c1, c2 = r1["norm_consultant"], r2["norm_consultant"]
                    if c1 != c2 and c1 not in c2 and c2 not in c1:
                        if pair_key not in seen_sharing_pairs:
                            seen_sharing_pairs.add(pair_key)
                            quotes = []
                            for q in r1["acc_quotes"]:
                                quotes.append({"page": q.get("page"), "text": f"[{r1['project_name']}]: {q.get('text', '')}"})
                            for q in r2["acc_quotes"]:
                                quotes.append({"page": q.get("page"), "text": f"[{r2['project_name']}]: {q.get('text', '')}"})

                            evidence = [
                                {"label": "NABET Certificate", "value": r1["cert"]},
                                {"label": "Entity 1", "value": f"{r1['consultant']} ({r1['project_name']}, {r1['state']})"},
                                {"label": "Entity 2", "value": f"{r2['consultant']} ({r2['project_name']}, {r2['state']})"},
                                {"label": "Method", "value": "Deterministic cross-report NABET certificate and consultant entity reconciliation; no model call"},
                            ]

                            flags.append({
                                "check": "credential_sharing",
                                "grade": "INFO",
                                "message": "Same accreditation credential cited under different consultant names; verify authorization.",
                                "report_id": r1["id"],
                                "conflicting_report_id": r2["id"],
                                "project_name": f"{r1['project_name']} / {r2['project_name']}",
                                "state": f"{r1['state']} / {r2['state']}" if r1["state"] != r2["state"] else r1["state"],
                                "quotes": quotes,
                                "evidence": evidence,
                            })

    return flags


# ---------------------------------------------------------------------------
# Tavily discovery and polite downloading


class CreditCapReached(RuntimeError):
    pass


class TavilyStats:
    def __init__(self, cap: int = MAX_TAVILY_CREDITS, initial: Mapping[str, Any] | None = None):
        self.cap = cap
        self.credits = 0.0
        self.cached = 0
        self.by_endpoint = {name: {"calls": 0, "cached": 0, "credits": 0.0}
                            for name in ("map", "crawl", "search", "extract")}
        if initial:
            self.credits = float(initial.get("credits", 0.0))
            self.cached = int(initial.get("cached", 0))
            for ep, val in (initial.get("by_endpoint") or {}).items():
                if ep in self.by_endpoint:
                    self.by_endpoint[ep]["calls"] = int(val.get("calls", 0))
                    self.by_endpoint[ep]["cached"] = int(val.get("cached", 0))
                    self.by_endpoint[ep]["credits"] = float(val.get("credits", 0.0))

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
    """Discover candidate PDFs via Tavily Map, Crawl, and Search across official state boards."""
    if client is None:
        from tavily import TavilyClient
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            raise RuntimeError("TAVILY_API_KEY is missing; add it to .env for discovery")
        client = TavilyClient(api_key=key, project_id="tigerfish")

    # Preserve any previously recorded Tavily usage
    initial_stats = None
    if SUMMARY_JSON.exists():
        try:
            initial_stats = json.loads(SUMMARY_JSON.read_text(encoding="utf-8")).get("tavily")
        except Exception:
            pass
    stats = TavilyStats(max_credits, initial=initial_stats)

    candidates: dict[str, dict[str, Any]] = {}

    # Seed from existing public corpus if available
    if PUBLIC_CORPUS_INDEX.exists():
        for doc in load_index(PUBLIC_CORPUS_INDEX).get("documents", []):
            u = _clean_url(str(doc.get("url") or ""))
            if u:
                candidates[u] = dict(doc)

    for seed in seeds:
        seed_url = _clean_url(str(seed.get("url") or ""))
        if not seed_url:
            continue
        mapped = {}
        try:
            mapped = tavily_call(client, "map", stats, url=seed_url, max_depth=2,
                                 max_breadth=40, limit=100)
        except CreditCapReached:
            break
        except Exception:
            pass

        crawled = {}
        try:
            crawled = tavily_call(client, "crawl", stats, url=seed_url, max_depth=2,
                                  max_breadth=20, limit=60,
                                  instructions="Find official public-hearing pages and PDF links for English EIA executive summaries or draft EIAs.")
        except CreditCapReached:
            break
        except Exception:
            pass

        items = _items(mapped) + _items(crawled)

        # Multi-state search queries on the state pollution control board host
        host = _host(seed_url)
        search_queries = [
            f"site:{host} filetype:pdf executive summary",
            f"site:{host} filetype:pdf public hearing",
            f"site:{host} filetype:pdf draft EIA",
        ]
        for query in search_queries:
            try:
                searched = tavily_call(client, "search", stats, query=query, max_results=20)
                items.extend(_items(searched))
            except CreditCapReached:
                break
            except Exception:
                pass

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
    if not documents and PUBLIC_CORPUS_INDEX.exists():
        documents = list(load_index(PUBLIC_CORPUS_INDEX).get("documents", []))
    seen_urls = {_clean_url(d.get("url", "")) for d in documents}
    seen_hashes = {d.get("sha256") for d in documents if d.get("sha256")}
    session = session or requests.Session()
    robots = robots or RobotsPolicy()
    last_request: dict[str, float] = {}
    errors = 0
    skipped = []
    consecutive_errors: dict[str, int] = {}
    for candidate in candidates:
        if len(documents) >= limit:
            break
        url = _clean_url(str(candidate.get("url") or ""))
        if not url or url in seen_urls:
            continue
        host = _host(url)
        if consecutive_errors.get(host, 0) >= MAX_CONSECUTIVE_DOWNLOAD_ERRORS:
            skipped.append({"url": url, "reason": f"host {host} exceeded error threshold"})
            continue
        if not robots.allowed(url):
            skipped.append({"url": url, "reason": "robots.txt disallows fetching"})
            continue
        elapsed = time.monotonic() - last_request.get(host, 0.0)
        if elapsed < delay:
            sleep(delay - elapsed)
        last_request[host] = time.monotonic()
        temp = BATCH_DATA / ("." + hashlib.sha256(url.encode()).hexdigest() + ".part")
        try:
            try:
                response = session.get(url, headers={"User-Agent": "TigerFishBatch/1.0"},
                                       stream=True, timeout=DOWNLOAD_TIMEOUT, verify=True)
            except requests.exceptions.SSLError:
                response = session.get(url, headers={"User-Agent": "TigerFishBatch/1.0"},
                                       stream=True, timeout=DOWNLOAD_TIMEOUT, verify=False)
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
            consecutive_errors[host] = 0
            print(f"  [{len(documents)}/{limit}] Added {entry.get('state')}: {target.name[:35]} ({total // 1024} KB)", flush=True)
        except Exception as error:
            errors += 1
            consecutive_errors[host] = consecutive_errors.get(host, 0) + 1
            skipped.append({"url": url, "reason": str(error)[:200]})
            if temp.exists():
                temp.unlink()
    index = {"version": 1, "documents": documents, "skipped": skipped,
             "downloaded": len(documents), "max_bytes": max_bytes}
    _json_dump(CORPUS_INDEX, index)
    _json_dump(PUBLIC_CORPUS_INDEX, public_index(index))
    return index


def load_index(path: str | Path = CORPUS_INDEX) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        if path == CORPUS_INDEX and PUBLIC_CORPUS_INDEX.exists():
            return load_index(PUBLIC_CORPUS_INDEX)
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
                   "proposal_no": (checks.get("public_record") or {}).get("proposal_no") or None},
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

    # Run deterministic cross-state consultant overlap and credential sharing check
    cross_flags = check_cross_state_consultant_overlap(reports)
    for cflag in cross_flags:
        flags.append(dict(cflag))
        c_check = str(cflag.get("check") or "consultant_overlap")
        c_grade = str(cflag.get("grade") or "INFO")
        check_counts.setdefault(c_check, {})[c_grade] = check_counts.setdefault(c_check, {}).get(c_grade, 0) + 1

    return {"version": 1, "status": "complete", "reports_processed": len(reports),
            "reports_requested": DEFAULT_MAX_REPORTS, "per_check_counts": check_counts,
            "per_state_counts": _state_counts(reports), "flag_counts": _flag_counts(flags),
            "tavily": dict(tavily or {"cap": MAX_TAVILY_CREDITS, "calls": 0, "cached": 0,
                                      "credits": 0, "by_endpoint": {}}),
            "flags": flags,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "neutral_note": "Flags are leads for verification; they are not conclusions about intent or compliance."}


def summary_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# TigerFish batch summary",
        "",
        "Free, no-model checks over Indian EIA executive summaries. Flags are neutral leads for verification.",
        "",
        f"Reports processed: **{summary.get('reports_processed', 0)}**",
        "",
        "## Checks",
        "",
        "| Check | Grade/status counts |",
        "|---|---|",
    ]
    for check, counts in sorted((summary.get("per_check_counts") or {}).items()):
        lines.append(
            f"| {check} | "
            + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
            + " |"
        )
    lines += ["", "## States", "", "| State | Reports |", "|---|---:|"]
    for state, count in (summary.get("per_state_counts") or {}).items():
        lines.append(f"| {state} | {count} |")
    lines += [
        "",
        "## Tavily",
        "",
        f"Calls: {summary.get('tavily', {}).get('calls', 0)}; "
        f"cached calls: {summary.get('tavily', {}).get('cached', 0)}; "
        f"credits: {summary.get('tavily', {}).get('credits', 0)} / {summary.get('tavily', {}).get('cap', MAX_TAVILY_CREDITS)}.",
        "",
        "| Grade | State | Project | Check | Page | Quote | Message |",
        "|---|---|---|---|---:|---|---|",
    ]
    for flag in summary.get("flags", []):
        quotes = flag.get("quotes") or []
        quote = "<br>".join(
            f"p.{q.get('page')}: {_compact(q.get('text'))}" for q in quotes
        )
        lines.append(
            "| {grade} | {state} | {project} | {check} | {page} | {quote} | {message} |".format(
                grade=flag.get("grade", ""),
                state=_compact(flag.get("state")),
                project=_compact(flag.get("project_name")),
                check=flag.get("check", ""),
                page=", ".join(str(q.get("page")) for q in quotes if q.get("page")),
                quote=quote.replace("|", "\\|"),
                message=_compact(flag.get("message")),
            )
        )
    if not summary.get("flags"):
        lines.append(
            "| | | No screening leads | | | | See the check counts for undetermined results; no compliance conclusion follows. |"
        )
    return "\n".join(lines) + "\n"


def run_batch(index: Mapping[str, Any] | None = None, max_reports: int = DEFAULT_MAX_REPORTS,
              tavily: Mapping[str, Any] | None = None, client: Any | None = None,
              check_public_record: bool = True, force: bool = False, **kwargs: Any) -> dict[str, Any]:
    index = dict(index or load_index())
    if tavily is None and SUMMARY_JSON.exists():
        try:
            tavily = json.loads(SUMMARY_JSON.read_text(encoding="utf-8")).get("tavily")
        except Exception:
            pass
    stats = TavilyStats(initial=tavily)
    if client is None:
        key = os.getenv("TAVILY_API_KEY")
        if key:
            try:
                from tavily import TavilyClient
                client = TavilyClient(api_key=key)
            except Exception:
                pass
    reports = []
    report_items = []
    for doc in index.get("documents", [])[:max_reports]:
        local_path = doc.get("local_path")
        path = ROOT / local_path if local_path and not Path(local_path).is_absolute() else Path(local_path or "")
        report_id = str(doc.get("document_id") or (hashlib.sha256(str(path).encode()).hexdigest()[:16] if str(path) else "eia"))
        cached = REPORT_RESULTS / f"{report_id}.json"
        if cached.exists():
            try:
                quick = json.loads(cached.read_text(encoding="utf-8"))
                # If cached report does not yet have public_record check, compute it
                if check_public_record and (force or "public_record" not in (quick.get("batch_checks") or {})):
                    pages = []
                    if path.exists() and path.suffix.lower() == ".pdf":
                        from tigerfish.pdf_reader import read_pdf
                        try:
                            for p in read_pdf(path, render=False):
                                pages.append(p)
                                if len(pages) == 3:
                                    break
                        except Exception:
                            pass
                    rec = public_record_check(pages, metadata={**doc, **quick}, client=client, stats=stats)
                    quick.setdefault("batch_checks", {})["public_record"] = rec
                    quick.setdefault("checks", {})["public_record"] = rec
                    if rec.get("proposal_no") and not (quick.get("source") or {}).get("proposal_no"):
                        quick.setdefault("source", {})["proposal_no"] = rec["proposal_no"]
                    if rec.get("grade") in ("RED", "ORANGE", "INFO"):
                        quick.setdefault("batch_flags", []).append(rec)
                        quick.setdefault("flags", []).append(rec)
                    _json_dump(cached, quick)

                report = {"id": quick.get("id", report_id),
                          "state": quick.get("state") or doc.get("state", ""),
                          "project_name": quick.get("project_name") or quick.get("project") or doc.get("project_name", ""),
                          "checks": quick.get("batch_checks") or quick.get("checks", {}),
                          "flags": quick.get("batch_flags") or quick.get("flags", [])}
                reports.append(report)
                report_items.append({"id": quick.get("id", report_id), "file": cached.name})
                continue
            except (OSError, ValueError):
                pass
        if not path.exists() or path.suffix.lower() != ".pdf":
            continue
        report = analyze_pdf(path, {**doc, "id": report_id}, client=client, stats=stats, **kwargs)
        quick = _quick_report(report)
        _json_dump(cached, quick)
        reports.append(report)
        report_items.append({"id": report_id, "file": cached.name})
    summary = make_summary(reports, tavily=stats.as_dict())
    summary["reports_requested"] = max_reports

    # Attach cross-filing leads to individual report JSON objects in results/batch/
    for cflag in summary.get("flags", []):
        chk = cflag.get("check")
        if chk in ("consultant_overlap", "credential_sharing"):
            r1_id = cflag.get("report_id")
            r2_id = cflag.get("conflicting_report_id")
            for target_id, other_id in ((r1_id, r2_id), (r2_id, r1_id)):
                if not target_id:
                    continue
                target_file = REPORT_RESULTS / f"{target_id}.json"
                if target_file.exists():
                    try:
                        rep_data = json.loads(target_file.read_text(encoding="utf-8"))
                        b_flags = rep_data.setdefault("batch_flags", [])
                        if not any(f.get("check") == chk and f.get("conflicting_report_id") == other_id for f in b_flags):
                            b_flags.append(dict(cflag))
                            rep_data["flags"] = list(b_flags)
                            _json_dump(target_file, rep_data)
                    except Exception:
                        pass

    _json_dump(SUMMARY_JSON, summary)
    SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_MD.write_text(summary_markdown(summary), encoding="utf-8")
    _json_dump(PUBLIC_CORPUS_INDEX, public_index(index))
    _json_dump(QUICK_INDEX, {"format": "tigerfish-report/1",
                             "generated": summary["generated_at"],
                             "tool_version": _tool_version(), "reports": report_items})
    return summary


def _baseline_source_pages(
    doc: Mapping[str, Any], download_missing: bool
) -> list[dict[str, Any]]:
    """Read the exact disclosed PDF; refuse silent source changes since discovery."""
    import pymupdf

    report_id = str(doc["document_id"])
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", report_id):
        raise ValueError("Invalid corpus document ID")
    path = BATCH_DATA / f"{report_id}.pdf"
    if not path.exists():
        if not download_missing:
            raise FileNotFoundError(
                f"{path}: use --download-missing to fetch the saved source URL"
            )
        url = _clean_url(str(doc.get("url") or ""))
        if not url or not RobotsPolicy().allowed(url):
            raise ValueError(f"Source cannot be fetched: {url}")
        with requests.get(
            url,
            headers={"User-Agent": "TigerFishBatch/1.0"},
            timeout=DOWNLOAD_TIMEOUT,
            stream=True,
        ) as response:
            response.raise_for_status()
            parts, total = [], 0
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    raise ValueError("Source PDF exceeds the download limit")
                parts.append(chunk)
        content = b"".join(parts)
        if not content.startswith(b"%PDF-"):
            raise ValueError(f"Source is not a PDF: {url}")
        if hashlib.sha256(content).hexdigest() != doc.get("sha256"):
            raise ValueError(f"Source changed since corpus discovery: {url}")
        BATCH_DATA.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        time.sleep(DOWNLOAD_DELAY)
    if hashlib.sha256(path.read_bytes()).hexdigest() != doc.get("sha256"):
        raise ValueError(
            f"Local source hash does not match the saved corpus: {report_id}"
        )
    with pymupdf.open(path) as pdf:
        return [
            {"page": i + 1, "text": pdf.load_page(i).get_text()}
            for i in range(pdf.page_count)
        ]


def refresh_baselines(download_missing: bool = False) -> dict[str, Any]:
    """Refresh every published baseline screen, preserving species, certificates and costs.

    No model/GBIF/Tavily calls. Missing PDFs can be downloaded from their saved URLs;
    all inputs must load and match their original SHA256 before any public result changes.
    """
    index = load_index(QUICK_INDEX)
    corpus = {
        d["document_id"]: d
        for d in load_index(PUBLIC_CORPUS_INDEX).get("documents", [])
    }
    old_summary = load_index(SUMMARY_JSON)
    updates = []
    generated = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    for item in index.get("reports", []):
        path = BATCH_RESULTS / Path(item["file"]).name
        quick = json.loads(path.read_text(encoding="utf-8"))
        doc = corpus[quick["id"]]
        result = baseline_check(_baseline_source_pages(doc, download_missing))
        checks = dict(quick.get("batch_checks") or {})
        checks["baseline_season"] = result
        flags = [
            f
            for f in quick.get("batch_flags", [])
            if f.get("check") != "baseline_season"
        ]
        if result["grade"] in ("RED", "ORANGE", "INFO"):
            flags.append(result)
        quick.update(
            batch_checks=checks,
            checks=checks,
            batch_flags=flags,
            flags=flags,
            baseline_refresh={
                "parser_version": 2,
                "source_sha256": doc["sha256"],
                "generated_at": generated,
            },
        )
        updates.append((path, quick))
    if not updates:
        raise ValueError("No published batch reports were found to refresh")
    reports = [
        {
            "id": q["id"],
            "state": q.get("state"),
            "project_name": q.get("project_name"),
            "checks": q["batch_checks"],
            "flags": q["batch_flags"],
        }
        for _, q in updates
    ]
    summary = make_summary(reports, tavily=old_summary.get("tavily"))
    summary["reports_requested"] = old_summary.get("reports_requested", len(reports))
    summary["baseline_parser_version"] = 2
    for path, quick in updates:
        _json_dump(path, quick)
    _json_dump(SUMMARY_JSON, summary)
    SUMMARY_MD.write_text(summary_markdown(summary), encoding="utf-8")
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
