"""Status check on a species table image: IUCN categories and WPA schedules.

Usage: python scripts/check_status.py <image> [--max-credits 100]
e.g.   python scripts/check_status.py data/demo/indira_point_table_3_16_mammals.png

The table is read by Super-VL (cached from scripts/demo_table.py). IUCN categories
come from GBIF (cached); the current WPA schedule structure from Tavily (cached).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import claims, copycheck, llm, status  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--max-credits", type=int, default=copycheck.MAX_TAVILY_CREDITS)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    table = claims.extract_table_from_image(args.image)
    if table is None:
        sys.exit("Super-VL did not return a readable table.")
    budget = copycheck.Budget(args.max_credits)
    out = status.check_table(table, budget)
    name_col, iucn_col, wpa_col = out["columns"]
    print(f"\nTable: {table['title']}")
    print(f"Columns used: names={name_col!r}, IUCN={iucn_col!r}, WPA={wpa_col!r}")

    src = out["wpa_source"]
    if src:
        print(f"\nCurrent WPA schedules (from source, {src['support']} supporting sentence(s)): "
              f"{src['count']}")
        print(f"  {src['url']}")
        print(f"  \"{src['quote']}\"")
        print(f"  agreeing sources: {', '.join(src['sources'])}")
    elif wpa_col:
        print("\nCurrent WPA schedule structure: not found in the retrieved sources (GREY).")

    for check, title in (("iucn", "IUCN Red List category"), ("wpa_schedule", "WPA schedule")):
        rows = [r for r in out["results"] if r["check"] == check]
        if not rows:
            continue
        print(f"\n=== {title}")
        print(f"{'name as printed':32} {'report':8} {'current':12} grade")
        for r in rows:
            print(f"{r['name']:32} {str(r['report_value']):8} {str(r.get('current_value', '-')):12} "
                  f"{r['grade']}")
        for r in rows:
            if r["grade"] == "ORANGE":
                note = f" [name: {r['name_note']}]" if r.get("name_note") else ""
                print(f"  ORANGE {r['name']}: {r['message']} {r['evidence']}{note}")
        for r in rows:
            if r["grade"] == "GREY" and r.get("name_note"):
                print(f"  check by hand (GREY, not a finding) {r['name']}: {r['evidence']}")

    if out["stopped"]:
        print(f"\nSTOPPED: {out['stopped']}")
    print(f"\nTavily credits used this run: {budget.used} ({budget.calls} calls, "
          f"{budget.cached} from cache)")
    print(f"Nebius cost this run: ${llm.session_cost_usd:.4f}")


if __name__ == "__main__":
    main()
