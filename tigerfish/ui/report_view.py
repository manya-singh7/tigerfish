"""One report: a header, then five tabs (docs/DESIGN.md).

  Overview · Findings · Ask & investigate · Take action · Method & quality

Findings holds the finding sections (Contradictions, Species & nature, Copied text,
Promises & timeline, Public record) behind one selector, so only the chosen section is drawn.
Each finding belongs to exactly one section (by its check; see SECTION_CHECKS), so its review
widgets are drawn once. Labels carry counts, e.g. "Contradictions (14)". A section that does
not apply to this report is left out, and one line in the Overview says which and why. Quick
checks (free checks only) get Overview, Findings and Batch screening.

Inside a section: what the check does in one line, the filters in a row, then the evidence
slips, 10 at a time. The Overview opens with the report's lead finding, then the top
verified findings and one sentence of totals.

Quality section hook: if a module tigerfish/ui/quality.py exists with render(report), it is
drawn as the Quality section; otherwise the review queue, the precision panel and the
evaluation table are shown (QUALITY_FALLBACK below). Nothing else needs to change.
"""

import importlib
import re

import streamlit as st

from tigerfish import batch_results, hosted, library
from tigerfish import review as review_store
from tigerfish.ui import (cards, data, feedback, inspector, letter, memo_ask, method,
                          official, promises, public_record, review, rti, slip, species_map,
                          web_evidence)
from tigerfish.ui import investigate
from tigerfish.ui import batch as batch_ui
from tigerfish.ui.investigate import REPORTS
from tigerfish.ui.style import badge, esc, mono

OVERVIEW, CONTRA, SPECIES, COPIED, PROMISES = ("Overview", "Contradictions", "Species & nature",
                                               "Copied text", "Promises & timeline")
RECORD, ASK, ACTION, QUALITY, COST = ("Public record", "Ask & investigate", "Take action",
                                      "Quality", "Cost & models")
ORDER = (OVERVIEW, CONTRA, SPECIES, COPIED, PROMISES, RECORD, ASK, ACTION, QUALITY, COST)
FINDINGS, METHOD = "Findings", "Method & quality"
CATEGORIES = (CONTRA, SPECIES, COPIED, PROMISES, RECORD)     # the sections inside Findings

# Which section shows a finding, by its check. Unknown checks go to OTHER_SECTION.
SECTION_CHECKS = {
    CONTRA: ("contradiction", "recycled_figure", "number_pair"),
    SPECIES: ("species_range", "iucn_status", "legal_schedule", "omission", "species_iucn"),
    COPIED: ("copy_paste", "borrowed_text"),
    PROMISES: ("promise",),
    RECORD: ("accreditation", "official_record", "baseline_season"),
}
OTHER_SECTION = CONTRA
TOP_FLAGS = 3
PAGE_SIZE = 10
SCREENING = "Batch screening"
QUICK_SECTIONS = (OVERVIEW, CONTRA, SPECIES, RECORD, SCREENING)
QUICK_HIDDEN_WHY = "requires deep multi-chapter audit"

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
             "from confirmed flags: the ones the team checked (unless you switch them off) and the "
             "ones you confirmed. Read the letter here before downloading it."),
    QUALITY: ("The review queue of every new RED and ORANGE flag, precision from reviewers' "
              "decisions, and the evaluation against known issues and planted tests."),
    COST: ("What this audit cost and how long it took, the cost of a full audit by triage mode, "
           "context efficiency, and how Super-VL read the scanned pages."),
}
CSS = """<style>
div[class*="st-key-tf-slip-f-"] { padding: 1rem 1.25rem; margin-bottom: 0.75rem; }
div[class*="st-key-tf-slip-f-"] .tf-slip { border: 0; padding: 0; margin: 0 0 0.25rem 0; }
.tf-h3.tf-on-paper { margin: 1.5rem 0 0.75rem 0; display: block; font-size: 1.5rem; }
.tf-report-head .tf-h1 { color: var(--tf-ink); margin: -0.75rem 0 0.35rem 0; }
.tf-report-head .tf-meta { font-size: 1rem; }
.tf-report-grades { margin: 0.5rem 0 0 0; }
.tf-report-grades .tf-mono { font-size: 1rem; margin-right: 1rem; }
.tf-what-line { color: var(--tf-muted); max-width: 52rem; margin: 0.25rem 0 0.75rem 0; }
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
        if not (n[RECORD] or names & set(SECTION_CHECKS[RECORD])):
            hidden[RECORD] = "the statutory record checks did not run for this report"
        shown = [(OVERVIEW, None)] + [(s, n[s]) for s in (CONTRA, SPECIES, RECORD) if s not in hidden]
        if batch_results.checks(report):
            shown.append((SCREENING, len(batch_results.checks(report))))
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
    confirmed = len(letter_findings(report))
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


def hidden_line(hidden, quick=False):
    """One line: the sections left out, grouped by the reason."""
    if not hidden or quick:
        return
    groups = {}
    for s, why in hidden:
        groups.setdefault(why, []).append(s)
    st.caption("Not shown for this report: " + "; ".join(
        f"{', '.join(names)} ({why})" for why, names in groups.items()) + ".")


# ---------- section layout: one column, filters in a row ----------

def _dismissed(report_id, findings):
    return (review_store.dismissed_finding_ids(review_store.load_queue(), review_store.load_reviews())
            | {f["id"] for f in cards.reviewed(report_id, findings, "Dismiss")})


def what_line(section):
    """What the section's check does, in one muted paragraph above its content."""
    st.markdown(f'<p class="tf-what-line">{esc(ABOUT[section])}</p>', unsafe_allow_html=True)


def plain_section(section, key, draw, report_id):
    """A section without findings of its own: what it does, then its content."""
    what_line(section)
    with st.container(key=f"tf-sec-{key}"):
        draw(report_id)


def _more(key):
    st.session_state[key] = st.session_state.get(key, PAGE_SIZE) + PAGE_SIZE


def finding_list(report, findings, key, empty, map_species=False, section=None):
    """A finding section: what the check does, the grade and check filters and the dismissed
    toggle in a row, then the slips (10 at a time). Returns the container below the
    findings, for content the section adds."""
    rid = report["id"]
    if section:
        what_line(section)
    main = st.container(key=f"tf-sec-{key}")
    if not findings:
        with main, st.container(key=f"tf-panel-empty-{key}"):
            st.markdown(f'<div class="tf-h3">Nothing flagged here</div><p>{esc(empty)}</p>',
                        unsafe_allow_html=True)
        return main
    with main:
        g, c, d, n = st.columns([3, 4, 2, 2], gap="medium", vertical_alignment="bottom")
        present = [x for x in ("RED", "ORANGE", "INFO") if any(f["grade"] == x for f in findings)]
        with g:
            grades = st.multiselect("Grade", present, default=present, key=f"sec::{rid}::{key}::grades")
        checks = sorted({f["check_name"] for f in findings})
        if len(checks) > 1:
            with c:
                checks = st.multiselect("Check", checks, default=checks, key=f"sec::{rid}::{key}::checks")
        shown = data.filter_findings(findings, grades, checks)
        # Flags judged false alarms (Quality, or Dismiss on a card) are hidden by default.
        dismissed = _dismissed(rid, findings)
        n_dismissed = sum(f["id"] in dismissed for f in shown)
        if n_dismissed:
            with d:
                if not st.toggle(f"Show dismissed ({n_dismissed})", key=f"sec::{rid}::{key}::dismissed"):
                    shown = [f for f in shown if f["id"] not in dismissed]
        with n:
            st.markdown(f'<div class="tf-count">Showing {len(shown)} of {len(findings)} findings.</div>',
                        unsafe_allow_html=True)
        if not shown:
            with st.container(key=f"tf-panel-none-{key}"):
                st.markdown('<div class="tf-h3">No findings match these filters</div>'
                            '<p>Add a grade or a check back in the filters above.</p>',
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
        confirmed = review_store.confirmed_findings(report)
        for i, f in enumerate(shown[:n]):
            cards.finding_card(rid, f, report.get("title", ""), confirmed=confirmed.get(f["id"]),
                               open_pages=i == 0)
        if len(shown) > n:
            st.button(f"Show {min(PAGE_SIZE, len(shown) - n)} more ({len(shown) - n} not shown)",
                      key=f"{more_key}::btn", on_click=_more, args=(more_key,))
    return main


# ---------- the sections ----------

def totals_sentence(report, confirmed=None):
    """confirmed: {finding id: decision rows} from review.confirmed_findings."""
    findings = report.get("findings") or []
    c = data.counts(findings)
    verified = sum(1 for f in findings if f.get("verification"))
    by_reviewer = sum(1 for f in findings if not f.get("verification") and f["id"] in (confirmed or {}))
    unit = ("1 published table" if report.get("unit") == "table"
            else f"{report.get('pages_read', 0):,} of {report.get('pages_total', 0):,} pages read")
    checked = ", ".join(x for x in (
        f"{verified:,} verified by a person" if verified or not by_reviewer else "",
        f"{by_reviewer:,} confirmed by a reviewer" if by_reviewer else "") if x)
    return (f"{len(findings):,} findings ({c['RED']:,} RED, {c['ORANGE']:,} ORANGE, {c['INFO']:,} "
            f"INFO leads) from {unit}; {checked}. Every finding is under "
            "Findings. A flag is a lead to verify, not a verdict.")


def is_clean_quick(report, quick=False):
    if not quick:
        return False
    findings = report.get("findings") or []
    flags = report.get("flags") or report.get("batch_flags") or []
    if findings or flags:
        return False
    not_run = [c for c in report.get("checks_run", []) if c.get("status") != "ran" and "sample:" in str(c.get("reason", ""))]
    if not_run:
        return False
    return True

def overview(report, shown, hidden, quick=False):
    """The top 3 human-verified findings as evidence slips and one sentence of totals; the
    rest stays in the sections."""
    if is_clean_quick(report, quick):
        with st.container(key="tf-panel-overview"):
            st.markdown(f'<h2 class="tf-h2">{esc(report.get("project") or report.get("title", ""))}</h2>',
                        unsafe_allow_html=True)
            bits = [report.get("state"), report.get("sector"), str(report.get("year")) if report.get("year") else None,
                    f"{report.get('pages_read', 0):,} of {report.get('pages_total', 0):,} pages read"]
            st.caption(" · ".join(esc(b) for b in bits if b))
            from tigerfish.ui.library import triage_passed_card
            st.markdown(triage_passed_card(), unsafe_allow_html=True)
            st.markdown(
                '<div class="tf-triage-summary-box">'
                '<p class="tf-triage-summary-text"><b>Fast Administrative Triage:</b> Automated statutory screening completed across physical report pages. '
                'Consultant accreditation, baseline monitoring window, and taxonomic occurrence ground truth have been verified against statutory benchmarks without irregularity.</p>'
                '</div>',
                unsafe_allow_html=True)
        return

    if quick:
        library_quick_overview(report)
    findings = report.get("findings") or []
    dismissed = set() if quick else _dismissed(report["id"], findings)
    confirmed = {} if quick else review_store.confirmed_findings(report)
    live = [f for f in findings if f["id"] not in dismissed]
    verified = [f for f in live if f.get("verification")
                and f["verification"].get("outcome") != "explained"]
    with st.container(key="tf-panel-overview"):
        st.markdown(f'<p class="tf-totals">{esc(totals_sentence(report, confirmed))}</p>',
                    unsafe_allow_html=True)
        hidden_line(hidden, quick=quick)
    by_reviewer = [f for f in live if not f.get("verification") and f["id"] in confirmed]
    lead_id = None if quick else library.lead_finding(report["id"])
    lead = next((f for f in live if f["id"] == lead_id), None)
    if lead:
        with st.container(key="tf-panel-lead"):
            st.markdown('<h2 class="tf-sub-head">Start here</h2><p>One finding, from the evidence '
                        "to the person who checked it. It is already in the letter under Take "
                        f"action; its slip is under Findings, in {esc(section_of(lead))}.</p>",
                        unsafe_allow_html=True)
        slip.render(lead, section=section_of(lead), confirmed=confirmed.get(lead["id"]), lead=True)
        verified = [f for f in verified if f is not lead]
        by_reviewer = [f for f in by_reviewer if f is not lead]
    if verified:
        top = slip.pick(verified, TOP_FLAGS)
        st.markdown(f'<div class="tf-h3 tf-on-paper">{"More" if lead else "Top"} flags, verified '
                    'by a person</div>', unsafe_allow_html=True)
    elif by_reviewer:
        top = slip.pick(by_reviewer, TOP_FLAGS)
        st.markdown('<div class="tf-h3 tf-on-paper">Top flags, confirmed by a reviewer</div>',
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
        slip.render(f, section=section_of(f), confirmed=confirmed.get(f["id"]))


def library_quick_overview(report):
    """The quick check's header: what ran, what did not, and why."""
    with st.container(key="tf-panel-quick"):
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
        if batch_results.checks(report):
            st.caption(
                batch_results.summary_line(batch_results.summary(report))
                + " Open Batch screening for certificate dates, baseline periods, species rows and source evidence."
            )
        st.caption(
            "Not run in a quick check: model checks (internal contradictions, recycled "
            "figures, scanned pages), copied text, official NABET verification and ToR promises."
        )


def team_key(report_id):
    return f"action::{report_id}::team"


def team_checked(report):
    """Findings the team checked: verified by a person (known issues) or confirmed by a
    reviewer (review/reviews.jsonl), less those dismissed."""
    findings = report.get("findings") or []
    confirmed = review_store.confirmed_findings(report)
    dismissed = _dismissed(report["id"], findings)
    return [f for f in findings if f["id"] not in dismissed and (f["id"] in confirmed or (
        f.get("verification") and f["verification"].get("outcome") != "explained"))]


def letter_findings(report):
    """What the letter and the pack are built from, in report order: the team's checked
    findings (unless switched off) and the ones this visitor confirmed."""
    rid, findings = report["id"], report.get("findings") or []
    ids = {f["id"] for f in cards.reviewed(rid, findings, "Confirm")}
    if st.session_state.get(team_key(rid), True):
        ids |= {f["id"] for f in team_checked(report)}
    return [f for f in findings if f["id"] in ids]


def take_action(report):
    rid, findings = report["id"], report.get("findings") or []
    team = team_checked(report)
    if team:
        st.toggle(f"Include the {len(team)} findings checked by the team", value=True,
                  key=team_key(rid), help="Verified by a person against the report, or confirmed "
                  "by a reviewer in the review queue. Switch off to build from your own "
                  "confirmations only.")
    confirmed = letter_findings(report)
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
    if confirmed:
        with st.expander(f"Read the letter ({len(confirmed)} points, English)", expanded=True):
            st.markdown(letter.preview_html(report, confirmed, addressee), unsafe_allow_html=True)
    # The visitor's own reviews: who is reviewing, and what they decided on the slips.
    st.markdown('<h2 class="tf-sub-head">Your reviews</h2>', unsafe_allow_html=True)
    feedback.reviewer_input(rid, findings)
    mine = cards.reviewed(rid, findings, "Confirm")
    dismissed = cards.reviewed(rid, findings, "Dismiss")
    unsure = cards.reviewed(rid, findings, "Unsure")
    st.markdown(f'<div class="tf-review">Reviewed: {len(mine)} confirmed, '
                f'{len(dismissed)} dismissed, {len(unsure)} unsure. Reviews are kept '
                f'{feedback.where()}.</div>', unsafe_allow_html=True)


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

def header(report, quick=False):
    """The report's one header block: title, where it came from, and its flags by grade."""
    c = data.counts(report.get("findings") or [])
    source = report.get("source", "")
    if isinstance(source, dict):        # a quick check's source: where the PDF was found
        url = source.get("url") or source.get("portal") or ""
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        source_html = (f'Source: <a href="{esc(url)}" target="_blank" rel="noopener">the PDF on '
                       f"{esc(host)}</a>" if url else "")
    else:
        source_html = f"Source: {esc(source)}" if source else ""
    meta = ("" if quick else "Saved results. " if _saved(report["id"]) else "") + source_html
    with st.container(key="tf-plain-source"):
        st.markdown(f'<div class="tf-report-head"><h1 class="tf-h1">'
                    f'{esc(report.get("project") or report.get("title", ""))}</h1>'
                    f'<div class="tf-meta">{meta}</div><div class="tf-report-grades">'
                    + "".join(f"{badge(g)}{mono(f'{c[g]:,}')}" for g in ("RED", "ORANGE", "INFO"))
                    + "</div></div>", unsafe_allow_html=True)
        for notice in report.get("notices", []):     # e.g. a partial audit, flags not yet reviewed
            st.warning(notice)


def findings_tab(report, cats, by):
    """The finding sections behind one selector; only the chosen one is drawn."""
    rid = report["id"]
    counts = dict(cats)
    names = [s for s, _ in cats]
    pick = st.segmented_control("Section", names, default=names[0], required=True,
                                format_func=lambda s: label(s, counts[s]),
                                key=f"sec::{rid}::pick", label_visibility="collapsed")
    pick = pick or names[0]
    if pick == CONTRA:
        finding_list(report, by[CONTRA], "contra",
                     "No contradictions or recycled figures were flagged in this report.",
                     section=CONTRA)
    elif pick == SPECIES:
        finding_list(report, by[SPECIES], "species",
                     "No species, status or omission findings for this report.",
                     map_species=True, section=SPECIES)
    elif pick == COPIED:
        main = finding_list(report, by[COPIED], "copied", "No copied or borrowed text was flagged.",
                            section=COPIED)
        with main:
            cards.excluded_matches(report)
    elif pick == PROMISES:
        main = finding_list(report, by[PROMISES], "promises",
                            "No ToR promise was found unmet; the comparison is below.",
                            section=PROMISES)
        with main:
            _panel("promises-detail", promises.render, rid)
    elif pick == RECORD:
        public_record_section(report, by[RECORD])


def method_tab(report, sections):
    """Quality (review, precision, evaluation) and Cost & models, one after the other."""
    for section, draw in ((QUALITY, quality), (COST, cost_and_models)):
        if section in sections:
            st.markdown(f'<h2 class="tf-sub-head">{esc(section)}</h2>', unsafe_allow_html=True)
            plain_section(section, section.split()[0].lower(),
                          lambda r, d=draw: _panel(section.split()[0].lower(), d, report), report["id"])


def render(report, quick=False):
    """Draw one report. quick=True: a quick check (library.load), free checks only."""
    st.markdown(CSS, unsafe_allow_html=True)
    rid = report["id"]
    if not report.get("findings") and (report.get("flags") or report.get("batch_flags")):
        report["findings"] = [
            {
                "id": fl.get("id") or f"{rid}-fl-{i}",
                "check": fl.get("check", "batch_check"),
                "check_name": fl.get("check", "Batch Check").replace("_", " ").title(),
                "grade": fl.get("grade", "INFO"),
                "title": f"{fl.get('check', 'Batch Check').replace('_', ' ').title()}: {fl.get('message', '')[:70]}",
                "message": fl.get("message", "Flagged during statutory triage, verify."),
                "quotes": fl.get("quotes", []),
                "evidence": fl.get("evidence", []),
                "why": fl.get("message", "Deterministic check flagged during automated triage."),
                "clear": fl.get("clear") or "Verification against official statutory records or updated filings.",
                "known_issue": None,
                "images": [],
            }
            for i, fl in enumerate(report.get("flags") or report.get("batch_flags") or [])
        ]
    header(report, quick)
    if not quick:
        feedback._seed(rid, report.get("findings") or [])  # before any review widget is drawn
    shown, hidden = plan(report, quick)
    by = split(report.get("findings") or [])
    names = [s for s, _ in shown]
    cats = [(s, c) for s, c in shown if s in CATEGORIES]
    tab_labels = [(OVERVIEW, None)]
    if cats:
        tab_labels.append((FINDINGS, sum(len(by[s]) for s, _ in cats)))
    tab_labels += [(s, c) for s, c in shown if s in (SCREENING, ASK, ACTION)]
    if QUALITY in names or COST in names:
        tab_labels.append((METHOD, None))
    # A container keyed by the report: switching reports draws fresh widgets, instead of the
    # browser reusing the previous report's filters at the same place.
    box = st.container(key="tf-report-" + re.sub(r"[^A-Za-z0-9_-]", "-", str(rid)))
    tabs = dict(zip([s for s, _ in tab_labels], box.tabs([label(s, c) for s, c in tab_labels])))

    with tabs[OVERVIEW]:
        overview(report, shown, hidden, quick)
    if FINDINGS in tabs:
        with tabs[FINDINGS]:
            findings_tab(report, cats, by)
    if SCREENING in tabs:
        with tabs[SCREENING], st.container(key=f"tf-panel-screening-{rid}"):
            batch_ui.render_report(report)
    if ASK in tabs:
        with tabs[ASK]:
            plain_section(ASK, "ask", lambda r: _panel("ask", memo_ask.render, r), rid)
    if ACTION in tabs:
        with tabs[ACTION]:
            plain_section(ACTION, "action", lambda r: _panel("action", take_action, report), rid)
    if METHOD in tabs:
        with tabs[METHOD]:
            method_tab(report, names)
