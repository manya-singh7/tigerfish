# Audit run: cuddalore_port_2026_draft_eia.pdf, pages all

Pairing: {'subjects': 4380, 'key_calls': 110, 'keys_missing': 4, 'numeric_claims': 5138, 'groups': 2130, 'representatives': 3032, 'readings_without_station': 401, 'dropped_by_cap': 22242, 'pairs_same_key': 366, 'pairs_related_key': 1210, 'pairs_part_whole': 0}

Pages audited 768, claims 7019, candidate pairs 1589, triage {'yes': 931, 'no': 657, 'unsure': 1}, Ultra verdicts 932 (failed 0), copy-paste passages 50.

**Cost $3.3379** (INR 280), **wall clock 8.3 min** with 6 workers. Cap $4.00. Stopped: no.

| Stage | Seconds | USD |
|---|---:|---:|
| claims | 10.6 | 0.0000 |
| triage + verdicts | 481.6 | 3.3379 |
| copy-paste | 0.9 | 0.0000 |

| Model | API calls | Cache hits | Tokens in | Tokens out | USD | API seconds |
|---|---:|---:|---:|---:|---:|---:|
| Nemotron-3.5-Super-VL | 0 | 876 | 0 | 0 | 0.0000 | 0 |
| Nemotron-3_5-Lightning | 245 | 1927 | 488,226 | 10,829 | 0.0319 | 158 |
| Nemotron-3-Ultra-550b-a55b | 339 | 596 | 973,149 | 777,632 | 3.3060 | 2639 |
| Tavily | 0 | 63 | | | 0 credits | |

Retries: {'retries': 0, 'rate_limited': 0, 'server_errors': 0, 'connection_errors': 0}

Findings by check and grade:

- recycled_figure: {'RED': 0, 'ORANGE': 0, 'NONE': 5}
- contradiction: {'RED': 12, 'ORANGE': 2, 'NONE': 913}
- copy_paste: {'NONE': 46, 'RED': 4}

Known issues matched: none

## All 18 new RED/ORANGE flags

**cp-p103-4 RED** (copy_paste, pages [103])
- p.103: "Category Area in Ac. % 1 Bulk Storage yard 11.07 7.58 2 Container Area 12.31 8.43 3 Multi Storage Yard 7.96 5.45 4 Liquid Storage Area 8.28 5.67 5 CFS Area 1.46 1.00 6 Transit Shed 7.64 5.23 7 Buildings 1.16 0.79 8 Desalination plant 0.02 0.01 9 Common Utility Area 0.69 0.47 10 Parking Area 3.68 2.52 11 Road 17.1 11.71 12 Rail siding area 7.01 4.80 13 Greenery / Landscaping 15.2 10.41 Total 93.58 14 Future Development area 18.14 12.40 Total Port Backup area 111.72 15 Shipbuilding and Repair area 34.29 23.51"
- Why: site-specific data also in the other document (numbers [0.01, 0.02, 0.47, 0.69, 0.79, 1.16, 1.46, 2.52, 3.68, 4.8, 5.23, 5.45, 5.67, 7.01, 7.58, 7.64, 7.96, 8.28, 8.43, 10.0, 10.41, 11.0, 11.07, 11.71, 12.0, 12.31, 12.4, 13.0, 14.0, 15.0, 15.2, 17.1, 18.14, 23.51, 34.29, 93.58, 111.72]; species [])
- Match: RED https://www.tnpcb.gov.in/PDF/Citizen_corner/ph/ExeSumEngMCPMPL2626.pdf

**cp-p40-2 RED** (copy_paste, pages [40])
- p.40: "Cum 0.0187 0.237 0.237 Beach nourishment towards north side of north breakwater and south side of south breakwater 17 Cargo type - Coal, Cement, Fertilizers and Clean Cargo like container s Coal, Cement, Fertilizers, container, Cereals, wood, clean cargo, Liquid cargo such as non- hazardous and Class A, B, C chemicals including Methanol, Ethylene Di Chloride, Sulphuric Acid 98%, Caustic Soda Lye 48%, Linear Alkyl Benzene, Acetic Acid, Palm Fatty Acid Distillate, Glycerine, Ethanol, Petcock, Bitumen, Low Sulphur Fuel Oil, Marine Gas Oil (NFPA Class II or Class IIIA), Motor Spirit (Class 1A), HSD (Class B Chemical) and Furnace Oil etc., Iron ore, Slag and Limestone Change in cargo mix 18 Water requirement KLD 100 - 100 Desalination plant 19 Desalination plant KLD 100 - 100 No change, 100 KLD will be sufficient."
- Why: site-specific data also in the other document (numbers [0.0187, 0.237, 17.0, 18.0, 19.0, 48.0, 98.0, 100.0]; species [])
- Match: RED https://www.tnpcb.gov.in/PDF/Citizen_corner/ph/ExeSumEngMCPMPL2626.pdf

**cp-p428-1 RED** (copy_paste, pages [428])
- p.428: "There are 235 Mechanized fishing boats and 2345 FRP boats, Non motorised boats 1906 are operating in this district."
- Why: site-specific data also in the other document (numbers [235.0, 1906.0, 2345.0]; species [])
- Match: RED https://cuddalore.nic.in/fisheries

**cp-p74-3 RED** (copy_paste, pages [74])
- p.74: "Cum 0.0187 0.237 0.237 Beach nourishment towards north side of north breakwater and south side of south breakwater 17 Cargo type - Coal, Cement, Fertilizers and Clean Cargo like container s Coal, Cement, Fertilizers, container, Cereals, wood, clean cargo, Liquid cargo such as non- hazardous and Class A, B, C chemicals including Methanol, Ethylene Di Chloride, Sulphuric Acid 98%, Caustic Soda Lye 48%, Linear Alkyl Benzene, Acetic Acid, Palm Fatty Acid Distillate, Glycerine, Ethanol, Petcoke, Bitumen, Low Sulphur Fuel Oil, Marine Gas Oil (NFPA Class II or Class IIIA), Motor Spirit (Class 1A), HSD (Class B Chemical) and Furnace Oil etc., Iron ore, slag and Limestone Change in cargo mix 18 Water requirement KLD 100 - 100 Desalination plant 19 Desalination plant KLD 100 - 100 No change, 100 KLD is not being consumed yet."
- Why: site-specific data also in the other document (numbers [0.0187, 0.237, 17.0, 18.0, 19.0, 48.0, 98.0, 100.0]; species [])
- Match: RED https://www.tnpcb.gov.in/PDF/Citizen_corner/ph/ExeSumEngMCPMPL2626.pdf

**ct-1009 RED** (contradiction, pages [40, 453])
- p.40: "25" (also on pp. 74)
- p.453: "Effluent Treatment Plant KLD - 25 25 No change"
- Why: Page 40 shows an approved capacity of 25 KLD for the Effluent Treatment Plant, while page 453 shows no approved capacity (dash) for the same item; the remarks also differ ("New proposal" vs "No change").
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-1234 RED** (contradiction, pages [40, 453])
- p.40: "25" (also on pp. 74, 492)
- p.453: "Effluent Treatment Plant KLD - 25 25 No change"
- Why: Both tables list the same three infrastructure items with identical Power and Sewage Treatment Plant figures, but the Effluent Treatment Plant row shows an Approved value of 25 KLD on page 40 and a dash on page 453, with conflicting remarks 'New proposal' versus 'No change'.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-354 RED** (contradiction, pages [57, 499])
- p.499: "traffic densities and parking capabilities in a 0.5 kms radius from the site"
- p.57: "in a 05 kms radius from the site"
- Why: The two statements specify different assessment radii (0.5 km vs 05 km) for the same traffic and parking impact assessment, making them numerically incompatible.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-506 RED** (contradiction, pages [98, 99])
- p.98: "Theta =130) and (Hs = 1.5m;"
- p.99: "Theta =70) To assess the wave tranquillity of proposed port expansion during extreme wave conditions, offshore wave climate of 2m has been considered for the analysis."
- Why: Statement 1 assigns Figures 2-30 to 2-32 to three operational wave conditions, while Statement 2 assigns the same figures to two extreme wave conditions. The same figures cannot represent both sets of conditions simultaneously.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-509 RED** (contradiction, pages [622, 623])
- p.623: "current speeds are observed in the range of 0.01 m/s to 1.2 m/s"
- p.622: "current speeds are observed in the range of 0.01 m/s to 1.30 m/s"
- Why: Both statements describe the observed range of current speeds during the same 15-day measurement period at Cuddalore Port, but they give different maximum values (1.2 m/s vs 1.30 m/s).
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-535 RED** (contradiction, pages [239, 433])
- p.239: "Among the 107 plant species reported from the study area, none of the species is listed in IUCN threatened category."
- p.433: "Among the 187 plant species reported from the study area, none of the species is listed in IUCN threatened category."
- Why: The two statements report different totals of plant species from the study area (107 vs 187) without any stated reason for the discrepancy.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-839 RED** (contradiction, pages [31, 39])
- p.31: "Dredging for Turning Circle area with depth -11 m CD, Diameter 300 m,"
- p.39: "Turning Circle Diameter m 310.0 90 400 Increase in diameter and depth" (also on pp. 73, 150)
- Why: Statement 1 lists the turning circle diameter as 300 m and depth as -11 m CD under developed facilities, while Statement 2 shows the approved diameter as 310 m and depth as -10 m CD in the comparison table. The report does not explicitly explain this discrepancy.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-846 RED** (contradiction, pages [253, 459])
- p.253: "The Working population in the project study area is 208711 which are around 41.47%;"
- p.459: "The Working population in the project study area is 208711" (also on pp. 253)
- Why: Statement 1 (Table 3-34) gives a non-working population of 294,621 for the study area, while Statement 2 gives 4,294,621; the working population figures (208,711, 41.47%) are identical.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-869 RED** (contradiction, pages [38, 39])
- p.38: "8.54" (also on pp. 75, 371, 454)
- p.39: "Cargo handling capacity MTPA 5.68 5.8 11.48 Increase in cargo handling capacity" (also on pp. 38, 72, 73, 75, 371, 451, 452, 454, 494)
- Why: Statement 1 lists bulk berth capacity as 8.54 MTPA within a total of 11.48 MTPA, while Statement 2 lists the proposed capacity increase as 5.8 MTPA on top of an approved 5.68 MTPA to reach the same total; the bulk berth capacity exceeds the proposed increase without explanation.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-875 RED** (contradiction, pages [108, 451])
- p.451: "2" (also on pp. 491)
- p.108: "(2- Multipurpose Cargo berths [440m length]"
- Why: Statement 1 shows three multipurpose berths totaling 440m quay length (2 approved + 1 proposed), while Statement 2 describes two multipurpose cargo berths of 440m length as proposed, creating a numerical discrepancy.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-924 RED** (contradiction, pages [451, 491])
- p.451: "21" (also on pp. 491)
- p.491: "Width m 21 21 21" (also on pp. 451)
- Why: Both statements refer to the width of multipurpose berths in the same expansion plan table, but page 451 shows a dash for the proposed width while page 491 shows 21 m, making the proposed values contradictory.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-962 RED** (contradiction, pages [38, 494])
- p.38: "11.48" (also on pp. 39, 72, 73, 75, 371, 451, 452, 454, 494)
- p.494: "8.54"
- Why: Both statements report a total cargo handling capacity of 11.48 MTPA and a bulk berth capacity of 8.54 MTPA, but the bulk berth cargo mix differs: Statement 1 includes Slag while Statement 2 does not, making the two descriptions mutually exclusive for the same berth.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-562 ORANGE** (contradiction, pages [84, 725])
- p.725: "08-09-2025 19:40 116.41 9.48 0.55 3.67"
- p.84: "The observation period at Cuddalore port crosses one neap and one spring tide. It shows that the significant wave height varies from 0.4m to 1.1m." (also on pp. 622)
- Why: Statement 1 shows significant wave height (Hs) measurements ranging from 0.43 to 0.55 m, while Statement 2 states that at Cuddalore port the significant wave height varies from 0.4 m to 1.1 m with a maximum of 1.1 m. The report does not explain why the measured maximum in the table is lower than the reported maximum for the observation period.
- Ultra's answers: {'same_subject': True, 'same_place': 'unclear', 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-946 ORANGE** (contradiction, pages [39, 150])
- p.150: "APPROACH CHANNEL (110m WIDE)"
- p.39: "Unprotected area/outer channel m - 160 160" (also on pp. 452)
- Why: Statement 1 gives a single approach channel width of 110 m, while Statement 2 lists several distinct widths for different channel sections (60 m, 100 m, 130 m, 160 m) without indicating that 110 m corresponds to any of them.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': 'unclear', 'incompatible': True, 'explained': False}
