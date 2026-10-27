"""Full-report audit with a scope filter. Use --dry-run first: it prints the pages kept and
the estimated cost, and calls no model.

Usage:
  python scripts/audit.py <pdf> --scope --dry-run [--top-passages 100]
  python scripts/audit.py <pdf> --scope --run --max-cost 10   (runs the audit: costs money)
  python scripts/audit.py <pdf> --pages 250-350 --scope --triage safe --run --max-cost 1.50
                                                              (rehearsal on a page range)

--scope skips Hindi pages, lab-report sheets, blank forms and annexure boilerplate
(tigerfish/scope.py) and limits the copy-paste check to the --top-passages most
site-specific passages (default 100, within the Tavily free plan of 1,000 credits/month).
Unit costs (per page, per candidate, triage pass rate) come from results/eval.json,
measured by scripts/evaluate.py; the estimate is labelled as such.

--run: model calls run in parallel (tigerfish.llm.WORKERS threads) and every reply is
cached, so an interrupted run is resumed by running the same command again (cached calls
are free). After claim extraction the real candidate count is known and a second,
cache-aware estimate is printed. The run report (cost, wall-clock time per stage, calls
per model, findings by check and grade) goes to results/audit_<name>.json and .md.
A --pages run keeps its ledger and findings under its own name, e.g.
cache/findings/<stem>__p250-350/, so it never overwrites the evaluation's files.
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from tigerfish import claims, contradictions, copycheck, evaluation as ev, llm, pdf_reader, promises, scope  # noqa: E402
from tigerfish import pairing  # noqa: E402
from check_contradictions import known_issues_for  # noqa: E402
from extract_claims import parse_pages  # noqa: E402

EVAL = ROOT / "results" / "eval.json"
RESULTS = ROOT / "results"
CREDITS_PER_PASSAGE = 2          # 1 search + up to 1 extract call per passage
TAVILY_FREE_CREDITS = 1000


def estimate(kept, per, top_passages, triage="safe"):
    """USD, minutes and Tavily credits for auditing `kept` pages (no model calls).

    triage: "safe" (two views; nothing real dropped in validation) or "fast" (quotes
    only; cheaper, but it dropped a real ORANGE in validation).
    """
    sfx = "_fast" if triage == "fast" else ""
    n_vision = sum(1 for p in kept if p.get("needs_vision"))
    n_text = len(kept) - n_vision
    candidates = per["verdicts_per_page"] * len(kept)
    verdicts = candidates * per.get("triage_pass_rate" + sfx, per["triage_pass_rate"])
    triage_usd = per.get("triage_usd_per_candidate" + sfx, per["triage_usd_per_candidate"])
    triage_s = per.get("triage_s_per_candidate" + sfx, per["triage_s_per_candidate"])
    usd = {
        "claims": n_text * per["text_page_usd"] + n_vision * per["vision_page_usd"],
        "triage": candidates * triage_usd,
        "verdicts": verdicts * per["verdict_usd"],
    }
    seconds = (n_text * per["text_page_s"] + n_vision * per["vision_page_s"]
               + candidates * triage_s + verdicts * per["verdict_s"])
    return {"pages": len(kept), "text_pages": n_text, "vision_pages": n_vision,
            "candidates": round(candidates), "ultra_verdicts": round(verdicts),
            "usd": {k: round(v, 2) for k, v in usd.items()}, "total_usd": round(sum(usd.values()), 2),
            "minutes_sequential": round(seconds / 60),
            "tavily_credits": top_passages * CREDITS_PER_PASSAGE}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--pages", help="page range to audit, e.g. 250-350 (default: all)")
    parser.add_argument("--scope", action="store_true", help="skip pages not worth auditing")
    parser.add_argument("--top-passages", type=int, default=100)
    parser.add_argument("--triage", choices=["safe", "fast"], default="safe",
                        help="safe: quotes + page context (default); fast: quotes only")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true", help="actually run the audit (costs money)")
    parser.add_argument("--max-cost", type=float, default=contradictions.MAX_COST_USD)
    parser.add_argument("--triage-audit", type=int, default=0, metavar="N",
                        help="also send N random triage-dropped pairs to Ultra and report grades")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not EVAL.exists():
        sys.exit("results/eval.json is missing: run scripts/evaluate.py first (unit costs).")
    per = json.loads(EVAL.read_text(encoding="utf-8"))["cost"]["extrapolation"]["per_unit"]

    pages = pdf_reader.read_pdf(args.pdf)
    if args.pages:
        wanted = set(parse_pages(args.pages))
        pages = [p for p in pages if p["page"] in wanted]
    kept, skipped = scope.select_pages(pages) if args.scope else (pages, {})
    print(f"{Path(args.pdf).name}: {len(pages)} pages, {len(kept)} kept"
          + (" (scope on)" if args.scope else " (scope off)"))
    for reason, nums in sorted(skipped.items()):
        shown = ", ".join(map(str, nums[:15])) + (" ..." if len(nums) > 15 else "")
        print(f"  skipped {reason:10} {len(nums):4}  pages {shown}")

    est = estimate(kept, per, args.top_passages, args.triage)
    print(f"\nEstimate (unit costs measured on the audited pages, see results/eval.md):")
    print(f"{'':30} {'pages':>6} {'Ultra verdicts':>15} {'USD':>8} {'INR':>8} {'API min':>8}")
    rows = [("all pages", pages)] + ([("scoped", kept)] if args.scope else [])
    for mode in ("safe", "fast"):
        for label, sel in rows:
            e = estimate(sel, per, args.top_passages, mode)
            mark = "  <- selected" if mode == args.triage and sel is kept else ""
            print(f"{label + ', ' + mode + ' triage':30} {e['pages']:>6} "
                  f"{e['ultra_verdicts']:>15,} {e['total_usd']:>8.2f} "
                  f"{round(ev.inr(e['total_usd'])):>8,} {e['minutes_sequential']:>8}{mark}")
    val = json.loads(EVAL.read_text(encoding="utf-8"))["known"]["triage_validation"]
    print(f"  safe: quotes + page context; RED/ORANGE dropped in validation: {len(val['violations'])}")
    print(f"  fast: quotes only, cheaper; RED/ORANGE dropped in validation: "
          f"{val.get('fast_violations', '?')} (see results/eval.md, triage cascade)")
    print(f"  of which: claims ${est['usd']['claims']:.2f}, triage ${est['usd']['triage']:.2f}, "
          f"Ultra verdicts ${est['usd']['verdicts']:.2f}  (1 USD = {ev.USD_TO_INR} INR)")
    print(f"  copy-paste: top {args.top_passages} passages, about {est['tavily_credits']} Tavily "
          f"credits (free plan: {TAVILY_FREE_CREDITS}/month)")
    print(f"  API minutes assume one call at a time; --run uses {llm.WORKERS} parallel calls.")

    if args.dry_run or not args.run:
        if not args.run:
            print("\nDry run only. Add --run to audit (costs money).")
        return
    run_audit(args, kept, per)


def run_audit(args, kept, per):
    """The real run (capped). Prints and saves the run report."""
    stem = Path(args.pdf).stem
    name = f"{stem}__p{args.pages}" if args.pages else stem
    contradictions.TRIAGE_MODE = args.triage
    spent0, wall0 = llm.session_cost_usd, time.perf_counter()
    stages = {}

    def stage(label, t0, c0):
        stages[label] = {"seconds": round(time.perf_counter() - t0, 1),
                         "usd": round(llm.session_cost_usd - c0, 4)}
        print(f"== {label}: {stages[label]['seconds']}s, ${stages[label]['usd']:.4f}")

    t0, c0 = time.perf_counter(), llm.session_cost_usd
    found = claims.extract_claims(kept, max_cost_usd=args.max_cost, pdf_stem=name)
    stage("claims", t0, c0)
    if claims.last_run.get("stopped"):
        print(f"Stopped: {claims.last_run['stopped']}")

    texts = {p["page"]: p["text"] for p in kept}
    tor = (contradictions.tor_location_counts(promises.TOR_PDF)
           if Path(args.pdf).name == promises.EIA_PDF.name else ())
    cands = contradictions.candidate_pairs(found, max_candidates=10**6, tor_counts=tor, keyed=True)
    st = pairing.last_stats
    print(f"Pairing: {st.get('numeric_claims')} numeric claims -> {st.get('groups')} subject groups, "
          f"{st.get('representatives')} distinct values; {st.get('pairs_same_key')} same-key + "
          f"{st.get('pairs_part_whole')} part>whole pairs; {st.get('dropped_by_cap')} dropped by the "
          f"per-group cap; {st.get('readings_without_station')} readings without a station not paired")
    ultra_all, uncached = contradictions.estimate_cost(cands, texts)
    rate = per.get("triage_pass_rate" + ("_fast" if args.triage == "fast" else ""),
                   per["triage_pass_rate"])
    spent = llm.session_cost_usd - spent0
    print(f"\nMeasured: {len(found)} claims, {len(cands)} candidate pairs "
          f"({uncached} without a cached verdict). Second estimate: Ultra verdicts about "
          f"${ultra_all * rate:.2f} (triage pass rate {rate:.2f}); spent so far ${spent:.2f}; "
          f"cap ${args.max_cost:.2f}.")
    if spent + ultra_all * rate > args.max_cost:
        print("  The cap will stop the Ultra verdicts partway (candidate order: recycled, "
              "statements, numeric).")

    t0, c0 = time.perf_counter(), llm.session_cost_usd
    left = args.max_cost - (llm.session_cost_usd - spent0)
    findings = contradictions.check(cands, texts, max_cost_usd=left, pdf_stem=name,
                                    ledger=found)
    stage("triage + verdicts", t0, c0)
    if not args.pages:   # the 10-page evaluation rewrites <stem>/contradictions.jsonl; keep a copy
        contradictions.save_findings(f"{stem}/full_run", findings)
    con_run = dict(contradictions.last_run)
    audit = triage_audit(args, cands, con_run, texts, found, spent0) if args.triage_audit else None

    t0, c0 = time.perf_counter(), llm.session_cost_usd
    budget = copycheck.Budget(args.top_passages * 3)
    passages = copycheck.select_passages(found, texts, max_passages=args.top_passages)
    copy, copy_stopped = copycheck.check_passages(passages, budget, pages=texts)
    stage("copy-paste", t0, c0)

    report = build_report(args, name, kept, found, cands, findings, con_run, copy, budget,
                          copy_stopped, stages, llm.session_cost_usd - spent0,
                          time.perf_counter() - wall0)
    report["triage_audit"] = audit
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"audit_{name}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS / f"audit_{name}.md").write_text(report_md(report), encoding="utf-8")
    print("\n" + report_md(report))
    print(f"Saved {out.relative_to(ROOT)} and .md")


def triage_audit(args, cands, con_run, texts, found, spent0, seed=42):
    """Ultra verdicts on a random sample of the pairs triage dropped (not saved as findings)."""
    dropped = [c for c, a in zip(cands, con_run.get("triage_answers") or []) if a == "no"]
    sample = random.Random(seed).sample(dropped, min(args.triage_audit, len(dropped)))
    left, c0 = args.max_cost - (llm.session_cost_usd - spent0), llm.session_cost_usd
    got = contradictions.check(sample, texts, max_cost_usd=left, ledger=found, use_triage=False)
    grades = {g: sum(f["grade"] == g for f in got) for g in ("RED", "ORANGE", "NONE")}
    print(f"== triage audit: {len(got)} of {len(dropped)} dropped pairs checked by Ultra: {grades}")
    return {"dropped": len(dropped), "sampled": len(sample), "checked": len(got), "grades": grades,
            "cost_usd": round(llm.session_cost_usd - c0, 4),
            "flagged": [{"pages": f["pages"], "grade": f["grade"], "reason": f["reason"],
                         "quotes": [{"page": q["page"], "text": q["text"]} for q in f["quotes"]]}
                        for f in got if f["grade"] in ("RED", "ORANGE")]}


def build_report(args, name, kept, found, cands, findings, con_run, copy, budget,
                 copy_stopped, stages, spent, wall_s):
    known_ids = {}
    for issue in known_issues_for(args.pdf):
        f = contradictions.match_issue(issue, findings)
        if f:
            known_ids[f["id"]] = issue["id"]
    by_check = {}
    for f in findings:
        row = by_check.setdefault(f["type"], {"RED": 0, "ORANGE": 0, "NONE": 0})
        row[f["grade"]] = row.get(f["grade"], 0) + 1
    copy_rows = []
    for r in copy:   # one row per passage; matching documents listed under it
        grade, hits = copycheck.flagged_hits(r)
        row = by_check.setdefault("copy_paste", {})
        row[grade or "NONE"] = row.get(grade or "NONE", 0) + 1
        if grade:
            copy_rows.append({"id": f"cp-p{r['page']}-{len(copy_rows) + 1}",
                              "grade": grade, "type": "copy_paste", "pages": [r["page"]],
                              "quotes": [{"page": r["page"], "text": r["passage"]}],
                              "reason": hits[0]["why"],
                              "urls": [f"{h['grade']} {h['url']}" for h in hits]})
        if r["borrowed"]:
            row = by_check.setdefault("borrowed_text", {"count": 0})
            row["count"] += len(r["borrowed"])
    flagged = [f for f in findings if f["grade"] in ("RED", "ORANGE")] + copy_rows
    new = [f for f in flagged if f["id"] not in known_ids]
    new.sort(key=lambda f: ({"RED": 0, "ORANGE": 1}[f["grade"]], f["id"]))
    return {
        "pdf": Path(args.pdf).name, "name": name, "pages": args.pages, "triage": args.triage,
        "workers": llm.WORKERS, "max_cost_usd": args.max_cost,
        "pages_audited": len(kept), "claims": len(found), "candidates": len(cands),
        "triage_answers": con_run.get("triage"), "verdicts": con_run.get("verdicts"),
        "verdicts_failed": con_run.get("failed"), "stopped": con_run.get("stopped"),
        "copy_passages": len(copy), "copy_stopped": copy_stopped,
        "copy_passage_list": [{"page": r["page"], "text": r["passage"],
                               "claim_ids": r["claim_ids"]} for r in copy],
        "pairing": {k: v for k, v in pairing.last_stats.items() if k != "dropped_groups"},
        "pairing_dropped_by_cap": pairing.last_stats.get("dropped_groups", []),
        "cost_usd": round(spent, 4), "wall_clock_s": round(wall_s, 1), "stages": stages,
        "calls_per_model": {m: {k: round(v, 4) if isinstance(v, float) else v
                                for k, v in st.items()} for m, st in llm.call_stats.items()},
        "tavily": {"calls": budget.calls, "cached": budget.cached, "credits": budget.used},
        "retries": dict(llm.retry_stats),
        "findings_by_check": by_check, "known_issues_matched": known_ids,
        "new_flagged": len(new),
        "flags": [{"id": f["id"], "grade": f["grade"], "type": f["type"], "pages": f["pages"],
                   "quotes": [{"page": q["page"], "text": q["text"],
                               **({"also_on": q["also_on"]} if q.get("also_on") else {})}
                              for q in f["quotes"]],
                   "reason": f["reason"], "part_total": f.get("part_total"),
                   "answers": {k: f.get(k) for k in ("same_subject", "same_place", "same_scope",
                                                     "incompatible", "explained") if k in f},
                   "urls": f.get("urls")}
                  for f in new],
    }


def report_md(r):
    lines = [f"# Audit run: {r['pdf']}, pages {r['pages'] or 'all'}", "",
             f"Pairing: {r.get('pairing')}", "",
             f"Pages audited {r['pages_audited']}, claims {r['claims']}, candidate pairs "
             f"{r['candidates']}, triage {r['triage_answers']}, Ultra verdicts {r['verdicts']} "
             f"(failed {r['verdicts_failed']}), copy-paste passages {r['copy_passages']}.", "",
             f"**Cost ${r['cost_usd']:.4f}** (INR {ev.inr(r['cost_usd']):.0f}), "
             f"**wall clock {r['wall_clock_s'] / 60:.1f} min** with {r['workers']} workers. "
             f"Cap ${r['max_cost_usd']:.2f}. Stopped: {r['stopped'] or 'no'}.", "",
             "| Stage | Seconds | USD |", "|---|---:|---:|"]
    lines += [f"| {k} | {v['seconds']} | {v['usd']:.4f} |" for k, v in r["stages"].items()]
    lines += ["", "| Model | API calls | Cache hits | Tokens in | Tokens out | USD | API seconds |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {m.split('/')[-1]} | {s['api_calls']} | {s['cache_hits']} | "
              f"{s['prompt_tokens']:,} | {s['completion_tokens']:,} | {s['cost_usd']:.4f} | "
              f"{s['api_seconds']:.0f} |" for m, s in r["calls_per_model"].items()]
    t = r["tavily"]
    lines += [f"| Tavily | {t['calls']} | {t['cached']} | | | {t['credits']} credits | |", "",
              f"Retries: {r['retries']}", "", "Findings by check and grade:", ""]
    lines += [f"- {k}: {v}" for k, v in r["findings_by_check"].items()]
    lines += ["", f"Known issues matched: {r['known_issues_matched'] or 'none'}", "",
              f"## All {r['new_flagged']} new RED/ORANGE flags", ""]
    for f in r["flags"]:
        lines.append(f"**{f['id']} {f['grade']}** ({f['type']}, pages {f['pages']})")
        lines += [f"- p.{q['page']}: \"{q['text']}\""
                  + (f" (also on pp. {', '.join(map(str, q['also_on']))})" if q.get("also_on") else "")
                  for q in f["quotes"]]
        lines.append(f"- Why: {f['reason']}")
        if f.get("answers"):
            lines.append(f"- Ultra's answers: {f['answers']}")
        lines += [f"- Match: {u}" for u in f.get("urls") or []] + [""]
    a = r.get("triage_audit")
    if a:
        lines += ["## Triage audit", "",
                  f"{a['checked']} of {a['dropped']} triage-dropped pairs (random sample) sent to "
                  f"Ultra: {a['grades']}", ""]
        for f in a["flagged"]:
            lines.append(f"- {f['grade']} pages {f['pages']}: {f['reason']}")
            lines += [f"  - p.{q['page']}: \"{q['text']}\"" for q in f["quotes"]]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
