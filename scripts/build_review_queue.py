"""Build review/review_queue.json: every new RED/ORANGE flag of the full audit, for review
by hand in the app's Review tab.

Usage: python scripts/build_review_queue.py      (no API calls; run after export_results.py)

Order: the TOP 30 below first (hand-picked: distinct issues, most consequential first),
then all other flags in a random order with a fixed seed, so the reviewed part of the rest
is a fair sample. DOUBLE flags (15 of the top 30) are judged by both reviewers
independently; the app hides the other reviewer's decision until both have decided.
The quick reads are Claude's (results/full_audit_summary.md); they are not put in the
queue, so reviewers judge without them.
"""

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import contradictions as ct  # noqa: E402
from tigerfish import review  # noqa: E402
from tigerfish.report import CHECK_NAMES  # noqa: E402

AUDIT = ROOT / "results" / "audit_great_nicobar_2021_draft_eia.json"
EXPORT = ROOT / "results" / "great_nicobar_2021_draft.json"
SEED = 42

# (flag id, quick read, why) in review order
TOP30 = [
    ("ct-071", "likely real", "p.1085 lists 117 scleractinian coral species and 17.46% live coral cover "
               "in Galathea Bay; p.738 says, citing ZSI, that coral does not exist in the Galathea Bay area."),
    ("ct-056", "likely real", "Same coral question as gn-001: p.978 (EIA form) says coral reef exists in "
               "the port site; p.738 says no coral in the Galathea Bay area."),
    ("ct-1645", "likely real", "Airport reclamation: 71 ha (p.446) vs 194 ha (p.438, and p.444 'the airport "
                "... total reclaimed land will be 194 ha'). Both tie the figure to the airport, so "
                "part-of-total (TODO ct-005) looks less likely."),
    ("ct-1464", "likely real", "Same sentence on p.133 and p.438, but '1.94 Ha' vs '194 Ha': a decimal or "
                "unit slip on p.133 (p.972 has 1.94 sq km = 194 ha)."),
    ("ct-783", "likely real", "Airport cost Rs 10,35,900 lakh (p.919, the ToR letter) vs Rs 8,58,300 lakh "
               "(p.725 cost table) and Rs 8,583 crore (p.24). Cost changed between ToR and EIA, unexplained."),
    ("ct-1086", "likely real", "p.87 says the breakwaters are 3.90 km long and, a few lines later, 3.27 km "
                "(2.53 + 0.74). Both on the same page."),
    ("ct-221", "likely real", "Two land-use charts with the same 166.10 sq km total but different "
               "categories (residential 36.66 vs 16.55 sq km). One of ~12 flags on p.918 vs p.972."),
    ("ct-217", "likely real", "Great Nicobar Biosphere Reserve 732.79 sq km (p.22 table) vs 885 sq km "
               "(pp.26, 938, 314; core 705 + buffer 180). 732.79 matches neither."),
    ("ct-225", "likely real", "Campbell Bay NP 426.23 sq km (p.26) vs 520 km2 (p.942, ZSI annexure); p.22 "
               "has a third value, 391.75."),
    ("ct-226", "likely real", "Galathea NP 107.10 sq km (p.22) vs 185 km2 (p.942)."),
    ("ct-1607", "likely real", "Island area 910.074 sq km vs 973 km2 (p.1115, annexure); p.243 has a third "
                "figure, 921 km2. Likely sources quoted without reconciling."),
    ("ct-1254", "likely real", "p.228 says Great Nicobar is about 700 km north of Sumatra; pp.19, 942 say "
                "144-145 km. 700 km is wrong (p.942 also says '60 N', another slip)."),
    ("ct-1176", "likely real", "Mangroves 1.842 sq km (184 ha) for the whole island (p.243 table) vs "
                "3,337 ha 'in the study area' (p.249); p.249 also says 0.01% of forest area."),
    ("ct-673", "likely real", "Leatherback nests 2018-19: 203 in the tables (pp.1037, 1126) vs '103 nests "
               "in 2018-19' in the text (p.1047). Probably a typo."),
    ("ct-239", "likely real", "Rainfall 3000-3500 cm (p.291) vs 300-350 cm (p.337): unit error, likely mm "
               "(already in TODO)."),
    ("ct-1385", "likely real", "Power plant land 39 hectares (pp.207, 485, 581, 975) vs 39 acres (p.210)."),
    ("ct-200", "likely real", "Airport power: DG sets of 2 x 5 MVA (p.134) vs the air-quality model run "
               "with 7 DG sets (p.459, airport chapter)."),
    ("ct-812", "likely real", "Water sampling: 10 SW + 10 GW planned (p.45) vs 8 + 8 examined (p.279). "
               "Same as ToR promise pr-13."),
    ("ct-414", "likely real", "Mammal species on the island: 14 (p.29) vs 25 (p.324); also 28 on p.1168. "
               "Different literature sources, never reconciled."),
    ("ct-387", "likely real", "Bird species: 71 (p.29) vs 97 (p.1168); p.327 says about 90."),
    ("ct-1625", "needs a look", "Total project area 16,610 ha vs '14,960 Ha and Power Plant' (p.1088 starts "
                "mid-sentence). Read p.1087: 14,960 ha may be one component."),
    ("ct-617", "possible false alarm", "Airport 4000 PHP (title) vs 1036 PHP for the 'airstrip ... Code C' "
               "(p.109). Could be an initial phase; check p.109's context."),
    ("ct-402", "possible false alarm", "Fauna 695 species (p.940) vs over 1800 (p.944). p.944's 1800 "
               "includes invertebrates; different scopes and sources."),
    ("ct-209", "possible false alarm", "Control points 2 (p.743, power plant plan) vs 10 (p.770, full "
               "operation): probably different components, not a contradiction."),
    ("ct-1106", "possible false alarm", "15 vs 14.2 million TEU. p.1051 describes the Casuarina Bay site "
                "option in the site-selection annexure, not the chosen site."),
    ("ct-240", "false alarm", "ICTT cost 'Rs. 35,95,900' at the end of p.918 continues 'lakhs.' on p.919: "
               "35,95,900 lakh = 35,959 crore, the same figure as p.24."),
    ("ct-604", "false alarm", "Both pages have the identical sentence ('east & west breakwater extends till "
               "the 20 m & 25 m contour'). Ultra misread it."),
    ("ct-1366", "false alarm", "The 13 berths on p.391 are at Dhamra port (Odisha), cited as an example; "
                "not this project."),
    ("ct-051", "false alarm", "Statement pair graded RED although Ultra answered incompatible=false: both "
               "pages say Galathea Bay has no coral. compute_grade ignores 'incompatible' for "
               "statement pairs (see summary)."),
    ("cp-p1001-1", "false alarm", "Copy-paste RED from shared taxonomic author years (Dana, 1849 ...); any "
                   "copepod checklist shares them. The site data (+/- by station) is not matched."),
]
DOUBLE = ["ct-071", "ct-1645", "ct-1464", "ct-1086", "ct-221", "ct-1254", "ct-1176", "ct-673",
          "ct-1625", "ct-617", "ct-402", "ct-240", "ct-604", "ct-051", "cp-p1001-1"]


def app_finding_id(flag, findings):
    """The id of this flag's finding in the app export (a kept duplicate if it was merged)."""
    ids = {f["id"] for f in findings}
    if flag["id"] in ids:
        return flag["id"]
    check = "copy_paste" if flag["type"] == "copy_paste" else (
        "recycled_figure" if flag["type"] == "recycled_figure" else "contradiction")
    for f in findings:
        if f["check"] != check or {q.get("page") for q in f["quotes"]} != set(flag["pages"]):
            continue
        if check == "copy_paste" or all(any(q["page"] == r.get("page") and ct.quotes_match(q["text"], r["text"])
                                            for r in f["quotes"]) for q in flag["quotes"]):
            return f["id"]
    return None


def main():
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    findings = json.loads(EXPORT.read_text(encoding="utf-8"))["findings"]
    flags = {f["id"]: f for f in audit["flags"]}
    top_ids = [t[0] for t in TOP30]
    assert len(top_ids) == 30 == len(set(top_ids)) and set(top_ids) <= set(flags), "bad TOP30"
    assert len(DOUBLE) == 15 and set(DOUBLE) <= set(top_ids), "bad DOUBLE"
    rest = sorted(set(flags) - set(top_ids))
    random.Random(SEED).shuffle(rest)
    items = []
    for n, fid in enumerate(top_ids + rest, 1):
        f = flags[fid]
        check = "copy_paste" if f["type"] == "copy_paste" else f["type"]
        items.append({"n": n, "flag_id": fid, "group": "top30" if fid in top_ids else "random",
                      "double_review": fid in DOUBLE, "grade": f["grade"], "check": check,
                      "check_name": CHECK_NAMES[check], "pages": f["pages"], "quotes": f["quotes"],
                      "reason": f["reason"], "answers": f.get("answers") or {},
                      "urls": f.get("urls") or [], "finding_id": app_finding_id(f, findings)})
    queue = {"report_id": "great_nicobar_2021_draft", "source": AUDIT.name,
             "created": time.strftime("%Y-%m-%d %H:%M"), "seed": SEED, "total": len(items),
             "top": len(top_ids), "double_review": len(DOUBLE),
             "order": "top 30 (hand-picked, most consequential first), then the rest in a "
                      f"random order (seed {SEED})",
             "items": items}
    review.REVIEW_DIR.mkdir(exist_ok=True)
    review.QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = [it["flag_id"] for it in items if not it["finding_id"]]
    print(f"Wrote {review.QUEUE.relative_to(ROOT)}: {len(items)} flags, {len(DOUBLE)} double review; "
          f"not in the app export: {missing or 'none'}")


if __name__ == "__main__":
    main()
