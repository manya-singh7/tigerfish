"""Review queue tab: walk the open report's queue (review.queue_for: every RED/ORANGE flag)
in order, record decisions, show precision (tigerfish/ui/quality.py: the 20-judged rule).

Decisions go to review/reviews.jsonl (two independent decisions for double-review flags).
A single-review decision is also saved to the card reviews (feedback/feedback.json), so the
finding's card and the per-check precision table show it.

Hosted app (tigerfish/hosted.py): the committed decisions (hand verifications in the queue,
and review/reviews.jsonl if it is committed) are shown read-only and the precision panel uses
only them. A visitor's decisions stay in their browser session (SESSION_ROWS), shown as
"Your decision", and can be downloaded; nothing is written to review/.
"""

import streamlit as st

from tigerfish import hosted, review
from tigerfish.ui import feedback
from tigerfish.ui.cards import quote_label
from tigerfish.ui.style import badge, esc

POS_KEY = "review::pos"
NAME_KEY = "review::name"
SESSION_ROWS = "review::session_rows"     # hosted: this visitor's decisions


def session_rows():
    return st.session_state.setdefault(SESSION_ROWS, [])


def pct(x):
    return "-" if x is None else f"{x:.0%}"


def precision_panel(queue, reviews):
    from tigerfish.ui import quality
    quality.precision_stats(queue, reviews)


def session_rows_for(report_id):
    """This visitor's decisions on one report (older rows without a report id: Great Nicobar)."""
    return [r for r in session_rows() if review.row_report(r) == report_id]


def item_card(item, reviews, reviewer):
    by = review.decisions(item, reviews)
    verified = item.get("verified")
    with st.container(border=True):
        tag = " · double review: judge on your own" if item["double_review"] and not verified else ""
        tag += " · human-verified" if verified else ""
        st.markdown(f'{badge(item["grade"])}<span class="tf-check">{esc(item["check_name"])} · '
                    f'{esc(item["flag_id"])}{esc(tag)}</span>'
                    f'<div class="tf-card-title">'
                    + (esc(item["title"]) + " · " if item.get("title") else "")
                    + (f'Pages {esc(", ".join(map(str, item["pages"])))}' if item["pages"]
                       else "No page (a public record)") + '</div>',
                    unsafe_allow_html=True)
        quotes = item["quotes"]
        cols = st.columns(len(quotes)) if len(quotes) > 1 else [st.container()]
        for col, q in zip(cols, quotes):
            also = f' (also on pp. {", ".join(map(str, q["also_on"]))})' if q.get("also_on") else ""
            col.markdown(f'<div class="tf-quote-label">{esc(quote_label(q))}{esc(also)}</div>'
                         f'<div class="tf-quote">{esc(q["text"])}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="tf-line" style="margin-top:0.6rem"><b>Model\'s reason</b> &nbsp;'
                    f'{esc(item["reason"])}</div>', unsafe_allow_html=True)
        if item.get("answers"):
            st.caption("Ultra's answers: " + ", ".join(f"{k} = {v}" for k, v in item["answers"].items()))
        for u in item.get("urls") or []:
            st.caption(f"Match: {u}")
        if verified:
            st.success(f"Already reviewed: {review.DECISIONS[verified['decision']]}, by "
                       f"{verified['by']} ({verified['on']}), checked by hand against the PDF"
                       + (f" as known issue {verified['known_issue']}" if verified.get("known_issue") else "")
                       + ". It counts toward precision; no further decision is needed.")
        else:
            st.caption("Check the quotes against the PDF pages before deciding.")

        mine = by.get(review.name_key(reviewer))
        others = [r for k, r in by.items() if k != review.name_key(reviewer)]
        # double review: hidden until you decide (a hand verification is shown: it is final)
        if others and (not item["double_review"] or mine or verified):
            st.caption("Other decisions: " + "; ".join(
                f"{r['reviewer']}: {review.DECISIONS[r['decision']]}" + (f" ({r.get('note') or r.get('comment')})" if (r.get('note') or r.get('comment')) else "")
                for r in others))
        if mine:
            st.caption(f"Your decision: {review.DECISIONS[mine['decision']]}"
                       + (f" ({mine.get('note') or mine.get('comment')})" if (mine.get('note') or mine.get('comment')) else "") + ". You can change it.")
        note = st.text_input("Note (optional)", key=f"review::note::{item['flag_id']}")
        b = st.columns(3)
        for col, (code, label) in zip(b, review.DECISIONS.items()):
            if col.button(label, key=f"review::{code}::{item['flag_id']}", disabled=not reviewer,
                          width="stretch"):
                return code, note
    return None, None


def title_of(report):
    return report.get("title") or report["id"]


def render(report_id, report=None):
    if report is None:
        from tigerfish.ui import data
        report = data.load(report_id)
    queue = review.queue_for(report)
    items = queue["items"]
    st.markdown(f"#### Review queue: {esc(title_of(report))} ({len(items)} RED/ORANGE flag"
                f"{'s' if len(items) != 1 else ''})")
    if not items:
        st.info("No RED or ORANGE flags in this report, so there is nothing to review.")
        return
    in_session = hosted.is_hosted()
    committed = review.load_reviews(report_id=report_id)
    reviews = review.with_rows(committed, session_rows_for(report_id)) if in_session else committed
    pos_key, name_key = f"{POS_KEY}::{report_id}", NAME_KEY
    double = (f"{queue['double_review']} flags are judged by both reviewers independently. "
              if queue.get("double_review") else "")
    st.markdown(f"Every new RED/ORANGE flag of this report, in order: {esc(queue['order'])}. {double}"
                + ("The team's saved decisions are shown read-only. Your decisions stay in this "
                   "browser session only (download them below); they never change the saved "
                   "review or the precision figures." if in_session
                   else "Decisions are saved to review/reviews.jsonl."))
    precision_panel(queue, committed)
    st.write("")

    st.session_state.setdefault(NAME_KEY, st.session_state.get(feedback.REVIEWER_KEY, ""))
    reviewer = st.text_input("Reviewer name (required)", key=NAME_KEY).strip()
    if not reviewer:
        st.caption("Enter your name to record decisions.")
    if pos_key not in st.session_state:
        # open on the first flag still needing a decision (human-verified ones are done)
        st.session_state[pos_key] = review.next_index(queue, reviews, reviewer) or 0
    pos = min(st.session_state[pos_key], len(items) - 1)
    st.session_state[POS_KEY] = pos             # the open report's position (tests read it)

    left = sum(review.needs(it, reviews, reviewer) for it in items) if reviewer else None
    st.progress(pos / max(len(items) - 1, 1), text=f"Flag {pos + 1} of {len(items)}"
                + (f" · {left} still need your decision" if left is not None else ""))
    nav = st.columns(3)
    if nav[0].button("Previous", disabled=pos == 0, width="stretch"):
        st.session_state[pos_key] = pos - 1
        st.rerun()
    if nav[1].button("Next", disabled=pos >= len(items) - 1, width="stretch"):
        st.session_state[pos_key] = pos + 1
        st.rerun()
    if nav[2].button("Next needing me", disabled=not reviewer, width="stretch"):
        nxt = review.next_index(queue, reviews, reviewer, start=pos + 1)
        st.session_state[pos_key] = pos if nxt is None else nxt
        st.rerun()

    decision, note = item_card(items[pos], reviews, reviewer)
    if decision:
        it = items[pos]
        try:
            if in_session:
                session_rows().append(review.make_row(it["flag_id"], reviewer, decision, note or "",
                                                      report_id))
            else:
                review.record(it["flag_id"], reviewer, decision, note or "", report_id=report_id)
            if not it["double_review"] and it.get("finding_id"):
                fid = it["finding_id"]
                feedback.save(feedback.record(feedback.load(), report_id,
                                              {"id": fid, "check": it["check"],
                                               "check_name": it["check_name"], "grade": it["grade"]},
                                              review.AS_FEEDBACK[decision], reviewer, note or ""))
                st.session_state.pop(feedback.widget_key(report_id, fid), None)  # card re-seeds
                st.session_state.pop(feedback.note_key(report_id, fid), None)
        except OSError as e:
            st.error(f"Could not save the decision ({e}). Reviews need a writable review/ folder.")
            return
        reviews = (review.with_rows(committed, session_rows_for(report_id)) if in_session
                   else review.load_reviews(report_id=report_id))
        nxt = review.next_index(queue, reviews, reviewer, start=pos + 1)
        if nxt is not None:
            st.session_state[pos_key] = nxt
        st.rerun()

    if in_session:
        rows = session_rows_for(report_id)
        st.download_button(f"Download your decisions (.jsonl, {len(rows)})", review.rows_jsonl(rows),
                           file_name=f"tigerfish_my_reviews_{report_id}.jsonl",
                           mime="application/json", disabled=not rows)
    elif review.REVIEWS.exists():
        st.download_button("Download reviews (.jsonl)", review.REVIEWS.read_bytes(),
                           file_name="reviews.jsonl", mime="application/json")
