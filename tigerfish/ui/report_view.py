"""One report, in sections side by side (tabs across the full width), not one long scroll.

  Overview · Contradictions · Species & nature · Copied text · Promises & timeline ·
  Public record · Ask & investigate · Take action · Quality · Cost & models

Each finding appears in exactly one section (by its check; see SECTION_CHECKS), so its review
widgets are drawn once. A label carries its count, e.g. "Contradictions (14)". A section that
does not apply to this report is left out, and one line in the Overview says which and why.
Quick checks (free checks only) get only the sections their checks fill.

Inside a finding section (docs/DESIGN.md): the evidence slips in the main column, 10 at a
time, and a side panel with the section's filters, counts and what the check does. The
Overview shows only the top 3 human-verified findings and one sentence of totals.

Quality section hook: if a module tigerfish/ui/quality.py exists with render(report), it is
drawn as the Quality section; otherwise the review queue, the precision panel and the
evaluation table are shown (QUALITY_FALLBACK below). Nothing else needs to change.
"""

import importlib
import re

import streamlit as st

from tigerfish import hosted, library
from tigerfish import review as review_store
from tigerfish.ui import (cards, data, feedback, inspector, letter, memo_ask, method,
                          official, promises, public_record, review, rti, slip, species_map,
                          web_evidence)
from tigerfish.ui import investigate
from tigerfish.ui.investigate import REPORTS
from tigerfish.ui.style import badge, esc, mono

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
PAGE_SIZE = 10
QUICK_SECTIONS = (OVERVIEW, CONTRA, SPECIES)
QUICK_HIDDEN_WHY = ("a quick check runs the free checks only; the model, web, review and cost "
                    "sections need a full audit")

# "What this check does": one paragraph per section, in its side panel.
ABOUT = {
    CONTRA: ("Statements in the report that give different values for the same thing "
             "(contradictions), the same figure reused for different places or years (recycled "
             "figures), and number pairs that disagree. Ultra reads both full pages before a pair "
             "is flagged; each slip shows the highlighted lines of both pages."),
    SPECIES: ("Species found in readable tables are checked against GBIF records, within this "
        "run's coverage and name limits. IUCN and Wildlife Protection Act checks run where "
        "their inputs are available. Threatened species recorded "
        "near the site that the report never mentions are listed as omissions. The map shows "
        "where the flagged species are actually recorded; photos are reference images."),
    COPIED: ("Site-specific passages are searched on the web to find the same text in documents "
             "about other places. Standard equipment and method wording is filtered out first."),
    PROMISES: ("What the Terms of Reference asked for, compared with what the report says it did. "
               "The granted ToR (the ministry's letter) and the proposed ToR are labelled, and the "
               "survey dates are drawn on one timeline."),
    RECORD: ("Key facts compared with official public sources, what happened to the project after "
             "the report, the project's own documents found on official sites, and who to write "
             "to. The consultant's NABET accreditation is checked here too."),
    ASK: ("The reviewer's memo: Ultra reads the included report text and lists cross-chapter issues, every "
        "quote checked against the page. Ask the report answers one question at a time with "
        "page citations. Investigate, on each flag, sends an agent for more evidence."),
    ACTION: ("Mark flags Confirm, Dismiss or Unsure on their slips. The objection letter (English, "
             "Hindi, and the state's language) and the RTI and public hearing pack are built only "
             "from the flags you confirmed."),
    QUALITY: ("The review queue of every new RED and ORANGE flag, precision from reviewers' "
              "decisions, and the evaluation against known issues and planted tests."),
    COST: ("What this audit cost and how long it took, the cost of a full audit by triage mode, "
           "context efficiency, and how Super-VL read the scanned pages."),
}
CSS = """<style>
@media (max-width: 1099px) {
  div[class*="st-key-tf-sec-"] [data-testid="stHorizontalBlock"] { flex-direction: column-reverse !important; }
  div[class*="st-key-tf-sec-"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
}
div[class*="st-key-tf-slip-f-"] { padding: 1rem; margin-bottom: 0.25rem; }
div[class*="st-key-tf-slip-f-"] .tf-slip { border: 0; padding: 0; margin: 0 0 0.25rem 0; }
.tf-h3.tf-on-paper { background: var(--tf-paper); border: 1px solid var(--tf-rule); border-radius: 3px;
  padding: 0.5rem 1rem; margin: 0 0 0.75rem 0; display: block; }
</style>"""


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


# ---------- section layout: main column and side panel ----------

def _dismissed(report_id, findings):
    return (review_store.dismissed_finding_ids(review_store.load_queue(), review_store.load_reviews())
            | {f["id"] for f in cards.reviewed(report_id, findings, "Dismiss")})


def section_columns(key):
    """(main, side) columns of a section; below 1100px the side panel goes on top (CSS)."""
    with st.container(key=f"tf-sec-{key}"):
        main, side = st.columns([7, 3], gap="medium")
    return main, side


def side_panel(side, section, key, findings=None):
    """The section's side panel, with its counts by grade. Returns the panel container."""
    with side:
        box = st.container(key=f"tf-side-{key}")
    with box:
        st.markdown(f'<div class="tf-h3">{esc(section)}</div>', unsafe_allow_html=True)
        if findings is not None:
            c = data.counts(findings)
            st.markdown('<div class="tf-rep-grades">' + " ".join(
                f"{badge(g)}{mono(f'{c[g]:,}')}&nbsp;&nbsp;" for g in ("RED", "ORANGE", "INFO"))
                + "</div>", unsafe_allow_html=True)
    return box


def about(box, section):
    with box:
        st.markdown(f'<div class="tf-meta" style="margin-top:0.8rem"><b>What this check does</b></div>'
                    f'<div class="tf-what">{esc(ABOUT[section])}</div>', unsafe_allow_html=True)


def plain_section(section, key, draw, report_id):
    """A section without findings of its own: content in the main column, the side panel
    says what it does."""
    main, side = section_columns(key)
    box = side_panel(side, section, key)
    about(box, section)
    with main:
        draw(report_id)


def _more(key):
    st.session_state[key] = st.session_state.get(key, PAGE_SIZE) + PAGE_SIZE


def finding_list(report, findings, key, empty, map_species=False, section=None):
    """A finding section: the slips in the main column (10 at a time); in the side panel the
    grade and check filters, the dismissed toggle, the counts and what the check does.
    Returns the main column, for content the section adds below its findings."""
    rid = report["id"]
    main, side = section_columns(key)
    box = side_panel(side, section or key, key, findings)
    if not findings:
        with main, st.container(key=f"tf-panel-empty-{key}"):
            st.markdown(f'<div class="tf-h3">Nothing flagged here</div><p>{esc(empty)}</p>',
                        unsafe_allow_html=True)
        if section:
            about(box, section)
        return main
    with box:
        present = [g for g in ("RED", "ORANGE", "INFO") if any(f["grade"] == g for f in findings)]
        grades = st.multiselect("Grade", present, default=present, key=f"sec::{rid}::{key}::grades")
        checks = sorted({f["check_name"] for f in findings})
        if len(checks) > 1:
            checks = st.multiselect("Check", checks, default=checks, key=f"sec::{rid}::{key}::checks")
        shown = data.filter_findings(findings, grades, checks)
        # Flags judged false alarms (Quality section, or Dismiss on a card) are hidden by default.
        dismissed = _dismissed(rid, findings)
        n_dismissed = sum(f["id"] in dismissed for f in shown)
        if n_dismissed and not st.toggle(f"Show dismissed ({n_dismissed})",
                                         key=f"sec::{rid}::{key}::dismissed"):
            shown = [f for f in shown if f["id"] not in dismissed]
        st.markdown(f'<div class="tf-count">Showing {len(shown)} of {len(findings)} findings.</div>',
                    unsafe_allow_html=True)
    if section:
        about(box, section)
    with main:
        if not shown:
            with st.container(key=f"tf-panel-none-{key}"):
                st.markdown('<div class="tf-h3">No findings match these filters</div>'
                            '<p>Add a grade or a check back in the side panel.</p>',
                            unsafe_allow_html=True)
        if map_species and any(f["check"] in species_map.SPECIES_CHECKS for f in shown):
            site = (REPORTS.get(rid) or (None, None))[1]
            with st.container(key=f"tf-panel-map-{key}"):
                species_map.render({**report, "findings": shown}, site)
        # Findings a person verified, or with a recorded investigation, first (stable order
        # otherwise), so the evidence-rich ones are never behind "show more".
        shown = sorted(shown, key=lambda f: (not f.get("verification"),
                                             investigate.saved(rid, f.get("investigation_id") or f["id"]) is None))
        more_key = f"sec::{rid}::{key}::shown"
        n = st.session_state.get(more_key, PAGE_SIZE)
        for f in shown[:n]:
            cards.finding_card(rid, f, report.get("title", ""))
        if len(shown) > n:
            st.button(f"Show {min(PAGE_SIZE, len(shown) - n)} more ({len(shown) - n} not shown)",
                      key=f"{more_key}::btn", on_click=_more, args=(more_key,))
    return main


# ---------- the sections ----------

def totals_sentence(report):
    findings = report.get("findings") or []
    c = data.counts(findings)
    verified = sum(1 for f in findings if f.get("verification"))
    unit = ("1 published table" if report.get("unit") == "table"
            else f"{report.get('pages_read', 0):,} of {report.get('pages_total', 0):,} pages read")
    return (f"{len(findings):,} findings ({c['RED']:,} RED, {c['ORANGE']:,} ORANGE, {c['INFO']:,} "
            f"INFO leads) from {unit}; {verified:,} verified by a person. Every finding is in its "
            "section tab. A flag is a lead to verify, not a verdict.")


def overview(report, shown, hidden, quick=False):
    """The top 3 human-verified findings as evidence slips and one sentence of totals; the
    rest stays in the sections."""
    if quick:
        library_quick_overview(report)
    findings = report.get("findings") or []
    dismissed = set() if quick else _dismissed(report["id"], findings)
    live = [f for f in findings if f["id"] not in dismissed]
    verified = [f for f in live if f.get("verification")
                and f["verification"].get("outcome") != "explained"]
    with st.container(key="tf-panel-overview"):
        st.markdown(f'<h2 class="tf-h2">{esc(report.get("project") or report.get("title", ""))}</h2>'
                    f'<p class="tf-totals">{esc(totals_sentence(report))}</p>', unsafe_allow_html=True)
        hidden_line(hidden)
    if verified:
        top = slip.pick(verified, TOP_FLAGS)
        st.markdown('<div class="tf-h3 tf-on-paper">Top flags, verified by a person</div>',
                    unsafe_allow_html=True)
    else:
        top = slip.pick([f for f in live if f["grade"] in ("RED", "ORANGE")], TOP_FLAGS)
        if top:
            with st.container(key="tf-panel-unverified"):
                st.markdown('<div class="tf-h3">Top flags, not yet verified by a person</div>'
                            "<p>No finding in this report has been checked by hand yet. These are "
                            "the strongest flags; review them in their section.</p>",
                            unsafe_allow_html=True)
    if not top:
        with st.container(key="tf-panel-noflags"):
            st.markdown('<div class="tf-h3">No RED or ORANGE flags</div><p>The checks that ran on '
                        "this report raised no RED or ORANGE flags. Its INFO leads, if any, are in "
                        "their sections.</p>", unsafe_allow_html=True)
    for f in top:
        slip.render(f, section=section_of(f))


def library_quick_overview(report):
    """The quick check's header: what ran, what did not, and why."""
    with st.container(key="tf-panel-quick"):
        st.markdown(f'<h2 class="tf-h2">{esc(report.get("project") or report["title"])}</h2>',
                    unsafe_allow_html=True)
        st.warning(library.QUICK_NOTICE)
        bits = [report.get("state"), report.get("sector"), report.get("year"),
                f"{report.get('pages_read', 0):,} of {report.get('pages_total', 0):,} pages read"]
        st.caption(" · ".join(str(b) for b in bits if b))
        ran = [c for c in report.get("checks_run", []) if c.get("status") == "ran"]
        not_run = [c for c in report.get("checks_run", []) if c.get("status") != "ran"]
        st.markdown("**Checks that ran** (free: no model calls)")
        for c in ran:
            n = c.get("count")
            st.markdown(f"- {esc(c['name'])}" + (f": {n} finding{'s' if n != 1 else ''}"
                                                   if n is not None else ""))
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
    st.caption("Mark findings Confirm, Dismiss or Unsure on their slips in each section. The "
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
                with hosted.paid_calls(st.session_state), st.spinner("Translating the letter..."):
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
        st.caption("Nothing to draft yet: mark at least one finding Confirm (on its slip, in any "
                   "section) to build the letter and the pack.")
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
    main = finding_list(report, findings, "record",
                        "No accreditation or official-record finding for this report; the "
                        "record and the documents found are below.", section=RECORD)
    with main:
        with st.container(key="tf-panel-official"):
            official.render(rid)
        with st.container(key="tf-panel-public"):
            public_record.render(rid)
        with st.expander("Evidence from the web (every saved report)"):
            web_evidence.render()


def _panel(key, draw, *args):
    """Draw a section's content on a paper panel."""
    with st.container(key=f"tf-panel-{key}"):
        draw(*args)


# ---------- the report page ----------

def render(report, quick=False):
    """Draw one report. quick=True: a quick check (library.load), free checks only."""
    st.markdown(CSS, unsafe_allow_html=True)
    rid = report["id"]
    if not quick:
        with st.container(key="tf-plain-source"):
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
                         "No contradictions or recycled figures were flagged in this report.",
                         section=CONTRA)
    if SPECIES in tabs:
        with tabs[SPECIES]:
            finding_list(report, by[SPECIES], "species",
                         "No species, status or omission findings for this report.",
                         map_species=True, section=SPECIES)
    if COPIED in tabs:
        with tabs[COPIED]:
            main = finding_list(report, by[COPIED], "copied", "No copied or borrowed text was flagged.",
                                section=COPIED)
            with main:
                cards.excluded_matches(report)
    if PROMISES in tabs:
        with tabs[PROMISES]:
            main = finding_list(report, by[PROMISES], "promises",
                                "No ToR promise was found unmet; the comparison is below.",
                                section=PROMISES)
            with main:
                _panel("promises-detail", promises.render, rid)
    if RECORD in tabs:
        with tabs[RECORD]:
            public_record_section(report, by[RECORD])
    if ASK in tabs:
        with tabs[ASK]:
            plain_section(ASK, "ask", lambda r: _panel("ask", memo_ask.render, r), rid)
    if ACTION in tabs:
        with tabs[ACTION]:
            plain_section(ACTION, "action", lambda r: _panel("action", take_action, report), rid)
    if QUALITY in tabs:
        with tabs[QUALITY]:
            plain_section(QUALITY, "quality", lambda r: _panel("quality", quality, report), rid)
    if COST in tabs:
        with tabs[COST]:
            plain_section(COST, "cost", lambda r: _panel("cost", cost_and_models, report), rid)
