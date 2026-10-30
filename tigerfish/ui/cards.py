"""Summary strip and finding cards (each finding is an evidence slip, tigerfish/ui/slip.py)."""

import re

import streamlit as st

from tigerfish import knowable, paper_trail, public_record, species_photos
from tigerfish.ui import badges, data, efficiency, feedback, investigate, official, slip
from tigerfish.ui import public_record as record_ui
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


def tavily_credits(report):
    """(total, [(what, credits)]): Tavily credits for this report's audit plus the saved
    web-context checks (official record, knowable at the time, public record, photos)."""
    rid = report["id"]
    parts = [("audit", (report.get("cost") or {}).get("tavily_credits") or 0)]
    rec = official.load(rid)
    if rec:
        parts.append(("official record", rec["tavily"]["credits"]))
    k = knowable.load(rid)
    if k:
        parts.append(("knowable at the time", k["tavily"]["credits"]))
    pr = public_record.load(rid)
    if pr:
        parts.append(("public record", pr["tavily"].get("credits", 0)))
    ph = species_photos.load()
    if ph:
        parts.append(("species photos", ph["tavily"].get("credits_by_report", {}).get(rid, 0)))
    trail = paper_trail.load(rid)
    if trail:
        parts.append(("paper trail", trail["tavily"].get("credits", 0)))
    parts = [(w, c) for w, c in parts if c]
    return sum(c for _, c in parts), parts


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
    credits, parts = tavily_credits(report)
    cost_value = f"${usd:.2f}" if usd is not None else "-"
    base = cost.get("note") or "Nebius models"
    cost_note = (f"{base}, plus {credits} Tavily credits ("
                 + ", ".join(f"{w} {c}" for w, c in parts) + ")") if credits else base
    if cost.get("gbif_calls"):
        cost_note += "; GBIF is free"
    eff = efficiency.report_total(report["id"])
    if eff:
        cost_note += f". {efficiency.line(eff)} ({efficiency.NOT_MEASURED_NOTE.lower()})"
    cols = st.columns(5)
    cols[0].markdown(stat("Pages read", pages, pages_note), unsafe_allow_html=True)
    cols[1].markdown(stat("Findings", str(sum(c.values())),
                          f"{c['RED']} red, {c['ORANGE']} orange, {c['INFO']} info"),
                     unsafe_allow_html=True)
    cols[2].markdown(stat("Checks run", str(len(report["checks"])), "see How it works"),
                     unsafe_allow_html=True)
    cols[3].markdown(stat("Cost", cost_value, base), unsafe_allow_html=True)
    cols[4].markdown(stat("Time", fmt_time(cost.get("approx_seconds")),
                          cost.get("time_note", "API time, estimated")),
                     unsafe_allow_html=True)
    if cost_note != base:        # the details behind the cost, under the row, not in a card
        st.caption(f"Cost: {cost_note}.".replace("$", "\\$").replace("..", "."))


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


def card_key(report_id, f):
    return "tf-slip-f-" + re.sub(r"[^A-Za-z0-9_-]", "-", f"{report_id}-{f['id']}")


def finding_card(report_id, f, report_title="", confirmed=None, open_pages=False):
    """One finding: its evidence slip (page crop, grade, check, quote, the whole reason, the
    person's check), then the evidence in an expander, the full pages, Investigate and the
    review. confirmed: reviewers' decision rows confirming it (review.confirmed_findings).
    open_pages: the highlighted pages start open (the first card of a section)."""
    with st.container(key=card_key(report_id, f)):
        photo = record_ui.photo_html(report_id, f["id"])
        has_crop = bool(slip.crops_for(f))
        extra = (badges.html(badges.finding_badges(f, badges.readers(report_id)))
                 + record_ui.knowable_html(report_id, f["id"])
                 + (photo if has_crop else ""))
        # A hand check is in the badges (with the name): no second "Verified by a person" line.
        slip.render(f, extra=extra, photo=None if has_crop else photo, confirmed=confirmed,
                    full_reason=True, person=not f.get("verification"))

        with st.expander("Evidence, why it was flagged and what would clear it"):
            known = (f'<div class="tf-meta">Matches known issue {esc(f["known_issue"])}</div>'
                     if f.get("known_issue") else "")
            quotes = "".join(f'<div class="tf-quote-label">{esc(quote_label(q))}</div>'
                             f'<div class="tf-quote">{esc(q["text"])}</div>'
                             for q in f["quotes"] if q.get("text"))
            st.markdown(verification_html(f.get("verification")) + known
                        + f'<div class="tf-message">{esc(f["message"])}</div>' + quotes
                        + f'<div style="margin-top:0.7rem">{evidence_html(f["evidence"], f.get("check"))}</div>'
                        f'<div class="tf-line" style="margin-top:0.6rem"><b>Why flagged</b> &nbsp;{esc(f["why"])}</div>'
                        f'<div class="tf-line"><b>What would clear this</b> &nbsp;{esc(f["clear"])}</div>',
                        unsafe_allow_html=True)

        images = list(dict.fromkeys(f.get("images") or []))
        if images:
            with st.expander("Show highlighted page" + ("s" if len(images) > 1 else ""),
                             expanded=open_pages):
                paths = [p for p in (data.image_path(rel) for rel in images) if p]
                if not paths:
                    st.caption("The page images for this finding are not in results/pages/.")
                for col, path in zip(st.columns(len(paths)) if paths else [], paths):
                    col.image(str(path), caption=f"Page {page_no(path)}", width="stretch")

        investigate.render(report_id, f, report_title)

        st.caption("Community feedback is saved as a reviewer suggestion and does not modify the verified finding without audit review.")
        feedback.review_widgets(report_id, f)


def page_no(path):
    return int(path.stem.rsplit("_p", 1)[1])       # file names end in _p<NNNN>.png

def excluded_matches(report):
    """Collapsed list of copied-text matches excluded as GREY self-matches (the matched
    document is this report's own, e.g. the lender's or the board's copy). Never hidden."""
    rows = report.get("excluded_matches") or []
    if not rows:
        return
    with st.expander(f"Excluded matches ({len(rows)})", expanded=False):
        st.caption("Copied-text matches graded GREY, not flagged: the matching document is this "
                   "report's own (same project), so a match is expected.")
        for e in rows:
            quote = e["quote"] if len(e["quote"]) <= 220 else e["quote"][:217] + "..."
            st.markdown(
                f'<div class="tf-excluded">{badge("GREY")} <b>p.{e["page"]}</b> · {esc(e["label"])}'
                f'<br><a href="{esc(e["url"])}" target="_blank">{esc(e.get("title") or e["url"])}</a>'
                f'<br><code>{esc(e["url"])}</code>'
                f'<br>Why: {esc(e["why"])}. Overlap: longest run {e["longest_run"]} words, '
                f'8-gram {e["ngram"]:.0%}.<br>Ours: &ldquo;{esc(quote)}&rdquo;</div>',
                unsafe_allow_html=True)
