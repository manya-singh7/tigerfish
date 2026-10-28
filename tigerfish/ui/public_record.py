""""Public record" tab, from saved results only (replay; no keys):
- one timeline: Tavily Research events (each quote verified against the Tavily-extracted
  source text) plus the paper trail's dated official documents; "Documents found" and the
  authorities to write to (tigerfish/ui/paper_trail.py),
- "What happened next": later news per verified finding (links, for context),
- local-language coverage of the public hearing (Hindi / Tamil links).
Also the "knowable at the time" lines and species photos shown on finding cards."""

from tigerfish import knowable, species_photos
from tigerfish import public_record as record
from tigerfish.ui.style import esc

NEXT_NOTE = ("Later news coverage on the same topic, found with Tavily (news search, after the "
             "report date). Shown for context; not checked against the report.")
LOCAL_NOTE = ("Local-language coverage of the project's public hearing, found with Tavily "
              "(language filter on). Links only; not checked against the report.")


def knowable_html(report_id, finding_id, data=None):
    """Card line(s) for a finding; "" when no dated, verified source exists (no badge)."""
    lines = knowable.card_lines(report_id, finding_id, data)
    if not lines:
        return ""
    items = "".join(
        f'<div style="margin-top:0.25rem">“{esc(q)}” (<a href="{esc(url)}" target="_blank">'
        f'{esc(src)}</a>, {esc(d)})</div>' for q, src, d, url in lines)
    return (f'<div class="tf-knowable"><b>Knowable at the time</b> &nbsp;{esc(knowable.CARD_TEXT)}'
            f'{items}</div>')


def photo_html(report_id, finding_id, data=None):
    """Species photo with attribution, or "" when no freely licensed image was found."""
    p = species_photos.photo_for(report_id, finding_id, data)
    if not p:
        return ""
    licence = (f'<a href="{esc(p["licence_url"])}" target="_blank">{esc(p["licence"])}</a>'
               if p.get("licence_url") else esc(p["licence"]))
    return (f'<figure class="tf-photo"><img src="{esc(p["image_url"])}" alt="{esc(p["species"])}" '
            f'loading="lazy"><figcaption><i>{esc(p["species"])}</i>. Photo: {esc(p["author"])}, '
            f'{licence}, via <a href="{esc(p["page"])}" target="_blank">Wikimedia Commons</a>. '
            f'Reference photo of the species, not from the site.</figcaption></figure>')


def _links(items, with_date=False):
    rows = []
    for i in items:
        when = f' · {esc(str(i["date"])[:16])}' if with_date and i.get("date") else ""
        rows.append(f'<div class="tf-ev"><a href="{esc(i["url"])}" target="_blank">{esc(i["title"])}</a>'
                    f'<span class="tf-ev-label" style="font-size:0.78rem"> · {esc(i["host"])}{when}</span></div>')
    return "".join(rows)


def render(report_id):
    import streamlit as st
    from tigerfish.ui import paper_trail as trail_ui
    rec = record.load(report_id)
    st.markdown("#### Public record")
    if rec:
        st.caption(f"{rec['project']}. Report dated {rec['report_date']}.")
    # one timeline (research events + dated official documents), documents found, contacts
    trail_ui.render(report_id, rec or {})
    if not rec:
        st.info("No public-record news results saved for this report "
                "(run: python scripts/check_public_record.py).")
        return
    r = rec.get("research") or {}
    if r:
        st.caption(f"One Tavily Research call (structured output; {r.get('credits') or '?'} credits) "
                   f"returned {r.get('events_returned', 0)} events; {len(rec['timeline'])} are shown "
                   f"because their quote was found in the Tavily-extracted source text, "
                   f"{len(rec['timeline_dropped'])} were dropped.")
        if rec["timeline_dropped"]:
            with st.expander("Dropped events (not verified)"):
                for e in rec["timeline_dropped"]:
                    st.markdown(f"- {esc(e.get('date'))}: {esc(e.get('event'))} ({esc(e['why'])})")

    st.markdown("##### What happened next")
    st.caption(NEXT_NOTE)
    shown = [n for n in rec["next"] if n["items"]]
    if not shown:
        st.caption("No later news found that names the project.")
    for n in shown:
        st.markdown(f'<div class="tf-line"><b>Findings {esc(", ".join(n["finding_ids"]))}</b> '
                    f'<span class="tf-ev-label">(search: {esc(n["query"])})</span></div>'
                    + _links(n["items"], with_date=True), unsafe_allow_html=True)

    st.markdown("##### Local-language coverage of the public hearing")
    st.caption(LOCAL_NOTE)
    local = [n for n in rec["local"] if n["items"]]
    if not local:
        st.caption("No local-language coverage found that names the project.")
    for n in local:
        st.markdown(f'<div class="tf-line"><b>{esc(n["language_name"])}</b></div>' + _links(n["items"]),
                    unsafe_allow_html=True)
