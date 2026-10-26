"""Does the Great Nicobar draft EIA match the official record?

    python scripts/check_official_record.py [--facts-only] [--env PATH] [--pages PATH]

Reads page texts from the cached pages.jsonl (read-only), runs tigerfish/official_record.py
and writes results/official_record_great_nicobar_2021_draft.json. Caps: $0.30 Nebius
(LIGHTNING), 60 Tavily credits. All calls are cached in this checkout's cache/.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_PAGES = ROOT / "cache" / "pages" / "great_nicobar_2021_draft_eia" / "pages.jsonl"
OUT = ROOT / "results" / "official_record_great_nicobar_2021_draft.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts-only", action="store_true", help="only step 1 (no Tavily)")
    ap.add_argument("--env", help=".env file with NEBIUS_API_KEY / TAVILY_API_KEY")
    ap.add_argument("--pages", default=str(DEFAULT_PAGES), help="pages.jsonl to read")
    args = ap.parse_args()
    if args.env:
        from dotenv import load_dotenv
        load_dotenv(args.env, override=False)

    from tigerfish import copycheck, llm
    from tigerfish import official_record as off

    with open(args.pages, encoding="utf-8") as f:
        pages = {p["page"]: p["text"] for p in map(json.loads, f)}
    started = time.time()
    if args.facts_only:
        facts, calls = off.report_facts(pages)
        print(json.dumps(facts, indent=1, ensure_ascii=False))
        print(f"{calls} LIGHTNING calls, ${llm.session_cost_usd:.4f}")
        return

    budget = copycheck.Budget(off.MAX_TAVILY_CREDITS)
    result = off.run(pages, budget=budget)
    result = {"id": "official_record_great_nicobar_2021_draft",
              "report_id": "great_nicobar_2021_draft",
              "title": "Great Nicobar EIA (2021 draft): does it match the official record?",
              "generated": time.strftime("%Y-%m-%d %H:%M"),
              "seconds": round(time.time() - started, 1), **result}
    OUT.write_text(off.dumps(result), encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))
    for r in result["comparisons"]:
        print(f"{r['grade']:7} {r['label']:28} {r['message']}")
    print("tavily:", {k: v for k, v in result["tavily"].items() if k != "queries"})
    print("cost:", result["cost"])


if __name__ == "__main__":
    main()
