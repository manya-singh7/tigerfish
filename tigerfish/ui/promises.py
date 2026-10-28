"""The "ToR promises" tab: what the Terms of Reference promised vs what the EIA describes,
and a timeline of the field studies' actual dates (from results/<report>_promises.json)."""

import json
from datetime import date, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from tigerfish.ui.style import ACCENT, MUTED

RESULTS = Path(__file__).resolve().parents[2] / "results"
GRADE_ORDER = {"ORANGE": 0, "INFO": 1, "NONE": 2}


def load(report_id):
    path = RESULTS / f"{report_id}_promises.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def table_rows(data):
    """Promises as display rows, ORANGE first."""
    rows = sorted(data["promises"], key=lambda p: (GRADE_ORDER.get(p["grade"], 9), p["id"]))
    return [{"Grade": "-" if p["grade"] == "NONE" else p["grade"], "Verdict": p["verdict"],
             "Topic": p["topic"], "ToR promise": p["commitment"], "Measure": p["measure"],
             "ToR page": p["page"], "Report describes": p["report_describes"],
             "EIA page": p["eia_page"], "Checked by": p["verdict_by"].capitalize(),
             "Link": f"{data['eia_url']}#page={p['eia_page']}" if p.get("eia_page") else None}
            for p in rows]


def timeline_frame(data):
    """One row per field study; end_excl is the day after the end, so a 1-day study has width."""
    rows = []
    for b in data["timeline"]:
        end = date.fromisoformat(b["end"]) + timedelta(days=1)
        rows.append({**{k: b[k] for k in ("study", "start", "end", "days", "page", "quote", "url")},
                     "end_excl": end.isoformat(),
                     "dates": f"{b['start']} to {b['end']} ({b['days']} days)",
                     "cite": f"EIA p.{b['page']}"})
    return pd.DataFrame(rows)


def chart(data):
    bars = timeline_frame(data)
    order = list(dict.fromkeys(bars.sort_values("start")["study"]))
    x = alt.X("start:T", title=None, axis=alt.Axis(format="%b %Y", tickCount="month", grid=True,
                                                    gridOpacity=0.3))
    layers = []
    w = data.get("window")
    if w:
        win = pd.DataFrame([{"start": w["start"], "end_excl": (date.fromisoformat(w["end"]) +
                             timedelta(days=1)).isoformat(), "label": w["label"],
                             "cite": f"EIA p.{w['page']}", "url": w["url"]}])
        layers.append(alt.Chart(win).mark_rect(color=MUTED, opacity=0.14).encode(
            x=x, x2="end_excl:T", href="url:N",
            tooltip=[alt.Tooltip("label:N", title="Window"), alt.Tooltip("cite:N", title="Source")]))
        layers.append(alt.Chart(win).mark_text(align="left", dx=4, dy=-6, baseline="bottom",
                                               color=MUTED, fontSize=11).encode(
            x="start:T", y=alt.value(0), text="label:N"))
    layers.append(alt.Chart(bars).mark_bar(cornerRadius=4, height=14, color=ACCENT,
                                           stroke="white", strokeWidth=1).encode(
        x=x, x2="end_excl:T", y=alt.Y("study:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)),
        href="url:N",
        tooltip=[alt.Tooltip("study:N", title="Study"), alt.Tooltip("dates:N", title="Dates"),
                 alt.Tooltip("cite:N", title="Source"), alt.Tooltip("quote:N", title="Report text")]))
    return alt.layer(*layers).properties(height=36 * len(order) + 30)


def load_granted(report_id):
    path = RESULTS / f"{report_id}_promises_granted.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def promises_table(data):
    st.dataframe(pd.DataFrame(table_rows(data)), hide_index=True, width="stretch",
                 column_config={"Link": st.column_config.LinkColumn("Open page", display_text="open")})


def render(report_id):
    from tigerfish.ui import paper_trail as trail_ui
    data, granted = load(report_id), load_granted(report_id)
    if not data and not granted:
        st.info("No Terms of Reference check for this report. Run: python scripts/check_promises.py")
        return
    st.markdown("#### Did the EIA do what its Terms of Reference promised?")
    st.caption("Measurable commitments in the ToR, compared with what the report itself says it "
               "did. ORANGE: the report's own text shows less than promised (confirmed by a second "
               "reading). INFO: not found, or not confirmed. Each is a question for the reviewer, "
               "not a conclusion.")
    if granted:
        st.markdown(f"##### Granted ToR (MoEFCC letter dated {granted['tor_date'] or 'not stated'})")
        st.markdown(f'<div class="tf-line">Uses the <b>granted</b> Terms of Reference found on an '
                    f'official site by the paper trail: <a href="{granted["tor_url"]}" target="_blank">'
                    f'{granted["tor_url"].split("/")[2]}</a> ({granted["tor_pages"]} pages). '
                    f'{len(granted["promises"])} measurable commitments found in it.</div>',
                    unsafe_allow_html=True)
        promises_table(granted)
    if data:
        st.markdown(f"##### Proposed ToR ({data['tor']})")
        st.caption("Uses the proposed Terms of Reference. The granted ToR may differ.")
        line = trail_ui.granted_tor_line(report_id)
        if line:
            st.markdown(f'<div class="tf-line tf-unusable">{line}</div>', unsafe_allow_html=True)
        promises_table(data)
    if not data:
        return

    st.markdown("#### Survey timeline")
    st.caption("Each bar is a field study's dates as the report states them; the shaded band is "
               "the stated baseline period. Click a bar to open the cited page of the report.")
    st.altair_chart(chart(data), width="stretch", theme="streamlit")
    with st.expander("Timeline as a table"):
        frame = timeline_frame(data)[["study", "start", "end", "days", "cite", "quote", "url"]]
        st.dataframe(frame, hide_index=True, width="stretch",
                     column_config={"url": st.column_config.LinkColumn("Page", display_text="open")})
