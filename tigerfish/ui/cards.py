"""Summary strip and finding cards."""

import streamlit as st

from tigerfish.ui import badges, crops, data, feedback, investigate
from tigerfish.ui.style import badge, esc, stat

REVIEW_OPTIONS = list(feedback.DECISIONS)
# Checks whose linked evidence was found with Tavily search / extract (every URL in their
# evidence comes from a cached Tavily response). GBIF and report-page links are not Tavily.
TAVILY_CHECKS = badges.TAVILY_CHECKS


def review_key(report_id, finding_id):
    return feedback.widget_key(report_id, finding_id)


def from_tavily(check, e):
    return check in TAVILY_CHECKS and bool(e.get("url")) and not e.get("manual")


OUTCOME_LABELS = {"confirmed": "Confirmed", "confirmed_with_nuance": "Confirmed, with nuance",
                  "explained": "Explained"}


def verification_html(v):
    """The hand check of a finding: who, when, outcome, the reviewed wording and the note."""
    if not v:
        return ""
    head = (f'<b>Human-verified</b> by {esc(v["by"])}, {esc(v["on"])} · '
            f'{esc(OUTCOME_LABELS.get(v.get("outcome"), "Confirmed"))}')
    wording = f'<div style="margin-top:0.25rem">{esc(v["wording"])}</div>' if v.get("wording") else ""
    note = (f'<div style="margin-top:0.25rem"><b>Checked</b> &nbsp;{esc(v["note"])}</div>'
            if v.get("note") else "")
    return f'<div class="tf-verified">{head}{wording}{note}</div>'


def tavily_tag(url):
    return (f' <a class="tf-tavily" href="{esc(url)}" target="_blank" '
            f'title="This source was found with Tavily web search">Found via Tavily</a>')


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
    base = cost.get("note") or "Nebius models"
    cost_note = f"{base}, plus {credits} Tavily credits" if credits else base
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


def evidence_html(items, check=None):
    rows = []
    for e in items:
        value = esc(e.get("value"))
        if e.get("url"):
            value = f'<a href="{esc(e["url"])}" target="_blank">{value or esc(e["url"])}</a>'
        if from_tavily(check, e):
            value += tavily_tag(e["url"])
        rows.append(f'<div class="tf-ev"><span class="tf-ev-label">{esc(e["label"])}:</span> {value}</div>')
    return "".join(rows)


def finding_card(report_id, f, report_title=""):
    with st.container(border=True):
        known = (f' <span class="tf-check">· matches known issue {esc(f["known_issue"])}</span>'
                 if f.get("known_issue") else "")
        st.markdown(f'{badge(f["grade"])}<span class="tf-check">{esc(f["check_name"])}</span>{known}'
                    f'<div class="tf-card-title">{esc(f["title"])}</div>'
                    + badges.html(badges.finding_badges(f, badges.readers(report_id)))
                    + verification_html(f.get("verification"))
                    + f'<div class="tf-message">{esc(f["message"])}</div>', unsafe_allow_html=True)

        quotes = f["quotes"]
        cols = st.columns(len(quotes)) if len(quotes) > 1 else [st.container()]
        for col, q in zip(cols, quotes):
            col.markdown(f'<div class="tf-quote-label">{esc(quote_label(q))}</div>'
                         f'<div class="tf-quote">{esc(q["text"])}</div>', unsafe_allow_html=True)

        st.markdown(f'<div style="margin-top:0.7rem">{evidence_html(f["evidence"], f.get("check"))}</div>'
                    f'<div class="tf-line" style="margin-top:0.6rem"><b>Why flagged</b> &nbsp;{esc(f["why"])}</div>'
                    f'<div class="tf-line"><b>What would clear this</b> &nbsp;{esc(f["clear"])}</div>',
                    unsafe_allow_html=True)

        images = list(dict.fromkeys(f.get("images") or []))
        if crops.wants_crops(f):
            zoomed(images)
        if images:
            with st.expander("Show highlighted page" + ("s" if len(images) > 1 else "")):
                paths = [p for p in (data.image_path(rel) for rel in images) if p]
                for col, path in zip(st.columns(len(paths)) if paths else [], paths):
                    col.image(str(path), caption=f"Page {page_no(path)}", width="stretch")

        investigate.render(report_id, f, report_title)

        feedback.review_widgets(report_id, f)


@st.cache_data(show_spinner=False)
def _crop(path):
    return crops.crop(path)


def page_no(path):
    return int(path.stem.rsplit("_p", 1)[1])       # file names end in _p<NNNN>.png


def zoomed(images):
    """The highlighted lines of each page, side by side (the full pages are below)."""
    shown = [(p, c) for p in (data.image_path(rel) for rel in images) if p
             for c in [_crop(str(p))] if c]
    if not shown:
        return
    st.markdown('<div class="tf-quote-label" style="margin-top:0.7rem">Highlighted lines, zoomed</div>',
                unsafe_allow_html=True)
    for col, (path, png) in zip(st.columns(len(shown)), shown):
        col.image(png, caption=f"Page {page_no(path)}", width="stretch")
