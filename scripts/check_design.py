"""Design check (docs/DESIGN.md): deterministic browser checks of the app in hosted mode, no LLM.

For every page (Home, Library, a full report with each section tab, a table report, a quick
check, Upload, How it works, Limitations), at 1440px in light and dark, from computed styles
and the DOM:
  fonts outside the type system (plus system fallbacks); gradients; box-shadows blurred more
  than 2px; emoji in headings, labels, buttons and tabs; em dashes in UI text; coloured left
  or top accent bars; all-caps headings; a pure #FFFFFF page; text sitting directly on the
  background pattern; "Lorem ipsum" / "John Doe" / 555 placeholders; the default favicon; a
  page title of "Streamlit"; any "Sees clearly" left anywhere (also in the repo's text files);
  the meta description.
At 1920, 1440, 1280, 820 and 390px: no horizontal scroll, no empty half-screen, nothing
cramped (text squeezed into a sliver, or clipped).
Then docs/FEATURES.md: every listed feature's entry point is followed from Home (at most two
clicks) and must be visible.

Start the app first (no keys), as for scripts/check_hosted_ui.py:
  set TIGERFISH_HOSTED=1 && set NEBIUS_API_KEY= && set TAVILY_API_KEY= &&
  set TIGERFISH_BATCH_DIR=tests/fixtures/library/batch &&
  streamlit run app.py --server.headless true --server.port 8631
Then:  python scripts/check_design.py http://localhost:8631 [screenshots folder]
Exit code 1 if anything fails.
"""

import hashlib
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8631"
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else None
TITLE = "TigerFish: built for murky water"
PURPOSE = "A second reader for environmental impact reports, and everyone who questions them."
FONTS = {"schibsted grotesk", "newsreader", "ibm plex mono", "noto sans devanagari",
         "noto sans tamil", "noto sans kannada"}
# System fallbacks, the icon font Streamlit uses for its own controls (Material icons), and
# "Source Sans", which Streamlit appends to the end of every font stack as its last resort for
# a glyph the type system lacks. No element may use it as its font (checked per element).
FALLBACKS = {"sans-serif", "serif", "monospace", "georgia", "consolas", "arial",
             "system-ui", "material symbols rounded"}
LAST_RESORT = {"source sans"}
WIDTHS = (1920, 1440, 1280, 820, 390)
SHOT_WIDTHS = (1920, 820, 390)       # screenshots of every page at these widths
REPORT = "great_nicobar_2021_draft"
PAGES = {   # name: (path, tab to open or None)
    "home": ("/", None),
    "library": ("/library", None),
    "upload": ("/upload", None),
    "how_it_works": ("/how-it-works", None),
    "limitations": ("/limitations", None),
    "report_overview": (f"/library?report={REPORT}", None),
    "table_report": ("/library?report=indira_point_table_3_16", None),
    "quick_check": ("/library?report=sample_quick_mine_odisha_2025", None),
}
TABS = ["Contradictions", "Species & nature", "Copied text", "Promises & timeline",
        "Public record", "Ask & investigate", "Take action", "Quality", "Cost & models"]
results = []


def ok(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""),
          flush=True)


def idle(page, timeout=180_000):
    page.wait_for_timeout(800)
    page.wait_for_function("""() => !document.querySelector('[data-testid="stStatusWidget"]')
        && document.querySelectorAll('[data-stale="true"]').length === 0
        && document.querySelector('[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]')""",
                           timeout=timeout)
    page.wait_for_timeout(1200)


def goto(page, path):
    page.goto(URL + path, timeout=120_000)
    page.wait_for_selector('[data-testid="stMainBlockContainer"]', timeout=180_000)
    idle(page)


def full_shot(page, path):
    """Screenshot the whole page. Streamlit scrolls an inner container, so the viewport is
    stretched to the content's height first (capped), then restored."""
    vp = page.viewport_size
    h = page.evaluate("""() => Math.max(...[...document.querySelectorAll('.stApp, .stApp *')]
        .filter(e => ['auto', 'scroll'].includes(getComputedStyle(e).overflowY))
        .map(e => e.scrollHeight), document.documentElement.scrollHeight)""")
    page.set_viewport_size({"width": vp["width"], "height": max(vp["height"], min(int(h) + 40, 14000))})
    page.wait_for_timeout(1500)
    page.screenshot(path=str(path))
    page.set_viewport_size(vp)
    page.wait_for_timeout(500)


def open_tab(page, name):
    page.get_by_role("tab", name=re.compile("^" + re.escape(name))).first.click()
    page.wait_for_timeout(1500)
    idle(page)


# One pass over the visible DOM: returns every problem as [kind, detail].
STYLE_JS = r"""
({fonts, fallbacks}) => {
  const out = [];
  const seen = new Set();
  const add = (kind, el, detail) => {
    const key = kind + '|' + detail;
    if (seen.has(key)) return; seen.add(key);
    const tag = el ? (el.tagName.toLowerCase() + (el.className && typeof el.className === 'string'
      ? '.' + el.className.split(' ').filter(c => c.startsWith('tf-') || c.startsWith('st-key')).join('.') : '')) : '';
    out.push([kind, (tag + ' ' + detail).slice(0, 160)]);
  };
  const visible = el => { const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
      && parseFloat(s.opacity) > 0.05; };
  const app = document.querySelector('.stApp');
  const scope = [...document.querySelectorAll('.stApp *')].filter(visible);
  const ownText = el => [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent)
    .join('').trim();
  const colorful = c => { const m = c.match(/[\d.]+/g); if (!m) return false;
    const [r, g, b, a] = m.map(Number); if (a === 0) return false;
    return Math.max(r, g, b) - Math.min(r, g, b) > 40; };
  const opaque = s => { const m = s.backgroundColor.match(/[\d.]+/g);
    return (m && (m.length < 4 || Number(m[3]) > 0.9)) || (s.backgroundImage !== 'none'); };
  const emoji = /\p{Extended_Pictographic}/u;
  for (const el of scope) {
    const s = getComputedStyle(el);
    const text = ownText(el);
    // fonts: the first family of the stack must be in the type system
    if (text && !el.closest('svg')) {
      const first = s.fontFamily.split(',')[0].replace(/["']/g, '').trim().toLowerCase();
      if (!fonts.includes(first) && !fallbacks.includes(first))
        add('font outside the type system', el, first + ': ' + text.slice(0, 40));
    }
    if (s.backgroundImage.includes('gradient')) add('gradient', el, s.backgroundImage.slice(0, 60));
    if (s.boxShadow && s.boxShadow !== 'none') {
      for (const part of s.boxShadow.split(/,(?![^(]*\))/)) {
        const px = (part.replace(/rgba?\([^)]*\)/, '').match(/-?[\d.]+px/g) || []).map(parseFloat);
        if (!part.includes('inset') && px.length >= 3 && px[2] > 2) add('box-shadow blur > 2px', el, part.trim());
      }
    }
    for (const side of ['Left', 'Top']) {
      const w = parseFloat(s['border' + side + 'Width']);
      const other = parseFloat(s['border' + (side === 'Left' ? 'Right' : 'Bottom') + 'Width']);
      if (w >= 2 && w > other && s['border' + side + 'Style'] !== 'none'
          && colorful(s['border' + side + 'Color']) && el.getBoundingClientRect().height > 16)
        add('coloured ' + side.toLowerCase() + ' accent bar', el, s['border' + side + 'Color']);
    }
    const heading = el.matches('h1,h2,h3,h4,h5,h6,.tf-h1,.tf-h2,.tf-h3,.tf-title,.tf-card-title');
    if (heading) {
      const t = el.innerText.trim();
      if (s.textTransform === 'uppercase' || (t.length > 6 && /[A-Z]/.test(t) && t === t.toUpperCase()
          && /[A-Z]{3,} [A-Z]{3,}/.test(t)))
        add('all-caps heading', el, t.slice(0, 50));
    }
    if (el.matches('h1,h2,h3,h4,h5,h6,label,button,[role=tab],[data-testid=stWidgetLabel],.tf-h1,.tf-h2,.tf-h3,a[data-testid=stTopNavLink]')
        && emoji.test(el.innerText)) add('emoji in a heading, label or button', el, el.innerText.slice(0, 40));
    // text never sits on the pattern: the first opaque ancestor must not be the app background
    if (text && text.length > 1 && !el.closest('header') && el.closest('[data-testid=stMain]')) {
      let a = el;
      while (a && a !== app) { if (opaque(getComputedStyle(a))) break; a = a.parentElement; }
      if (!a || a === app) add('text directly on the pattern', el, text.slice(0, 50));
    }
  }
  // em dashes in UI text: everything visible except quotes and evidence taken from the reports
  const walker = document.createTreeWalker(document.querySelector('.stApp'), NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const p = n.parentElement;
    if (!p || !visible(p) || !n.textContent.includes('—')) continue;
    if (p.closest('.tf-slip-quote,.tf-quote,blockquote,.tf-ev,.tf-doc,.tf-table td,.tf-memo-list,.tf-step-body,code,pre,[data-testid=stDataFrame]'))
      continue;
    add('em dash in UI text', p, n.textContent.trim().slice(0, 60));
  }
  const body = document.body.innerText;
  for (const bad of ['Lorem ipsum', 'John Doe', 'Sees clearly'])
    if (body.toLowerCase().includes(bad.toLowerCase())) add('placeholder or old text', null, bad);
  if (/\(?\b555\)?[-. ]\d{3}[-. ]\d{4}\b|\b555-\d{4}\b/.test(body)) add('placeholder or old text', null, '555 number');
  if (document.documentElement.innerHTML.includes('Sees clearly')) add('placeholder or old text', null, 'Sees clearly (in the HTML)');
  const bg = getComputedStyle(app).backgroundColor;
  if (bg === 'rgb(255, 255, 255)') add('pure #FFFFFF page background', app, bg);
  return out;
}
"""

LAYOUT_JS = r"""
() => {
  const out = [];
  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + 1) out.push(['horizontal scroll', `${de.scrollWidth} > ${de.clientWidth}`]);
  const main = document.querySelector('[data-testid=stMainBlockContainer]');
  const vw = de.clientWidth;
  // empty half-screen: in the first screenful, content must reach both halves of the viewport
  const els = [...main.querySelectorAll('[data-testid=stElementContainer], [class*="st-key-tf-"]')]
    .map(e => e.getBoundingClientRect()).filter(r => r.width > 0 && r.height > 0 && r.top < innerHeight);
  if (els.length) {
    const left = Math.min(...els.map(r => r.left)), right = Math.max(...els.map(r => r.right));
    if (vw >= 1000 && (right - left) < vw * 0.5) out.push(['empty half-screen', `content spans ${Math.round(right - left)} of ${vw}px`]);
  }
  // cramped: long text squeezed into a sliver, or text clipped by its box
  for (const el of main.querySelectorAll('p, span, label, button, div, a, td, th')) {
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
    if (!own) continue;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width === 0 || s.visibility === 'hidden' || el.closest('[data-baseweb=popover], svg, [role=tablist]')) continue;
    if (r.width < 64 && own.length > 14 && own.includes(' '))
      out.push(['cramped', `${Math.round(r.width)}px wide: ${own.slice(0, 40)}`]);
    if (s.overflow === 'hidden' && s.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 1
        && !el.closest('[data-baseweb=select], [data-testid=stSelectbox], [data-testid=stMultiSelect]'))
      out.push(['cramped', `clipped with an ellipsis: ${own.slice(0, 40)}`]);
  }
  return out;
}
"""


def style_checks(page, where):
    problems = page.evaluate(STYLE_JS, {"fonts": sorted(FONTS), "fallbacks": sorted(FALLBACKS)})
    kinds = {}
    for kind, detail in problems:
        kinds.setdefault(kind, []).append(detail)
    for kind in ("font outside the type system", "gradient", "box-shadow blur > 2px",
                 "emoji in a heading, label or button", "em dash in UI text",
                 "coloured left accent bar", "coloured top accent bar", "all-caps heading",
                 "pure #FFFFFF page background", "text directly on the pattern",
                 "placeholder or old text"):
        got = kinds.get(kind, [])
        ok(f"{where}: no {kind}", not got, "; ".join(got[:4]) + (f" (+{len(got) - 4})" if len(got) > 4 else ""))
    loaded = page.evaluate("""() => [...document.fonts].filter(f => f.status === 'loaded')
        .map(f => f.family.replace(/["']/g, '').toLowerCase())""")
    extra = sorted({f for f in loaded if f not in FONTS | FALLBACKS | LAST_RESORT})
    ok(f"{where}: only the type system's fonts are loaded", not extra, ", ".join(extra))


def layout_checks(page, where):
    problems = page.evaluate(LAYOUT_JS)
    for kind in ("horizontal scroll", "empty half-screen", "cramped"):
        got = [d for k, d in problems if k == kind]
        ok(f"{where}: no {kind}", not got, "; ".join(got[:3]))


def head_checks(page):
    page.wait_for_function(f"() => document.title === {TITLE!r}", timeout=30_000)
    ok("page title", page.title() == TITLE, page.title())
    ok("page title is not 'Streamlit'", page.title() != "Streamlit")
    desc = page.evaluate("() => (document.querySelector('meta[name=description]') || {}).content")
    ok("meta description is the purpose line", desc == PURPOSE, str(desc))
    hrefs = page.evaluate("() => [...document.querySelectorAll('link[rel*=icon]')].map(l => l.href)")
    want = hashlib.sha256((ROOT / "assets" / "favicon-64.png").read_bytes()).hexdigest()
    got = []
    for h in hrefs:
        try:
            got.append(hashlib.sha256(urllib.request.urlopen(h, timeout=20).read()).hexdigest())
        except Exception:
            got.append("unreadable")
    ok("favicon is TigerFish's (not the default)", want in got, " ".join(hrefs)[:120])
    purpose = page.evaluate("""() => { const d = document.querySelector(
        'header div:has(> img[data-testid=stHeaderLogo]), header div:has(> [data-testid=stLogoLink])');
        return d ? getComputedStyle(d, '::after').content : '' }""")
    ok("purpose line beside the logo in the top bar", PURPOSE in purpose, purpose[:60])


def repo_text_check():
    """No "Sees clearly" left in the repo's text files (app, docs, page titles)."""
    hits = []
    for p in ROOT.rglob("*"):
        if (p.is_file() and p.suffix in (".py", ".md", ".svg", ".toml", ".txt", ".html", ".json")
                and not any(part in (".git", "cache", "logs", "__pycache__", ".pytest_cache", "results")
                            for part in p.relative_to(ROOT).parts)
                and p.name != "check_design.py"):
            try:
                if "sees clearly" in p.read_text(encoding="utf-8", errors="ignore").lower():
                    hits.append(str(p.relative_to(ROOT)))
            except OSError:
                pass
    ok("repo: no 'Sees clearly' left", not hits, ", ".join(hits))


def features(page):
    """docs/FEATURES.md: follow each entry point from Home; it must be visible in <= 2 clicks."""
    rows = []
    for line in (ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and "=" in cells[2] and not cells[0].startswith("-"):
            rows.append((cells[0], [tuple(s.split("=", 1)) for s in cells[2].split(" · ")]))
    ok("features: inventory read", len(rows) >= 30, f"{len(rows)} features")
    for name, steps in rows:
        goto(page, "/")
        clicks, seen, why = 0, False, ""
        try:
            for key, value in steps:
                if key == "menu":
                    page.locator('[data-testid="stTopNavLink"]').filter(
                        has=page.get_by_text(value, exact=True)).first.click()
                    clicks += 1
                    idle(page)
                elif key == "report":
                    page.locator(f'.st-key-tf-slip-rep-{value} button', has_text="Open report").first.click()
                    clicks += 1
                    page.wait_for_selector('[role="tab"]', timeout=180_000)
                    idle(page)
                elif key == "tab":
                    open_tab(page, value)
                    clicks += 1
                elif key == "text":
                    loc = page.get_by_text(value, exact=False).filter(visible=True)
                    loc.first.wait_for(timeout=30_000)
                    seen = loc.count() > 0
                elif key == "css":
                    loc = page.locator(value).filter(visible=True)
                    loc.first.wait_for(timeout=30_000)
                    seen = loc.count() > 0
        except Exception as e:
            why = type(e).__name__
        ok(f"feature visible within 2 clicks: {name}", seen and clicks <= 2,
           f"{clicks} clicks, {'seen' if seen else 'not seen'} {why}")


def main():
    repo_text_check()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        errors = []
        for scheme in ("light", "dark"):
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, color_scheme=scheme)
            page.on("pageerror", lambda e: errors.append(str(e)))
            goto(page, "/")
            if scheme == "light":
                head_checks(page)
            for name, (path, _) in PAGES.items():
                goto(page, path)
                style_checks(page, f"{scheme} {name}")
                if name == "report_overview":
                    for t in TABS:
                        open_tab(page, t)
                        style_checks(page, f"{scheme} report {t}")
            page.close()
        for w in WIDTHS:
            page = browser.new_page(viewport={"width": w, "height": 1000 if w > 500 else 844})
            for name, (path, _) in PAGES.items():
                goto(page, path)
                layout_checks(page, f"{w}px {name}")
                if SHOTS and w in SHOT_WIDTHS:
                    SHOTS.mkdir(parents=True, exist_ok=True)
                    full_shot(page, SHOTS / f"{name}_{w}.png")
            goto(page, PAGES["report_overview"][0])
            for t in ("Contradictions", "Species & nature", "Public record"):
                open_tab(page, t)
                layout_checks(page, f"{w}px report {t}")
                if SHOTS and w in SHOT_WIDTHS:
                    full_shot(page, SHOTS / f"report_{t.split()[0].lower()}_{w}.png")
            page.close()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        features(page)
        page.close()
        ok("no page errors in the browser", not errors, "; ".join(errors[:3]))
        browser.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} of {len(results)} design checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
