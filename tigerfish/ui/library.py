"""The report library: all matching evidence-slip previews in two full-width binders.
Search, the Audit type radio and other filters sit in a plain container above them.
Deep Investigation Audits contains saved audits/table; Automated Batch Triage contains
quick checks. There is no active page-size cap (docs/DESIGN.md).

Navigation lives in the URL:
  (none)            the library
  ?report=<id>      a report (tigerfish/ui/report_view.py: sections side by side; a quick
                    check gets only its own sections)
  ?view=upload      upload a new EIA (app.py sends it on to the Upload page)
"""

import streamlit as st

from tigerfish import batch_results, library
from tigerfish.ui import data, slip
from tigerfish.ui.style import badge, esc, mono

PAGE_SIZE = 30
UPLOAD_NOTE = ("Saved audits are full runs. Upload your own EIA to run live checks: the free "
               "checks read the whole report; the model checks run on up to 30 pages you choose "
               "on this site (run locally for full reports).")
FILTER_KEYS = ("lib::q", "lib::state", "lib::sector", "lib::year", "lib::type", "lib::red",
               "lib::verified")
CSS = """<style>
/* report slips: two per row above 1400px, one below */
@media (min-width: 1400px) {
  .st-key-tf-grid, div[class*="st-key-tf-grid-"] { display: grid !important;
    grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; align-items: start; }
}
/* below 1100px the side panel goes above the list, full width */
@media (max-width: 1099px) {
  .st-key-tf-lib-layout [data-testid="stHorizontalBlock"] { flex-direction: column-reverse !important; }
  .st-key-tf-lib-layout [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
}
/* side panel is a clean container */
.st-key-tf-side-lib {
  background: var(--tf-paper) !important;
  border: 1px solid var(--tf-rule) !important;
  border-radius: 3px !important;
  padding: 1.25rem 1.5rem !important;
  margin-bottom: 1.5rem !important;
  pointer-events: auto !important;
  position: relative;
  z-index: 2;
}
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"],
div[data-testid="stMultiSelect"],
div[data-testid="stCheckbox"],
div[data-testid="stRadio"],
div[data-testid="stExpanderDetails"] * {
  pointer-events: auto !important;
}
.st-key-tf-side-lib input, .st-key-tf-side-lib [data-baseweb="select"], .st-key-tf-side-lib [data-testid="stCheckbox"], .st-key-tf-side-lib button {
  pointer-events: auto !important; cursor: pointer;
}
.st-key-tf-side-lib input[type="text"] { cursor: text; }
.st-key-tf-side-lib div[data-testid="stRadio"] {
  background: var(--tf-paper-2);
  border: 1px solid var(--tf-rule);
  border-radius: 3px;
  padding: 0.6rem 0.8rem;
  margin-bottom: 0.75rem;
  pointer-events: auto !important;
}
.st-key-tf-side-lib div[data-testid="stRadio"] [role="radiogroup"] {
  gap: 0.35rem;
}
.st-key-tf-side-lib div[data-testid="stRadio"] label {
  font-family: "Schibsted Grotesk", sans-serif !important;
  color: var(--tf-ink) !important;
  font-size: 0.8125rem !important;
  cursor: pointer !important;
  pointer-events: auto !important;
}
.st-key-tf-side-lib div[data-testid="stRadio"] [data-testid="stWidgetLabel"] p {
  font-family: "Schibsted Grotesk", sans-serif !important;
  font-size: 0.8125rem !important;
  font-weight: 600 !important;
  color: var(--tf-ink) !important;
  margin-bottom: 0.25rem !important;
}

.tf-sec-header {
  background: var(--tf-paper) !important;
  border: 1px solid var(--tf-rule) !important;
  border-radius: 3px !important;
  padding: 1.25rem 1.5rem !important;
  margin: 0 0 1rem 0 !important;
  display: block !important;
  width: 100% !important;
  box-sizing: border-box !important;
}
.tf-sec-title {
  font-family: Newsreader, Georgia, serif !important;
  font-size: 1.5rem !important;
  font-weight: 600 !important;
  color: var(--tf-teal) !important;
  line-height: 1.2 !important;
  margin: 0 0 0.35rem 0 !important;
}
.tf-sec-sub {
  font-family: "Schibsted Grotesk", sans-serif !important;
  font-size: 0.9375rem !important;
  color: var(--tf-muted) !important;
  line-height: 1.4 !important;
  margin: 0 !important;
}
.tf-sec-rule {
  border: 0 !important;
  border-top: 1px solid var(--tf-rule) !important;
  margin: 2rem 0 !important;
  width: 100% !important;
}
.tf-sec-empty-box {
  background: var(--tf-paper) !important;
  border: 1px solid var(--tf-rule) !important;
  border-radius: 3px !important;
  padding: 1rem 1.25rem !important;
  margin: 0 0 1rem 0 !important;
}
.tf-sec-empty {
  font-family: "Schibsted Grotesk", sans-serif !important;
  font-size: 0.875rem !important;
  color: var(--tf-muted) !important;
  margin: 0 !important;
}
.tf-badge-quick {
  font-family: "IBM Plex Mono", Consolas, monospace;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--tf-teal);
  background: var(--tf-paper-2);
  border: 1px solid var(--tf-teal);
  border-radius: 2px;
  padding: 0.1rem 0.4rem;
  margin-right: 0.45rem;
  display: inline-block;
}
.tf-lib-total { font-size: 1rem; color: var(--tf-ink); margin: 0.6rem 0 0.2rem 0; }
.tf-lib-title { font-family: Newsreader, Georgia, serif; font-size: 1.125rem; font-weight: 600;
  line-height: 1.15; color: var(--tf-ink); }
.tf-lib-meta { font-size: 0.8125rem; color: var(--tf-muted); margin-top: 0.2rem; }
.tf-lib-grades { margin: 0.4rem 0 0.6rem 0; font-size: 0.8125rem; color: var(--tf-ink); }
div[class*="st-key-tf-slip-rep"] { padding: 1rem; }
div[class*="st-key-tf-slip-rep"] .tf-slip { border: 0; padding: 0; margin: 0.4rem 0 0.2rem 0;
  grid-template-columns: minmax(0, 1fr); gap: 0.6rem; }
div[class*="st-key-tf-slip-rep"] .tf-slip-title { font-size: 1rem; }
</style>"""


def _stamp():
    """Changes when any library file changes, so the cached list refreshes."""
    files = [
        library.RESULTS / "index.json",
        library.RESULTS / "library.json",
        library.batch_dir() / "index.json",
        library.batch_dir() / "batch_summary.json",
    ]
    return tuple((str(f), f.stat().st_mtime) if f.exists() else (str(f), 0) for f in files)


@st.cache_data(show_spinner=False)
def _entries(stamp):
    return library.entries()


def entries():
    return _entries(_stamp())


@st.cache_data(show_spinner=False, max_entries=256)
def _preview(path, report_id, stamp):
    """The finding a library card shows: human-verified first, then the strongest with a page."""
    if report_id in {r["id"] for r in data.reports()}:
        report = data.load(report_id)
    else:
        report = library.load({"path": path})
    findings = [f for f in report.get("findings") or [] if f.get("grade") in ("RED", "ORANGE")]
    top = slip.pick(findings, 1)
    return top[0] if top else None


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
    if st.button("Back to library", key="tf::back", type="tertiary",
                 icon=":material/arrow_back:"):
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


# ---------- one report card ----------


def grade_line(g):
    return " ".join(f'{badge(k)}{mono(f"{g[k]:,}")}&nbsp;&nbsp;' for k in ("RED", "ORANGE", "INFO"))


def meta_line(e):
    pages = ("1 table" if e["unit"] == "table"
             else f"{e['pages']:,} of {e['pages_total']:,} pages" if e["pages_total"] != e["pages"]
             else f"{e['pages']:,} pages")
    bits = [e.get("state") or "state not recorded", e.get("sector") or "sector not recorded",
            str(e.get("year") or "year not recorded"), pages]
    return " · ".join(esc(b) for b in bits)


def row(e):
    """A report card: title, facts, grade counts, and a slip of its strongest finding."""
    with st.container(key=f"tf-slip-rep-{e['id']}"):
        reviewed = (f' · {e["verified"]} verified by a person' if e.get("verified") else "")
        table_note = (f'<div class="tf-lib-meta">{esc(library.TABLE_NOTE)}</div>'
                      if e.get("audit_type") == library.TABLE else "")
        is_quick = (e.get("kind") == "batch" or e.get("audit_type") == library.QUICK)
        badge_html = '<span class="tf-badge-quick">Quick Audit</span> ' if is_quick else ''
        st.markdown(
            f'<div class="tf-lib-title">{badge_html}{esc(e["project"])}</div>'
            f'<div class="tf-lib-meta"><span class="tf-kind">{esc(e["audit_type"])}</span> · '
            f'{meta_line(e)}{esc(reviewed)}</div>'
            f'<div class="tf-lib-grades">{grade_line(e["grades"])}</div>'
            f'{table_note}',
            unsafe_allow_html=True)
        top = _preview(e["path"], e["id"], _stamp())
        if top:
            slip.render(top, max_crops=1)
        if e.get("screening"):
            st.caption(batch_results.summary_line(e["screening"]))
            st.caption(
                "Open Batch screening for check outcomes, uncertainties and source quotations."
            )
        elif not top:
            st.caption("No RED or ORANGE flags in this report: its INFO leads are inside.")
        st.button("Open report", key=f"tf::open::{e['id']}", on_click=open_report, args=(e["id"],),
                  type="secondary", help=f"Open {e['title']}")


# ---------- the side panel ----------


def reset_filters():
    for k in FILTER_KEYS:
        st.session_state.pop(k, None)
    st.session_state["lib::shown"] = PAGE_SIZE


def _chips():
    ss = st.session_state
    chips = []
    if (ss.get("lib::q") or "").strip():
        chips.append(f'"{ss["lib::q"].strip()}"')
    type_val = ss.get("lib::type")
    if type_val and isinstance(type_val, str) and not type_val.startswith("All"):
        if "Full Audits" in type_val:
            chips.append("Full Audits")
        elif "Quick Batch Audits" in type_val or "Quick" in type_val:
            chips.append("Quick Batch Audits")
    for k in ("lib::state", "lib::sector", "lib::year"):
        chips += [str(v) for v in ss.get(k) or []]
    if ss.get("lib::red"):
        chips.append("Has RED flags")
    if ss.get("lib::verified"):
        chips.append("Has human-verified findings")
    return chips


def side_panel(items, shown):
    t = library.totals(items)
    n_full = sum(1 for e in items if e.get("kind") == "saved" or e.get("audit_type") in (library.FULL, library.TABLE))
    n_quick = sum(1 for e in items if e.get("kind") == "batch" or e.get("audit_type") == library.QUICK)
    opt_all = f"All ({len(items)})"
    opt_full = f"Full Audits ({n_full})"
    opt_quick = f"Quick Batch Audits ({n_quick})"
    audit_options = [opt_all, opt_full, opt_quick]

    # Explicit default: never start empty or uninitialized
    if "lib::type" not in st.session_state or not isinstance(st.session_state["lib::type"], str) or st.session_state["lib::type"] not in audit_options:
        st.session_state["lib::type"] = opt_all

    idx = audit_options.index(st.session_state["lib::type"])

    with st.container(key="tf-side-lib"):
        st.markdown('<div class="tf-h3">Find a report</div>', unsafe_allow_html=True)
        st.text_input("Search by project name", key="lib::q", placeholder="e.g. port, Karnataka")
        st.radio("Audit type", audit_options, index=idx, key="lib::type")
        st.multiselect("State", library.options(items, "state"), key="lib::state")
        st.multiselect("Sector", library.options(items, "sector"), key="lib::sector")
        st.multiselect("Year", library.options(items, "year"), key="lib::year")
        st.checkbox("Has RED flags", key="lib::red")
        st.checkbox("Has human-verified findings", key="lib::verified")
        chips = _chips()
        if chips:
            st.markdown('<div class="tf-chips">' + "".join(
                f'<span class="tf-chip">{esc(c)}</span>' for c in chips) + "</div>",
                unsafe_allow_html=True)
            st.button("Reset filters", key="lib::reset", type="tertiary", on_click=reset_filters)
        st.markdown(f'<div class="tf-count">Showing {len(shown)} of {len(items)} reports.</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="tf-lib-total">{esc(library.totals_line(t))}</div>',
                    unsafe_allow_html=True)
        st.caption(f"{t['full']} full audit{'s' if t['full'] != 1 else ''}, {t['quick']} quick "
                   f"check{'s' if t['quick'] != 1 else ''}. Computed from the saved results. A flag "
                   "is a lead to verify against the report, not a verdict.")
        st.button("Upload your EIA", key="tf::upload", type="primary", on_click=open_upload,
                  width="stretch")
        st.caption(UPLOAD_NOTE)
        screening = batch_results.totals(items)
        if screening["reports"]:
            st.caption(
                f"Batch screening: {screening['observations']} additional observations and "
                f"{screening['undetermined']} undetermined check results, separate from audit findings."
            )


# ---------- the library ----------


def _filtered(items):
    ss = st.session_state
    audit_choice = ss.get("lib::type", "")
    audit_types = ()
    if isinstance(audit_choice, str):
        if "Full Audits" in audit_choice or audit_choice == library.FULL:
            audit_types = (library.FULL, library.TABLE)
        elif "Quick Batch Audits" in audit_choice or audit_choice == library.QUICK:
            audit_types = (library.QUICK,)
    elif isinstance(audit_choice, (list, tuple, set)):
        if library.FULL in audit_choice and library.QUICK not in audit_choice:
            audit_types = (library.FULL, library.TABLE)
        elif library.QUICK in audit_choice and library.FULL not in audit_choice:
            audit_types = (library.QUICK,)
        else:
            audit_types = tuple(audit_choice)

    return library.filter_entries(items, ss.get("lib::q", ""), ss.get("lib::state") or (),
                                  ss.get("lib::sector") or (), ss.get("lib::year") or (),
                                  audit_types, bool(ss.get("lib::red")),
                                  bool(ss.get("lib::verified")))


def show_more():
    st.session_state["lib::shown"] = st.session_state.get("lib::shown", PAGE_SIZE) + PAGE_SIZE


def render():
    st.markdown(CSS, unsafe_allow_html=True)
    items = entries()
    if not items:
        with st.container(key="tf-panel-lib-empty"):
            st.markdown('<div class="tf-h2">The library is empty</div>', unsafe_allow_html=True)
            st.markdown("No saved reports were found in `results/` (results/index.json is missing "
                        "or lists no reports). Run `scripts/export_results.py` after an audit, or "
                        "upload an EIA to run the free checks now.")
            st.button("Upload your EIA", key="tf::upload", type="primary", on_click=open_upload)
        return
    shown = _filtered(items)
    side_panel(items, shown)

    if not shown:
        with st.container(key="tf-panel-lib-none"):
            st.markdown('<div class="tf-h3">No reports match these filters</div>',
                        unsafe_allow_html=True)
            st.markdown(f"None of the {len(items)} reports matches every filter you chose. "
                        "Remove a filter, or reset them all.")
            st.button("Reset filters", key="lib::reset-empty", on_click=reset_filters)
        st.write("")
        from tigerfish.ui import quality
        quality.library_section()
        return

    audit_choice = st.session_state.get("lib::type", "")
    is_full_only = isinstance(audit_choice, str) and "Full Audits" in audit_choice
    is_quick_only = isinstance(audit_choice, str) and ("Quick Batch Audits" in audit_choice or audit_choice == library.QUICK)

    full_total = [e for e in items if e.get("kind") == "saved" or e.get("audit_type") in (library.FULL, library.TABLE)]
    quick_total = [e for e in items if e.get("kind") == "batch" or e.get("audit_type") == library.QUICK]

    limit = st.session_state.get("lib::shown", PAGE_SIZE)
    to_show = shown[:limit]

    full_shown = [e for e in to_show if e.get("kind") == "saved" or e.get("audit_type") in (library.FULL, library.TABLE)]
    quick_shown = [e for e in to_show if e.get("kind") == "batch" or e.get("audit_type") == library.QUICK]

    # Section A: Deep Investigation Audits
    if not is_quick_only:
        st.markdown(
            '<div class="tf-sec-header">'
            f'<h2 class="tf-h2 tf-sec-title">Deep Investigation Audits ({len(full_total)} Benchmark Reports)</h2>'
            '<p class="tf-sec-sub">Multi-chapter contradiction analysis, cross-document text overlap, GBIF species checks, and NVIDIA Nemotron LLM validation.</p>'
            '</div>',
            unsafe_allow_html=True)
        if full_shown:
            with st.container(key="tf-grid-full"):
                for e in full_shown:
                    row(e)
        else:
            st.markdown('<div class="tf-sec-empty-box"><p class="tf-sec-empty">No reports match these filters in this category.</p></div>',
                        unsafe_allow_html=True)

    # Divider: Clean visual hairline separator (when both sections are shown)
    if not is_full_only and not is_quick_only:
        st.markdown('<hr class="tf-sec-rule">', unsafe_allow_html=True)

    # Section B: Automated Batch Triage
    if not is_full_only:
        st.markdown(
            '<div class="tf-sec-header">'
            f'<h2 class="tf-h2 tf-sec-title">Automated Batch Triage ({len(quick_total)} State Pollution Board Filings)</h2>'
            '<p class="tf-sec-sub">Zero-token automated checks: NABET accreditation validity, baseline monitoring duration, and GBIF species status.</p>'
            '</div>',
            unsafe_allow_html=True)
        if quick_shown:
            with st.container(key="tf-grid-quick"):
                for e in quick_shown:
                    row(e)
        else:
            st.markdown('<div class="tf-sec-empty-box"><p class="tf-sec-empty">No reports match these filters in this category.</p></div>',
                        unsafe_allow_html=True)

<<<<<<< HEAD
    if any(e.get("screening") for e in items):
        from tigerfish.ui import batch as batch_ui

        with (
            st.container(key="tf-panel-batch-summary"),
            st.expander("Batch screening results"),
        ):
            batch_ui.render_summary(items)
=======
    if len(shown) > len(to_show):
        st.button(f"Show more ({len(shown) - len(to_show)} remaining)", key="lib::more",
                  on_click=show_more)
>>>>>>> 3cb6ea9 (Synchronize UI pages, review queue, and batch triage ledger)

    st.write("")
    from tigerfish.ui import quality

    quality.library_section()
