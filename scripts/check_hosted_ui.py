"""Browser check of the app in hosted replay mode (no keys): hero, findings with badges and page
images, species map, official record, letter and RTI downloads, letter-language gating, public record,
knowable-at-the-time line, species photos, cost card, every tab, no exceptions.

Start the app first:  set TIGERFISH_HOSTED=1 && streamlit run app.py --server.headless true --server.port 8631
Then:  python scripts/check_hosted_ui.py http://localhost:8631 shots/   (needs requirements-dev.txt)
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
results, errors = [], []


def ok(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def no_exception(page, where):
    n = page.locator('[data-testid="stException"]').count()
    ok(f"no exception: {where}", n == 0, f"{n} exception boxes")


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL, timeout=120_000)
    page.wait_for_selector(".tf-hero", timeout=180_000)
    page.get_by_text("Does it match the official record?").wait_for(timeout=180_000)  # full render
    page.wait_for_timeout(3000)
    ok("hero card", page.locator(".tf-hero-headline").count() > 0)
    ok("replay-only note", page.get_by_text("runs in replay mode").count() > 0)
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

    for tab, marker, shot in (("Review queue", "Every new RED/ORANGE flag", "review"),
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
    ok("no page errors in the browser", not errors, "; ".join(errors[:3]))
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
sys.exit(1 if failed else 0)
