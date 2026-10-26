"""Summary strip and finding cards."""

import streamlit as st

from tigerfish.ui import data, investigate
from tigerfish.ui.style import badge, esc, stat

REVIEW_OPTIONS = ["Confirm", "Dismiss", "Unsure"]


def review_key(report_id, finding_id):
    return f"review::{report_id}::{finding_id}"


def reviewed(report_id, findings, choice):
    return [f for f in findings if st.session_state.get(review_key(report_id, f["id"])) == choice]


def fmt_time(seconds):
    if not seconds:
        return "not recorded"
    return f"about {seconds / 60:.0f} min" if seconds >= 90 else f"about {seconds:.0f} s"


def summary_strip(report):
    c = data.counts(report["findings"])
    cost = report.get("cost", {})
    unit = report.get("unit", "page")
    if unit == "table":
        pages = "1 table"
        pages_note = "image of the published table"
    else:
        pages = f"{report['pages_read']:,} of {report['pages_total']:,}"
        pages_note = report.get("pages_note", "pages audited in this run")
    usd = cost.get("nebius_usd")
    credits = cost.get("tavily_credits", 0)
    cost_value = f"${usd:.2f}" if usd is not None else "-"
    cost_note = (f"Nebius models, plus {credits} Tavily credits" if credits else "Nebius models")
    if cost.get("gbif_calls"):
        cost_note += "; GBIF is free"
    cols = st.columns(5)
    cols[0].markdown(stat("Pages read", pages, pages_note), unsafe_allow_html=True)
    cols[1].markdown(stat("Findings", str(sum(c.values())),
                          f"{c['RED']} red, {c['ORANGE']} orange, {c['INFO']} info"),
                     unsafe_allow_html=True)
    cols[2].markdown(stat("Checks run", str(len(report["checks"])), "see Method & limits"),
                     unsafe_allow_html=True)
    cols[3].markdown(stat("Cost", cost_value, cost_note), unsafe_allow_html=True)
    cols[4].markdown(stat("Time", fmt_time(cost.get("approx_seconds")),
                          cost.get("time_note", "API time, estimated")),
                     unsafe_allow_html=True)


def quote_label(q):
    return f"Page {q['page']}" if q.get("page") else q.get("where", "Source")


def evidence_html(items):
    rows = []
    for e in items:
        value = esc(e.get("value"))
        if e.get("url"):
            value = f'<a href="{esc(e["url"])}" target="_blank">{value or esc(e["url"])}</a>'
        rows.append(f'<div class="tf-ev"><span class="tf-ev-label">{esc(e["label"])}:</span> {value}</div>')
    return "".join(rows)


def finding_card(report_id, f, report_title=""):
    with st.container(border=True):
        known = (f' <span class="tf-check">· matches known issue {esc(f["known_issue"])}</span>'
                 if f.get("known_issue") else "")
        st.markdown(f'{badge(f["grade"])}<span class="tf-check">{esc(f["check_name"])}</span>{known}'
                    f'<div class="tf-card-title">{esc(f["title"])}</div>'
                    f'<div class="tf-message">{esc(f["message"])}</div>', unsafe_allow_html=True)

        quotes = f["quotes"]
        cols = st.columns(len(quotes)) if len(quotes) > 1 else [st.container()]
        for col, q in zip(cols, quotes):
            col.markdown(f'<div class="tf-quote-label">{esc(quote_label(q))}</div>'
                         f'<div class="tf-quote">{esc(q["text"])}</div>', unsafe_allow_html=True)

        st.markdown(f'<div style="margin-top:0.7rem">{evidence_html(f["evidence"])}</div>'
                    f'<div class="tf-line" style="margin-top:0.6rem"><b>Why flagged</b> &nbsp;{esc(f["why"])}</div>'
                    f'<div class="tf-line"><b>What would clear this</b> &nbsp;{esc(f["clear"])}</div>',
                    unsafe_allow_html=True)

        images = list(dict.fromkeys(f.get("images") or []))
        if images:
            with st.expander("Show highlighted page" + ("s" if len(images) > 1 else "")):
                paths = [p for p in (data.image_path(rel) for rel in images) if p]
                for col, path in zip(st.columns(len(paths)) if paths else [], paths):
                    # file names end in _p<NNNN>.png
                    col.image(str(path), caption=f"Page {int(path.stem.rsplit('_p', 1)[1])}",
                              width="stretch")

        investigate.render(report_id, f, report_title)

        st.segmented_control("Reviewer", REVIEW_OPTIONS, key=review_key(report_id, f["id"]),
                             label_visibility="collapsed")
