# Audit run: karnataka_rural_roads_2026_adb_eia.pdf, pages all

Pairing: {'subjects': 1640, 'key_calls': 41, 'keys_missing': 0, 'numeric_claims': 1697, 'groups': 1108, 'representatives': 1357, 'readings_without_station': 172, 'dropped_by_cap': 993, 'pairs_same_key': 140, 'pairs_related_key': 222, 'pairs_part_whole': 39}

Pages audited 364, claims 4359, candidate pairs 404, triage {'yes': 248, 'no': 151, 'unsure': 5}, Ultra verdicts 253 (failed 0), copy-paste passages 100.

**Cost $2.4040** (INR 202), **wall clock 66.5 min** with 6 workers. Cap $5.00. Stopped: no.

| Stage | Seconds | USD |
|---|---:|---:|
| claims | 50.9 | 0.0056 |
| triage + verdicts | 3062.0 | 2.3725 |
| copy-paste | 408.4 | 0.0016 |

| Model | API calls | Cache hits | Tokens in | Tokens out | USD | API seconds |
|---|---:|---:|---:|---:|---:|---:|
| Nemotron-3_5-Lightning | 313 | 130 | 649,706 | 82,094 | 0.0587 | 17065 |
| Nemotron-3.5-Super-VL | 2 | 450 | 9,065 | 3,210 | 0.0056 | 31 |
| Nemotron-3-Ultra-550b-a55b | 253 | 0 | 829,770 | 503,325 | 2.3397 | 2357 |
| Tavily | 154 | 8 | | | 128 credits | |

Retries: {'retries': 4, 'rate_limited': 0, 'server_errors': 0, 'connection_errors': 4}

Findings by check and grade:

- recycled_figure: {'RED': 0, 'ORANGE': 0, 'NONE': 2}
- contradiction: {'RED': 11, 'ORANGE': 0, 'NONE': 240}
- copy_paste: {'NONE': 90, 'GREY': 10}

Known issues matched: none

## All 11 new RED/ORANGE flags

**ct-007 RED** (contradiction, pages [11, 317])
- p.11: "requires forest clearance for diversion of 0.748 ha under the Van (Sanrakshan Evam Samvardhan) Adhiniyam, 1980" (also on pp. 12)
- p.317: "Forest Clearance – Scrutiny of the forest clearance proposal for road ID 4817 involving 1.02 hectares of forest land diversion, recommendation to state government for the clearance, providing stage-1 clearance and provide report on compliance with the conditions to the State Government/ MoEFCC, Implementation Monitoring and Reporting, to assist in the process of providing stage-2 forest clearance."
- Why: Page 11 states 0.748 ha of forest land diversion for Road ID 4817, while page 317 states 1.02 hectares for the same road. The report does not explain the discrepancy.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-019 RED** (contradiction, pages [136, 286])
- p.136: "Out of the 1335 project roads, 547 roads are reported to have surface water body within 500m."
- p.286: "Approximately 500 roads not only has surface water bodies within 2 km of the roads, streams or canals also crosses a number of project roads."
- Why: The first statement reports 547 roads with surface water bodies within 500 m, while the second states approximately 500 roads have surface water bodies within 2 km; since the 500 m buffer is a subset of the 2 km buffer, the latter number should be at least 547, making the two figures incompatible.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-020 RED** (contradiction, pages [51, 271])
- p.271: "The requirement of 0.748 hectares of additional forest land for one project road (4817) has been indicated in the data shared by KRRDA."
- p.51: "one road will require additional forest land amounting to ~1.02 hectares"
- Why: Both statements cite KRRDA data for additional forest land needed for project road 4817 but report different hectare figures (0.748 vs ~1.02) with no explanation in the provided text for the discrepancy.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-056 RED** (contradiction, pages [51, 59])
- p.51: "one road will require additional forest land amounting to ~1.02 hectares"
- p.59: "except for one road (4817) which requires ~0.748 ha of forest land" (also on pp. 206)
- Why: The two statements give different figures (~1.02 ha vs ~0.748 ha) for the additional forest land required for road 4817, and the report does not explain the discrepancy.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-094 RED** (contradiction, pages [14, 23])
- p.23: "305 roads are located outside protected areas and eco-sensitive zones but fall within EAAAs identified as critical habitat"
- p.14: "The remaining 420 roads are within EAAAs determined to be critical habitats but outside legally designated protected areas, forest lands, or eco-sensitive zones"
- Why: The two statements give different counts (305 vs 420) for the same residual category of roads within EAAAs but outside protected areas, forest lands, and eco-sensitive zones. Page 14 notes that 171 roads fall into multiple categories, which may affect the calculation, but the report does not explicitly reconcile the two figures.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-102 RED** (contradiction, pages [57, 357])
- p.357: "0.748 ha of forest land"
- p.57: "except road ID 4817, where 1.02 hectares of forest land will be required."
- Why: Both statements refer to forest land for Road ID 4817, but report different areas (0.748 ha diversion vs 1.02 ha required) without any explanation in the provided pages.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-264 RED** (contradiction, pages [263, 329])
- p.329: "50" (also on pp. 263)
- p.263: "Noise Pollution (Regulation and Control) Rules, 2000 limits applicable to Silence Zones (50 dB(A) day; 40 dB(A) night)."
- Why: Both statements give a nighttime noise limit for Silence Zones but cite different values (50 dB(A) vs 40 dB(A)) without reconciling them.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-265 RED** (contradiction, pages [263, 329])
- p.329: "50" (also on pp. 263)
- p.263: "Noise Pollution (Regulation and Control) Rules, 2000 limits applicable to Silence Zones (50 dB(A) day; 40 dB(A) night)."
- Why: Both statements refer to Silence Zone noise limits under India's Noise Pollution (Regulation and Control) Rules, 2000, but give different nighttime values (50 dB(A) vs 40 dB(A)). The report does not explain this discrepancy.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-283 RED** (contradiction, pages [263, 329])
- p.329: "50"
- p.263: "Noise Pollution (Regulation and Control) Rules, 2000 limits applicable to Silence Zones (50 dB(A) day; 40 dB(A) night)."
- Why: Both statements give the daytime Silence Zone limit as 50 dB(A), but the national standards table (page 329) lists the night limit as 50 dB(A) while the assessment text (page 263) cites the Rules as 40 dB(A) night, a direct numerical conflict.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-284 RED** (contradiction, pages [263, 329])
- p.329: "50"
- p.263: "Noise Pollution (Regulation and Control) Rules, 2000 limits applicable to Silence Zones (50 dB(A) day; 40 dB(A) night)."
- Why: Both statements give noise limits for Silence Zones under Indian national standards, but the night limit differs (50 dB vs 40 dB) with no explanation in the report for the discrepancy.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-354 RED** (contradiction, pages [71, 253])
- p.71: "Borrow materials such as soil, gravel, moorum, or laterite required for embankment, subgrade, and shoulders will be procured from approved borrow areas generally located within 2 km to 10 km of the Project alignment."
- p.253: "with borrow areas to be sourced within 200 m of the alignment wherever suitable material is available"
- Why: The first statement says borrow areas are generally 2-10 km from the alignment, while the second says they should be sourced within 200 m wherever suitable material is available, without clarifying how these two ranges relate.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

## Excluded copied-text matches (10, GREY: self-match: same report published elsewhere)

- p.17: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 18 words)
- p.115: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 16 words)
- p.154: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 19 words)
- p.155: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 18 words)
- p.23: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 20 words)
- p.25: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 24 words)
- p.53: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 20 words)
- p.57: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 41 words)
- p.91: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 21 words)
- p.93: https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf (self-match: same report published elsewhere (one of this report's paper-trail documents); longest run 35 words)
