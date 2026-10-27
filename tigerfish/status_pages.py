"""Status check on a report's own species tables (text layer): IUCN categories and WPA
schedules, compared by tigerfish/status.py. Free except the WPA source search (Tavily,
cached, capped); no LLM.

The tables come from the PDF's text layer, one cell per line. A table is any run of rows
under a header that names an IUCN column (and maybe an IWPA / Schedule column). A row
starts at a serial-number line ("12" or "12."). In the row, the IUCN cell is the line
right after the Family cell (a name ending in -idae / -aceae), or, in tables without a
family column, right after the scientific name; the IWPA cell follows the IUCN cell. Empty
cells are blank lines, so they stay in place. Rows whose name or cells can't be read are
skipped (never guessed).
"""

import re

from tigerfish import claims as claims_mod
from tigerfish import copycheck, status
from tigerfish.species_pages import candidate_names

SERIAL = re.compile(r"^\d{1,3}\.?$")
HEADER_START = re.compile(r"^(?:S\.?\s?No|Sl\.?\s?No)\b", re.IGNORECASE)
FAMILY_CELL = re.compile(r"[A-Z][a-z]+(?:idae|aceae)$")
HEADER_SPAN = 14         # header lines looked at after "S.No"
NAME_CELLS = 3           # the scientific name is in the row's first cells (it may wrap)
WPA_CELL = re.compile(r"^(?:Sch(?:edule)?[\s.\-]*)?(?:[IVX]{1,4}|[1-6])$", re.IGNORECASE)
NAME_COL, IUCN_COL, WPA_COL = "Scientific name", "IUCN", "IWPA Schedule"


def _cells(text):
    return [line.strip() for line in (text or "").split("\n")]


def _header(lines, i):
    """(has_iucn, has_wpa, index after the header) for a header starting at line i."""
    span = lines[i:i + HEADER_SPAN]
    joined = " ".join(span)
    if "IUCN" not in joined:
        return False, False, i + 1
    end = i + 1
    while end < len(lines) and end < i + HEADER_SPAN and not SERIAL.match(lines[end]):
        end += 1
    head = " ".join(lines[i:end])
    return True, bool(re.search(r"\bI?WPA\b|Schedule", head)), end


def _row(cells, has_wpa):
    """{name, iucn, wpa} from one row's cells, or None."""
    head = [c for c in cells if c][:NAME_CELLS]
    names = candidate_names(claims_mod.normalize(" ".join(head)))
    if not names:
        return None
    name = " ".join(names[0].split()[:2])
    fam = [k for k, c in enumerate(cells) if FAMILY_CELL.fullmatch(c)]
    if fam:
        anchor = fam[0]
    else:   # no family column: the cell that ends the scientific name
        epithet = name.split()[1]
        anchor = next((k for k, c in enumerate(cells) if re.search(rf"\b{re.escape(epithet)}\b", c)),
                      None)
        if anchor is None:
            return None
    cell = lambda k: cells[k] if k < len(cells) else ""          # noqa: E731
    iucn = cell(anchor + 1)
    wpa = cell(anchor + 2) if has_wpa else ""
    # A cell that is not an IUCN code / schedule numeral (a shifted or garbled row) is left
    # empty, so it is graded GREY ("not in the report row"), never guessed.
    return {NAME_COL: name, IUCN_COL: iucn if status.iucn_code(iucn) else None,
            WPA_COL: wpa if has_wpa and WPA_CELL.match(wpa) else None,
            "cells": [c for c in cells if c][:12]}


def tables_from_pages(pages):
    """[{title, page, columns, rows}] for every IUCN table section on the text pages."""
    out = []
    for p in pages:
        lines = _cells(p.get("text"))
        i, table = 0, None
        while i < len(lines):
            if HEADER_START.match(lines[i]):
                has_iucn, has_wpa, nxt = _header(lines, i)
                if has_iucn:
                    table = {"title": f"species table, p.{p['page']}", "page": p["page"],
                             "columns": [NAME_COL, IUCN_COL] + ([WPA_COL] if has_wpa else []),
                             "rows": []}
                    out.append(table)
                    i = nxt
                    continue
            if table is not None and SERIAL.match(lines[i]):
                j = i + 1
                while j < len(lines) and not SERIAL.match(lines[j]) and not HEADER_START.match(lines[j]):
                    j += 1
                row = _row(lines[i + 1:j], WPA_COL in table["columns"])
                if row:
                    table["rows"].append(row)
                i = j
                continue
            i += 1
    return [t for t in out if t["rows"]]


def check_pages(pages, max_credits=copycheck.MAX_TAVILY_CREDITS):
    """IUCN / WPA results for every row of the report's IUCN tables, each with its page."""
    budget = copycheck.Budget(max_credits)
    tables = tables_from_pages(pages)
    results, wpa_source, stopped = [], None, None
    for t in tables:
        got = status.check_table(t, budget)
        wpa_source = wpa_source or got["wpa_source"]
        stopped = stopped or got["stopped"]
        results += [{**r, "page": t["page"]} for r in got["results"]]
    return {"tables": [{"page": t["page"], "columns": t["columns"], "rows": len(t["rows"])}
                       for t in tables],
            "results": results, "wpa_source": wpa_source, "stopped": stopped,
            "tavily": {"calls": budget.calls, "cached": budget.cached, "credits": budget.used}}
