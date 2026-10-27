"""The "aha first" hero: one finding, one sentence, shown above everything else when the
app opens. Change HERO_REPORT_ID / HERO_FINDING_ID to feature another finding; set
HERO_HEADLINE to None to use the finding's own message as the headline."""

import streamlit as st

from tigerfish.ui import badges, cards, data
from tigerfish.ui.style import badge, esc

HERO_REPORT_ID = "great_nicobar_2021_draft"
HERO_FINDING_ID = "pr-06"
HERO_HEADLINE = ("The Terms of Reference ask for 3 months of terrestrial ecology baseline data; "
                 "the EIA describes a 9-day field survey (14-22 December 2020) and a 7-day "
                 "turtle survey (12-18 February 2021).")
HERO_NOTE = ("Compared with the proposed Terms of Reference; the granted ToR may differ. "
             "A lead for human review, not a verdict.")
CLOSED_KEY = "hero_closed"


def hero_finding(report):
    """The configured finding when this is the hero's report, else None."""
    if not report or report.get("id") != HERO_REPORT_ID:
        return None
    return next((f for f in report.get("findings", []) if f["id"] == HERO_FINDING_ID), None)


def headline(f):
    """One sentence: the configured headline for the hero finding, else the finding's message."""
    return HERO_HEADLINE if HERO_HEADLINE and f["id"] == HERO_FINDING_ID else f["message"]


def close():
    st.session_state[CLOSED_KEY] = True


def render(report):
    """Draw the hero card. Returns True when drawn (hero report, finding found, not closed)."""
    f = hero_finding(report)
    if f is None or st.session_state.get(CLOSED_KEY):
        return False
    with st.container(border=True):
        st.markdown(f'<div class="tf-hero">TigerFish found this in the {esc(report.get("title", ""))}</div>'
                    f'{badge(f["grade"])}<span class="tf-check">{esc(f["check_name"])}</span>'
                    f'<div class="tf-hero-headline">{esc(headline(f))}</div>'
                    + badges.html(badges.finding_badges(f, badges.readers(report["id"]))),
                    unsafe_allow_html=True)
        quotes = f["quotes"]
        cols = st.columns(len(quotes)) if len(quotes) > 1 else [st.container()]
        for col, q in zip(cols, quotes):
            col.markdown(f'<div class="tf-quote-label">{esc(cards.quote_label(q))}</div>'
                         f'<div class="tf-quote">{esc(q["text"])}</div>', unsafe_allow_html=True)
        images = list(dict.fromkeys(f.get("images") or []))
        cards.zoomed(images)
        paths = [p for p in (data.image_path(rel) for rel in images) if p]
        if paths:
            with st.expander("Show the full page" + ("s" if len(paths) > 1 else "")):
                for col, path in zip(st.columns(len(paths)), paths):
                    col.image(str(path), caption=f"Page {cards.page_no(path)}", width="stretch")
        st.markdown(f'<div class="tf-hero-note">{esc(HERO_NOTE)}</div>', unsafe_allow_html=True)
        st.button("See all findings", type="primary", key="hero_see_all", on_click=close)
    return True
