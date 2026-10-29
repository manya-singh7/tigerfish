# TigerFish: known limitations and failure cases

**Every flag is a lead for human review, not a verdict.** TigerFish shows statements that
may disagree, their physical PDF pages, exact quotations and supporting evidence. It does
not establish intent, certify a report correct, or decide regulatory compliance.

## Current saved coverage

Snapshot on 30 October 2026; the UI computes its totals from saved files.

| Entry | Recorded coverage | Scope |
|---|---|---|
| Great Nicobar draft EIA, Vimta Labs | 1,114 of 1,213 pages | Scoped full run plus specialized checks |
| Cuddalore Port draft EIA | 768 of 802 pages | Scoped full run plus specialized checks |
| Karnataka Rural Roads EIA, ADB | 356 of 364 pages in replay | Run ledger records 364; check-specific coverage differs |
| Indira Point REIA, WAPCOS | One published table | Species/status checks, not the whole REIA |
| Maharashtra batch | 25 executive summaries, 564 pages | No-model certificate-date/baseline screens; GBIF where readable names exist |

The library has 2,802 PDF pages plus one table, 234 RED/ORANGE cards and 23 standard INFO
leads. Three additional batch baseline INFO leads are stored outside those totals and have
known extraction errors (below). Zero flags does not mean all checks ran or the report is correct.

Great Nicobar's full run recorded 10,463 claims, 1,866 candidates, 1,440 Ultra verdicts,
$15.78 model cost and about 62 minutes (`results/eval.md`). Cuddalore and Karnataka record
$13.34 and $2.40 model-run costs. Separate web-context checks have their own costs.
The older pages 250-350 rehearsal and cost estimates are historical, not current coverage.

## GBIF coverage, taxonomy and geographical scope

- No occurrence records does not prove absence. The Nicobars are poorly surveyed. The
  Indira Point snapshot has 85 mammal records within 100 km and 513 within 500 km; the
  wider fallback only narrowly clears the 500-record threshold.
- The Great Nicobar species-table run graded 391 of 581 names GREY. Birds, marine species
  and plants recorded elsewhere in the archipelago or within 3,000 km are conservatively
  protected from out-of-range flags by the mobile-species rules. This also misses genuine
  site-level discrepancies. The saved run suppressed 151 such flags.
- *Panulirus interruptus*, p.954, has no records within 3,000 km and 294,577 worldwide in
  the saved snapshot. It was checked by hand as likely misidentification (gn-009), not
  established absent by the automated check.
- GBIF maps *Pteropus giganteus* to *P. vampyrus*, while the Indian flying fox is usually
  *P. medius*. Status disagreements after a name correction are GREY because taxa may differ.
- IUCN comparisons use current GBIF data, not necessarily the assessment available when the
  report was written. Only selected findings have dated "knowable at the time" evidence.
- Species-map arcs end at approximate country centres. They show occurrence counts, not
  exact range boundaries; records may include introduced or captive populations.
- Omissions mean a name was not found in searchable material, not proof that an impact
  was unassessed. Common names, synonyms, scans and incomplete source volumes limit recall.

## False alarms and protections developed in the rehearsal

The first 100-page rehearsal produced eight RED/ORANGE flags. Several were false alarms;
fixes included the following (`tigerfish/copycheck.py`, `claims.py`, `contradictions.py`).

| Failure | Protection |
|---|---|
| Noise-meter specifications and L10/L50/L90 definitions matched elsewhere | Boilerplate filter and Lightning site-specific screening |
| "20 locations" repeated in unrelated sampling plans | Recycled figures require values above 25 and at least three shared breakdown figures; ToR counts excluded |
| Vague "not found" claims paired with unrelated species lists | Explicit statement subjects and structured scope/place answers |
| Chloride/sulphate fragments looked inconsistent | Ultra receives complete source sentences and page context |
| Long vision replies were cut off | Larger retry budget, partial-JSON salvage, duplicate filtering |

Rainfall "3000 to 3500 Cm" (p.291) vs "300 to 350 Cm" (p.337) is now ct-239 in the
full replay, checked by hand as gn-008: confirmed, low severity, likely a unit slip.
Rehearsal IDs and older grades should not be substituted for current full-report IDs.

## Long-context quotations are checked, reasoning is not independently verified

The Great Nicobar memo includes 1,071 pages of usable text. Of 39 attempted quotations,
30 verified, and 23 of those needed a page correction of one to three pages. Nine were
dropped (`results/memo_great_nicobar_2021_draft.json`). In the context test Ultra named
**p.1143** as the final page when it was **p.1173** at roughly 545k input tokens.

`fulltext.verify` accepts a nearby match with the page corrected and the original citation
recorded; more distant/unmatched quotations are not evidence. Finding a quotation verifies
its presence, not the model's interpretation. Memo reasoning and unsupported agent reasons
are labelled unverified. An Ask answer with no verified quote becomes "The report does not say."

## Proposed and granted Terms of Reference

Both comparisons are saved and separately labelled in Promises & timeline. pr-06 compares
the **proposed** three-month requirement with a nine-day terrestrial survey and separate
seven-day turtle survey. The air/water/soil baseline did run three months. This lead does
not establish a breach of the granted conditions.

The paper trail found the 18-page **granted** MoEFCC letter of 25 May 2021, F.No.
10/17/2021-IA.III. The saved check found two measurable commitments, both INFO. It contains
no explicit "three months" phrase, but incorporates standard ToR conditions that were not
checked. Read those conditions before relying on pr-06. Sources:
`results/great_nicobar_2021_draft_promises.json` and the `_promises_granted.json` counterpart.

The parser treats a duration over a list as applying to each attribute. Missing dates do
not create a timeline bar. Search, regexes and split-page tables can miss relevant evidence.
An INFO "not found" result is not proof a commitment was unmet.

## Hindi and image-only pages

The whole-report text prompt skipped 77 Hindi pages and 65 pages without usable text;
the older estimate skipped 91 Hindi pages under its different scope. Claim extraction
routed 521 pages to Super-VL in the saved reader ledger, but downstream text searches do
not automatically inherit every vision reading. The omissions run searched 1,132 of 1,213
pages, leaving 81 without searchable text.

Image-only readings have no independent text layer for quotation matching. The scanned-page
inspector labels these unverified and displays the image beside the rows. The handwritten
tables on pp.896/901 and map on p.909 have not been checked cell by cell by a person.

## Part vs total and model judgments

A component smaller than a total is not a contradiction. ct-005 paired 194 ha total
reclamation (p.444) with 71 ha for the airport (p.751); the part-vs-total rule grades it
NONE, but its interpretation remains on the manual-check list. gn-002, coral restoration
of 4 ha for the whole project versus 1-2 ha affected, was checked by hand and is an
explained negative control. Such rules can also hide a real discrepancy if scope is misread.

Grades are computed from structured Ultra answers, not a proposed model grade. RED is not
a calibrated probability. The current coral pair ct-031 and the ten-page evaluation are
both ORANGE; older artifacts graded related claims RED. The verdict prompt is frozen to
preserve the evaluation baseline, not because its judgments are infallible.

## Thresholds and candidate selection

| Rule | Current setting | Limitation |
|---|---|---|
| Numeric difference | More than 5% | Smaller differences can be missed |
| Subject similarity | 0.75 | Loose grouping creates noise; strict grouping misses comparisons |
| Fuzzy quotation repair | 90% | A repaired quote is actual source text, not the model's original wording |
| Recycled figures | Values above 25, at least 3 shared breakdown figures | Small reused counts are ignored |
| Generic borrowed text | 20 consecutive words | Citation detection is page-local and heuristic |
| GBIF effort | 500 class records at 100 km, else 500 at 500 km | Sensitive to sampling and regional geography |
| Distant absence | No records within 3,000 km, at least 100 worldwide | No occurrence record is not proof of absence |
| Default contradiction cap | 30 candidates | Small/deep checks can stop early; full audit explicitly raises this cap |
| Keyed pairing | At most 8 pairs per group | Even full runs are not exhaustive all-pairs comparisons |

**Triage:** the completed Great Nicobar run retained 1,440/1,866 candidates (about 77%):
1,431 yes, 9 unsure, 426 dropped. Safe mode kept all 11 ten-page evaluation candidates.
An earlier sample of 19 dropped pairs all graded NONE, but this does not establish recall
over the report. Safe mode drops a pair only when both Lightning views say no; a single
view has missed real findings during development. Recycled candidates bypass this triage.

Cuddalore's old subject keys used Great Nicobar wording. Later report profiles fix this,
but the old candidate selection may have missed comparisons or created irrelevant ones;
there is no independent rerun establishing that the findings were unaffected.

## Copied text, attribution and self-matches

Self-matches are GREY, never flags: a known paper-trail document, or an official/lender/
proponent portal document naming the project. URLs and reasons remain under Excluded
matches. Cache regrading removed Karnataka's 10 ADB self-matches and three Cuddalore
executive-summary matches. The older Great Nicobar exclusion heuristics still apply;
third-party coverage is not universally recognized as a report's own document.

Remaining text matches are not proof of improper reuse. Cuddalore matches district
fisheries statistics; Great Nicobar taxonomy lists share authority publication years
that the checker counts as numbers. Legitimate secondary data, nomenclature and attribution
need human interpretation. The checker does not establish direction of copying or intent.

## Official records and source dates

Vimta's accreditation lead uses NABET minutes of **26 October 2021**, before the December
2021 report. The minutes have no validity date; ORANGE means accreditation could not be
confirmed for the relevant sector/category, not that the consultant was unaccredited.
WPA evidence from PRS is labelled **authoritative, non-government**, never official.
Later project revisions are not automatically errors in the earlier EIA. Web extraction,
publication-date detection and project matching can miss or misidentify relevant records.

## Batch screening and UI integration gaps

All 25 saved quick checks are Maharashtra executive summaries, not full model audits.
Discovery cost 41 Tavily credits; the subsequent regex/GBIF screens made no model calls.
The snapshot has GREY results for certificate dates in 17 reports, baseline periods in
15, and species data in 23. Certificate-date screening is not official NABET verification.

The baseline parser currently uses nearby dates without establishing a fieldwork interval.
It reads October-December 2025 plus a report number as December-January, treats traffic
counts as a baseline, and pairs application/EAC dates as a study. These cause the three
saved INFO leads in `results/batch/batch_summary.json`; none is a verified shortfall.
Fix and regenerate them before using them as examples. Batch-only evidence lives in
`batch_checks`/`batch_flags` but is not fully exposed in the current quick-report UI.

The library renders 10 cards initially and then Show more. Reset clears filters and
restores 10 cards; the current test instead expects all 29. The behavior contract needs
explicit coverage, including reachability and ordering of every matching report.

## Evaluation, human review and demo scope

`results/eval.md` records 7/7 ten-page known-case checks and 12/12 full-audit checks
(including two negative controls), 10/10 planted contradictions caught, 0/5 explained
differences wrongly flagged, 5/5 planted out-of-place species flagged and 0/5 locally
recorded species wrongly flagged. These are small, development-influenced samples.

Only 10 flags have recorded human judgments, all Great Nicobar and confirmed. This is
too few to estimate general precision. Thresholds were developed mainly on Great Nicobar
and the Indira Point table; more reports do not establish generalization. Software tests
are not human validation of the results.

Home's tigerfish occurrence counts come from a **planted evaluation case**, not a quoted
finding extracted from an audited EIA. The published story is separate motivation. Rich
saved memos/questions and the scanned-page inspector exist mainly for Great Nicobar;
live investigation of saved reports needs local source material and keys.

## Uploads and hosted operation

Free checks use the readable text layer of at most 2,000 pages, with name caps and missing-
input restrictions. Paid deep audits use up to 30 chosen pages. Specialized web checks
need local scripts/keys; ToR comparison also needs the second document. A full audit does
not mean every check ran on every page.

The upload renderer passes its truncated page count to the omission check. Above 2,000
pages this can misrepresent an incomplete search as complete. New Ask questions require
available page text; saved reports on the host do not include a universal full-text store.

Owner-key controls target $0.50/upload and $1/day, three uploads and three Ask questions per
session. They do not reserve the next request's cost: in-flight calls and concurrent sessions
can overshoot. The temporary daily-spend file resets on a cold container restart. Visitor
keys bypass the owner's daily allowance, not the session limits. Visitor reviews stay in
session state; committed team decisions are not overwritten. See `docs/DEPLOY.md`.
