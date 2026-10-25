"""Contradiction check on a PDF's claims ledger, with evaluation against known issues.

Usage:
  python scripts/check_contradictions.py <pdf> --pages 234,392,... [--max-cost 0.50] [--dry-run]

Needs the ledger from scripts/extract_claims.py for the same pages.
Prints the estimated cost first (cached verdicts are free) and the real cost at the end.
If data/known_issues.json is about this PDF, also prints the evaluation table, the
verdict on the negative-control pair, and every other flag for review by hand.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import claims, contradictions as ct, llm, pdf_reader  # noqa: E402
from extract_claims import parse_pages  # noqa: E402

KNOWN_ISSUES = ROOT / "data" / "known_issues.json"


def known_issues_for(pdf):
    if not KNOWN_ISSUES.exists():
        return []
    data = json.loads(KNOWN_ISSUES.read_text(encoding="utf-8"))
    return data["issues"] if Path(data["document"]).name == Path(pdf).name else []


def run(pdf, pages_wanted, max_cost=ct.MAX_COST_USD, dry_run=False):
    """Returns a dict with candidates, findings, controls, evaluation, cost."""
    pdf = Path(pdf)
    ledger = [c for c in claims.load_ledger(pdf.stem) if c["page"] in pages_wanted]
    pages = {p["page"]: p["text"] for p in pdf_reader.read_pdf(pdf) if p["page"] in pages_wanted}
    cands = ct.candidate_pairs(ledger)
    known = known_issues_for(pdf)
    controls = [ct.control_candidate(i) for i in known
                if i["expected_grade"] == "NONE" and set(i["pages"]) <= set(pages)]
    est, uncached = ct.estimate_cost(cands + controls, pages)
    out = {"ledger": len(ledger), "candidates": cands, "controls": controls,
           "estimate": est, "uncached": uncached, "findings": [], "control_findings": [],
           "evaluation": [], "known": known}
    if dry_run:
        return out
    start = llm.session_cost_usd
    out["findings"] = ct.check(cands, pages, max_cost_usd=max_cost, pdf_stem=pdf.stem,
                               ledger=ledger)
    out["stopped"] = ct.last_run.get("stopped")
    left = max_cost - (llm.session_cost_usd - start)
    out["control_findings"] = ct.check(controls, pages, max_cost_usd=left) if controls else []
    out["evaluation"] = ct.evaluate(out["findings"], known) if known else []
    out["cost"] = llm.session_cost_usd - start
    return out


def short(text, n=70):
    text = claims.normalize(str(text))
    return text if len(text) <= n else text[:n - 3] + "..."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--pages", required=True, help="e.g. 234,392,400-402")
    parser.add_argument("--max-cost", type=float, default=ct.MAX_COST_USD)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    wanted = set(parse_pages(args.pages))
    first = run(args.pdf, wanted, dry_run=True)
    kinds = {}
    for c in first["candidates"]:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print(f"{first['ledger']} claims on {len(wanted)} pages -> {len(first['candidates'])} "
          f"candidates {kinds} (+{len(first['controls'])} negative-control pair)")
    if ct.last_run.get("candidates_suppressed"):
        print(f"  {ct.last_run['candidates_suppressed']} numeric pairs suppressed "
              f"(already covered by a recycled-figure group)")
    if ct.last_run.get("candidates_dropped"):
        print(f"  {ct.last_run['candidates_dropped']} candidates dropped by MAX_CANDIDATES")
    print(f"{first['uncached']} Ultra calls needed. Estimated cost: ${first['estimate']:.4f} "
          f"(cap ${args.max_cost:.2f})")
    if args.dry_run:
        return

    out = run(args.pdf, wanted, max_cost=args.max_cost)
    print(f"\n{'id':7} {'grade':6} {'type':15} {'pages':16} reason")
    for f in out["findings"]:
        tag = " [part-vs-total]" if f.get("part_total") else ""
        print(f"{f['id']:7} {f['grade']:6} {f['type']:15} {str(f['pages']):16} "
              f"{short(f['reason'], 90)}{tag}")

    if out["known"]:
        print("\n=== Evaluation against data/known_issues.json")
        print(f"{'issue':11} {'type':17} {'pages':16} {'expected':11} {'found':6} {'grade':7} "
              f"{'result':12} status")
        for r in out["evaluation"]:
            result = ("PASS" if r["ok"] else "FAIL") + ("" if r["scored"] else " (unscored)")
            print(f"{r['id']:11} {r['type']:17} {str(r['pages']):16} {'/'.join(r['expected']):11} "
                  f"{'yes' if r['found'] else 'no':6} {str(r['grade']):7} {result:12} "
                  f"{r['status'] or ''}")
        passed, scored = ct.score(out["evaluation"])
        print(f"Score: {passed}/{scored} scored issues pass "
              f"(under_review / candidate_new_finding are printed but not scored)")
        for f in out["control_findings"]:
            print(f"\nNegative-control pair {f['pages']} sent to Ultra directly: grade {f['grade']}"
                  f" -> {'PASS (not flagged)' if f['grade'] == 'NONE' else 'FAIL (flagged)'}")
            print(f"  reason: {f['reason']}")
            if f["explanation_quote"]:
                print(f"  explanation (p.{f['explanation_page']}): {short(f['explanation_quote'], 140)}")

        matched = {r["finding_id"] for r in out["evaluation"] if r["finding_id"]}
        others = [f for f in out["findings"] if f["id"] not in matched and f["grade"] != "NONE"]
        print(f"\n=== Other flags on these pages, for review by hand ({len(others)})")
        for f in others:
            print(f"{f['id']} {f['grade']} {f['type']} pages {f['pages']}: {f['reason']}")
            for q in f["quotes"]:
                mark = " (re-selected to match reason)" if q.get("reselected") else ""
                print(f"    p.{q['page']}: {short(q['text'], 110)}{mark}")
            if f.get("evidence_note"):
                print(f"    note: {f['evidence_note']}")
        none_count = sum(f["grade"] == "NONE" for f in out["findings"])
        print(f"\n({none_count} candidates judged NONE: explained or different scope)")

    if out.get("stopped"):
        print(f"\nSTOPPED: {out['stopped']}")
    print(f"\nReal API cost this run: ${out['cost']:.4f}")
    print(f"Findings: {ct.FINDINGS_DIR / Path(args.pdf).stem / 'contradictions.jsonl'}")


if __name__ == "__main__":
    main()
