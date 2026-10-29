# TigerFish: reminders by block

Agent: at the start of every block, read this file and remind the user of the items for that block.

## Current state and next work (30 October 2026)

Saved JSON and code take precedence over the historical run notes below. The library has
3 full-report audits, 1 published-table check and 25 Maharashtra executive-summary checks:
2,802 PDF pages plus one table, 234 RED/ORANGE cards and 23 standard INFO leads. Three
additional batch baseline INFO leads have known extraction errors. See `docs/LIMITATIONS.md`
for scope and `docs/FEATURES.md` for current UI entry points.

- [x] Python 3.12 + uv lockfile and dev dependency group.
- [x] Branded Home, Library, Upload, How it works and Limitations; report sections, evidence
  slips, highlighted crops, model badges, responsive theme, logo and self-hosted fonts.
- [x] Three full-report replays, Indira Point table, 25 quick checks, corpus index and batch
  discovery/check scripts. Quick checks are not full three-model audits.
- [x] Own-document copy matches excluded and inspectable: 10 Karnataka and 3 Cuddalore RED cards removed.
- [x] Human review/feedback, regional-language letters, RTI pack and review imports exist.
- [x] Offline suite run: 976 passed, 1 failed, 1 skipped, 7 deselected. Failure: reset-filter
  test expects all cards despite the library's initial 10-card pagination.
- [ ] Specify and test pagination: 10 initially, ordered Show more without duplicates,
  reset clears filters and restores the initial page, all matching reports remain reachable.
- [ ] Fix batch baseline extraction: shared-year ranges, report-number exclusion, study vs
  administrative/traffic context, calendar-aware durations and conflicting evidence.
- [ ] Regenerate baseline results from source documents without rerunning unrelated checks.
- [ ] Expose batch check results, uncertainty and observations on report pages and a reachable summary.
- [ ] Recheck copied-text leads for taxonomy years, legitimate secondary data and attribution.
- [ ] Verify and rehearse a short three-NVIDIA-model demo with real pages and labelled replays.
- [ ] Confirm public deployment, record video/screenshots and finish submission.

The Ultra verdict prompt remains **FROZEN** (Block G). Do not mark manual reviews or
deployment complete based on tests. Balances and estimates below are historical.

## Waiting on (check daily)
- [x] Hackathon credits promo code (form sent Oct 24, ~10:40pm IST): ARRIVED (Oct 27)
- [x] Builders Program email ($25 Token Factory, $25 Tavily, $100 LangSmith, $100 Toloka): ARRIVED (Oct 27)
- Balance as of Oct 27: Token Factory ~$29.50, Tavily ~4,000 credits
- [ ] Replies: Discord #devpost-global-ai-hackathon, sujee@nebius.com, support@devpost.com, Token Factory "Contact us" ticket, Devpost forum
- [ ] Confirm the received Token Factory/Tavily codes were redeemed in Billing (arrival is recorded; redemption is not).
- [ ] Before the trial ends: check whether promo credits need paid usage turned on; set a spending limit/alert first

## Before any commit
- [x] .gitignore has: .env, cache/, logs/, .venv/, __pycache__/, data/eias/*.pdf
- [ ] Run `git status` and make sure no PDFs, .env, cache or logs are staged

## Manual verification (you + teammate, by hand, not AI)
- [x] Hand check recorded (Oct 27, Manya Singh): 12 known issues in data/known_issues.json, 12/12 pass on the full audit (eval.md 1b); "Human-verified" badge + reviewed wording on 10 app cards; ct-071 / ct-979 / ct-239 count as reviewed in the queue. New ids: gn-006 (ct-071), gn-007 (ct-979), gn-008 (ct-239), gn-009 (sp-p954-001), gn-010 (ac-01), gn-011 (pr-06, id chosen by Claude: rename if you prefer)
- [x] gn-001: p.392 and p.978 read: confirmed with nuance (ORANGE), "inconsistent about coral at the port site"
- [ ] gn-001: ZSI coral pages p.937-1079 (search 116 / hectare / reef / Galathea)
- [x] gn-002: explained (p.751: the 4 ha covers the whole project); kept as a second negative control (status explained), not deleted
- [x] gn-003: p.818 / 851 / 1168 breakdowns identical: confirmed
- [x] Add verified_by, verified_on, verification_note to each entry
- [x] rf-001 / gn-005: confirmed (attribution: the duplication is in the Gazette ESZ notifications); now scored (status removed)
- [ ] ct-005: p.444 (total reclaimed land 194 ha) vs p.751 (71 ha for the airport): likely part-vs-total; Ultra now grades NONE. Confirm the 71 ha is a component of the 194 ha.
- [ ] Table 3.16 status: Macaca fascicularis listed VU in the report, IUCN now EN (GBIF https://www.gbif.org/species/2436603). Confirm on the IUCN Red List and note the assessment year.
- [ ] Table 3.16 taxonomy: Pteropus giganteus. GBIF (and GBIF's IUCN data) map it to P. vampyrus (EN); the Indian flying fox is usually P. medius (LC). Decide which name the report means before using any status for it.
- [x] gn-002: the 4 ha of coral restoration covers the entire project (p.751 Table 10.3): explained, now a negative control

- [x] (gn-009, confirmed: likely misidentification) Species table p.954: Panulirus interruptus, RED at Campbell Bay: GBIF 0 within 100 km, 0 within 500 km, 0 in the A&N Islands, 0 within 3,000 km, 294,577 worldwide. Is it really recorded at Great Nicobar?
- [ ] Species tables, flora (not in the app): Musa sabuana p.310, Phalaenopsis speciosa p.317, Phalaenopsis speciosa p.1030: each has only 1 GBIF record worldwide; likely data gaps (Phalaenopsis speciosa is native to the islands). Check against the Flora of Andaman & Nicobar.

- [ ] ToR promises (ORANGE, check by hand against data/eias/great_nicobar_tor_2021.pdf and the draft EIA):
  - [x] (gn-011, confirmed; say "proposed ToR": flora/fauna was a rapid reconnaissance 14-22 Dec 2020, air/water/soil did run 3 months) pr-06: ToR p.1 baseline "3 months" (flora & fauna listed) vs p.292 "Quick primary survey" 14-22 Dec 2020 (9 days) + turtle survey 12-18 Feb 2021. Does any other page show a longer ecology survey?
  - [ ] pr-08: ToR p.2 corals "up to a depth of about 40 m" vs p.987 transects "deeper reef-16-30m". Check the ZSI coral pages for any dive deeper than 30 m.
  - [ ] pr-13: ToR p.3 water "20 locations" vs p.279 "sixteen locations" (8 surface + 8 ground water). Check Table 3.18 / Figure 3.34.
  - [ ] pr-15: ToR p.3 soil "three different levels up to a depth of 90 cm" vs p.258 "three different depths viz. 30 cm" and "up to a depth of 30 cm"; but p.870 (annexure) says "30 cm, 60 cm and 90 cm". Also p.258 says "20 locations" and "A total of 10 numbers of samples". Which is right?
- [x] Find the granted ToR (25 May 2021) through the paper trail and run a separately labelled comparison: 2 measurable commitments, both INFO.
- [ ] Read the granted letter and standard ToR it incorporates; pr-06 still rests on the proposed ToR, not a proven granted-condition breach.

- [ ] Full-audit top 30 (review/review_queue.json, report section "Quality"; D = independent judgments; quick triage notes in results/full_audit_summary.md are not recorded human decisions):
  - [x] (verified by hand: gn-006) 1. ct-071 (D) ORANGE p.738/1085: "As per the ZSI report, coral do not exist in the Galathea Bay area, ho" vs "the presence of 117 species of scleractinian corals" [likely real]
  - [ ] 2. ct-056 ORANGE p.738/978: "As per the ZSI report, coral do not exist in the Galathea Bay area, ho" vs "Coral reef exists in the proposed site for Transshipment / Port" [likely real]
  - [ ] 3. ct-1645 (D) RED p.438/446: "916 Ha of area has been identified for development of International Ai" vs "the present site needs to reclaim land approximately 194 Ha of land in" [likely real]
  - [ ] 4. ct-1464 (D) RED p.133/438: "The present site needs to reclaim land approx. 1.94 Ha of land in orde" vs "the present site needs to reclaim land approximately 194 Ha of land in" [likely real]
  - [ ] 5. ct-783 RED p.725/919: "The cost of the Airport is estimated at Rs. 10,35,900 lakhs." vs "1 Airport 8,58,300" [likely real]
  - [ ] 6. ct-1086 (D) RED p.87/1151: "The breakwaters are shore connected with a length of 3.90 km." vs "Breakwaters of 3.27 Km (2.53 km east breakwater & 0.74 km west offshor" [likely real]
  - [ ] 7. ct-221 (D) RED p.918/972: "RESIDENTIAL 16.55 9.97" vs "RESIDENTIAL 36.66 22.07" [likely real]
  - [ ] 8. ct-217 RED p.22/26: "Great Nicobar Biosphere Reserve 732.79" vs "Great Nicobar Biosphere reserve (885 sq.km)" [likely real]
  - [ ] 9. ct-225 RED p.26/942: "Campbell bay National Park (426.23 sq.km)" vs "Campbell Bay National Park (520 km2 area)" [likely real]
  - [ ] 10. ct-226 RED p.22/942: "Galathea National Park 107.10" vs "the Galathea National Park (185 km2 area)" [likely real]
  - [ ] 11. ct-1607 RED p.17/1115: "With an area of 910.074 sq.km, the Island represents a huge, strategic" vs "The total area of the island is 973 km2" [likely real]
  - [ ] 12. ct-1254 (D) RED p.228/942: "Great Nicobar Island marks the southernmost tip of India 7° N, about 7" vs "is only about 145 km from Sumatra Island of Indonesia" [likely real]
  - [ ] 13. ct-1176 (D) RED p.243/249: "1.842" vs "Approximately 65.43 ha of the mangroves were affected, and 32.06 ha ar" [likely real]
  - [ ] 14. ct-673 (D) RED p.1047/1126: "203" vs "103 nests in 2018-19" [likely real]
  - [x] (verified by hand: gn-008) 15. ct-239 RED p.291/337: "heavy annual rainfall of 300 to 350 Cm spreading over 9 months" vs "The annual rainfall ranges from 3000 to 3500 Cm" [likely real]
  - [ ] 16. ct-1385 RED p.207/210: "39 Acres" vs "Planned layout has been developed in order to accommodate the plant fa" [likely real]
  - [ ] 17. ct-200 RED p.134/459: "Out of which part will be met by the DG sets of 2 x 5 MVA each" vs "operation of 7 DG sets for continuous 8 hours per day" [likely real]
  - [ ] 18. ct-812 RED p.45/279: "10 SW" vs "Eight surface water and Eight ground water sources covering were exami" [likely real]
  - [ ] 19. ct-414 RED p.29/324: "Of the 25 species of mammals found on the island" vs "A total of 14 species of mammals" [likely real]
  - [ ] 20. ct-387 RED p.29/1168: "71 species of birds" vs "97 species of birds" [likely real]
  - [ ] 21. ct-1625 (D) RED p.445/1088: "in 16610 ha, at Great Nicobar Islands, Nicobar District" vs "14,960 Ha and Power Plant" [needs a look]
  - [ ] 22. ct-617 (D) RED p.40/109: "4000 Peak Hour Passengers" vs "The airstrip will be developed to cater for operation of Code C type o" [possible false alarm]
  - [ ] 23. ct-402 (D) RED p.940/944: "A total of 695 species of fauna with the endemism of 158 species" vs "The fauna consists of over 1800 species" [possible false alarm]
  - [ ] 24. ct-209 RED p.743/770: "Two control points with two porta cabins and with 3 shifts total 6 per" vs "Ten control points with 10 porta cabins and with 3 shift, total 30 per" [possible false alarm]
  - [ ] 25. ct-1106 RED p.1051/1053: "Estimated capacity: 15 Million TEUs per annum" vs "Estimated capacity: 14.2 Million TEUs per annum" [possible false alarm]
  - [ ] 26. ct-240 (D) RED p.24/918: "The ICTT can be developed at a cost of Rs. 35,95,900" vs "The ICTT will be developed at a cost of Rs. 35,959 Crore." [false alarm]
  - [ ] 27. ct-604 (D) RED p.87/965: "The east & west breakwater extends till the 20 m & 25 m contour respec" vs "The east & west breakwater extends till the 20 m & 25 m contour respec" [false alarm]
  - [ ] 28. ct-1366 RED p.69/391: "2 2055 Final Phase 16 5,400 3,700" vs "building of 13 berths" [false alarm]
  - [ ] 29. ct-051 (D) RED p.411/1124: "ZSI data suggest that the Galathea Bay is devoid of any coral reefs." vs "Except the Galathea Bay, coral reefs were found near the all nesting b" [false alarm]
  - [ ] 30. cp-p1001-1 (D) RED p.1001: "ZOOPLANKTON SPECIES CB JB LB RB GB Class HEXANAUPLIA Oakley, Wolfe, Li" [false alarm]
  - [ ] Then the rest of the queue (123, random order) as time allows; report precision on the random part. New after the top-up: ct-1815 RED p.1144/1166, deemed forest 4.39 vs 8.88 sq km (#123).

## Block B (PDF reader + Super-VL)
- [ ] Demo: Super-VL reads the table image -> species list -> species check. This is the headline demo shot.

## Block D (species check, GBIF)
- [x] Test case: data/demo/indira_point_table_3_16_mammals.png (Table 3.16 of the WAPCOS Indira Point REIA, Apr 2026, as published by Scroll.in Aug 31 2026). Location: Indira Point 6.75 N, 93.83 E.
  - Assert only: Macaca fascicularis and Tupaia nicobarica must NOT be flagged (real Nicobar species).
  - All others are report-only (GREY is acceptable, it's the safe outcome).
  - [x] Handle old synonyms (Cervus unicolor -> Rusa unicolor) and typos ("Taupaia") via GBIF match; report the corrected name.
- [x] Add the source line to data/eias/SOURCES.md.
- [ ] Check GBIF synonym mappings by hand: Pteropus giganteus -> Pteropus vampyrus looks wrong (Indian flying fox is usually P. medius)
- [ ] Regional-effort fallback is borderline here: 513 mammal records within 500 km vs threshold 500

## Public record / knowable (added Oct 28)
- [ ] Check by hand the 3 timeline events in the Public record tab (results/public_record_great_nicobar_2021_draft.json) against their sources (dstpcc.andamannicobar.gov.in public-hearing PDF, PIB 2076917)
- [ ] Check the one "knowable at the time" line (st-06, Mongabay Oct 2025: Macaca fascicularis raised to Endangered in 2022): 16 other findings had no dated pre-report source, so they show nothing
- [ ] Glance at the 8 species photos (results/species_photos.json): right species, attribution OK

## What's next / stretch
- [x] ToR vs EIA check: compare promises in data/eias/great_nicobar_tor_2021.pdf (3-month baseline, corals to 40 m, 20 water/noise sites) with what the EIA delivered (tigerfish/promises.py, scripts/check_promises.py, "ToR promises" tab).

## Block E (copy-paste check, Tavily)
- [x] Use the "Deep Research Agent with Tavily + Token Factory" cookbook (github.com/nebius/token-factory-cookbook) as the reference pattern

## Block F (Streamlit UI)
- [ ] Optional: LangSmith free plan (smith.langchain.com), add LANGSMITH_API_KEY to .env, wrap calls in llm.py (~30 min)
- [ ] Take one clean trace screenshot for README/video
- [x] Replay opens on Home with the library below it; saved reports and evidence need no keys or source PDFs.
- [ ] Host free on Streamlit Community Cloud or Hugging Face Spaces (not paid Nebius compute)

## Block G (evaluation)
- [x] Use the "Agentic Cost Benchmark" cookbook to report cost, tokens and time per audit ("Full 1,213-page EIA audit: Rs X, Y min")
- [x] gn-001 counts as caught if graded RED or ORANGE
- [x] Parallel calls (6 workers, retries, resumable) + rehearsal on p.250-350: $0.80, 7.2 min (results/audit_great_nicobar_2021_draft_eia__p250-350.md, results/full_run_estimate.md)
- [x] False-alarm fixes (structured Ultra verdicts, statement subject X, recycled >25 / ToR counts, copy-paste boilerplate, Super-VL long retry + salvage, number words): rehearsal now 2 flags
- [x] Rainfall p.291 "3000 to 3500 Cm" vs p.337 "300 to 350 Cm": confirmed by hand (gn-008, low severity, likely unit slip)
- [x] gn-001 wording fix applied ("differences of place belong in same_place"): gn-001 now ORANGE
- [x] Scope wording applied ("unclear only with a concrete, named reason"); statement pairs are incompatible by construction (compute_grade). Eval: gn-001 ORANGE, gn-003/004/005 RED, control NONE, planted 10/10, 0/5 explained
- **Ultra verdict prompt is FROZEN (Oct 27): no further wording changes before submission** (tigerfish/contradictions.py, step 3)
- [x] Ultra now gets the full sentence(s) around each quote: ct-105 (p.285 vs p.286) is NONE
- [x] Full run (Oct 27): $15.18, 54 min, 84 Tavily credits; known issues unchanged; 152 new flags in the review queue (results/full_audit_summary.md)
- [x] Top-up (Oct 27 16:31, $0.49, 0 Tavily): 166 salvaged claims added (+67 pairs), failed verdict retried (ct-1179 NONE); earlier ids and grades unchanged; 1 new flag (ct-1815). Final: $15.67, 153 new flags
- [x] 11 added pairs judged (Oct 27 22:19, $0.11, all NONE). Final: $15.78, 62 min, 1,866 pairs, 0 not judged
- [x] Second estimate in scripts/audit.py now prices only pairs that would reach Ultra (cached triage "no" skipped; untriaged pairs at the pass rate)
- [x] Evaluation re-run from cache ($0): 7/7 on the 10 known-issue pages, 12/12 on the full audit with every check, both negative controls not flagged
- [x] Run the offline suite: `uv run --locked python -m pytest -q -m "not live" --ignore=tests/test_species_live.py`. Latest result and remaining failure are recorded above.
- [x] Statement-pair rule tightened (override only if same_subject yes and same_place not no): 0 of the 19 flags change (all 19 qualify), gn-001 still ORANGE

## Write-up (Oct 29)
- [ ] "What's next": route uncertain ORANGE flags to human experts via Toloka
- [x] Feedback section, reviewer suggestions and export/import are implemented.
- [ ] Great Nicobar EIA consultant is Vimta Labs; Indira Point REIA is WAPCOS. Never describe them as the same consultant.
- [ ] Submit by the hard deadline: Oct 30, 10:30pm IST (the Oct 29 evening target has passed).

## Optional stretch / earlier scope cuts
- LangSmith and Toloka expert routing remain optional. The earlier 5/10-EIA target has
  been superseded by 3 full audits and 25 no-model summaries, not 25 full model audits.
