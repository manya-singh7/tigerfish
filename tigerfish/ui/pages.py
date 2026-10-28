"""The app's pages, in the top menu: Home · Library · Upload · How it works · Limitations.

app.py builds the menu with st.navigation(position="top") from PAGES. The library stays the
main entry point: Home leads into it, and a report opens inside it (Library, ?report=<id>).
Old links keep working: /?report=<id> and /?view=upload are sent on to the right page
(redirect() in app.py).
"""

from pathlib import Path

import streamlit as st

from tigerfish import library, page_picks
from tigerfish.ui import data, method, report_view, upload
from tigerfish.ui import library as library_ui
from tigerfish.ui.style import esc

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
FEATURED = "great_nicobar_2021_draft"
BUILT_WITH = "Built with NVIDIA Nemotron on Nebius Token Factory + Tavily"
TAGLINE = "Sees clearly in murky waters."
PROBLEM = ("An Environmental Impact Assessment can run to a thousand pages, and the people who "
           "have to read it, from appraisal committees to communities at a public hearing, rarely "
           "have time to check every figure. TigerFish reads the whole report and flags statements "
           "that disagree with each other or with public records, with the page, the exact quote "
           "and the evidence, so a reviewer can verify each one.")
STORY = ("The tigerfish hunts in fast, silt-heavy African rivers, where the water is rarely clear.  \n"
         "It still finds what it is looking for.  \n"
         "TigerFish does the same with EIA reports: long, dense documents where the details that "
         "matter are hard to see.")

# Which model does what, and why (tigerfish/llm.py).
MODELS = [
    ("Nemotron Lightning", "Reads text pages and pulls out every claim with its quote; first "
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
    ("Quick check", "free, whole report",
     "Every free check on every page with a text layer: number pairs, species and IUCN "
     "categories against GBIF, threatened species near the site that are never mentioned. "
     "No key, no model calls."),
    ("Deep audit", "chosen pages, live",
     f"The model checks (claims, contradictions, recycled figures) on up to "
     f"{page_picks.MAX_PAGES} pages you choose. Needs a key: the site's or your own. The cost "
     "is shown before anything runs."),
    ("Full audit", "every page",
     "Every page and every check, about an hour per report. Run scripts/audit.py locally "
     "with your own keys. The saved audits in the library are full runs."),
]

CSS = """<style>
.tf-home-tag { font-size: 1.9rem; font-weight: 750; line-height: 1.15; margin: 0.4rem 0 0.6rem 0; }
.tf-home-lede { max-width: 48rem; font-size: 1.02rem; margin-bottom: 1rem; opacity: 0.9; }
.tf-card-head { font-size: 1.05rem; font-weight: 650; margin-bottom: 0.2rem; }
.tf-card-body { font-size: 0.9rem; opacity: 0.85; min-height: 4.6rem; }
.tf-built { font-size: 0.85rem; opacity: 0.75; margin-top: 1.6rem; }
</style>"""


def heading(title, sub=None):
    st.markdown(f'<div class="tf-title">{esc(title)}</div>'
                + (f'<div class="tf-tagline">{esc(sub)}</div>' if sub else ""),
                unsafe_allow_html=True)


def _card(col, title, body, page, label, query_params=None, primary=False):
    with col.container(border=True):
        st.markdown(f'<div class="tf-card-head">{esc(title)}</div>'
                    f'<div class="tf-card-body">{esc(body)}</div>', unsafe_allow_html=True)
        st.page_link(page, label=label, icon=":material/arrow_forward:", query_params=query_params,
                     width="stretch")


def logo_path():
    """The full lockup for the viewer's theme (logo.svg on light, logo_dark.svg on dark)."""
    try:
        dark = st.context.theme.type == "dark"
    except Exception:
        dark = False
    return ASSETS / ("logo_dark.svg" if dark else "logo.svg")


def home():
    st.markdown(CSS, unsafe_allow_html=True)
    st.image(str(logo_path()), width=320)
    st.markdown(f'<div class="tf-home-tag">{esc(TAGLINE)}</div>'
                f'<div class="tf-home-lede">{esc(PROBLEM)}</div>', unsafe_allow_html=True)

    t = library.totals(library_ui.entries())
    m = st.columns(4)
    m[0].metric("EIAs checked", f"{t['reports']:,}")
    m[1].metric("Pages read", f"{t['pages']:,}")
    m[2].metric("Flags", f"{t['flags']:,}", help=f"{t['red']:,} RED, {t['orange']:,} ORANGE")
    m[3].metric("INFO leads", f"{t['info']:,}")
    st.caption(f"Live totals, computed from the saved results: {library.totals_line(t)}. "
               "A flag is a lead to verify against the report, not a verdict.")

    st.write("")
    a, b, c = st.columns(3)
    _card(a, "Browse the library", f"Every report TigerFish has checked ({t['full']} full "
          f"audit{'s' if t['full'] != 1 else ''}, {t['quick']} quick check"
          f"{'s' if t['quick'] != 1 else ''}), with filters and search.",
          PAGES["library"], "Open the library")
    _card(b, "Upload your EIA", "Run the free checks on a PDF of your own, then choose pages "
          "for the model checks.", PAGES["upload"], "Upload a report")
    featured = library.find(library_ui.entries(), FEATURED)
    if featured:
        g = featured["grades"]
        _card(c, "See a full audit: Great Nicobar",
              f"{featured['pages']:,} pages read, {g['RED']} RED and {g['ORANGE']} ORANGE flags, "
              "each with its page and quote.", PAGES["library"], "Open the audit",
              query_params={"report": FEATURED})

    st.write("")
    st.markdown("#### Why a tigerfish")
    st.markdown(STORY)
    st.markdown(f'<div class="tf-built">{esc(BUILT_WITH)}</div>', unsafe_allow_html=True)


def library_page():
    view, report_id = library_ui.current()
    if view != "report":
        heading("Report library")
        library_ui.render()
        return
    library_ui.back_link()
    entry = library.find(library_ui.entries(), report_id)
    if entry is None:
        st.error("This report is not in the library.")
        return
    library_ui.switcher(report_id)
    if entry["audit_type"] == library.QUICK:      # free checks only: the lighter view
        report_view.render(library.load(entry), quick=True)
    else:
        report_view.render(data.load(report_id))


def upload_page():
    library_ui.back_link()
    heading("Upload your EIA")
    report = upload.render()
    if report is not None:
        report_view.render(report)


def how_it_works():
    heading("How it works", "From a PDF to flags a person can check.")
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.image(str(ASSETS / "how_it_works.svg"), width="stretch")
    with right:
        st.markdown("#### Which model does what, and why")
        for name, does, why in MODELS:
            st.markdown(f"**{name}**  \n{does}  \n*Why:* {why}")
        st.caption("NVIDIA Nemotron models run on Nebius Token Factory. Every quote a model "
                   "returns is checked against the page text before it is shown.")
    st.markdown("#### Three levels")
    cols = st.columns(3)
    for col, (name, sub, body) in zip(cols, LEVELS):
        with col.container(border=True):
            st.markdown(f"**{name}** ({sub})  \n{body}")
    st.write("")
    st.markdown(method.method_text())
    st.page_link(PAGES["limitations"], label="Known limitations", icon=":material/arrow_forward:")


def limitations():
    heading("Limitations", "Every flag is a lead for human review, not a verdict.")
    st.markdown(method.limits_text())
    text = method.limitations_text()
    if text:
        st.markdown("#### Failure cases from our own runs (docs/LIMITATIONS.md)")
        st.markdown(text.replace("$", "\\$"))      # $ pairs would render as LaTeX


# Filled by build(); the keys are used across the app (st.page_link / st.switch_page).
PAGES = {}


def build():
    """The page objects, in menu order. Call once per run, before st.navigation."""
    PAGES.update({
        "home": st.Page(home, title="Home", icon=":material/home:", url_path="home", default=True),
        "library": st.Page(library_page, title="Library", icon=":material/library_books:",
                           url_path="library"),
        "upload": st.Page(upload_page, title="Upload", icon=":material/upload_file:", url_path="upload"),
        "how": st.Page(how_it_works, title="How it works", icon=":material/account_tree:",
                       url_path="how-it-works"),
        "limitations": st.Page(limitations, title="Limitations", icon=":material/info:",
                               url_path="limitations"),
    })
    return list(PAGES.values())
