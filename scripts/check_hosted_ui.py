"""Browser check of the app in hosted replay mode (no keys): hero, findings with badges and page
images, species map, official record, letter and RTI downloads, every tab, no exceptions.

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

    for tab, marker, shot in (("Review queue", "Every new RED/ORANGE flag", "review"),
                              ("Reviewer's memo & Ask", "Ask the report", "memo"),
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
    no_exception(page, "all tabs")
    ok("no page errors in the browser", not errors, "; ".join(errors[:3]))
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
sys.exit(1 if failed else 0)
