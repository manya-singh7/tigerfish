# TigerFish: reminders by block

Agent: at the start of every block, read this file and remind the user of the items for that block.

## Waiting on (check daily)
- [ ] Hackathon credits promo code (form sent Oct 24, ~10:40pm IST)
- [ ] Builders Program email ($25 Token Factory, $25 Tavily, $100 LangSmith, $100 Toloka)
- [ ] Replies: Discord #devpost-global-ai-hackathon, sujee@nebius.com, support@devpost.com, Token Factory "Contact us" ticket, Devpost forum
- [ ] When a Token Factory promo code arrives: Billing > Top up > With promo code
- [ ] When a Tavily promo code arrives: Tavily dashboard > Billing
- [ ] Before the trial ends: check whether promo credits need paid usage turned on; set a spending limit/alert first

## Before any commit
- [ ] .gitignore has: .env, cache/, logs/, .venv/, __pycache__/, data/eias/*.pdf
- [ ] Run `git status` and make sure no PDFs, .env, cache or logs are staged

## Manual verification (you + teammate, by hand, not AI)
- [ ] gn-001: read all of p.392 (scope of "bay portion" vs "eastern flank") and p.978 (which form is it?)
- [ ] gn-001: ZSI coral pages p.937-1079 (search 116 / hectare / reef / Galathea)
- [ ] gn-002: p.444 vs p.751: is restoring more than you lose normal practice? If yes, delete gn-002
- [ ] gn-003: confirm p.818 / 851 / 1168 breakdowns really are identical
- [ ] Add verified_by, verified_on, verification_note to each entry

## Block B (PDF reader + Super-VL)
- [ ] Demo: Super-VL reads the table image -> species list -> species check. This is the headline demo shot.

## Block D (species check, GBIF)
- [ ] Test case: data/demo/indira_point_table_3_16_mammals.png (Table 3.16 of the WAPCOS Indira Point REIA, Apr 2026, as published by Scroll.in Aug 31 2026). Location: Indira Point 6.75 N, 93.83 E.
  - Assert only: Macaca fascicularis and Tupaia nicobarica must NOT be flagged (real Nicobar species).
  - All others are report-only (GREY is acceptable, it's the safe outcome).
  - Handle old synonyms (Cervus unicolor -> Rusa unicolor) and typos ("Taupaia") via GBIF match; report the corrected name.
- [ ] Add the source line to data/eias/SOURCES.md.
- [ ] Check GBIF synonym mappings by hand: Pteropus giganteus -> Pteropus vampyrus looks wrong (Indian flying fox is usually P. medius)
- [ ] Regional-effort fallback is borderline here: 513 mammal records within 500 km vs threshold 500

## What's next / stretch
- [ ] ToR vs EIA check: compare promises in data/eias/great_nicobar_tor_2021.pdf (3-month baseline, corals to 40 m, 20 water/noise sites) with what the EIA delivered.

## Block E (copy-paste check, Tavily)
- [ ] Use the "Deep Research Agent with Tavily + Token Factory" cookbook (github.com/nebius/token-factory-cookbook) as the reference pattern

## Block F (Streamlit UI)
- [ ] Optional: LangSmith free plan (smith.langchain.com), add LANGSMITH_API_KEY to .env, wrap calls in llm.py (~30 min)
- [ ] Take one clean trace screenshot for README/video
- [ ] Replay mode opens by default (saved Great Nicobar results), so judges spend zero tokens
- [ ] Host free on Streamlit Community Cloud or Hugging Face Spaces (not paid Nebius compute)

## Block G (evaluation)
- [ ] Use the "Agentic Cost Benchmark" cookbook to report cost, tokens and time per audit ("Full 1,213-page EIA audit: Rs X, Y min")
- [ ] gn-001 counts as caught if graded RED or ORANGE

## Write-up (Oct 29)
- [ ] "What's next": route uncertain ORANGE flags to human experts via Toloka
- [ ] Feedback section (for the vibes)
- [ ] Submit by Oct 29 evening (hard deadline Oct 30, 10:30pm IST)

## Drop if behind on Oct 28
- LangSmith, then batch audit size (go to 5 EIAs instead of 10)