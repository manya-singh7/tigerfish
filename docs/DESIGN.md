# TigerFish design

Read this before any UI task. `scripts/check_design.py` enforces the rules marked **(checked)**.

## Who it is for

First, someone meeting TigerFish for a few minutes (a hackathon judge, a journalist, a
reviewer): they should understand what it does, see one real finding with its evidence, and
see what the models did, without reading instructions. Then the person who uses it: someone
preparing an objection, who needs the page, the quote, a way to confirm it and a letter.

Every page answers, in order: what is this, what did it find, how do I check it, what do I do
next.

## Mood

A simplified field notebook: paper, ink, evidence. A plain paper page, serif headings, one
accent (teal), and colour only where it means something (the grades). Nothing glows, nothing
sparkles; every mark on the page is there because someone could check it.

## Layout

- One reading column, at most 1200px wide, with padding that shrinks with the screen. No
  horizontal scroll at 390px; no half-empty screen at 1920px **(checked)**.
- Sections are separated by space and hairlines, not boxes. No panel-in-a-box stacks.
- The evidence slip is the one card (below). Report rows and Home's finding cards are its
  smaller relatives: paper, a 1px hairline, no shadow.
- Filters sit in a row above what they filter, never in a side panel.

## Pages

- **Home**: the tagline as a small line, the purpose line as the headline, one paragraph on
  what TigerFish does, two actions (see the Great Nicobar audit, upload an EIA) and the live
  totals in one line. Then three findings a person checked, each a card that opens its
  report; what each Nemotron model did on the showcase audit, with the counts from the saved
  run; the fully audited reports as rows; a link to the whole library. Home does not repeat
  the library's filters.
- **Library**: the totals and Upload in one line; search and the audit type in one row,
  state, sector, year and the two checkboxes in a second; the count and the active filters;
  then two groups (Full audits, Quick checks), one row per report: name, facts, flags by
  grade, Open report.
- **Report**: one header (the report's name as the page title, its source, its flags by
  grade), then five tabs: Overview, Findings, Ask & investigate, Take action, Method &
  quality. A quick check gets Overview, Findings and Batch screening.
  - Overview opens with the report's lead finding ("Start here", from `lead_finding` in
    `results/library.json`), then the other findings a person checked, and one sentence of
    totals.
  - Findings holds the finding sections (Contradictions, Species & nature, Copied text,
    Promises & timeline, Public record) behind one selector with counts. Inside a section:
    what the check does in one line, the filters in a row, the slips 10 at a time.
  - Take action starts from the findings the team checked (a switch turns them off) and
    shows the letter on the page before the downloads.
- **Upload**: the drop zone first, then the key field, then what runs at each level.
- **How it works**: the diagram beside the method, what each model did (with counts), the
  models and tools, the three levels.
- **Limitations**: the known limits, then the failure cases from our own runs.

## Palette

Sampled from `assets/tigerfish_icon_source.png`: tile teal `#0D4242`, fish cream `#F5EEDF`.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--tf-page` | `#F6F2E9` | `#0F1716` | the page and the top bar |
| `--tf-paper` | `#FFFDF8` | `#16201F` | cards: slips, report rows on hover, inputs |
| `--tf-paper-2` | `#EFE9DC` | `#1C2827` | quiet fills: page crops' mat, table heads |
| `--tf-ink` | `#17302F` | `#ECE5D6` | body text, headings |
| `--tf-teal` | `#0D4242` | `#8CC7BE` | links, primary actions, the tagline |
| `--tf-muted` | `#59625F` | `#A7AFAB` | meta lines, captions |
| `--tf-rule` | `#DDD5C4` | `#33403E` | 1px hairlines |
| `--tf-red` | `#9E2A1F` | `#F08F84` | RED grade only |
| `--tf-orange` | `#8F4A06` | `#E5A35C` | ORANGE grade only |
| `--tf-grey` | `#59625F` | `#A7AFAB` | GREY grade (INFO leads, not enough data) |

- Never pure `#FFFFFF` for the page **(checked)**.
- Colour is reserved for meaning: RED, ORANGE, GREY grades. Everything else is ink, teal and
  paper. No gradients **(checked)**, no glows, no purple, no neon, no rainbow accents.
- All text meets WCAG AA (4.5:1) in light and dark.

## Type

| Role | Face | Weights |
|---|---|---|
| Headings, the "TigerFish" wordmark | Newsreader (optical sizes) | 500 to 600, sentence case |
| UI text, buttons, labels, body | Schibsted Grotesk | 400, 500, 600 |
| Quotes from the reports (inside slips) | Newsreader italic, one step above body | 400 |
| Numbers, page refs (p.737), flag IDs, costs, model names | IBM Plex Mono, tabular figures | 400, 500 |
| Hindi, Tamil, Kannada in the app | Noto Sans Devanagari, Tamil, Kannada | 400 to 600 |

Fonts are self-hosted in `static/fonts/` and declared as `[[theme.fontFaces]]` in
`.streamlit/config.toml`. Only these families plus system fallbacks may appear **(checked)**.
Sizes: 2.5rem (page headline), 1.5rem (section heading), 1.125rem (sub-heading, quotes), 1rem
(body), 0.8125rem (meta, captions). No all-caps headings **(checked)**; a grade stamp may be
capitals because the grade is a code.

## The evidence slip

The one card (`tigerfish/ui/slip.py`): a crop of the real report page with the quote
highlighted, the grade stamp, the check, the page, the title, the quote, the reason, and who
checked it. Crop and text side by side on desktop, stacked on a phone. A lead slip (the
Overview's "Start here") shows both pages side by side and the whole reason.

- Hairline 1px borders. No drop shadows (at most a 2px blur) **(checked)**.
- No coloured left or top accent bars **(checked)**. A grade is a small stamp, not a stripe.
- "Verified by a person" (hand check against the PDF) and "Confirmed by a reviewer" (the
  review queue) are kept apart and each shown once.

## Brand lines

- Tagline, Newsreader italic, small, above Home's headline: **Built for murky water.**
- Purpose line, Home's headline: **A second reader for environmental impact reports, and
  everyone who questions them.** It is also the meta description **(checked)**.
- Browser title: "TigerFish: built for murky water" **(checked)**.

## Copy

- No em dashes in UI text **(checked)**. Use a colon, a comma or a new sentence.
- No emojis as icons or bullets **(checked)**, no sparkles, no stat-banner rows, no badge above
  the headline, no fake testimonials, no placeholder names or numbers **(checked)**.
- Plain headings that say what is there ("Full audits", "Quick checks"), not marketing
  ("Deep Investigation Audits (4 Benchmark Reports)").
- Every number is computed from `results/` at render time. If a number has no source, it
  does not ship.
- A flag is a lead to verify, not a verdict. Say so where flags are counted.

## States

Every section has an empty state that says why it is empty, loading tied to real work (a
spinner around the call that is running), and an error state that says what happened and
what to do next. Every button gives visible feedback, and a disabled button keeps a readable
label. Uploads are validated on the server (type, size, page count) with a clear message.

## Nothing gets buried

Every feature is reachable in at most three clicks from Home: the top menu, a report row, a
report tab, a section under Findings. `docs/FEATURES.md` is the inventory;
`check_design.py` fails if a listed feature has no visible entry point **(checked)**.
