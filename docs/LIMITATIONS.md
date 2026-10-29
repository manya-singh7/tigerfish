# TigerFish: known limitations and failure cases

**Every flag is a lead for human review, not a verdict.** TigerFish says that two statements
in a report do not agree with each other or with a public record, and shows the page, the
exact quote and the evidence. It does not say why, and it does not decide whether a project
complies with its approval. A person has to read the pages.

Each item below gives the evidence from our own runs, with the file it comes from. "Rehearsal"
means the 100-page test run on pages 250-350 of the Great Nicobar draft EIA
(`results/audit_great_nicobar_2021_draft_eia__p250-350.md`). The full 1,213-page run had not
finished when this was written, so its numbers are not here.

## 1. GBIF has few records for the Nicobar Islands

Having no GBIF records of a species near the site does not prove the species is absent. The
Nicobars are poorly surveyed.

- **Evidence.** Indira Point (Table 3.16): 85 mammal records of any species within 100 km
  and 513 within 500 km. The local survey-effort threshold is 500 records, so the check only
  works there through the 500 km fallback, and 513 is barely above 500
  (`results/indira_point_table_3_16.json`, finding sp-01). On the Great Nicobar species
  tables, 391 of 581 names were graded GREY ("too little surveyed to judge") and never shown.
- **Mobile-species rule.** Birds, fish, marine invertebrates, sea turtles, crocodiles, sea
  snakes, marine mammals and plants are flagged only when GBIF has no record of them anywhere
  in the Andaman & Nicobar Islands and none within 3,000 km. On the Great Nicobar tables this
  rule kept 151 names from being flagged (local cache, `species_pages.json`). Land mammals,
  amphibians and land reptiles keep the strict 100 km / 500 km rules.
- **Effect.** The species check misses some real errors (for example a mobile species that
  is recorded somewhere in the region but not at the site). The one Great Nicobar species
  flagged RED, *Panulirus interruptus* (p.954), has 0 records within 3,000 km and 294,577
  worldwide, mostly from North America. It is still a lead: TODO.md asks for a manual check.
- **Taxonomy.** GBIF's synonyms can differ from current usage. It maps *Pteropus giganteus*
  to *P. vampyrus* (EN), while the Indian flying fox is usually *P. medius* (LC). Status
  differences after a name correction are graded GREY.

## 2. False alarms found in the rehearsal, and how each was fixed

The first rehearsal (commit bfb7720) gave **8 RED/ORANGE flags**. Only one of them (rainfall, below) still looks
real; the other 7 and their fixes are in the table. After the fixes below (commit 4f0f98e), the same pages gave 2 flags, and then 1 after
the last fix.

| Flag in the first rehearsal | Why it was wrong | Fix |
|---|---|---|
| cp-p287-1, cp-p287-2 RED: noise meter description "found in another document" | Standard equipment text (model OB-100, 31.5 to 16000 Hz) copied across many EIAs. Not site data | Boilerplate phrase list plus a Lightning yes/no "is this site-specific?" before any copy-paste flag (`tigerfish/copycheck.py`) |
| cp-p288-3 RED: L10 / L50 / L90 noise definitions | Textbook definitions | Same boilerplate filter |
| rf-001 RED: "20 locations" for soil sampling and for noise monitoring | Small counts repeat by chance, and the ToR itself asks for 20 locations | Recycled figures need values above 25 and at least 3 shared figures; counts that come from the ToR are ignored (`TRIVIAL_MAX`, `tor_location_counts`) |
| ct-008, ct-010 ORANGE: "not found in Andaman Islands" vs a list of endemic species on p.292 | Ultra was given a vague subject, and its free-form grade turned "different scope" into ORANGE | Statement pairs must name every key word of the subject X; Ultra answers fixed yes/no questions (same subject, place, scope; incompatible; explained) and code computes the grade |
| ct-215 ORANGE: about 600 plant species in the reserve vs 640 higher plants on the island | Different scopes (all groups vs higher plants, reserve vs island) | Same structured verdict: "unclear" only with a concrete, named reason |
| ct-105 RED (second rehearsal): chlorides and sulphates "18 to 16300 mg/l" (p.285) vs "18 to 16,300 mg/l and 4.8 to 2150 mg/l respectively" (p.286) | Ultra saw a sentence fragment; the full sentence on p.285 is the same statement | Ultra now gets the complete sentence(s) around each quote; ct-105 is NONE |

Other changes from the same work: Super-VL replies cut off on long tables (p.307, p.330) are
re-asked with a larger budget and partial JSON is salvaged; numbers written as words
("sixteen locations") are read.

**Still open.** ct-037, rainfall "3000 to 3500 Cm" (p.291) vs "300 to 350 Cm" (p.337). It looks
real (probably mm vs cm) but has not been checked by hand. The saved rehearsal report still
lists ct-105 as RED because it was written before the last fix.

The Ultra verdict prompt was frozen on Oct 27 so the evaluation numbers stay comparable.
Fixing false alarms on the pages we tested could have tuned TigerFish to those pages; the
planted-error test below is the guard against that.

## 3. Ultra's page citations drift on very long inputs

When Nemotron Ultra reads the whole report in one call, it often cites a page next to the
right one.

- **Evidence.** Reviewer's memo (`results/memo_great_nicobar_2021_draft.json`): 39 quotes,
  30 found word for word in the report, and **23 of those 30 were on a page 1 to 3 away from
  the page Ultra cited**. The other 9 could not be found close to the cited page and are dropped.
- **Context test** (`results/ultra_context_test.json`): at 191k tokens (371 pages) Ultra
  named the last page correctly. At 545k tokens (1,071 pages) it named **p.1143 as the last
  page; it is p.1173**.
- **What the app does.** Every quote is searched in the page text. A quote found on a page up
  to 3 away is shown with the corrected page and a note ("cited as p.X; the quote is on
  p.Y"). A quote further away, or not found at all, is listed as "did not check out" and is
  not used as evidence. Ultra's reasoning text is shown but labelled "not checked".

## 4. Proposed ToR, not the granted ToR

The ToR promises check compares the EIA with `data/eias/great_nicobar_tor_2021.pdf`, which
is the **proposed** Terms of Reference. The ToR MoEFCC granted (letter of 25 May 2021, cited on
EIA p.44) may differ, and an expert committee can approve changes later. Example: pr-06 (the
ToR asks for 3 months of baseline data; the EIA describes surveys on 14-22 December 2020 and
12-18 February 2021, p.292) is a strong lead only if the granted ToR kept the 3-month
requirement. TODO.md lists the comparison with the granted ToR as manual work.

**Granted ToR, found by the paper trail.** The MoEFCC letter granting the ToR (F.No.
10/17/2021-IA.III, 25 May 2021, proposal IA/AN/NCP/201159/2021, 18 pages) was found on
environmentclearance.nic.in and checked the same way (`results/great_nicobar_2021_draft_promises_granted.json`).
It states few measurable study conditions: the check found 2 (one complete non-monsoon season of
site-specific meteorological and air-quality data; at least one monitoring station upwind and one
downwind), both INFO (not confirmed from the report text searched). Its numbered conditions are
split into separate items and its running page header is removed before the check; quotes stay
verbatim from the letter. The letter's text has no "3 months" / "three months"; it grants
specific conditions "in addition to all standard ToR conditions applicable for such projects",
which are not in the letter and were not checked. So pr-06 rests on the proposed ToR only. Read
the granted letter (and the standard ToR it refers to) by hand before using pr-06.

Other limits of this check: "3 months" for a list of attributes is read as applying to each;
studies without stated dates have no bar on the timeline; regex can miss numbers in tables
split across pages.

## 5. Hindi pages and scanned pages are partly skipped

- **Hindi.** The text layer of the Hindi summary and the Gazette notifications does not extract
  cleanly. 91 pages containing Devanagari were left out of the cost estimate
  (`results/eval.json`), and 77 Hindi pages were skipped when Ultra read the whole report
  (memo and Ask). The Hindi pages are not checked for contradictions with the English text.
- **Scanned pages.** Claim extraction sends scanned and table pages to Super-VL (521 pages
  in the claims ledger, `results/page_readers_great_nicobar_2021_draft.json`), but
  text-only steps cannot search them: the omissions check searched 1,132 of 1,213 pages (81
  scanned pages not searched), and Ultra's whole-report read skipped 65 pages with no text
  layer. Handwritten tables (p.896, p.901) and maps (p.909) are read by Super-VL in the
  inspector; those readings have not been checked cell by cell.

## 6. Part vs total

A smaller figure for a component does not contradict a larger total, but the two look alike
to a number-pairing rule.

- **Evidence.** ct-005 (TODO.md): total reclaimed land 194 ha (p.444) vs 71 ha for the airport
  (p.751). The pairing rule paired them. Ultra now gets an explicit part-vs-total rule for such pairs
  and grades it NONE. gn-002 (coral loss 1-2 ha vs 4 ha restoration, p.444 vs p.751) is also
  graded NONE; Ultra reads the 4 ha as covering the whole project, not just the airport. Both
  are on the manual-check list.
- **Risk.** The rule can now hide a real contradiction where a "component" really is
  larger than the report allows. The negative-control test (island area 1045 vs 910 sq km,
  explained in the text) is not flagged, and 0 of 5 planted explained differences were flagged.

## 7. Thresholds and their effects

Lower thresholds find more and flag more noise; higher ones miss weaker cases. Current values:

| Threshold | Value | Effect of raising it / lowering it |
|---|---|---|
| Numeric difference before a pair is checked | 5% | Higher misses small but real differences; lower sends rounding to Ultra |
| Subject similarity for pairing | 0.75 | Lower pairs unrelated subjects (more Ultra cost, more noise) |
| Quote match (fuzzy repair) | 90% | Lower would accept quotes the model reworded |
| Recycled figure | values > 25, at least 3 shared figures | Lower brings back the "20 locations" false alarm |
| Borrowed text | 20+ consecutive words | Lower flags common phrases |
| GBIF survey effort | 500 class records within 100 km, else 500 within 500 km | Indira Point passes with 513 at 500 km; a little lower would grade those 5 mammals GREY |
| Far range | no records within 3,000 km (and 100+ worldwide) is RED | |
| Ultra calls per contradiction run | 30 candidates | Extra candidates are dropped and logged |
| Accreditation | official record within 12 months of the report date | See item 9 |

## 8. Triage drops most candidate pairs before Ultra sees them

Nemotron Lightning screens candidate pairs ("could these disagree?") so that only some reach
Ultra.

- **Evidence.** Rehearsal: 280 candidate pairs, **85 passed (30%)**, 195 dropped. A random
  sample of 19 dropped pairs was sent to Ultra anyway: all 19 graded NONE. The earlier run used
  in `results/full_run_estimate.md` passed 88 of 286 (31%).
- **But** on the 10 known-issue pages the pass rate was 90% (`results/eval.json`), so the rate
  depends heavily on the pages. A 19-pair sample cannot rule out that triage drops a few real
  contradictions across the whole report. The full-run cost estimate ranges from $9.30
  (31% pass rate) to $41.50 (90%, faster growth of pairs) for the same reason.
- Recycled-figure candidates and the negative control are never triaged.

## 9. Accreditation evidence predates the report

Consultant accreditation (ac-01, Vimta Labs) is compared with the closest official record we
could find: the NABET Accreditation Committee minutes of **26 October 2021**. The report is
dated **December 2021**, about two months later. The minutes state no validity date, so
accreditation status on the report date cannot be confirmed from them. The finding says so
in its evidence. The grade is ORANGE ("could not be confirmed"), not a claim that the
consultant was unaccredited.

## 10. PRS Legislative Research is not a government source

For Wild Life (Protection) Act schedules (st-07, Indira Point), India Code and the Gazette were
searched first; the pages read did not state the number of schedules. The source used is PRS
Legislative Research, labelled in the app as **"authoritative, non-government"**, never as
official. The finding records that the official tier gave nothing.

## 11. Other known limits

- **Hosted app limits.** An upload always gets the free checks on the whole report (up to
  2,000 pages, `MAX_FREE_PAGES` in `tigerfish/ui/upload.py`). The paid model checks run on at
  most 30 pages the visitor picks (`page_picks.MAX_PAGES`; the default pick is the pages with
  the most figures and species names), within caps of $0.50 per upload (`MAX_RUN_USD`) and
  $1.00 per UTC day for all visitors together on the owner's key (`DAILY_BUDGET_USD`, in
  `tigerfish/hosted.py`). A visitor's own key is not counted against the daily cap. The daily
  total is kept in memory and in a temporary file (`tigerfish_daily_spend.json` in the system
  temp folder), so it survives app reruns but resets when the hosted container restarts cold
  and its temp folder is cleared.
- **Self-match rule (Oct 29).** Before grading, a copied-text match is checked against the report's own identity. It is graded GREY "self-match: same report published elsewhere" only if the matched document is one of the report's paper-trail documents, or is hosted on an official, lender or proponent portal (`SELF_MATCH_PORTALS` in `tigerfish/copycheck.py`: gov.in, nic.in, adb.org, worldbank.org, plus the report's own official sites from its paper trail) and names the project or its proposal/project number (`paper_trail.names_project`). It is listed under a collapsed "Excluded matches" list with the URL and never counted as a flag. News coverage and other third-party pages are graded by the normal rules, even when they name the project. Re-graded from cache: Karnataka 10 RED -> 0 (all on ADB's own copy of the EIA), Cuddalore 4 RED -> 1 (3 on TNPCB's executive summary); Great Nicobar unchanged. Self-matches are limited to the report's own paper-trail documents and official/lender portals that name the project; news coverage is graded normally.
- **Cuddalore subject grouping.** Cuddalore's subject-grouping step was run with wording that
  named Great Nicobar Island; this was fixed for later reports. Its claims, verdicts and flags
  were not affected by the wording, only how numbers were grouped into pairs.
- **Coverage of the replay.** The saved Great Nicobar results count 47 of 1,213 pages as read:
  the contradiction and copy-paste checks ran on 10 pages with known issues, and the
  species check on 40 species-table pages (3 overlap). The ToR, accreditation and omission
  checks searched the report text more widely, but only for their own topics. Zero findings on a
  page means it was not checked, not that it is correct.
- **The grade can change between runs.** The saved app finding ct-003 (gn-001, coral at the
  port site, p.392 vs p.978) is RED; the latest evaluation (`results/eval.json`) grades the same
  pair ORANGE. Both count as caught, but a grade is the model's reading, not a measured quantity.
- **Models misread.** Models can misread tables or silently fix spelling. Quotes are checked
  against the page text, and table names keep the spelling the model read.
- **Small evaluation.** 4 of 4 scored known issues, 10 of 10 planted contradictions,
  0 of 5 planted explained differences flagged, 5 of 5 planted out-of-place species, 0 of 5
  real species wrongly flagged (`results/eval.md`). These are small samples from one report.
- **Two reports.** Great Nicobar (Vimta Labs) and the Indira Point Table 3.16 (WAPCOS, as
  published by Scroll.in). Thresholds were set on these and may not transfer to other EIAs.
