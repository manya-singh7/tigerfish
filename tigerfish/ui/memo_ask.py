"""Nemotron Ultra reads the whole report: the reviewer's memo and "Ask the report".

Replay (default, no keys): results/memo_<report>.json, results/ask_<report>.json and
results/ultra_context_test.json. Live questions only with NEBIUS_API_KEY, at most
ask.SESSION_LIMIT per session, with the cost estimate shown before sending.
"""

import json
import os
from pathlib import Path

from tigerfish import ask, fulltext
from tigerfish.ui import badges

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
CATEGORY = {"contradiction": "Figures disagree", "baseline_gap": "Baseline gap",
            "missing_assessment": "Impact not assessed", "unsupported_claim": "Not supported",
            "other": "Other"}


def _load(name):
    p = RESULTS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def memo(report_id):
    return _load(f"memo_{report_id}.json")


def answers(report_id):
    return _load(f"ask_{report_id}.json")


def context_test():
    return _load("ultra_context_test.json")


def live_available():
    return bool(os.getenv("NEBIUS_API_KEY"))


def caption(text):
    """st.caption with $ escaped: a pair of $ signs would otherwise render as LaTeX."""
    import streamlit as st
    st.caption(text.replace("$", "\\$"))


def usd(x):
    return f"${x:.4f}" if x < 1 else f"${x:.2f}"


def cost_line(c):
    """'545,436 input tokens (539,648 cached) + 652 output: $0.0725, $0.4749 saved by the cache'."""
    share = c["cached_tokens"] / c["prompt_tokens"] if c.get("prompt_tokens") else 0
    return (f"{c['prompt_tokens']:,} input tokens ({c['cached_tokens']:,} cached, {share:.0%}) + "
            f"{c['completion_tokens']:,} output: {usd(c['cost_usd'])}; without the prompt cache "
            f"{usd(c['cost_if_uncached_usd'])} ({usd(c['saving_usd'])} saved)")


def citation_html(c):
    from tigerfish.ui.style import esc
    moved = (f" <span class='tf-ev-label'>(cited as p.{c['cited_page']}; the quote is on "
             f"p.{c['page']})</span>") if c.get("cited_page") else ""
    return (f"<div class='tf-quote-label'>p.{c['page']}{moved}</div>"
            f"<div class='tf-quote' style='margin-bottom:0.45rem'>{esc(c['quote'])}</div>")


def unverified_html(cites):
    from tigerfish.ui.style import esc
    if not cites:
        return ""
    items = "".join(f"<li>p.{esc(c.get('page'))}: {esc(c['quote'][:200])}"
                    + (f" <i>(found on p.{', '.join(map(str, c['found_on']))}, too far from the "
                       f"cited page)</i>" if c.get("found_on") else " <i>(not found in the report text)</i>")
                    + "</li>" for c in cites)
    return (f"<div class='tf-ev-label' style='font-size:0.82rem;margin-top:0.3rem'>Quotes that did "
            f"not check out, dropped ({len(cites)}):<ul style='margin:0.2rem 0'>{items}</ul></div>")


def memo_summary(m):
    s = m["stats"]
    return (f"Nemotron Ultra read {m['pages_included']:,} pages (p.{m['first_page']} to "
            f"p.{m['last_page']}) in one call and wrote {s['issues_returned']} issues. Every quote "
            f"was checked against the page text: {s['citations_verified']} of {s['citations']} "
            f"found word for word ({s['page_corrected']} on a page next to the one cited, up to "
            f"{fulltext.MAX_PAGE_SHIFT} pages away; the page shown is where the quote is).")


def skipped_line(skipped):
    return "; ".join(f"{len(v)} {k}" for k, v in skipped.items())


def render_memo(report_id):
    import streamlit as st
    from tigerfish.ui.style import esc
    st.markdown("#### Reviewer's memo")
    m = memo(report_id)
    if not m:
        st.info("The reviewer's memo is saved for the Great Nicobar EIA only.")
        return
    st.markdown(f"<div class='tf-message'>{esc(memo_summary(m))}</div>", unsafe_allow_html=True)
    caption(f"Not read: {skipped_line(m['skipped'])}. Cost of the memo: {cost_line(m['cost'])}. "
               f"Neutral wording: these are points to verify, not findings.")
    for n, issue in enumerate(m["issues"], 1):
        with st.container(border=True):
            pages = ", ".join(f"p.{p}" for p in issue["pages"])
            st.markdown(f"<div class='tf-check'>{n}. {esc(CATEGORY.get(issue['category'], issue['category']))}"
                        f" · {esc(pages)}</div><div class='tf-card-title'>{esc(issue['title'])}</div>"
                        + badges.html(badges.memo_badges(m))
                        + f"<div class='tf-message'>{esc(issue['summary'])}</div>"
                        + "".join(citation_html(c) for c in issue["citations"])
                        + f"<div class='tf-ev'><span class='tf-ev-label'>Why it matters (Ultra's "
                          f"reasoning, not checked):</span> {esc(issue['reasoning'])}</div>"
                        + unverified_html(issue["unverified_citations"]), unsafe_allow_html=True)
    st.markdown(f"##### {esc('Unverified reasoning (not checked)')}")
    if m["unverified_reasoning"]:
        for issue in m["unverified_reasoning"]:
            st.markdown(f"<div class='tf-ev'><b>{esc(issue['title'])}</b>: {esc(issue['summary'])} "
                        f"<span class='tf-ev-label'>(no quote could be found in the report)</span></div>",
                        unsafe_allow_html=True)
    else:
        caption("None: every issue above has at least one quote found word for word in the report.")


def answer_html(a):
    from tigerfish.ui.style import esc
    body = badges.html(badges.ask_badges(a))
    if not a["report_says"]:
        body += f"<div class='tf-message'><b>{esc(ask.DOES_NOT_SAY)}</b></div>"
        if a.get("model_answer_unverified"):
            body += (f"<div class='tf-ev-label' style='font-size:0.85rem'>Ultra's answer had no quote "
                     f"that could be found in the report, so it is not shown as an answer.</div>")
    else:
        body += (f"<div class='tf-ev-label' style='font-size:0.8rem'>Ultra's answer (a summary; only "
                f"the quotes below are checked)</div><div class='tf-message'>{esc(a['answer'])}</div>"
                + "".join(citation_html(c) for c in a["citations"]))
    return body + unverified_html(a["unverified_citations"])


def ask_totals_line(t, n):
    return (f"{n} questions: {t['prompt_tokens']:,} input tokens, {t['cached_tokens']:,} of them "
            f"served from Token Factory's prompt cache ({t['cached_share']:.1%}). Cost "
            f"{usd(t['cost_usd'])}; without the cache it would be {usd(t['cost_if_uncached_usd'])}.")


def render_ask(report_id):
    import streamlit as st
    from tigerfish.ui.style import esc
    st.markdown("#### Ask the report")
    rec = answers(report_id)
    if not rec:
        st.info("Recorded questions are saved for the Great Nicobar EIA only.")
        return
    st.markdown("<div class='tf-message'>Every question sends the whole report to Nemotron Ultra. The "
                "report comes first, word for word the same each time, and the question last, so "
                "Token Factory serves the report from its prompt cache at "
                f"${fulltext.PRICE_CACHED:.2f} instead of ${fulltext.PRICE_IN:.2f} per million tokens. "
                "Answers must quote the report; quotes are checked, and an answer with no quote that "
                f"checks out is replaced by “{esc(ask.DOES_NOT_SAY)}”</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='tf-review'>{esc(ask_totals_line(rec['totals'], len(rec['answers'])))}</div>",
                unsafe_allow_html=True)
    for a in rec["answers"]:
        with st.expander(a["question"]):
            st.markdown(answer_html(a), unsafe_allow_html=True)
            caption(f"Cost: {cost_line(a['cost'])}"
                       + (f" · {a['calls']} calls (a cut-off or malformed reply was asked again)"
                          if a.get("calls", 1) > 1 else ""))
    render_live(report_id)


def render_live(report_id):
    import streamlit as st
    from tigerfish.ui.style import esc
    used = st.session_state.get("ask_used", 0)
    if not live_available():
        caption("Asking new questions needs NEBIUS_API_KEY (live mode). The answers above are recorded.")
        return
    pages_file = ROOT / "cache" / "pages" / fulltext.PDF_STEM / "pages.jsonl"
    if not pages_file.exists():
        caption("Asking new questions needs the page cache of this report (cache/pages/).")
        return
    pending = st.session_state.pop("ask_pending", None)      # set by the Send button's callback
    if pending:
        pages = fulltext.load_pages(ROOT / "cache")
        with st.spinner("Ultra is reading the whole report..."):
            try:
                a = ask.ask(pending, pages, log=lambda *_: None)
            except fulltext.CapReached as e:
                st.error(str(e))
                a = None
        if a:
            st.markdown(f"<div class='tf-card-title'>{esc(a['question'])}</div>" + answer_html(a),
                        unsafe_allow_html=True)
            caption(f"Cost: {cost_line(a['cost'])}")
    left = ask.SESSION_LIMIT - used
    q = st.text_input(f"Ask your own question ({left} of {ask.SESSION_LIMIT} left this session)",
                      max_chars=ask.MAX_QUESTION_CHARS, disabled=left <= 0, key="ask_question")
    if left <= 0:
        caption("Question limit for this session reached.")
        return
    if not q.strip():
        return
    report = fulltext.report_text(fulltext.load_pages(ROOT / "cache"))
    est = ask.estimate(q, report)
    caption(f"Estimated cost: about {usd(est['expected_usd'])} with the prompt cache warm; at most "
               f"{usd(est['worst_usd'])} if the cache is cold and the reply has to be asked again. "
               f"Spent so far on Ultra: {usd(fulltext.spent())} of the ${fulltext.SPEND_CAP_USD:.2f} cap.")

    def send():          # runs before the next script run, so the counter is already updated
        if st.session_state.get("ask_used", 0) < ask.SESSION_LIMIT:
            st.session_state["ask_used"] = st.session_state.get("ask_used", 0) + 1
            st.session_state["ask_pending"] = q

    st.button("Send to Nemotron Ultra", type="primary", on_click=send)


def render_context_note():
    import streamlit as st
    ct = context_test()
    if not ct or "full" not in ct:
        return
    f = ct["full"]
    caption(f"Context test: {f['prompt_tokens']:,} tokens ({f['pages_included']:,} pages) in one "
               f"Ultra call, {f['latency_s']:.0f} s. At that length Ultra named p.{f['answer'].get('last_page')} "
               f"as the last page (it is p.{f['last_page']}), and it often cites a page next to the "
               f"right one: that is why every quote is checked and the page corrected or dropped.")


def render(report_id):
    import streamlit as st
    render_memo(report_id)
    render_context_note()
    st.write("")
    render_ask(report_id)
