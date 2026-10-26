""""Does it match the official record?" section: key project facts in the report vs official
public sources, from results/official_record_<report>.json (replay; no keys needed)."""

import json
from pathlib import Path

from tigerfish.ui.style import badge, esc

RESULTS = Path(__file__).resolve().parents[2] / "results"
SHOWN = ("ORANGE", "INFO", "NONE")          # GREY (source date unknown) is never shown as a result
RESULT_LABEL = {"ORANGE": "Differs, verify", "INFO": "Changed after the EIA", "NONE": "Matches"}


def path(report_id):
    return RESULTS / f"official_record_{report_id}.json"


def load(report_id):
    p = path(report_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def fmt(value, unit):
    if value == 0 and "none" in (unit or ""):
        return "none proposed"
    v = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{v} {unit}".strip()


def source_cell(o):
    when = o.get("date") or "date not found"
    tag = "" if o["label"] == "official source" else f" · {esc(o['label'])}"
    return (f'<a href="{esc(o["url"])}" target="_blank">{esc(o.get("title") or o["url"])}</a>'
            f'<div class="tf-ev-label" style="font-size:0.8rem">{esc(when)}{tag}</div>')


def table_html(rows):
    head = ("<tr><th>Fact</th><th>Report</th><th>Official record</th><th>Source</th>"
            "<th>Result</th></tr>")
    body = []
    for r in rows:
        rep, off = r["report"], r["official"]
        body.append(
            f"<tr><td>{esc(r['label'])}</td>"
            f"<td>{esc(fmt(rep['value'], rep['unit']))}<div class='tf-ev-label' style='font-size:0.8rem'>"
            f"p.{esc(rep['page'])}</div></td>"
            f"<td>{esc(fmt(off['value'], off['unit']))}</td>"
            f"<td>{source_cell(off)}</td>"
            f"<td style='white-space:nowrap'>{badge(r['grade']) if r['grade'] != 'NONE' else ''}"
            f"{esc(RESULT_LABEL[r['grade']])}</td></tr>")
    return f'<table class="tf-table">{head}{"".join(body)}</table>'


def counts(data):
    rows = data["comparisons"]
    return {g: sum(r["grade"] == g for r in rows) for g in ("ORANGE", "INFO", "NONE", "GREY")}


def render(report_id):
    import streamlit as st
    data = load(report_id)
    if data is None:
        return False
    st.markdown("#### Does it match the official record?")
    c = counts(data)
    facts = len(data["facts"])
    st.markdown(
        f'<div class="tf-message">{facts} key facts read from the report were compared with '
        f'official sources found with Tavily: {c["NONE"]} comparisons match, {c["ORANGE"]} differ, '
        f'{c["INFO"]} changed after the EIA ({esc(data["eia_date"])}).</div>', unsafe_allow_html=True)
    shown = [r for r in data["comparisons"] if r["grade"] in SHOWN]
    shown.sort(key=lambda r: SHOWN.index(r["grade"]))
    if shown:
        st.markdown(table_html(shown), unsafe_allow_html=True)
    for r in [r for r in shown if r["grade"] != "NONE"]:
        st.markdown(f'<div class="tf-line">{badge(r["grade"])}{esc(r["message"])}</div>',
                    unsafe_allow_html=True)
    with st.expander("Quotes behind each comparison"):
        for r in shown:
            rep, off = r["report"], r["official"]
            st.markdown(
                f'<div class="tf-card-title" style="font-size:0.95rem">{esc(r["label"])}</div>'
                f'<div class="tf-quote-label">Report, page {esc(rep["page"])} ({esc(rep["quote_check"])})</div>'
                f'<div class="tf-quote">{esc(rep["quote"])}</div>'
                f'<div class="tf-quote-label" style="margin-top:0.4rem">{esc(off.get("title") or off["url"])} '
                f'<a class="tf-tavily" href="{esc(off["url"])}" target="_blank">Found via Tavily</a></div>'
                f'<div class="tf-quote">{esc(off["quote"])}</div>'
                f'<div class="tf-memo-note">{esc(off["quote_check"])}; date: '
                f'{esc(off.get("date") or "not found")}'
                + (f' (read from “{esc(off["date_quote"])}”)' if off.get("date_quote") else "")
                + "</div>", unsafe_allow_html=True)
    if data.get("official_only"):
        st.markdown('<div class="tf-memo-sub">Stated officially, not found in the report pages read</div>',
                    unsafe_allow_html=True)
        for r in data["official_only"]:
            o = r["official"]
            st.markdown(f'<div class="tf-line"><b>{esc(r["label"])}</b> &nbsp;{esc(r["message"])} '
                        f'<a class="tf-tavily" href="{esc(o["url"])}" target="_blank">Found via Tavily</a></div>'
                        f'<div class="tf-quote" style="margin:0.2rem 0 0.5rem 0">{esc(o["quote"])}</div>',
                        unsafe_allow_html=True)
    notes = [f"Same quantity only (units normalised); a difference above "
             f"{data['method']['min_difference']:.0%} is a candidate. A source dated more than about six "
             f"months after the EIA counts as a later revision (INFO); sources older than the project "
             f"are not compared."]
    if c["GREY"]:
        notes.append(f"{c['GREY']} comparison(s) not shown: the source's date could not be found.")
    if data.get("not_found_in_report"):
        notes.append("Not stated on the report pages read: "
                     + ", ".join(k.replace("_", " ") for k in data["not_found_in_report"]) + ".")
    st.caption(" ".join(notes))
    return True
