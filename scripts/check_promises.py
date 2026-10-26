"""Promises check: did the EIA do what its Terms of Reference promised?

Usage: python scripts/check_promises.py [--max-ultra 6] [--budget 0.08]

Prints the estimated cost first, then the promises table, the survey timeline and the cost.
Saves cache/findings/<pdf>/promises.json (for scripts/export_results.py) and
results/<report>_promises.json (promises table + timeline data for the app).
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import llm, pdf_reader, promises as pr, trace  # noqa: E402

REPORT_ID = "great_nicobar_2021_draft"
FINDINGS = ROOT / "cache" / "findings" / pr.EIA_PDF.stem / "promises.json"
RESULTS = ROOT / "results" / f"{REPORT_ID}_promises.json"


def run_cost(used):
    """USD of every model call this run used, cached or not (what a fresh run would cost)."""
    total = 0.0
    for kind, path in dict.fromkeys(used):
        if kind == "llm" and path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            u = d.get("usage") or {}
            total += llm.cost_usd(d.get("model"), u.get("prompt_tokens", 0), u.get("completion_tokens", 0)) or 0
    return round(total, 5)


def show(out):
    print(f"\n{'id':4} {'grade':6} {'verdict':10} {'by':9} {'topic':20} {'promised':>10} {'found':>8}  ToR -> EIA")
    for p in out["promises"]:
        found = "-" if p["found_value"] is None else f"{p['found_value']:g}"
        print(f"{p['id']:4} {p['grade']:6} {p['verdict']:10} {p['verdict_by']:9} {p['topic'][:20]:20} "
              f"{p['measure'][:10]:>10} {found:>8}  p.{p['page']} -> p.{p['eia_page'] or '-'}")
        print(f"     ToR: {p['commitment']}")
        print(f"     EIA: {p['report_describes']}")
    print("\nSurvey timeline (field-study dates found in the EIA):")
    w = out["window"]
    if w:
        print(f"  window  {w['start']} to {w['end']} ({w['days']} days), p.{w['page']}")
    for b in out["timeline"]:
        print(f"  {b['study'][:26]:26} {b['start']} to {b['end']} {b['days']:>4} days  p.{b['page']}"
              f"{' (also ' + ', '.join(map(str, b['pages'][1:6])) + ')' if len(b['pages']) > 1 else ''}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-ultra", type=int, default=pr.MAX_ULTRA)
    parser.add_argument("--budget", type=float, default=pr.BUDGET_USD)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    trace.reset()
    tor = pdf_reader.read_pdf(pr.TOR_PDF, render=False)
    eia = pdf_reader.read_pdf(pr.EIA_PDF)
    out = pr.check(tor, eia, budget=args.budget, max_ultra=args.max_ultra)
    out["cost_usd"] = run_cost(trace.used)
    show(out)

    FINDINGS.parent.mkdir(parents=True, exist_ok=True)
    FINDINGS.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    RESULTS.write_text(json.dumps({"report": REPORT_ID, "tor": pr.TOR_PDF.name, "eia_url": pr.EIA_URL,
                                   "promises": out["promises"], "window": out["window"],
                                   "timeline": out["timeline"]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    grades = {g: sum(p["grade"] == g for p in out["promises"]) for g in ("ORANGE", "INFO", "NONE")}
    print(f"\n{len(out['promises'])} promises {grades}; {out['ultra_calls']} Ultra calls. "
          f"Cost of this check: ${out['cost_usd']:.4f} (new spend this run: ${out['new_spend_usd']:.4f}). "
          f"Saved {FINDINGS.relative_to(ROOT)} and {RESULTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
