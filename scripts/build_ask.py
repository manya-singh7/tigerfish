"""Record the replay Q&As: results/ask_great_nicobar_2021_draft.json.

    python scripts/build_ask.py --cache ../tigerfish/cache

Each question is one Nemotron Ultra call on the whole report (identical prefix, question last;
estimate printed first; the $3 spend cap applies). Already-asked questions replay free from the
local cache.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tigerfish import ask, fulltext  # noqa: E402

REPORT_ID = "great_nicobar_2021_draft"
OUT = ROOT / "results" / f"ask_{REPORT_ID}.json"
QUESTIONS = [
    "How long did the terrestrial flora and fauna baseline survey last?",
    "What does the report say about leatherback turtle nesting at Galathea Bay?",
    "Does the report assess impacts on dugongs?",
    "How much coral area will be affected, and what is proposed for it?",
    "Who prepared the report, and what accreditation is stated?",
    "What does the report say about the Shompen community?",
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(ROOT / "cache"), help="cache dir with pages/ (read only)")
    pages = fulltext.load_pages(Path(ap.parse_args().cache))
    report = fulltext.report_text(pages)
    answers = []
    for q in QUESTIONS:
        a = ask.ask(q, pages, report)
        answers.append(a)
        print(f"  -> {'answered' if a['report_says'] else 'does not say'}; "
              f"{len(a['citations'])} verified, {len(a['unverified_citations'])} unverified citations")
    OUT.write_text(json.dumps({
        "report_id": REPORT_ID, "created": date.today().isoformat(), "model": answers[0]["model"],
        "pages_included": len(report["pages"]), "skipped": report["skipped"],
        "prices_usd_per_million": {"input": fulltext.PRICE_IN, "cached_input": fulltext.PRICE_CACHED,
                                   "output": fulltext.PRICE_OUT},
        "answers": answers, "totals": ask.totals(answers)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(ask.totals(answers), indent=2), f"\nSpent so far (all Ultra calls): ${fulltext.spent():.4f}")
