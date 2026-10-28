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
- copy_paste: {'NONE': 90, 'RED': 10}

Known issues matched: none

## All 21 new RED/ORANGE flags

**cp-p115-2 RED** (copy_paste, pages [115])
- p.115: "95 Table IV-7 Project Roads Located in High Drought Recurrence Taluks (12–15 Year Frequency Class) District High Drought- prone Taluka Drought Frequency Roads IDs Bagalkote Jamkhandi,Badami, Guledagudda High (12- 15 Years) 24, 109, 117, 118, 125, 131, 136, 141, 1324, 1372, 2085, 2160, 2337, 2818, 2821, 3372, 3644, 4487, 4598, 4606, 4607, 4648, 5183, 5251 Total – 24 Roads Raichur Deodurga, Raichur High (12- 15 Years) 1931, 2442, 3099, 3113, 3114, 3127, 3190, 3307, 4410, 4480, 4481, 4506, 4902, 4920, 5247, 5248, 5249, 5264 Total – 18 Roads Ballari & Vijayanagara Siruguppa, Kampli, Hosapete, Sandur,Ballari, High (12- 15 Years) 351, 630, 660, 671, 679, 695, 700, 808, 810, 825, 828, 892, 901, 904, 909, 913, 925, 2765, 2968, 3257, 3270, 3354, 3367, 3378, 3381, 4007, 4009, 4446, 4468, 4745, 4749, 4756, 4757, 4758, 4759, 4842, 4886, 4925, 4997, 5019, 5252, 5385, 5391, 5479 Total – 44 Roads Haveri Hirekerur High (12- 15 Years) 954, 997, 2214, 2380, 4246, 5343, 5434 Total – 7 Roads Gadag Laxmeshwar High (12- 15 Years) 144, 2301, 4287, 4522, 4580 Total – 5 Roads Chikkaballapu ra Bagepalli, Chikkaballapura, Chintamani High (12- 15 Years) 60, 409, 417, 462, 470, 476, 491, 1897, 3117, 3186, 3868, 3869, 3870, 3878, 3998, 4081, 5219 Total – 17 Roads Kolar Srinivasapura, Kolar, Mulbagal, Bangrapete, High (12- 15 Years) 120, 382, 438, 596, 748, 912, 950, 960, 1108, 1126, 1203, 1204, 1217, 1302, 1425, 1444, 1663, 1697, 1897, 1975, 2211, 2485, 2492, 2789, 2958, 3462, 3469, 3526, 3539, 3546, 3565, 3609, 3841, 4013, 4578, 5282, 5373, 5508 Total – 38 Roads Ramanagara Horohalli, Kanakapura, High (12- 15 Years) 1817, 1818, 1819, 3891, 5085, 5089, 5130, 5141, 5142, 5180, 5226, 5422, 5423, 5427, 5428 Total – 15 Roads Chamarajana gara Kollegal, Hansur High (12- 15 Years) 2536, 2538, 2540, 2543, 4221 Total –5 Roads Note: The classification is based on taluka-level drought frequency and provides a screening-level indication; it does not represent road-specific drought intensity."
- Why: site-specific data also in the other document (numbers [12.0, 15.0, 17.0, 18.0, 24.0, 38.0, 44.0, 60.0, 95.0, 109.0, 117.0, 118.0, 120.0, 125.0, 131.0, 136.0, 141.0, 144.0, 4446.0, 4758.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

**cp-p154-3 RED** (copy_paste, pages [154])
- p.154: "Railway Weed Euphorbiace ae Herb - 197 Cryptocarya wightiana Thwaites Cupped-Fruit Litsea Lauraceae Tree LC 198 Cucumis prophetarum L."
- Why: site-specific data also in the other document (numbers [197.0, 198.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

**cp-p155-4 RED** (copy_paste, pages [155])
- p.155: "Chanchali Amaranthace ae Herb - 231 Digitaria ciliaris (Retz.) Koeler Wild Crabgrass Poaceae Gras s - 232 Dillenia pentagyna Roxb."
- Why: site-specific data also in the other document (numbers [231.0, 232.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

**cp-p17-1 RED** (copy_paste, pages [17])
- p.17: "The estimated EMP implementation budget is ₹326 million, and the Biodiversity Action Plan budget is ₹370 million, a combined ₹696 million or approximately ₹0.13 million per km, in addition to costs embedded in civil works contracts."
- Why: site-specific data also in the other document (numbers [326.0, 370.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

**cp-p23-5 RED** (copy_paste, pages [23])
- p.23: "Of these, 307 roads intersect forests, 14 roads traverse legally protected areas and 86 are in their eco-sensitive zones."
- Why: site-specific data also in the other document (numbers [14.0, 86.0, 307.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

**cp-p25-6 RED** (copy_paste, pages [25])
- p.25: "According to the Census of India 2011, Karnataka had a population of 61,095,297 individuals, comprising 5.05% of the country’s total population."
- Why: site-specific data also in the other document (numbers [5.05, 2011.0, 61095297.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

**cp-p53-7 RED** (copy_paste, pages [53])
- p.53: "Further, 307 roads intersect reserved forests, 14 roads traverse legally protected areas and 86 are in their eco-sensitive zones14."
- Why: site-specific data also in the other document (numbers [14.0, 86.0, 307.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

**cp-p57-8 RED** (copy_paste, pages [57])
- p.57: "Roads inside forest lands, legally protected areas, and other ecologically sensitive areas where sufficient ROW was not available and required additional land were not selected in this Project, except road ID 4817, where 1.02 hectares of forest land will be required."
- Why: site-specific data also in the other document (numbers [1.02, 4817.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

**cp-p91-9 RED** (copy_paste, pages [91])
- p.91: "In the year 2025, the state recorded 1,319 mm rainfall, representing a 14% positive departure from the long-term normal."
- Why: site-specific data also in the other document (numbers [14.0, 1319.0, 2025.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

**cp-p93-10 RED** (copy_paste, pages [93])
- p.93: "District wise Annual rainfall pattern during 2025 in Karnataka state is presented in Figure IV-11 indicates that during 2025, the rainfall was Excess in 11 Districts, Normal in 19 districts while Deficit in Chamarajanagara."
- Why: site-specific data also in the other document (numbers [11.0, 19.0, 2025.0]; species [])
- Match: RED https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf

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
