"""One report, in sections side by side (tabs), not one long scroll.

  Overview · Contradictions · Species & nature · Copied text · Promises & timeline ·
  Public record · Ask & investigate · Take action · Quality · Cost & models

Each finding appears in exactly one section (by its check; see SECTION_CHECKS), so its review
widgets are drawn once. A label carries its count, e.g. "Contradictions (14)". A section that
does not apply to this report is left out, and one line under the tabs says which and why.
Quick checks (free checks only) get only the sections their checks fill.

Quality section hook: if a module tigerfish/ui/quality.py exists with render(report), it is
drawn as the Quality section; otherwise the review queue, the precision panel and the
evaluation table are shown (QUALITY_FALLBACK below). Nothing else needs to change.
"""

import importlib
import re

import streamlit as st

from tigerfish import hosted, library
from tigerfish import review as review_store
from tigerfish.ui import (cards, data, feedback, hero, inspector, letter, memo_ask, method,
                          official, promises, public_record, review, rti, species_map,
                          web_evidence)
from tigerfish.ui.investigate import REPORTS
from tigerfish.ui.style import badge, esc

OVERVIEW, CONTRA, SPECIES, COPIED, PROMISES = ("Overview", "Contradictions", "Species & nature",
                                               "Copied text", "Promises & timeline")
RECORD, ASK, ACTION, QUALITY, COST = ("Public record", "Ask & investigate", "Take action",
                                      "Quality", "Cost & models")
ORDER = (OVERVIEW, CONTRA, SPECIES, COPIED, PROMISES, RECORD, ASK, ACTION, QUALITY, COST)

# Which section shows a finding, by its check. Unknown checks go to OTHER_SECTION.
SECTION_CHECKS = {
    CONTRA: ("contradiction", "recycled_figure", "number_pair"),
    SPECIES: ("species_range", "iucn_status", "legal_schedule", "omission"),
    COPIED: ("copy_paste", "borrowed_text"),
    PROMISES: ("promise",),
    RECORD: ("accreditation", "official_record"),
}
OTHER_SECTION = CONTRA
TOP_FLAGS = 3
QUICK_SECTIONS = (OVERVIEW, CONTRA, SPECIES)
QUICK_HIDDEN_WHY = ("a quick check runs the free checks only; the model, web, review and cost "
                    "sections need a full audit")


def section_of(finding):
    for name, checks in SECTION_CHECKS.items():
        if finding.get("check") in checks:
            return name
    return OTHER_SECTION


def split(findings):
    """{section: [findings]} for the finding sections, in report order."""
    out = {name: [] for name in SECTION_CHECKS}
    for f in findings:
        out[section_of(f)].append(f)
    return out


def _ran(report, *words):
    """True if the report's list of checks names any of these words."""
    text = " ".join(str(c) for c in report.get("checks", [])).lower()
    return any(w in text for w in words)


def _saved(report_id):
    return report_id in {r["id"] for r in data.reports()}


def plan(report, quick=False):
    """([(section, count or None)], [(section, why it is hidden)]) for this report."""
    rid = report["id"]
    by = split(report.get("findings") or [])
    n = {k: len(v) for k, v in by.items()}
    table = report.get("unit") == "table"
    saved = _saved(rid)
    hidden = {}
    if quick:
        names = {c.get("check") for c in report.get("checks_run", []) if c.get("status") == "ran"}
        if not (n[CONTRA] or names & set(SECTION_CHECKS[CONTRA])):
            hidden[CONTRA] = "the number-pair check did not run for this report"
        if not (n[SPECIES] or names & set(SECTION_CHECKS[SPECIES])):
            hidden[SPECIES] = "the species checks did not run for this report"
        shown = [(OVERVIEW, None)] + [(s, n[s]) for s in QUICK_SECTIONS[1:] if s not in hidden]
        hidden.update({s: QUICK_HIDDEN_WHY for s in ORDER if s not in QUICK_SECTIONS})
        return shown, [(s, hidden[s]) for s in ORDER if s in hidden]

    if not (n[CONTRA] or _ran(report, "contradiction")):
        hidden[CONTRA] = ("one published table was audited, so there are no pages to compare"
                          if table else "the contradiction check was not part of this audit")
    if not (n[SPECIES] or _ran(report, "species", "gbif", "iucn")):
        hidden[SPECIES] = "the species checks were not part of this audit"
    if not (n[COPIED] or _ran(report, "copied", "copy")):
        hidden[COPIED] = ("one published table was audited, so there is no running text to search"
                          if table else "the copied-text check was not part of this audit")
    if not (n[PROMISES] or promises.load(rid)):
        hidden[PROMISES] = ("one published table was audited, so there is no Terms of Reference to compare"
                            if table else "no Terms of Reference were compared for this report")
    live = (st.session_state.get("live_pages") or {}).get("id") == rid
    if not (memo_ask.memo(rid) or memo_ask.answers(rid) or live):
        hidden[ASK] = "no reviewer's memo or recorded questions were saved for this report"
    if not saved:
        hidden[QUALITY] = "review and precision figures exist only for saved audits"
    confirmed = len(cards.reviewed(rid, report.get("findings") or [], "Confirm"))
    counts = {CONTRA: n[CONTRA], SPECIES: n[SPECIES], COPIED: n[COPIED], PROMISES: n[PROMISES],
              RECORD: n[RECORD] + _record_count(rid), ACTION: confirmed,
              QUALITY: _quality_count(rid)}
    shown = [(s, counts.get(s)) for s in ORDER if s not in hidden]
    return shown, [(s, hidden[s]) for s in ORDER if s in hidden]


def _record_count(report_id):
    """Key facts that differ from, or changed after, the official record."""
    rec = official.load(report_id)
    c = official.counts(rec) if rec else {}
    return c.get("ORANGE", 0) + c.get("INFO", 0)


def _quality_count(report_id):
    """Flags in this report's review queue (None if it has none)."""
    q = review_store.load_queue()
    return len(q["items"]) if q and q.get("report_id") == report_id else None


def label(section, count):
    return section if count is None else f"{section} ({count:,})"


def hidden_line(hidden):
    """One line: the sections left out, grouped by the reason."""
    if not hidden:
        return
    groups = {}
    for s, why in hidden:
        groups.setdefault(why, []).append(s)
    st.caption("Not shown for this report: " + "; ".join(
        f"{', '.join(names)} ({why})" for why, names in groups.items()) + ".")


# ---------- the sections ----------

def _dismissed(report_id, findings):
    return (review_store.dismissed_finding_ids(review_store.load_queue(), review_store.load_reviews())
            | {f["id"] for f in cards.reviewed(report_id, findings, "Dismiss")})


def finding_list(report, findings, key, empty, map_species=False):
    """Grade filter, dismissed toggle and the finding cards of one section."""
    rid = report["id"]
    if not findings:
        st.info(empty)
        return
    present = [g for g in ("RED", "ORANGE", "INFO") if any(f["grade"] == g for f in findings)]
    grades = st.multiselect("Grade", present, default=present, key=f"sec::{rid}::{key}::grades")
    checks = sorted({f["check_name"] for f in findings})
    if len(checks) > 1:
        checks = st.multiselect("Check", checks, default=checks, key=f"sec::{rid}::{key}::checks")
    shown = data.filter_findings(findings, grades, checks)
    # Flags judged false alarms (Quality section, or Dismiss on a card) are hidden by default.
    dismissed = _dismissed(rid, findings)
    n_dismissed = sum(f["id"] in dismissed for f in shown)
    if n_dismissed and not st.toggle(f"Show dismissed ({n_dismissed})", key=f"sec::{rid}::{key}::dismissed"):
        shown = [f for f in shown if f["id"] not in dismissed]
    if not shown:
        st.info("No findings match these filters.")
    if map_species and any(f["check"] in species_map.SPECIES_CHECKS for f in shown):
        site = (REPORTS.get(rid) or (None, None))[1]
        species_map.render({**report, "findings": shown}, site)
    for f in shown:
        cards.finding_card(rid, f, report.get("title", ""))


def top_flag(f, section):
    q = (f.get("quotes") or [{}])[0]
    where = cards.quote_label(q) if q else ""
    with st.container(border=True):
        st.markdown(f'{badge(f["grade"])}<span class="tf-check">{esc(f["check_name"])} · '
                    f'in {esc(section)}</span><div class="tf-card-title">{esc(f["title"])}</div>'
                    f'<div class="tf-message">{esc(f["message"])}</div>'
                    + (f'<div class="tf-quote-label">{esc(where)}</div>'
                       f'<div class="tf-quote">{esc(q["text"])}</div>' if q.get("text") else ""),
                    unsafe_allow_html=True)


def overview(report, shown, hidden, quick=False):
    if quick:
        library_quick_overview(report)
    else:
        hero.render(report)
        st.write("")
        cards.summary_strip(report)
    st.write("")
    findings = report.get("findings") or []
    flags = [f for f in findings if f["grade"] in ("RED", "ORANGE")]
    dismissed = set() if quick else _dismissed(report["id"], findings)
    top = [f for f in flags if f["id"] not in dismissed][:TOP_FLAGS]
    st.markdown("#### Top flags")
    if not top:
        st.info("No RED or ORANGE flags for this report.")
    for f in top:
        top_flag(f, section_of(f))
    if top:
        st.caption("The strongest flags first. Each one, with its evidence, page images and "
                   "review buttons, is in its section tab. A flag is a lead to verify, not a verdict.")
    st.markdown("#### Sections")
    st.markdown("\n".join(f"- **{esc(label(s, c))}**" for s, c in shown if s != OVERVIEW))
    hidden_line(hidden)


def library_quick_overview(report):
    """The quick check's header: what ran, what did not, and why."""
    st.markdown(f"### {esc(report.get('project') or report['title'])}")
    st.warning(library.QUICK_NOTICE)
    bits = [report.get("state"), report.get("sector"), report.get("year"),
            f"{report.get('pages_read', 0):,} of {report.get('pages_total', 0):,} pages read"]
    st.caption(" · ".join(str(b) for b in bits if b))
    ran = [c for c in report.get("checks_run", []) if c.get("status") == "ran"]
    not_run = [c for c in report.get("checks_run", []) if c.get("status") != "ran"]
    st.markdown("**Checks that ran** (free: no model calls)")
    for c in ran:
        n = c.get("count")
        st.markdown(f"- {esc(c['name'])}" + (f": {n} finding{'s' if n != 1 else ''}" if n is not None else ""))
    if not_run:
        st.markdown("**Not run for this report**")
        for c in not_run:
            st.markdown(f"- {esc(c['name'])}: {esc(c.get('reason') or 'not available')}")
    st.caption("Not run in a quick check: the model checks (internal contradictions, recycled "
               "figures, scanned pages), copied text, consultant accreditation, ToR promises.")


def take_action(report):
    rid, findings = report["id"], report.get("findings") or []
    feedback.reviewer_input(rid, findings)
    confirmed = cards.reviewed(rid, findings, "Confirm")
    dismissed = cards.reviewed(rid, findings, "Dismiss")
    unsure = cards.reviewed(rid, findings, "Unsure")
    st.markdown(f'<div class="tf-review">Reviewed: {len(confirmed)} confirmed, '
                f'{len(dismissed)} dismissed, {len(unsure)} unsure. Reviews are kept '
                f'{feedback.where()}.</div>', unsafe_allow_html=True)
    st.caption("Mark findings Confirm, Dismiss or Unsure on their cards in each section. The "
               "letter and the pack are built from the findings you confirmed.")
    lang_options = letter.language_options(report)
    lang_label = st.radio("Letter language", list(lang_options), horizontal=True,
                          help=" and ".join(["Hindi"] + letter.regional_languages(report))
                               + (" are" if letter.regional_languages(report) else " is")
                               + " machine-translated (the letter says so: please review). Quotes "
                               "from the report, page numbers and links are never translated.")
    lang = lang_options[lang_label]
    docx_bytes, letter_error = b"", None
    addressee = report.get("letter_addressee", "committee")
    if confirmed:
        try:
            if lang != "en" and hosted.is_hosted():
                # Hindi/Tamil/Kannada translation is a paid (Lightning) call: the session's key and the daily budget
                if not hosted.paid_key(st.session_state):
                    raise letter.TranslationUnavailable("no key on the hosted app")
                with hosted.paid_calls(st.session_state):
                    docx_bytes = letter.build_letter(report, confirmed, lang, addressee=addressee)
            else:
                docx_bytes = letter.build_letter(report, confirmed, lang, addressee=addressee)
        except letter.TranslationUnavailable:
            letter_error = ("The translated letter needs the translation model (NEBIUS_API_KEY), and "
                            "this selection has not been translated before. Choose English.")
    st.download_button(
        "Draft objection letter (.docx)",
        data=docx_bytes,
        file_name=f"tigerfish_{rid}_letter_{lang}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        disabled=not confirmed or bool(letter_error), type="primary",
        help="Built from the findings you marked Confirm. Neutral and factual, with page "
             "citations and evidence links.")
    st.download_button(
        "RTI + public hearing pack (.zip)",
        data=rti.build_pack(report, confirmed) if confirmed else b"",
        file_name=f"tigerfish_{rid}_rti_hearing_pack.zip", mime="application/zip",
        disabled=not confirmed,
        help="Drafts, please review: written comments for the EIA public consultation (EIA "
             "Notification, 2006) and RTI applications (Section 6, RTI Act 2005), one question "
             "per confirmed finding. English only; fill in the [placeholders].")
    if not confirmed:
        st.caption("Mark at least one finding as Confirm to draft the letter and the pack.")
    if letter_error:
        st.caption(letter_error)


def QUALITY_FALLBACK(report):
    """Shown until tigerfish/ui/quality.py provides render(report)."""
    rid = report["id"]
    review.render(rid)
    st.write("")
    feedback.panel(rid, report.get("findings") or [])
    st.write("")
    method.render_evaluation(with_costs=False)


def quality(report):
    try:
        mod = importlib.import_module("tigerfish.ui.quality")
    except ModuleNotFoundError as e:
        if e.name != "tigerfish.ui.quality":
            raise
        mod = None
    (mod.render if mod and hasattr(mod, "render") else QUALITY_FALLBACK)(report)


def cost_and_models(report):
    cards.summary_strip(report)
    st.write("")
    method.render_costs()
    st.write("")
    inspector.render(report["id"])


def public_record_section(report, findings):
    rid = report["id"]
    if findings:
        finding_list(report, findings, "record", "")
        st.write("")
    official.render(rid)
    st.write("")
    public_record.render(rid)
    st.write("")
    with st.expander("Evidence from the web (every saved report)"):
        web_evidence.render()


# ---------- the report page ----------

def render(report, quick=False):
    """Draw one report. quick=True: a quick check (library.load), free checks only."""
    rid = report["id"]
    if not quick:
        st.caption(f"Saved results. Source: {report.get('source', '')}" if _saved(rid)
                   else f"Source: {report.get('source', '')}")
        for notice in report.get("notices", []):     # e.g. a partial audit, flags not yet reviewed
            st.warning(notice)
        feedback._seed(rid, report.get("findings") or [])   # before any review widget is drawn
    shown, hidden = plan(report, quick)
    by = split(report.get("findings") or [])
    # A container keyed by the report: switching reports draws fresh widgets, instead of the
    # browser reusing the previous report's filters at the same place.
    box = st.container(key="tf-report-" + re.sub(r"[^A-Za-z0-9_-]", "-", str(rid)))
    tabs = dict(zip([s for s, _ in shown], box.tabs([label(s, c) for s, c in shown])))

    with tabs[OVERVIEW]:
        overview(report, shown, hidden, quick)
    if CONTRA in tabs:
        with tabs[CONTRA]:
            finding_list(report, by[CONTRA], "contra",
                         "No contradictions or recycled figures were flagged in this report.")
    if SPECIES in tabs:
        with tabs[SPECIES]:
            finding_list(report, by[SPECIES], "species",
                         "No species, status or omission findings for this report.", map_species=True)
    if COPIED in tabs:
        with tabs[COPIED]:
            finding_list(report, by[COPIED], "copied", "No copied or borrowed text was flagged.")
    if PROMISES in tabs:
        with tabs[PROMISES]:
            if by[PROMISES]:
                finding_list(report, by[PROMISES], "promises", "")
                st.write("")
            promises.render(rid)
    if RECORD in tabs:
        with tabs[RECORD]:
            public_record_section(report, by[RECORD])
    if ASK in tabs:
        with tabs[ASK]:
            memo_ask.render(rid)
    if ACTION in tabs:
        with tabs[ACTION]:
            take_action(report)
    if QUALITY in tabs:
        with tabs[QUALITY]:
            quality(report)
    if COST in tabs:
        with tabs[COST]:
            cost_and_models(report)

