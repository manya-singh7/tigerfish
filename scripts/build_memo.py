"""Write results/memo_great_nicobar_2021_draft.json: Nemotron Ultra's reviewer's memo on the
whole report (one call; the estimate is printed first and the $3 spend cap applies).

    python scripts/build_memo.py --cache ../tigerfish/cache
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tigerfish import fulltext, memo  # noqa: E402

REPORT_ID = "great_nicobar_2021_draft"
OUT = ROOT / "results" / f"memo_{REPORT_ID}.json"

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(ROOT / "cache"), help="cache dir with pages/ (read only)")
    pages = fulltext.load_pages(Path(ap.parse_args().cache))
    result = {"report_id": REPORT_ID, "created": date.today().isoformat(), **memo.run(pages)}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    s = result["stats"]
    print(f"{s['issues_verified']} issues with verified quotes, {s['moved_to_unverified']} moved to "
          f"unverified; {s['citations_verified']}/{s['citations']} citations verified "
          f"({s['page_corrected']} page-corrected). Spent so far ${fulltext.spent():.4f}")
