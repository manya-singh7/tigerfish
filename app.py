"""TigerFish: an accuracy checker for Indian Environmental Impact Assessment reports.

Run:  streamlit run app.py
Replay mode (default) shows saved results from results/ and needs no API keys.
Live mode appears only when NEBIUS_API_KEY is set.
"""

import streamlit as st

from tigerfish.ui import cards, data, letter, live, method
from tigerfish.ui.style import CSS

st.set_page_config(page_title="TigerFish", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

# ---------- header ----------
st.markdown('<div class="tf-title">TigerFish</div>'
            '<div class="tf-tagline">Sees clearly in murky waters.</div>'
            '<div class="tf-lede">TigerFish reads Environmental Impact Assessment reports and flags '
            'statements that disagree with each other or with public records, with the page, '
            'the exact quote and the evidence for each, so a reviewer can verify them.</div>',
            unsafe_allow_html=True)

saved = data.reports()
titles = {r["title"]: r["id"] for r in saved}
pick_col, mode_col = st.columns([3, 1])
live_mode = False
if live.available():
    live_mode = mode_col.toggle("Live mode", help="Upload a PDF and run the models (costs money).")
if not live_mode:
    choice = pick_col.selectbox("Report", list(titles), label_visibility="collapsed")

# ---------- load the report ----------
if live_mode:
    report = live.render()
    if report is None:
        st.stop()
else:
    if not saved:
        st.error("No saved results found. Run: python scripts/export_results.py")
        st.stop()
    report = data.load(titles[choice])
    st.caption(f"Saved results. Source: {report.get('source', '')}")

findings_tab, method_tab = st.tabs(["Findings", "Method & limits"])

with findings_tab:
    st.write("")
    cards.summary_strip(report)
    st.write("")

    findings = report["findings"]
    f1, f2 = st.columns(2)
    grades = f1.multiselect("Grade", ["RED", "ORANGE", "INFO"], default=["RED", "ORANGE", "INFO"])
    check_names = sorted({f["check_name"] for f in findings})
    checks = f2.multiselect("Check", check_names, default=check_names)
    shown = data.filter_findings(findings, grades, checks)

    if not findings:
        st.info("No RED, ORANGE or INFO findings for this report.")
    elif not shown:
        st.info("No findings match these filters.")
    for f in shown:
        cards.finding_card(report["id"], f, report.get("title", ""))

    # ---------- letter from confirmed findings ----------
    st.write("")
    confirmed = cards.reviewed(report["id"], findings, "Confirm")
    dismissed = cards.reviewed(report["id"], findings, "Dismiss")
    unsure = cards.reviewed(report["id"], findings, "Unsure")
    st.markdown(f'<div class="tf-review">Reviewed: {len(confirmed)} confirmed, '
                f'{len(dismissed)} dismissed, {len(unsure)} unsure. Reviews are kept for this '
                f'session only.</div>', unsafe_allow_html=True)
    lang_label = st.radio("Letter language", ["English", "Hindi", "Both"], horizontal=True,
                          help="Hindi is machine-translated. Quotes from the report, page "
                               "numbers and links are never translated.")
    lang = {"English": "en", "Hindi": "hi", "Both": "both"}[lang_label]
    docx_bytes, letter_error = b"", None
    if confirmed:
        try:
            docx_bytes = letter.build_letter(report, confirmed, lang)
        except letter.TranslationUnavailable:
            letter_error = ("The Hindi letter needs the translation model (NEBIUS_API_KEY), and "
                            "this selection has not been translated before. Choose English.")
    st.download_button(
        "Draft objection letter (.docx)",
        data=docx_bytes,
        file_name=f"tigerfish_{report['id']}_letter_{lang}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        disabled=not confirmed or bool(letter_error), type="primary",
        help="Built from the findings you marked Confirm. Neutral and factual, with page "
             "citations and evidence links.")
    if not confirmed:
        st.caption("Mark at least one finding as Confirm to draft the letter.")
    if letter_error:
        st.caption(letter_error)

with method_tab:
    method.render()
