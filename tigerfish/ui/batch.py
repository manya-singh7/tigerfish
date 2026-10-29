"""Replay-only UI for the free batch corpus."""

import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "results" / "batch" / "batch_summary.json"


def load_summary():
    if not SUMMARY.exists():
        return {"status": "not_run", "reports_processed": 0, "flags": [],
                "per_check_counts": {}, "per_state_counts": {}, "tavily": {}}
    try:
        return json.loads(SUMMARY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "not_run", "reports_processed": 0, "flags": [],
                "per_check_counts": {}, "per_state_counts": {}, "tavily": {}}


def report_count() -> int:
    return int(load_summary().get("reports_processed", 0) or 0)


def _rows(summary):
    rows = []
    for flag in summary.get("flags", []):
        quote = "\n".join(f"p.{q.get('page')}: {q.get('text', '')}" for q in flag.get("quotes", []))
        rows.append({"Grade": flag.get("grade", ""), "State": flag.get("state", ""),
                     "Project": flag.get("project_name", ""), "Check": flag.get("check", ""),
                     "Pages/quotes": quote, "Message": flag.get("message", "")})
    return rows


def render():
    summary = load_summary()
    n = report_count()
    if summary.get("status") == "not_run":
        st.info("The batch corpus has not been run in this checkout. Run scripts/build_corpus.py with a Tavily key; the tab itself needs no API keys.")
    else:
        st.caption("Free checks only: regexes over report text plus cached GBIF occurrence lookups. No Nebius/NVIDIA model calls.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Reports", n)
    counts = summary.get("flag_counts", {})
    c2.metric("RED", counts.get("RED", 0))
    c3.metric("ORANGE", counts.get("ORANGE", 0))
    c4.metric("INFO", counts.get("INFO", 0))

    left, right = st.columns(2)
    with left:
        st.subheader("Checks")
        st.json(summary.get("per_check_counts", {}))
    with right:
        st.subheader("States")
        st.json(summary.get("per_state_counts", {}))
        tavily = summary.get("tavily", {})
        st.caption(f"Tavily: {tavily.get('calls', 0)} calls, {tavily.get('credits', 0)} credits; cached: {tavily.get('cached', 0)}")

    st.subheader("Flags to verify")
    rows = _rows(summary)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No batch flags are available yet.")
