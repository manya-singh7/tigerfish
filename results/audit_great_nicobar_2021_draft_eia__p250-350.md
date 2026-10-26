# Audit run: great_nicobar_2021_draft_eia.pdf, pages 250-350

Pairing: {'subjects': 227, 'key_calls': 6, 'keys_missing': 0, 'numeric_claims': 331, 'groups': 154, 'representatives': 165, 'readings_without_station': 62, 'dropped_by_cap': 0, 'pairs_same_key': 3, 'pairs_related_key': 6, 'pairs_part_whole': 0}

Pages audited 94, claims 1424, candidate pairs 9, triage {'yes': 3, 'no': 6, 'unsure': 0}, Ultra verdicts 3 (failed 0), copy-paste passages 100.

**Cost $0.0331** (INR 3), **wall clock 0.6 min** with 6 workers. Cap $1.50. Stopped: no.

| Stage | Seconds | USD |
|---|---:|---:|
| claims | 2.2 | 0.0000 |
| triage + verdicts | 11.9 | 0.0265 |
| copy-paste | 12.6 | 0.0034 |

| Model | API calls | Cache hits | Tokens in | Tokens out | USD | API seconds |
|---|---:|---:|---:|---:|---:|---:|
| Nemotron-3_5-Lightning | 16 | 45 | 77,727 | 10,386 | 0.0072 | 58 |
| Nemotron-3.5-Super-VL | 0 | 111 | 0 | 0 | 0.0000 | 0 |
| Nemotron-3-Ultra-550b-a55b | 3 | 0 | 9,715 | 5,413 | 0.0260 | 24 |
| Tavily | 2 | 156 | | | 2 credits | |

Retries: {'retries': 0, 'rate_limited': 0, 'server_errors': 0, 'connection_errors': 0}

Findings by check and grade:

- contradiction: {'RED': 1, 'ORANGE': 0, 'NONE': 2}
- copy_paste: {'NONE': 99, 'RED': 1}

Known issues matched: none

## All 2 new RED/ORANGE flags

**cp-p327-1 RED** (copy_paste, pages [327])
- p.327: "A total of 10 species of amphibians have been reported from the island including the endemic Nicobar Tree Frog (Polypedatesinsularis), Red eared frog (Hylaranaerythraea), Cricket Frog (Acris gryllus) and the Indian Toad (Duttaphrynusmelanostictus) Avi Fauna of Great Nicobar Island The endemic birds include the Nicobar sparrow hawk, great Nicobar serpent eagle, Nicobar megapode, Nicobar parakeet, Nicobar imperial pigeon, Nicobar scops-owl, Nicobar bulbul, and Nicobar jungle flycatcher, all now threatened by human settlements and resulting habitat modification."
- Why: site-specific data also in the other document (numbers [10.0]; species [])
- Match: RED https://zsi.gov.in/public/PDFVolumes/ess/016/index.pdf

**ct-001 RED** (contradiction, pages [291, 337])
- p.337: "heavy annual rainfall of 300 to 350 Cm spreading over 9 months"
- p.291: "The annual rainfall ranges from 3000 to 3500 Cm"
- Why: The two statements give different numerical ranges for annual rainfall (300–350 cm vs 3000–3500 cm) for the same island, with no explanation in the report for the discrepancy.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}
