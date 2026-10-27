# Full audit: Great Nicobar draft EIA (1,213 pages)

Run of Oct 27, 2026 (`scripts/audit.py ... --scope --triage safe --run`), plus a top-up sitting at 16:31 that added the 166 salvaged claims and retried the one failed verdict. **$15.67 (Rs 1,316 at 1 USD = 84 INR), 60 min wall clock, 84 Tavily credits.** 1,114 of 1,213 pages audited; 99 skipped (79 Hindi, 15 lab sheets, 5 forms). 157 RED/ORANGE findings: the 4 known issues plus 153 new flags, all in the review queue (review/review_queue.json). Nothing here is verified by hand yet.

## The run

| | |
|---|---|
| Claims extracted | 10,463 (10,297 + 166 salvaged in the top-up) |
| Candidate pairs | 1,866 (keyed pairing; 1,799 + 67 from the salvaged claims) |
| Triage (Lightning) | yes 1,431 / unsure 9 / no 426 |
| Triage pass rate | **77%** (1,440 of 1,866 went to Ultra) |
| Ultra verdicts | 1,429 (0 failed; 11 added pairs not judged, cost cap) |
| Copy-paste passages checked | 100 |

Triage pass rate: 77% here (77% in the first 1,799 pairs too) vs 33% in the 100-page rehearsal (p.250-350). The rehearsal had only 9 candidate pairs (3 yes), so its rate says little. Keyed pairing only pairs claims that already share a subject key, so most pairs are plausible contradictions and Lightning passes them. Triage saved 426 Ultra calls (about $4.05; 410 in the main run).

## Cost per model (all sittings)

The audit took four sittings, all from the same cache: claim extraction (02:39, first attempt), keyed run 1 (04:11, stopped before all verdicts; its log was overwritten), the resume with `--max-cost 13.5` (14:27, no stop) and the top-up with `--max-cost 0.5 --new-pages ... --reuse-passages` (16:31, stopped at the cap). Source: logs/usage.jsonl and the run report's run_totals.

| Model | API calls | Tokens in | Tokens out | USD | INR |
|---|---:|---:|---:|---:|---:|
| Nemotron Super-VL (vision pages) | 946 | 3,423,968 | 927,840 | $1.86 | Rs 156 |
| Nemotron Lightning (text pages, keys, triage) | 1,562 | 2,515,597 | 328,340 | $0.23 | Rs 19 |
| Nemotron Ultra (verdicts) | 1,436 | 4,159,953 | 3,139,959 | $13.58 | Rs 1,141 |
| **Total** | 3,944 | | | **$15.67** | **Rs 1,316** |

| Sitting | USD | Wall clock |
|---|---:|---:|
| Claim extraction (02:39-02:55) | $1.96 | 15.3 min |
| Keyed run 1 (04:11-04:44, stopped) | $12.01 | 33.0 min |
| Resume (14:27-14:33) | $1.21 | 6.0 min |
| Top-up: salvaged claims + failed verdict (16:31-16:36) | $0.49 | 5.3 min |
| **Total** | **$15.67** | **59.6 min** |

- Estimate before the run: $16.31 (scoped, safe triage). Actual: $15.67 with the top-up ($15.18 without).
- Not counted: the abandoned unkeyed triage of 67,689 pairs (02:58-03:25), $0.91. All spend on the full audit: $16.58.
- Tavily: 84 credits in the 145 responses used (100 searches, 45 extracts); 75 newly spent in this run, the rest reused from the rehearsal.
- Average Ultra output: **2,176 tokens per verdict** in the main run (3,031,557 over 1,393 calls, reasoning included; 2,187 with the top-up). The 10-page evaluation measured about 1,100 (planted test about 2,000). So a verdict cost $0.0094 against $0.0070 in the estimate. Far fewer verdicts (1,389 vs 2,217) kept the total under the estimate.
- Retries in the resume: none, no rate limits or server errors (run 1's log was overwritten, so its retries are not known).

## Known issues on the full run (no change)

| Issue | Expected | Full run | Finding |
|---|---|---|---|
| gn-001 coral, p.392 vs p.978 | RED/ORANGE | ORANGE, pass | ct-031 |
| gn-003 recycled flora figures, p.818/851/1168 | RED | RED, pass | rf-010 |
| gn-004 fauna counts, p.1168 vs p.940 | RED | RED, pass | ct-403 |
| gn-005 recycled figures, p.818 vs p.851 (unscored) | RED | RED | rf-009 |
| gn-neg-001 island area 1045 vs 910 sq km | not flagged | not flagged, pass | (no pair) |
| gn-002 (under review, unscored) | ORANGE | not found | - |

Four other flags touch p.234 (the control's page), none about the 1045/910 area: ct-1718 and ct-1528 (distance to Sumatra), ct-1732 (tsunami subsidence), ct-1608 (973 km2 vs 1045/910).

## Findings by check and grade

| Check | RED | ORANGE | NONE | New RED/ORANGE (queue) |
|---|---:|---:|---:|---:|
| Internal contradiction | 103 | 46 | 1266 | 147 (102 RED, 45 ORANGE) |
| Recycled figure | 4 | 1 | 9 | 3 (2 RED, 1 ORANGE) |
| Copied text | 2 | 1 | 97 | 3 (2 RED, 1 ORANGE) |
| **Total** | 109 | 48 | 1372 | 153 |

App export (results/great_nicobar_2021_draft.json): 146 findings after duplicates are merged (same pages, matching quotes), with the other checks added. Consultant accreditation 0/1/0; Copied text 2/1/0; Internal contradiction 92/35/0; Not mentioned 0/1/0; Recycled figure 4/1/0; Species out of range 1/0/0; ToR promise 0/4/4 (RED/ORANGE/INFO). Summary strip: "1,114 of 1,213 pages audited; 99 skipped: Hindi/lab sheets/forms".

## Patterns likely to cost precision

1. **Statement pairs override Ultra's 'incompatible' answer** (`compute_grade`). In 19 of the flags (5 RED, 14 ORANGE), Ultra answered incompatible = false, e.g. ct-051: both pages say Galathea Bay has no coral. gn-001 (ct-031) also has incompatible = false, so simply requiring it would lose the known issue. **Rule tightened (Oct 27, 16:20):** the override now applies only when Ultra says same_subject = yes and same_place is not "no"; otherwise the pair is graded from Ultra's answers as usual. Re-graded from the cached verdicts (no calls): **0 of the 19 flags change, and 0 of all 144 statement verdicts.** All 19 have same_subject = yes and same_place yes (5) or unclear (14), so they still qualify. The rule changes nothing here because a pair where Ultra says the subjects or places differ was already NONE, whatever its incompatible answer. gn-001 stays ORANGE. Measuring these 19 in review is still the way to decide.
2. **One issue, many flags.** 15 flags compare the two land-use charts on p.918 and p.972, 5 compare p.396 and p.1077 (turtles/megapode), and 3 each compare the breakwater, berth and nest-count pairs. The app merges exact duplicates (153 queue flags map to fewer app findings), but row-by-row variants stay.
3. **Site-selection annexure (pp.1048-1060).** It describes the alternative sites (Casuarina Bay, Anderson Bay), so its TEU, berth and capacity figures are paired with the chosen site's (ct-1106, ct-1230/1231/1398, ct-735).
4. **Units split by a page break** (ct-240: 'Rs. 35,95,900' / 'lakhs.' on the next page) and **identical sentences** read as different (ct-604).
5. **Copy-paste on taxonomic author years.** Both copy-paste REDs share only years like 'Dana, 1849' with copepod and coral checklists. The ORANGE (p.29) matches a page about the Great Nicobar Biosphere Reserve itself (indianculture.gov.in); `same_project` checks the page text but not the URL.

## Lost data (fixed in the top-up, see below)

- **Copy-paste site-specific batch** (the two Lightning calls of about 64k tokens, 04:42): all 200 candidate passages went in one call with a 500-token reply limit. Lightning answered "1, 2, 3, ... 120, 12" and was cut off; the retry too, then the batch was skipped. **No passages were lost**: the run fell back to the top 100 by score, and Lightning's own list kept all of those before the cut. Fixed: batches of 20, each passage trimmed to 600 characters for this question, and a broken batch keeps its own passages only (tigerfish/copycheck.py, test added). audit.py now saves the checked passages so the export reuses them exactly.
- **Claim extraction: 7 pages produced no claims** (broken JSON after retry): p.539 (title block), 939 (phytoplankton figures), 1029 (flora list), 1038 (photo page), 1097 and 1099 (coral species lists), 1166 (executive summary). Fixed for the next run at no cost: complete rows of the cached cut-off reply are now kept for any model (they were only kept for Super-VL). From cache this recovers 166 claims (p.939 43, p.1166 43, p.1097 40, p.1099 35, p.539 5; p.1029 and p.1038 still give none). Added in the top-up.
- **1 failed Ultra verdict**: the reply hit the 6,000-token limit twice (9,067 tokens in). Retried in the top-up with a 16,000-token limit: ct-1179 (p.55 vs p.385, ICTT land 739 ha vs 966 ha), graded NONE.

## Top-up sitting (Oct 27 16:31, $0.49, 0 Tavily credits)

`scripts/audit.py ... --scope --triage safe --run --max-cost 0.5 --new-pages 539,939,1029,1038,1097,1099,1166 --reuse-passages`

- **Same ids, same grades.** The earlier 1,799 candidates are rebuilt from the earlier 10,297 claims exactly (subject keys, triage and verdicts all from cache), so all 1,388 earlier verdicts and all 152 earlier flags keep their ids and grades. Keying the 65 new subjects in their own batches avoids shifting every key batch (a cache-only dry run without this showed about 1,130 uncached Ultra verdicts, about $10).
- The 166 salvaged claims add 67 pairs (ids 1800 onward): triage passed 51, Ultra judged 40 before the $0.50 cap; **11 added pairs are not judged**. Of the 40 judged, 32 involve p.939 (phytoplankton figures) and 8 p.1166 (executive summary); 39 are NONE.
- **One new flag: ct-1815 RED** (p.1144 vs p.1166): deemed forest 4.39 sq km vs 8.88 sq km of the project area. Placed in the random part of the queue (#123).
- Copy-paste: the same 100 passages as the run (rebuilt from the earlier claims, top 100 by score without the Lightning filter, as the export does), all 145 Tavily replies from cache: still 2 RED, 1 ORANGE. The report now saves the passage list.
- Known issues and the negative control: unchanged (gn-001 ct-031 ORANGE, gn-003 rf-010, gn-004 ct-403, gn-005 rf-009 RED; gn-neg-001 not flagged).

## Copy-paste re-grade (new grade_hit rule, cache only)

All 100 passages and their 145 cached Tavily responses were re-graded with the rule "one shared number alone is not data". **No copy-paste flag changed grade**: still 2 RED (p.1001, p.1015) and 1 ORANGE (p.29). The full run never matched a passage with exactly one shared number (the p.327 Vembanad case was in the rehearsal). Note: audit.py does not pass species names to grade_hit. Passing them would make p.29 RED against two news pages about this same project, so leave it off.

## Top 30 RED/ORANGE flags (quick read, not verified)

Review order in the queue; **D** = double review (both reviewers judge independently).

| # | Flag | Grade | Pages | Quotes | Quick read | Why |
|---:|---|---|---|---|---|---|
| 1 | ct-071 **D** | ORANGE | 738, 1085 | p.738: "As per the ZSI report, coral do not exist in the Galathea Bay area, however, on the eastern peninsula part (Outside the construction area) ..."<br>p.1085: "the presence of 117 species of scleractinian corals" | **likely real** | p.1085 lists 117 scleractinian coral species and 17.46% live coral cover in Galathea Bay; p.738 says, citing ZSI, that coral does not exist in the Galathea Bay area. |
| 2 | ct-056 | ORANGE | 738, 978 | p.738: "As per the ZSI report, coral do not exist in the Galathea Bay area, however, on the eastern peninsula part (Outside the construction area) ..."<br>p.978: "Coral reef exists in the proposed site for Transshipment / Port" | **likely real** | Same coral question as gn-001: p.978 (EIA form) says coral reef exists in the port site; p.738 says no coral in the Galathea Bay area. |
| 3 | ct-1645 **D** | RED | 438, 446 | p.446: "916 Ha of area has been identified for development of International Airport which includes 845 ha of land and 71 ha of reclaimed area."<br>p.438: "the present site needs to reclaim land approximately 194 Ha of land in order to establish an operational airport." | **likely real** | Airport reclamation: 71 ha (p.446) vs 194 ha (p.438, and p.444 'the airport ... total reclaimed land will be 194 ha'). Both tie the figure to the airport, so part-of-total (TODO ct-005) looks less likely. |
| 4 | ct-1464 **D** | RED | 133, 438 | p.133: "The present site needs to reclaim land approx. 1.94 Ha of land in order to establish an operational airport."<br>p.438: "the present site needs to reclaim land approximately 194 Ha of land in order to establish an operational airport." | **likely real** | Same sentence on p.133 and p.438, but '1.94 Ha' vs '194 Ha': a decimal or unit slip on p.133 (p.972 has 1.94 sq km = 194 ha). |
| 5 | ct-783 | RED | 725, 919 | p.919: "The cost of the Airport is estimated at Rs. 10,35,900 lakhs."<br>p.725: "1 Airport 8,58,300" | **likely real** | Airport cost Rs 10,35,900 lakh (p.919, the ToR letter) vs Rs 8,58,300 lakh (p.725 cost table) and Rs 8,583 crore (p.24). Cost changed between ToR and EIA, unexplained. |
| 6 | ct-1086 **D** | RED | 87, 1151 | p.87: "The breakwaters are shore connected with a length of 3.90 km."<br>p.1151: "Breakwaters of 3.27 Km (2.53 km east breakwater & 0.74 km west offshore breakwater)" | **likely real** | p.87 says the breakwaters are 3.90 km long and, a few lines later, 3.27 km (2.53 + 0.74). Both on the same page. |
| 7 | ct-221 **D** | RED | 918, 972 | p.972: "RESIDENTIAL 16.55 9.97"<br>p.918: "RESIDENTIAL 36.66 22.07" | **likely real** | Two land-use charts with the same 166.10 sq km total but different categories (residential 36.66 vs 16.55 sq km). One of ~12 flags on p.918 vs p.972. |
| 8 | ct-217 | RED | 22, 26 | p.22: "Great Nicobar Biosphere Reserve 732.79"<br>p.26: "Great Nicobar Biosphere reserve (885 sq.km)" | **likely real** | Great Nicobar Biosphere Reserve 732.79 sq km (p.22 table) vs 885 sq km (pp.26, 938, 314; core 705 + buffer 180). 732.79 matches neither. |
| 9 | ct-225 | RED | 26, 942 | p.26: "Campbell bay National Park (426.23 sq.km)"<br>p.942: "Campbell Bay National Park (520 km2 area)" | **likely real** | Campbell Bay NP 426.23 sq km (p.26) vs 520 km2 (p.942, ZSI annexure); p.22 has a third value, 391.75. |
| 10 | ct-226 | RED | 22, 942 | p.22: "Galathea National Park 107.10"<br>p.942: "the Galathea National Park (185 km2 area)" | **likely real** | Galathea NP 107.10 sq km (p.22) vs 185 km2 (p.942). |
| 11 | ct-1607 | RED | 17, 1115 | p.17: "With an area of 910.074 sq.km, the Island represents a huge, strategically located land mass in the Bay of Bengal"<br>p.1115: "The total area of the island is 973 km2" | **likely real** | Island area 910.074 sq km vs 973 km2 (p.1115, annexure); p.243 has a third figure, 921 km2. Likely sources quoted without reconciling. |
| 12 | ct-1254 **D** | RED | 228, 942 | p.228: "Great Nicobar Island marks the southernmost tip of India 7° N, about 700 km north of Sumatra"<br>p.942: "is only about 145 km from Sumatra Island of Indonesia" | **likely real** | p.228 says Great Nicobar is about 700 km north of Sumatra; pp.19, 942 say 144-145 km. 700 km is wrong (p.942 also says '60 N', another slip). |
| 13 | ct-1176 **D** | RED | 243, 249 | p.243: "1.842"<br>p.249: "Approximately 65.43 ha of the mangroves were affected, and 32.06 ha are submerged and degraded during 26th December 2004 tsunami." | **likely real** | Mangroves 1.842 sq km (184 ha) for the whole island (p.243 table) vs 3,337 ha 'in the study area' (p.249); p.249 also says 0.01% of forest area. |
| 14 | ct-673 **D** | RED | 1047, 1126 | p.1126: "203"<br>p.1047: "103 nests in 2018-19" | **likely real** | Leatherback nests 2018-19: 203 in the tables (pp.1037, 1126) vs '103 nests in 2018-19' in the text (p.1047). Probably a typo. |
| 15 | ct-239 | RED | 291, 337 | p.337: "heavy annual rainfall of 300 to 350 Cm spreading over 9 months"<br>p.291: "The annual rainfall ranges from 3000 to 3500 Cm" | **likely real** | Rainfall 3000-3500 cm (p.291) vs 300-350 cm (p.337): unit error, likely mm (already in TODO). |
| 16 | ct-1385 | RED | 207, 210 | p.210: "39 Acres"<br>p.207: "Planned layout has been developed in order to accommodate the plant facilities within the proposed 39 Hectare of land parcel." | **likely real** | Power plant land 39 hectares (pp.207, 485, 581, 975) vs 39 acres (p.210). |
| 17 | ct-200 | RED | 134, 459 | p.134: "Out of which part will be met by the DG sets of 2 x 5 MVA each"<br>p.459: "operation of 7 DG sets for continuous 8 hours per day" | **likely real** | Airport power: DG sets of 2 x 5 MVA (p.134) vs the air-quality model run with 7 DG sets (p.459, airport chapter). |
| 18 | ct-812 | RED | 45, 279 | p.45: "10 SW"<br>p.279: "Eight surface water and Eight ground water sources covering were examined for physio-chemical, heavy metals and bacteriological parameters" | **likely real** | Water sampling: 10 SW + 10 GW planned (p.45) vs 8 + 8 examined (p.279). Same as ToR promise pr-13. |
| 19 | ct-414 | RED | 29, 324 | p.324: "Of the 25 species of mammals found on the island"<br>p.29: "A total of 14 species of mammals" | **likely real** | Mammal species on the island: 14 (p.29) vs 25 (p.324); also 28 on p.1168. Different literature sources, never reconciled. |
| 20 | ct-387 | RED | 29, 1168 | p.29: "71 species of birds"<br>p.1168: "97 species of birds" | **likely real** | Bird species: 71 (p.29) vs 97 (p.1168); p.327 says about 90. |
| 21 | ct-1625 **D** | RED | 445, 1088 | p.445: "in 16610 ha, at Great Nicobar Islands, Nicobar District"<br>p.1088: "14,960 Ha and Power Plant" | **needs a look** | Total project area 16,610 ha vs '14,960 Ha and Power Plant' (p.1088 starts mid-sentence). Read p.1087: 14,960 ha may be one component. |
| 22 | ct-617 **D** | RED | 40, 109 | p.40: "4000 Peak Hour Passengers"<br>p.109: "The airstrip will be developed to cater for operation of Code C type of aircraft in all weather conditions having peak hour passenger’s ..." | **possible false alarm** | Airport 4000 PHP (title) vs 1036 PHP for the 'airstrip ... Code C' (p.109). Could be an initial phase; check p.109's context. |
| 23 | ct-402 **D** | RED | 940, 944 | p.940: "A total of 695 species of fauna with the endemism of 158 species"<br>p.944: "The fauna consists of over 1800 species" | **possible false alarm** | Fauna 695 species (p.940) vs over 1800 (p.944). p.944's 1800 includes invertebrates; different scopes and sources. |
| 24 | ct-209 | RED | 743, 770 | p.743: "Two control points with two porta cabins and with 3 shifts total 6 person to be employed"<br>p.770: "Ten control points with 10 porta cabins and with 3 shift, total 30 person to be employed" | **possible false alarm** | Control points 2 (p.743, power plant plan) vs 10 (p.770, full operation): probably different components, not a contradiction. |
| 25 | ct-1106 | RED | 1051, 1053 | p.1051: "Estimated capacity: 15 Million TEUs per annum"<br>p.1053: "Estimated capacity: 14.2 Million TEUs per annum" | **possible false alarm** | 15 vs 14.2 million TEU. p.1051 describes the Casuarina Bay site option in the site-selection annexure, not the chosen site. |
| 26 | ct-240 **D** | RED | 24, 918 | p.918: "The ICTT can be developed at a cost of Rs. 35,95,900"<br>p.24: "The ICTT will be developed at a cost of Rs. 35,959 Crore." | **false alarm** | ICTT cost 'Rs. 35,95,900' at the end of p.918 continues 'lakhs.' on p.919: 35,95,900 lakh = 35,959 crore, the same figure as p.24. |
| 27 | ct-604 **D** | RED | 87, 965 | p.87: "The east & west breakwater extends till the 20 m & 25 m contour respectively."<br>p.965: "The east & west breakwater extends till the 20 m & 25 m contour respectively." | **false alarm** | Both pages have the identical sentence ('east & west breakwater extends till the 20 m & 25 m contour'). Ultra misread it. |
| 28 | ct-1366 | RED | 69, 391 | p.69: "2 2055 Final Phase 16 5,400 3,700"<br>p.391: "building of 13 berths" | **false alarm** | The 13 berths on p.391 are at Dhamra port (Odisha), cited as an example; not this project. |
| 29 | ct-051 **D** | RED | 411, 1124 | p.411: "ZSI data suggest that the Galathea Bay is devoid of any coral reefs."<br>p.1124: "Except the Galathea Bay, coral reefs were found near the all nesting beaches (Map 2 and Table 1)." | **false alarm** | Statement pair graded RED although Ultra answered incompatible=false: both pages say Galathea Bay has no coral. compute_grade overrides 'incompatible' for statement pairs when Ultra says same subject and the places do not differ, as here (see pattern 1). |
| 30 | cp-p1001-1 **D** | RED | 1001 | p.1001: "ZOOPLANKTON SPECIES CB JB LB RB GB Class HEXANAUPLIA Oakley, Wolfe, Lindgren & Zaharof, 2013 Subclass COPEPODA Milne Edwards, 1840 Acartia ..." | **false alarm** | Copy-paste RED from shared taxonomic author years (Dana, 1849 ...); any copepod checklist shares them. The site data (+/- by station) is not matched. |

Tally: 20 likely real, 1 needs a look, 4 possible false alarm, 5 false alarm. The top 30 is hand-picked (most consequential first, plus one example of each false-alarm pattern), so its precision is not the tool's precision. The random part of the queue gives that.

## Review queue

review/review_queue.json lists all 153 new RED/ORANGE flags: the top 30 above, then the other 123 in a random order (seed 42; rebuilt after the top-up, so the random order differs from the 152-flag queue). 15 of the top 30 are marked double review. The app's Review queue tab walks the queue in order ("Flag n of 153"). A reviewer name is required. For double-review flags, the other reviewer's decision stays hidden until you have decided. Decisions are saved to review/reviews.jsonl. The Precision panel shows precision on everything reviewed so far, precision on the random part alone, and agreement on the double-review flags (with Cohen's kappa). Flags judged false alarms are hidden from the Findings view unless "Show dismissed" is on. My quick reads are not in the queue, so reviewers judge without them.
