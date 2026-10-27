"""Species check on a report's own species tables (free except optional Super-VL pages).

Usage: python scripts/check_species_pages.py <pdf> [--dry-run] [--max-vision 10] [--no-vision]

Prints the species-table pages, the scanned pages that would go to Super-VL and the
estimated cost first; then the results table (page, name as printed, GBIF name, grade,
local / 500 km / far counts, location used and why). Results are cached (GBIF, models)
and written to cache/findings/<pdf>/species_pages.json for scripts/export_results.py.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import claims, llm, pdf_reader, sites, species_pages as sp  # noqa: E402

OUT_DIR = ROOT / "cache" / "findings"


def fmt(n):
    return "-" if n is None else f"{n:,}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--max-vision", type=int, default=10)
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pages = pdf_reader.read_pdf(args.pdf)
    by = {p["page"]: p for p in pages}
    table_pages = sp.species_table_pages(pages)
    vision = [] if args.no_vision else sp.scanned_neighbours(pages, table_pages)[:args.max_vision]
    est = sum(claims.estimate_page_cost({**by[n], "needs_vision": True}) for n in vision)
    texts = {p["page"]: p["text"] for p in pages}
    n_cands = len({n for t in table_pages for n in sp.candidate_names(texts[t])})
    print(f"Species-table pages with text ({len(table_pages)}): {table_pages}")
    print(f"Scanned neighbours for Super-VL ({len(vision)}): {vision}")
    print(f"{n_cands} name candidates to confirm with GBIF (free). "
          f"Estimated model cost: ${est:.4f}")
    if args.dry_run:
        return

    prof = sites.profile(Path(args.pdf).stem)
    if prof:
        print(f"Site profile: {prof['site_label']} {prof['site']}; archipelago rule: "
              f"{prof['archipelago_gadm'] or 'off'}")
    out = sp.check_pages(pages, max_vision=args.max_vision, use_vision=not args.no_vision,
                         profile=prof)
    rows = out["rows"]
    print(f"\n{'page':>5} {'name as printed':34} {'GBIF name':30} {'grade':6} "
          f"{'local':>6} {'500 km':>7} {'far':>6}  location")
    for r in rows:
        print(f"{r['page']:>5} {r['name'][:34]:34} {str(r['gbif_name'])[:30]:30} "
              f"{str(r['grade'] or 'ok'):6} {fmt(r['local']):>6} {fmt(r['regional']):>7} "
              f"{fmt(r['far']):>6}  {r['location']}")
    grades = Counter(r["grade"] or "plausible" for r in rows)
    print(f"\n{len(rows)} names checked: {dict(grades)}")
    print("\nLocations used:")
    seen = set()
    for r in rows:
        if r["page"] not in seen:
            seen.add(r["page"])
    for page in sorted({r["page"] for r in rows}):
        r = next(x for x in rows if x["page"] == page)
        print(f"  p.{page}: {r['location']} ({r['lat']}, {r['lon']}): {r['reason']}")
    path = OUT_DIR / Path(args.pdf).stem / "species_pages.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nSaved {path}. Model cost this run: ${llm.session_cost_usd:.4f}")


if __name__ == "__main__":
    main()
