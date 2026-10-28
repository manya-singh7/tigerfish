"""Paper trail part of the "Public record" tab, from results/paper_trail_<report>.json only:
who the project is (from the report's own text), one timeline (Public record events plus every
official document whose page states a date), "Documents found" with source, date, quote and
how Tavily found it, what was dropped, and the authorities a member of the public writes to."""

from tigerfish import paper_trail
from tigerfish.ui.style import esc

NOT_USABLE = ("returned nothing usable (the portal's pages are built with JavaScript or need a "
              "search form, so map / crawl see no documents)")


def identity_md(ident):
    rows = []
    for f in ident["facts"]:
        where = f"report p.{f['page']}" if f.get("page") else "report title and caption as published"
        rows.append(f"- **{f['fact'].replace('_', ' ')}**: {esc(f['value'])} ({where}: "
                    f"“{esc(f['quote'] or '')}”)")
    if not ident["proposals"]:
        rows.append("- **proposal number**: not stated in the report text available")
    if not ident["state"]:
        rows.append("- **state**: not stated in the report text available")
    return "\n".join(rows)


def timeline_html(rows):
    body = "".join(
        f"<tr><td style='white-space:nowrap'>{esc(r['date'])}</td><td>{esc(r['event'])}"
        f"<div class='tf-quote' style='margin-top:0.3rem'>“{esc(r['quote'])}”</div></td>"
        f"<td><a href='{esc(r['source'])}' target='_blank'>{esc(r['host'])}</a>"
        f"<div><span class='tf-via'>{esc(r['via'])}</span></div></td></tr>" for r in rows)
    return ("<table class='tf-table tf-timeline'><tr><th>Date</th><th>Event and quote</th>"
            "<th>Source</th></tr>" + body + "</table>")


def documents_html(docs):
    out = []
    for d in docs:
        date = (f"{esc(d['date'])} (the page states: “{esc(d['date_quote'])}”)" if d.get("date")
                else "date not stated on the page")
        tor = " · <b>granted ToR</b>" if d.get("granted_tor") else ""
        out.append(
            f"<div class='tf-doc'><div><b>{esc(d['type'])}</b>{tor} · "
            f"<a href='{esc(d['url'])}' target='_blank'>{esc(d['title'])}</a></div>"
            f"<div class='tf-ev-label' style='font-size:0.8rem'>{esc(d['host'])} · {date} · "
            f"names the project by its {esc(d['match'])}</div>"
            f"<div class='tf-quote' style='margin-top:0.25rem'>“{esc(d['quote'])}”</div>"
            f"<span class='tf-via'>{esc(paper_trail.FOUND_VIA.get(d['found_via'], d['found_via']))}</span>"
            f"</div>")
    return "".join(out)


ROLE_LABELS = {
    "hearing": "Public hearing (state pollution control board / committee)",
    "clearance": "Environmental clearance (MoEFCC, Expert Appraisal Committee)",
    "borrower": "Executing agency (the borrower's agency that prepared the report)",
    "lender": "Asian Development Bank (the project's listed contact)",
    "accountability": "Asian Development Bank Accountability Mechanism (complaints)",
}
ADB_NOTE = ("This project is financed by the Asian Development Bank and assessed under ADB's "
            "Safeguard Policy Statement (2009). The Indian clearance steps (Terms of Reference, "
            "environmental clearance, public hearing under the EIA Notification, 2006) do not apply "
            "to it; its consultations follow ADB's rules. Its official documents are ADB disclosures "
            "and Karnataka government pages, searched below.")


def is_adb(trail):
    return ((trail or {}).get("identity") or {}).get("framework") == "adb"


def roles_for(trail):
    return ("borrower", "lender", "accountability") if is_adb(trail) else ("hearing", "clearance")


def contact_md(role, c):
    label = ROLE_LABELS[role]
    if not c or not c.get("found"):
        return f"- **{label}**: not found ({esc((c or {}).get('why', 'not searched'))}). The letter keeps its [placeholders]."
    email = f"; email {esc(c['email'])}" if c.get("email") else "; no email published on the pages read"
    return (f"- **{label}**: {esc(c['body'])}, {esc(c['address'])}{email}. Source: "
            f"[{esc(c['host'])}]({c['source']}), “{esc(c['quote'])}”. {esc(c['note'])}")


def render(report_id, rec=None):
    import streamlit as st
    trail = paper_trail.load(report_id)
    rows = paper_trail.timeline(report_id, rec, trail or {})
    st.markdown("##### Timeline (official sources)")
    if rows:
        st.markdown(timeline_html(rows), unsafe_allow_html=True)
        st.caption("Public record events (Tavily research, each quote found in the source text) and "
                   "official documents whose page states its date. Verify each against its source.")
    else:
        st.caption("No dated event could be verified against an official source.")

    st.markdown("##### Documents found")
    if not trail:
        st.caption("No paper-trail search saved for this report (run: python scripts/check_paper_trail.py).")
        return
    if is_adb(trail):
        st.markdown(f'<div class="tf-line tf-adb">{esc(ADB_NOTE)}</div>', unsafe_allow_html=True)
    number = trail["identity"].get("number_label", "proposal number")
    st.caption(f"Searched {trail['searched_on']} on official sites only: {', '.join(trail['sites'])}, "
               "plus any .gov.in / .nic.in page Tavily found. A document is kept only if its text "
               f"names the project or its {number}; the quote shows where.")
    with st.expander("Who the project is, from the report's own text"):
        st.markdown(identity_md(trail["identity"]))
        if trail["identity"].get("note"):
            st.caption(trail["identity"]["note"])
    unusable = sorted({u["site"] for u in trail.get("unusable", []) if u["tool"] == "map"}
                      & {u["site"] for u in trail.get("unusable", []) if u["tool"] == "crawl"})
    if unusable:
        st.markdown(f'<div class="tf-line tf-unusable">Tavily map and crawl on {esc(", ".join(unusable))} '
                    f'{NOT_USABLE}.</div>', unsafe_allow_html=True)
    docs = trail["documents"]
    if docs:
        st.markdown(documents_html(docs), unsafe_allow_html=True)
    else:
        st.markdown('<div class="tf-line tf-unusable">No official document naming this project was '
                    'found. Nothing is shown rather than a guess.</div>', unsafe_allow_html=True)
    drops = trail.get("drop_counts") or {}
    if drops:
        with st.expander(f"Dropped: {sum(drops.values())} pages"):
            st.markdown("\n".join(f"- {n}: {esc(why)}" for why, n in drops.items()))
            st.markdown("\n".join(f"- [{esc(d['host'])}]({d['url']}): {esc(d['why'])}"
                                  for d in trail["dropped"][:60]))
    gt = trail.get("granted_tor") or {}
    if gt.get("applicable") is not False:          # not shown for an ADB project (no ToR applies)
        st.caption("Granted Terms of Reference: " + (
            f"found ({gt['date'] or 'date not stated'}); the ToR promises tab checks the report "
            "against it." if gt.get("found") else
            f"not found on official sites (searched: {', '.join(trail['sites'])}, {trail['searched_on']})."))

    st.markdown("##### Who to write to")
    st.markdown("\n".join(contact_md(role, (trail.get("contacts") or {}).get(role))
                          for role in roles_for(trail)))
    t = trail["tavily"]
    st.caption(f"Tavily: map and crawl with instructions, official-domain search, extract. "
               f"{t['credits']} credits (as Tavily reported per response).")


def granted_tor_line(report_id):
    """The "granted ToR not found" line for the ToR promises tab ("" when found, not searched,
    or not applicable: an ADB project has no Indian ToR)."""
    trail = paper_trail.load(report_id)
    gt = (trail or {}).get("granted_tor") or {}
    if not trail or gt.get("found") or gt.get("applicable") is False:
        return ""
    return (f"Granted ToR not found on official sites (searched: {', '.join(trail['sites'])}, "
            f"{trail['searched_on']})")
