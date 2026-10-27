"""Public record timeline, "what happened next" news and local-language links for each report;
saves results/public_record_<report id>.json. Cached: a re-run costs nothing.

  python scripts/check_public_record.py [--max-credits 150]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import copycheck, knowable, public_record  # noqa: E402
from tigerfish.ui import data  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-credits", type=int, default=public_record.MAX_CREDITS)
    args = ap.parse_args()
    budget = copycheck.Budget(args.max_credits)
    for rid in public_record.PROJECTS:
        ids = {f["id"] for f, _, _ in knowable.verified_findings(data.load(rid))}
        result = public_record.run(rid, budget, ids)
        public_record.path(rid).write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
        print(f"{rid}: {len(result['timeline'])} verified events "
              f"({len(result['timeline_dropped'])} dropped); "
              f"{sum(len(n['items']) for n in result['next'])} news links; "
              f"{sum(len(n['items']) for n in result['local'])} local-language links; "
              f"stopped: {result['stopped']}")
        for e in result["timeline"]:
            print(f"   {e['date']}  {e['event'][:90]}  ({e['host']})")
        for e in result["timeline_dropped"]:
            print(f"   DROPPED {e.get('date')} {str(e.get('event'))[:60]} ({e['why']})")
    print(f"Tavily credits this run: {budget.used} (cached calls: {budget.cached})")


if __name__ == "__main__":
    main()
