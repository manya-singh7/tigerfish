"""Consultant accreditation check (NABET / QCI) for one EIA PDF.

Usage: python scripts/check_accreditation.py [pdf] [--max-credits 15]

One LIGHTNING call (cached) reads the pages that mention NABET / accreditation; Tavily
(cached, capped) finds the official accreditation entry. Prints the extracted details,
the official evidence and the grade, and saves cache/findings/<pdf>/accreditation.json
for scripts/export_results.py.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from tigerfish import accreditation as ac, llm, pdf_reader, sites  # noqa: E402
from check_omissions import write_not_applicable  # noqa: E402

DEFAULT_PDF = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", nargs="?", default=str(DEFAULT_PDF))
    parser.add_argument("--max-credits", type=int, default=ac.MAX_CREDITS)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pdf = Path(args.pdf)
    reason = sites.not_applicable(pdf.stem, "accreditation")
    if reason:          # e.g. no Indian EIA consultant: NABET does not apply (no Lightning, no Tavily)
        write_not_applicable(pdf, "accreditation.json", reason)
        return
    out = ac.check(pdf_reader.read_pdf(pdf), max_credits=args.max_credits)
    print(f"Pages read for consultant details: {out['pages_searched']}\n")
    print("Extracted from the report (quotes verified on the page):")
    for field, v in out["details"].items():
        if v is None:
            print(f"  {field:24} not stated")
        else:
            ok = "verified" if v["verified"] else "NOT verified"
            print(f"  {field:24} {v['value']!r}  (p.{v['page']}, {ok}): \"{v['quote'][:110]}\"")
    print("\nOfficial records found:")
    for r in out.get("records", []):
        print(f"  {r.get('date')} | {r['kind']} | {r['revision']} | {len(r['sectors'])} sectors | {r['url']}")
    e = out["entry"]
    print("\nRecord used (closest to the report date):")
    if not e:
        print("  no accreditation entry found")
    else:
        print(f"  {e['label']}: {e['url']}  ({e['revision'] or 'revision not stated'})")
        for s in e["sectors"]:
            if s.get("quote") and not s.get("schedule"):
                print(f"    source text: \"{s['quote']}\"")
                break
        for s in e["sectors"]:
            print(f"    sector {s['number']:>2} | {s['name'][:70]} | Category {s['category']} | {s['schedule']}")
    print("\nComparison:")
    for r in out["rows"]:
        s = r["sector"]
        sector = f"sector {s['number']} ({s['name'][:40]}), Category {s['category']}" if s else "none"
        print(f"  {r['component'][:46]:46} -> {sector}: {r['why']}")
    print(f"  validity: {out['validity']}")
    print(f"\nGrade: {out['grade']}")
    for m in out["messages"]:
        print(f"  {m}")
    print(f"\nTavily credits this run: {out['tavily_credits']}; Nebius ${llm.session_cost_usd:.4f}")
    path = ROOT / "cache" / "findings" / pdf.stem / "accreditation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
