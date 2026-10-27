""""Evidence from the web" tab: every Tavily-backed fact across all checks, from the saved
results only (replay; no keys): the claim, the source, whether it is official, and how its
quote was verified; plus Tavily usage (searches, extracts, credits, share official)."""

import json
from pathlib import Path

from tigerfish import knowable, public_record, species_photos
from tigerfish.official_record import AUTHORITATIVE_LABEL, host, is_official, source_label
from tigerfish.ui import data, official
from tigerfish.ui.cards import TAVILY_CHECKS

RESULTS = Path(__file__).resolve().parents[2] / "results"

HOW_VERIFIED = {   # check -> how the quote from the web source was checked
    "copy_paste": "longest verbatim run and 8-gram overlap computed against the Tavily-extracted text",
    "borrowed_text": "verbatim run of words found in the Tavily-extracted source text",
    "accreditation": "sector rows parsed from the Tavily-extracted official document; source text quoted",
    "legal_schedule": "exact sentence from the Tavily-extracted source text",
    "investigation": "agent quote checked against the text it read with Tavily extract; unverified quotes dropped",
    "official_record": "exact sentence from the Tavily-extracted text (whitespace collapsed)",
    "knowable": "dated before the report; quote found in the Tavily-extracted text, then confirmed by Ultra",
    "timeline": "Tavily Research event; its quote found in the Tavily-extracted source text",
    "photo": "licence and author read from the Commons file page (free licences only)",
}
CHECK_LABEL = {"copy_paste": "Copied text", "borrowed_text": "Borrowed text",
               "accreditation": "Consultant accreditation", "legal_schedule": "WPA schedule",
               "investigation": "Investigate agent", "official_record": "Official record",
               "knowable": "Knowable at the time", "timeline": "Public record timeline",
               "photo": "Species photo"}

# Tavily features used across TigerFish, and where (shown in this tab and in the README).
FEATURES = [
    ("Search + extract", "every web-backed check: copied text, official record, accreditation, WPA schedule"),
    ("exact_match", "copy-paste check: only pages containing the quoted phrase verbatim"),
    ("include_domains", "official-only searches; Commons-only image search"),
    ("include_domains_mode=\"prefer\"", "official and scientific sites first in one search "
     "(knowable at the time, accreditation, WPA schedule) instead of an official search plus an open-web fallback"),
    ("end_date / start_date", "sources published before the report (knowable at the time); news after it"),
    ("topic=\"news\"", "what happened next, per verified finding"),
    ("Research (structured output)", "one call for the project's clearance timeline, {date, event, source, quote}"),
    ("include_images", "species photos from Wikimedia Commons, with licence and author"),
    ("language + filter_by_language", "Hindi and Tamil coverage of the public hearing"),
    ("extract_depth=\"advanced\"", "official PDF tables (NABET accreditation lists); pages basic extraction cannot read"),
    ("project_id=\"tigerfish\"", "every request tagged, so usage is tracked per project"),
]


def _row(report, check, claim, title, url, quote=""):
    title = str(title or "")
    title = title if len(title) <= 90 else title[:87].rsplit(" ", 1)[0] + " ..."
    return {"report": report, "check": CHECK_LABEL.get(check, check), "claim": claim,
            "source": title or host(url), "url": url, "host": host(url),
            "official": is_official(url), "label": source_label(url), "quote": quote,
            "verified": HOW_VERIFIED[check]}


def finding_rows(report):
    out = []
    for f in report["findings"]:
        if f["check"] not in TAVILY_CHECKS:
            continue
        for e in f["evidence"]:
            if e.get("url"):
                out.append(_row(report["title"], f["check"], f["title"], e.get("value"), e["url"]))
    return out


def investigation_rows(titles):
    out = []
    for p in sorted((RESULTS / "investigations").glob("*.json")):
        inv = json.loads(p.read_text(encoding="utf-8"))
        for e in inv["memo"].get("evidence") or []:
            if e.get("url"):
                out.append(_row(titles.get(inv["report_id"], inv["report_id"]), "investigation",
                                f"{inv['finding_title']} ({e.get('id', '')})", host(e["url"]),
                                e["url"], e.get("quote", "")))
    return out


def official_record_rows(report_id, title):
    rec = official.load(report_id)
    if not rec:
        return []
    out = []
    for r in rec["comparisons"] + rec.get("official_only", []):
        o = r["official"]
        out.append(_row(title, "official_record", r["label"], o.get("title"), o["url"], o["quote"]))
    return out


def knowable_rows(report_id, title):
    rows = []
    for f in (knowable.load(report_id) or {}).get("findings", []):
        for s in f["sources"]:
            rows.append(_row(title, "knowable", f"{f['title']} (source dated {s['date']})",
                             s["title"], s["url"], s["quote"]))
    return rows


def timeline_rows(report_id, title):
    return [_row(title, "timeline", f"{e['date']}: {e['event']}", e["host"], e["source"], e["quote"])
            for e in (public_record.load(report_id) or {}).get("timeline", [])]


def photo_rows(report_id, title):
    rows = []
    for fid, r in (((species_photos.load() or {}).get("photos") or {}).get(report_id) or {}).items():
        p = r.get("photo")
        if p:
            rows.append(_row(title, "photo", f"{p['species']} ({p['licence']}, {p['author'][:40]})",
                             p["title"], p["page"]))
    return rows


def collect():
    """All Tavily-backed facts in the saved results."""
    reports = [data.load(r["id"]) for r in data.reports()]
    titles = {r["id"]: r["title"] for r in reports}
    rows = []
    for rep in reports:
        rows += finding_rows(rep) + official_record_rows(rep["id"], rep["title"])
        rows += (knowable_rows(rep["id"], rep["title"]) + timeline_rows(rep["id"], rep["title"])
                 + photo_rows(rep["id"], rep["title"]))
    return rows + investigation_rows(titles)


SEPARATE = ("Official record", "Investigate agent", "Knowable at the time", "Public record timeline",
            "Species photo")   # counted in their own rows, not in the audit's credits


def stats(rows):
    """Usage per check. Searches / extracts are recorded for the official-record check and the
    Investigate agent; for the other checks only their credits were saved."""
    out = []
    reports = [data.load(r["id"]) for r in data.reports()]
    for rep in reports:
        credits = (rep.get("cost") or {}).get("tavily_credits") or 0
        if credits:
            names = sorted({r["check"] for r in rows if r["report"] == rep["title"]
                            and r["check"] not in SEPARATE})
            out.append({"what": f"{rep['title']}: {', '.join(names) or 'checks'}",
                        "searches": None, "extracts": None, "credits": credits})
        rec = official.load(rep["id"])
        if rec:
            t = rec["tavily"]
            out.append({"what": f"{rep['title']}: official record", "searches": t["searches"],
                        "extracts": t["extracts"], "credits": t["credits"]})
        k = knowable.load(rep["id"])
        if k:
            out.append({"what": f"{rep['title']}: knowable at the time", "searches": k["tavily"]["searches"],
                        "extracts": k["tavily"]["extracts"], "credits": k["tavily"]["credits"]})
        pr = public_record.load(rep["id"])
        if pr and pr["tavily"].get("credits"):
            out.append({"what": f"{rep['title']}: public record (research, news, local language)",
                        "searches": None, "extracts": None, "credits": pr["tavily"]["credits"]})
    searches = extracts = credits = 0
    for p in sorted((RESULTS / "investigations").glob("*.json")):
        inv = json.loads(p.read_text(encoding="utf-8"))
        searches += sum(1 for s in inv["trace"] if s.get("tool") == "web_search")
        extracts += sum(1 for s in inv["trace"] if s.get("tool") == "read_url")
        credits += inv["totals"].get("tavily_credits", 0)
    if searches or extracts or credits:
        out.append({"what": "Investigate agent (recorded runs)", "searches": searches,
                    "extracts": extracts, "credits": credits})
    ph = species_photos.load()
    if ph and ph["tavily"].get("credits"):
        out.append({"what": "Species photos (image search)", "searches": ph["tavily"]["credits"],
                    "extracts": 0, "credits": ph["tavily"]["credits"]})
    urls = {r["url"]: r["official"] for r in rows}
    authoritative = {r["url"] for r in rows if r["label"] == AUTHORITATIVE_LABEL}
    return {"rows": out, "credits": sum(r["credits"] for r in out),
            "sources": len(urls), "official_sources": sum(urls.values()),
            "authoritative_sources": len(authoritative),
            "official_share": (sum(urls.values()) / len(urls)) if urls else None}


def badge_html(row):
    """Who publishes the source: official / government / authoritative non-government / open web."""
    if row["label"] == "official source":
        return "<span class='tf-off'>official</span>"
    if row["official"]:
        return "<span class='tf-off'>government</span>"
    if row["label"] == AUTHORITATIVE_LABEL:
        return "<span class='tf-auth'>authoritative, non-government</span>"
    return "<span class='tf-open'>open web</span>"


def render():
    import streamlit as st
    from tigerfish.ui.style import esc
    rows = collect()
    s = stats(rows)
    auth_note = (f", {s['authoritative_sources']} authoritative non-government "
                 f"(PRS Legislative Research)" if s["authoritative_sources"] else "")
    st.markdown("#### Evidence from the web")
    st.markdown(f'<div class="tf-message">{len(rows)} facts across all checks rest on web sources '
                f'found with Tavily: {s["sources"]} distinct sources, {s["official_sources"]} of them '
                f'official or government sites ({(s["official_share"] or 0):.0%})'
                f'{auth_note}.</div>',
                unsafe_allow_html=True)
    lines = ["| Where | Searches | Extracts | Credits |", "|---|---:|---:|---:|"]
    for r in s["rows"]:
        lines.append(f"| {r['what']} | {'-' if r['searches'] is None else r['searches']} | "
                     f"{'-' if r['extracts'] is None else r['extracts']} | {r['credits']} |")
    lines.append(f"| **Total** | | | **{s['credits']}** |")
    st.markdown("\n".join(lines))
    st.caption("Searches and extracts are recorded for the official-record, knowable-at-the-time "
               "and photo checks and the Investigate agent; for the other checks the saved results "
               "keep only their credits (-).")
    with st.expander("Tavily features used"):
        st.markdown("\n".join(f"- **{name}**: {where}" for name, where in FEATURES))
    body = []
    for r in rows:
        badge = badge_html(r)
        body.append(f"<tr><td>{esc(r['check'])}<div class='tf-ev-label' style='font-size:0.78rem'>"
                    f"{esc(r['report'])}</div></td><td>{esc(r['claim'])}</td>"
                    f"<td><a href='{esc(r['url'])}' target='_blank'>{esc(r['source'])}</a>"
                    f"<div class='tf-ev-label' style='font-size:0.78rem'>{esc(r['host'])}</div></td>"
                    f"<td>{badge}</td><td style='font-size:0.82rem'>{esc(r['verified'])}</td></tr>")
    st.markdown("<table class='tf-table'><tr><th>Check</th><th>Fact</th><th>Source</th>"
                "<th>Source type</th><th>How the quote was verified</th></tr>" + "".join(body)
                + "</table>", unsafe_allow_html=True)
