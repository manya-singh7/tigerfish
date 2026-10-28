"""Omissions check: threatened species recorded near the project site but never mentioned.

Usage: python scripts/check_omissions.py [pdf] [--lat 6.83 --lon 93.87]

Free (GBIF + text search, cached). Prints the full results table, asserts the sanity check
(the leatherback, Dermochelys coriacea, is mentioned in the Great Nicobar report, so it must
not be flagged) and saves cache/findings/<pdf>/omissions.json for scripts/export_results.py.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import claims, omissions as om, pdf_reader, sites  # noqa: E402

DEFAULT_PDF = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"
MUST_BE_MENTIONED = ["Dermochelys coriacea"]      # sanity check for the Great Nicobar report


def write_not_applicable(pdf, name, reason):
    """Save {"not_applicable": reason} as the check's result (no GBIF call) and say so."""
    path = ROOT / "cache" / "findings" / pdf.stem / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"not_applicable": reason, "grade": "NOT_APPLICABLE"},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sites.NOT_APPLICABLE.capitalize()}: {reason}")
    print(f"No calls made. Saved {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", nargs="?", default=str(DEFAULT_PDF))
    parser.add_argument("--lat", type=float, help="default: the report's site (tigerfish/sites.py)")
    parser.add_argument("--lon", type=float)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pdf = Path(args.pdf)
    prof = sites.profile(pdf.stem)
    reason = sites.not_applicable(pdf.stem, "omission")
    if reason:          # e.g. a statewide road network: no single site to search around
        write_not_applicable(pdf, "omissions.json", reason)
        return
    default = prof["site"] if prof else om.SITE
    if args.lat is None or args.lon is None:
        if not prof:
            print(f"No site profile for {pdf.stem}: using {default}. Pass --lat/--lon.")
        args.lat, args.lon = default
    pages = pdf_reader.read_pdf(pdf)
    out = om.check(pages, claims.load_ledger(pdf.stem), args.lat, args.lon)
    rows = out["rows"]
    print(f"Site {args.lat}, {args.lon}. Searched {out['pages_searched']} pages; "
          f"{len(out['pages_without_text'])} have no usable text (scanned, no Super-VL output), "
          f"so names on them could be missed.\n")
    print(f"{'grade':6} {'IUCN':4} {'species':30} {'10 km':>5} {'25 km':>5} "
          f"{'10 km since 2000':>16} {'latest':>6}  mentioned on (match)")
    for r in rows:
        where = (f"{r['mentioned_pages'][:5]}{' ...' if len(r['mentioned_pages']) > 5 else ''} "
                 f"({r['matched'][0]})" if r["mentioned_pages"] else "not mentioned")
        print(f"{str(r['grade'] or '-'):6} {r['category']:4} {r['name'][:30]:30} {r['near']:>5} "
              f"{r['wide']:>5} {r['near_since_2000']:>16} {str(r['latest_year']):>6}  {where}")

    if pdf == DEFAULT_PDF or pdf.name == DEFAULT_PDF.name:
        by = {r["name"]: r for r in rows}
        for name in MUST_BE_MENTIONED:
            if name in by:
                assert by[name]["grade"] is None, f"sanity check failed: {name} flagged"
                print(f"\nSanity check OK: {name} is mentioned (pages {by[name]['mentioned_pages'][:5]}), not flagged.")
            else:
                print(f"\nSanity check: {name} not among the species recorded near the site.")

    path = ROOT / "cache" / "findings" / pdf.stem / "omissions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {g: sum(r["grade"] == g for r in rows) for g in ("RED", "ORANGE", "INFO")}
    print(f"\n{len(rows)} species; flags {counts}. Saved {path}")


if __name__ == "__main__":
    main()
