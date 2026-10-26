# Full-run estimate (Great Nicobar draft EIA, scoped)

## Update, 2026-10-27: keyed pairing (tigerfish/pairing.py)

The first full run (`--max-cost 18`) finished claim extraction (1,114 pages, 10,297 claims,
$1.96, 15.6 min) and then found **67,689 candidate pairs** (second estimate: ~$509 of Ultra
verdicts). Repeated header figures ("Power plant capacity 450 MVA" on hundreds of pages) were
paired against every other figure with a similar subject. The run was stopped during triage
(system memory), after about $2.9 in total.

Numeric pairs now come from a LIGHTNING subject key per distinct subject ("flora species count"
| "galathea national park"; 101 cached calls, $0.06), with repeats collapsed to one claim per
distinct value ("also on pp. ..."), monitoring readings paired only at the same station, and at
most 8 pairs per subject group. The Ultra verdict prompt is unchanged (frozen).

| Set | Pairs before | Pairs after | Checks |
|---|---:|---:|---|
| 10 known-issue pages | 21 | 11 | gn-001 ORANGE, gn-003/004/005 RED, control not flagged (unchanged) |
| Planted test | 75 | 23 | 10/10 caught, 0/5 explained flagged (unchanged) |
| Rehearsal p.250-350 | 280 | 9 | rainfall p.291 vs p.337 RED kept; chloride p.285/286 false alarm gone; $0.03 |
| Full scoped report (cached claims) | 67,689 | 1,799 | 13 recycled, 178 statement, 1,608 numeric; 910 dropped by the per-group cap |

Full run from the cached claims (claims free; triage ~$0.13; Ultra $0.0084 per verdict with
2,000 output tokens assumed, $0.0056 measured in the rehearsal):

| Triage pass rate | Ultra verdicts | Total | Wall clock (6 workers) |
|---|---:|---:|---:|
| 0.33 (rehearsal, 3 of 9) | ~600 | **~$5.1** | ~20 min |
| 0.5 | ~900 | ~$7.6 | ~25 min |
| 1.0 (worst case) | 1,792 | ~$15.2 (~$10.2 at the measured verdict cost) | ~40 min |

Plus copy-paste: top 100 passages, about 200 Tavily credits. Recommendation: `--max-cost 12`
as a hard cap (verdict order: recycled, statements, numeric with the most alike subjects first).

## Earlier estimate (before keyed pairing), from the p.250-350 rehearsal

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
