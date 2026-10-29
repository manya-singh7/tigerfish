"""Upload a new EIA (one the app has never seen). Nothing is looked up per report.

Three levels, shown side by side with their cost before anything paid runs:
  Quick check (free, whole report)   every free check on every page with a text layer
                                     (tigerfish/upload_checks.py): no key needed
  Deep audit (chosen pages, live)    the model checks on up to page_picks.MAX_PAGES pages the
                                     visitor chooses: a page range, a quick pick built from the
                                     report's own headings (tigerfish/page_picks.py), or by
                                     default the pages with the most figures and species names.
                                     Needs a key (the site's or the visitor's), within the caps
  Full audit                         every page: run locally (scripts/audit.py) or with your
                                     own key; the estimate uses the cost per page of the saved
                                     full runs in results/

Project, state, site, consultant and year come from the report's text (tigerfish/detect.py;
one cheap Lightning call on the first pages when a key is available), shown as "detected:
<value> (page N), check this", and are editable. The PDF stays in cache/uploads/ (never
committed). Returns the report dict for the usual report view, or None before an upload.
"""

import hashlib
import json
import time
from pathlib import Path

import pymupdf
import streamlit as st

from tigerfish import claims, contradictions, detect, hosted, page_picks, pdf_reader, upload_checks
from tigerfish import library
from tigerfish.ui import live
from tigerfish.ui.library import UPLOAD_NOTE
from tigerfish.ui.style import esc

S = "upload::"          # session-state prefix
NOT_DETECTED = "not detected"
MAX_FREE_PAGES = 2000   # the free checks read at most this many pages of one upload
DEFAULT_PICK = "Pages with the most figures and species names (default)"
RANGE_PICK = "Type a page range"
NOTE = UPLOAD_NOTE


def has_key():
    return bool(hosted.paid_key(st.session_state))


def full_audit_rates():
    """(low, high) USD per page from the saved full runs in results/ (None if none)."""
    rates = []
    for e in library.entries():
        try:
            run = json.loads(Path(e["path"]).read_text(encoding="utf-8")).get("full_run") or {}
        except (OSError, ValueError):
            continue
        if run.get("cost_usd") and run.get("pages_audited"):
            rates.append(run["cost_usd"] / run["pages_audited"])
    return (min(rates), max(rates)) if rates else None


def levels(n_pages, chosen_usd=None):
    """The three levels as cards."""
    a, b, c = st.columns(3)
    where = f"all {n_pages:,} pages" if n_pages else "every page"
    a.markdown(f"**Quick check (free, whole report)**  \nAvailable free checks on the readable text of {where}: number pairs, species and IUCN categories vs GBIF, threatened species "
        "near the site that are never mentioned. Page/name limits and missing-input restrictions apply. No key, no model cost.")
    cost = (f"Estimated **\\${chosen_usd:.2f}** for the pages chosen below."
            if chosen_usd is not None else "Cost shown before it runs.")
    b.markdown(f"**Deep audit (chosen pages, live)**  \nThe model checks (claims, contradictions, "
               f"recycled figures) on up to {page_picks.MAX_PAGES} pages you choose. Needs a key: "
               f"the site's or your own. {cost}")
    rates = full_audit_rates()
    est = (f" This report: about \\${rates[0] * n_pages:.0f}-{rates[1] * n_pages:.0f} "
           f"({n_pages:,} pages at the cost per page of our saved full runs)."
           if rates and n_pages else "")
    price = library.price_line(library.entries(), dollar="\\$")   # from the saved full runs
    c.markdown("**Full audit (your own key or run locally)**"
               + (f"  \n{price}." if price else "")
               + f"  \nScoped report processing; specialized checks need their own scripts and inputs.{est} Run `scripts/audit.py` locally "
        "with your own keys. The saved full runs took about an hour each.")


def save(upload):
    """(saved pdf path, page count)."""
    path = live.save_upload(upload)
    with pymupdf.open(path) as doc:
        return path, doc.page_count


def render_chosen(pdf, pages, chosen):
    """The chosen pages, with a PNG for each page that needs Super-VL (tables, scans)."""
    by_no = {p["page"]: p for p in pages}
    out = []
    with pymupdf.open(pdf) as doc:
        for n in chosen:
            p = dict(by_no[n])
            if p.get("needs_vision") and not p.get("image_path"):
                p["image_path"] = str(pdf_reader.render_page(doc.load_page(n - 1), pdf.stem, n))
            out.append(p)
    return out


def detected_caption(f, label):
    if not f:
        return f"{label}: not detected in the report text. Enter it if you know it."
    value = f["value"]
    if isinstance(value, tuple):
        value = f"{value[0]}, {value[1]}"
    how = "" if f["how"] == "text search" else f" ({f['how']})"
    return f"Detected: {value} (page {f['page']}){how}. Check this."


def fields_form(found, digest):
    """Editable fields, prefilled with what was detected. Returns the visitor's values."""
    s = st.session_state
    k = lambda name: f"{S}{digest}::{name}"
    defaults = {"project": (found.get("project") or {}).get("value") or "",
                "consultant": (found.get("consultant") or {}).get("value") or "",
                "year": str((found.get("year") or {}).get("value") or ""),
                "site": ", ".join(str(x) for x in (found.get("site") or {}).get("value") or ()),
                "state": (found.get("state") or {}).get("value") or NOT_DETECTED}
    for name, value in defaults.items():
        s.setdefault(k(name), value)
    st.markdown("#### What TigerFish found in the report")
    st.caption("Read from the report's own text. Check each one and correct it if needed: the "
               "species checks use the site, and the letter's language follows the state.")
    a, b = st.columns(2)
    project = a.text_input("Project name", key=k("project"))
    a.caption(detected_caption(found.get("project"), "Project name"))
    state = b.selectbox("State / union territory", [NOT_DETECTED] + detect.STATES, key=k("state"))
    b.caption(detected_caption(found.get("state"), "State"))
    c, d = st.columns(2)
    site_text = c.text_input("Project site (latitude, longitude)", key=k("site"),
                             placeholder="e.g. 11.7062, 79.7751")
    site_f = found.get("site")
    c.caption(detected_caption(site_f, "Project site"))
    consultant = d.text_input("EIA consultant", key=k("consultant"))
    d.caption(detected_caption(found.get("consultant"), "EIA consultant"))
    e, g = st.columns(2)
    year = e.text_input("Year", key=k("year"))
    e.caption(detected_caption(found.get("year"), "Year"))
    state_value = None if state == NOT_DETECTED else state
    lang = detect.letter_language(state_value)
    g.text_input("Letter language", value=lang["value"], disabled=True, key=k(f"lang::{state}"))
    if lang["regional"] and not lang["translated"]:
        g.caption(f"From the state. A {lang['regional']} letter is not available yet; English "
                  f"and Hindi are.")
    else:
        g.caption("From the state. Translations need a key (machine-translated, marked as such).")
    site = live.free_checks.parse_site(site_text)
    if site_text.strip() and site is None:
        c.error("Write the site as two numbers: latitude, longitude.")
    detected_site = tuple(site_f["value"]) if site_f else None
    approx = bool(site_f and "midpoint" in site_f["how"] and site == detected_site)
    if approx:
        c.caption("This is the midpoint of a range the report gives (a statewide or district-wide "
                  "report): checks that need one project site are not run.")
    try:
        year_value = int(year) if year.strip() else None
    except ValueError:
        year_value = None
    return {"project": project.strip() or "Uploaded report", "state": state_value, "site": site,
            "site_approximate": approx, "consultant": consultant.strip() or None,
            "year": year_value, "site_label": "the site detected from the report"
            if site and site == detected_site else "the site you entered"}


def status_table(statuses):
    rows = "".join(
        f"<tr><td>{esc(x['name'])}</td><td><b>{esc(x['status'])}</b>"
        + (f": {x['count']} finding{'s' if x['count'] != 1 else ''}" if x.get("count") is not None
           and x["status"] == upload_checks.RAN else "")
        + (f"<div class='tf-step-why'>{esc(x['detail'])}</div>" if x.get("detail") else "")
        + "</td></tr>" for x in statuses)
    st.markdown(f'<table class="tf-table"><tr><th>Check</th><th>Status</th></tr>{rows}</table>',
                unsafe_allow_html=True)


def page_chooser(pages, digest):
    """Up to MAX_PAGES page numbers for the deep audit, and how they were chosen."""
    s = st.session_state
    if s.get(f"{S}picks_for") != digest:
        with st.spinner("Finding the report's sections (free)..."):
            s[f"{S}picks"] = page_picks.quick_picks(pages)
            s[f"{S}default"] = page_picks.default_pick(pages)
        s[f"{S}picks_for"] = digest
    picks = {f"{p['label']} (pp. {page_picks.fmt_pages(p['pages'])})": p for p in s[f"{S}picks"]}
    choice = st.radio("Pages for the deep audit", [DEFAULT_PICK] + list(picks) + [RANGE_PICK],
                      key=f"{S}{digest}::pick")
    if choice == RANGE_PICK:
        text = st.text_input(f"Pages (up to {page_picks.MAX_PAGES})", key=f"{S}{digest}::range",
                             placeholder="e.g. 140-160, 212")
        chosen, err = page_picks.parse_range(text, len(pages))
        if err:
            st.caption(err)
        how = "the page range you typed"
    elif choice in picks:
        chosen, how = picks[choice]["pages"], picks[choice]["how"]
    else:
        chosen = s[f"{S}default"]
        how = ("the pages with the most figures (numbers with units) and Latin species names, "
               "skipping lab sheets, forms and Hindi pages")
    if chosen:
        st.caption(f"{len(chosen)} pages: {page_picks.fmt_pages(chosen)}. Chosen from {how}.")
    return chosen


MAX_UPLOAD_MB = 100      # also server.maxUploadSize; checked again here, on the server
MAX_UPLOAD_PDF_PAGES = 5000


def validate_pdf(data):
    """(error message or None, page count). Checked on the server, whatever the browser sent:
    the file type by its bytes, the size, and that the PDF opens and has pages."""
    if not data:
        return "The file is empty. Choose the EIA PDF again.", 0
    mb = len(data) / 1e6
    if mb > MAX_UPLOAD_MB:
        return (f"This file is {mb:,.0f} MB; the limit is {MAX_UPLOAD_MB} MB. Upload the main "
                "report volume on its own, or run scripts/audit.py locally for larger files."), 0
    if b"%PDF-" not in data[:1024]:
        return ("This file is not a PDF (it does not start like one, whatever its name). Upload "
                "the EIA as a PDF."), 0
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                return ("This PDF is password-protected, so its text cannot be read. Upload a "
                        "copy without a password."), 0
            n = doc.page_count
    except Exception:
        return ("This PDF could not be opened: it may be damaged or incomplete. Download it "
                "again and upload the new copy."), 0
    if n == 0:
        return "This PDF has no pages. Check that it is the full report.", 0
    if n > MAX_UPLOAD_PDF_PAGES:
        return (f"This PDF has {n:,} pages; the limit is {MAX_UPLOAD_PDF_PAGES:,}. Upload one "
                "volume at a time."), n
    return None, n


def read_upload(upload, digest):
    s = st.session_state
    if s.get(f"{S}digest") == digest:
        return
    with st.spinner("Reading the whole PDF (text only, free)..."):
        pdf, total = save(upload)
        pages = pdf_reader.read_pdf(pdf, render=False)[:MAX_FREE_PAGES]
    for key in [k for k in list(s.keys()) if str(k).startswith(S)]:
        del s[key]
    s.update({f"{S}digest": digest, f"{S}pdf": str(pdf), f"{S}pages": pages, f"{S}total": total})


def render():
    s = st.session_state
    is_hosted = hosted.is_hosted()
    st.caption(NOTE + f" PDF only, up to {MAX_UPLOAD_MB} MB.")
    live.key_field_any()
    upload = st.file_uploader("EIA PDF", type=["pdf"], label_visibility="collapsed")
    if upload is None:
        levels(0)
        st.markdown(
            "- **Without a key:** the quick check runs on the whole report.\n"
            "- **With a key** (the site's, or your own): also the deep audit on the pages you "
            "choose. Its cost is shown before it runs.\n"
            "- **Locally only:** copied text, consultant accreditation and WPA schedules (Tavily "
            "credits), ToR promises (needs the ToR PDF), and the full audit of every page.")
        return None

    error, _ = validate_pdf(upload.getvalue())
    if error:
        st.error(f"Upload not accepted. {error}")
        return None
    digest = hashlib.sha256(upload.getvalue()).hexdigest()[:12]
    seen = s.setdefault(live.SEEN_KEY, [])
    if digest not in seen:
        if is_hosted and hosted.uploads_left(s) <= 0:
            st.error(f"Upload limit reached ({hosted.MAX_UPLOADS_PER_SESSION} per session).")
            return None
        seen.append(digest)
        if is_hosted:
            hosted.bump(s, "uploads")
    read_upload(upload, digest)
    pdf, pages, total = Path(s[f"{S}pdf"]), s[f"{S}pages"], s[f"{S}total"]
    if len(pages) < total:
        st.info(f"This PDF has {total:,} pages; the free checks read the first {len(pages):,}.")

    if f"{S}found" not in s:
        with st.spinner("Finding the project, state and site in the text..."):
            found = detect.detect(pages)
            if has_key():
                try:
                    with hosted.paid_calls(s):
                        found = detect.detect(pages, use_model=True)
                except Exception as e:          # budget used up, bad key: text search only
                    found["model_error"] = type(e).__name__
        s[f"{S}found"] = found
    found = s[f"{S}found"]
    if found.get("model_error"):
        st.caption(f"The model read of the first pages failed ({esc(found['model_error'][:80])}); "
                   "these come from plain text search.")
    meta = fields_form(found, digest)
    meta["pages_total"] = len(pages)

    free_key = (digest, meta["site"], meta["state"], meta["site_approximate"])
    if s.get(f"{S}free_key") != free_key:
        with st.spinner(f"Quick check: free checks on all {len(pages):,} pages..."):
            findings, statuses = upload_checks.run_free(pages, meta)
            s[f"{S}free"] = (live.attach_page_images(pdf, findings), statuses)
        s[f"{S}free_key"] = free_key
    free, statuses = s[f"{S}free"]

    paid = s.get(f"{S}paid")
    cost, seconds, paid_pages = s.get(f"{S}paid_cost", (0.0, 0, []))

    st.markdown("#### Deep audit: choose the pages")
    chosen = page_chooser(pages, digest)
    chosen_pages = [p for p in pages if p["page"] in set(chosen)]
    extract_usd, _ = claims.estimate_cost(chosen_pages)
    upper = extract_usd + contradictions.MAX_CANDIDATES * live.EST_VERDICT_USD
    cap = (hosted.run_cap(s) if is_hosted else live.MAX_COST_USD) if has_key() else 0.0

    st.markdown("#### Three levels")
    levels(len(pages), upper if chosen else None)
    st.markdown("#### Checks")
    status_table(statuses + upload_checks.keyed_statuses(has_key(), paid is not None,
                                                         cost if paid is not None else None))

    st.markdown("#### Deep audit")
    if not has_key():
        st.info("No key: only the quick check ran. The deep audit (contradictions and recycled "
                "figures on the pages you chose) needs a Nebius key: paste your own above"
                + (" or run TigerFish locally." if is_hosted else ", or set NEBIUS_API_KEY in .env."))
    elif chosen:
        st.markdown(f"**{len(chosen)} pages chosen.** Estimated cost: about **\\${extract_usd:.3f}** "
                    f"to read the claims, plus up to **\\${upper - extract_usd:.2f}** for the "
                    f"contradiction check (at most **\\${upper:.2f}**). The run stops at "
                    f"**\\${cap:.2f}**.")
        if paid is not None:
            st.caption(f"Ran on pp. {page_picks.fmt_pages(paid_pages)}: \\${cost:.3f}.")
        if st.button("Run the deep audit", type="primary", disabled=cap <= 0 or paid is not None):
            progress = st.progress(0.0, text="Starting")
            started = time.time()
            try:
                with hosted.paid_calls(s):
                    found_paid, cost = live.run_paid(pdf, render_chosen(pdf, pages, chosen),
                                                     progress, cap)
                s[f"{S}paid"] = found_paid
                s[f"{S}paid_cost"] = (cost, round(time.time() - started), chosen)
                st.rerun()
            except hosted.BudgetExceeded as e:
                st.error(str(e))
            except Exception as e:      # bad key, network: keep the free results
                st.error(f"The deep audit could not run ({type(e).__name__}). The quick-check "
                         f"results are shown below.")

    return build_report(pdf, pages, total, meta, found, free, statuses, paid, cost, seconds, paid_pages)


def build_report(pdf, pages, total, meta, found, free, statuses, paid=None, cost_usd=0.0,
                 seconds=0, paid_pages=()):
    checks = [x["name"] for x in statuses if x["status"] == upload_checks.RAN]
    if paid is not None:
        checks += [f"{name} (pp. {page_picks.fmt_pages(paid_pages)})" for _, name in upload_checks.KEYED]
    notices = ["Uploaded report: flags are leads to verify against the report, not verdicts."]
    if paid is None:
        notices.append("Quick check: free checks only; the deep audit has not run.")
    if len(pages) < total:
        notices.append(f"The free checks read the first {len(pages):,} of {total:,} pages.")
    return {"id": pdf.stem, "title": meta["project"], "project": meta["project"],
            "source": "uploaded PDF" + (f", consultant: {meta['consultant']}" if meta.get("consultant") else ""),
            "state": meta["state"], "year": meta["year"],
            "site": {"lat": meta["site"][0], "lon": meta["site"][1], "label": meta["site_label"]}
            if meta["site"] else None,
            "detected": {k: found.get(k) for k in detect.FIELDS},
            "pages_read": len(pages), "pages_total": total, "checks": checks,
            "checks_run": statuses, "audit_type": "upload", "notices": notices,
            "pages_note": "pages read by the free checks"
                          + (f"; model checks on {len(paid_pages)}" if paid is not None else ""),
            "cost": {"nebius_usd": cost_usd, "approx_seconds": seconds,
                     "note": "Nemotron models" if paid is not None else "free checks only"},
            "findings": live.report.sort_findings(free + (paid or []))}
