"""Review queue tab: walk review/review_queue.json in order, record decisions, show precision.

Decisions go to review/reviews.jsonl (two independent decisions for double-review flags).
A single-review decision is also saved to the card reviews (feedback/feedback.json), so the
finding's card and the per-check precision table show it.
"""

import streamlit as st

from tigerfish import review
from tigerfish.ui import feedback
from tigerfish.ui.cards import quote_label
from tigerfish.ui.style import badge, esc, stat

POS_KEY = "review::pos"
NAME_KEY = "review::name"


def pct(x):
    return "-" if x is None else f"{x:.0%}"


def precision_panel(queue, reviews):
    p = review.precision(queue, reviews)
    a = review.agreement(queue, reviews)
    rnd = review.precision(queue, reviews, [i for i in queue["items"] if i["group"] == "random"])
    top = review.precision(queue, reviews, [i for i in queue["items"] if i["group"] == "top30"])
    cols = st.columns(4)
    cols[0].markdown(stat("Reviewed", f"{p['reviewed']} of {p['total']}",
                          f"{p['unsure']} unsure, {p['disputed']} disputed, "
                          f"{p['waiting']} waiting for a 2nd reviewer"), unsafe_allow_html=True)
    cols[1].markdown(stat("Precision", pct(p["precision"]),
                          f"{p['real']} real of {p['judged']} judged (unsure and disputed left out)"),
                     unsafe_allow_html=True)
    cols[2].markdown(stat("Precision, random part", pct(rnd["precision"]),
                          f"{rnd['judged']} judged; the fair sample (top 30 was hand-picked: "
                          f"{pct(top['precision'])} of {top['judged']})"), unsafe_allow_html=True)
    kappa = "" if a["kappa"] is None else f"; Cohen's kappa {a['kappa']:.2f}"
    cols[3].markdown(stat("Reviewer agreement", pct(a["rate"]),
                          f"{a['agree']} of {a['both_reviewed']} double-review flags agree "
                          f"({a['double_total']} marked){kappa}"), unsafe_allow_html=True)


def queue_section(report_id):
    """For the Precision panel on the Findings tab (nothing if there is no queue)."""
    queue = review.load_queue()
    if queue and queue["report_id"] == report_id:
        st.markdown("**Review queue** (all new RED/ORANGE flags of the full audit; see the "
                    "Review queue tab)")
        precision_panel(queue, review.load_reviews())


def item_card(item, reviews, reviewer):
    by = review.decisions(item, reviews)
    verified = item.get("verified")
    with st.container(border=True):
        tag = " · double review: judge on your own" if item["double_review"] and not verified else ""
        tag += " · human-verified" if verified else ""
        st.markdown(f'{badge(item["grade"])}<span class="tf-check">{esc(item["check_name"])} · '
                    f'{esc(item["flag_id"])}{esc(tag)}</span>'
                    f'<div class="tf-card-title">Pages {esc(", ".join(map(str, item["pages"])))}</div>',
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
                f"{r['reviewer']}: {review.DECISIONS[r['decision']]}" + (f" ({r['note']})" if r["note"] else "")
                for r in others))
        if mine:
            st.caption(f"Your decision: {review.DECISIONS[mine['decision']]}"
                       + (f" ({mine['note']})" if mine["note"] else "") + ". You can change it.")
        note = st.text_input("Note (optional)", key=f"review::note::{item['flag_id']}")
        b = st.columns(3)
        for col, (code, label) in zip(b, review.DECISIONS.items()):
            if col.button(label, key=f"review::{code}::{item['flag_id']}", disabled=not reviewer,
                          width="stretch"):
                return code, note
    return None, None


def render(report_id):
    queue = review.load_queue()
    if not queue or queue["report_id"] != report_id:
        st.info("No review queue for this report.")
        return
    reviews = review.load_reviews()
    items = queue["items"]
    st.markdown(f"Every new RED/ORANGE flag of the full audit, in order: {esc(queue['order'])}. "
                f"{queue['double_review']} flags are judged by both reviewers independently. "
                "Decisions are saved to review/reviews.jsonl.")
    precision_panel(queue, reviews)
    st.write("")

    st.session_state.setdefault(NAME_KEY, st.session_state.get(feedback.REVIEWER_KEY, ""))
    reviewer = st.text_input("Reviewer name (required)", key=NAME_KEY).strip()
    if not reviewer:
        st.caption("Enter your name to record decisions.")
    if POS_KEY not in st.session_state:
        # open on the first flag still needing a decision (human-verified ones are done)
        st.session_state[POS_KEY] = review.next_index(queue, reviews, reviewer) or 0
    pos = st.session_state[POS_KEY]

    left = sum(review.needs(it, reviews, reviewer) for it in items) if reviewer else None
    st.progress(pos / max(len(items) - 1, 1), text=f"Flag {pos + 1} of {len(items)}"
                + (f" · {left} still need your decision" if left is not None else ""))
    nav = st.columns(3)
    if nav[0].button("Previous", disabled=pos == 0, width="stretch"):
        st.session_state[POS_KEY] = pos - 1
        st.rerun()
    if nav[1].button("Next", disabled=pos >= len(items) - 1, width="stretch"):
        st.session_state[POS_KEY] = pos + 1
        st.rerun()
    if nav[2].button("Next needing me", disabled=not reviewer, width="stretch"):
        nxt = review.next_index(queue, reviews, reviewer, start=pos + 1)
        st.session_state[POS_KEY] = pos if nxt is None else nxt
        st.rerun()

    decision, note = item_card(items[pos], reviews, reviewer)
    if decision:
        it = items[pos]
        try:
            review.record(it["flag_id"], reviewer, decision, note or "")
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
        reviews = review.load_reviews()
        nxt = review.next_index(queue, reviews, reviewer, start=pos + 1)
        if nxt is not None:
            st.session_state[POS_KEY] = nxt
        st.rerun()

    if review.REVIEWS.exists():
        st.download_button("Download reviews (.jsonl)", review.REVIEWS.read_bytes(),
                           file_name="reviews.jsonl", mime="application/json")
