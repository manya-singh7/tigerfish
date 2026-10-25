"""Copy-paste check with Tavily: site-specific passages, and a species table's source.

Usage:
  python scripts/check_copypaste.py <pdf> --pages 234,392,... [--table <image>]
         [--max-credits 100] [--dry-run]

Needs the claims ledger (scripts/extract_claims.py) for the pages. The table is read
by Super-VL (cached from scripts/demo_table.py). Prints the estimated Tavily credits
first; every Tavily call is cached in cache/tavily/ (cached calls are free).
"""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import claims, copycheck as cc, llm, pdf_reader, species  # noqa: E402
from extract_claims import parse_pages  # noqa: E402

INDIRA_POINT = (6.75, 93.83)   # used only to rank table names by GBIF rarity


def short(text, n=110):
    text = claims.normalize(str(text))
    return text if len(text) <= n else text[:n - 3] + "..."


def table_names(image):
    table = claims.extract_table_from_image(image)
    if table is None:
        return []
    return [c["value"] for c in claims.species_claims_from_table(table, source=image)]


def rank_names(names):
    """(names rarest first by GBIF global records, names flagged RED/ORANGE at the site).

    GBIF answers are cached from the species check, so this is free after the first run.
    """
    results = {n: species.check_species(n, *INDIRA_POINT) for n in names}
    rarest = sorted(names, key=lambda n: results[n]["global_count"]
                    if results[n]["global_count"] is not None else 10**9)
    flagged = [n for n in names if results[n]["grade"] in ("RED", "ORANGE")]
    return rarest, flagged


def run(pdf, pages_wanted, table=None, max_credits=cc.MAX_TAVILY_CREDITS, dry_run=False):
    pdf = Path(pdf)
    ledger = [c for c in claims.load_ledger(pdf.stem) if c["page"] in pages_wanted]
    pages = {p["page"]: p["text"] for p in pdf_reader.read_pdf(pdf) if p["page"] in pages_wanted}
    passages = cc.select_passages(ledger, pages)
    names = table_names(table) if table else []
    rarest, flagged = rank_names(names) if names else ([], [])
    hunt = cc.hunt_queries(names, rarest, flagged) if names else []
    est = (sum(0 if cc._cache_path("search", search_params(p)).exists() else 2 for p in passages)
           + 2 * len(hunt))
    out = {"passages": passages, "names": names, "flagged": flagged, "hunt_queries": hunt,
           "est_credits": est, "results": [], "hunt": [], "stopped": None}
    if dry_run:
        return out
    budget = cc.Budget(max_credits)
    start = llm.session_cost_usd
    species_names = {str(c["value"]) for c in ledger if c["type"] == "species"}
    out["results"], out["stopped"] = cc.check_passages(passages, budget, species_names)
    if names and not out["stopped"]:
        out["hunt"], out["stopped"] = cc.hunt_species_source(names, budget, rarest, flagged)
    out.update(credits=budget.used, tavily_calls=budget.calls, tavily_cached=budget.cached,
               nebius_cost=llm.session_cost_usd - start)
    return out


def search_params(passage):
    """Same parameters copycheck.search() uses, to tell whether it is cached."""
    return {"query": f'"{cc.distinctive_phrase(passage["text"])}"', "search_depth": "basic",
            "max_results": cc.SEARCH_RESULTS, "exact_match": True,
            "exclude_domains": cc.EXCLUDE_DOMAINS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--pages", required=True)
    parser.add_argument("--table", help="species table image, e.g. data/demo/...png")
    parser.add_argument("--max-credits", type=int, default=cc.MAX_TAVILY_CREDITS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    wanted = set(parse_pages(args.pages))
    plan = run(args.pdf, wanted, args.table, dry_run=True)
    print(f"{len(plan['passages'])} site-specific passages; "
          f"{len(plan['hunt_queries'])} species-hunt queries")
    print(f"Estimated Tavily credits: up to {plan['est_credits']} (cap {args.max_credits}; "
          f"cached calls are free)")
    if args.dry_run:
        for p in plan["passages"]:
            print(f"  p.{p['page']}: \"{cc.distinctive_phrase(p['text'])}\"")
        for q in plan["hunt_queries"]:
            print(f"  hunt: {q}")
        return

    out = run(args.pdf, wanted, args.table, max_credits=args.max_credits)
    print(f"\n=== Passages ({len(out['results'])})")
    flagged = 0
    for r in out["results"]:
        graded = [h for h in r["hits"] if h["grade"] in ("RED", "ORANGE")]
        flagged += len(graded)
        same = sum(h["grade"] == "NONE" for h in r["hits"])
        print(f"p.{r['page']:<5} results={r['results']}  flagged={len(graded)}  "
              f"same-project/generic={same}  \"{r['phrase']}\"")
        for h in graded:
            print(f"    {h['grade']}: {h['message']}")
            print(f"      overlap: longest run {h['longest_run']} words, "
                  f"8-gram {h['ngram']:.0%}; {h['why']}")
            print(f"      ours  p.{r['page']}: {short(r['passage'])}")
            print(f"      theirs: {short(h['snippet'], 200)}")
    print(f"\n{flagged} RED/ORANGE matches.")

    if out["names"]:
        print(f"\n=== Species-list source hunt ({len(out['names'])} names)")
        print("queries: " + " | ".join(out["hunt_queries"]))
        print(f"out-of-place names (flagged by the species check): {', '.join(out['flagged'])}")
        for m in out["hunt"][:10]:
            tag = " [same project / coverage]" if m["same_project"] else ""
            odd = sum(n in out["flagged"] for n in m["names"])
            print(f"  {len(m['names']):2}/{len(out['names'])} names, {odd}/{len(out['flagged'])} "
                  f"out-of-place  {m['url']}{tag}")
            if m["names"]:
                print(f"        {', '.join(m['names'])}")

    if out["stopped"]:
        print(f"\nSTOPPED: {out['stopped']}")
    print(f"\nTavily credits used this run: {out['credits']} "
          f"({out['tavily_calls']} calls, {out['tavily_cached']} from cache)")
    print(f"Nebius cost this run: ${out['nebius_cost']:.4f}")


if __name__ == "__main__":
    main()
