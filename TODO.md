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
