"""Status check (IUCN via GBIF + WPA schedules) on a report's own species tables.

Usage: python scripts/check_status_pages.py <pdf> [--max-credits 10]

Reads the tables from the PDF's text layer (tigerfish/status_pages.py), so no model call.
GBIF is free and cached; the WPA schedule source is a Tavily search (cached, capped).
Saves cache/findings/<pdf>/status_pages.json for scripts/export_results.py.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import llm, pdf_reader, status_pages  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--max-credits", type=int, default=10)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pdf = Path(args.pdf)
    out = status_pages.check_pages(pdf_reader.read_pdf(pdf), max_credits=args.max_credits)
    for t in out["tables"]:
        print(f"p.{t['page']}: {t['rows']} rows, columns {t['columns']}")
    src = out["wpa_source"]
    if src:
        print(f"\nCurrent WPA schedules: {src['count']} ({src['label']}) {src['url']}\n  \"{src['quote']}\"")
    for check in ("iucn", "wpa_schedule"):
        rows = [r for r in out["results"] if r["check"] == check]
        grades = {g: sum(r["grade"] == g for r in rows) for g in ("ORANGE", "NONE", "GREY")}
        print(f"\n=== {check}: {grades}")
        for r in rows:
            if r["grade"] == "ORANGE" or (r["grade"] == "GREY" and r.get("name_note")):
                print(f"  {r['grade']:6} p.{r['page']} {r['name']}: {r['evidence']}")
    if out["stopped"]:
        print(f"\nSTOPPED: {out['stopped']}")
    t = out["tavily"]
    print(f"\nTavily: {t['credits']} credits ({t['calls']} calls, {t['cached']} cached); "
          f"Nebius ${llm.session_cost_usd:.4f}")
    path = ROOT / "cache" / "findings" / pdf.stem / "status_pages.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
