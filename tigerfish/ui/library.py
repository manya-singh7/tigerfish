"""Home screen: the report library (every report under results/), live totals, filters,
and the "Upload your own EIA" button. Navigation lives in the URL:
  (none)            the library
  ?report=<id>      a report (full audit: the usual tabs; quick check: the lighter view)
  ?view=upload      upload a new EIA
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
    st.button("← Back to library", key="tf::back", on_click=back, type="tertiary")


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
        kind = {library.QUICK: "tf-lib-quick", library.TABLE: "tf-lib-table"}.get(e["audit_type"],
                                                                               "tf-lib-full")
        reviewed = (f'<div class="tf-lib-meta">human-reviewed: {e["reviewed"][0]} of '
                    f'{e["reviewed"][1]} flags</div>' if e.get("reviewed") else "")
        if e["audit_type"] == library.TABLE:
            reviewed = f'<div class="tf-lib-meta">{esc(library.TABLE_NOTE)}</div>' + reviewed
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
.tf-lib-table { color: #4A4A6A; background: #EEEEF6; }
</style>"""


def render():
    st.markdown(CSS, unsafe_allow_html=True)
    items = entries()
    t = library.totals(items)
    st.markdown(f'<div class="tf-lib-total">{esc(library.totals_line(t))}</div>',
                unsafe_allow_html=True)
    table = (f", {t['table']} single-table check{'s' if t['table'] != 1 else ''}"
             if t.get("table") else "")
    st.caption(f"{t['full']} full audit{'s' if t['full'] != 1 else ''}, {t['quick']} quick "
               f"check{'s' if t['quick'] != 1 else ''}{table}. Totals are computed from the saved results. "
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
    types = c4.multiselect("Audit type", [library.FULL, library.QUICK, library.TABLE], key="lib::type")
    c5.write("")
    red = c5.checkbox("Has RED flags", key="lib::red")
    shown = library.filter_entries(items, query, states, sectors, years, types, red)
    st.caption(f"Showing {len(shown)} of {len(items)} reports.")
    if not shown:
        st.info("No reports match these filters.")
    pages = max(1, -(-len(shown) // PAGE_SIZE))
    page = 1
    if pages > 1:
        page = st.number_input(f"Page (of {pages})", 1, pages, 1, key="lib::page")
    for e in shown[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]:
        row(e)

    st.write("")
    from tigerfish.ui import quality      # across all reports, from the saved review files
    quality.library_section()


# ---------- a quick check (lighter view) ----------

def render_quick(report):
    """Only the checks that ran, what did not run and why, and the findings."""
    from tigerfish.ui import cards
    st.markdown(f"### {esc(report.get('project') or report['title'])}")
    st.warning(library.QUICK_NOTICE)
    bits = [report.get("state"), report.get("sector"), report.get("year"),
            f"{report.get('pages_read', 0):,} of {report.get('pages_total', 0):,} pages read"]
    st.caption(" · ".join(str(b) for b in bits if b))
    ran = [c for c in report.get("checks_run", []) if c.get("status") == "ran"]
    not_run = [c for c in report.get("checks_run", []) if c.get("status") != "ran"]
    st.markdown("**Checks that ran** (free: no model calls)")
    for c in ran:
        n = c.get("count")
        st.markdown(f"- {esc(c['name'])}" + (f": {n} finding{'s' if n != 1 else ''}" if n is not None else ""))
    if not_run:
        st.markdown("**Not run for this report**")
        for c in not_run:
            st.markdown(f"- {esc(c['name'])}: {esc(c.get('reason') or 'not available')}")
    st.caption("Not run in a quick check: the model checks (internal contradictions, recycled "
               "figures, scanned pages), copied text, consultant accreditation, ToR promises.")
    findings = report.get("findings") or []
    if not findings:
        st.info("No RED, ORANGE or INFO findings from the checks that ran.")
    for f in findings:
        cards.finding_card(report["id"], f, report.get("title", ""))
