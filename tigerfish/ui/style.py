"""Look and feel: one accent colour (deep teal), dark text, grade colours only on badges."""

import html

ACCENT = "#0F5E5E"
TEXT = "#1C2B33"
MUTED = "#5B6B73"
BORDER = "#E3E8EA"

BADGE = {  # grade: (text colour, background)
    "RED": ("#9B1C1C", "#FDE8E8"),
    "ORANGE": ("#8A4B08", "#FDF0D9"),
    "INFO": ("#1E4E79", "#E3EEF8"),
}

CSS = f"""
<style>
  .block-container {{ max-width: 1320px; padding-top: 2.2rem; padding-bottom: 4rem; }}
  h1, h2, h3, h4 {{ color: {TEXT}; letter-spacing: -0.01em; }}
  .tf-title {{ font-size: 2.4rem; font-weight: 750; color: {TEXT}; line-height: 1.1; }}
  .tf-tagline {{ font-size: 1.05rem; color: {ACCENT}; margin: 0.1rem 0 0.4rem 0; }}
  .tf-lede {{ color: {MUTED}; margin-bottom: 1.2rem; max-width: 46rem; }}
  .tf-stat {{ border: 1px solid {BORDER}; border-radius: 10px; padding: 0.8rem 1rem;
              background: #FFFFFF; height: 100%; }}
  .tf-stat-label {{ font-size: 0.78rem; color: {MUTED}; text-transform: uppercase;
                    letter-spacing: 0.04em; }}
  .tf-stat-value {{ font-size: 1.35rem; font-weight: 650; color: {TEXT}; margin-top: 0.15rem; }}
  .tf-stat-note {{ font-size: 0.8rem; color: {MUTED}; margin-top: 0.1rem; }}
  .tf-badge {{ display: inline-block; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.05em;
               padding: 0.12rem 0.55rem; border-radius: 999px; margin-right: 0.5rem; }}
  .tf-check {{ font-size: 0.82rem; color: {MUTED}; text-transform: uppercase; letter-spacing: 0.04em; }}
  .tf-card-title {{ font-size: 1.08rem; font-weight: 650; color: {TEXT}; margin: 0.35rem 0 0.2rem 0; }}
  .tf-message {{ color: {TEXT}; margin-bottom: 0.6rem; }}
  .tf-quote-label {{ font-size: 0.78rem; color: {ACCENT}; font-weight: 650; margin-bottom: 0.25rem; }}
  .tf-quote {{ border-left: 3px solid {ACCENT}; background: #F4F7F7; padding: 0.55rem 0.8rem;
               color: {TEXT}; font-size: 0.93rem; border-radius: 0 6px 6px 0; }}
  .tf-ev {{ font-size: 0.9rem; color: {TEXT}; margin: 0.15rem 0; }}
  .tf-ev-label {{ color: {MUTED}; }}
  .tf-line {{ font-size: 0.92rem; margin: 0.2rem 0; }}
  .tf-line b {{ color: {ACCENT}; font-weight: 650; }}
  .tf-review {{ font-size: 0.85rem; color: {MUTED}; }}
  .tf-timeline {{ border-left: 2px solid {BORDER}; margin: 0.4rem 0 0 0.6rem; }}
  .tf-step {{ display: flex; gap: 0.7rem; margin: 0 0 0.75rem -0.75rem; }}
  .tf-step-n {{ flex: 0 0 1.4rem; height: 1.4rem; border-radius: 999px; background: {ACCENT}; color: #FFF;
                font-size: 0.75rem; font-weight: 700; text-align: center; line-height: 1.4rem; }}
  .tf-step-body {{ flex: 1; min-width: 0; font-size: 0.9rem; color: {TEXT}; }}
  .tf-tool {{ font-family: ui-monospace, Consolas, monospace; font-size: 0.72rem; font-weight: 700;
              letter-spacing: 0.04em; color: {ACCENT}; border: 1px solid {ACCENT}; border-radius: 4px;
              padding: 0.05rem 0.35rem; margin-right: 0.5rem; }}
  .tf-step-args {{ overflow-wrap: anywhere; }}
  .tf-step-why {{ color: {MUTED}; font-size: 0.85rem; margin-top: 0.15rem; }}
  .tf-step-result {{ margin-top: 0.1rem; }}
  .tf-step-meta {{ color: {MUTED}; font-size: 0.75rem; }}
  .tf-memo-head {{ font-weight: 700; font-size: 1rem; padding: 0.35rem 0.7rem; border-radius: 6px;
                   display: inline-block; margin-bottom: 0.4rem; }}
  .tf-memo-strengthens {{ background: #FDF0D9; color: #8A4B08; }}
  .tf-memo-weakens {{ background: #E3EEF8; color: #1E4E79; }}
  .tf-memo-inconclusive {{ background: #EEF1F2; color: {MUTED}; }}
  .tf-memo-sub {{ font-size: 0.78rem; color: {MUTED}; text-transform: uppercase; letter-spacing: 0.04em;
                  margin: 0.6rem 0 0.3rem 0; }}
  .tf-memo-list {{ margin: 0.1rem 0 0.4rem 1.1rem; padding: 0; font-size: 0.92rem; }}
  .tf-memo-note {{ font-size: 0.85rem; color: {MUTED}; margin: 0.2rem 0 0.6rem 0; }}
  .tf-ref {{ font-family: ui-monospace, Consolas, monospace; font-size: 0.7rem; font-weight: 700;
             color: {ACCENT}; background: #EAF2F2; border-radius: 4px; padding: 0.02rem 0.3rem;
             margin: 0 0.35rem 0 0.1rem; }}
  .tf-unverified {{ color: #8A979D; }}
  .tf-unverified .tf-memo-sub {{ color: #9AA6AB; }}
  .tf-memo-foot {{ font-size: 0.8rem; color: {MUTED}; margin-top: 0.6rem; }}
  .tf-tavily {{ display: inline-block; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.03em;
                color: #5A3E99 !important; background: #EFEAFB; border: 1px solid #D9CFF5;
                border-radius: 999px; padding: 0.02rem 0.45rem; margin-left: 0.35rem;
                text-decoration: none !important; vertical-align: 1px; }}
  .tf-models {{ display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0.1rem 0 0.55rem 0; }}
  .tf-model {{ display: inline-block; font-size: 0.7rem; font-weight: 650; letter-spacing: 0.02em;
               border-radius: 4px; padding: 0.08rem 0.45rem; border: 1px solid; white-space: nowrap;
               cursor: help; }}
  .tf-model-detail {{ font-weight: 500; opacity: 0.8; }}
  .tf-model-nemotron {{ color: {ACCENT}; background: #EAF2F2; border-color: #C7DEDE; }}
  .tf-model-tavily {{ color: #5A3E99; background: #EFEAFB; border-color: #D9CFF5; }}
  .tf-model-gbif {{ color: #3B6B2A; background: #EDF5E8; border-color: #CFE3C4; }}
  .tf-model-human {{ color: #7A4B00; background: #FFF4DE; border-color: #F0D9A8; }}
  .tf-verified {{ border-left: 3px solid #E0B24F; background: #FFFAF0; padding: 0.45rem 0.7rem;
                  margin: 0 0 0.6rem 0; font-size: 0.92rem; color: {TEXT}; }}
  .tf-verified b {{ color: #7A4B00; }}
  .tf-knowable {{ border-left: 3px solid {ACCENT}; background: #F2F8F8; padding: 0.45rem 0.7rem;
                  margin: 0.6rem 0 0.2rem 0; font-size: 0.9rem; color: {TEXT}; }}
  .tf-knowable b {{ color: {ACCENT}; }}
  .tf-photo {{ margin: 0.7rem 0 0.2rem 0; max-width: 300px; }}
  .tf-photo img {{ width: 100%; border-radius: 6px; display: block; }}
  .tf-photo figcaption {{ font-size: 0.74rem; color: #5B6B73; margin-top: 0.25rem; line-height: 1.35; }}
  .tf-hero {{ font-size: 0.78rem; color: {ACCENT}; font-weight: 700; text-transform: uppercase;
              letter-spacing: 0.05em; margin-bottom: 0.3rem; }}
  .tf-hero-headline {{ font-size: 1.45rem; font-weight: 700; color: {TEXT}; line-height: 1.3;
                       margin: 0.3rem 0 0.5rem 0; max-width: 52rem; }}
  .tf-hero-note {{ font-size: 0.82rem; color: {MUTED}; margin-top: 0.4rem; }}
  .tf-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; margin: 0.4rem 0 0.8rem 0; }}
  .tf-table th {{ text-align: left; color: {MUTED}; font-weight: 600; font-size: 0.78rem;
                  text-transform: uppercase; letter-spacing: 0.03em; border-bottom: 1px solid {BORDER};
                  padding: 0.4rem 0.5rem; }}
  .tf-table td {{ border-bottom: 1px solid {BORDER}; padding: 0.45rem 0.5rem; vertical-align: top;
                  color: {TEXT}; overflow-wrap: anywhere; }}
  .tf-off, .tf-open, .tf-auth {{ display: inline-block; font-size: 0.7rem; font-weight: 700; border-radius: 999px;
                       padding: 0.05rem 0.5rem; white-space: nowrap; }}
  .tf-off {{ color: {ACCENT}; background: #E3F0F0; }}
  .tf-open {{ color: #8A4B08; background: #FDF0D9; }}
  .tf-auth {{ color: #3D4A8A; background: #E8EBF7; }}
  .tf-via {{ display: inline-block; font-size: 0.7rem; font-weight: 650; border-radius: 999px;
             padding: 0.05rem 0.5rem; margin-top: 0.3rem; color: #3D4A8A; background: #E8EBF7; }}
  .tf-doc {{ border-bottom: 1px solid {BORDER}; padding: 0.55rem 0; font-size: 0.9rem; }}
  .tf-unusable {{ color: #8A4B08; }}
  .tf-adb {{ color: {TEXT}; background: #F4F7F7; border-radius: 6px; padding: 0.5rem 0.7rem; }}
  a {{ color: {ACCENT}; }}
</style>
"""


def esc(text):
    return html.escape(str(text if text is not None else ""))


def badge(grade):
    fg, bg = BADGE.get(grade, (TEXT, "#EEE"))
    return f'<span class="tf-badge" style="color:{fg};background:{bg}">{esc(grade)}</span>'


def stat(label, value, note=""):
    note_html = f'<div class="tf-stat-note">{esc(note)}</div>' if note else ""
    return (f'<div class="tf-stat"><div class="tf-stat-label">{esc(label)}</div>'
            f'<div class="tf-stat-value">{esc(value)}</div>{note_html}</div>')


# Dark theme (.streamlit/config.toml [theme.dark]): the cards above use light colours; these
# override them when the viewer's theme is dark. Palette from assets/theme_proposal.toml.
DARK_CSS = """
<style>
  h1, h2, h3, h4, .tf-title, .tf-card-title, .tf-message, .tf-ev, .tf-step-body,
  .tf-stat-value {{ color: #E6F4F1; }}
  .tf-tagline, .tf-quote-label, .tf-line b {{ color: #5FD4C6; }}
  .tf-lede, .tf-stat-label, .tf-stat-note, .tf-check, .tf-ev-label, .tf-review, .tf-step-why,
  .tf-step-meta, .tf-lib-meta {{ color: #A9C4C0; }}
  .tf-stat {{ background: #11292F; border-color: #2A4A52; }}
  .tf-quote {{ background: #11292F; color: #E6F4F1; border-left-color: #5FD4C6; }}
  .tf-timeline {{ border-left-color: #2A4A52; }}
  .tf-lib-full {{ color: #5FD4C6; background: #11292F; }}
  .tf-tool {{ color: #5FD4C6; border-color: #5FD4C6; }}
  .tf-hero, .tf-knowable b {{ color: #5FD4C6; }}
  .tf-hero-headline, .tf-adb {{ color: #E6F4F1; }}
  .tf-hero-note, .tf-photo figcaption, .tf-unverified, .tf-unverified .tf-memo-sub {{ color: #A9C4C0; }}
  .tf-verified {{ background: #2A2416; color: #E6F4F1; }}
  .tf-verified b {{ color: #F2B544; }}
  .tf-knowable {{ background: #11292F; color: #E6F4F1; border-left-color: #5FD4C6; }}
  .tf-adb {{ background: #11292F; }}
  .tf-doc {{ border-bottom-color: #2A4A52; }}
</style>
""".format()


def theme_css():
    """Extra CSS for the dark theme ("" in the light theme)."""
    import streamlit as st
    try:
        dark = st.context.theme.type == "dark"
    except Exception:      # no browser context (tests)
        dark = False
    return DARK_CSS if dark else ""
