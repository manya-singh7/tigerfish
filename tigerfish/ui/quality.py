"""Review quality in the app, from saved files (tigerfish/quality.py):

  library_section()        library home: per report, flags, reviewed, confirmed, dismissed,
                           unsure and precision, plus an overall line
  reviews_panel(report)    a report's Findings tab: "Team reviews (saved)" (committed files)
                           apart from "Your reviews" (this browser session on the hosted app,
                           feedback/feedback.json locally)
  precision_stats(...)     the Review queue tab's four figures, with the 20-judged rule
"""

import streamlit as st

from tigerfish import library, quality, review
from tigerfish.ui import feedback
from tigerfish.ui.style import esc, stat

TOO_FEW = "Too few judged"


def _review_stamp():
    files = [review.QUEUE, review.REVIEWS]
    return tuple((str(f), f.stat().st_mtime) if f.exists() else (str(f), 0) for f in files)


@st.cache_data(show_spinner=False)
def _rows(stamp):
    from tigerfish.ui import library as library_ui
    rows = []
    for e in library_ui.entries():
        if e.get("audit_type") == library.QUICK:
            continue
        try:
            report = library.load(e)
        except (OSError, ValueError):
            continue
        rows.append({**quality.report_quality(report), "type": e["audit_type"],
                     "project": e["project"]})
    return rows


def rows():
    from tigerfish.ui import library as library_ui
    return _rows(library_ui._stamp() + _review_stamp())


def library_section():
    """The "Quality" section on the library home."""
    data = rows()
    if not data:
        return
    with st.container(key="tf-panel-quality"):
        st.markdown("#### Quality")
        st.markdown(esc(quality.overall_line(quality.overall(data))))
        table = [{"Report": r["title"], "Type": r["type"], "Flags (RED/ORANGE)": r["flags"],
                  "Reviewed": r["reviewed"], "Confirmed": r["confirmed"], "Dismissed": r["dismissed"],
                  "Unsure": r["unsure"], "Disputed": r["disputed"], "Precision": r["text"]}
                 for r in data]
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption("From the team's saved reviews only (hand checks against the PDF and "
                   "review/reviews.jsonl); reviews made in a browser session are not counted. "
                   f"Precision = confirmed / (confirmed + dismissed), shown once {quality.MIN_JUDGED} "
                   "flags are judged, with a 95% Wilson interval.")


def headline(k, n, what="precision"):
    """(value, note) for a stat box: ("78%", "62-89%, 27 judged") or ("Too few judged", ...)."""
    if n < quality.MIN_JUDGED:
        return TOO_FEW, quality.estimate(k, n, what=what)
    lo, hi = quality.wilson(k, n)
    return f"{k / n:.0%}", f"95% interval {lo * 100:.0f}-{hi * 100:.0f}%, {n} judged"


def precision_stats(queue, reviews):
    """Reviewed, precision, random sample and reviewer agreement (the 20-judged rule)."""
    p = review.precision(queue, reviews)
    a = review.agreement(queue, reviews)
    random_items = [i for i in queue["items"] if i.get("group") == "random"]
    cols = st.columns(4)
    cols[0].markdown(stat("Reviewed", f"{p['reviewed']} of {p['total']}",
                          f"{p['unsure']} unsure, {p['disputed']} disputed, "
                          f"{p['waiting']} waiting for a 2nd reviewer"), unsafe_allow_html=True)
    value, note = headline(p["real"], p["judged"])
    cols[1].markdown(stat("Precision", value, f"{note}; {p['real']} confirmed of {p['judged']} "
                                              "judged (unsure and disputed left out)"),
                     unsafe_allow_html=True)
    if random_items:
        rnd = review.precision(queue, reviews, random_items)
        value, note = headline(rnd["real"], rnd["judged"])
        cols[2].markdown(stat("Precision, random sample", value,
                              f"{note}; the fair sample (the top of the queue was hand-picked)"),
                         unsafe_allow_html=True)
    else:
        cols[2].markdown(stat("Precision, random sample", "No random sample",
                              "this report's queue is in grade order, not a random draw"),
                         unsafe_allow_html=True)
    if a["both_reviewed"] < quality.MIN_JUDGED:
        value, note = TOO_FEW, quality.agreement_text(a)
    else:
        lo, hi = quality.wilson(a["agree"], a["both_reviewed"])
        kappa = "" if a["kappa"] is None else f"; Cohen's kappa {a['kappa']:.2f}"
        value = f"{a['rate']:.0%}"
        note = f"95% interval {lo * 100:.0f}-{hi * 100:.0f}%, {a['both_reviewed']} flags judged by two people{kappa}"
    cols[3].markdown(stat("Reviewer agreement", value,
                          f"{note} ({a['agree']} agree; {a['double_total']} marked for double review)"),
                     unsafe_allow_html=True)


def per_check(queue, reviews):
    """Team reviews per check, in the shape of feedback.precision() rows."""
    out = {}
    for it in queue["items"]:
        v = review.verdict(it, reviews)
        if v not in ("real", "false_alarm", "unsure"):
            continue
        r = out.setdefault(it.get("check_name") or it.get("check"),
                           {"check": it.get("check_name") or it.get("check"),
                            "confirmed": 0, "dismissed": 0, "unsure": 0})
        r[{"real": "confirmed", "false_alarm": "dismissed", "unsure": "unsure"}[v]] += 1
    rows = []
    for r in sorted(out.values(), key=lambda r: r["check"]):
        decided = r["confirmed"] + r["dismissed"]
        rows.append({**r, "reviewed": decided + r["unsure"],
                     "precision": r["confirmed"] / decided if decided else None})
    return rows


def your_label():
    return ("Your reviews (this browser session)" if feedback.in_session()
            else "Your reviews (this computer, feedback/feedback.json)")


def reviews_panel(report, entries=None):
    """Team reviews (saved) and your reviews, kept apart."""
    entries = feedback.load() if entries is None else entries
    queue = review.queue_for(report)
    team = review.load_reviews(report_id=report["id"])
    q = quality.report_quality(report, queue, team)

    st.markdown("**Team reviews (saved)**")
    if q["reviewed"]:
        st.markdown(esc(f"{q['reviewed']} of {q['flags']} RED/ORANGE flags reviewed: "
                        f"{q['confirmed']} confirmed, {q['dismissed']} dismissed, {q['unsure']} "
                        f"unsure" + (f", {q['disputed']} disputed" if q["disputed"] else "")
                        + f". Precision: {q['text']}."))
        st.markdown(feedback.precision_table(per_check(queue, team)))
    else:
        st.caption(f"No team reviews saved for this report yet ({q['flags']} RED/ORANGE flags "
                   "to review). Hand checks are added with scripts/import_reviews.py.")

    st.markdown(f"**{your_label()}**")
    mine = feedback.precision(entries, report["id"])
    if mine:
        st.markdown(feedback.precision_table(mine))
    else:
        st.caption("You have not reviewed any flags of this report"
                   + (" in this session." if feedback.in_session() else " on this computer."))
    st.caption("Precision = confirmed / (confirmed + dismissed); unsure reviews are counted but "
               f"left out. A percentage is shown once {quality.MIN_JUDGED} flags are judged, "
               "with a 95% Wilson interval.")


def render(report):
    """Render the Quality section of a report (review queue, feedback panel, evaluation)."""
    from tigerfish.ui import feedback, method, review
    rid = report["id"]
    review.render(rid)
    st.write("")
    feedback.panel(rid, report.get("findings") or [])
    st.write("")
    method.render_evaluation(with_costs=False)

