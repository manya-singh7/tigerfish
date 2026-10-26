# Audit run: great_nicobar_2021_draft_eia.pdf, pages 250-350

Pages audited 94, claims 1325, candidate pairs 286, triage {'yes': 84, 'no': 198, 'unsure': 4}, Ultra verdicts 88 (failed 0), copy-paste passages 100.

**Cost $0.7984** (INR 67), **wall clock 7.2 min** with 6 workers. Cap $1.50. Stopped: no.

| Stage | Seconds | USD |
|---|---:|---:|
| claims | 156.0 | 0.2814 |
| triage + verdicts | 105.3 | 0.5138 |
| copy-paste | 172.1 | 0.0032 |

| Model | API calls | Cache hits | Tokens in | Tokens out | USD | API seconds |
|---|---:|---:|---:|---:|---:|---:|
| Nemotron-3_5-Lightning | 229 | 0 | 415,278 | 37,659 | 0.0340 | 295 |
| Nemotron-3.5-Super-VL | 96 | 0 | 417,109 | 162,366 | 0.2713 | 749 |
| Nemotron-3-Ultra-550b-a55b | 88 | 0 | 215,920 | 92,422 | 0.4932 | 356 |
| Tavily | 64 | 93 | | | 59 credits | |

Retries: {'retries': 0, 'rate_limited': 0, 'server_errors': 0, 'connection_errors': 0}

Findings by check and grade:

- recycled_figure: {'RED': 1, 'ORANGE': 0, 'NONE': 1}
- contradiction: {'RED': 1, 'ORANGE': 3, 'NONE': 82}
- copy_paste: {'NONE': 112, 'RED': 3}

Known issues matched: none

## Top 8 new RED/ORANGE (of 8)

**cp-p287-1 RED** (copy_paste, pages [287])
- p.287: "The integrating sound level meter is an integrating/logging type with Octave filter attachment (model OB-100) with frequency range of 31.5 to 16000 Hz."
- Why: site-specific data also in the other document (numbers [31.5, 100.0, 16000.0]; species []) (https://jsw-steel-s3.s3.ap-south-1.amazonaws.com/jsw-steel-images/uploads/2026/01/JSW_Narayanposhi-Mines_OCT.2023-MAR.2024-Six-monthly-EC-Compliance_compressed.pdf)

**cp-p287-2 RED** (copy_paste, pages [287])
- p.287: "The integrating sound level meter is an integrating/logging type with Octave filter attachment (model OB-100) with frequency range of 31.5 to 16000 Hz."
- Why: site-specific data also in the other document (numbers [31.5, 100.0, 16000.0]; species []) (https://www.tnpcb.gov.in/PDF/Citizen_corner/ph/EIARptEngAshokleyland2482.pdf)

**cp-p288-3 RED** (copy_paste, pages [288])
- p.288: "The notation for the statistical quantities of noise levels are described below: • L10 is the noise level exceeded 10 per cent of the time; • L50 is the noise level exceeded 50 per cent of the time; and • L90 is the noise level exceeded 90 per cent of the time."
- Why: site-specific data also in the other document (numbers [10.0, 50.0]; species []) (https://www.studocu.com/ph/document/polytechnic-university-of-the-philippines/human-resources-management/eia-report-for-textile-processing-cluster-project-eia-tp-2020/166816780)

**ct-047 RED** (contradiction, pages [291, 337])
- p.291: "The annual rainfall ranges from 3000 to 3500 Cm"
- p.337: "heavy annual rainfall of 300 to 350 Cm spreading over 9 months"
- Why: Both statements refer to annual rainfall on Great Nicobar Island but give values differing by a factor of ten (3000–3500 cm vs 300–350 cm) with no explanation in the provided pages.

**rf-001 RED** (recycled_figure, pages [258, 287])
- p.258: "20 locations within study area from the proposed development area were selected for soil sampling."
- p.287: "The noise monitoring has been conducted for determination of noise levels at 20 locations in the study area for winter season (1st December 2020 to 28th February 2021)."
- Why: Soil sampling and noise monitoring each report 20 locations in the study area, but the subjects are different and the report does not explain why the same number appears for both.

**ct-008 ORANGE** (contradiction, pages [292, 331])
- p.331: "They are not found in Andaman Islands or in other IBAs."
- p.292: "Kailash Chandra (1999) states that the interesting and endemic species of higher animals of Great Nicobar Biosphere Reserve include the Nicobar crab-eating monkey, Nicobar fruit-bat, Nicobar flying fox, Nicobar tree-shrew among mammals; and Nicobar serpent eagle, South Nicobar-Megapode, Nicobar quill, Nicobar pigeon, Nicobar cuckoo-dove, Nicobar parakeet, white bellied swiftlet, Nicobar kingfisher, Nicobar myna, Nicobar sun-bird etc. among the birds. The other interesting fauna belonging to amphibians and reptiles are - Nicobar tree frog, Nicobar toad. Nicobarese tree skink, water monitor lizard, Daniel's forest lizard, worm lizard, Nicobar water snake, reticulated python, leather - back sea turtle, green sea turtle, Hawk's bill turtle, Olive Ridley turtle, south east Asian box turtle, estuarine crocodile ete. Among the invertebrates. Coconut crab and endemic insects including butterflies are also found in Great Nicobar Island."
- Why: The statements cite different sources (1999 vs 2010) and different geographic scopes (Great Nicobar Biosphere Reserve vs. Nicobar Islands), so any inconsistency is ambiguous.

**ct-010 ORANGE** (contradiction, pages [292, 332])
- p.332: "This macaque is found in Great Nicobar, Little Nicobar and Katchal islands of the Nicobar group. It is not found in Andaman Islands."
- p.292: "Kailash Chandra (1999) states that the interesting and endemic species of higher animals of Great Nicobar Biosphere Reserve include the Nicobar crab-eating monkey, Nicobar fruit-bat, Nicobar flying fox, Nicobar tree-shrew among mammals; and Nicobar serpent eagle, South Nicobar-Megapode, Nicobar quill, Nicobar pigeon, Nicobar cuckoo-dove, Nicobar parakeet, white bellied swiftlet, Nicobar kingfisher, Nicobar myna, Nicobar sun-bird etc. among the birds. The other interesting fauna belonging to amphibians and reptiles are - Nicobar tree frog, Nicobar toad. Nicobarese tree skink, water monitor lizard, Daniel's forest lizard, worm lizard, Nicobar water snake, reticulated python, leather - back sea turtle, green sea turtle, Hawk's bill turtle, Olive Ridley turtle, south east Asian box turtle, estuarine crocodile ete. Among the invertebrates. Coconut crab and endemic insects including butterflies are also found in Great Nicobar Island."
- Why: Statement 1 describes the macaque's distribution across three Nicobar islands, while Statement 2 lists it as an endemic species of the Great Nicobar Biosphere Reserve, which appears to cover only Great Nicobar Island. The scopes differ (entire Nicobar group vs. a single reserve) and the sources differ (current survey vs. Kailash Chandra 1999), but the report does not clarify whether 'endemic to the Biosphere Reserve' implies exclusivity.

**ct-215 ORANGE** (contradiction, pages [292, 315])
- p.292: "About 600 plant species of different groups are known from the biosphere reserve"
- p.315: "As many as 640 species of higher plants belonging to 422 genera and 142 families have been reported from the Island."
- Why: Statement 1 cites ~600 plant species of all groups in the biosphere reserve; Statement 2 cites 640 higher-plant species on the whole island. The geographic and taxonomic scopes differ (reserve vs. island; all groups vs. higher plants only), but the report does not clarify the relationship between these figures on the given pages.
