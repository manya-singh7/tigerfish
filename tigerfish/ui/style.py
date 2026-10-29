"""Look and feel, from docs/DESIGN.md: an auditor's field notebook.

One background personality (the doodle pattern, assets/bg_pattern.svg, on the page colour)
and one repeated card (the evidence slip, tigerfish/ui/slip.py) on solid paper surfaces.
Colour is reserved for the grades: RED, ORANGE and GREY (INFO leads). Tokens are CSS
variables, redefined for the dark theme by theme_css().
"""

import html
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN = ROOT / "assets" / "bg_pattern.svg"

LIGHT = {
    "page": "#E9E2D2", "paper": "#FAF6EC", "paper-2": "#F2ECDF", "ink": "#17302F",
    "teal": "#0D4242", "muted": "#59625F", "rule": "#CFC6B3", "on-teal": "#FAF6EC",
    "red": "#9E2A1F", "orange": "#8F4A06", "grey": "#59625F",
    "pattern": "#0D4242", "pattern-alpha": "0.10", "mark": "#F3E3A6",
}
DARK = {
    "page": "#0F1716", "paper": "#16201F", "paper-2": "#1C2827", "ink": "#ECE5D6",
    "teal": "#8CC7BE", "muted": "#A7AFAB", "rule": "#33403E", "on-teal": "#0F1716",
    "red": "#F08F84", "orange": "#E5A35C", "grey": "#A7AFAB",
    "pattern": "#ECE5D6", "pattern-alpha": "0.07", "mark": "#5A4E22",
}
# Kept for modules that colour charts (species map, cost chart): light-theme values.
ACCENT, TEXT, MUTED, BORDER = LIGHT["teal"], LIGHT["ink"], LIGHT["muted"], LIGHT["rule"]
PAPER, PAPER_2 = LIGHT["paper"], LIGHT["paper-2"]
BODY_FONT = "Schibsted Grotesk, Noto Sans Devanagari, Noto Sans Tamil, Noto Sans Kannada, sans-serif"
HEAD_FONT = "Newsreader, Georgia, serif"
MONO_FONT = "IBM Plex Mono, Consolas, monospace"

GRADE_CLASS = {"RED": "red", "ORANGE": "orange", "INFO": "grey", "GREY": "grey", "NONE": "grey"}
PURPOSE = "A second reader for environmental impact reports, and everyone who questions them."
TAGLINE = "Built for murky water."


def _pattern_uri(t):
    svg = PATTERN.read_text(encoding="utf-8")
    svg = svg.replace('stroke="#0D4242"', f'stroke="{t["pattern"]}" stroke-opacity="{t["pattern-alpha"]}"')
    return "data:image/svg+xml," + urllib.parse.quote(svg, safe="")


def _vars(t):
    return "".join(f"--tf-{k}:{v};" for k, v in t.items() if k not in ("pattern", "pattern-alpha"))


# Sizes: 2.5rem, 1.5rem, 1.125rem, 1rem, 0.8125rem. Nothing else.
CSS_BODY = """
:root { @@VARS@@ }
html, body { background: var(--tf-page); }
.stApp { background-color: var(--tf-page);
  background-image: url("@@PATTERN@@"); background-size: 520px 520px; background-repeat: repeat; }
.stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input, .stApp textarea { line-height: 1.5; }
h1, h2, h3, h4, h5, h6 { line-height: 1.15 !important; letter-spacing: -0.005em; text-transform: none !important; }
code, kbd, pre, .tf-mono { font-family: "IBM Plex Mono", Consolas, monospace !important;
  font-variant-numeric: tabular-nums; }
.tf-mono { font-size: 0.8125rem; }
a { color: var(--tf-teal); font-family: "Schibsted Grotesk", sans-serif; }

/* ---- the top bar: paper, hairline, logo and the purpose line ---- */
header[data-testid="stHeader"] { background: var(--tf-paper) !important;
  border-bottom: 1px solid var(--tf-rule); }
header [data-testid="stHeaderLogo"] { height: 2rem; width: auto; max-width: none; }
header div:has(> img[data-testid="stHeaderLogo"]), header div:has(> [data-testid="stLogoLink"]) { display: flex; align-items: center; }
header div:has(> img[data-testid="stHeaderLogo"])::after, header div:has(> [data-testid="stLogoLink"])::after { content: "@@PURPOSE@@";
  font-family: "Schibsted Grotesk", sans-serif; font-size: 0.8125rem; line-height: 1.3;
  color: var(--tf-muted); width: max-content; max-width: 36rem; margin-left: 1.1rem; white-space: normal;
  overflow: visible; text-overflow: clip; display: block; }
header nav { margin-left: auto !important; display: flex !important; justify-content: flex-end !important; align-items: center !important; gap: 0.5rem !important; }
header [data-testid="stTopNavLink"] { padding: 0.35rem 0.65rem !important; }

/* ---- page width: 1480px max, padding that scales with the screen ---- */
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1480px !important;
  padding: 5.25rem clamp(1rem, 3vw, 2.5rem) 4rem !important; }

/* ---- surfaces that cover the pattern ---- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { }
[data-testid="stVerticalBlock"] [data-testid="stVerticalBlockBorderWrapper"][data-test-border="true"],
div[class*="st-key-tf-panel"], div[class*="st-key-tf-slip"] {
  background: var(--tf-paper); border: 1px solid var(--tf-rule) !important; border-radius: 3px;
  box-shadow: none !important; }
div[class*="st-key-tf-panel"] { padding: 1.25rem 1.5rem; }
div[class*="st-key-tf-plain"] { background: var(--tf-paper); padding: 1rem 1.25rem;
  border: 1px solid var(--tf-rule); border-radius: 3px; }
[data-testid="stExpander"] details { background: var(--tf-paper); border: 1px solid var(--tf-rule);
  border-radius: 3px; box-shadow: none; }
[data-testid="stTabs"] [role="tablist"] { background: var(--tf-paper); border: 1px solid var(--tf-rule);
  border-radius: 3px; padding: 0 0.75rem; gap: 0.9rem; }
[data-testid="stTabs"] [role="tab"] { padding-left: 0.1rem; padding-right: 0.1rem; }
[data-testid="stTabs"] [role="tab"] p { font-size: 1rem; font-weight: 500; }
[data-testid="stTabs"] [role="tabpanel"] { padding-top: 1rem; }
[data-testid="stAlert"] > div { background: var(--tf-paper) !important; border: 1px solid var(--tf-rule);
  border-radius: 3px; color: var(--tf-ink) !important; }
[data-testid="stAlert"] [data-testid="stAlertContentInfo"] *,
[data-testid="stAlert"] [data-testid="stAlertContentWarning"] *,
[data-testid="stAlert"] [data-testid="stAlertContentSuccess"] *,
[data-testid="stAlert"] [data-testid="stAlertContentError"] * { color: var(--tf-ink) !important; }
[data-testid="stAlertContentError"] p:first-child, [data-testid="stAlertContentWarning"] p:first-child { font-weight: 600; }
[data-testid="stAlertDynamicIcon"] { display: none; }
div[data-baseweb="tooltip"], [role="tooltip"], div[data-testid="stTooltipContent"] { pointer-events: none !important; }
[data-testid="stCaptionContainer"], .stCaption { font-size: 0.8125rem !important; color: var(--tf-muted) !important; }
[data-testid="stWidgetLabel"] p { font-size: 0.8125rem !important; font-weight: 600; color: var(--tf-ink); }
[data-testid="stTable"], [data-testid="stDataFrame"] { background: var(--tf-paper); }
input, textarea, [data-baseweb="select"] > div, [data-baseweb="input"] { background: var(--tf-paper) !important; }
button[kind="primary"], button[data-testid="stBaseButton-primary"] { color: var(--tf-on-teal) !important; }
button:focus-visible, a:focus-visible { outline: 2px solid var(--tf-teal) !important; outline-offset: 2px; }
.stButton button:active, .stDownloadButton button:active { transform: translateY(1px); }
[data-testid="stMarkdownContainer"] p { font-size: 1rem; }
[data-testid="stMarkdownContainer"] small, .tf-small { font-size: 0.8125rem; }
hr { border-color: var(--tf-rule) !important; }

/* the zero-height component that sets the meta description (app.py) */
.stElementContainer:has(> iframe[height="0"]), [data-testid="stElementContainer"]:has(iframe[height="0"]) { display: none; }

[data-testid="stElementToolbarButtonContainer"], [data-testid="stElementToolbar"] * { box-shadow: none !important; }
[data-testid="stTabs"] button:not([role="tab"]) { background-image: none !important; background-color: var(--tf-paper) !important; }
@media (max-width: 760px) {
  .tf-table { display: block; overflow-x: auto; }
  .tf-table th, .tf-table td { min-width: 7.5rem; }
}

/* ---- type helpers ---- */
.tf-h1 { font-family: Newsreader, Georgia, serif; font-size: 2.5rem; font-weight: 600; line-height: 1.15;
  color: var(--tf-teal); margin: 0 0 0.6rem 0; font-optical-sizing: auto; }
.tf-h2 { font-family: Newsreader, Georgia, serif; font-size: 1.5rem; font-weight: 600; line-height: 1.15;
  color: var(--tf-teal); margin: 0 0 0.4rem 0; }
.tf-h3 { font-family: Newsreader, Georgia, serif; font-size: 1.125rem; font-weight: 600; line-height: 1.15;
  color: var(--tf-ink); margin: 0 0 0.3rem 0; }
.tf-purpose { font-size: 1.125rem; color: var(--tf-ink); max-width: 36rem; margin: 0 0 1rem 0; }
.tf-lede { color: var(--tf-muted); font-size: 1rem; max-width: 46rem; margin: 0 0 0.6rem 0; }
.tf-meta { font-size: 0.8125rem; color: var(--tf-muted); }
.tf-totals { font-size: 1rem; color: var(--tf-ink); margin: 0.2rem 0 0.8rem 0; }
.tf-totals .tf-mono { font-size: 1rem; }

/* ---- grade stamps: the only colour ---- */
.tf-badge { display: inline-block; font-family: "IBM Plex Mono", Consolas, monospace; font-size: 0.8125rem;
  font-weight: 500; letter-spacing: 0.04em; padding: 0 0.4rem; border: 1px solid currentColor;
  border-radius: 2px; margin-right: 0.5rem; line-height: 1.5; background: transparent; }
.tf-g-red { color: var(--tf-red) !important; }
.tf-g-orange { color: var(--tf-orange) !important; }
.tf-g-grey { color: var(--tf-grey) !important; }
.tf-check { font-size: 0.8125rem; color: var(--tf-muted); font-weight: 500; }
.tf-ref { font-family: "IBM Plex Mono", Consolas, monospace; font-size: 0.8125rem; color: var(--tf-teal);
  margin: 0 0.3rem 0 0.1rem; font-variant-numeric: tabular-nums; }

/* ---- the evidence slip ---- */
.tf-slip { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap: 1.25rem;
  background: var(--tf-paper); border: 1px solid var(--tf-rule); border-radius: 3px; padding: 1rem;
  margin: 0 0 1rem 0; color: var(--tf-ink); }
.tf-slip.tf-slip-noimg { grid-template-columns: minmax(0, 1fr); }
.tf-slip-compact { grid-template-columns: minmax(0, 1fr); }
.tf-slip-crops { display: flex; flex-direction: column; gap: 0.6rem; align-self: start; }
.tf-slip-crop { background: var(--tf-paper-2); border: 1px solid var(--tf-rule); align-self: start;
  margin: 0; }
.tf-slip-crop img { width: 100%; display: block; max-height: 260px; object-fit: cover; object-position: center; }
.tf-slip-crop figcaption, .tf-slip-photo figcaption { font-size: 0.8125rem; color: var(--tf-muted);
  padding: 0.3rem 0.5rem; }
.tf-slip-photo { margin: 0; align-self: start; }
.tf-slip-photo img { width: 100%; max-height: 260px; object-fit: cover; display: block; border: 1px solid var(--tf-rule); }
.tf-slip-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.25rem 0.5rem; }
.tf-slip-head .tf-badge { margin-right: 0; }
.tf-slip-page { margin-left: auto; font-family: "IBM Plex Mono", Consolas, monospace; font-size: 0.8125rem;
  color: var(--tf-muted); font-variant-numeric: tabular-nums; }
.tf-slip-title { font-family: Newsreader, Georgia, serif; font-size: 1.125rem; font-weight: 600;
  line-height: 1.15; color: var(--tf-ink); margin: 0.45rem 0 0.4rem 0; }
.tf-slip-quote { border-left: 0 !important; padding: 0 !important; opacity: 1; color: var(--tf-ink) !important; font-family: Newsreader, Georgia, serif; font-style: italic; font-size: 1.125rem;
  line-height: 1.4; color: var(--tf-ink); margin: 0 0 0.5rem 0; overflow-wrap: anywhere; }
.tf-slip-quote .tf-ref { font-style: normal; }
.tf-slip-reason { font-size: 1rem; color: var(--tf-ink); margin: 0 0 0.4rem 0; }
.tf-slip-foot { display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; font-size: 0.8125rem; color: var(--tf-muted);
  margin-top: 0.4rem; }
.tf-person { color: var(--tf-teal); font-weight: 600; }
.tf-person::before { content: ""; display: inline-block; width: 0.55rem; height: 0.55rem; margin-right: 0.35rem;
  border: 1.5px solid currentColor; border-radius: 50%; vertical-align: 0; }
.tf-slip a.tf-open { font-weight: 600; text-decoration: none; }
mark { background: var(--tf-mark); color: inherit; padding: 0 0.1rem; }
.tf-slipbox { container-type: inline-size; }
@container (max-width: 820px) { .tf-slip { grid-template-columns: minmax(0, 1fr); } .tf-slip-crop img { max-height: 320px; } }

/* ---- report cards in the library (slip previews) ---- */
.tf-rep-title { font-family: Newsreader, Georgia, serif; font-size: 1.125rem; font-weight: 600; line-height: 1.15;
  color: var(--tf-ink); margin: 0 0 0.25rem 0; }
.tf-rep-meta { font-size: 0.8125rem; color: var(--tf-muted); margin-bottom: 0.4rem; }
.tf-rep-grades { font-size: 0.8125rem; margin: 0.2rem 0 0.4rem 0; color: var(--tf-ink); }
.tf-rep-grades .tf-mono { margin-right: 0.9rem; }
.tf-kind { font-size: 0.8125rem; font-weight: 600; color: var(--tf-teal); }

/* ---- side panel: sticky on wide screens ---- */
@media (min-width: 1100px) {
  div[class*="st-key-tf-side"] { position: sticky; top: 4.5rem; align-self: flex-start; z-index: 10; }
  [data-testid="stColumn"]:has(div[class*="st-key-tf-side"]) { position: sticky; top: 4.5rem; align-self: flex-start; z-index: 10; }
}
div[class*="st-key-tf-side"] { background: var(--tf-paper); border: 1px solid var(--tf-rule);
  border-radius: 3px; padding: 1rem 1.1rem; pointer-events: auto !important; }
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"],
div[data-testid="stMultiSelect"],
div[data-testid="stCheckbox"],
div[data-testid="stExpanderDetails"] * {
  pointer-events: auto !important;
}

/* ---- multiselect pills and close buttons ---- */
[data-testid="stMultiSelect"] [data-tag],
[data-testid="stMultiSelectTagsContainer"] [data-tag],
[data-baseweb="tag"] {
  background: var(--tf-paper-2) !important;
  color: var(--tf-ink) !important;
  border: 1px solid var(--tf-rule) !important;
  border-radius: 3px !important;
  padding: 0.15rem 0.5rem !important;
  height: auto !important;
  min-height: 1.55rem !important;
  display: inline-flex !important;
  align-items: center !important;
  gap: 0.35rem !important;
  font-family: "Schibsted Grotesk", sans-serif !important;
  font-size: 0.8125rem !important;
  line-height: 1.25 !important;
}
[data-testid="stMultiSelect"] [data-tag] span[title],
[data-testid="stMultiSelectTagsContainer"] [data-tag] span[title],
[data-baseweb="tag"] span {
  color: var(--tf-ink) !important;
  font-size: 0.8125rem !important;
  font-weight: 500 !important;
  white-space: nowrap !important;
}
[data-testid="stMultiSelect"] [data-tag] button,
[data-testid="stMultiSelectTagsContainer"] [data-tag] button,
[data-baseweb="tag"] [role="button"] {
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  margin: 0 !important;
  width: 1rem !important;
  height: 1rem !important;
  min-width: 1rem !important;
  min-height: 1rem !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  color: var(--tf-muted) !important;
  cursor: pointer !important;
  border-radius: 2px !important;
  opacity: 0.8 !important;
  line-height: 1 !important;
}
[data-testid="stMultiSelect"] [data-tag] button:hover,
[data-testid="stMultiSelectTagsContainer"] [data-tag] button:hover,
[data-baseweb="tag"] [role="button"]:hover {
  opacity: 1 !important;
  color: var(--tf-red) !important;
  background: rgba(0, 0, 0, 0.06) !important;
}
[data-testid="stMultiSelect"] [data-tag] button svg,
[data-testid="stMultiSelectTagsContainer"] [data-tag] button svg,
[data-baseweb="tag"] [role="button"] svg {
  width: 0.75rem !important;
  height: 0.75rem !important;
  min-width: 0.75rem !important;
  min-height: 0.75rem !important;
  display: block !important;
  stroke: currentColor !important;
  color: inherit !important;
}
.tf-chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.2rem 0 0.4rem 0; }
.tf-chip { font-size: 0.8125rem; border: 1px solid var(--tf-rule); border-radius: 2px; padding: 0 0.4rem;
  color: var(--tf-ink); background: var(--tf-paper-2); }
.tf-count { font-size: 0.8125rem; color: var(--tf-muted); }
.tf-what { font-size: 0.8125rem; color: var(--tf-ink); }

/* ---- older helpers, restyled to the system ---- */
.tf-title { font-family: Newsreader, Georgia, serif; font-size: 2.5rem; font-weight: 600; color: var(--tf-teal); line-height: 1.15; }
.tf-tagline { font-size: 1rem; color: var(--tf-muted); margin: 0.2rem 0 0.6rem 0; }
.tf-card-title { font-family: Newsreader, Georgia, serif; font-size: 1.125rem; font-weight: 600; color: var(--tf-ink); margin: 0.35rem 0 0.2rem 0; }
.tf-message { color: var(--tf-ink); margin-bottom: 0.6rem; }
.tf-quote-label { font-size: 0.8125rem; color: var(--tf-muted); font-weight: 600; margin-bottom: 0.25rem; }
.tf-quote { font-family: Newsreader, Georgia, serif; font-style: italic; font-size: 1.125rem; color: var(--tf-ink);
  background: var(--tf-paper-2); border: 1px solid var(--tf-rule); padding: 0.5rem 0.75rem; }
.tf-ev { font-size: 1rem; color: var(--tf-ink); margin: 0.15rem 0; overflow-wrap: anywhere; }
.tf-ev-label { color: var(--tf-muted); }
.tf-line { font-size: 1rem; margin: 0.2rem 0; color: var(--tf-ink); }
.tf-line b { color: var(--tf-teal); font-weight: 600; }
.tf-review { font-size: 0.8125rem; color: var(--tf-muted); }
.tf-timeline { border-left: 1px solid var(--tf-rule); margin: 0.4rem 0 0 0.6rem; }
.tf-step { display: flex; gap: 0.7rem; margin: 0 0 0.75rem -0.6rem; }
.tf-step-n { flex: 0 0 1.2rem; height: 1.2rem; border-radius: 50%; background: var(--tf-paper); color: var(--tf-teal);
  border: 1px solid var(--tf-teal); font-family: "IBM Plex Mono", monospace; font-size: 0.8125rem; text-align: center; line-height: 1.1rem; }
.tf-step-body { flex: 1; min-width: 0; font-size: 1rem; color: var(--tf-ink); }
.tf-tool { font-family: "IBM Plex Mono", Consolas, monospace; font-size: 0.8125rem; font-weight: 500; color: var(--tf-teal);
  border: 1px solid var(--tf-rule); border-radius: 2px; padding: 0 0.3rem; margin-right: 0.5rem; }
.tf-step-args { overflow-wrap: anywhere; }
.tf-step-why { color: var(--tf-muted); font-size: 0.8125rem; margin-top: 0.15rem; }
.tf-step-result { margin-top: 0.1rem; }
.tf-step-meta { color: var(--tf-muted); font-size: 0.8125rem; }
.tf-memo-head { font-family: Newsreader, Georgia, serif; font-weight: 600; font-size: 1.125rem; padding: 0.2rem 0.5rem;
  border: 1px solid var(--tf-rule); border-radius: 2px; display: inline-block; margin-bottom: 0.4rem; color: var(--tf-ink); }
.tf-memo-strengthens { color: var(--tf-orange); border-color: currentColor; }
.tf-memo-weakens, .tf-memo-inconclusive { color: var(--tf-grey); border-color: currentColor; }
.tf-memo-sub { font-size: 0.8125rem; color: var(--tf-muted); font-weight: 600; margin: 0.6rem 0 0.3rem 0; }
.tf-memo-list { margin: 0.1rem 0 0.4rem 1.1rem; padding: 0; font-size: 1rem; }
.tf-memo-note { font-size: 0.8125rem; color: var(--tf-muted); margin: 0.2rem 0 0.6rem 0; }
.tf-unverified { color: var(--tf-muted); }
.tf-memo-foot { font-size: 0.8125rem; color: var(--tf-muted); margin-top: 0.6rem; }
.tf-tavily, .tf-via { display: inline-block; font-size: 0.8125rem; font-weight: 500; color: var(--tf-teal) !important;
  border: 1px solid var(--tf-rule); border-radius: 2px; padding: 0 0.35rem; margin-left: 0.35rem;
  text-decoration: none !important; background: transparent; }
.tf-via { margin: 0.3rem 0 0 0; }
.tf-models { display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0.1rem 0 0.5rem 0; }
.tf-model { display: inline-block; font-family: "IBM Plex Mono", Consolas, monospace; font-size: 0.8125rem;
  font-weight: 500; border-radius: 2px; padding: 0 0.35rem; border: 1px solid var(--tf-rule);
  white-space: nowrap; cursor: help; color: var(--tf-ink); background: transparent; }
.tf-model-detail { font-weight: 400; color: var(--tf-muted); }
.tf-model-human { color: var(--tf-teal); border-color: var(--tf-teal); }
.tf-verified { border: 1px solid var(--tf-rule); background: var(--tf-paper-2); padding: 0.45rem 0.7rem;
  margin: 0 0 0.6rem 0; font-size: 1rem; color: var(--tf-ink); }
.tf-verified b { color: var(--tf-teal); }
.tf-knowable { border: 1px solid var(--tf-rule); background: var(--tf-paper-2); padding: 0.45rem 0.7rem;
  margin: 0.6rem 0 0.2rem 0; font-size: 1rem; color: var(--tf-ink); }
.tf-knowable b { color: var(--tf-teal); }
.tf-photo { margin: 0.7rem 0 0.2rem 0; max-width: 300px; }
.tf-photo img { width: 100%; display: block; border: 1px solid var(--tf-rule); }
.tf-photo figcaption { font-size: 0.8125rem; color: var(--tf-muted); margin-top: 0.25rem; line-height: 1.35; }
.tf-table { width: 100%; border-collapse: collapse; font-size: 1rem; margin: 0.4rem 0 0.8rem 0; background: var(--tf-paper); }
.tf-table th { text-align: left; color: var(--tf-muted); font-weight: 600; font-size: 0.8125rem;
  border-bottom: 1px solid var(--tf-rule); padding: 0.4rem 0.5rem; background: var(--tf-paper-2); }
.tf-table td { border-bottom: 1px solid var(--tf-rule); padding: 0.45rem 0.5rem; vertical-align: top;
  color: var(--tf-ink); overflow-wrap: anywhere; }
.tf-off, .tf-open, .tf-auth { display: inline-block; font-size: 0.8125rem; font-weight: 600; border-radius: 2px;
  padding: 0 0.4rem; white-space: nowrap; border: 1px solid currentColor; }
.tf-off { color: var(--tf-teal); }
.tf-open { color: var(--tf-orange); }
.tf-auth { color: var(--tf-grey); }
.tf-doc { border-bottom: 1px solid var(--tf-rule); padding: 0.55rem 0; font-size: 1rem; }
.tf-unusable { color: var(--tf-orange); }
.tf-adb { color: var(--tf-ink); background: var(--tf-paper-2); border: 1px solid var(--tf-rule); padding: 0.5rem 0.7rem; }
.tf-stat { border: 1px solid var(--tf-rule); border-radius: 3px; padding: 0.7rem 0.9rem; background: var(--tf-paper); height: 100%; }
.tf-stat-label { font-size: 0.8125rem; color: var(--tf-muted); font-weight: 600; }
.tf-stat-value { font-family: "IBM Plex Mono", Consolas, monospace; font-size: 1.125rem; font-weight: 500;
  color: var(--tf-ink); margin-top: 0.15rem; font-variant-numeric: tabular-nums; }
.tf-stat-note { font-size: 0.8125rem; color: var(--tf-muted); margin-top: 0.1rem; }

/* ---- the How it works diagram, drawn inline so it takes the page's fonts and theme ---- */
.tf-diagram { width: 100%; max-width: 720px; height: auto; display: block; background: var(--tf-paper);
  border: 1px solid var(--tf-rule); }
.tf-diagram .d-box { fill: var(--tf-paper); stroke: var(--tf-teal); stroke-width: 1; }
.tf-diagram .d-key { stroke-width: 2; }
.tf-diagram .d-dash { fill: none; stroke: var(--tf-muted); stroke-width: 1; stroke-dasharray: 5 5; }
.tf-diagram .d-line, .tf-diagram .d-head { fill: none; stroke: var(--tf-teal); stroke-width: 1.5; }
.tf-diagram .d-title { font-family: Newsreader, Georgia, serif; font-weight: 600; font-size: 22px; fill: var(--tf-ink); }
.tf-diagram .d-body { font-family: "Schibsted Grotesk", sans-serif; font-size: 17px; fill: var(--tf-muted); }
.tf-diagram .d-model { font-family: "IBM Plex Mono", monospace; font-size: 15px; font-weight: 500; fill: var(--tf-teal); }

/* ---- phone and tablet ---- */
@media (max-width: 1200px) {
  header div:has(> img[data-testid="stHeaderLogo"])::after, header div:has(> [data-testid="stLogoLink"])::after { max-width: 22rem; }
}
@media (max-width: 760px) {
  .tf-h1 { font-size: 2.5rem; }
  .block-container, [data-testid="stMainBlockContainer"] { padding-top: 7rem !important; }
  header[data-testid="stHeader"] { height: auto !important; min-height: 3.75rem; }
  header div:has(> img[data-testid="stHeaderLogo"]), header div:has(> [data-testid="stLogoLink"]) { flex-direction: column; align-items: flex-start;
    padding: 0.4rem 0; }
  header div:has(> img[data-testid="stHeaderLogo"])::after, header div:has(> [data-testid="stLogoLink"])::after { margin: 0.25rem 0 0 0; width: 14rem; }
}
"""


def _css(t):
    return (CSS_BODY.replace("@@VARS@@", _vars(t)).replace("@@PATTERN@@", _pattern_uri(t))
            .replace("@@PURPOSE@@", PURPOSE))


CSS = "<style>" + _css(LIGHT) + "</style>"
DARK_CSS = "<style>:root { " + _vars(DARK) + " } .stApp { background-image: url(\"" + _pattern_uri(DARK) + "\"); }</style>"


def esc(text):
    return html.escape(str(text if text is not None else ""))


def grade_class(grade):
    return "tf-g-" + GRADE_CLASS.get(str(grade).upper(), "grey")


def badge(grade):
    """The grade stamp: text and hairline in the grade's colour, no fill."""
    return f'<span class="tf-badge {grade_class(grade)}">{esc(grade)}</span>'


def mono(text):
    return f'<span class="tf-mono">{esc(text)}</span>'


def stat(label, value, note=""):
    note_html = f'<div class="tf-stat-note">{esc(note)}</div>' if note else ""
    return (f'<div class="tf-stat"><div class="tf-stat-label">{esc(label)}</div>'
            f'<div class="tf-stat-value">{esc(value)}</div>{note_html}</div>')


def is_dark():
    import streamlit as st
    try:
        return st.context.theme.type == "dark"
    except Exception:      # no browser context (tests)
        return False


def theme_css():
    """The dark tokens and pattern ("" in the light theme)."""
    return DARK_CSS if is_dark() else ""
