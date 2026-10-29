"""TigerFish: a second reader for environmental impact reports, and everyone who questions them.

Run:  streamlit run app.py
Top menu (tigerfish/ui/pages.py): Home · Library · Upload · How it works · Limitations.
The library is the main entry point: every saved report in results/, needing no API keys;
a report opens inside it (/library?report=<id>) in sections side by side
(tigerfish/ui/report_view.py). Upload (tigerfish/ui/upload.py) runs the free checks with no
key, and the model checks with a key. On the hosted app (tigerfish/hosted.py) everything shown
comes from committed files, and paid model calls are capped. Design rules: docs/DESIGN.md.
"""

import streamlit as st
import streamlit.components.v1 as components

from tigerfish.ui import pages
from tigerfish.ui import library as library_ui
from tigerfish.ui.style import CSS, PURPOSE, is_dark, theme_css

PAGE_TITLE = "TigerFish: built for murky water"

st.set_page_config(page_title=PAGE_TITLE, page_icon="assets/favicon-64.png", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(CSS + theme_css(), unsafe_allow_html=True)
# Wordmark in the top bar, light or dark by the viewer's theme (st.context.theme.type can lag
# one rerun after a theme switch; the teal icon tile reads on both). The purpose line beside it
# is drawn by CSS (style.py), so it wraps under the logo on a phone.
st.logo("assets/wordmark_dark.svg" if is_dark() else "assets/wordmark.svg", size="large")
# The meta description: Streamlit has no option for it, so a zero-height component sets it once
# (same origin as the app). Hidden by style.py.
components.html(f"""<script>
const d = window.parent.document;
let m = d.querySelector('meta[name="description"]');
if (!m) {{ m = d.createElement('meta'); m.name = 'description'; d.head.appendChild(m); }}
m.content = {PURPOSE!r};
</script>""", height=0)

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
