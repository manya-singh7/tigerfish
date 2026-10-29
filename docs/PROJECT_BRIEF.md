# TigerFish: project brief (read this before every task)
Tagline: "Built for murky water."
Purpose line: "A second reader for environmental impact reports, and everyone who questions them."
Design rules: docs/DESIGN.md (read it before any UI task). Feature inventory: docs/FEATURES.md.
What: An AI auditor for Indian Environmental Impact Assessment (EIA) reports. It finds
(1) internal contradictions, (2) biogeographically implausible species, (3) copy-pasted
site-specific data. Every flag must include: page number, exact quote, evidence, and a
grade (RED = strong, ORANGE = likely, GREY = not enough data, never shown as a finding).
Neutral accuracy checker, never accusatory language ("inconsistency flagged, verify").

Hackathon: Nebius x NVIDIA Global AI Hackathon. Deadline Oct 30 2026, 10:30pm IST.
Hard rules: all AI calls go through Nebius Token Factory (OpenAI-compatible API) and use
NVIDIA Nemotron models. Public repo, MIT license. Never commit .env or API keys.

Models (Nebius Token Factory, base URL https://api.tokenfactory.nebius.com/v1/):
- nvidia/Nemotron-3-Ultra-550b-a55b : whole-document reasoning, final verdicts
- nvidia/Nemotron-3.5-Super-VL : scanned pages, tables, maps (image input)
- nvidia/Nemotron-3_5-Lightning : fast cheap claim extraction
If a model ID fails, list available models via the API and use the correct ID/region URL.

Other tools: Tavily (search/extract/crawl), GBIF API (species occurrence records),
Nebius Sandboxes (optional, later; local Python fallback is fine).

Stack: Python 3.12 (uv, pyproject.toml), PyMuPDF, openai SDK, tavily-python, requests, Streamlit, python-dotenv.
Rules for the agent: small modules in tigerfish/, tests in tests/, cache every API result
to cache/ (never call the same model on the same input twice), log token usage and cost,
keep code simple and readable, explain what you changed after each task.
