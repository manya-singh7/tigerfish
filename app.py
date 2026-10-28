"""TigerFish: an accuracy checker for Indian Environmental Impact Assessment reports.

Run:  streamlit run app.py
Top menu (tigerfish/ui/pages.py): Home · Library · Upload · How it works · Limitations.
The library is the main entry point: every saved report in results/, needing no API keys;
a report opens inside it (/library?report=<id>) in sections side by side
(tigerfish/ui/report_view.py). Upload (tigerfish/ui/upload.py) runs the free checks with no
key, and the model checks with a key. On the hosted app (tigerfish/hosted.py) everything shown
comes from committed files, and paid model calls are capped.
"""

import streamlit as st

from tigerfish.ui import pages
from tigerfish.ui import library as library_ui
from tigerfish.ui.style import CSS, theme_css

st.set_page_config(page_title="TigerFish", page_icon="assets/favicon-64.png", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(CSS + theme_css(), unsafe_allow_html=True)
# Full lockup in the top bar; st.context.theme.type picks the light or dark wordmark (it can lag
# one rerun after a theme switch; the icon tile reads on both).
st.logo("assets/logo_dark.svg" if st.context.theme.type == "dark" else "assets/logo.svg",
        icon_image="assets/logo_icon.svg", size="large")

page = st.navigation(pages.build(), position="top")


def redirect(page):
    """Old links: /?report=<id> opens the report in the Library, /?view=upload the Upload page."""
    view, report_id = library_ui.current()
    if view == "report" and page is not pages.PAGES["library"]:
        st.switch_page(pages.PAGES["library"], query_params={"report": report_id})
    if view == "upload":
        st.switch_page(pages.PAGES["upload"])


redirect(page)
page.run()
