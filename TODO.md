# TigerFish: reminders by block

Agent: at the start of every block, read this file and remind the user of the items for that block.

## Waiting on (check daily)
- [x] Hackathon credits promo code (form sent Oct 24, ~10:40pm IST): ARRIVED (Oct 27)
- [x] Builders Program email ($25 Token Factory, $25 Tavily, $100 LangSmith, $100 Toloka): ARRIVED (Oct 27)
- Balance as of Oct 27: Token Factory ~$29.50, Tavily ~4,000 credits
- [ ] Replies: Discord #devpost-global-ai-hackathon, sujee@nebius.com, support@devpost.com, Token Factory "Contact us" ticket, Devpost forum
- [ ] When a Token Factory promo code arrives: Billing > Top up > With promo code
- [ ] When a Tavily promo code arrives: Tavily dashboard > Billing
- [ ] Before the trial ends: check whether promo credits need paid usage turned on; set a spending limit/alert first

## Before any commit
- [x] .gitignore has: .env, cache/, logs/, .venv/, __pycache__/, data/eias/*.pdf
- [ ] Run `git status` and make sure no PDFs, .env, cache or logs are staged

## Manual verification (you + teammate, by hand, not AI)
- [ ] gn-001: read all of p.392 (scope of "bay portion" vs "eastern flank") and p.978 (which form is it?)
- [ ] gn-001: ZSI coral pages p.937-1079 (search 116 / hectare / reef / Galathea)
- [ ] gn-002: p.444 vs p.751: is restoring more than you lose normal practice? If yes, delete gn-002
- [ ] gn-003: confirm p.818 / 851 / 1168 breakdowns really are identical
- [ ] Add verified_by, verified_on, verification_note to each entry
- [ ] rf-001 / gn-005: compare the flora figures on p.818 (Campbell Bay NP) vs p.851 (Galathea NP): 648 species, 422 genera, 142 families, 48 endemic, 85 rare on both. If confirmed, change status to verified.
- [ ] ct-005: p.444 (total reclaimed land 194 ha) vs p.751 (71 ha for the airport): likely part-vs-total; Ultra now grades NONE. Confirm the 71 ha is a component of the 194 ha.
- [ ] Table 3.16 status: Macaca fascicularis listed VU in the report, IUCN now EN (GBIF https://www.gbif.org/species/2436603). Confirm on the IUCN Red List and note the assessment year.
- [ ] Table 3.16 taxonomy: Pteropus giganteus. GBIF (and GBIF's IUCN data) map it to P. vampyrus (EN); the Indian flying fox is usually P. medius (LC). Decide which name the report means before using any status for it.
- [ ] gn-002 (under_review): p.751, whose budget is the 4 ha of coral restoration? Ultra says it covers the entire project (Port, Power plant, Township), not just the airport. If so, delete gn-002.

- [ ] Species table p.954: Panulirus interruptus, RED at Campbell Bay: GBIF 0 within 100 km, 0 within 500 km, 0 in the A&N Islands, 0 within 3,000 km, 294,577 worldwide. Is it really recorded at Great Nicobar?
- [ ] Species tables, flora (not in the app): Musa sabuana p.310, Phalaenopsis speciosa p.317, Phalaenopsis speciosa p.1030: each has only 1 GBIF record worldwide; likely data gaps (Phalaenopsis speciosa is native to the islands). Check against the Flora of Andaman & Nicobar.

- [ ] ToR promises (ORANGE, check by hand against data/eias/great_nicobar_tor_2021.pdf and the draft EIA):
  - [ ] pr-06: ToR p.1 baseline "3 months" (flora & fauna listed) vs p.292 "Quick primary survey" 14-22 Dec 2020 (9 days) + turtle survey 12-18 Feb 2021. Does any other page show a longer ecology survey?
  - [ ] pr-08: ToR p.2 corals "up to a depth of about 40 m" vs p.987 transects "deeper reef-16-30m". Check the ZSI coral pages for any dive deeper than 30 m.
  - [ ] pr-13: ToR p.3 water "20 locations" vs p.279 "sixteen locations" (8 surface + 8 ground water). Check Table 3.18 / Figure 3.34.
  - [ ] pr-15: ToR p.3 soil "three different levels up to a depth of 90 cm" vs p.258 "three different depths viz. 30 cm" and "up to a depth of 30 cm"; but p.870 (annexure) says "30 cm, 60 cm and 90 cm". Also p.258 says "20 locations" and "A total of 10 numbers of samples". Which is right?
  - [ ] Compare against the ToR actually granted (MoEFCC letter of 25 May 2021, cited on EIA p.44); our file is the proposed ToR.

## Block B (PDF reader + Super-VL)
- [ ] Demo: Super-VL reads the table image -> species list -> species check. This is the headline demo shot.

## Block D (species check, GBIF)
- [x] Test case: data/demo/indira_point_table_3_16_mammals.png (Table 3.16 of the WAPCOS Indira Point REIA, Apr 2026, as published by Scroll.in Aug 31 2026). Location: Indira Point 6.75 N, 93.83 E.
  - Assert only: Macaca fascicularis and Tupaia nicobarica must NOT be flagged (real Nicobar species).
  - All others are report-only (GREY is acceptable, it's the safe outcome).
  - [x] Handle old synonyms (Cervus unicolor -> Rusa unicolor) and typos ("Taupaia") via GBIF match; report the corrected name.
- [x] Add the source line to data/eias/SOURCES.md.
- [ ] Check GBIF synonym mappings by hand: Pteropus giganteus -> Pteropus vampyrus looks wrong (Indian flying fox is usually P. medius)
- [ ] Regional-effort fallback is borderline here: 513 mammal records within 500 km vs threshold 500

## What's next / stretch
- [x] ToR vs EIA check: compare promises in data/eias/great_nicobar_tor_2021.pdf (3-month baseline, corals to 40 m, 20 water/noise sites) with what the EIA delivered (tigerfish/promises.py, scripts/check_promises.py, "ToR promises" tab).

## Block E (copy-paste check, Tavily)
- [x] Use the "Deep Research Agent with Tavily + Token Factory" cookbook (github.com/nebius/token-factory-cookbook) as the reference pattern

## Block F (Streamlit UI)
- [ ] Optional: LangSmith free plan (smith.langchain.com), add LANGSMITH_API_KEY to .env, wrap calls in llm.py (~30 min)
- [ ] Take one clean trace screenshot for README/video
- [x] Replay mode opens by default (saved Great Nicobar results), so judges spend zero tokens
- [ ] Host free on Streamlit Community Cloud or Hugging Face Spaces (not paid Nebius compute)

## Block G (evaluation)
- [x] Use the "Agentic Cost Benchmark" cookbook to report cost, tokens and time per audit ("Full 1,213-page EIA audit: Rs X, Y min")
- [x] gn-001 counts as caught if graded RED or ORANGE
- [x] Parallel calls (6 workers, retries, resumable) + rehearsal on p.250-350: $0.80, 7.2 min (results/audit_great_nicobar_2021_draft_eia__p250-350.md, results/full_run_estimate.md)
- [ ] Review the 8 rehearsal RED/ORANGE flags by hand (rainfall p.291 vs p.337 looks real; the copy-paste noise-meter boilerplate and "20 locations" look like false alarms)
- [ ] Before the full run: raise Super-VL VISION_MAX_TOKENS (p.307, p.330 lost to max_tokens); p.279 gave zero claims
- [ ] Full run: `scripts/audit.py ... --scope --triage safe --run --max-cost 18` (not run yet)

## Write-up (Oct 29)
- [ ] "What's next": route uncertain ORANGE flags to human experts via Toloka
- [ ] Feedback section (for the vibes)
- [ ] Great Nicobar EIA consultant is Vimta Labs; Indira Point REIA is WAPCOS. Never describe them as the same consultant.
- [ ] Submit by Oct 29 evening (hard deadline Oct 30, 10:30pm IST)

## Drop if behind on Oct 28
- LangSmith, then batch audit size (go to 5 EIAs instead of 10)