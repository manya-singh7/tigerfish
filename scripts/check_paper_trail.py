"""Paper trail: official documents, authority contacts and (if found) the granted ToR check.

Usage:
  python scripts/check_paper_trail.py [--env PATH] [--max-credits 150] [--only REPORT_ID]
                                      [--promises] [--max-usd 0.25]

For every report in results/index.json that has a profile in tigerfish/paper_trail.py:
map + crawl (with instructions) on the official sites, official-domain searches, one step of
document links, extract, keep only documents that name the project or its proposal number.
Prints every Tavily step with the credits Tavily reported for it, then the totals.

--promises: if the granted ToR was found, run the ToR promises check (tigerfish/promises.py)
against it and save results/<report>_promises_granted.json (Nebius; capped by --max-usd).

Saves results/paper_trail_<report>.json. Cached: a re-run costs nothing.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from tigerfish import copycheck, knowable, llm, paper_trail, tavily_usage  # noqa: E402
from tigerfish.ui import data  # noqa: E402


def granted_promises(report_id, trail, raw, max_usd, say=print):
    """Run the promises check on the granted ToR text; returns the saved dict or None."""
    from tigerfish import promises as pr
    tor = trail["granted_tor"]
    text = knowable.plain_text(raw.get(paper_trail.canonical(tor["url"]), ""))
    tor_pages = paper_trail.split_pages(text)
    stem = paper_trail.PROFILES[report_id]["pages"]
    path = paper_trail.PAGES_DIR / stem / "pages.jsonl"
    if not path.exists():
        say(f"  promises: report pages not available locally ({path}); skipped")
        return None
    with path.open(encoding="utf-8") as f:
        eia_pages = [json.loads(line) for line in f]
    for it in pr.tor_items(tor_pages):          # the ToR sentences sent to Lightning
        tavily_usage.used_text(it["quote"], "sent to model")
    start = llm.session_cost_usd
    out = pr.check(tor_pages, eia_pages, budget=max_usd, say=lambda m: say("  " + m))
    spent = llm.session_cost_usd - start
    saved = {"report": report_id, "tor_kind": "granted",
             "tor": f"granted ToR, {tor['title']}", "tor_url": tor["url"], "tor_date": tor["date"],
             "tor_pages": len(tor_pages), "eia_url": pr.EIA_URL, "promises": out["promises"],
             "window": out["window"], "timeline": out["timeline"],
             "nebius_usd_spent_this_run": round(spent, 4), "ultra_calls": out["ultra_calls"]}
    (ROOT / "results" / f"{report_id}_promises_granted.json").write_text(
        json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    grades = {g: sum(p["grade"] == g for p in out["promises"]) for g in ("ORANGE", "INFO", "NONE")}
    say(f"  granted ToR promises: {len(out['promises'])} {grades}; Nebius ${spent:.4f} this run")
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ROOT / ".env"))
    ap.add_argument("--max-credits", type=int, default=150)
    ap.add_argument("--only")
    ap.add_argument("--promises", action="store_true")
    ap.add_argument("--max-usd", type=float, default=0.25)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv(args.env)

    budget = copycheck.Budget(args.max_credits)
    total_usd = llm.session_cost_usd
    for r in data.reports():
        rid = r["id"]
        if rid not in paper_trail.PROFILES or (args.only and rid != args.only):
            continue
        print(f"\n== {rid}")
        report = data.load(rid)
        out = paper_trail.run(rid, report, budget)
        raw = out.pop("_raw")
        for s in out["steps"]:
            what = s.get("site") or s.get("query") or f"{s.get('urls')} URLs"
            print(f"  {s['tool']:18} {str(what)[:70]:70} results {s['results']:>3}  credits {s['credits']}")
        if args.promises and out["granted_tor"]["found"]:
            granted_promises(rid, out, raw, args.max_usd)
            out["efficiency"] = tavily_usage.snapshot()
        paper_trail.path(rid).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        t = out["tavily"]
        print(f"  documents kept: {len(out['documents'])}; dropped: {len(out['dropped'])} {out['drop_counts']}")
        for d in out["documents"]:
            print(f"    {d['date'] or '(no date)':10} {d['type']:28} {d['url'][:110]}")
        print(f"  granted ToR: {'found ' + out['granted_tor']['url'][:90] if out['granted_tor']['found'] else 'not found'}")
        for role, c in out["contacts"].items():
            print(f"  contact {role}: " + (f"{c['body']} | {c['address'][:80]} | {c['email'] or 'no email'} | {c['host']}"
                                          if c.get("found") else f"not found ({c.get('why')})"))
        eff = out["efficiency"]["total"]
        print(f"  Tavily returned {eff['returned']:,} chars; used {eff['used']:,} "
              f"({(eff['share'] or 0):.1%})")
        print(f"  credits (Tavily usage per response): {t['credits']}; new this run: "
              f"{t['credits_spent_this_run']}; cached calls so far: {t['cached_calls']}")
    print(f"\nTotal new Tavily credits this run: {budget.used} (cap {args.max_credits}); "
          f"Nebius this run: ${llm.session_cost_usd - total_usd:.4f}")


if __name__ == "__main__":
    main()
