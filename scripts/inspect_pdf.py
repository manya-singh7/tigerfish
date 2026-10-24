"""Inspect one EIA PDF: page count, vision pages, and where key numbers/words appear.

Usage: python scripts/inspect_pdf.py [path/to/file.pdf]
"""

import logging
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import pdf_reader  # noqa: E402

DEFAULT_PDF = "data/eias/great_nicobar_2021_draft_eia.pdf"
SNIPPET = 60   # characters of context on each side of a match
NEAR = 150     # "near" = within this many characters


def number(n):
    """Match a number on its own, not inside 1.910, 9101 or 3,910."""
    return rf"(?<![\d.,]){n}(?![\d]|[.,]\d)"


TERMS = {
    "coral": r"coral",
    "1045 / 1,045": number(r"1,?045"),
    "910": number("910"),
}
NEAR_WORDS = r"species|fauna"
NEAR_TERMS = {"330": number("330"), "695": number("695")}


def snippet(text, start, end):
    s = text[max(0, start - SNIPPET):end + SNIPPET]
    return "..." + " ".join(s.split()) + "..."


def find_hits(pages):
    hits = {name: [] for name in [*TERMS, *(f"{n} near species/fauna" for n in NEAR_TERMS)]}
    for page in pages:
        text = page["text"]
        for name, pattern in TERMS.items():
            for m in re.finditer(pattern, text, re.IGNORECASE):
                hits[name].append((page["page"], snippet(text, m.start(), m.end())))
        for n, pattern in NEAR_TERMS.items():
            for m in re.finditer(pattern, text):
                window = text[max(0, m.start() - NEAR):m.end() + NEAR]
                if re.search(NEAR_WORDS, window, re.IGNORECASE):
                    hits[f"{n} near species/fauna"].append(
                        (page["page"], snippet(text, m.start(), m.end())))
    return hits


def main():
    pdf = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # PDF text has odd characters
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    started = time.time()
    pages = pdf_reader.read_pdf(pdf)  # first run ~10 min on 1200 pages; cached after that
    reasons = Counter(r for p in pages for r in p["reasons"])

    print(f"File: {pdf}")
    print(f"Total pages: {len(pages)}")
    print(f"Pages needing vision: {sum(p['needs_vision'] for p in pages)}"
          f"  (PNGs in cache/pages/{Path(pdf).stem}/)")
    print(f"  by reason (a page can have several): {dict(reasons)}")
    print(f"Pages that failed to parse: {[p['page'] for p in pages if p['error']]}")
    print(f"Time: {time.time() - started:.0f} s")

    for name, found in find_hits(pages).items():
        per_page = Counter(p for p, _ in found)
        print(f"\n=== {name}: {len(found)} matches on {len(per_page)} pages")
        print(f"pages: {sorted(per_page)}")
        shown = set()
        for p, snip in found:   # one snippet per page keeps the output readable
            if p not in shown:
                shown.add(p)
                extra = f" (+{per_page[p] - 1} more)" if per_page[p] > 1 else ""
                print(f"  p.{p}{extra}: {snip}")


if __name__ == "__main__":
    main()
