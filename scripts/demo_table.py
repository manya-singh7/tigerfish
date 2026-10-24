"""Headline demo: Super-VL reads a species table image, GBIF checks every species.

Usage: python scripts/demo_table.py <image> <lat> <lon>
e.g.   python scripts/demo_table.py data/demo/indira_point_table_3_16_mammals.png 6.75 93.83
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import claims, llm, species  # noqa: E402


def run(image, lat, lon):
    """Returns (table, [(claim, species_result), ...]); table is None if unreadable."""
    table = claims.extract_table_from_image(image)
    if table is None:
        return None, []
    found = claims.species_claims_from_table(table, source=image)
    return table, [(c, species.check_species(c["value"], lat, lon)) for c in found]


def fmt(n):
    return "-" if n is None else f"{n:,}"


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    image, lat, lon = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])

    table, results = run(image, lat, lon)
    if table is None:
        sys.exit("Super-VL did not return a readable table.")

    print(f"\nTable read by Super-VL: {table['title']}")
    print(f"Columns: {table['columns']}  ->  names from: {claims.name_column(table)!r}")
    print(f"Site: {lat}, {lon}\n")
    print(f"{'name as printed':32} {'GBIF name':24} {'grade':6} {'local':>6} {'500 km':>7} "
          f"{'global':>9}")
    for c, r in results:
        print(f"{c['value']:32} {str(r['matched_name']):24} {str(r['grade']):6} "
              f"{fmt(r['local_count']):>6} {fmt(r['regional_count']):>7} "
              f"{fmt(r['global_count']):>9}")

    flagged = [(c, r) for c, r in results if r["grade"] in ("RED", "ORANGE")]
    print(f"\n{len(flagged)} of {len(results)} species flagged (RED/ORANGE). "
          f"GREY = not enough data, not shown as a finding.\n")
    for c, r in flagged:
        note = f" [name: {r['name_note']}]" if r["name_note"] else ""
        print(f"{r['grade']:6} {c['value']}: {r['evidence']}{note}")
    print(f"\nReal API cost this run: ${llm.session_cost_usd:.4f} "
          f"(Super-VL price is an unverified placeholder)")


if __name__ == "__main__":
    main()
