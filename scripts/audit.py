"""Full-report audit with a scope filter. Use --dry-run first: it prints the pages kept and
the estimated cost, and calls no model.

Usage:
  python scripts/audit.py <pdf> --scope --dry-run [--top-passages 100]
  python scripts/audit.py <pdf> --scope --run --max-cost 10   (runs the audit: costs money)

--scope skips Hindi pages, lab-report sheets, blank forms and annexure boilerplate
(tigerfish/scope.py) and limits the copy-paste check to the --top-passages most
site-specific passages (default 100, within the Tavily free plan of 1,000 credits/month).
Unit costs (per page, per candidate, triage pass rate) come from results/eval.json,
measured by scripts/evaluate.py; the estimate is labelled as such.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import claims, contradictions, copycheck, evaluation as ev, pdf_reader, scope  # noqa: E402

EVAL = ROOT / "results" / "eval.json"
CREDITS_PER_PASSAGE = 2          # 1 search + up to 1 extract call per passage
TAVILY_FREE_CREDITS = 1000


def estimate(kept, per, top_passages):
    """USD, minutes and Tavily credits for auditing `kept` pages (no model calls)."""
    n_vision = sum(1 for p in kept if p.get("needs_vision"))
    n_text = len(kept) - n_vision
    candidates = per["verdicts_per_page"] * len(kept)
    verdicts = candidates * per["triage_pass_rate"]
    usd = {
        "claims": n_text * per["text_page_usd"] + n_vision * per["vision_page_usd"],
        "triage": candidates * per["triage_usd_per_candidate"],
        "verdicts": verdicts * per["verdict_usd"],
    }
    seconds = (n_text * per["text_page_s"] + n_vision * per["vision_page_s"]
               + candidates * per["triage_s_per_candidate"] + verdicts * per["verdict_s"])
    return {"pages": len(kept), "text_pages": n_text, "vision_pages": n_vision,
            "candidates": round(candidates), "ultra_verdicts": round(verdicts),
            "usd": {k: round(v, 2) for k, v in usd.items()}, "total_usd": round(sum(usd.values()), 2),
            "minutes_sequential": round(seconds / 60),
            "tavily_credits": top_passages * CREDITS_PER_PASSAGE}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--scope", action="store_true", help="skip pages not worth auditing")
    parser.add_argument("--top-passages", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true", help="actually run the audit (costs money)")
    parser.add_argument("--max-cost", type=float, default=contradictions.MAX_COST_USD)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not EVAL.exists():
        sys.exit("results/eval.json is missing: run scripts/evaluate.py first (unit costs).")
    per = json.loads(EVAL.read_text(encoding="utf-8"))["cost"]["extrapolation"]["per_unit"]

    pages = pdf_reader.read_pdf(args.pdf)
    kept, skipped = scope.select_pages(pages) if args.scope else (pages, {})
    print(f"{Path(args.pdf).name}: {len(pages)} pages, {len(kept)} kept"
          + (" (scope on)" if args.scope else " (scope off)"))
    for reason, nums in sorted(skipped.items()):
        shown = ", ".join(map(str, nums[:15])) + (" ..." if len(nums) > 15 else "")
        print(f"  skipped {reason:10} {len(nums):4}  pages {shown}")

    full = estimate(pages, per, args.top_passages)
    est = estimate(kept, per, args.top_passages)
    print(f"\nEstimate (unit costs measured on the audited pages, see results/eval.md):")
    print(f"{'':22} {'pages':>6} {'Ultra verdicts':>15} {'USD':>8} {'INR':>8} {'API min':>8}")
    for label, e in (("all pages", full), ("scoped" if args.scope else "same", est)):
        print(f"{label:22} {e['pages']:>6} {e['ultra_verdicts']:>15,} {e['total_usd']:>8.2f} "
              f"{round(ev.inr(e['total_usd'])):>8,} {e['minutes_sequential']:>8}")
    print(f"  of which: claims ${est['usd']['claims']:.2f}, triage ${est['usd']['triage']:.2f}, "
          f"Ultra verdicts ${est['usd']['verdicts']:.2f}  (1 USD = {ev.USD_TO_INR} INR)")
    print(f"  copy-paste: top {args.top_passages} passages, about {est['tavily_credits']} Tavily "
          f"credits (free plan: {TAVILY_FREE_CREDITS}/month)")
    print("  API minutes assume one call at a time; parallel calls finish sooner.")

    if args.dry_run or not args.run:
        if not args.run:
            print("\nDry run only. Add --run to audit (costs money).")
        return
    # ---- the real run (not used in development; capped) ----
    spent0 = claims.llm.session_cost_usd
    found = claims.extract_claims(kept, max_cost_usd=args.max_cost, pdf_stem=Path(args.pdf).stem)
    texts = {p["page"]: p["text"] for p in kept}
    left = args.max_cost - (claims.llm.session_cost_usd - spent0)
    cands = contradictions.candidate_pairs(found, max_candidates=10**6)
    findings = contradictions.check(cands, texts, max_cost_usd=left, pdf_stem=Path(args.pdf).stem,
                                    ledger=found)
    passages = copycheck.select_passages(found, texts, max_passages=args.top_passages)
    copy, stopped = copycheck.check_passages(passages, copycheck.Budget(args.top_passages * 3),
                                             pages=texts)
    print(f"Done: {len(found)} claims, {len(findings)} verdicts, {len(copy)} passages searched. "
          f"Spent ${claims.llm.session_cost_usd - spent0:.2f}. {stopped or ''}")


if __name__ == "__main__":
    main()
