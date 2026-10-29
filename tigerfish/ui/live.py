"""Live mode: upload a short PDF; free checks always, paid checks (Nemotron) within caps.

Offered only when NEBIUS_API_KEY is set (.env locally, Streamlit secrets when hosted).
Free checks (tigerfish/free_checks.py, no model calls): number pairs, and the GBIF species
check when a project site is given. Paid checks: claim extraction + the contradiction check,
with the estimated cost shown first and a cost cap per run. Hosted (tigerfish/hosted.py):
at most hosted.MAX_UPLOAD_PAGES pages and hosted.MAX_UPLOADS_PER_SESSION uploads per session,
the owner's key limited to hosted.DAILY_BUDGET_USD a day, and an optional "your own Nebius
key" field (session only, never stored or logged). Files go to cache/uploads/ (never committed).
"""

import hashlib
import time
from pathlib import Path

import streamlit as st

from tigerfish import (claims, contradictions, free_checks, hosted, llm, pairing, pdf_reader,
                       report)

ROOT = Path(__file__).resolve().parents[2]
UPLOADS = ROOT / "cache" / "uploads"
MAX_PAGES = hosted.MAX_UPLOAD_PAGES
MAX_COST_USD = hosted.MAX_RUN_USD
EST_VERDICT_USD = 0.01        # rough cost of one Ultra verdict, for the upper estimate
SEEN_KEY = "live::seen_uploads"


def available():
    return bool(hosted.owner_key())


def replay_only_note():
    """Shown on the hosted app when no key is configured."""
    return ("This hosted demo runs in replay mode: it shows saved results and makes no model "
            "calls. To audit your own PDF, run TigerFish locally with a Nebius key (see DEPLOY.md in the GitHub repo).")


def save_upload(upload):
    data = upload.getvalue()
    stem = f"upload_{hashlib.sha256(data).hexdigest()[:12]}"
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / f"{stem}.pdf"
    path.write_bytes(data)
    return path


def attach_page_images(pdf, findings):
    """Each finding's pages, with only its own quotes highlighted."""
    for f in findings:
        quotes = {}
        for q in f["quotes"]:
            quotes.setdefault(q["page"], []).append(q["text"])
        images = report.highlight_pages(pdf, quotes, UPLOADS / pdf.stem / "pages",
                                        f"{pdf.stem}_{f['id']}")
        report.attach_images([f], images)
    return findings


def run_free(pdf, pages, site):
    """Free checks (no model calls). Returns findings."""
    found = free_checks.number_pair_findings(pages)
    if site:
        found += free_checks.species_findings(pages, site)
    return attach_page_images(pdf, found)


def run_paid(pdf, pages, progress, max_cost_usd):
    """Claims, then contradictions, within max_cost_usd. Returns (findings, cost in USD)."""
    start_cost = llm.session_cost_usd
    for i, page in enumerate(pages, 1):
        progress.progress(i / (len(pages) + 1), text=f"Reading claims: page {page['page']} "
                                                     f"({i} of {len(pages)})")
        spent = llm.session_cost_usd - start_cost
        claims.extract_claims([page], max_cost_usd=max(0.0, max_cost_usd - spent),
                              pdf_stem=pdf.stem)
    ledger = claims.load_ledger(pdf.stem)
    texts = {p["page"]: p["text"] for p in pages}
    # An upload is no saved report: neutral places, never Great Nicobar's (the default)
    pairing.use_profile({"pairing": pairing.UPLOAD_PAIRING})
    cands = contradictions.candidate_pairs(ledger, keyed=True)
    found = []
    for i, cand in enumerate(cands, 1):
        progress.progress(min(0.99, (len(pages) + i / max(1, len(cands))) / (len(pages) + 1)),
                          text=f"Checking candidate {i} of {len(cands)} with Nemotron Ultra")
        spent = llm.session_cost_usd - start_cost
        out = contradictions.check([cand], texts, max_cost_usd=max(0.0, max_cost_usd - spent),
                                   ledger=ledger)
        for f in out:
            f["id"] = f"{'rf' if f['type'] == 'recycled_figure' else 'ct'}-{len(found) + 1:03d}"
            found.append(f)
    progress.progress(1.0, text="Done")
    findings = attach_page_images(pdf, report.contradiction_findings(found))
    return findings, round(llm.session_cost_usd - start_cost, 4)


def build_report(pdf, pages, free, paid=None, cost_usd=0.0, seconds=0):
    checks = ["Number pairs (rule, free)"]
    if any(f["check"] == "species_range" for f in free) or st.session_state.get("live::site"):
        checks.append("Species out of range (GBIF, free)")
    if paid is not None:
        checks += ["Claim extraction (Nemotron Lightning / Super-VL)",
                   "Internal contradictions and recycled figures (Nemotron Ultra)"]
    return {"id": pdf.stem, "title": "Uploaded report", "source": "uploaded PDF",
            "pages_read": len(pages), "pages_total": len(pages), "checks": checks,
            "cost": {"nebius_usd": cost_usd, "approx_seconds": seconds,
                     "note": "Nemotron models" if paid is not None else "free checks only"},
            "findings": report.sort_findings(free + (paid or []))}


def key_field():
    """Hosted: the visitor's own key (session only), and what the caps are."""
    s = st.session_state
    st.text_input("Your own Nebius key (optional)", key=hosted.BYOK_KEY, type="password",
                  help="Used for this browser session only: never saved, logged or shared. "
                       "With your key, model calls are billed to you and the demo's daily "
                       "budget does not apply.")
    if hosted.uses_owner_budget(s):
        left = hosted.budget.remaining()
        st.caption(f"Demo key: ${left:.2f} of ${hosted.DAILY_BUDGET_USD:.2f} left today (UTC) for "
                   f"model calls, all visitors together.".replace("$", "\\$"))
    st.caption(f"Limits per session: {hosted.MAX_UPLOADS_PER_SESSION} uploads of up to "
               f"{MAX_PAGES} pages ({hosted.uploads_left(s)} left), "
               f"{hosted.MAX_ASKS_PER_SESSION} questions to “Ask the report”, "
               f"\\${MAX_COST_USD:.2f} of model calls per upload.")


def key_field_any():
    """The own-key field everywhere (tigerfish/ui/upload.py). Hosted: with the caps
    (key_field). Locally: says which key the model checks will use."""
    if hosted.is_hosted() and hosted.owner_key():
        key_field()
        return
    st.text_input("Your own Nebius key (optional)", key=hosted.BYOK_KEY, type="password",
                  help="Used for this browser session only: never saved, logged or shared.")
    if hosted.visitor_key(st.session_state):
        st.caption("Model checks will use your key.")
    elif hosted.owner_key():
        st.caption("Model checks will use the key in .env (NEBIUS_API_KEY).")
    else:
        st.caption("No key: the free checks run; the model checks need a key."
                   + (f" Limit: {hosted.MAX_UPLOADS_PER_SESSION} uploads per session "
                      f"({hosted.uploads_left(st.session_state)} left)." if hosted.is_hosted() else ""))


def render():
    """Upload, free checks, estimate, paid checks. Returns a report dict, else None."""
    s = st.session_state
    is_hosted = hosted.is_hosted()
    st.markdown(f"Upload an EIA PDF of up to {MAX_PAGES} pages. The free checks (number pairs, "
                "and species against GBIF if you give the project site) run straight away. The "
                "model checks show their estimated cost first and run only when you start them.")
    if is_hosted:
        key_field()
    upload = st.file_uploader("EIA PDF", type=["pdf"], label_visibility="collapsed")
    if upload is None:
        return s.get("live_report")

    digest = hashlib.sha256(upload.getvalue()).hexdigest()[:12]
    seen = s.setdefault(SEEN_KEY, [])
    if digest not in seen:
        if is_hosted and hosted.uploads_left(s) <= 0:
            st.error(f"Upload limit reached ({hosted.MAX_UPLOADS_PER_SESSION} per session).")
            return s.get("live_report")
        seen.append(digest)
        if is_hosted:
            hosted.bump(s, "uploads")
    pdf = save_upload(upload)
    pages = pdf_reader.read_pdf(pdf)
    if len(pages) > MAX_PAGES:
        st.error(f"This PDF has {len(pages)} pages. Live mode takes at most {MAX_PAGES}; "
                 f"split the file and upload the part you want to check.")
        return None
    s["live_pages"] = {"id": pdf.stem, "pages": pages}

    site_text = st.text_input("Project site for the species check (latitude, longitude)",
                              key="live::site_text", placeholder="e.g. 6.83, 93.87 (optional)")
    site = free_checks.parse_site(site_text)
    if site_text.strip() and site is None:
        st.caption("Write the site as two numbers: latitude, longitude.")
    s["live::site"] = site
    free_key = (digest, site)
    if s.get("live::free_key") != free_key:
        with st.spinner("Free checks (no model calls)..."):
            s["live::free"] = run_free(pdf, pages, site)
        s["live::free_key"] = free_key
        s.pop("live::paid", None)
    free = s["live::free"]
    paid = s.get("live::paid") if s.get("live::paid_key") == digest else None

    cap = hosted.run_cap(s) if is_hosted else MAX_COST_USD
    extract_usd, _ = claims.estimate_cost(pages)
    upper = extract_usd + contradictions.MAX_CANDIDATES * EST_VERDICT_USD
    st.markdown(f"**{len(pages)} pages.** Model checks: about **\\${extract_usd:.3f}** to read "
                f"the claims, plus up to **\\${upper - extract_usd:.2f}** for the contradiction "
                f"check. The run stops at **\\${cap:.2f}**.")
    if cap <= 0:
        st.caption("The demo's daily budget for model calls is used up. The free checks still "
                   "run; add your own Nebius key above to run the model checks.")
    if st.button("Run the model checks", type="primary", disabled=cap <= 0 or paid is not None):
        progress = st.progress(0.0, text="Starting")
        started = time.time()
        try:
            with hosted.paid_calls(s):
                found, cost = run_paid(pdf, pages, progress, cap)
            s["live::paid"], s["live::paid_key"] = found, digest
            s["live::paid_cost"] = (cost, round(time.time() - started))
            paid = found
        except hosted.BudgetExceeded as e:
            st.error(str(e))
        except Exception as e:      # bad key, network: keep the free results
            st.error(f"The model checks could not run ({type(e).__name__}). The free checks "
                     f"are shown below.")
    cost, seconds = s.get("live::paid_cost", (0.0, 0)) if paid is not None else (0.0, 0)
    s["live_report"] = build_report(pdf, pages, free, paid, cost, seconds)
    return s["live_report"]
