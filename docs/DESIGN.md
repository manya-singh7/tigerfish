# TigerFish design

Read this before any UI task. `scripts/check_design.py` enforces the rules marked **(checked)**.

## Mood

An environmental auditor's field notebook. Murky water, paper, ink, evidence. Nothing glows,
nothing sparkles; every mark on the page is there because someone could check it.

## Core principle

One background personality and one repeated card.

- **The water**: a hand-drawn doodle pattern (fish, reeds, mangrove roots, coral, ripples, a
  survey stake, a magnifier, a loose report page, a stamp) covers the app background
  (`assets/bg_pattern.svg`, drawn in ink at low contrast on the paper colour).
- **The evidence slip**: the one card. Content sits on solid paper surfaces that cover the
  pattern, so the library visibly fills the water as reports are added. Text never sits
  directly on the pattern **(checked)**.

## Palette

Sampled from `assets/tigerfish_icon_source.png`: tile teal `#0D4242`, fish cream `#F5EEDF`.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--tf-page` | `#E9E2D2` | `#0F1716` | app background, under the pattern |
| `--tf-paper` | `#FAF6EC` | `#16201F` | every surface: slips, panels, inputs |
| `--tf-paper-2` | `#F2ECDF` | `#1C2827` | quiet fills: page crops' mat, table heads |
| `--tf-ink` | `#17302F` | `#ECE5D6` | body text |
| `--tf-teal` | `#0D4242` | `#8CC7BE` | headings, links, primary actions |
| `--tf-muted` | `#59625F` | `#A7AFAB` | meta lines, captions |
| `--tf-rule` | `#CFC6B3` | `#33403E` | 1px hairlines |
| `--tf-pattern` | `#0D4242` at 9% | `#ECE5D6` at 7% | the doodles |
| `--tf-red` | `#9E2A1F` | `#F08F84` | RED grade only |
| `--tf-orange` | `#8F4A06` | `#E5A35C` | ORANGE grade only |
| `--tf-grey` | `#59625F` | `#A7AFAB` | GREY grade (INFO leads, not enough data) |

- Never pure `#FFFFFF` for the page **(checked)**.
- Colour is reserved for meaning: RED, ORANGE, GREY grades. Everything else is ink, teal and
  paper. No gradients **(checked)**, no glows, no purple, no neon, no rainbow accents.
- All text meets WCAG AA (4.5:1). On `--tf-paper`, light: ink 13.0, teal 10.4, muted 5.8,
  red 6.9, orange 6.2; dark: ink 13.3, teal 8.7, muted 7.4, red 7.1, orange 7.7. Button
  text on teal: 10.4 (light), 9.6 (dark). Even on the bare page colour every pair stays
  above 4.5 (lowest: muted on the light page, 4.9).

## Type

| Role | Face | Weights |
|---|---|---|
| Headings, the "TigerFish" wordmark | Newsreader (optical sizes) | 500 to 600, sentence case |
| UI text, buttons, labels, body | Schibsted Grotesk | 400, 500, 600 |
| Quotes from the reports (inside slips) | Newsreader italic, one step above body | 400 |
| Numbers, page refs (p.737), flag IDs, costs, coordinates, model names | IBM Plex Mono, tabular figures | 400, 500 |
| Hindi, Tamil, Kannada in the app | Noto Sans Devanagari, Tamil, Kannada | 400 to 600 |

The `.docx` letters keep Nirmala UI. Fonts are self-hosted in `static/fonts/` (Streamlit only
serves a folder named `static/`; `server.enableStaticServing = true`) and declared as
`[[theme.fontFaces]]` in `.streamlit/config.toml`, with `font`, `headingFont` and `codeFont`
naming them. Only these families plus system fallbacks may appear **(checked)**. Streamlit
appends its own Source Sans to the end of every stack as a last resort for a glyph none of
the above has; no element may use it as its font.

Five sizes, no more: 2.5rem (page headline), 1.5rem (section heading), 1.125rem (sub-heading,
quotes), 1rem (body), 0.8125rem (meta, labels, captions). Body line height 1.5, headings 1.15.
No all-caps headings **(checked)**; a grade stamp may be capitals because the grade is a code.

## The evidence slip

The signature layout primitive (`tigerfish/ui/slip.py`), reused on Home, in every flag list
and in the library's report previews:

```
+--------------------------------------------------------------+
| [page crop, quote highlighted]  | RED  Contradiction   p.737 |
|                                 | Title of the finding         |
|                                 | "Quote from the report, in   |
|                                 |  Newsreader italic."         |
|                                 | One-line reason.             |
|                                 | Verified by a person, 27 Oct |
+--------------------------------------------------------------+
```

- A cropped image of the real report page with the quote highlighted (`results/pages/`,
  cut by `tigerfish/ui/crops.py`), the page number, the grade, the check name, a one-line
  reason, and "Verified by a person" only when a person did.
- Crop and text side by side on desktop, stacked on a phone.
- Hairline 1px borders in `--tf-rule`. No drop shadows (at most a 2px blur) **(checked)**.
  Radius 3px, and not on everything (crops and tables are square).
- No coloured left or top accent bars **(checked)**. A grade is a small stamp, not a stripe.

## Layout

- `layout="wide"`, content max-width 1480px, side padding that shrinks with the screen. No
  half-empty screens at 1920px **(checked)**; no horizontal scroll at 390px **(checked)**.
- Library: a plain filter container above two full-width binders, Deep Investigation Audits
  (saved full audits and the standalone table) and Automated Batch Triage (quick checks).
  Each binder has a full-width header and a two-column card grid above 1400px.
- Audit type is one radio choice: All, Full Audits, or Quick Batch Audits. State, Sector
  and Year remain multiselects; search and the RED/human-verified checkboxes combine with them.
- Render every matching report in its binder, in stable order, without duplicates. There is
  no active page-size cap or Show more control. Reset clears all filters and restores All;
  empty binders explain that no reports match. Batch screening evidence remains separately reachable.
- Home: left, the hero slip (species flags on the Indira Point table that a reviewer
  confirmed, with reference photos; the planted tigerfish slip only if those reviews are
  missing); right, tagline, purpose line, totals as one sentence, a
  search box into the library and "Upload your EIA". Below, the library. No centered hero,
  no row of three feature cards.
- Report: section tabs across the full width; inside a section, findings in the main column
  and a side panel with that section's filters, counts and what the check does.

## Brand lines

- Tagline, Home headline only, Newsreader: **Built for murky water.**
- Purpose line, Schibsted Grotesk: **A second reader for environmental impact reports, and
  everyone who questions them.** Under the tagline on Home and, small, beside the logo in the
  top bar of every page. It wraps under the logo on a phone; it is never truncated.
- Browser title: "TigerFish: built for murky water". Meta description: the purpose line.

## Copy

- No em dashes in UI text **(checked)**. Use a colon, a comma or a new sentence.
- No emojis as icons or bullets **(checked)**, no sparkles, no "1, 2, 3" step rows, no
  stat-banner rows, no badge above the H1, no checkmark bullet lists, no fake testimonials,
  no placeholder names or numbers **(checked)**.
- Every number is computed from `results/` at render time. If a number has no source, it
  does not ship.
- A flag is a lead to verify, not a verdict. Say so where flags are counted.

## States

Every section has an empty state that says why it is empty, loading tied to real work (a
spinner around the call that is running, never a fake skeleton), and an error state that
says what happened and what to do next. Every button gives visible feedback. Uploads are
validated on the server (type, size, page count) with a clear message.

## Nothing gets buried

Every feature is reachable in two clicks from Home and listed in the top menu, a report's
section tabs or a side panel. `docs/FEATURES.md` is the inventory; `check_design.py` fails if
a listed feature has no visible entry point.
