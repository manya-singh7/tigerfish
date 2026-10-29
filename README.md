# TigerFish

*Built for murky water.* A second reader for environmental impact reports, and everyone who
questions them. An accuracy checker for Indian Environmental Impact
Assessment (EIA) reports: internal contradictions, implausible species, copied site data,
each with the page, the exact quote and the evidence, so a reviewer can verify it.

Run the app (replay mode, no keys needed): `streamlit run app.py`

## Tavily features used

Every Tavily response is cached in `cache/tavily/` (a re-run costs no credits) and each run
has a credit cap. Every request carries `project_id="tigerfish"`.

| Feature | Where | What it does for the check |
|---|---|---|
| Search + extract | every web-backed check | sources and their full text; quotes are verified against the extracted text |
| `exact_match=True` | copy-paste check | only pages containing the quoted phrase verbatim |
| `include_domains` | official-only searches; species photos | restrict to official sites, or to `commons.wikimedia.org` |
| `include_domains_mode="prefer"` | knowable at the time, accreditation, WPA schedule | official and scientific sites first in one search, instead of an official search followed by an open-web fallback (cached older runs replay unchanged) |
| `end_date` | knowable at the time | sources published before the report date (2021-12-27 for the Great Nicobar draft); a source is kept only if its own publish date is earlier and its quote states the point |
| `topic="news"` + `start_date` | Public record tab | "What happened next" for each verified finding |
| Research (structured output) | Public record tab | one call for the project's clearance timeline as `{date, event, source, quote}`, limited to official sites; each event's quote is checked against the extracted source text and unverified events are dropped |
| `include_images` | species cards | Wikimedia Commons photos; only free licences (checked on the Commons file page), shown with licence and author |
| `language` + `filter_by_language` | Public record tab | Hindi and Tamil coverage of the public hearing |
| `extract_depth="advanced"` | accreditation; timeline sources | official PDF tables (NABET lists) and pages basic extraction cannot read |

Credits per report are shown on the Cost card and in the "Evidence from the web" tab.

## Accessibility

The draft objection letter can be machine-translated into Hindi, and into Tamil for Tamil
Nadu reports. Quotes, page numbers and links are never translated, and the letter starts with
"Machine-translated; please review."

MIT licence.
