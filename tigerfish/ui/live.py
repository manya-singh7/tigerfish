"""Live mode: upload a short PDF and run claim extraction + the contradiction check.

Only offered when NEBIUS_API_KEY is set. Max MAX_PAGES pages. The estimated cost is
shown before anything runs; the run stops at the cost cap. Files go to cache/uploads/
(never committed). Copy-paste and species checks are not run live.
"""

import hashlib
import os
import time
from pathlib import Path

import streamlit as st

from tigerfish import claims, contradictions, llm, pdf_reader, report

ROOT = Path(__file__).resolve().parents[2]
UPLOADS = ROOT / "cache" / "uploads"
MAX_PAGES = 20
MAX_COST_USD = 0.50
EST_VERDICT_USD = 0.01        # rough cost of one Ultra verdict, for the upper estimate


def available():
    return bool(os.getenv("NEBIUS_API_KEY"))


def save_upload(upload):
    data = upload.getvalue()
    stem = f"upload_{hashlib.sha256(data).hexdigest()[:12]}"
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / f"{stem}.pdf"
    path.write_bytes(data)
    return path


def run_audit(pdf, pages, progress):
    """Claims, then contradictions, with progress. Returns a report dict like replay's."""
    started, start_cost = time.time(), llm.session_cost_usd
    for i, page in enumerate(pages, 1):
        progress.progress(i / (len(pages) + 1), text=f"Reading claims: page {page['page']} "
                                                     f"({i} of {len(pages)})")
        spent = llm.session_cost_usd - start_cost
        claims.extract_claims([page], max_cost_usd=max(0.0, MAX_COST_USD - spent),
                              pdf_stem=pdf.stem)
    ledger = claims.load_ledger(pdf.stem)
    texts = {p["page"]: p["text"] for p in pages}
    cands = contradictions.candidate_pairs(ledger)
    found = []
    for i, cand in enumerate(cands, 1):
        progress.progress(min(0.99, (len(pages) + i / max(1, len(cands))) / (len(pages) + 1)),
                          text=f"Checking candidate {i} of {len(cands)} with Nemotron Ultra")
        spent = llm.session_cost_usd - start_cost
        out = contradictions.check([cand], texts, max_cost_usd=max(0.0, MAX_COST_USD - spent),
                                   ledger=ledger)
        for f in out:
            f["id"] = f"{'rf' if f['type'] == 'recycled_figure' else 'ct'}-{len(found) + 1:03d}"
            found.append(f)
    findings = report.contradiction_findings(found)
    for f in findings:   # each finding's pages show only its own quotes highlighted
        quotes = {}
        for q in f["quotes"]:
            quotes.setdefault(q["page"], []).append(q["text"])
        images = report.highlight_pages(pdf, quotes, UPLOADS / pdf.stem / "pages",
                                        f"{pdf.stem}_{f['id']}")
        report.attach_images([f], images)
    progress.progress(1.0, text="Done")
    return {"id": pdf.stem, "title": "Uploaded report", "source": "uploaded PDF",
            "pages_read": len(pages), "pages_total": len(pages),
            "checks": ["Claim extraction (Nemotron Lightning / Super-VL)",
                       "Internal contradictions and recycled figures (Nemotron Ultra)"],
            "cost": {"nebius_usd": round(llm.session_cost_usd - start_cost, 4),
                     "approx_seconds": round(time.time() - started)},
            "findings": report.sort_findings(findings)}


def render():
    """Upload, estimate, run. Returns a report dict when a run has finished, else None."""
    st.markdown("Upload an EIA PDF of up to 20 pages. TigerFish shows the estimated cost first; "
                "nothing is sent to the models until you start the audit. The copy-paste and "
                "species checks run only in the saved reports.")
    upload = st.file_uploader("EIA PDF", type=["pdf"], label_visibility="collapsed")
    if upload is None:
        return st.session_state.get("live_report")
    pdf = save_upload(upload)
    pages = pdf_reader.read_pdf(pdf)
    if len(pages) > MAX_PAGES:
        st.error(f"This PDF has {len(pages)} pages. Live mode takes at most {MAX_PAGES}; "
                 f"split the file and upload the part you want to check.")
        return None
    extract_usd, uncached = claims.estimate_cost(pages)
    upper = extract_usd + contradictions.MAX_CANDIDATES * EST_VERDICT_USD
    st.markdown(f"**{len(pages)} pages.** Estimated cost: about **${extract_usd:.3f}** to read "
                f"the claims, plus up to **${upper - extract_usd:.2f}** for the contradiction "
                f"check. The run stops at **${MAX_COST_USD:.2f}**.")
    if st.button("Start audit", type="primary"):
        progress = st.progress(0.0, text="Starting")
        st.session_state["live_report"] = run_audit(pdf, pages, progress)
    return st.session_state.get("live_report")
