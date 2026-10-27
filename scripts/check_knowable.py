"""Knowable at the time: run tigerfish.knowable over saved reports, save results/knowable_*.json.

  python scripts/check_knowable.py                      # every report with topics
  python scripts/check_knowable.py --only ct-239        # one finding (probe)
Cached: a re-run costs nothing. Caps: knowable.MAX_CREDITS Tavily credits, MAX_NEBIUS_USD.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import copycheck, knowable, llm  # noqa: E402
from tigerfish.ui import data  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="finding id (probe; result not saved)")
    ap.add_argument("--max-credits", type=int, default=knowable.MAX_CREDITS)
    args = ap.parse_args()
    budget = copycheck.Budget(args.max_credits)
    for rid in knowable.TOPICS:
        report = data.load(rid)
        if args.only:
            report = {**report, "findings": [f for f in report["findings"] if f["id"] == args.only]}
            if not report["findings"]:
                continue
        result = knowable.run(report, budget)
        for f in result["findings"]:
            print(f"{f['finding_id']}: {len(f['sources'])} source(s); dropped "
                  + "; ".join(f"{d['url']} ({d['why']})" for d in f["dropped"]))
            for s in f["sources"]:
                print(f"   {s['date']} {s['url']}\n   \"{s['quote'][:200]}\"")
        if not args.only:
            knowable.path(rid).write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
            print(f"saved {knowable.path(rid).name}")
    print(f"Tavily credits this run: {budget.used} (cached calls: {budget.cached}); "
          f"Nebius ${llm.session_cost_usd:.4f}")


if __name__ == "__main__":
    main()
