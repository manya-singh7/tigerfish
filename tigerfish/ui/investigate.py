"""Investigate panel in each finding card: a pre-recorded investigation (replay) or an
"Investigate" button (live, only with NEBIUS_API_KEY and the source PDF), shown as a
step-by-step timeline and then the evidence memo. The agent never changes the grade."""

import json
from pathlib import Path
from urllib.parse import urlsplit

import streamlit as st

from tigerfish import agent, hosted, pdf_reader
from tigerfish.ui import live
from tigerfish.ui.style import esc

ROOT = Path(__file__).resolve().parents[2]
LIVE_DIR = ROOT / "cache" / "investigations"        # live runs (not committed)
REPORTS = {  # report id -> (source PDF or None, project site)
    "great_nicobar_2021_draft": (ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf", (6.83, 93.87)),
    "indira_point_table_3_16": (None, (6.75, 93.83)),
    # site from the report's own coordinates (tigerfish/sites.py); no live investigations yet
    "cuddalore_port_2026_draft": (None, (11.7062, 79.7751)),
    # statewide road network: midpoint of the state's extent given on report p.23 (sites.py)
    "karnataka_rural_roads_2026_adb": (None, (15.0, 76.25)),
}
TOOL_LABELS = {"search_report": "SEARCH REPORT", "read_page": "READ PAGE", "check_species": "GBIF CHECK",
               "web_search": "WEB SEARCH", "read_url": "READ URL", "finish": "MEMO", None: "NO ACTION"}
CONCLUSION_LABELS = {"strengthens": "Evidence strengthens the finding",
                     "weakens": "Evidence weakens the finding",
                     "inconclusive": "Inconclusive"}


def saved(report_id, finding_id):
    """A live run from cache/investigations (only where live runs are possible: never on the
    hosted app, never without a key), else the pre-recorded one in results/, else None."""
    if can_run(report_id)[0]:
        p = LIVE_DIR / f"{report_id}__{finding_id}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return agent.load(report_id, finding_id)


def can_run(report_id):
    pdf = (REPORTS.get(report_id) or (None, None))[0]
    if hosted.is_hosted():
        return False, "Live investigation runs only locally (it needs the source PDF)."
    if not live.available():
        return False, "Live investigation needs NEBIUS_API_KEY."
    if pdf is None or not pdf.exists():
        return False, "Live investigation needs the source PDF locally."
    return True, ""


def run(report_id, finding, report_title):
    pdf, site = REPORTS[report_id]
    pages = pdf_reader.read_pdf(pdf, render=False)
    out = agent.investigate(finding, pages, site=site, report_name=report_title)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    (LIVE_DIR / f"{report_id}__{finding['id']}.json").write_text(
        json.dumps({"report_id": report_id, **out}, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def fmt_args(tool, args):
    if tool == "read_page":
        return f"page {args.get('n')}"
    if tool == "check_species":
        return f"{args.get('name')} at {args.get('lat')}, {args.get('lon')}"
    if tool == "web_search":
        return f"“{args.get('query')}”" + (" (official sources only)" if args.get("official_only") else "")
    if tool == "read_url":
        return urlsplit(str(args.get("url"))).netloc or str(args.get("url"))
    if tool == "search_report":
        return f"“{args.get('query')}”"
    return ""


def timeline_html(trace):
    rows = []
    for s in trace:
        meta = (f"{s['tokens_in']:,} in + {s['tokens_out']:,} out tokens, ${s['cost_usd']:.4f}"
                if s["tokens_in"] or s["tokens_out"] else "same model reply")
        why = f'<div class="tf-step-why">{esc(s["reason"])}</div>' if s.get("reason") else ""
        rows.append(
            f'<div class="tf-step"><div class="tf-step-n">{s["step"]}</div><div class="tf-step-body">'
            f'<span class="tf-tool">{esc(TOOL_LABELS.get(s["tool"], str(s["tool"]).upper()))}</span>'
            f'<span class="tf-step-args">{esc(fmt_args(s["tool"], s["args"]))}</span>{why}'
            f'<div class="tf-step-result">{esc(s["result"])}</div>'
            f'<div class="tf-step-meta">{esc(meta)}</div></div></div>')
    return '<div class="tf-timeline">' + "".join(rows) + "</div>"


def memo_html(memo):
    out = [f'<div class="tf-memo-head tf-memo-{esc(memo["conclusion"])}">'
           f'{esc(CONCLUSION_LABELS.get(memo["conclusion"], memo["conclusion"]))}</div>']
    if memo.get("reasons"):
        out.append("<ul class='tf-memo-list'>" + "".join(
            f"<li>{esc(r['text'])} " + "".join(f'<span class="tf-ref">{esc(i)}</span>' for i in r["evidence"])
            + "</li>" for r in memo["reasons"]) + "</ul>")
    if memo.get("unverified_reasons"):
        out.append('<div class="tf-unverified"><div class="tf-memo-sub">Unverified reasoning (not checked)</div>'
                   '<ul class="tf-memo-list">' + "".join(f"<li>{esc(r)}</li>" for r in memo["unverified_reasons"])
                   + "</ul></div>")
    if memo.get("evidence") or memo.get("data"):
        out.append('<div class="tf-memo-sub">Verified evidence</div>')
    for e in memo.get("evidence") or []:
        if e.get("page"):
            where = esc(f"Page {e['page']}")
        else:
            where = f'<a href="{esc(e["url"])}" target="_blank">{esc(urlsplit(e["url"]).netloc)}</a>'
            # web sources in a memo come from the agent's web_search / read_url tools (Tavily)
            where += (f' <a class="tf-tavily" href="{esc(e["url"])}" target="_blank" '
                      f'title="This source was found with Tavily web search">Found via Tavily</a>')
        out.append(f'<div class="tf-quote-label"><span class="tf-ref">{esc(e.get("id", ""))}</span>{where}</div>'
                   f'<div class="tf-quote">{esc(e["quote"])}</div>'
                   f'<div class="tf-memo-note">{esc(e["note"])}</div>')
    for d in memo.get("data") or []:
        link = f' <a href="{esc(d["url"])}" target="_blank">GBIF page</a>' if d.get("url") else ""
        out.append(f'<div class="tf-ev"><span class="tf-ref">{esc(d.get("id", ""))}</span>'
                   f'<span class="tf-ev-label">{esc(d["source"])}, {esc(d["about"])}:</span> '
                   f'{esc(d["value"])}{link}</div>')
    if memo.get("checked"):
        out.append('<div class="tf-memo-sub">What was checked</div><ul class="tf-memo-list">'
                   + "".join(f"<li>{esc(c)}</li>" for c in memo["checked"]) + "</ul>")
    dropped = len(memo.get("dropped_quotes") or [])
    notes = []
    if dropped:
        notes.append(f"{dropped} quote{'s' if dropped > 1 else ''} could not be verified against the "
                     f"page or source text and {'were' if dropped > 1 else 'was'} dropped.")
    if memo.get("stopped"):
        notes.append(f"Stopped early: {memo['stopped']}.")
    notes.append("Each reason above points to verified evidence by id; reasons without verified "
                 "support are listed as unverified. The grade is unchanged: the reviewer decides.")
    out.append(f'<div class="tf-memo-foot">{esc(" ".join(notes))}</div>')
    return "".join(out)


def render(report_id, finding, report_title):
    inv = saved(report_id, finding.get("investigation_id") or finding["id"])
    if inv is None:
        ok, why = can_run(report_id)
        if st.button("Investigate", key=f"inv::{report_id}::{finding['id']}", disabled=not ok,
                     help=why or "An agent (Nemotron Ultra) gathers more evidence with tools and "
                                 f"writes a short memo. Max {agent.MAX_STEPS} steps, "
                                 f"${agent.MAX_COST_USD:.2f}, {agent.MAX_CREDITS} web credits."):
            with st.spinner("Investigating..."):
                inv = run(report_id, finding, report_title)
        if inv is None:
            return
    t = inv["totals"]
    label = (f"Investigation: {CONCLUSION_LABELS.get(inv['memo']['conclusion'], '')}  ·  "
             f"{t['steps']} steps, ${t['cost_usd']:.3f}")
    with st.expander(label):
        st.markdown(f'<div class="tf-memo-sub">Steps ({esc(inv["model"].split("/")[-1])}, {esc(inv["mode"])}, '
                    f'recorded {esc(inv.get("created", ""))})</div>' + timeline_html(inv["trace"]),
                    unsafe_allow_html=True)
        st.markdown('<div class="tf-memo-sub" style="margin-top:0.8rem">Evidence memo</div>'
                    + memo_html(inv["memo"]), unsafe_allow_html=True)
        st.caption(f"{t['tool_calls']} tool calls, {t['tokens_in']:,} + {t['tokens_out']:,} tokens, "
                   f"${t['cost_usd']:.3f}, {t['tavily_credits']} web credits, about {t['seconds']:.0f} s.")
