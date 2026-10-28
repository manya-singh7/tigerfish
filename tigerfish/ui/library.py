"""Home screen: the report library (every report under results/), live totals, filters,
and the "Upload your own EIA" button. Navigation lives in the URL:
  (none)            the library
  ?report=<id>      a report (tigerfish/ui/report_view.py: sections side by side; a quick
                    check gets only its own sections)
  ?view=upload      upload a new EIA (app.py sends it on to the Upload page)
"""

from pathlib import Path

import streamlit as st

from tigerfish import library
from tigerfish.ui.style import badge, esc

PAGE_SIZE = 25
UPLOAD_NOTE = ("Saved audits are full runs. Upload your own EIA to run live checks: the free "
               "checks read the whole report; the model checks run on up to 30 pages you choose "
               "on this site (run locally for full reports).")


def _stamp():
    """Changes when any library file changes, so the cached list refreshes."""
    files = [library.RESULTS / "index.json", library.RESULTS / "library.json",
             library.batch_dir() / "index.json"]
    return tuple((str(f), f.stat().st_mtime) if f.exists() else (str(f), 0) for f in files)


@st.cache_data(show_spinner=False)
def _entries(stamp):
    return library.entries()


def entries():
    return _entries(_stamp())


# ---------- navigation ----------

def current():
    """("library" | "upload" | "report", report id or None)."""
    qp = st.query_params
    if qp.get("report"):
        return "report", qp.get("report")
    if qp.get("view") == "upload":
        return "upload", None
    return "library", None


def open_report(report_id):
    st.query_params.clear()
    st.query_params["report"] = report_id


def open_upload():
    st.query_params.clear()
    st.query_params["view"] = "upload"


def back():
    st.query_params.clear()


def back_link():
    if st.button("← Back to library", key="tf::back", type="tertiary"):
        from tigerfish.ui import pages
        back()
        st.switch_page(pages.PAGES["library"])


def switcher(report_id):
    """Report picker on a report page (jump between reports without going back)."""
    items = entries()
    titles = {e["title"]: e["id"] for e in items}
    now = next((t for t, i in titles.items() if i == report_id), None)
    if now is None:
        return

    def change():
        open_report(titles[st.session_state["tf::switch"]])

    st.selectbox("Report", list(titles), index=list(titles).index(now), key="tf::switch",
                 on_change=change, label_visibility="collapsed")


# ---------- the library ----------

def grade_line(g):
    parts = [f"{badge(k)} {g[k]}" for k in ("RED", "ORANGE", "INFO")]
    return " &nbsp; ".join(parts)


def meta_line(e):
    pages = ("1 table" if e["unit"] == "table"
             else f"{e['pages']:,} of {e['pages_total']:,} pages" if e["pages_total"] != e["pages"]
             else f"{e['pages']:,} pages")
    bits = [e.get("state") or "state not recorded", e.get("sector") or "sector not recorded",
            str(e.get("year") or "year not recorded"), pages]
    return " · ".join(esc(b) for b in bits)


def row(e):
    with st.container(border=True):
        left, right = st.columns([5, 1])
        kind = "tf-lib-quick" if e["audit_type"] == library.QUICK else "tf-lib-full"
        reviewed = (f'<div class="tf-lib-meta">human-reviewed: {e["reviewed"][0]} of '
                    f'{e["reviewed"][1]} flags</div>' if e.get("reviewed") else "")
        left.markdown(
            f'<div class="tf-lib-title">{esc(e["project"])}</div>'
            f'<div class="tf-lib-meta"><span class="tf-lib-type {kind}">{esc(e["audit_type"])}</span> '
            f'{meta_line(e)}</div>'
            f'<div class="tf-lib-grades">{grade_line(e["grades"])}</div>{reviewed}',
            unsafe_allow_html=True)
        right.button("Open", key=f"tf::open::{e['id']}", on_click=open_report, args=(e["id"],),
                     width="stretch")


CSS = """<style>
.tf-lib-total { font-size: 1.05rem; font-weight: 600; margin: 0.2rem 0 0.6rem 0; }
.tf-lib-title { font-size: 1.02rem; font-weight: 650; }
.tf-lib-meta { font-size: 0.85rem; color: #5B6B73; margin-top: 0.15rem; }
.tf-lib-grades { margin-top: 0.3rem; font-size: 0.85rem; }
.tf-lib-type { display: inline-block; font-size: 0.7rem; font-weight: 700; padding: 0.05rem 0.4rem;
  border-radius: 4px; margin-right: 0.3rem; }
.tf-lib-full { color: #1F5F5F; background: #EAF2F2; }
.tf-lib-quick { color: #6B5200; background: #FFF4DE; }
</style>"""


def render():
    st.markdown(CSS, unsafe_allow_html=True)
    items = entries()
    t = library.totals(items)
    st.markdown(f'<div class="tf-lib-total">{esc(library.totals_line(t))}</div>',
                unsafe_allow_html=True)
    st.caption(f"{t['full']} full audit{'s' if t['full'] != 1 else ''}, {t['quick']} quick "
               f"check{'s' if t['quick'] != 1 else ''}. Totals are computed from the saved results. "
               "A flag is a lead to verify against the report, not a verdict.")
    up, note = st.columns([1, 3])
    up.button("Upload your own EIA", key="tf::upload", type="primary", on_click=open_upload,
              width="stretch")
    note.caption(UPLOAD_NOTE)

    st.write("")
    query = st.text_input("Search by project name", key="lib::q", placeholder="e.g. port, Karnataka")
    c1, c2, c3, c4, c5 = st.columns([2, 2, 1.2, 1.6, 1.2])
    states = c1.multiselect("State", library.options(items, "state"), key="lib::state")
    sectors = c2.multiselect("Sector", library.options(items, "sector"), key="lib::sector")
    years = c3.multiselect("Year", library.options(items, "year"), key="lib::year")
    types = c4.multiselect("Audit type", [library.FULL, library.QUICK], key="lib::type")
    c5.write("")
    red = c5.checkbox("Has RED flags", key="lib::red")
    shown = library.filter_entries(items, query, states, sectors, years, types, red)
    st.caption(f"Showing {len(shown)} of {len(items)} reports.")
    if not shown:
        st.info("No reports match these filters.")
        return
    pages = max(1, -(-len(shown) // PAGE_SIZE))
    page = 1
    if pages > 1:
        page = st.number_input(f"Page (of {pages})", 1, pages, 1, key="lib::page")
    for e in shown[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]:
        row(e)

