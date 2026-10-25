# TigerFish evaluation

Generated 2026-10-25 15:09. Seed 42. Cost of the evaluation's own API calls (planted test, from their token usage): $0.1165; new spend in this run: $0.0000 (the rest came from cache; cap $0.03).

## Summary

| Test | Result |
|---|---|
| Known issues (scored) | 4/4 pass |
| Negative control (1045 vs 910 sq km) | not flagged |
| Planted contradictions caught | 10/10 |
| Explained differences wrongly flagged | 0/5 |
| Other new flags on modified pages | 1 |
| Out-of-place species flagged | 5/5 |
| Locally recorded species wrongly flagged | 0/5 |
| Table 3.16: species judged plausible | 3 (article: 3) |
| Triage: Ultra calls saved, known-issue pages | 13/21 |
| Triage: Ultra calls saved, planted test | 43/75 |
| Triage: RED/ORANGE findings it would drop | 1 (known issues, planted catches and the negative control: none) |
| Full 1,213-page audit (estimate, with triage) | $7.04 = Rs 591 at 1 USD = 84 INR; about 262 min of API time if run one call at a time |
| Full 1,213-page audit (estimate, without triage) | $15.49 = Rs 1,302; about 348 min |

## 1. Known issues (data/known_issues.json)

| Issue | Type | Pages | Expected | Grade | Result | Status |
|---|---|---|---|---|---|---|
| gn-001 | contradiction | [392, 978] | RED/ORANGE | RED | PASS |  |
| gn-002 | mismatch | [444, 751] | ORANGE | NONE | FAIL (unscored) | under_review |
| gn-003 | recycled_figure | [818, 851, 1168] | RED | RED | PASS |  |
| gn-004 | contradiction | [1168, 940] | RED | RED | PASS |  |
| gn-neg-001 | negative_control | [234, 1141] | NONE | - | PASS |  |
| gn-005 | recycled_figure | [818, 851] | RED | RED | PASS (unscored) | candidate_new_finding |

Negative-control pair sent to Ultra directly: NONE. Both statements refer to Great Nicobar Island area; the report explains the reduction from 1045 to 910 sq km as due to submergence after the 2004 tsunami.

## 2. Planted contradictions

10 real numeric claims were restated on other real pages with a value x0.5 or x1.5, and 5 with an explicit 'revised from X to Y after the 2021 survey'. Pages were changed in memory only. Recall fixes in this run: (A) a statement with a number and a unit is paired like a quantity; (B) a deterministic pass adds a claim for any sentence with a number and a unit that the model did not cover (6 added on the modified pages). Of 75 candidate pairs, LIGHTNING triage passed 30 yes + 2 unsure and dropped 43; 20 went to Ultra, planted pairs first (12 more dropped by the cap of 20).

| Plant | Kind | Source p. | Target p. | Subject | Value | Extracted | Paired | Grade | Result | Missed at | Why |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pl-01 | planted | 940 | 198 | flora species reported from Great Nicobar Island | 600 -> 900 species | yes | yes | RED | OK |  |  |
| pl-02 | planted | 751 | 657 | airport runway reclamation | 71 -> 106 Ha | yes | yes | ORANGE | OK |  |  |
| pl-03 | planted | 234 | 594 | Megapode Island submergence area | 550 -> 275 sq km | yes | yes | RED | OK |  |  |
| pl-04 | planted | 1168 | 730 | fauna species recorded from GNI | 330 -> 495 species | yes | yes | RED | OK |  |  |
| pl-05 | planted | 818 | 642 | mangrove species recorded from Campbell Bay National Park | 14 -> 7 species | yes | yes | RED | OK |  |  |
| pl-06 | planted | 851 | 386 | amphibian species recorded from Galathea National Park | 10 -> 5 species | yes | yes | RED | OK |  |  |
| pl-07 | planted | 751 | 643 | coral restoration cost | 3200 -> 1600 INR Lacs/ Yr | yes | yes | RED | OK |  |  |
| pl-08 | planted | 1168 | 634 | Shompen population in Great Nicobar Island | 237 -> 356 number | yes | yes | RED | OK |  |  |
| pl-09 | planted | 1168 | 489 | bird species recorded from GNI | 97 -> 146 species | yes | yes | RED | OK |  |  |
| pl-10 | planted | 1168 | 572 | male literacy percentage in study area | 63.7 -> 95.55 % | yes | yes | ORANGE | OK |  |  |
| ex-11 | explained | 234 | 140 | Great Nicobar Island area post-tsunami | 910 -> 455 sq km | yes | yes | NONE | OK |  |  |
| ex-12 | explained | 1141 | 403 | Indira Point to international sea route | 25 -> 12 km | yes | yes | NONE | OK |  |  |
| ex-13 | explained | 1168 | 1117 | reptile species recorded from GNI | 23 -> 34 species | yes | no | - | OK |  |  |
| ex-14 | explained | 1168 | 557 | butterfly species recorded from GNI | 52 -> 26 species | yes | yes | NONE | OK |  |  |
| ex-15 | explained | 1168 | 777 | odonate species recorded from GNI | 24 -> 36 species | yes | yes | NONE | OK |  |  |

Other new flags on the modified pages (review by hand):

- ct-015 ORANGE pages [730, 940]: One figure (695) refers to total fauna species historically reported from Great Nicobar Island, while the other (495) refers to species recorded in a specific field survey; the report does not clarify whether the field survey was intended to be comprehensive or limited in scope.

### Triage cascade (LIGHTNING before Ultra)

Every candidate pair is first screened by LIGHTNING in batches of 8: could the two quotes be about the same subject, place and scope with incompatible values? Only yes/unsure go to Ultra. Validation: triage answers compared with the cached Ultra verdicts for the same pairs.

| Set | Candidates | yes / unsure / no | Ultra calls saved | With a cached Ultra verdict | RED/ORANGE it would drop |
|---|---|---|---|---|---|
| Known-issue pages | 21 | 8 / 0 / 13 | 13 | 20 | 1 |
| Planted test | 75 | 30 / 2 / 43 | 43 | 28 | 0 |

- Dropped by triage on the known-issue pages: pages [851, 940] (Ultra had graded it ORANGE). Not a known issue, planted catch or the negative control. Triage sees only the two quotes; Ultra found the problem by reading the whole page.


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
| Contradiction check (Ultra verdicts) | 12 | 32,642 | 11,017 | 43,659 | ~33s | $0.0631 | Rs 5.30 |
| Copy-paste check (Lightning) | 1 | 1,632 | 70 | 1,702 | ~132s | $0.0001 | Rs 0.01 |
| Table reading (Super-VL) + GBIF | 1 | 799 | 401 | 1,200 | ~2s | $0.0006 | Rs 0.05 |
| Planted test: claim extraction | 15 | 13,688 | 2,571 | 16,259 | 13s | $0.0014 | Rs 0.12 |
| Planted test: triage (Lightning) | 10 | 7,565 | 962 | 8,527 | 10s | $0.0007 | Rs 0.06 |
| Planted test: Ultra verdicts | 20 | 50,487 | 21,306 | 71,793 | 80s | $0.1144 | Rs 9.61 |

Tavily credits: copy-paste check 15, status check 2. GBIF calls (free): 55.

### Full 1,213-page audit (estimate)

Pages: 543 text + 579 vision; 91 Hindi pages skipped.

`cost = text_pages x cost_per_text_page + vision_pages x cost_per_vision_page + candidates x triage_cost_per_candidate + candidates x triage_pass_rate x cost_per_verdict, where candidates = candidates_per_page x pages`

| Unit | Value |
|---|---|
| text_page_usd | 0.00032 |
| vision_page_usd | 0.00281 |
| verdict_usd | 0.005548 |
| verdicts_per_page | 2.2 |
| tavily_per_page | 1.5 |
| text_page_s | 5.975 |
| vision_page_s | 15.25 |
| verdict_s | 3.55625 |
| triage_pass_rate | 0.380952 |
| triage_usd_per_candidate | 9e-06 |
| triage_s_per_candidate | 0.126667 |

|  | Ultra verdicts | Cost USD | Cost INR (1 USD = 84 INR) | API time, one call at a time |
|---|---|---|---|---|
| Without triage | 2,468 | $15.49 | Rs 1,302 | 348 min |
| With triage | 940 of 2,468 candidates | $7.04 | Rs 591 | 262 min |

**Estimate with triage: $7.04 (Rs 591 at 1 USD = 84 INR, labelled rate), about 940 Ultra verdicts, about 262 minutes of API time if run one call at a time (less in parallel), and about 1,683 Tavily credits for the copy-paste check.** The triage pass rate comes from the known-issue pages (a real document). This assumes the same density of claims and contradiction candidates as the 10 audited pages, and the candidate cap raised accordingly. The Ultra verdicts are most of the cost and the main uncertainty: candidate pairs can grow faster than the page count across a whole report, so the real number could be higher unless the cap stays.
