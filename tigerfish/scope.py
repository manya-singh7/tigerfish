"""Which pages of a full report are worth auditing.

skip_reason(page) returns why a page is left out, or None to keep it:
  hindi       mostly Devanagari text (the Hindi summary; its text layer does not extract
              cleanly, and it repeats the English report)
  lab_report  laboratory test sheets: dense numbers plus test-report vocabulary
              (mg/l, NABL, detection limit, sample ID, ...); their numbers are measurements,
              not claims about the site that other pages restate
  blank_form  empty forms: rows of underscores or dot leaders
  annexure    annexure boilerplate: certificates, undertakings, ToR / compliance tables,
              office memoranda
Deterministic and free; thresholds are constants so the effect is easy to tune.
"""

import re

MIN_HINDI_SHARE = 0.20        # share of letters that are Devanagari
LAB_TERMS = re.compile(
    r"mg/l|mg/kg|µg/m|ug/m3|μg/m|NABL|test report|sample (?:id|no)|sampling date|"
    r"date of (?:sampling|analysis)|detection limit|\bBDL\b|IS\s?:?\s?3025|APHA|"
    r"\bMPN\b|\bCFU\b|turbidity|\bNTU\b|permissible limit|analysed by|method of analysis",
    re.IGNORECASE)
MIN_LAB_TERMS = 3
MIN_LAB_DIGIT_SHARE = 0.08    # digits / characters
FORM_FIELDS = re.compile(r"_{5,}|\.{6,}|…{3,}")
MIN_FORM_FIELDS = 6
ANNEXURE_HEAD = re.compile(r"\bannexure\b|\bappendix\b", re.IGNORECASE)
BOILERPLATE_TERMS = re.compile(
    r"terms of reference|compliance|undertaking|certificate|certified that|"
    r"office memorandum|minutes of the meeting|accreditation|declaration|"
    r"letter no\.?|F\.\s?No\.|this is to certify|applicable environment(?:al)? standards|"
    r"ambient air quality standards|noise (?:level )?standards|effluent standards",
    re.IGNORECASE)
# Gazette notifications (e.g. eco-sensitive zones) are kept: they hold site figures that
# other pages restate, such as species counts for a national park.
ANNEXURE_HEAD_CHARS = 400     # "Annexure" must appear near the top of the page


def hindi_share(text):
    letters = re.findall(r"[A-Za-zऀ-ॿ]", text)
    if not letters:
        return 0.0
    return sum("ऀ" <= ch <= "ॿ" for ch in letters) / len(letters)


def skip_reason(page):
    text = page.get("text") or ""
    if hindi_share(text) >= MIN_HINDI_SHARE:
        return "hindi"
    digits = sum(ch.isdigit() for ch in text)
    if (len(LAB_TERMS.findall(text)) >= MIN_LAB_TERMS
            and digits / max(1, len(text)) >= MIN_LAB_DIGIT_SHARE):
        return "lab_report"
    if len(FORM_FIELDS.findall(text)) >= MIN_FORM_FIELDS:
        return "blank_form"
    if ANNEXURE_HEAD.search(text[:ANNEXURE_HEAD_CHARS]) and BOILERPLATE_TERMS.search(text):
        return "annexure"
    return None


def select_pages(pages):
    """(kept pages, {reason: [page numbers]})."""
    kept, skipped = [], {}
    for p in pages:
        if p.get("error"):
            skipped.setdefault("error", []).append(p["page"])
            continue
        reason = skip_reason(p)
        if reason:
            skipped.setdefault(reason, []).append(p["page"])
        else:
            kept.append(p)
    return kept, skipped
