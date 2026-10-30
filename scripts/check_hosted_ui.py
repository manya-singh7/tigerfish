"""Browser check of the app in hosted mode (no keys): the top menu (Home · Library · Upload ·
How it works · Limitations); Home (tagline, purpose line as the headline, live totals sentence,
the three checked findings, the full audits as rows, built-with line); the brand (logo,
favicon, light and dark theme); How it works (diagram,
models, three levels); Limitations; the report library (live totals, filters, search, a quick
check with only its own sections, back link); the no-key upload (detected facts, free checks,
which checks need a key, the three levels); then the report opened from the library, in five
tabs (the finding sections under Findings) with their counts: Overview (the lead slip and the
top 3 human-verified slips, one totals sentence), Contradictions (badges, page images),
Species & nature (map, photos), Promises & timeline (granted and proposed ToR), Take action
(letter and RTI downloads, letter-language gating), Quality (review queue, evaluation), Ask &
investigate (memo), Cost & models (cost card, efficiency line, scanned pages), Public record
(official record, merged paper trail: one timeline, documents found with
their Tavily tag, who to write to; evidence from the web); Indira Point (sections that do not
apply are hidden with the reason; knowable-at-the-time line; no document guessed); Cuddalore
(audit status from the saved audit, Tamil letter, documents, TNPCB contact); the back link;
no exceptions. Screenshots of every page and section go to the output folder.

Start the app first, with no keys and the sample quick checks from tests/fixtures:
  set TIGERFISH_HOSTED=1 && set NEBIUS_API_KEY= && set TAVILY_API_KEY= &&
  set TIGERFISH_BATCH_DIR=tests/fixtures/library/batch &&
  streamlit run app.py --server.headless true --server.port 8631
Then:  python scripts/check_hosted_ui.py http://localhost:8631 docs/screenshots/ui/
(needs requirements-dev.txt)
"""
import os
import re
import sys
from pathlib import Path

import pymupdf
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TIGERFISH_BATCH_DIR", "tests/fixtures/library/batch")   # as the app was started
from tigerfish import library  # noqa: E402

URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8631"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs/screenshots/ui/")
ROOT_RESULTS = ROOT / "results"
OUT.mkdir(parents=True, exist_ok=True)
TMP = OUT / "_tmp"           # the test PDF and downloads, deleted at the end
TMP.mkdir(exist_ok=True)
SECTIONS = ["Overview", "Findings", "Ask & investigate", "Take action", "Method & quality"]
FINDING_SECTIONS = ["Contradictions", "Species & nature", "Copied text", "Promises & timeline",
                    "Public record"]
MENU = ["Home", "Library", "Upload", "How it works", "Limitations"]
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


def no_exception(page, where):
    n = page.locator('[data-testid="stException"]').count()
    ok(f"no exception: {where}", n == 0, f"{n} exception boxes")


def menu_link(page, name):
    return page.locator('[data-testid="stTopNavLink"]').filter(has=page.get_by_text(name, exact=True))


def nav(page, name):
    """Click a page in the top menu."""
    menu_link(page, name).first.click()
    idle(page)


def tab(page, name):
    """A report tab; its label may carry a count, e.g. "Findings (146)"."""
    return page.get_by_role("tab", name=re.compile("^" + re.escape(name)))


def section(page, name):
    """A section under the Findings tab (a radio button; its label carries a count)."""
    return page.locator('[data-testid="stButtonGroup"] [role="radio"]').filter(
        has_text=re.compile("^" + re.escape(name)))


def labels(page):
    return [re.sub(r" \(.*", "", x).strip() for x in page.get_by_role("tab").all_inner_texts()]


def open_tab(page, name, shot=None):
    """Open a report tab, or a section under Findings, or Quality / Cost & models (both in the
    Method & quality tab)."""
    if name in FINDING_SECTIONS:
        tab(page, "Findings").click()
        page.wait_for_timeout(1500)
        section(page, name).first.click()
    elif name in ("Quality", "Cost & models"):
        tab(page, "Method & quality").click()
    else:
        tab(page, name).click()
    page.wait_for_timeout(2000)
    if shot:
        page.screenshot(path=str(OUT / f"{shot}.png"), full_page=True)


def switch_report(page, name):
    """Pick another report in the switcher above the sections (retried once: the dropdown can
    miss a click while the page is still settling far down a long section)."""
    for _ in range(2):
        idle(page)
        page.keyboard.press("Escape")
        page.evaluate("() => window.scrollTo(0, 0)")
        page.locator('[data-testid="stSelectbox"]').first.click()
        try:
            page.get_by_role("option", name=name).click(timeout=10_000)
            return
        except Exception:
            continue
    raise RuntimeError(f"could not switch to {name}")


def visible_images(page):
    return page.evaluate("""() => [...document.querySelectorAll('img')].filter(
        i => i.complete && i.naturalWidth > 100 && i.offsetParent !== null).length""")


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 1000}, accept_downloads=True,
                            color_scheme="light")
    # Each browser error with the check it followed, so a failure says where it happened.
    # Ignored: Plotly's "_axisMatchGroups" error, thrown now and then when a section switch
    # removes the species map while Plotly is still laying it out; nothing on the page changes.
    page.on("pageerror", lambda e: errors.append(f"{e} (after: {results[-1][0] if results else 'start'})")
            if "topojson" not in str(e) and "_axisMatchGroups" not in str(e) else None)
    page.goto(URL, timeout=120_000)

    # ---------- Home ----------
    page.wait_for_selector(".tf-home-tag", timeout=180_000)
    idle(page)
    items = library.entries()
    t = library.totals(items)
    ok("home: tagline", page.locator(".tf-home-tag").inner_text().strip() == "Built for murky water.")
    ok("home: purpose line as the headline", page.locator(".tf-home-intro h1").inner_text().strip() ==
       "A second reader for environmental impact reports, and everyone who questions them.")
    totals = page.locator(".tf-home-totals").inner_text()
    ok("home: live totals from results/, one sentence", library.totals_line(t) in totals, totals)
    ok("home: three findings a person checked", page.locator("a.tf-tile").count() == 3
       and page.get_by_text("names the sambar and the barking deer", exact=False).count() == 1)
    ok("home: no row of feature cards or metric banner", page.locator(".tf-card-head").count() == 0
       and page.locator('[data-testid="stMetricValue"]').count() == 0)
    ok("home: the full audits as rows", page.locator("a.tf-row").count()
       == sum(e["audit_type"] != library.QUICK for e in items))
    ok("home: built with", page.get_by_text(
        "Built with NVIDIA Nemotron on Nebius Token Factory + Tavily").count() == 1)
    shown_menu = [n for n in MENU if menu_link(page, n).count()]
    ok("top menu: five pages", shown_menu == MENU, ", ".join(shown_menu))
    ok("brand: logo in the top bar", page.locator("header img").count() > 0)
    icon = page.evaluate("() => [...document.querySelectorAll('link[rel*=icon]')].map(l => l.href).join(' ')")
    ok("brand: favicon set", bool(icon) and "favicon.png" not in icon.split("/")[-1:], icon[:120])
    bg = page.evaluate("() => getComputedStyle(document.querySelector('.stApp')).backgroundColor")
    ok("light theme: paper background", bg == "rgb(246, 242, 233)", bg)
    page.screenshot(path=str(OUT / "home.png"), full_page=True)
    no_exception(page, "home")

    # ---------- How it works, Limitations ----------
    nav(page, "How it works")
    page.get_by_text("Which model does what, and why").wait_for(timeout=60_000)
    idle(page)
    ok("how it works: diagram", page.evaluate("""() => [...document.querySelectorAll('img')].some(
        i => i.complete && i.naturalWidth > 300)"""))
    ok("how it works: models and three levels", page.get_by_text("Nemotron Ultra").count() > 0
       and page.get_by_text("Three levels").count() == 1 and page.get_by_text("Deep audit").count() > 0)
    page.screenshot(path=str(OUT / "how_it_works.png"), full_page=True)
    no_exception(page, "how it works")
    nav(page, "Limitations")
    page.get_by_text("Every flag is a lead, not a verdict.").first.wait_for(timeout=60_000)
    ok("limitations: the plain list, linking the technical notes",
       page.get_by_role("link", name="docs/LIMITATIONS.md").count() == 1
       and page.get_by_text("Failure cases from our own runs").count() == 0)
    page.screenshot(path=str(OUT / "limitations.png"), full_page=True)
    no_exception(page, "limitations")

    # ---------- the library ----------
    nav(page, "Library")
    page.wait_for_selector(".tf-lib-total", timeout=180_000)
    page.wait_for_timeout(1500)
    expected = library.totals_line(t)
    shown = page.locator(".tf-lib-total").inner_text().strip()
    ok("library: totals computed from results/", shown.startswith(expected), shown)

    def opens():
        idle(page)
        return page.locator(".tf-lib-title:visible").count()

    ok("library: one row per report", opens() == len(items), f"{opens()} rows, {len(items)} reports")
    ok("library: upload button and note",
       page.get_by_role("button", name="Upload your EIA").count() == 1
       and page.get_by_text("Saved audits are full runs").count() > 0)
    page.get_by_text("Has RED flags").first.click()
    page.wait_for_timeout(2500)
    n_red = sum(e["grades"]["RED"] > 0 for e in items)
    ok("library: 'Has RED flags' filter", opens() == n_red, f"{opens()} shown, {n_red} expected")
    page.get_by_text("Has RED flags").first.click()
    page.wait_for_timeout(2000)
    search = page.get_by_label("Search by project name")
    search.fill("Cuddalore")
    search.press("Enter")
    page.wait_for_timeout(2500)
    ok("library: search by project name", opens() == 1, f"{opens()} shown")
    search.fill("")
    search.press("Enter")
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "library.png"), full_page=True)
    no_exception(page, "library")

    # ---------- upload a new EIA with no key ----------
    pdf = TMP / "visitor_upload.pdf"
    doc = pymupdf.open()
    for text in ("India: Sample Harbour Expansion Project\nDraft EIA Report\nMay 2026\n"
                 "Prepared by Sample Enviro Consultants Pvt. Ltd. for the Port Trust.",
                 "The harbour is in Tamil Nadu. Tamil Nadu has a long coast.",
                 "The site is located at latitude 11°42'22\" N, longitude 79°46'30\" E.",
                 "The total reclaimed area is 45 ha at the harbour site.",
                 "The total reclaimed area is 62 ha at the harbour site."):
        doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=11)
    doc.save(pdf)
    page.get_by_role("button", name="Upload your EIA").click()
    page.get_by_text("Free, whole report.").first.wait_for(timeout=60_000)
    idle(page)
    ok("upload: opens the Upload page", "/upload" in page.url, page.url)
    ok("upload: three levels shown", page.get_by_text("Chosen pages, live.").count() > 0
       and page.get_by_text("Your own key, or run locally.").count() > 0)
    ok("upload: no-key note", page.get_by_text("No key: the free checks run").count() > 0)
    page.screenshot(path=str(OUT / "upload.png"), full_page=True)
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
    ok("upload: the result opens in sections", "Overview" in labels(page), " | ".join(labels(page)))
    page.screenshot(path=str(OUT / "upload_no_key.png"), full_page=True)
    no_exception(page, "upload without a key")
    nav(page, "Library")
    page.wait_for_selector(".tf-lib-total", timeout=60_000)
    ok("menu: upload -> library", page.locator(".tf-lib-total").count() == 1 and "/library" in page.url)

    # ---------- open the Great Nicobar report from the library ----------
    idle(page)
    page.locator('[data-testid="stButton"] button', has_text="Open").first.click()
    page.wait_for_selector(".tf-slip", timeout=180_000)
    tab(page, "Method & quality").wait_for(timeout=180_000)
    idle(page)
    ok("report opens in the Library", "/library" in page.url and "report=" in page.url, page.url)
    tab_text = page.get_by_role("tab").all_inner_texts()
    ok("sections side by side", labels(page) == SECTIONS, " | ".join(tab_text))
    ok("tab labels carry counts", any(re.fullmatch(r"Findings \([\d,]+\)", x.strip())
                                      for x in tab_text))
    ok("Overview: the lead slip, then the top 3 human-verified slips",
       page.locator(".tf-slip-lead:visible").count() == 1
       and page.locator(".tf-slip:visible").count() == 4
       and page.locator(".tf-slip:visible .tf-person").count() == 4)
    ok("Overview: more flags", page.get_by_text("More flags").count() == 1)
    ok("back link on the report", page.get_by_role("button", name="Back to library").count() == 1)
    ok("no live toggle without a key", page.locator('[data-testid="stToggle"]').count() == 0
       or page.get_by_text("Live mode").count() == 0)
    page.screenshot(path=str(OUT / "report_overview.png"), full_page=True)
    no_exception(page, "Overview")

    open_tab(page, "Contradictions")
    ok("finding badges", page.locator(".tf-model").count() > 0, f"{page.locator('.tf-model').count()} badges")
    ok("human-verified badge", page.get_by_text("Human-verified").count() > 0)
    page.get_by_text("Show highlighted page").filter(visible=True).first.click()
    page.wait_for_timeout(2500)
    ok("page images load", visible_images(page) > 0, f"{visible_images(page)} visible images")
    page.screenshot(path=str(OUT / "report_contradictions.png"))
    no_exception(page, "Contradictions")
    # mark the first visible finding Confirm (for the letter and the pack)
    page.locator("button:visible", has_text="Confirm").first.click()
    idle(page)

    open_tab(page, "Species & nature", "report_species")
    ok("species map", page.get_by_text("Where the flagged species are actually recorded").count() > 0
       and page.locator(".js-plotly-plot").count() > 0)
    ok("species photo with attribution", page.locator(".tf-photo img").count() > 0
       and page.get_by_text("via Wikimedia Commons").count() > 0)
    open_tab(page, "Copied text", "report_copied")
    open_tab(page, "Promises & timeline", "report_promises")
    ok("ToR promises: granted and proposed labelled", page.get_by_text("Granted ToR (MoEFCC letter").count() > 0
       and page.get_by_text("Proposed ToR (").count() > 0)

    open_tab(page, "Take action")
    page.get_by_role("button", name="Draft objection letter (.docx)").and_(
        page.locator(":enabled")).wait_for(timeout=120_000)
    page.wait_for_timeout(2000)
    n_action = re.fullmatch(r"Take action \((\d+)\)", tab(page, "Take action").inner_text().strip())
    ok("Take action counts the team's and the confirmed findings", bool(n_action)
       and int(n_action.group(1)) >= 1, tab(page, "Take action").inner_text())
    page.screenshot(path=str(OUT / "report_take_action.png"), full_page=True)
    for label, suffix in (("Draft objection letter (.docx)", ".docx"),
                          ("RTI + public hearing pack (.zip)", ".zip")):
        btn = page.get_by_role("button", name=label)
        with page.expect_download(timeout=60_000) as d:
            btn.click()
        path = TMP / f"download{suffix}"
        d.value.save_as(str(path))
        ok(f"download {label}", path.stat().st_size > 1000, f"{path.stat().st_size} bytes")
    page.mouse.move(0, 0)
    page.keyboard.press("Escape")
    ok("reviews kept in session (wording)", page.get_by_text("in this browser session only").count() > 0)
    # letter language: Tamil only for Tamil Nadu reports; a translation without a key is gated
    radio = page.locator('[data-testid="stRadio"]').filter(has_text="Letter language")
    ok("no Tamil option for a non-Tamil Nadu report", radio.get_by_text("Tamil").count() == 0)
    radio.get_by_text("Hindi", exact=True).click(force=True)
    try:
        page.get_by_text("needs the translation model").wait_for(timeout=120_000)   # full rerun
    except Exception:
        pass
    ok("Hindi letter gated without a key", page.get_by_text("needs the translation model").count() > 0
       and page.get_by_role("button", name="Draft objection letter (.docx)").is_disabled())
    radio.get_by_text("English", exact=True).click(force=True)
    page.get_by_role("button", name="Draft objection letter (.docx)").and_(
        page.locator(":enabled")).wait_for(timeout=120_000)

    open_tab(page, "Quality", "report_quality")
    ok("Quality: review queue", page.get_by_text("Every new RED/ORANGE flag").count() > 0)
    ok("review queue: committed decisions read-only", page.get_by_text("shown read-only").count() > 0)
    ok("Quality: evaluation", page.get_by_role("heading", name="Evaluation").count() > 0)
    open_tab(page, "Ask & investigate", "report_ask")
    ok("memo and Ask", page.get_by_text("Reviewer's memo").count() > 0
       and page.get_by_text("Ask the report").count() > 0)
    open_tab(page, "Cost & models")
    ok("scanned pages", page.get_by_text("How TigerFish reads scanned pages").count() > 0)
    ok("inspector images", visible_images(page) > 0, f"{visible_images(page)} visible images")
    ok("cost card", page.get_by_text("Cost per full audit, by triage mode").count() > 0)
    eff = page.locator(".tf-efficiency")
    ok("efficiency line on the cost card", eff.filter(has_text="Context efficiency").count() > 0
       and eff.filter(has_text="Tavily returned").count() > 0)
    page.screenshot(path=str(OUT / "report_cost.png"), full_page=True)

    open_tab(page, "Public record")
    ok("official record", page.get_by_text("Does it match the official record?").count() > 0)
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
    page.screenshot(path=str(OUT / "report_public_record.png"), full_page=True)
    page.get_by_text("Evidence from the web (every saved report)").click()
    page.wait_for_timeout(1500)
    ok("evidence from the web", page.locator(".tf-efficiency").filter(has_text="Tavily returned").count() > 0
       and page.get_by_text("Context efficiency").count() > 0)
    no_exception(page, "all sections")

    # second report: sections that do not apply, knowable-at-the-time line, species photos
    switch_report(page, "Indira Point")
    page.wait_for_url(re.compile("report=indira_point"), timeout=120_000)
    page.get_by_text("Not shown for this report").first.wait_for(timeout=180_000)
    idle(page)
    tab(page, "Findings").click()
    page.wait_for_timeout(1500)
    ok("table report: sections that do not apply are hidden, with why",
       section(page, "Contradictions").count() == 0 and section(page, "Copied text").count() == 0
       and section(page, "Species & nature").count() == 1, " | ".join(labels(page)))
    tab(page, "Overview").click()
    page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT / "second_report_overview.png"), full_page=True)
    open_tab(page, "Species & nature")
    page.locator(".tf-knowable").first.wait_for(timeout=120_000)
    ok("knowable at the time line", page.locator(".tf-knowable").count() > 0)
    ok("species photos (second report)", page.locator(".tf-photo img").count() > 1,
       f"{page.locator('.tf-photo img').count()} photos")
    page.screenshot(path=str(OUT / "second_report_species.png"))
    open_tab(page, "Public record")
    ok("second report: no document guessed", page.get_by_text(
        "No official document naming this project was found").count() > 0
       and page.locator(".tf-doc").filter(visible=True).count() == 0)
    no_exception(page, "second report")

    # Cuddalore (Tamil Nadu): audit-status and not-reviewed notices, Tamil letter offered
    switch_report(page, "Cuddalore")
    page.wait_for_url(re.compile("report=cuddalore"), timeout=120_000)
    page.get_by_text("Flags not yet human-reviewed").first.wait_for(timeout=180_000)
    tab(page, "Take action").wait_for(timeout=180_000)
    idle(page)
    # the notice follows the saved audit (partial while it ran; "Audit complete" since 4aa7aab)
    status = "complete" if "Audit complete" in (ROOT_RESULTS / "cuddalore_port_2026_draft.json").read_text(
        encoding="utf-8") else "partial"
    ok(f"Cuddalore: 'Audit {status}' notice", page.get_by_text(f"Audit {status}").count() > 0)
    ok("Cuddalore: 'Flags not yet human-reviewed' notice",
       page.get_by_text("Flags not yet human-reviewed").count() > 0)
    page.screenshot(path=str(OUT / "cuddalore_overview.png"), full_page=True)
    open_tab(page, "Take action")
    radio = page.locator('[data-testid="stRadio"]').filter(has_text="Letter language")
    try:
        radio.get_by_text("English + Tamil", exact=True).wait_for(timeout=180_000)
    except Exception:
        pass
    ok("Cuddalore: Tamil letter option", radio.get_by_text("Tamil", exact=True).count() > 0
       and radio.get_by_text("English + Tamil", exact=True).count() > 0)
    open_tab(page, "Public record", "cuddalore_public_record")
    docs = page.locator(".tf-doc").filter(visible=True)
    ok("Cuddalore: documents found", page.get_by_text("Documents found").count() > 0 and docs.count() > 0,
       f"{docs.count()} documents")
    ok("Cuddalore: TNPCB hearing contact", page.get_by_text("Tamil Nadu Pollution Control Board").count() > 0)
    ok("Cuddalore: no ADB wording", page.locator(".tf-adb").filter(visible=True).count() == 0)
    no_exception(page, "Cuddalore")
    page.get_by_role("button", name="Back to library").click()
    page.wait_for_selector(".tf-lib-total", timeout=60_000)
    idle(page)
    ok("back link: report -> library", page.locator(".tf-lib-total").count() == 1
       and page.get_by_role("tab").count() == 0)

    # ---------- a quick check gets only its own sections ----------
    quick = [e for e in items if e["audit_type"] == library.QUICK]
    if quick:
        radio = page.locator('[data-testid="stRadio"]').filter(has_text="Audit type")
        if radio.count():
            radio.locator('label').filter(has_text="Quick Batch Audits").click()
        else:
            page.locator('[data-testid="stMultiSelect"]').filter(has_text="Audit type").click()
            page.get_by_role("option", name=library.QUICK).click()
            page.keyboard.press("Escape")
        page.wait_for_timeout(2500)
        ok("library: audit type filter", opens() == len(quick), f"{opens()} shown")
        page.locator('[data-testid="stButton"] button', has_text="Open").first.click()
        page.get_by_text(library.QUICK_NOTICE).wait_for(timeout=60_000)
        idle(page)
        q = labels(page)
        ok("quick check: only its own sections, with its notice",
           page.get_by_text("Checks that ran").count() > 0 and q[:1] == ["Overview"]
           and set(q) <= {"Overview", "Findings", "Batch screening"}, " | ".join(q))
        page.screenshot(path=str(OUT / "quick_check.png"), full_page=True)
        no_exception(page, "quick check")
        page.get_by_role("button", name="Back to library").click()
        page.wait_for_selector(".tf-lib-total", timeout=60_000)
        ok("back link: quick check -> library", page.locator(".tf-lib-total").count() == 1)

    # ---------- old links still work ----------
    page.goto(URL + "/?report=great_nicobar_2021_draft", timeout=120_000)
    page.wait_for_selector(".tf-slip", timeout=180_000)
    ok("old link /?report=<id> opens the report in the Library", "/library" in page.url, page.url)
    ok("no page errors in the browser", not errors, "; ".join(errors[:3]))

    # ---------- dark theme (the viewer's system setting picks [theme.dark]) ----------
    dark = browser.new_page(viewport={"width": 1400, "height": 1000}, color_scheme="dark")
    dark.goto(URL, timeout=120_000)
    dark.wait_for_selector(".tf-home-tag", timeout=180_000)
    idle(dark)
    bg = dark.evaluate("() => getComputedStyle(document.querySelector('.stApp')).backgroundColor")
    ok("dark theme: background from [theme.dark]", bg == "rgb(15, 23, 22)", bg)
    dark.screenshot(path=str(OUT / "home_dark.png"), full_page=True)
    dark.goto(URL + "/library?report=great_nicobar_2021_draft", timeout=120_000)
    dark.wait_for_selector(".tf-slip", timeout=180_000)
    idle(dark)
    dark.screenshot(path=str(OUT / "report_overview_dark.png"), full_page=True)
    browser.close()

for f in TMP.iterdir():
    f.unlink()
TMP.rmdir()
failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
sys.exit(1 if failed else 0)
