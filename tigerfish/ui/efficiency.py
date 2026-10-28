"""Context efficiency of Tavily, from results/tavily_usage.json only (measured, not estimated):
"Tavily returned X; we used Y (Z%)", overall and per feature. Shown in the cost card
(Method & limits) and in the "Evidence from the web" tab."""

import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "results" / "tavily_usage.json"

EXPLAIN = ("Characters of web content in every Tavily response (titles, snippets, page text, "
           "map URLs) vs. the characters of it we sent to a model or show as evidence (quotes, "
           "titles, timeline events). Measured by replaying each check from the cache with "
           "nothing paid allowed (scripts/measure_tavily_usage.py); the paper trail counted "
           "during its own run.")


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else None


def fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    return f"{n:,}"


def pct(share):
    if share is None:
        return "-"
    return f"{share:.1%}" if share >= 0.001 or share == 0 else f"{share:.2%}"


def line(row):
    """'Tavily returned X; we used Y (Z%)' for one totals row."""
    return f"Tavily returned {fmt(row['returned'])} characters; we used {fmt(row['used'])} ({pct(row['share'])})"


def table_md(data):
    lines = ["| Tavily feature | Calls | Returned (chars) | Sent to a model | Shown as evidence | Used |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, r in data["overall"]["features"].items():
        lines.append(f"| {name} | {r['calls']} | {r['returned']:,} | {r['sent to model']:,} | "
                     f"{r['shown as evidence']:,} | {pct(r['share'])} |")
    t = data["overall"]["total"]
    lines.append(f"| **All features** | {t['calls']} | **{t['returned']:,}** | {t['sent to model']:,} | "
                 f"{t['shown as evidence']:,} | **{pct(t['share'])}** |")
    return "\n".join(lines)


def checks_md(data):
    lines = ["| Check / report | Returned (chars) | Used | Share |", "|---|---:|---:|---:|"]
    for name, s in data["checks"].items():
        t = s["total"]
        lines.append(f"| {name} | {t['returned']:,} | {t['used']:,} | {pct(t['share'])} |")
    return "\n".join(lines)


def render_card():
    """One line for the cost card, with the per-feature table in an expander."""
    import streamlit as st
    data = load()
    if not data:
        return
    st.markdown(f'<div class="tf-message tf-efficiency"><b>Context efficiency:</b> '
                f'{line(data["overall"]["total"])}.</div>', unsafe_allow_html=True)
    with st.expander("Per Tavily feature"):
        st.markdown(table_md(data))
        st.caption(EXPLAIN)


def render_tab():
    """Full section for the "Evidence from the web" tab."""
    import streamlit as st
    data = load()
    if not data:
        return
    st.markdown("##### Context efficiency")
    st.markdown(f'<div class="tf-message tf-efficiency">{line(data["overall"]["total"])}: '
                f'{fmt(data["overall"]["total"]["sent to model"])} sent to a model, '
                f'{fmt(data["overall"]["total"]["shown as evidence"])} shown as evidence.</div>',
                unsafe_allow_html=True)
    st.markdown(table_md(data))
    with st.expander("Per check and report"):
        st.markdown(checks_md(data))
        for name, why in (data.get("not_measured") or {}).items():
            st.caption(f"Not measured: {name}: {why}.")
    st.caption(EXPLAIN + f" Measured on {data['measured_on']}.")


def report_total(report_id):
    """Totals row for one report: every measured check of that report (None if none)."""
    from tigerfish import tavily_usage
    data = load()
    if not data:
        return None
    snaps = [s for name, s in data["checks"].items() if name.endswith(f"/ {report_id}")]
    return tavily_usage.merge(snaps)["total"] if snaps else None
