# Full-run estimate (Great Nicobar draft EIA, scoped), from the p.250-350 rehearsal

Measured on 2026-10-27: `scripts/audit.py --pages 250-350 --scope --triage safe --run --max-cost 1.50`,
6 workers. 94 pages audited (50 scanned/table pages on Super-VL, 44 text pages on Lightning),
real cost **$0.80**, wall clock **7.2 min**. Report: `results/audit_great_nicobar_2021_draft_eia__p250-350.md`.

## Unit costs measured in the rehearsal

| Unit | Rehearsal | Old estimate (10 known-issue pages, eval.json) |
|---|---:|---:|
| Scanned/table page (Super-VL) | $0.00543, 7.8 s API | $0.00281, 15.3 s |
| Text page (Lightning) | $0.00023 | $0.00032 |
| Candidate pairs per page | 3.04 | 2.2 |
| Triage pass rate (safe) | **0.31** (88 of 286) | 0.90 |
| Triage per candidate | $0.000072 | $0.000066 |
| Ultra verdict | $0.0056, 4.1 s API | $0.0051, 3.0 s |
| Speed-up from 6 workers | claims 5.6x, verdicts ~4x | (sequential) |

## Full scoped report: 1,114 pages (566 scanned/table, 548 text)

Claim extraction is about **$3.20** and **~31 min** in every case. Most of the uncertainty is
in the Ultra verdicts: how fast candidate pairs grow across the whole report, and whether
triage drops ~70% of them (rehearsal) or ~10% (known-issue pages).

| Scenario | Candidates | Ultra verdicts | Cost | Wall clock (6 workers) |
|---|---:|---:|---:|---:|
| **Likely**: linear growth, rehearsal pass rate 0.31 | 3,400 | 1,050 | **$9.30** | **~1 h** |
| Superlinear growth (exponent 1.32), pass rate 0.31 | 7,500 | 2,300 | $16.60 | ~1.4 h |
| Linear growth, old pass rate 0.90 | 3,400 | 3,050 | $20.50 | ~1.4 h |
| Worst: superlinear, pass rate 0.90 | 7,500 | 6,700 | $41.50 | ~2.4 h |

The growth exponent 1.32 comes from candidate counts on the first 24 and all 94 rehearsal pages
(47 -> 286). Between 47 and 94 pages the growth was nearly flat, so this exponent is a cautious upper bound.
Copy-paste (top 100 passages, Tavily, still sequential): ~3-6 min, about 200 credits.

**Recommendation:** run with `--max-cost 18`. That covers the likely and superlinear cases and
stays well inside the ~$29.50 balance. The worst case would stop at the cap rather than overspend,
and a re-run with a higher cap resumes from the cache.
