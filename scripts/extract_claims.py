"""Extract a claim ledger from an EIA PDF.

Usage:
  python scripts/extract_claims.py <pdf> --pages 234,392,444 [--max-cost 0.50] [--dry-run]

Prints the estimated cost first (cached pages are free). --dry-run stops there.
The ledger goes to cache/claims/<pdf_stem>/claims.jsonl.
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import claims, llm, pdf_reader  # noqa: E402


def parse_pages(spec):
    """'234,392,400-402' -> [234, 392, 400, 401, 402]"""
    pages = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            pages.extend(range(int(a), int(b) + 1))
        elif part.strip():
            pages.append(int(part))
    return pages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--pages", help="e.g. 234,392,400-402 (default: all pages)")
    parser.add_argument("--max-cost", type=float, default=claims.MAX_COST_USD)
    parser.add_argument("--dry-run", action="store_true", help="only print the estimate")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    pdf = Path(args.pdf)
    pages = pdf_reader.read_pdf(pdf)
    if args.pages:
        wanted = set(parse_pages(args.pages))
        pages = [p for p in pages if p["page"] in wanted]
        missing = wanted - {p["page"] for p in pages}
        if missing:
            sys.exit(f"pages not in PDF: {sorted(missing)}")

    est, uncached = claims.estimate_cost(pages)
    vision = sum(1 for p in pages if p["needs_vision"])
    print(f"{len(pages)} pages ({vision} via Super-VL); {uncached} need a real API call.")
    print(f"Estimated cost: ${est:.4f}  (cap ${args.max_cost:.2f})")
    if args.dry_run:
        return

    found = claims.extract_claims(pages, max_cost_usd=args.max_cost, pdf_stem=pdf.stem)
    run = claims.last_run

    print(f"\n{'page':>5} {'type':10} {'ok':3} {'value':>10} {'unit':8} quote")
    for c in found:
        ok = {True: "yes", False: "NO", None: "-"}[c["verified"]]
        quote = c["quote"] if len(c["quote"]) <= 90 else c["quote"][:87] + "..."
        print(f"{c['page']:>5} {c['type']:10} {ok:3} {str(c['value'])[:10]:>10} "
              f"{str(c['unit'] or '')[:8]:8} {quote}")

    rate = run["verified_rate"]
    print(f"\nClaims: {run['claims']}  by type: {dict(Counter(c['type'] for c in found))}")
    print(f"Verified quotes: {run['verified']}/{run['claims']}"
          + (f" ({rate:.0%})" if rate is not None else ""))
    print(f"Pages done: {run['pages_done']}")
    if run["pages_skipped"]:
        print(f"Pages skipped: {run['pages_skipped']}")
    if run["stopped"]:
        print(f"STOPPED: {run['stopped']}")
    print(f"Real API cost this run: ${run['cost_usd']:.4f}")
    print(f"Ledger: {claims.ledger_path(pdf.stem)}")
    if vision:
        print("(Super-VL price is an unverified placeholder; real cost may be lower)")


if __name__ == "__main__":
    main()
