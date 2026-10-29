"""The app's pages, in the top menu: Home · Library · Upload · How it works · Limitations.

app.py builds the menu with st.navigation(position="top") from PAGES. Home leads into the
library (it carries the library below its opening row); a report opens inside the Library
(?report=<id>). Old links keep working: /?report=<id> and /?view=upload are sent on to the
right page (redirect() in app.py). Layout rules: docs/DESIGN.md.
"""

import json
from pathlib import Path

import streamlit as st

from tigerfish import library, page_picks
from tigerfish.ui import data, method, report_view, upload
from tigerfish.ui import library as library_ui
from tigerfish.ui.style import PURPOSE, TAGLINE, badge, esc, mono

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
BUILT_WITH = "Built with NVIDIA Nemotron on Nebius Token Factory + Tavily"
# The Home slip. The story text is fixed; the numbers come from results/eval.json.
TIGERFISH_STORY = ("An African fish at Great Nicobar? This planted evaluation case shows how "
    "TigerFish checks a species claim against recorded geography.")
SCROLL_URL = ("https://scroll.in/article/1095311/fake-claims-great-nicobar-lighthouse-project-"
              "study-lists-species-found-in-africa-amazon")
TIGERFISH_SPECIES = "Hydrocynus vittatus"
INDIRA_POINT = (6.75, 93.83)

# Which model does what, and why (tigerfish/llm.py).
MODELS = [
    ("Nemotron Lightning", "Reads text pages and extracts checkable claims with quotes; first "
        "pass on candidate pairs (triage); ToR promises; translates the letter.",
     "Fast and cheap, so it can read every page of a 1,000-page report."),
    ("Nemotron Super-VL", "Reads scanned pages, tables and maps from the page image.",
     "Takes images: many EIA tables exist only as scans."),
    ("Nemotron Ultra", "Reads both full pages of each candidate pair and gives the verdict; "
     "re-reads possible ToR shortfalls; writes the reviewer's memo and answers questions.",
     "The strongest reasoning, used only where a verdict is made."),
    ("Tavily", "Searches the web for copied text, the official record, the paper trail and "
     "the public record.", "Returns sources with their text, so every quote can be checked."),
    ("GBIF (no model)", "Species names, occurrence records near the site and IUCN categories.",
     "Open biodiversity data; free."),
]
LEVELS = [
    ("Quick check", "free, text layer",
     "Available free checks on the readable text layer, within page and name caps: number pairs, species and IUCN "
        "categories against GBIF, threatened species near the site that are never mentioned. "
        "No key, no model calls."),
    ("Deep audit", "chosen pages, live",
     f"The model checks (claims, contradictions, recycled figures) on up to "
     f"{page_picks.MAX_PAGES} pages you choose. Needs a key: the site's or your own. The cost "
     "is shown before anything runs."),
    ("Full audit", "scoped report run",
     "Claim extraction, contradictions and copied-text checks over the selected report scope. "
        "Run scripts/audit.py locally; specialized checks use separate scripts and inputs. "
        "The three saved full audits took about an hour each; quick checks are a different scope."),
]


def heading(title, sub=None, key=None, back=False):
    """A page heading on its own paper strip (text never sits on the pattern)."""
    with st.container(key=key or f"tf-panel-head-{title.lower().replace(' ', '-')}"):
        if back:
            library_ui.back_link()
        st.markdown(f'<h1 class="tf-h1 tf-title">{esc(title)}</h1>'
                    + (f'<div class="tf-lede">{esc(sub)}</div>' if sub else ""),
                    unsafe_allow_html=True)


def tigerfish_row():
    """The tigerfish species check at Indira Point, from results/eval.json (None if absent)."""
    path = ROOT / "results" / "eval.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))["species"]["rows"]
    except (OSError, KeyError, ValueError):
        return None
    return next((r for r in rows if r.get("name") == TIGERFISH_SPECIES), None)


def tigerfish_slip():
    r = tigerfish_row()
    lat, lon = INDIRA_POINT
    facts = ""
    if r:
        facts = (f'<div class="tf-slip-head">{badge(r["grade"])}<span class="tf-check">Species out '
                 f'of range</span><span class="tf-slip-page">{lat:.2f} N, {lon:.2f} E</span></div>'
                 f'<div class="tf-slip-title"><i>{esc(r["gbif_name"])}</i>, the tigerfish, at '
                 f'Indira Point</div>'
                 f'<div class="tf-slip-reason">GBIF records: {mono(f"{r["local"]:,}")} within 100 km, '
                 f'{mono(f"{r["regional"]:,}")} within 500 km, {mono(f"{r["global"]:,}")} worldwide.</div>')
    return (f'<div class="tf-slip tf-slip-noimg tf-home-slip"><div class="tf-slip-text">'
        f'<blockquote class="tf-slip-quote tf-story">{esc(TIGERFISH_STORY)}</blockquote>'
        f'{facts}<div class="tf-slip-foot"><span>Planted species check from results/eval.json, not an extracted report finding.</span>'
        f'<a href="{SCROLL_URL}" target="_blank" rel="noopener">Read the Scroll.in report</a>'
        f"</div></div></div>")


def go_search():
    st.session_state["lib::q"] = st.session_state.get("home::q", "")
    st.session_state["lib::shown"] = library_ui.PAGE_SIZE


HOME_CSS = """<style>
.tf-home-slip { margin: 0; height: 100%; }
.tf-home-slip .tf-story { font-size: 1.5rem; line-height: 1.3; margin-bottom: 1rem; }
.st-key-tf-home-top [data-testid="stHorizontalBlock"] { align-items: stretch; }
@media (max-width: 1099px) {
  .st-key-tf-home-top [data-testid="stHorizontalBlock"] { flex-direction: column-reverse !important; }
  .st-key-tf-home-top [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
}
</style>"""


def home():
    st.markdown(HOME_CSS, unsafe_allow_html=True)
    t = library.totals(library_ui.entries())
    with st.container(key="tf-home-top"):
        left, right = st.columns([6, 5], gap="medium")
        with left:
            st.markdown(tigerfish_slip(), unsafe_allow_html=True)
        with right, st.container(key="tf-panel-home"):
            st.markdown(f'<h1 class="tf-h1 tf-home-tag">{esc(TAGLINE)}</h1>'
                        f'<p class="tf-purpose">{esc(PURPOSE)}</p>'
                        f'<p class="tf-totals tf-home-totals">{esc(library.totals_line(t))}, '
                        f'computed from the saved results.</p>', unsafe_allow_html=True)
            st.text_input("Search the library", key="home::q", on_change=go_search,
                          placeholder="Project, state or sector, e.g. port")
            st.page_link(PAGES["upload"], label="Upload your EIA", icon=":material/upload_file:")
            st.markdown(f'<div class="tf-meta">{esc(BUILT_WITH)}</div>', unsafe_allow_html=True)
    st.write("")
    library_ui.render()


def library_page():
    view, report_id = library_ui.current()
    if view != "report":
        heading("Report library", "Every EIA TigerFish has read. Open one to see its flags, "
                "each with the page and the quote.")
        library_ui.render()
        return
    entry = library.find(library_ui.entries(), report_id)
    with st.container(key="tf-panel-report-bar"):
        a, b = st.columns([1, 2], vertical_alignment="center")
        with a:
            library_ui.back_link()
        with b:
            library_ui.switcher(report_id)
    if entry is None:
        with st.container(key="tf-panel-missing"):
            st.error("This report is not in the library.")
            st.markdown(f"No saved report has the id `{esc(report_id)}`. The link may be old or "
                        "mistyped. Go back to the library and pick the report from the list.")
        return
    if entry["audit_type"] == library.QUICK:      # free checks only: the lighter view
        report_view.render(library.load(entry), quick=True)
    else:
        report_view.render(data.load(report_id))


def upload_page():
    heading("Upload your EIA", back=True, sub="Run the free checks on a PDF of your own, then choose pages for "
            "the model checks.")
    with st.container(key="tf-panel-upload"):
        report = upload.render()
    if report is not None:
        report_view.render(report)


def levels_table():
    rows = "".join(f"<tr><td><b>{esc(n)}</b></td><td>{esc(s)}</td><td>{esc(b)}</td></tr>"
                   for n, s, b in LEVELS)
    return ('<table class="tf-table"><thead><tr><th>Level</th><th>Scope</th><th>What runs</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>')


def _diagram():
    from tigerfish.ui.diagram import diagram_svg
    return diagram_svg()


def how_it_works_page():
    heading("How it works", "From a PDF to flags a person can check.")
    left, right = st.columns([5, 6], gap="medium")
    with left, st.container(key="tf-panel-diagram"):
        st.markdown(_diagram(), unsafe_allow_html=True)
    with right:
        with st.container(key="tf-panel-levels"):
            st.markdown('<h2 class="tf-h2">Three levels</h2>' + levels_table(), unsafe_allow_html=True)
        with st.container(key="tf-panel-models"):
            st.markdown('<h2 class="tf-h2">Which model does what, and why</h2>'
                        '<table class="tf-table"><thead><tr><th>Model</th><th>Does</th><th>Why</th>'
                        '</tr></thead><tbody>' + "".join(
                            f'<tr><td class="tf-mono">{esc(n)}</td><td>{esc(d)}</td><td>{esc(w)}</td></tr>'
                            for n, d, w in MODELS) + "</tbody></table>", unsafe_allow_html=True)
            st.caption("NVIDIA Nemotron models run on Nebius Token Factory. Text-backed quotes "
                "are matched to source text; image-only readings are shown with their "
                "source image and labelled unverified.")
        with st.container(key="tf-panel-method"):
            st.markdown(method.method_text())
            st.page_link(PAGES["limitations"], label="Known limitations",
                         icon=":material/arrow_forward:")


def limitations():
    heading("Limitations", "Every flag is a lead for human review, not a verdict.")
    with st.container(key="tf-panel-limits"):
        st.markdown(method.limits_text())
    text = method.limitations_text()
    if text:
        with st.container(key="tf-panel-failures"):
            st.markdown("#### Failure cases from our own runs (docs/LIMITATIONS.md)")
            st.markdown(text.replace("$", "\\$"))      # $ pairs would render as LaTeX


# Filled by build(); the keys are used across the app (st.page_link / st.switch_page).
PAGES = {}


def build():
    """The page objects, in menu order. Call once per run, before st.navigation."""
    PAGES.update({
        "home": st.Page(home, title="Home", url_path="home", default=True),
        "library": st.Page(library_page, title="Library", url_path="library"),
        "upload": st.Page(upload_page, title="Upload", url_path="upload"),
        "how": st.Page(how_it_works_page, title="How it works", url_path="how-it-works"),
        "limitations": st.Page(limitations, title="Limitations", url_path="limitations"),
    })
    return list(PAGES.values())
