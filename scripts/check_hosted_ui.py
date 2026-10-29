"""Browser check of the app in hosted mode (no keys): the report library (live totals, filters,
search, a quick check in the lighter view, back link), the no-key upload (detected facts, free
checks, which checks need a key, the three levels); then the report opened from the library:
hero, findings with badges and page images, species map, official record, letter and RTI
downloads, letter-language gating, public record with the merged paper trail (one timeline,
documents found with their Tavily tag, who to write to), ToR promises (granted and proposed),
knowable-at-the-time line, species photos, cost card and efficiency line, every tab;
Indira Point (no document guessed); Cuddalore (audit status from the saved audit, Tamil letter,
documents, TNPCB contact); copied-text self-matches in a collapsed "Excluded matches" list
(Cuddalore, Karnataka); the back link; no exceptions.

Start the app first, with no keys and the sample quick checks from tests/fixtures:
  set TIGERFISH_HOSTED=1 && set NEBIUS_API_KEY= && set TAVILY_API_KEY= &&
  set TIGERFISH_BATCH_DIR=tests/fixtures/library/batch &&
  streamlit run app.py --server.headless true --server.port 8631
Then:  python scripts/check_hosted_ui.py http://localhost:8631 shots/   (needs requirements-dev.txt)
"""
import json
import os
import sys
from pathlib import Path

import pymupdf
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TIGERFISH_BATCH_DIR", "tests/fixtures/library/batch")   # as the app was started
from tigerfish import library  # noqa: E402

URL, OUT = sys.argv[1], Path(sys.argv[2])
ROOT_RESULTS = ROOT / "results"
OUT.mkdir(parents=True, exist_ok=True)
results, errors = [], []


def ok(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def idle(page, timeout=120_000):
    """Wait until Streamlit has finished rerunning (stale elements are gone)."""
    page.wait_for_timeout(800)
    page.wait_for_function("""() => !document.querySelector('[data-testid="stStatusWidget"]')
        && document.querySelectorAll('[data-stale="true"]').length === 0""", timeout=timeout)
    page.wait_for_timeout(500)


def excluded_matches(page, name, report_id):
    """GREY copied-text self-matches: a collapsed "Excluded matches (N)" list with the URLs."""
    rows = json.loads((ROOT_RESULTS / f"{report_id}.json").read_text(encoding="utf-8")).get(
        "excluded_matches") or []
    exp = page.locator('[data-testid="stExpander"]').filter(has_text=f"Excluded matches ({len(rows)})")
    ok(f"{name}: 'Excluded matches ({len(rows)})' list", exp.count() == 1 if rows else exp.count() == 0)
    if not rows:
        return
    url = exp.locator(".tf-excluded code").first
    ok(f"{name}: excluded matches collapsed", not url.is_visible())
    exp.locator("summary").first.click()
    page.wait_for_timeout(800)
    ok(f"{name}: excluded match shows GREY self-match and URL",
       url.is_visible() and rows[0]["url"] in url.inner_text()
       and exp.get_by_text("self-match: same report published elsewhere").count() > 0)


def no_exception(page, where):
    n = page.locator('[data-testid="stException"]').count()
    ok(f"no exception: {where}", n == 0, f"{n} exception boxes")


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL, timeout=120_000)

    # ---------- the library (home screen) ----------
    page.wait_for_selector(".tf-lib-total", timeout=180_000)
    page.wait_for_timeout(1500)
    items = library.entries()
    expected = library.totals_line(library.totals(items))
    shown = page.locator(".tf-lib-total").inner_text().strip()
    ok("library: totals computed from results/", shown == expected, shown)

    def opens():
        idle(page)
        return page.locator(".tf-lib-title:visible").count()

    ok("library: one row per report", opens() == len(items), f"{opens()} rows, {len(items)} reports")
    ok("library: upload button and note",
       page.get_by_role("button", name="Upload your own EIA").count() == 1
       and page.get_by_text("Saved audits are full runs").count() > 0)
    page.get_by_text("Has RED flags").click()
    page.wait_for_timeout(2500)
    n_red = sum(e["grades"]["RED"] > 0 for e in items)
    ok("library: 'Has RED flags' filter", opens() == n_red, f"{opens()} shown, {n_red} expected")
    page.get_by_text("Has RED flags").click()
    page.wait_for_timeout(2000)
    search = page.get_by_label("Search by project name")
    search.fill("Cuddalore")
    search.press("Enter")
    page.wait_for_timeout(2500)
    ok("library: search by project name", opens() == 1, f"{opens()} shown")
    search.fill("")
    search.press("Enter")
    page.wait_for_timeout(2500)
    # quality across all reports, from the saved review files; Indira Point is not a full audit
    ok("library: Quality section", page.get_by_role("heading", name="Quality").count() > 0
       and page.get_by_text("RED/ORANGE flags,").count() > 0)
    table_rows = [e for e in items if e["audit_type"] == library.TABLE]
    ok("library: single-table check labelled", not table_rows or (
        page.locator(".tf-lib-table").count() == len(table_rows)
        and page.get_by_text(library.TABLE_NOTE).count() == len(table_rows)))
    ok("library: no 'No reviews saved yet'", page.get_by_text("No reviews saved yet").count() == 0)
    page.screenshot(path=str(OUT / "library.png"), full_page=True)
    no_exception(page, "library")

    # ---------- upload a new EIA with no key ----------
    pdf = OUT / "visitor_upload.pdf"
    doc = pymupdf.open()
    for text in ("India: Sample Harbour Expansion Project\nDraft EIA Report\nMay 2026\n"
                 "Prepared by Sample Enviro Consultants Pvt. Ltd. for the Port Trust.",
                 "The harbour is in Tamil Nadu. Tamil Nadu has a long coast.",
                 "The site is located at latitude 11°42'22\" N, longitude 79°46'30\" E.",
                 "The total reclaimed area is 45 ha at the harbour site.",
                 "The total reclaimed area is 62 ha at the harbour site."):
        doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=11)
    doc.save(pdf)
    page.get_by_role("button", name="Upload your own EIA").click()
    page.get_by_text("Quick check (free, whole report)").first.wait_for(timeout=60_000)
    idle(page)
    ok("upload: three levels shown", page.get_by_text("Deep audit (chosen pages, live)").count() > 0
       and page.get_by_text("Full audit (your own key or run locally").count() > 0)
    ok("upload: no-key note", page.get_by_text("No key: the free checks run").count() > 0)
    price = library.price_line(items)
    ok("upload: full-audit price measured from saved runs", price and page.get_by_text(
        price.split(" (measured")[0]).count() > 0 and page.get_by_text("$4-13").count() == 0, price)
    page.locator('[data-testid="stFileUploaderDropzoneInput"]').set_input_files(str(pdf))
    page.get_by_text("Deep audit: choose the pages").wait_for(timeout=240_000)
    page.get_by_text("No key: only the quick check ran").wait_for(timeout=240_000)
    idle(page, 300_000)
    ok("upload: state detected with its page", page.get_by_text("Detected: Tamil Nadu (page 2)").count() > 0)
    ok("upload: site detected", page.get_by_text("Detected: 11.7061").count() > 0)
    ok("upload: free checks ran", page.get_by_text("Number pairs: the same subject").count() > 0
       and page.locator("td", has_text="ran").count() >= 3)
    ok("upload: model checks need a key", page.get_by_text("needs a Nebius key").count() > 0)
    ok("upload: local-only checks listed", page.locator("td", has_text="run locally").count() >= 4)
    page.screenshot(path=str(OUT / "upload_no_key.png"), full_page=True)
    no_exception(page, "upload without a key")
    page.get_by_role("button", name="Back to library").click()
    page.wait_for_selector(".tf-lib-total", timeout=60_000)
    ok("back link: upload -> library", page.locator(".tf-lib-total").count() == 1)

    # ---------- open the Great Nicobar report from the library ----------
    idle(page)
    page.locator('[data-testid="stButton"] button', has_text="Open").first.click()
    page.wait_for_selector(".tf-hero", timeout=180_000)
    page.get_by_text("Does it match the official record?").wait_for(timeout=180_000)  # full render
    page.wait_for_timeout(3000)
    ok("hero card", page.locator(".tf-hero-headline").count() > 0)
    ok("back link on the report", page.get_by_role("button", name="Back to library").count() == 1)
    ok("no live toggle without a key", page.locator('[data-testid="stToggle"]').count() == 0
       or page.get_by_text("Live mode").count() == 0)
    ok("finding badges", page.locator(".tf-model").count() > 0, f"{page.locator('.tf-model').count()} badges")
    ok("human-verified badge", page.get_by_text("Human-verified").count() > 0)
    exp = page.get_by_text("Show highlighted page").first
    exp.click()
    page.wait_for_timeout(2500)
    imgs = page.locator('[data-testid="stImage"] img, [data-testid="stImageContainer"] img')
    loaded = page.evaluate("""() => [...document.querySelectorAll('img')].filter(
        i => i.complete && i.naturalWidth > 100).length""")
    ok("page images load", imgs.count() > 0 and loaded > 0, f"{imgs.count()} images, {loaded} loaded")
    ok("species map", page.get_by_text("Where the flagged species are actually recorded").count() > 0
       and page.locator(".js-plotly-plot").count() > 0)
    ok("official record", page.get_by_text("Does it match the official record?").count() > 0)
    no_exception(page, "Findings")
    page.screenshot(path=str(OUT / "findings.png"))

    # letter + RTI: mark the first finding Confirm, then download both
    page.locator("button", has_text="Confirm").first.click()
    page.get_by_role("button", name="Draft objection letter (.docx)").and_(
        page.locator(":enabled")).wait_for(timeout=120_000)
    page.wait_for_timeout(3000)
    for label, suffix in (("Draft objection letter (.docx)", ".docx"),
                          ("RTI + public hearing pack (.zip)", ".zip")):
        btn = page.get_by_role("button", name=label)
        with page.expect_download(timeout=60_000) as d:
            btn.click()
        path = OUT / f"download{suffix}"
        d.value.save_as(str(path))
        ok(f"download {label}", path.stat().st_size > 1000, f"{path.stat().st_size} bytes")
    ok("reviews kept in session (wording)", page.get_by_text("in this browser session only").count() > 0)
    ok("species photo with attribution", page.locator(".tf-photo img").count() > 0
       and page.get_by_text("via Wikimedia Commons").count() > 0)

    # letter language: Tamil only for Tamil Nadu reports; a translation without a key is gated
    radio = page.locator('[data-testid="stRadio"]').filter(has_text="Letter language")
    ok("no Tamil option for a non-Tamil Nadu report", radio.get_by_text("Tamil").count() == 0)
    radio.get_by_text("Hindi", exact=True).click()
    try:
        page.get_by_text("needs the translation model").wait_for(timeout=120_000)   # full rerun
    except Exception:
        pass
    ok("Hindi letter gated without a key", page.get_by_text("needs the translation model").count() > 0
       and page.get_by_role("button", name="Draft objection letter (.docx)").is_disabled())
    radio.get_by_text("English", exact=True).click()
    page.get_by_role("button", name="Draft objection letter (.docx)").and_(
        page.locator(":enabled")).wait_for(timeout=120_000)

    for tab, marker, shot in (("Review queue", "Review queue: Great Nicobar", "review"),
                              ("Reviewer's memo & Ask", "Ask the report", "memo"),
                              ("Public record", "Timeline (official sources)", "record"),
                              ("Evidence from the web", "Evidence from the web", "web"),
                              ("Scanned pages", "How TigerFish reads scanned pages", "inspector"),
                              ("Method & limits", "Evaluation", "method")):
        page.get_by_role("tab", name=tab).click()
        page.wait_for_timeout(2000)
        ok(f"tab {tab}", page.get_by_text(marker).count() > 0)
        page.screenshot(path=str(OUT / f"{shot}.png"))
    page.get_by_role("tab", name="Review queue").click()
    page.wait_for_timeout(1500)
    ok("review queue: committed decisions read-only", page.get_by_text("shown read-only").count() > 0)
    ok("review queue: too few judged, no percentage", page.get_by_text("Too few judged").count() > 0
       or page.get_by_text("% (").count() > 0)
    page.get_by_role("tab", name="Findings").click()
    page.wait_for_timeout(1500)
    ok("findings: team reviews apart from yours", page.get_by_text("Team reviews (saved)").count() > 0
       and page.get_by_text("Your reviews (this browser session)").count() > 0
       and page.get_by_text("No reviews saved yet").count() == 0)
    page.get_by_role("tab", name="Reviewer's memo & Ask").click()
    page.wait_for_timeout(1000)
    ok("memo: reviewer's memo", page.get_by_text("Reviewer's memo").count() > 0)
    page.get_by_role("tab", name="Scanned pages").click()
    page.wait_for_timeout(1500)
    loaded = page.evaluate("""() => [...document.querySelectorAll('img')].filter(
        i => i.complete && i.naturalWidth > 100 && i.offsetParent !== null).length""")
    ok("inspector images", loaded > 0, f"{loaded} visible images")
    page.get_by_role("tab", name="Method & limits").click()
    page.wait_for_timeout(1500)
    ok("cost card", page.get_by_text("Cost per full audit, by triage mode").count() > 0)
    eff = page.locator(".tf-efficiency")
    ok("efficiency line on the cost card", eff.filter(has_text="Context efficiency").count() > 0
       and eff.filter(has_text="Tavily returned").count() > 0)
    page.get_by_role("tab", name="Public record").click()
    page.wait_for_timeout(1500)
    ok("public record: what happened next", page.get_by_text("What happened next").count() > 0)
    # merged paper trail: one timeline, documents found with their Tavily tag, contacts
    rows = page.locator("table.tf-timeline tr").count()
    ok("public record: one timeline", page.get_by_text("Timeline (official sources)").count() == 1
       and page.get_by_role("heading", name="Clearance timeline (official sources)").count() == 0
       and rows > 1, f"{rows - 1} events")
    ok("public record: documents found", page.get_by_text("Documents found").count() > 0
       and page.locator(".tf-doc").count() > 0, f"{page.locator('.tf-doc').count()} documents")
    ok("public record: found-via tags", page.locator(".tf-doc .tf-via").filter(
        has_text="Found via Tavily").count() == page.locator(".tf-doc").count())
    ok("public record: who to write to", page.get_by_text("Who to write to").count() > 0
       and page.get_by_text("Check the address before sending.").count() > 0)
    ok("public record: no duplicate tab", page.get_by_role("tab", name="Paper trail").count() == 0)
    page.get_by_role("tab", name="Evidence from the web").click()
    page.wait_for_timeout(1500)
    ok("efficiency line in the web tab", page.locator(".tf-efficiency").filter(
        has_text="Tavily returned").count() > 0 and page.get_by_text("Context efficiency").count() > 0)
    page.get_by_role("tab", name="ToR promises").click()
    page.wait_for_timeout(1500)
    ok("ToR promises: granted and proposed labelled", page.get_by_text("Granted ToR (MoEFCC letter").count() > 0
       and page.get_by_text("Proposed ToR (").count() > 0)
    no_exception(page, "all tabs")

    # second report: knowable-at-the-time line and species photos on its cards
    page.locator('[data-testid="stSelectbox"]').first.click()
    page.get_by_role("option", name="Indira Point").click()
    page.wait_for_timeout(1000)
    page.get_by_role("tab", name="Findings").click()
    page.locator(".tf-knowable").first.wait_for(timeout=120_000)
    ok("knowable at the time line", page.locator(".tf-knowable").count() > 0)
    ok("species photos (second report)", page.locator(".tf-photo img").count() > 1,
       f"{page.locator('.tf-photo img').count()} photos")
    page.screenshot(path=str(OUT / "second_report.png"))
    page.get_by_role("tab", name="Public record").click()
    page.wait_for_timeout(2000)
    ok("second report: no document guessed", page.get_by_text(
        "No official document naming this project was found").count() > 0
       and page.locator(".tf-doc").filter(visible=True).count() == 0)
    no_exception(page, "second report")

    # Cuddalore (Tamil Nadu): audit-status and not-reviewed notices, Tamil letter offered
    page.locator('[data-testid="stSelectbox"]').first.click()
    page.get_by_role("option", name="Cuddalore").click()
    page.get_by_text("Flags not yet human-reviewed").first.wait_for(timeout=180_000)
    page.wait_for_timeout(2000)
    # the notice follows the saved audit (partial while it ran; "Audit complete" since 4aa7aab)
    status = "complete" if "Audit complete" in (ROOT_RESULTS / "cuddalore_port_2026_draft.json").read_text(
        encoding="utf-8") else "partial"
    ok(f"Cuddalore: 'Audit {status}' notice", page.get_by_text(f"Audit {status}").count() > 0)
    ok("Cuddalore: 'Flags not yet human-reviewed' notice",
       page.get_by_text("Flags not yet human-reviewed").count() > 0)
    radio = page.locator('[data-testid="stRadio"]').filter(has_text="Letter language")
    try:   # the letter section is far below the notices: wait for this report's full render
        radio.get_by_text("English + Tamil", exact=True).wait_for(timeout=180_000)
    except Exception:
        pass
    ok("Cuddalore: Tamil letter option", radio.get_by_text("Tamil", exact=True).count() > 0
       and radio.get_by_text("English + Tamil", exact=True).count() > 0)
    excluded_matches(page, "Cuddalore", "cuddalore_port_2026_draft")
    page.screenshot(path=str(OUT / "cuddalore.png"))
    # Cuddalore paper trail: documents found, Tamil Nadu board as the hearing contact
    page.get_by_role("tab", name="Public record").click()
    page.wait_for_timeout(2500)
    docs = page.locator(".tf-doc").filter(visible=True)
    ok("Cuddalore: documents found", page.get_by_text("Documents found").count() > 0 and docs.count() > 0,
       f"{docs.count()} documents")
    ok("Cuddalore: TNPCB hearing contact", page.get_by_text("Tamil Nadu Pollution Control Board").count() > 0)
    ok("Cuddalore: no ADB wording", page.locator(".tf-adb").filter(visible=True).count() == 0)
    page.get_by_role("tab", name="Review queue").click()
    page.wait_for_timeout(2000)
    ok("Cuddalore: its own review queue", page.get_by_text("Review queue: Cuddalore").count() > 0)
    no_exception(page, "Cuddalore")

    # Karnataka (ADB): full audit with its own site, not-applicable checks, Kannada letter
    ka = library.find(items, "karnataka_rural_roads_2026_adb")
    if ka:
        page.locator('[data-testid="stSelectbox"]').first.click()
        page.get_by_role("option", name="Karnataka").click()
        page.get_by_text("not applicable").first.wait_for(timeout=180_000)
        page.wait_for_timeout(2000)
        ok("Karnataka: not-applicable reasons", page.get_by_text("No single project site").count() > 0)
        radio = page.locator('[data-testid="stRadio"]').filter(has_text="Letter language")
        try:
            radio.get_by_text("English + Kannada", exact=True).wait_for(timeout=180_000)
        except Exception:
            pass
        ok("Karnataka: Kannada letter option", radio.get_by_text("Kannada", exact=True).count() > 0)
        excluded_matches(page, "Karnataka", "karnataka_rural_roads_2026_adb")
        page.get_by_role("tab", name="Review queue").click()
        page.wait_for_timeout(2000)
        ok("Karnataka: its own review queue", page.get_by_text("Review queue: Karnataka").count() > 0)
        page.get_by_role("tab", name="Public record").click()
        page.wait_for_timeout(2500)
        ok("Karnataka: paper trail", page.get_by_text("Timeline (official sources)").count() > 0
           or page.get_by_text("Documents found").count() > 0)
        page.screenshot(path=str(OUT / "karnataka.png"))
        no_exception(page, "Karnataka")
    page.get_by_role("button", name="Back to library").click()
    page.wait_for_selector(".tf-lib-total", timeout=60_000)
    ok("back link: report -> library", page.locator(".tf-lib-total").count() == 1
       and page.locator('[data-testid="stTab"]').count() == 0)
    # ---------- a quick check opens in the lighter view ----------
    quick = [e for e in items if e["audit_type"] == library.QUICK]
    if quick:
        page.locator('[data-testid="stMultiSelect"]').filter(has_text="Audit type").click()
        page.get_by_role("option", name=library.QUICK).click()
        page.keyboard.press("Escape")
        page.wait_for_timeout(2500)
        ok("library: audit type filter", opens() == len(quick), f"{opens()} shown")
        page.locator('[data-testid="stButton"] button', has_text="Open").first.click()
        page.get_by_text(library.QUICK_NOTICE).wait_for(timeout=60_000)
        ok("quick check: lighter view with its notice", page.get_by_text("Checks that ran").count() > 0
           and page.locator('[data-testid="stTab"]').count() == 0)
        page.screenshot(path=str(OUT / "quick_check.png"))
        no_exception(page, "quick check")
        page.get_by_role("button", name="Back to library").click()
        page.wait_for_selector(".tf-lib-total", timeout=60_000)
        ok("back link: quick check -> library", page.locator(".tf-lib-total").count() == 1)
    ok("no page errors in the browser", not errors, "; ".join(errors[:3]))
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
sys.exit(1 if failed else 0)
