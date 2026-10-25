"""Block G evaluation -> results/eval.json + results/eval.md.

Usage: python scripts/evaluate.py [--max-cost 0.30] [--dry-run]

1. Known cases (data/known_issues.json, from cache): scored issues + negative control.
2. Planted contradictions: 10 restated claims with a different value + 5 "explained"
   differences, inserted into other real pages (in memory, seeded). Claim extraction and
   the contradiction check run on the modified pages only.
3. Planted species: 5 out-of-place + 5 locally recorded species at Indira Point.
4. Table 3.16 vs the Scroll.in article.
5. Cost and speed per check (calls, tokens, API time, cost; cookbook-style table) and an
   estimate for a full 1,213-page audit, in USD and INR.
The whole run stops before new spend would pass --max-cost (default MAX_COST_USD).
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_contradictions  # noqa: E402
import check_copypaste  # noqa: E402
import demo_table  # noqa: E402
from export_results import gaps_by_dir  # noqa: E402
from tigerfish import claims, contradictions, copycheck, evaluation as ev, llm  # noqa: E402
from tigerfish import pdf_reader, species, status, trace  # noqa: E402

MAX_COST_USD = 0.30
SEED = 42
EVAL_MAX_CANDIDATES = 20        # Ultra verdicts for the planted test, planted pairs first
GN_PDF = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"
KNOWN_PAGES = [234, 392, 444, 751, 818, 851, 940, 978, 1141, 1168]
TABLE_IMAGE = ROOT / "data" / "demo" / "indira_point_table_3_16_mammals.png"
INDIRA_POINT = (6.75, 93.83)
RESULTS = ROOT / "results"

OUT_OF_PLACE = {   # name: where it actually lives
    "Hydrocynus vittatus": "Africa (tigerfish)",
    "Semaprochilodus insignis": "South America (Amazon fish)",
    "Erinaceus europaeus": "Europe (hedgehog)",
    "Antilope cervicapra": "mainland India (blackbuck)",
    "Giraffa camelopardalis": "Africa (giraffe)",
}
# Recorded on Great Nicobar; the first 5 with GBIF records within 100 km are used.
REAL_CANDIDATES = ["Macaca fascicularis", "Tupaia nicobarica", "Megapodius nicobariensis",
                   "Dermochelys coriacea", "Crocodylus porosus", "Sus scrofa",
                   "Malayopython reticulatus", "Chelonia mydas"]
SCROLL = {
    "title": "'Fake claims': Great Nicobar lighthouse project study lists species found in "
             "Africa, Amazon",
    "author": "Pankaj Sekhsaria", "date": "31 Aug 2026",
    "url": "https://scroll.in/article/1095311/fake-claims-great-nicobar-lighthouse-project-"
           "study-lists-species-found-in-africa-amazon",
    "quote": "Of the 12 mammals in the table, only three are found on Great Nicobar.",
    "named_mainland": ["Cervus unicolor", "Muntiacus muntjak"],   # sambar, barking deer
}


def load_pages():
    pages = pdf_reader.read_pdf(GN_PDF)
    return {p["page"]: p for p in pages}


# ---------- 1. known cases ----------

def known_cases():
    out = check_contradictions.run(GN_PDF, set(KNOWN_PAGES))
    passed, scored = contradictions.score(out["evaluation"])
    control = [{"pages": f["pages"], "grade": f["grade"], "reason": f["reason"]}
               for f in out["control_findings"]]
    return {"rows": out["evaluation"], "passed": passed, "scored": scored, "control": control}


# ---------- 2. planted contradictions ----------

def planted(pages, ledger, budget_usd, dry_run):
    plants = ev.make_plants(ledger, pages, seed=SEED)
    mod = ev.modified_pages(pages, plants, seed=SEED)
    extract_usd, _ = claims.estimate_cost(list(mod.values()))
    verdict_usd = EVAL_MAX_CANDIDATES * contradictions.EST_OUTPUT_TOKENS * 3.0 / 1e6 \
        + EVAL_MAX_CANDIDATES * 4000 * 1.0 / 1e6          # Ultra: ~4k tokens in, 2k out
    plan = {"plants": plants, "estimate_usd": round(extract_usd + verdict_usd, 4),
            "estimate_extract_usd": round(extract_usd, 4),
            "estimate_verdicts_usd": round(verdict_usd, 4)}
    if dry_run:
        return plan

    start = llm.session_cost_usd
    trace.reset()
    extracted = claims.extract_claims(list(mod.values()), max_cost_usd=budget_usd)
    extract_used = list(trace.used)
    pool = [c for c in ledger if c["page"] in KNOWN_PAGES] + extracted
    texts = {n: pages[n]["text"] for n in KNOWN_PAGES}
    texts.update({n: p["text"] for n, p in mod.items()})
    cands = [c for c in contradictions.candidate_pairs(pool, max_candidates=10**6)
             if any(cl["page"] in mod for cl in c["claims"])]

    def priority(cand):          # pairs linking a plant to its source claim first
        for p in plants:
            ids = {cl["id"] for cl in cand["claims"]}
            if p["source_id"] in ids and any(cl["page"] == p["target_page"] for cl in cand["claims"]):
                return 0
        return 1

    cands.sort(key=priority)
    dropped = max(0, len(cands) - EVAL_MAX_CANDIDATES)
    cands = cands[:EVAL_MAX_CANDIDATES]
    trace.reset()
    left = budget_usd - (llm.session_cost_usd - start)
    findings = contradictions.check(cands, texts, max_cost_usd=left, ledger=pool)
    verdict_used = list(trace.used)
    score = ev.score_plants(plants, findings, extracted, cands)
    for row in score["rows"]:      # say why a miss happened
        plant = next(pl for pl in plants if pl["id"] == row["id"])
        got = [c for c in extracted if c["page"] == plant["target_page"]
               and contradictions.quotes_match(c["quote"], plant["sentence"])]
        if row["stage_missed"] == "extraction":
            row["note"] = "the planted sentence was not extracted as a claim"
        elif row["stage_missed"] == "pairing" and got:
            c = got[0]
            row["note"] = (f"extracted as type '{c['type']}' ({c['value']} {c['unit']}); "
                           f"numeric pairing only compares quantity/count/area/distance claims")
        elif row["stage_missed"] == "verdict":
            row["note"] = "paired, but Ultra did not grade it RED or ORANGE"
    plan.update(score=score, candidates=len(cands), candidates_dropped=dropped,
                stopped=contradictions.last_run.get("stopped"),
                cost_usd=round(llm.session_cost_usd - start, 4),
                usage=[ev.usage_row("Planted test: claim extraction", extract_used),
                       ev.usage_row("Planted test: Ultra verdicts", verdict_used)])
    return plan


# ---------- 3. planted species ----------

def planted_species():
    real, checked = [], {}
    for name in REAL_CANDIDATES:
        r = species.check_species(name, *INDIRA_POINT)
        checked[name] = r
        if r["local_count"]:
            real.append(name)
        if len(real) == 5:
            break
    results = {n: species.check_species(n, *INDIRA_POINT) for n in OUT_OF_PLACE}
    results.update({n: checked[n] for n in real})
    out = ev.score_species(results, list(OUT_OF_PLACE), real)
    for row in out["rows"]:
        row["lives_in"] = OUT_OF_PLACE.get(row["name"], "Great Nicobar")
    return out


# ---------- 4. Table 3.16 vs the article ----------

def table_vs_article():
    _, results = demo_table.run(str(TABLE_IMAGE), *INDIRA_POINT)
    rows = [{"name": c["value"], "gbif_name": r["matched_name"], "grade": r["grade"],
             "local": r["local_count"]} for c, r in results]
    plausible = [r for r in rows if r["grade"] is None]
    flagged = [r for r in rows if r["grade"] in ("RED", "ORANGE")]
    grey = [r for r in rows if r["grade"] == "GREY"]
    named = {r["name"]: r["grade"] for r in rows if r["name"] in SCROLL["named_mainland"]}
    return {"article": SCROLL, "rows": rows, "plausible": [r["name"] for r in plausible],
            "flagged": len(flagged), "grey": len(grey), "others": len(rows) - len(plausible),
            "named_mainland_grades": named}


# ---------- 5. cost and speed ----------

def stage(name, fn):
    trace.reset()
    started = time.time()
    fn()
    used = list(trace.used)
    return used, time.time() - started


def cost_and_speed(pages):
    gaps = gaps_by_dir()
    known = [pages[n] for n in KNOWN_PAGES]
    text_pages = [p for p in known if not p["needs_vision"]]
    vision_pages = [p for p in known if p["needs_vision"]]
    rows = []
    u, _ = stage("text", lambda: claims.extract_claims(text_pages))
    text_row = ev.usage_row(f"Claim extraction, text pages ({len(text_pages)})", u, gaps)
    u, _ = stage("vision", lambda: claims.extract_claims(vision_pages))
    vision_row = ev.usage_row(f"Claim extraction, vision pages ({len(vision_pages)})", u, gaps)
    holder = {}
    u, _ = stage("contra", lambda: holder.update(con=check_contradictions.run(GN_PDF, set(KNOWN_PAGES))))
    con_row = ev.usage_row("Contradiction check (Ultra verdicts)", u, gaps)
    n_cands = len(holder["con"]["candidates"]) + len(holder["con"]["controls"])
    u, _ = stage("copy", lambda: holder.update(cp=check_copypaste.run(GN_PDF, set(KNOWN_PAGES))))
    copy_row = ev.usage_row("Copy-paste check (Lightning)", u, gaps)
    tavily_copy = tavily_credits(u)      # credits the cached responses cost originally
    u, _ = stage("table", lambda: holder.update(tab=demo_table.run(str(TABLE_IMAGE), *INDIRA_POINT)))
    table_row = ev.usage_row("Table reading (Super-VL) + GBIF", u, gaps)
    gbif_calls = ev.other_calls(u, "gbif")
    u, _ = stage("status", lambda: status.check_table(holder["tab"][0], copycheck.Budget(100)))
    status_credits = tavily_credits(u)
    rows += [text_row, vision_row, con_row, copy_row, table_row]

    # ---- extrapolation to the full report ----
    all_pages = list(pages.values())
    hindi = [p for p in all_pages if ev.re.search(r"[ऀ-ॿ]", p["text"])]
    n_total = len(all_pages)
    n_vision = sum(1 for p in all_pages if p["needs_vision"] and p not in hindi)
    n_text = n_total - n_vision - len(hindi)
    per = {
        "text_page_usd": text_row["cost_usd"] / max(1, len(text_pages)),
        "vision_page_usd": vision_row["cost_usd"] / max(1, len(vision_pages)),
        "verdict_usd": con_row["cost_usd"] / max(1, con_row["calls"]),
        "verdicts_per_page": n_cands / len(KNOWN_PAGES),
        "tavily_per_page": tavily_copy / len(KNOWN_PAGES),
        "text_page_s": text_row["seconds"] / max(1, len(text_pages)),
        "vision_page_s": vision_row["seconds"] / max(1, len(vision_pages)),
        "verdict_s": con_row["seconds"] / max(1, con_row["calls"]),
    }
    verdicts = per["verdicts_per_page"] * (n_text + n_vision)
    full_usd = (n_text * per["text_page_usd"] + n_vision * per["vision_page_usd"]
                + verdicts * per["verdict_usd"])
    full_s = (n_text * per["text_page_s"] + n_vision * per["vision_page_s"]
              + verdicts * per["verdict_s"])
    extrapolation = {
        "pages_total": n_total, "pages_text": n_text, "pages_vision": n_vision,
        "pages_hindi_skipped": len(hindi), "per_unit": {k: round(v, 6) for k, v in per.items()},
        "verdicts": round(verdicts), "usd": round(full_usd, 2), "inr": round(ev.inr(full_usd)),
        "api_minutes_sequential": round(full_s / 60), "tavily_credits": round(per["tavily_per_page"] * (n_text + n_vision)),
        "formula": ("cost = text_pages x cost_per_text_page + vision_pages x cost_per_vision_page "
                    "+ (verdicts_per_page x pages) x cost_per_verdict"),
    }
    return {"rows": rows, "tavily_credits": {"copy_paste": tavily_copy, "status": status_credits},
            "gbif_calls": gbif_calls, "extrapolation": extrapolation}


def tavily_credits(used):
    total = 0
    for kind, path in dict.fromkeys(used):
        if kind != "tavily" or not Path(path).exists():
            continue
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        c = (data["data"].get("usage") or {}).get("credits")
        total += c if isinstance(c, (int, float)) else (
            1 if data["endpoint"] == "search" else -(-len(data["params"]["urls"]) // 5))
    return total


# ---------- report ----------

def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def write_md(res):
    k, p, s, t, c = res["known"], res["planted"], res["species"], res["table"], res["cost"]
    sc = p.get("score", {})
    x = c["extrapolation"]
    lines = [
        "# TigerFish evaluation", "",
        f"Generated {res['generated']}. Seed {SEED}. Cost of the evaluation's own API calls "
        f"(planted test, from their token usage): "
        f"${sum(r['cost_usd'] for r in p.get('usage', [])):.4f}; new spend in this run: "
        f"${res['eval_cost_usd']:.4f} (the rest came from cache; cap ${res['max_cost_usd']:.2f}).", "",
        "## Summary", "",
        md_table(["Test", "Result"], [
            ["Known issues (scored)", f"{k['passed']}/{k['scored']} pass"],
            ["Negative control (1045 vs 910 sq km)",
             "not flagged" if all(r["ok"] for r in k["rows"] if r["id"] == "gn-neg-001") else "FLAGGED"],
            ["Planted contradictions caught", f"{sc.get('planted_caught')}/{sc.get('planted_total')}"],
            ["Explained differences wrongly flagged",
             f"{sc.get('explained_wrongly_flagged')}/{sc.get('explained_total')}"],
            ["Other new flags on modified pages", len(sc.get("other_new_flags", []))],
            ["Out-of-place species flagged", f"{s['out_of_place_flagged']}/{s['out_of_place_total']}"],
            ["Locally recorded species wrongly flagged", f"{s['real_wrongly_flagged']}/{s['real_total']}"],
            ["Table 3.16: species judged plausible", f"{len(t['plausible'])} (article: 3)"],
            ["Full 1,213-page audit (estimate)",
             f"${x['usd']:.2f} = Rs {x['inr']:,} at 1 USD = {ev.USD_TO_INR} INR; "
             f"about {x['api_minutes_sequential']} min of API time if run one call at a time"],
        ]), "",
        "## 1. Known issues (data/known_issues.json)", "",
        md_table(["Issue", "Type", "Pages", "Expected", "Grade", "Result", "Status"],
                 [[r["id"], r["type"], r["pages"], "/".join(r["expected"]), r["grade"] or "-",
                   ("PASS" if r["ok"] else "FAIL") + ("" if r["scored"] else " (unscored)"),
                   r["status"] or ""] for r in k["rows"]]), "",
        f"Negative-control pair sent to Ultra directly: "
        f"{', '.join(c['grade'] for c in k['control'])}. "
        + (k["control"][0]["reason"] if k["control"] else ""), "",
        "## 2. Planted contradictions", "",
        f"{sc.get('planted_total')} real numeric claims were restated on other real pages with "
        f"a value x0.5 or x1.5, and {sc.get('explained_total')} with an explicit "
        f"'revised from X to Y after the 2021 survey'. Pages were changed in memory only. "
        f"{p.get('candidates')} candidate pairs were checked ({p.get('candidates_dropped')} "
        f"dropped by the cap of {EVAL_MAX_CANDIDATES}).", "",
        md_table(["Plant", "Kind", "Source p.", "Target p.", "Subject", "Value", "Extracted",
                  "Paired", "Grade", "Result", "Missed at", "Why"],
                 [[r["id"], r["kind"], r["source_page"], r["target_page"], r["subject"],
                   f"{r['source_value']} -> {r['new_value']} {r['unit']}",
                   "yes" if r["extracted"] else "no", "yes" if r["paired"] else "no",
                   r["grade"] or "-", "OK" if r["ok"] else "MISS" if r["kind"] == "planted" else "WRONG FLAG",
                   r["stage_missed"] or "", r.get("note", "")] for r in sc.get("rows", [])]), "",
        "Suggested fix for the pairing miss: treat a statement claim that carries a number and a "
        "unit as a quantity when pairing. Not applied in this run, to keep the known-issue "
        "results unchanged.", "",
        "Other new flags on the modified pages (review by hand):", "",
    ]
    lines += [f"- {o['id']} {o['grade']} pages {o['pages']}: {o['reason']}"
              for o in sc.get("other_new_flags", [])] or ["- none"]
    lines += ["", "## 3. Planted species (Indira Point, 6.75 N 93.83 E)", "",
              md_table(["Species", "Group", "Lives in", "Grade", "GBIF local / 500 km / world"],
                       [[r["name"], r["group"], r["lives_in"], r["grade"] or "plausible",
                         f"{r['local']} / {r['regional']} / {r['global']}"] for r in s["rows"]]), "",
              "## 4. Table 3.16 vs Scroll.in", "",
              f"Scroll.in, \"{t['article']['title']}\", by {t['article']['author']}, "
              f"{t['article']['date']} ({t['article']['url']}): \"{t['article']['quote']}\" "
              f"The article does not name the three; it names the sambar and the barking deer "
              f"as mainland species.", "",
              f"- TigerFish judges **{len(t['plausible'])}** of 12 plausible at the site: "
              f"{', '.join(t['plausible'])}. The count matches the article's three; the names "
              f"cannot be compared because the article does not give them.",
              f"- Of the other {t['others']}: **{t['flagged']}** flagged ORANGE, "
              f"**{t['grey']}** GREY (not enough GBIF survey data to judge).",
              f"- The two species the article names as mainland: "
              + ", ".join(f"{n} {g or 'plausible'}" for n, g in t["named_mainland_grades"].items()) + ".",
              "", md_table(["Name as printed", "GBIF name", "Grade", "GBIF records within 100 km"],
                           [[r["name"], r["gbif_name"], r["grade"] or "plausible", r["local"]]
                            for r in t["rows"]]), "",
              "## 5. Cost and speed", "",
              "Per check, for the 10 known-issue pages and Table 3.16 (table layout from the "
              "Nebius cookbook's agent cost comparison). Time is measured per call where the "
              "call was made after timing was added; older calls use an estimate from cache "
              "file timestamps (marked ~). The ~ values are rough: a gap between cache files "
              "can include idle time (the copy-paste figure is one such case). The planted-test "
              "rows are measured.", "",
              md_table(["Check", "Calls", "In tok", "Out tok", "Tot tok", "Time", "Cost USD", "Cost INR"],
                       [[r["stage"], r["calls"], f"{r['in_tokens']:,}", f"{r['out_tokens']:,}",
                         f"{r['total_tokens']:,}", ("" if r["time_measured"] else "~") + f"{r['seconds']:.0f}s",
                         f"${r['cost_usd']:.4f}", f"Rs {ev.inr(r['cost_usd']):.2f}"]
                        for r in c["rows"] + p.get("usage", [])]), "",
              f"Tavily credits: copy-paste check {c['tavily_credits']['copy_paste']}, status "
              f"check {c['tavily_credits']['status']}. GBIF calls (free): {c['gbif_calls']}.", "",
              "### Full 1,213-page audit (estimate)", "",
              f"Pages: {x['pages_text']} text + {x['pages_vision']} vision; "
              f"{x['pages_hindi_skipped']} Hindi pages skipped.", "",
              f"`{x['formula']}`", "",
              md_table(["Unit", "Value"], [[k2, v] for k2, v in x["per_unit"].items()]), "",
              f"**Estimate: ${x['usd']:.2f} (Rs {x['inr']:,} at 1 USD = {ev.USD_TO_INR} INR, "
              f"labelled rate), about {x['verdicts']:,} Ultra verdicts, about "
              f"{x['api_minutes_sequential']} minutes of API time if run one call at a time "
              f"(less in parallel), and about {x['tavily_credits']:,} Tavily credits for the "
              f"copy-paste check.** This assumes the same density of claims and contradiction "
              f"candidates as the 10 audited pages, and the candidate cap raised accordingly. "
              f"The Ultra verdicts are most of the cost and the main uncertainty: candidate pairs "
              f"can grow faster than the page count across a whole report, so the real number "
              f"could be higher unless the cap stays.", ""]
    (RESULTS / "eval.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cost", type=float, default=MAX_COST_USD)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pages = load_pages()
    ledger = claims.load_ledger(GN_PDF.stem)
    plan = planted(pages, ledger, args.max_cost, dry_run=True)
    print(f"Planted test estimate: ${plan['estimate_usd']:.3f} "
          f"(extraction ${plan['estimate_extract_usd']:.3f} + up to {EVAL_MAX_CANDIDATES} Ultra "
          f"verdicts ${plan['estimate_verdicts_usd']:.3f}); other parts run from cache. "
          f"Cap ${args.max_cost:.2f}.")
    if plan["estimate_usd"] > args.max_cost:
        sys.exit("Estimate is above the cap; lower EVAL_MAX_CANDIDATES or raise --max-cost.")
    if args.dry_run:
        return

    start = llm.session_cost_usd
    res = {"generated": time.strftime("%Y-%m-%d %H:%M"), "seed": SEED, "max_cost_usd": args.max_cost}
    res["known"] = known_cases()
    res["planted"] = planted(pages, ledger, args.max_cost - (llm.session_cost_usd - start), False)
    res["species"] = planted_species()
    res["table"] = table_vs_article()
    res["cost"] = cost_and_speed(pages)
    res["eval_cost_usd"] = round(llm.session_cost_usd - start, 4)
    (RESULTS / "eval.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str),
                                       encoding="utf-8")
    write_md(res)
    print(f"Wrote results/eval.json and results/eval.md. New spend: ${res['eval_cost_usd']:.4f}")


if __name__ == "__main__":
    main()
