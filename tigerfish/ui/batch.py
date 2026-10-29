"""Replay-only batch screening: inspect every check, including undetermined results."""

import json
from datetime import date
from pathlib import Path

import streamlit as st

from tigerfish import batch_results, library
from tigerfish.ui import slip
from tigerfish.ui.style import badge, esc

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "results" / "batch" / "batch_summary.json"
NOTE = (
    "Batch screening uses text rules and saved GBIF responses, with no NVIDIA model calls. "
    "Certificate dates are not official NABET verification. A three-month baseline is a "
    "screening reference, not a verified project requirement. OK is not a compliance verdict; "
    "GREY means the check could not determine a result."
)


def load_summary():
    try:
        return json.loads(SUMMARY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def report_count():
    return int(load_summary().get("reports_processed", 0))


def _source(report, page=None):
    source = report.get("source") or {}
    url = source.get("url") if isinstance(source, dict) else None
    if url and url.startswith(("https://", "http://")):
        url = url.split("#", 1)[0] + (f"#page={page}" if page else "")
        return (
            f'<a href="{esc(url)}" target="_blank" rel="noopener">Open source PDF'
            + (f", page {page}" if page else "")
            + "</a>"
        )
    return "Source PDF URL not recorded."


def _period_date(value, precision):
    if not value:
        return "not stated"
    parsed = date.fromisoformat(value)
    return parsed.strftime("%B %Y") if precision == "month" else parsed.isoformat()


def render_report(report):
    """Display checks even when no standard finding or batch observation was raised."""
    checks = batch_results.checks(report)
    st.markdown("#### Batch screening")
    st.caption(NOTE)
    if not checks:
        st.info("No batch screening results were saved for this report.")
        return
    st.markdown(batch_results.summary_line(batch_results.summary(report)))
    st.markdown(_source(report), unsafe_allow_html=True)
    for name, result in checks.items():
        with st.container(key=f"tf-panel-batch-{report['id']}-{name}"):
            status = result.get("grade", result.get("status", "GREY"))
            stamp = (
                badge(status)
                if status in (*batch_results.LEAD_GRADES, "GREY")
                else '<span class="tf-mono">Extracted information</span>'
            )
            st.markdown(
                f'<h3 class="tf-h3">{esc(batch_results.CHECK_NAMES.get(name, name))}</h3>'
                f"{stamp}<p>{esc(result.get('message') or 'No explanation was saved.')}</p>",
                unsafe_allow_html=True,
            )
            if name == "accreditation":
                for key, label in (
                    ("certificate", "Printed certificate"),
                    ("report_date", "Parsed report date (verify)"),
                    ("valid_until", "Printed valid-until date"),
                ):
                    if result.get(key):
                        st.markdown(f"**{label}:** {esc(result[key])}")
            for period in result.get("periods") or []:
                precision = period.get("precision")
                interval = (
                    f"{_period_date(period.get('start_date'), precision)} to "
                    f"{_period_date(period.get('end_date'), precision)}"
                )
                if not period.get("start_date"):
                    interval = "explicit duration; dates not stated"
                st.markdown(
                    f"**{esc(period.get('topic', 'baseline'))}:** {esc(interval)}; "
                    f"{period['duration_months']:g} months; page {period.get('page')}. "
                    f"Precision: {esc(precision)}."
                )
            location = result.get("location")
            if location:
                st.caption(
                    f"Checked location: {location.get('label', '')} ({location.get('lat')}, "
                    f"{location.get('lon')}); {location.get('source', 'not recorded')}."
                )
            if result.get("rows"):
                st.markdown("**Species rows checked against GBIF**")
                st.dataframe(result["rows"], hide_index=True, width="stretch")
            for q in result.get("quotes") or []:
                st.markdown(
                    f'<div class="tf-quote-label">{esc(q.get("label", "Source"))}, '
                    f'page {esc(q.get("page"))}</div><blockquote class="tf-quote">'
                    f"{esc(q.get('text'))}</blockquote>{_source(report, q.get('page'))}",
                    unsafe_allow_html=True,
                )
            for evidence in result.get("evidence") or []:
                st.caption(
                    f"{evidence.get('label', 'Evidence')}: {evidence.get('value', '')}"
                )
            if not result.get("quotes") and not result.get("rows"):
                st.caption(
                    "No supporting quotation or readable species row was saved; this is not evidence of absence."
                )
    leads = batch_results.observations(report)
    st.markdown("#### Additional screening observations")
    if not leads:
        st.caption(
            "No additional screening observations. Undetermined checks above are not findings."
        )
    for i, flag in enumerate(leads, 1):
        slip.render(batch_results.observation_finding(flag, i), crop=False)


def render_summary(entries):
    """Compute the summary from the same reports used by the library, not a second counter."""
    items = [e for e in entries if e.get("screening")]
    counts = batch_results.totals(items)
    st.markdown("#### Batch screening results")
    st.caption(NOTE)
    st.markdown(
        f"{counts['reports']} reports; {counts['checks']} check results; "
        f"Additional observations: {counts['observations']}; {counts['undetermined']} undetermined results. "
        "These counts are separate from the standard audit findings and are computed from the saved reports."
    )
    if not items:
        st.info("No batch screening reports are available in this library.")
        return
    rows = []
    for entry in items:
        report = library.load(entry)
        rows.append(
            {
                "Report": f"/library?report={entry['id']}",
                "Project": entry["project"],
                "State": entry.get("state"),
                "Pages": entry["pages"],
                **{
                    batch_results.CHECK_NAMES.get(k, k): v.get(
                        "grade", v.get("status", "GREY")
                    )
                    for k, v in batch_results.checks(report).items()
                },
                "Additional observations": entry["screening"]["observations"],
            }
        )
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Report": st.column_config.LinkColumn("Report", display_text="Open report")
        },
    )
    saved = load_summary()
    if counts["reports"] == saved.get("reports_processed"):
        credits = (saved.get("tavily") or {}).get("credits")
        if credits is not None:
            st.caption(
                f"Recorded corpus discovery: {credits:g} Tavily credits. Reading these saved results makes no calls."
            )


def render():
    render_summary(library.entries())
