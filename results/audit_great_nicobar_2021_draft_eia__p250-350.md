# Audit run: great_nicobar_2021_draft_eia.pdf, pages 250-350

Pages audited 94, claims 1387, candidate pairs 280, triage {'yes': 85, 'no': 195, 'unsure': 0}, Ultra verdicts 85 (failed 0), copy-paste passages 100.

**Cost $0.8475** (INR 71), **wall clock 3.6 min** with 6 workers. Cap $0.85. Stopped: no.

| Stage | Seconds | USD |
|---|---:|---:|
| claims | 63.9 | 0.0926 |
| triage + verdicts | 109.4 | 0.6307 |
| copy-paste | 7.8 | 0.0033 |

| Model | API calls | Cache hits | Tokens in | Tokens out | USD | API seconds |
|---|---:|---:|---:|---:|---:|---:|
| Nemotron-3_5-Lightning | 19 | 204 | 76,709 | 1,942 | 0.0051 | 27 |
| Nemotron-3.5-Super-VL | 14 | 96 | 99,568 | 69,685 | 0.0926 | 231 |
| Nemotron-3-Ultra-550b-a55b | 104 | 0 | 272,013 | 159,276 | 0.7498 | 699 |
| Tavily | 0 | 157 | | | 0 credits | |

Retries: {'retries': 0, 'rate_limited': 0, 'server_errors': 0, 'connection_errors': 0}

Findings by check and grade:

- contradiction: {'RED': 2, 'ORANGE': 0, 'NONE': 83}
- copy_paste: {'NONE': 100}

Known issues matched: none

## All 2 new RED/ORANGE flags

**ct-037 RED** (contradiction, pages [291, 337])
- p.291: "The annual rainfall ranges from 3000 to 3500 Cm"
- p.337: "heavy annual rainfall of 300 to 350 Cm spreading over 9 months"
- Why: Both statements refer to annual rainfall on Great Nicobar Island but give values differing by a factor of ten (3000–3500 cm vs 300–350 cm) with no explanation in the text.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

**ct-105 RED** (contradiction, pages [285, 286])
- p.285: "The chlorides and sulphates were found to be in the range of 18 to 16300 mg/l"
- p.286: "The chlorides and sulphates were found to be in the range of 18 to 16,300 mg/l and 4.8 to 2150 mg/l respectively"
- Why: Statement 1 gives a single range for both chlorides and sulphates, while Statement 2 gives separate ranges for each parameter.
- Ultra's answers: {'same_subject': True, 'same_place': True, 'same_scope': True, 'incompatible': True, 'explained': False}

## Triage audit

19 of 195 triage-dropped pairs (random sample) sent to Ultra: {'RED': 0, 'ORANGE': 0, 'NONE': 19}
