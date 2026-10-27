# TigerFish evaluation

Generated 2026-10-27 23:07. Seed 42. Cost of the evaluation's own API calls (planted test, from their token usage): $0.1925; new spend in this run: $0.0000 (the rest came from cache; cap $0.30).

## Summary

| Test | Result |
|---|---|
| Known issues, 10 known-issue pages (scored) | 7/7 pass |
| Negative controls (1045 vs 910 sq km; coral 1-2 vs 4 ha) | gn-002 not flagged, gn-neg-001 not flagged |
| Planted contradictions caught | 10/10 |
| Explained differences wrongly flagged | 0/5 |
| Other new flags on modified pages | 0 |
| Out-of-place species flagged | 5/5 |
| Locally recorded species wrongly flagged | 0/5 |
| Table 3.16: species judged plausible | 3 (article: 3) |
| Triage: Ultra calls saved, known-issue pages | 0/11 |
| Triage: Ultra calls saved, planted test | 0/23 |
| Triage: RED/ORANGE findings it would drop | 0 (known issues, planted catches and the negative control: none) |
| Full 1,213-page audit (estimate, with triage) | $11.32 = Rs 951 at 1 USD = 84 INR; about 358 min of API time if run one call at a time |
| Full 1,213-page audit (estimate, without triage) | $11.24 = Rs 944; about 345 min |
| Full 1,213-page audit (measured) | $15.78 = Rs 1,326; 62 min wall clock with 6 parallel calls; 84 Tavily credits |
| Full audit: known issues | 12/12 pass with every check (gn-001 ct-031, gn-003 rf-010, gn-004 ct-403, gn-005 rf-009, gn-006 ct-071, gn-007 ct-979, gn-008 ct-239, gn-009 sp-p954-001, gn-010 ac-01, gn-011 pr-06); both negative controls not flagged; all verified by hand |
| Full audit: new RED/ORANGE flags | 153 (review queue; 3 already reviewed as human-verified known issues (ct-071, ct-239, ct-979); reviewed so far 3 of 153, 3 real of 3 judged; precision on the rest to be measured by hand) |

## 1. Known issues (data/known_issues.json)

On the 10 known-issue pages (pp.234, 392, 444, 751, 818, 851, 940, 978, 1141, 1168), contradiction check only. Issues on other pages or found by other checks are scored on the full audit (1b).

| Issue | Type | Pages | Expected | Grade | Result | Status |
|---|---|---|---|---|---|---|
| gn-001 | contradiction | [392, 978] | RED/ORANGE | ORANGE | PASS |  |
| gn-002 | negative_control | [444, 751] | NONE | - | PASS | explained |
| gn-003 | recycled_figure | [818, 851, 1168] | RED | RED | PASS |  |
| gn-004 | contradiction | [1168, 940] | RED | RED | PASS |  |
| gn-neg-001 | negative_control | [234, 1141] | NONE | - | PASS |  |
| gn-005 | recycled_figure | [818, 851] | RED | RED | PASS |  |
| gn-007 | contradiction | [851, 940] | RED/ORANGE | ORANGE | PASS |  |

Negative-control pair sent to Ultra directly: NONE. Both statements refer to the area of Great Nicobar Island (GNI), noting a reduction from 1045 sq km to 910 sq km. The report explains this difference as resulting from land submergence caused by the 2004 tsunami.

### 1b. Known issues on the full audit (all checks)

Every known issue scored against the full 1,213-page audit as exported for the app (contradictions and recycled figures by matching quotes; species, accreditation and ToR issues by their finding id). **12/12 pass.** All 12 issues were verified by hand against the PDF (verified_by, verified_on, verification_note in data/known_issues.json).

| Issue | Type | Expected | Grade | Finding | Result | Hand check |
|---|---|---|---|---|---|---|
| gn-001 | contradiction | RED/ORANGE | ORANGE | ct-031 | PASS | confirmed, with nuance, Manya Singh 2026-10-27 |
| gn-002 | negative_control | NONE | - | - | PASS | explained (negative control), Manya Singh 2026-10-27 |
| gn-003 | recycled_figure | RED | RED | rf-010 | PASS | confirmed, Manya Singh 2026-10-27 |
| gn-004 | contradiction | RED | RED | ct-403 | PASS | confirmed, Manya Singh 2026-10-27 |
| gn-neg-001 | negative_control | NONE | - | - | PASS | explained (negative control), Manya Singh 2026-10-27 |
| gn-005 | recycled_figure | RED | RED | rf-009 | PASS | confirmed, with nuance, Manya Singh 2026-10-27 |
| gn-006 | contradiction | RED/ORANGE | ORANGE | ct-071 | PASS | confirmed, with nuance, Manya Singh 2026-10-27 |
| gn-007 | contradiction | RED/ORANGE | ORANGE | ct-979 | PASS | confirmed, with nuance, Manya Singh 2026-10-27 |
| gn-008 | contradiction | RED/ORANGE | RED | ct-239 | PASS | confirmed, Manya Singh 2026-10-27 |
| gn-009 | species_range | RED | RED | sp-p954-001 | PASS | confirmed, Manya Singh 2026-10-27 |
| gn-010 | accreditation | ORANGE | ORANGE | ac-01 | PASS | confirmed, Manya Singh 2026-10-27 |
| gn-011 | tor_promise | ORANGE | ORANGE | pr-06 | PASS | confirmed, Manya Singh 2026-10-27 |

Hand-check notes:

- **gn-001**: p.978 (Form 1 screening): "Coral reef exists in the proposed site for Transshipment / Port"; p.392 and p.738: corals outside the construction area; p.392 plans translocation "if affected".
- **gn-002**: p.751 Table 10.3 says the ~4 ha restoration "involves restoration for the entire project including Port, Power plant and Township", so 1-2 ha (port) vs 4 ha (whole project) is not a contradiction. TigerFish correctly grades it NONE; scored as a second negative control.
- **gn-003**: pp.818/851 (Gazette ESZ notifications) give the identical 330-species breakdown; p.1168 (Executive Summary, the EIA's own text) applies it to "the whole GNI area".
- **gn-004**: p.1168 (330 species, whole GNI area) vs p.940 ZSI: "695 species of fauna with the endemism of 158 species".
- **gn-neg-001**: Confirmed: explained by the 2004 tsunami (1045 -> 910 sq km), as p.234 says.
- **gn-005**: pp.818/851 are Gazette ESZ notifications reproduced in the EIA; identical 648/422/142/48/85 for both parks; the duplication originates in the official notifications.
- **gn-006**: p.1085 lists "presence of 117 species of scleractinian corals along with the live coral cover of 17.46%" among issues "Galathea Bay stands with" (the sentence ends "in adjoining Galathea"); p.738: "coral do not exist in the Galathea Bay area".
- **gn-007**: p.851 "About 648" vs p.940 BSI "approximately 600"; different sources, approximate, not reconciled.
- **gn-008**: Low severity, likely a unit slip: p.291 "3000 to 3500 Cm" vs p.337 "300 to 350 Cm".
- **gn-009**: p.954: "rock lobsters (Panulirus interruptus) also being landed in considerable quantity"; GBIF has 0 records within 3,000 km. Likely misidentification.
- **gn-010**: EIA p.18: category A, ICTT 7(e), township 8(b). NABET minutes 061/2021 (26 Oct 2021, citing RA AC 15 Jun 2021): 33(B), 39(B). Supporting evidence: Vimta NABET certificate NABET/EIA/2326/RA 0301 (2023-26): sector 33 Cat. B, sector 39 Cat. B (dated after the report; supporting only).
- **gn-011**: pp.292-293: "rapid reconnaissance type of survey" 14-22 Dec 2020 (road corridor 15-21 Dec, 7 days), "not intensive except in non-forest residential areas". Proposed ToR p.1: "base line data to be collected for 3 months to represent a season". The air/water/soil baseline did run 3 months.

## 2. Planted contradictions

10 real numeric claims were restated on other real pages with a value x0.5 or x1.5, and 5 with an explicit 'revised from X to Y after the 2021 survey'. Pages were changed in memory only. Recall fixes in this run: (A) a statement with a number and a unit is paired like a quantity; (B) a deterministic pass adds a claim for any sentence with a number and a unit that the model did not cover (6 added on the modified pages). Of 23 candidate pairs, LIGHTNING triage passed 23 yes + 0 unsure and dropped 0; 20 went to Ultra, planted pairs first (3 more dropped by the cap of 20).

| Plant | Kind | Source p. | Target p. | Subject | Value | Extracted | Paired | Grade | Result | Missed at | Why |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pl-01 | planted | 940 | 198 | flora species reported from Great Nicobar Island | 600 -> 900 species | yes | yes | RED | OK |  |  |
| pl-02 | planted | 751 | 657 | airport runway reclamation | 71 -> 106 Ha | yes | yes | RED | OK |  |  |
| pl-03 | planted | 234 | 594 | Megapode Island submergence area | 550 -> 275 sq km | yes | yes | ORANGE | OK |  |  |
| pl-04 | planted | 1168 | 730 | fauna species recorded from GNI | 330 -> 495 species | yes | yes | RED | OK |  |  |
| pl-05 | planted | 818 | 642 | mangrove species recorded from Campbell Bay National Park | 14 -> 7 species | yes | yes | RED | OK |  |  |
| pl-06 | planted | 851 | 386 | amphibian species recorded from Galathea National Park | 10 -> 5 species | yes | yes | RED | OK |  |  |
| pl-07 | planted | 751 | 643 | coral restoration cost | 3200 -> 1600 INR Lacs/ Yr | yes | yes | RED | OK |  |  |
| pl-08 | planted | 1168 | 634 | Shompen population in Great Nicobar Island | 237 -> 356 number | yes | yes | RED | OK |  |  |
| pl-09 | planted | 1168 | 489 | bird species recorded from GNI | 97 -> 146 species | yes | yes | RED | OK |  |  |
| pl-10 | planted | 1168 | 572 | male literacy percentage in study area | 63.7 -> 95.55 % | yes | yes | RED | OK |  |  |
| ex-11 | explained | 234 | 140 | Great Nicobar Island area post-tsunami | 910 -> 455 sq km | yes | yes | NONE | OK |  |  |
| ex-12 | explained | 1141 | 403 | Indira Point to international sea route | 25 -> 12 km | yes | yes | NONE | OK |  |  |
| ex-13 | explained | 1168 | 1117 | reptile species recorded from GNI | 23 -> 34 species | yes | yes | NONE | OK |  |  |
| ex-14 | explained | 1168 | 557 | butterfly species recorded from GNI | 52 -> 26 species | yes | yes | NONE | OK |  |  |
| ex-15 | explained | 1168 | 777 | odonate species recorded from GNI | 24 -> 36 species | yes | yes | NONE | OK |  |  |

Other new flags on the modified pages (review by hand):

- none

### Triage cascade (LIGHTNING before Ultra)

Every candidate pair is first screened by LIGHTNING in batches of 2: could the two quotes be about the same subject, place and scope with incompatible values? Only yes/unsure go to Ultra. Validation: triage answers compared with the cached Ultra verdicts for the same pairs.

| Set | Candidates | yes / unsure / no | Ultra calls saved | With a cached Ultra verdict | RED/ORANGE it would drop |
|---|---|---|---|---|---|
| Known-issue pages | 11 | 11 / 0 / 0 | 0 | 11 | 0 |
| Planted test | 23 | 23 / 0 / 0 | 0 | 20 | 0 |


Fast mode (`scripts/audit.py --triage fast`, quotes-only view alone) on the known-issue pages: yes / unsure / no = 9 / 0 / 2, and it would drop 0 RED/ORANGE finding(s) that safe mode keeps.

Triage runs two LIGHTNING views of each pair: the two quotes alone (8 pairs per call) and the quotes with about 1,500 characters of page context each (2 pairs per call). A pair is dropped only if both views say no: in validation, each view alone dropped a different real finding (quotes only lost a 648-vs-600 flora ORANGE that needs page context; context alone lost a planted RED).


## 3. Planted species (Indira Point, 6.75 N 93.83 E)

| Species | Group | Lives in | Grade | GBIF local / 500 km / world |
|---|---|---|---|---|
| Hydrocynus vittatus | out of place | Africa (tigerfish) | RED | 0 / 0 / 1342 |
| Semaprochilodus insignis | out of place | South America (Amazon fish) | RED | 0 / 0 / 8669 |
| Erinaceus europaeus | out of place | Europe (hedgehog) | ORANGE | 0 / 0 / 956468 |
| Antilope cervicapra | out of place | mainland India (blackbuck) | ORANGE | 0 / 0 / 2332 |
| Giraffa camelopardalis | out of place | Africa (giraffe) | ORANGE | 0 / 0 / 5644 |
| Macaca fascicularis | recorded locally | Great Nicobar | plausible | 16 / 39 / 20211 |
| Tupaia nicobarica | recorded locally | Great Nicobar | plausible | 40 / 42 / 42 |
| Megapodius nicobariensis | recorded locally | Great Nicobar | plausible | 128 / 205 / 228 |
| Dermochelys coriacea | recorded locally | Great Nicobar | plausible | 3 / 3 / 53588 |
| Crocodylus porosus | recorded locally | Great Nicobar | plausible | 1 / 2 / 107676 |

## 4. Table 3.16 vs Scroll.in

Scroll.in, "'Fake claims': Great Nicobar lighthouse project study lists species found in Africa, Amazon", by Pankaj Sekhsaria, 31 Aug 2026 (https://scroll.in/article/1095311/fake-claims-great-nicobar-lighthouse-project-study-lists-species-found-in-africa-amazon): "Of the 12 mammals in the table, only three are found on Great Nicobar." The article does not name the three; it names the sambar and the barking deer as mainland species.

- TigerFish judges **3** of 12 plausible at the site: Macaca fascicularis, Sus scrofa andamanensis, Tupaia nicobarica nicobarica. The count matches the article's three; the names cannot be compared because the article does not give them.
- Of the other 9: **5** flagged ORANGE, **4** GREY (not enough GBIF survey data to judge).
- The two species the article names as mainland: Cervus unicolor ORANGE, Muntiacus muntjak ORANGE.

| Name as printed | GBIF name | Grade | GBIF records within 100 km |
|---|---|---|---|
| Axis axis | Axis axis | ORANGE | 0 |
| Cervus unicolor | Rusa unicolor | ORANGE | 0 |
| Crocidura hispida | Crocidura hispida | GREY | 0 |
| Felis chaus | Felis chaus | ORANGE | 0 |
| Funambulus pennantii | Funambulus pennantii | ORANGE | 0 |
| Macaca fascicularis | Macaca fascicularis | plausible | 16 |
| Muntiacus muntjak | Muntiacus muntjak | ORANGE | 0 |
| Paguma larvata | Paguma larvata | GREY | 0 |
| Pteropus giganteus | Pteropus vampyrus | GREY | 0 |
| Rattus rattus | Rattus rattus | GREY | 0 |
| Sus scrofa andamanensis | Sus scrofa | plausible | 2 |
| Tupaia nicobarica nicobarica | Tupaia nicobarica | plausible | 40 |

## 5. Cost and speed

Per check, for the 10 known-issue pages and Table 3.16 (table layout from the Nebius cookbook's agent cost comparison). Time is measured per call where the call was made after timing was added; older calls use an estimate from cache file timestamps (marked ~). The ~ values are rough: a gap between cache files can include idle time (the copy-paste figure is one such case). The planted-test rows are measured.

| Check | Calls | In tok | Out tok | Tot tok | Time | Cost USD | Cost INR |
|---|---|---|---|---|---|---|---|
| Claim extraction, text pages (8) | 8 | 11,832 | 7,710 | 19,542 | ~48s | $0.0026 | Rs 0.22 |
| Claim extraction, vision pages (2) | 3 | 10,842 | 2,625 | 13,467 | ~30s | $0.0056 | Rs 0.47 |
| Contradiction check (Ultra verdicts) | 21 | 60,218 | 22,978 | 83,196 | 111s | $0.1050 | Rs 8.82 |
| Copy-paste check (Lightning) | 2 | 1,737 | 79 | 1,816 | 3s | $0.0001 | Rs 0.01 |
| Table reading (Super-VL) + GBIF | 1 | 799 | 401 | 1,200 | ~0s | $0.0006 | Rs 0.05 |
| Planted test: claim extraction | 15 | 13,688 | 2,571 | 16,259 | 13s | $0.0014 | Rs 0.12 |
| Planted test: triage (Lightning) | 15 | 22,144 | 643 | 22,787 | 13s | $0.0015 | Rs 0.12 |
| Planted test: fast triage, quotes only (Lightning) | 3 | 2,494 | 294 | 2,788 | 4s | $0.0002 | Rs 0.02 |
| Planted test: Ultra verdicts | 21 | 65,486 | 41,294 | 106,780 | 158s | $0.1894 | Rs 15.91 |

Tavily credits: copy-paste check 15, status check 4. GBIF calls (free): 55.

### Full 1,213-page audit (estimate)

Pages: 543 text + 579 vision; 91 Hindi pages skipped.

`cost = text_pages x cost_per_text_page + vision_pages x cost_per_vision_page + candidates x triage_cost_per_candidate + candidates x triage_pass_rate x cost_per_verdict, where candidates = candidates_per_page x pages`

| Unit | Value |
|---|---|
| text_page_usd | 0.00032 |
| vision_page_usd | 0.00281 |
| verdict_usd | 0.007009 |
| verdicts_per_page | 1.2 |
| tavily_per_page | 1.5 |
| text_page_s | 5.975 |
| vision_page_s | 15.25 |
| verdict_s | 6.404762 |
| triage_pass_rate | 1.0 |
| triage_pass_rate_fast | 0.818182 |
| triage_usd_per_candidate_fast | 1e-05 |
| triage_s_per_candidate_fast | 0.191304 |
| triage_usd_per_candidate | 6.4e-05 |
| triage_s_per_candidate | 0.582609 |

|  | Ultra verdicts | Cost USD | Cost INR (1 USD = 84 INR) | API time, one call at a time |
|---|---|---|---|---|
| Without triage | 1,346 | $11.24 | Rs 944 | 345 min |
| With triage | 1,346 of 1,346 candidates | $11.32 | Rs 951 | 358 min |

**Estimate with triage: $11.32 (Rs 951 at 1 USD = 84 INR, labelled rate), about 1,346 Ultra verdicts, about 358 minutes of API time if run one call at a time (less in parallel), and about 1,683 Tavily credits for the copy-paste check.** The triage pass rate comes from the known-issue pages (a real document). This assumes the same density of claims and contradiction candidates as the 10 audited pages, and the candidate cap raised accordingly. The Ultra verdicts are most of the cost and the main uncertainty: candidate pairs can grow faster than the page count across a whole report, so the real number could be higher unless the cap stays.

## 6. Full 1,213-page audit (measured)

`scripts/audit.py` with scope and safe triage: 1,114 pages audited (99 skipped: Hindi, lab sheets, forms), 10,463 claims, 1,866 candidate pairs, triage passed 1,440 (77%), 1,440 Ultra verdicts (0 failed), 100 copy-paste passages. Whole audit: claim extraction (Oct 27 02:39, first attempt, reused from cache), keyed run 1 (04:11, stopped before all verdicts) and the resume (14:27, --max-cost 13.5, no stop). Excludes the abandoned unkeyed triage of 67,689 pairs (02:58-03:25). Plus a top-up sitting (Oct 27 16:31, --new-pages 539,939,1029,1038,1097,1099,1166, $0.49). Plus a top-up sitting (Oct 27 22:19, --new-pages 539,939,1029,1038,1097,1099,1166, $0.11).

| Model | API calls | In tok | Out tok | Cost USD | Cost INR |
|---|---|---|---|---|---|
| Nemotron-3_5-Lightning | 1,562 | 2,515,597 | 328,340 | $0.23 | Rs 19 |
| Nemotron-3.5-Super-VL | 946 | 3,423,968 | 927,840 | $1.86 | Rs 156 |
| Nemotron-3-Ultra-550b-a55b | 1,447 | 4,200,900 | 3,162,518 | $13.69 | Rs 1,150 |

Ultra wrote 2,186 output tokens per verdict on average (reasoning included), $0.0095 per verdict.

**Measured: $15.78 (Rs 1,326), 62 min wall clock, 84 Tavily credits.** The estimate above assumed the 10 audited pages' density; the full report had fewer candidate pairs per page after keyed pairing, but each verdict was longer. Findings by check: recycled_figure {'RED': 4, 'ORANGE': 1, 'NONE': 9}; contradiction {'RED': 103, 'ORANGE': 46, 'NONE': 1277}; copy_paste {'NONE': 97, 'RED': 2, 'ORANGE': 1}. Details and the top 30 flags: results/full_audit_summary.md.
