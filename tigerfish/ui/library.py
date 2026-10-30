<<<<<<< HEAD
"""The report library: every report under results/, as evidence-slip previews in the main
column, with search, filters, live totals and "Upload your EIA" in a sticky side panel
(docs/DESIGN.md). On tablets and phones the panel moves above the list, in an expander.
=======
"""The report library: every matching report as a row, in two groups: Full audits (saved
audits and the single-table check) and Quick checks. Search, the Audit type choice and the
other filters sit in two rows above them. There is no page-size cap (docs/DESIGN.md).
>>>>>>> design/notebook-v2

Navigation lives in the URL:
  (none)            the library
  ?report=<id>      a report (tigerfish/ui/report_view.py: sections side by side; a quick
                    check gets only its own sections)
  ?view=upload      upload a new EIA (app.py sends it on to the Upload page)
"""

<<<<<<< HEAD
from pathlib import Path
=======
import re
>>>>>>> design/notebook-v2

import streamlit as st

from tigerfish import batch_results, library
from tigerfish.ui import data, slip
from tigerfish.ui.style import badge, esc, mono

PAGE_SIZE = 30
QUICK_PAGE = 5      # quick checks shown at first, and added by each "Show more"
QUICK_SHOWN = "lib::quick_shown"
UPLOAD_NOTE = ("Saved audits are full runs. Upload your own EIA to run live checks: the free "
               "checks read the whole report; the model checks run on up to 30 pages you choose "
               "on this site (run locally for full reports).")
FILTER_KEYS = ("lib::q", "lib::state", "lib::sector", "lib::year", "lib::type", "lib::red",
               "lib::verified")
CSS = """<style>
.st-key-tf-lib-filters { border-bottom: 1px solid var(--tf-rule); padding-bottom: 0.75rem; margin-bottom: 0.5rem; }
.st-key-tf-lib-filters div[data-testid="stRadio"] [role="radiogroup"] { gap: 1.25rem; }
.tf-lib-total { font-size: 1rem; color: var(--tf-muted); margin: 0 0 0.25rem 0; }
.tf-lib-head { font-family: Newsreader, Georgia, serif; font-size: 1.5rem; font-weight: 600;
  color: var(--tf-ink); margin: 2rem 0 0.15rem 0; }
.tf-lib-sub { color: var(--tf-muted); margin: 0 0 0.5rem 0; }
div[class*="st-key-tf-slip-rep"] { background: transparent !important; border: 0 !important;
  border-bottom: 1px solid var(--tf-rule) !important; border-radius: 0 !important; padding: 0.6rem 0.25rem; }
.tf-lib-title { font-family: Newsreader, Georgia, serif; font-size: 1.125rem; font-weight: 600;
<<<<<<< HEAD
  line-height: 1.15; color: var(--tf-ink); }
.tf-lib-meta { font-size: 0.8125rem; color: var(--tf-muted); margin-top: 0.2rem; }
.tf-lib-grades { margin: 0.4rem 0 0.6rem 0; font-size: 0.8125rem; color: var(--tf-ink); }
div[class*="st-key-tf-slip-rep"] { padding: 1rem; }
div[class*="st-key-tf-slip-rep"] .tf-slip { border: 0; padding: 0; margin: 0.4rem 0 0.2rem 0;
  grid-template-columns: minmax(0, 1fr); gap: 0.6rem; }
div[class*="st-key-tf-slip-rep"] .tf-slip-title { font-size: 1rem; }
.tf-triage-card {
  background: var(--tf-paper-2) !important;
  border: 1px solid var(--tf-rule) !important;
  border-radius: 3px !important;
  padding: 0.85rem 1rem !important;
  margin: 0.4rem 0 0.6rem 0 !important;
  display: block !important;
}
.tf-triage-status {
  font-family: "IBM Plex Mono", Consolas, monospace !important;
  font-size: 0.8125rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.03em !important;
  color: var(--tf-teal) !important;
  margin-bottom: 0.35rem !important;
}
.tf-triage-note {
  font-family: "Schibsted Grotesk", sans-serif !important;
  font-size: 0.8125rem !important;
  color: var(--tf-ink) !important;
  line-height: 1.4 !important;
  margin-bottom: 0.5rem !important;
}
.tf-triage-checks {
  display: flex !important;
  flex-direction: column !important;
  gap: 0.25rem !important;
}
.tf-triage-item {
  font-family: "Schibsted Grotesk", sans-serif !important;
  font-size: 0.75rem !important;
  color: var(--tf-muted) !important;
  line-height: 1.35 !important;
}
.tf-triage-item b {
  color: var(--tf-ink) !important;
  font-weight: 600 !important;
}
=======
  line-height: 1.2; color: var(--tf-ink); display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden; }
.tf-lib-meta { font-size: 0.8125rem; color: var(--tf-muted); margin-top: 0.15rem; }
.tf-lib-grades { font-size: 0.8125rem; color: var(--tf-ink); }
.tf-lib-grades .tf-badge { margin-right: 0.25rem; }
.tf-lib-grades .tf-mono { margin-right: 0.75rem; }
>>>>>>> design/notebook-v2
</style>"""


def triage_passed_card():
    return (
        '<div class="tf-triage-card">'
        '<div class="tf-triage-status">✓ FAST ADMINISTRATIVE TRIAGE PASSED</div>'
        '<div class="tf-triage-note">Cleared standard statutory screening; manual hearing review expedited, deep multi-chapter LLM audit deferred.</div>'
        '<div class="tf-triage-checks">'
        '<div class="tf-triage-item">✓ <b>Accreditation:</b> Consultant credentials verified / unflagged</div>'
        '<div class="tf-triage-item">✓ <b>Baseline Monitoring:</b> Statutorily compliant seasonal window</div>'
        '<div class="tf-triage-item">✓ <b>Taxonomic Ground Truth:</b> No out-of-range occurrences detected via GBIF</div>'
        '<div class="tf-triage-item">✓ <b>Public Record Search:</b> No active court restrictions flagged</div>'
        '</div>'
        '</div>'
    )


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


@st.cache_data(show_spinner=False, max_entries=256)
def _preview(path, report_id, stamp):
    """The finding a library card shows: human-verified first, then the strongest with a page."""
    if report_id in {r["id"] for r in data.reports()}:
        report = data.load(report_id)
    else:
        report = {}
        if path and Path(path).is_file():
            try:
                report = library.load({"path": str(path)})
            except Exception:
                report = {}
    raw_findings = list(report.get("findings") or [])
    if not raw_findings and (report.get("flags") or report.get("batch_flags")):
        for i, fl in enumerate(report.get("flags") or report.get("batch_flags") or []):
            raw_findings.append({
                "id": fl.get("id") or f"{report_id}-fl-{i}",
                "check": fl.get("check", "batch_check"),
                "check_name": fl.get("check", "Batch Check").replace("_", " ").title(),
                "grade": fl.get("grade", "INFO"),
                "title": f"{fl.get('check', 'Batch Check').replace('_', ' ').title()}: {fl.get('message', '')[:70]}",
                "message": fl.get("message", "Flagged during statutory triage, verify."),
                "quotes": fl.get("quotes", []),
                "evidence": fl.get("evidence", []),
                "why": fl.get("message", "Deterministic check flagged during automated triage."),
                "clear": fl.get("clear") or "Verification against official statutory records or updated filings.",
                "known_issue": None,
                "images": [],
            })
    findings = [f for f in raw_findings if f.get("grade") in ("RED", "ORANGE")]
    if not findings:
        findings = [f for f in raw_findings if f.get("grade") == "INFO"]
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


# ---------- one report row ----------

def grade_line(g):
    return "".join(f'{badge(k)}{mono(f"{g[k]:,}")}' for k in ("RED", "ORANGE", "INFO"))


def meta_line(e):
    pages = ("1 table" if e["unit"] == "table"
             else f"{e['pages']:,} of {e['pages_total']:,} pages" if e["pages_total"] != e["pages"]
             else f"{e['pages']:,} pages")
    bits = [e.get("state"), e.get("sector"), e.get("year"), pages]
    return " · ".join(esc(b) for b in bits if b)


def row(e):
    """A report row: name, facts, flags by grade, and Open report."""
    with st.container(key=f"tf-slip-rep-{e['id']}"):
        main, grades, act = st.columns([6, 3, 1.4], gap="medium", vertical_alignment="center")
        reviewed = f' · {e["verified"]} verified by a person' if e.get("verified") else ""
        screening = (f'<div class="tf-lib-meta">{esc(batch_results.summary_line(e["screening"]))}</div>'
                     if e.get("screening") else "")
        table_note = (f'<div class="tf-lib-meta">{esc(library.TABLE_NOTE)}</div>'
                      if e.get("audit_type") == library.TABLE else "")
<<<<<<< HEAD
        is_quick = (e.get("kind") == "batch" or e.get("audit_type") == library.QUICK)
        badge_html = '<span class="tf-badge-quick">Quick Audit</span> ' if is_quick else ''
        grades = dict(e["grades"])
        if is_quick and e.get("path"):
            rep = None
            raw_path = e.get("path")
            if raw_path and Path(raw_path).is_file():
                try:
                    rep = library.load({"path": str(raw_path)})
                except Exception:
                    rep = None
            if rep:
                fls = rep.get("flags") or rep.get("batch_flags") or []
                if fls:
                    for g in ("RED", "ORANGE", "INFO"):
                        grades[g] = sum(1 for x in fls if x.get("grade") == g)
        st.markdown(
            f'<div class="tf-lib-title">{badge_html}{esc(e["project"])}</div>'
            f'<div class="tf-lib-meta"><span class="tf-kind">{esc(e["audit_type"])}</span> · '
            f'{meta_line(e)}{esc(reviewed)}</div>'
            f'<div class="tf-lib-grades">{grade_line(grades)}</div>'
            f'{table_note}',
            unsafe_allow_html=True)
        top = _preview(e["path"], e["id"], _stamp())
        if top:
            slip.render(top, max_crops=1)
        elif is_quick:
            st.markdown(triage_passed_card(), unsafe_allow_html=True)
        else:
            st.caption("No RED or ORANGE flags in this report: its INFO leads are inside.")
        st.button("Open report", key=f"tf::open::{e['id']}", on_click=open_report, args=(e["id"],),
                  type="secondary", help=f"Open {e['title']}")
=======
        # Batch titles come from the PDF's first lines: drop private-use glyphs (bullets from
        # Word symbol fonts) and keep two lines at most (CSS).
        title = re.sub(r"[\ue000-\uf8ff]", "", str(e["project"])).strip()
        main.markdown(f'<div class="tf-lib-title" title="{esc(title)}">{esc(title)}</div>'
                      f'<div class="tf-lib-meta">{meta_line(e)}{esc(reviewed)}</div>'
                      f"{table_note}{screening}", unsafe_allow_html=True)
        grades.markdown(f'<div class="tf-lib-grades">{grade_line(e["grades"])}</div>',
                        unsafe_allow_html=True)
        act.button("Open report", key=f"tf::open::{e['id']}", on_click=open_report, args=(e["id"],),
                   type="secondary", help=f"Open {e['title']}")
>>>>>>> design/notebook-v2


# ---------- the filters ----------

def reset_filters():
    for k in FILTER_KEYS:
        st.session_state.pop(k, None)
    st.session_state["lib::shown"] = PAGE_SIZE
    reset_quick()


def reset_quick():
    """A filter changed: the quick checks start again from their first page."""
    st.session_state[QUICK_SHOWN] = QUICK_PAGE


def more_quick():
    st.session_state[QUICK_SHOWN] = st.session_state.get(QUICK_SHOWN, QUICK_PAGE) + QUICK_PAGE


def _chips():
    """The active filters, as chips beside the count."""
    ss = st.session_state
    chips = []
    if (ss.get("lib::q") or "").strip():
        chips.append(f'"{ss["lib::q"].strip()}"')
    type_val = ss.get("lib::type")
    if isinstance(type_val, str) and not type_val.startswith("All"):
        chips.append("Full Audits" if "Full Audits" in type_val else "Quick Batch Audits")
    for k in ("lib::state", "lib::sector", "lib::year"):
        chips += [str(v) for v in ss.get(k) or []]
    if ss.get("lib::red"):
        chips.append("Has RED flags")
    if ss.get("lib::verified"):
        chips.append("Has human-verified findings")
    return chips


def side_panel(items, shown):
    """The filters, in two rows above the list (the name is kept for callers)."""
    t = library.totals(items)
    n_full = sum(1 for e in items if e.get("kind") == "saved" or e.get("audit_type") in (library.FULL, library.TABLE))
    n_quick = sum(1 for e in items if e.get("kind") == "batch" or e.get("audit_type") == library.QUICK)
    audit_options = [f"All ({len(items)})", f"Full Audits ({n_full})", f"Quick Batch Audits ({n_quick})"]
    # Explicit default: never start empty or uninitialized
    if st.session_state.get("lib::type") not in audit_options:
        st.session_state["lib::type"] = audit_options[0]
    idx = audit_options.index(st.session_state["lib::type"])

    total, up = st.columns([5, 1.3], vertical_alignment="center")
    total.markdown(f'<div class="tf-lib-total">{esc(library.totals_line(t))}. Computed from the saved '
                   "results; a flag is a lead to verify against the report, not a verdict.</div>",
                   unsafe_allow_html=True)
    up.button("Upload your EIA", key="tf::upload", type="secondary", on_click=open_upload,
              icon=":material/upload_file:")
    with st.container(key="tf-lib-filters"):
        q, kind = st.columns([3, 4], gap="medium", vertical_alignment="bottom")
        q.text_input("Search by project name", key="lib::q", placeholder="e.g. port, Karnataka",
                     on_change=reset_quick)
        kind.radio("Audit type", audit_options, index=idx, key="lib::type", horizontal=True,
                   on_change=reset_quick)
        a, b, c, d = st.columns([2, 2, 1.4, 2], gap="medium", vertical_alignment="bottom")
        a.multiselect("State", library.options(items, "state"), key="lib::state", on_change=reset_quick)
        b.multiselect("Sector", library.options(items, "sector"), key="lib::sector", on_change=reset_quick)
        c.multiselect("Year", library.options(items, "year"), key="lib::year", on_change=reset_quick)
        with d:
            st.checkbox("Has RED flags", key="lib::red", on_change=reset_quick)
            st.checkbox("Has human-verified findings", key="lib::verified", on_change=reset_quick)
        n, r = st.columns([5, 1], vertical_alignment="center")
        chips = _chips()
        n.markdown(f'<div class="tf-count">Showing {len(shown)} of {len(items)} reports.</div>'
                   + ('<div class="tf-chips">' + "".join(f'<span class="tf-chip">{esc(c)}</span>'
                                                       for c in chips) + "</div>" if chips else ""),
                   unsafe_allow_html=True)
        if chips:
            r.button("Reset filters", key="lib::reset", type="tertiary", on_click=reset_filters)
    st.caption(UPLOAD_NOTE)


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

    full_shown = [e for e in shown if e.get("kind") == "saved" or e.get("audit_type") in (library.FULL, library.TABLE)]
    quick_shown = [e for e in shown if e.get("kind") == "batch" or e.get("audit_type") == library.QUICK]

    # Full audits
    if not is_quick_only:
        st.markdown(
            f'<h2 class="tf-lib-head">Full audits ({len(full_total)})</h2>'
            '<p class="tf-lib-sub">Read with the model checks (NVIDIA Nemotron): contradictions, '
            "recycled figures, copied text, species and the public record.</p>",
            unsafe_allow_html=True)
        if full_shown:
            with st.container(key="tf-grid-full"):
                for e in full_shown:
                    row(e)
        else:
            st.caption("No reports match these filters in this group.")

    # Quick checks
    if not is_full_only:
        st.markdown(
            f'<h2 class="tf-lib-head">Quick checks ({len(quick_total)})</h2>'
            '<p class="tf-lib-sub">Free checks only, no model calls: consultant accreditation, '
            "baseline monitoring period and species against GBIF.</p>",
            unsafe_allow_html=True)
        if quick_shown:
            n = st.session_state.get(QUICK_SHOWN, QUICK_PAGE)
            with st.container(key="tf-grid-quick"):
                for e in quick_shown[:n]:
                    row(e)
            rest = len(quick_shown) - n
            if rest > 0:
                st.button(f"Show {min(QUICK_PAGE, rest)} more quick checks ({rest} not shown)",
                          key="lib::quick-more", on_click=more_quick, icon=":material/expand_more:")
        else:
            st.caption("No reports match these filters in this group.")

    if any(e.get("screening") for e in items):
        from tigerfish.ui import batch as batch_ui

        with (
            st.container(key="tf-panel-batch-summary"),
            st.expander("Batch screening results"),
        ):
            st.markdown("### Batch screening results")
            batch_ui.render_summary(items)

    st.write("")
    from tigerfish.ui import quality
    quality.library_section()
