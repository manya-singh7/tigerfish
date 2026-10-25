"""Run the Investigate agent on saved findings and save the results for replay.

Usage: python scripts/investigate.py [finding_id ...] [--report great_nicobar_2021_draft]
       [--total-cap 0.20]

Each investigation is capped at agent.MAX_COST_USD, MAX_STEPS and MAX_CREDITS; together they
share --total-cap (each run gets an equal share of what is left). Results go to
results/investigations/<report>__<finding>.json. Model calls and Tavily are cached.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import agent, llm, pdf_reader  # noqa: E402
from tigerfish.ui import data  # noqa: E402
from tigerfish.ui.investigate import REPORTS  # noqa: E402

DEFAULT = ["ct-003", "ac-01", "sp-p954-001"]     # gn-001 (coral), accreditation, Panulirus interruptus


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("findings", nargs="*", default=DEFAULT)
    parser.add_argument("--report", default="great_nicobar_2021_draft")
    parser.add_argument("--total-cap", type=float, default=0.20)
    parser.add_argument("--rerender", action="store_true",
                        help="re-render the saved memos (link reasons to evidence); no model calls")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.rerender:
        return rerender(args.report, args.findings)

    report = data.load(args.report)
    pdf, site = REPORTS[args.report]
    pages = pdf_reader.read_pdf(pdf, render=False) if pdf else []
    by_id = {f["id"]: f for f in report["findings"]}
    total = 0.0
    for i, fid in enumerate(args.findings):
        share = (args.total_cap - total) / (len(args.findings) - i)
        cap = min(agent.MAX_COST_USD, share)
        out = agent.investigate(by_id[fid], pages, site=site, report_name=report["title"], max_cost=cap)
        path = agent.save(args.report, out)
        total += out["totals"]["cost_usd"]
        m, t = out["memo"], out["totals"]
        print(f"\n=== {fid}: {out['finding_title']} ({out['mode']}, cap ${cap:.3f})")
        for s in out["trace"]:
            print(f"  {s['step']}. [{(s['tool'] or 'none').upper()}] {s['args']} -> {s['result']}"
                  f"   ({s['tokens_in']}+{s['tokens_out']} tok, ${s['cost_usd']:.4f})")
            if s["reason"]:
                print(f"       why: {s['reason']}")
        print(f"  CONCLUSION: {m['conclusion']}" + (f" (stopped: {m['stopped']})" if m["stopped"] else ""))
        for r in m["reasons"]:
            print(f"   - {r}")
        print("  Checked: " + "; ".join(m["checked"]))
        for e in m["evidence"]:
            where = f"p.{e['page']}" if e.get("page") else e["url"]
            print(f"   [{where}] \"{e['quote'][:200]}\" -> {e['note']}")
        print(f"  dropped unverified quotes: {len(m['dropped_quotes'])}")
        print(f"  totals: {t}  -> {path.relative_to(ROOT)}")
    print(f"\nTotal model cost (as if uncached): ${total:.4f}; new API spend this run: ${llm.session_cost_usd:.4f}")


def rerender(report_id, finding_ids):
    for fid in finding_ids:
        inv = agent.load(report_id, fid)
        if inv is None:
            print(f"{fid}: no saved investigation")
            continue
        inv.pop("report_id", None)
        inv["memo"] = agent.relink_memo(inv["memo"])
        agent.save(report_id, inv)
        m = inv["memo"]
        print(f"\n=== {fid}: {m['conclusion']}")
        for e in [*m["evidence"], *m["data"]]:
            where = f"p.{e['page']}" if e.get("page") else (e.get("url") or e.get("source"))
            print(f"  {e['id']}  [{where}] {(e.get('quote') or e.get('value'))[:110]}")
        print("  Reasons (supported):")
        for r in m["reasons"]:
            print(f"   - {r['text']}  [{', '.join(r['evidence'])}]")
        print("  Unverified reasoning (not checked):")
        for r in m["unverified_reasons"]:
            print(f"   - {r}")


if __name__ == "__main__":
    main()
