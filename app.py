"""TigerFish: an accuracy checker for Indian Environmental Impact Assessment reports.

Run:  streamlit run app.py
Replay mode (default) shows saved results from results/ and needs no API keys.
Live mode appears only when NEBIUS_API_KEY is set. On the hosted app (tigerfish/hosted.py)
everything shown comes from committed files, and paid model calls are capped.
"""

import streamlit as st

from tigerfish import hosted
from tigerfish import review as review_store
from tigerfish.ui import (cards, data, feedback, hero, inspector, letter, live, memo_ask, method,
                          official, promises, public_record, review, rti, species_map,
                          web_evidence, batch as batch_ui)
from tigerfish.ui.investigate import REPORTS
from tigerfish.ui.style import CSS

st.set_page_config(page_title="TigerFish", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

# ---------- hero: one finding first (filled in once the report is loaded) ----------
hero_slot = st.container()

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
elif hosted.is_hosted():
    st.info(live.replay_only_note())
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
    for notice in report.get("notices", []):     # e.g. a partial audit, flags not yet reviewed
        st.warning(notice)
    with hero_slot:
        hero.render(report)

(findings_tab, review_tab, memo_tab, promises_tab, record_tab, web_tab, scanned_tab,
 batch_tab, method_tab) = st.tabs(
    ["Findings", "Review queue", "Reviewer's memo & Ask", "ToR promises", "Public record",
     "Evidence from the web", "Scanned pages", f"Batch: {batch_ui.report_count()} reports",
     "Method & limits"])

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
    feedback.reviewer_input(report["id"], findings)
    # Flags judged false alarms (Review queue tab, or Dismiss on a card) are hidden by default.
    dismissed = (review_store.dismissed_finding_ids(review_store.load_queue(), review_store.load_reviews())
                 | {f["id"] for f in cards.reviewed(report["id"], findings, "Dismiss")})
    n_dismissed = sum(f["id"] in dismissed for f in shown)
    if n_dismissed and not st.toggle(f"Show dismissed ({n_dismissed})", key="show_dismissed"):
        shown = [f for f in shown if f["id"] not in dismissed]

    if not findings:
        st.info("No RED, ORANGE or INFO findings for this report.")
    elif not shown:
        st.info("No findings match these filters.")
    map_drawn = False
    for f in shown:
        if f["check"] in species_map.SPECIES_CHECKS and not map_drawn:
            site = (REPORTS.get(report["id"]) or (None, None))[1]
            species_map.render({**report, "findings": shown}, site)
            map_drawn = True
        cards.finding_card(report["id"], f, report.get("title", ""))

    # ---------- key facts vs the official record ----------
    st.write("")
    official.render(report["id"])

    # ---------- letter from confirmed findings ----------
    st.write("")
    confirmed = cards.reviewed(report["id"], findings, "Confirm")
    dismissed = cards.reviewed(report["id"], findings, "Dismiss")
    unsure = cards.reviewed(report["id"], findings, "Unsure")
    st.markdown(f'<div class="tf-review">Reviewed: {len(confirmed)} confirmed, '
                f'{len(dismissed)} dismissed, {len(unsure)} unsure. Reviews are kept '
                f'{feedback.where()}.</div>', unsafe_allow_html=True)
    lang_options = letter.language_options(report)
    lang_label = st.radio("Letter language", list(lang_options), horizontal=True,
                          help=" and ".join(["Hindi"] + letter.regional_languages(report))
                               + (" are" if letter.regional_languages(report) else " is")
                               + " machine-translated (the letter says so: please review). Quotes "
                               "from the report, page numbers and links are never translated.")
    lang = lang_options[lang_label]
    docx_bytes, letter_error = b"", None
    if confirmed:
        try:
            if lang != "en" and hosted.is_hosted():
                # Hindi/Tamil/Kannada translation is a paid (Lightning) call: the session's key and the daily budget
                if not hosted.paid_key(st.session_state):
                    raise letter.TranslationUnavailable("no key on the hosted app")
                with hosted.paid_calls(st.session_state):
                    docx_bytes = letter.build_letter(report, confirmed, lang,
                                                     addressee=report.get("letter_addressee", "committee"))
            else:
                docx_bytes = letter.build_letter(report, confirmed, lang,
                                                 addressee=report.get("letter_addressee", "committee"))
        except letter.TranslationUnavailable:
            letter_error = ("The translated letter needs the translation model (NEBIUS_API_KEY), and "
                            "this selection has not been translated before. Choose English.")
    st.download_button(
        "Draft objection letter (.docx)",
        data=docx_bytes,
        file_name=f"tigerfish_{report['id']}_letter_{lang}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        disabled=not confirmed or bool(letter_error), type="primary",
        help="Built from the findings you marked Confirm. Neutral and factual, with page "
             "citations and evidence links.")
    st.download_button(
        "RTI + public hearing pack (.zip)",
        data=rti.build_pack(report, confirmed) if confirmed else b"",
        file_name=f"tigerfish_{report['id']}_rti_hearing_pack.zip", mime="application/zip",
        disabled=not confirmed,
        help="Drafts, please review: written comments for the EIA public consultation (EIA "
             "Notification, 2006) and RTI applications (Section 6, RTI Act 2005), one question "
             "per confirmed finding. English only; fill in the [placeholders].")
    if not confirmed:
        st.caption("Mark at least one finding as Confirm to draft the letter and the pack.")
    if letter_error:
        st.caption(letter_error)

    st.write("")
    feedback.panel(report["id"], findings)

with review_tab:
    review.render(report["id"])

with memo_tab:
    memo_ask.render(report["id"])

with promises_tab:
    promises.render(report["id"])

with record_tab:
    public_record.render(report["id"])

with web_tab:
    web_evidence.render()

with scanned_tab:
    inspector.render(report["id"])

with batch_tab:
    batch_ui.render()

with method_tab:
    method.render()
