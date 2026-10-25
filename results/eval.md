# TigerFish evaluation

Generated 2026-10-25 07:05. Seed 42. Cost of the evaluation's own API calls (planted test, from their token usage): $0.1243; new spend in this run: $0.0000 (the rest came from cache; cap $0.30).

## Summary

| Test | Result |
|---|---|
| Known issues (scored) | 4/4 pass |
| Negative control (1045 vs 910 sq km) | not flagged |
| Planted contradictions caught | 7/10 |
| Explained differences wrongly flagged | 0/5 |
| Other new flags on modified pages | 1 |
| Out-of-place species flagged | 5/5 |
| Locally recorded species wrongly flagged | 0/5 |
| Table 3.16: species judged plausible | 3 (article: 3) |
| Full 1,213-page audit (estimate) | $19.01 = Rs 1,597 at 1 USD = 84 INR; about 350 min of API time if run one call at a time |

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

10 real numeric claims were restated on other real pages with a value x0.5 or x1.5, and 5 with an explicit 'revised from X to Y after the 2021 survey'. Pages were changed in memory only. 20 candidate pairs were checked (45 dropped by the cap of 20).

| Plant | Kind | Source p. | Target p. | Subject | Value | Extracted | Paired | Grade | Result | Missed at | Why |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pl-01 | planted | 940 | 198 | flora species reported from Great Nicobar Island | 600 -> 900 species | yes | yes | RED | OK |  |  |
| pl-02 | planted | 751 | 657 | airport runway reclamation | 71 -> 106 Ha | no | no | - | MISS | extraction | the planted sentence was not extracted as a claim |
| pl-03 | planted | 234 | 594 | Megapode Island submergence area | 550 -> 275 sq km | yes | yes | RED | OK |  |  |
| pl-04 | planted | 1168 | 730 | fauna species recorded from GNI | 330 -> 495 species | yes | yes | RED | OK |  |  |
| pl-05 | planted | 818 | 642 | mangrove species recorded from Campbell Bay National Park | 14 -> 7 species | yes | yes | RED | OK |  |  |
| pl-06 | planted | 851 | 386 | amphibian species recorded from Galathea National Park | 10 -> 5 species | yes | yes | RED | OK |  |  |
| pl-07 | planted | 751 | 643 | coral restoration cost | 3200 -> 1600 INR Lacs/ Yr | no | no | - | MISS | extraction | the planted sentence was not extracted as a claim |
| pl-08 | planted | 1168 | 634 | Shompen population in Great Nicobar Island | 237 -> 356 number | yes | yes | RED | OK |  |  |
| pl-09 | planted | 1168 | 489 | bird species recorded from GNI | 97 -> 146 species | yes | yes | RED | OK |  |  |
| pl-10 | planted | 1168 | 572 | male literacy percentage in study area | 63.7 -> 95.55 % | yes | no | - | MISS | pairing | extracted as type 'statement' (95.55 %); numeric pairing only compares quantity/count/area/distance claims |
| ex-11 | explained | 234 | 140 | Great Nicobar Island area post-tsunami | 910 -> 455 sq km | yes | yes | NONE | OK |  |  |
| ex-12 | explained | 1141 | 403 | Indira Point to international sea route | 25 -> 12 km | yes | yes | NONE | OK |  |  |
| ex-13 | explained | 1168 | 1117 | reptile species recorded from GNI | 23 -> 34 species | yes | yes | NONE | OK |  |  |
| ex-14 | explained | 1168 | 557 | butterfly species recorded from GNI | 52 -> 26 species | yes | yes | NONE | OK |  |  |
| ex-15 | explained | 1168 | 777 | odonate species recorded from GNI | 24 -> 36 species | yes | yes | NONE | OK |  |  |

Suggested fix for the pairing miss: treat a statement claim that carries a number and a unit as a quantity when pairing. Not applied in this run, to keep the known-issue results unchanged.

Other new flags on the modified pages (review by hand):

- ct-013 ORANGE pages [730, 940]: One figure (695) refers to total fauna species historically reported from Great Nicobar Island, while the other (495) refers to species recorded in a specific field survey; the report does not clarify whether the field survey was intended to be comprehensive or limited in scope.

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
| Contradiction check (Ultra verdicts) | 21 | 74,327 | 26,354 | 100,681 | ~79s | $0.1534 | Rs 12.88 |
| Copy-paste check (Lightning) | 1 | 1,632 | 70 | 1,702 | ~132s | $0.0001 | Rs 0.01 |
| Table reading (Super-VL) + GBIF | 1 | 799 | 401 | 1,200 | ~3s | $0.0006 | Rs 0.05 |
| Planted test: claim extraction | 15 | 13,688 | 2,571 | 16,259 | 13s | $0.0014 | Rs 0.12 |
| Planted test: Ultra verdicts | 20 | 52,348 | 23,497 | 75,845 | 79s | $0.1228 | Rs 10.32 |

Tavily credits: copy-paste check 15, status check 2. GBIF calls (free): 55.

### Full 1,213-page audit (estimate)

Pages: 543 text + 579 vision; 91 Hindi pages skipped.

`cost = text_pages x cost_per_text_page + vision_pages x cost_per_vision_page + (verdicts_per_page x pages) x cost_per_verdict`

| Unit | Value |
|---|---|
| text_page_usd | 0.00032 |
| vision_page_usd | 0.00281 |
| verdict_usd | 0.007304 |
| verdicts_per_page | 2.1 |
| tavily_per_page | 1.5 |
| text_page_s | 5.975 |
| vision_page_s | 15.25 |
| verdict_s | 3.780952 |

**Estimate: $19.01 (Rs 1,597 at 1 USD = 84 INR, labelled rate), about 2,356 Ultra verdicts, about 350 minutes of API time if run one call at a time (less in parallel), and about 1,683 Tavily credits for the copy-paste check.** This assumes the same density of claims and contradiction candidates as the 10 audited pages, and the candidate cap raised accordingly. The Ultra verdicts are most of the cost and the main uncertainty: candidate pairs can grow faster than the page count across a whole report, so the real number could be higher unless the cap stays.
