"""Find freely licensed Wikimedia Commons photos for flagged species; saves
results/species_photos.json. Cached: a re-run costs nothing."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import copycheck, species_photos  # noqa: E402


def main():
    budget = copycheck.Budget(species_photos.MAX_CREDITS)
    result = species_photos.run(budget)
    species_photos.PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for rid, rows in result["photos"].items():
        for fid, r in rows.items():
            p = r["photo"]
            print(f"{rid} {fid} {r['species']}: "
                  + (f"{p['licence']} by {p['author'][:50]} ({p['title']})" if p else
                     "no licensed image; " + "; ".join(c["why"] for c in r["checked"][:3])))
    print(f"Tavily credits this run: {budget.used} (cached calls: {budget.cached}); stopped: {result['stopped']}")


if __name__ == "__main__":
    main()
