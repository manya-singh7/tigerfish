""""Evidence from the web" tab: every Tavily-backed fact across all checks, from the saved
results only (replay; no keys): the claim, the source, whether it is official, and how its
quote was verified; plus Tavily usage (searches, extracts, credits, share official)."""

import json
from pathlib import Path

from tigerfish.official_record import host, is_official, source_label
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
}
CHECK_LABEL = {"copy_paste": "Copied text", "borrowed_text": "Borrowed text",
               "accreditation": "Consultant accreditation", "legal_schedule": "WPA schedule",
               "investigation": "Investigate agent", "official_record": "Official record"}


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


def collect():
    """All Tavily-backed facts in the saved results."""
    reports = [data.load(r["id"]) for r in data.reports()]
    titles = {r["id"]: r["title"] for r in reports}
    rows = []
    for rep in reports:
        rows += finding_rows(rep) + official_record_rows(rep["id"], rep["title"])
    return rows + investigation_rows(titles)


def stats(rows):
    """Usage per check. Searches / extracts are recorded for the official-record check and the
    Investigate agent; for the other checks only their credits were saved."""
    out = []
    reports = [data.load(r["id"]) for r in data.reports()]
    for rep in reports:
        credits = (rep.get("cost") or {}).get("tavily_credits") or 0
        if credits:
            names = sorted({r["check"] for r in rows if r["report"] == rep["title"]
                            and r["check"] not in ("Official record", "Investigate agent")})
            out.append({"what": f"{rep['title']}: {', '.join(names) or 'checks'}",
                        "searches": None, "extracts": None, "credits": credits})
        rec = official.load(rep["id"])
        if rec:
            t = rec["tavily"]
            out.append({"what": f"{rep['title']}: official record", "searches": t["searches"],
                        "extracts": t["extracts"], "credits": t["credits"]})
    searches = extracts = credits = 0
    for p in sorted((RESULTS / "investigations").glob("*.json")):
        inv = json.loads(p.read_text(encoding="utf-8"))
        searches += sum(1 for s in inv["trace"] if s.get("tool") == "web_search")
        extracts += sum(1 for s in inv["trace"] if s.get("tool") == "read_url")
        credits += inv["totals"].get("tavily_credits", 0)
    if searches or extracts or credits:
        out.append({"what": "Investigate agent (recorded runs)", "searches": searches,
                    "extracts": extracts, "credits": credits})
    urls = {r["url"]: r["official"] for r in rows}
    return {"rows": out, "credits": sum(r["credits"] for r in out),
            "sources": len(urls), "official_sources": sum(urls.values()),
            "official_share": (sum(urls.values()) / len(urls)) if urls else None}


def render():
    import streamlit as st
    from tigerfish.ui.style import esc
    rows = collect()
    s = stats(rows)
    st.markdown("#### Evidence from the web")
    st.markdown(f'<div class="tf-message">{len(rows)} facts across all checks rest on web sources '
                f'found with Tavily: {s["sources"]} distinct sources, {s["official_sources"]} of them '
                f'official or government sites ({(s["official_share"] or 0):.0%}).</div>',
                unsafe_allow_html=True)
    lines = ["| Where | Searches | Extracts | Credits |", "|---|---:|---:|---:|"]
    for r in s["rows"]:
        lines.append(f"| {r['what']} | {'-' if r['searches'] is None else r['searches']} | "
                     f"{'-' if r['extracts'] is None else r['extracts']} | {r['credits']} |")
    lines.append(f"| **Total** | | | **{s['credits']}** |")
    st.markdown("\n".join(lines))
    st.caption("Searches and extracts are recorded for the official-record check and the "
               "Investigate agent; for the other checks the saved results keep only their credits (-).")
    body = []
    for r in rows:
        badge = ("<span class='tf-off'>official</span>" if r["label"] == "official source" else
                 "<span class='tf-off'>government</span>" if r["official"] else
                 "<span class='tf-open'>open web</span>")
        body.append(f"<tr><td>{esc(r['check'])}<div class='tf-ev-label' style='font-size:0.78rem'>"
                    f"{esc(r['report'])}</div></td><td>{esc(r['claim'])}</td>"
                    f"<td><a href='{esc(r['url'])}' target='_blank'>{esc(r['source'])}</a>"
                    f"<div class='tf-ev-label' style='font-size:0.78rem'>{esc(r['host'])}</div></td>"
                    f"<td>{badge}</td><td style='font-size:0.82rem'>{esc(r['verified'])}</td></tr>")
    st.markdown("<table class='tf-table'><tr><th>Check</th><th>Fact</th><th>Source</th>"
                "<th>Official?</th><th>How the quote was verified</th></tr>" + "".join(body)
                + "</table>", unsafe_allow_html=True)
