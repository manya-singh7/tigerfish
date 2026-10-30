"""The app's pages, in the top menu: Home · Library · Upload · How it works · Limitations.

app.py builds the menu with st.navigation(position="top") from PAGES. Home leads into the
library (it carries the library below its opening row); a report opens inside the Library
(?report=<id>). Old links keep working: /?report=<id> and /?view=upload are sent on to the
right page (redirect() in app.py). Layout rules: docs/DESIGN.md.
"""

import json
from pathlib import Path

import streamlit as st

from tigerfish import library, page_picks, review, species_photos
from tigerfish.ui import data, method, report_view, slip, upload
from tigerfish.ui import library as library_ui
from tigerfish.ui.style import PURPOSE, TAGLINE, badge, esc, mono

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
BUILT_WITH = "Built with NVIDIA Nemotron on Nebius Token Factory + Tavily"
# Home's species tile: these flags of the Indira Point table, once a reviewer confirmed them
# (review/reviews.jsonl). Common names are fixed; every number comes from the saved findings.
HERO_REPORT = "indira_point_table_3_16"
HERO_SPECIES = {"sp-02": "sambar", "sp-05": "barking deer"}
GBIF_LABEL = "GBIF records of this species"

# Which model does what, and why (tigerfish/llm.py).
MODELS = [
    ("Nemotron Lightning", "Reads text pages and extracts checkable claims with quotes; first "
        "pass on candidate pairs (triage); ToR promises; translates the letter.",
     "Fast and cheap, so it can read every page of a 1,000-page report."),
    ("Nemotron Super-VL", "Reads scanned pages, tables and maps from the page image.",
     "Takes images: many EIA tables exist only as scans."),
    ("Nemotron Ultra", "Reads both full pages of each candidate pair and gives the verdict; "
     "re-reads possible ToR shortfalls; writes the reviewer's memo and answers questions.",
     "The strongest reasoning, used only where a verdict is made."),
    ("Tavily", "Searches the web for copied text, the official record, the paper trail and "
     "the public record.", "Returns sources with their text, so every quote can be checked."),
    ("GBIF (no model)", "Species names, occurrence records near the site and IUCN categories.",
     "Open biodiversity data; free."),
]
LEVELS = [
    ("Quick check", "free, text layer",
     "Available free checks on the readable text layer, within page and name caps: number pairs, species and IUCN "
        "categories against GBIF, threatened species near the site that are never mentioned. "
        "No key, no model calls."),
    ("Deep audit", "chosen pages, live",
     f"The model checks (claims, contradictions, recycled figures) on up to "
     f"{page_picks.MAX_PAGES} pages you choose. Needs a key: the site's or your own. The cost "
     "is shown before anything runs."),
    ("Full audit", "scoped report run",
     "Claim extraction, contradictions and copied-text checks over the selected report scope. "
        "Run scripts/audit.py locally; specialized checks use separate scripts and inputs. "
        "The three saved full audits took about an hour each; quick checks are a different scope."),
]


def heading(title, sub=None, key=None, back=False):
    """A page heading on its own paper strip (text never sits on the pattern)."""
    with st.container(key=key or f"tf-panel-head-{title.lower().replace(' ', '-')}"):
        if back:
            library_ui.back_link()
        st.markdown(f'<h1 class="tf-h1 tf-title">{esc(title)}</h1>'
                    + (f'<div class="tf-lede">{esc(sub)}</div>' if sub else ""),
                    unsafe_allow_html=True)


def hero_flags():
    """[(finding, common name, reviewers' decision rows)] for the Home slip, or [] when the
    report or a reviewer's confirmation is missing (Home then shows the tigerfish slip)."""
    try:
        report = data.load(HERO_REPORT)
    except (OSError, KeyError, ValueError):
        return []
    confirmed = review.confirmed_findings(report)
    by_id = {f["id"]: f for f in report.get("findings") or []}
    rows = [(by_id[i], name, confirmed[i]) for i, name in HERO_SPECIES.items()
            if i in by_id and i in confirmed]
    return rows if len(rows) == len(HERO_SPECIES) else []


def gbif_line(finding):
    """"0 within 100 km, 0 within 500 km, 67,764 worldwide" from the finding's evidence."""
    return next((e["value"] for e in finding.get("evidence") or [] if e["label"] == GBIF_LABEL), "")


def _none_within_500(finding):
    return gbif_line(finding).split(", ")[1:2] == ["0 within 500 km"]


# Home's other findings (report id, finding id), after the hero: each verified by a person.
HOME_FINDINGS = [("great_nicobar_2021_draft", "ct-031"), ("great_nicobar_2021_draft", "rf-010")]
SHOWCASE = "great_nicobar_2021_draft"      # the audit Home sends a visitor to, and counts from


def _tile(visual, f, title, reason, foot, href):
    head = (f'<div class="tf-slip-head">{badge(f["grade"])}<span class="tf-check">'
            f'{esc(f.get("check_name", ""))}</span></div>')
    return (f'<a class="tf-tile" href="{esc(href)}" target="_self">{visual}<div class="tf-tile-body">'
            f'{head}<div class="tf-tile-title">{esc(title)}</div>'
            f'<div class="tf-tile-reason">{esc(reason)}</div><div class="tf-slip-foot">{foot}</div>'
            f"</div></a>")


def hero_tile(flags):
    """The species tile: the hero flags (sambar, barking deer) a reviewer confirmed."""
    names = " and the ".join(name for _, name, _ in flags)
    reason = f"A species list for Indira Point, Great Nicobar, names the {names}."
    if all(_none_within_500(f) for f, _, _ in flags):
        reason += " GBIF has no record of either within 500 km."
    p = species_photos.photo_for(HERO_REPORT, flags[0][0]["id"])
    visual = (f'<img class="tf-tile-img" src="{esc(p["image_url"])}" alt="{esc(flags[0][1])}, '
              f'reference photo, not from the site" loading="lazy">') if p else ""
    rows = [r for _, _, rs in flags for r in rs]
    return _tile(visual, flags[0][0], "Mainland deer on an island's species list", reason,
                 slip.verified_html(flags[0][0], rows), f"/library?report={HERO_REPORT}")


def finding_tile(report_id, finding_id):
    try:
        f = next(x for x in data.load(report_id)["findings"] if x["id"] == finding_id)
    except (OSError, KeyError, ValueError, StopIteration):
        return ""
    uri, page = slip.crop_for(f)
    visual = (f'<img class="tf-tile-img tf-tile-crop" src="{uri}" alt="Highlighted lines of page '
              f'{esc(page)} of the report">') if uri else ""
    return _tile(visual, f, f["title"], slip.reason_of(f), slip.verified_html(f),
                 f"/library?report={report_id}")


def model_counts(report_id=SHOWCASE):
    """What each Nemotron model did in this report's saved full audit, from results/ (None if
    the audit's files are missing)."""
    rep = _read_json(ROOT / "results" / f"{report_id}.json")
    run = (rep or {}).get("full_run") or {}
    audit = _read_json(ROOT / "results" / run["file"]) if run.get("file") else None
    readers = _read_json(ROOT / "results" / f"page_readers_{report_id}.json") or {}
    if not rep or not audit:
        return None
    flags = sum(n for check, by in audit.get("findings_by_check", {}).items()
                if check in ("contradiction", "recycled_figure")
                for g, n in by.items() if g in ("RED", "ORANGE"))
    return {"title": rep["title"], "pages": audit["pages_audited"], "claims": audit["claims"],
            "candidates": audit["candidates"], "verdicts": audit["verdicts"], "flags": flags,
            "text_pages": len(readers.get("lightning", [])),
            "scan_pages": len(readers.get("super_vl", [])),
            "usd": run.get("cost_usd"), "minutes": round((run.get("wall_clock_s") or 0) / 60)}


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def models_html(c):
    cols = [
        ("Nemotron Lightning", "reads and screens",
         f"Pulled {c['claims']:,} checkable claims, each with its quote, out of the pages "
         f"(the {c['text_pages']:,} text pages among them). Then screened {c['candidates']:,} "
         "pairs of claims that might disagree."),
        ("Nemotron Super-VL", "reads the images",
         f"Read {c['scan_pages']:,} pages from the page image: scans, tables and maps, where "
         "the text layer cannot be trusted."),
        ("Nemotron Ultra", "gives the verdict",
         f"Read both full pages of {c['verdicts']:,} pairs and answered yes/no questions about "
         f"each. TigerFish computes the grade from those answers, not from the model's say: "
         f"{c['flags']:,} pairs graded RED or ORANGE."),
    ]
    body = "".join(f'<div class="tf-model-col"><div class="tf-model-name">{esc(n)}</div>'
                   f'<div class="tf-model-role">{esc(r)}</div><p>{esc(t)}</p></div>'
                   for n, r, t in cols)
    cost = (f" for ${c['usd']:,.2f} in model calls" if c.get("usd") else "")
    return (f'<div class="tf-models-row">{body}</div><p class="tf-meta">{esc(c["title"])}: '
            f'{c["pages"]:,} pages{esc(cost)}, about {c["minutes"]} minutes. Every flag is a lead '
            "for a person to check, not a verdict.</p>")


def report_rows(items):
    """The fully audited reports as rows: title, where and when, flags, checks by a person."""
    rows = []
    for e in items:
        g = e["grades"]
        meta = " · ".join(str(x) for x in (e.get("state"), e.get("year"), e["audit_type"]) if x)
        n = _reviewer_confirmed(e)
        checked = ", ".join(x for x in (
            f'{e["verified"]} verified by a person' if e.get("verified") else "",
            f"{n} confirmed by a reviewer" if n else "") if x)
        rows.append(
            f'<a class="tf-row" href="/library?report={esc(e["id"])}" target="_self">'
            f'<span class="tf-row-main"><span class="tf-row-title">{esc(e["project"])}</span>'
            f'<span class="tf-meta">{esc(meta)}</span></span>'
            f'<span class="tf-row-grades">{badge("RED")}{mono(f"{g["RED"]:,}")} '
            f'{badge("ORANGE")}{mono(f"{g["ORANGE"]:,}")}</span>'
            f'<span class="tf-meta tf-row-checked">{esc(checked)}</span></a>')
    return f'<div class="tf-rows">{"".join(rows)}</div>'


def _reviewer_confirmed(entry):
    """Findings of a saved report that reviewers confirmed and no one hand-verified."""
    if entry["audit_type"] == library.QUICK:
        return 0
    try:
        rep = data.load(entry["id"])
    except (OSError, KeyError, ValueError):
        return 0
    confirmed = review.confirmed_findings(rep)
    return sum(1 for f in rep["findings"] if f["id"] in confirmed and not f.get("verification"))


def open_showcase():
    library_ui.open_report(SHOWCASE)


HOME_CSS = """<style>
.tf-home-intro { max-width: 46rem; margin: 1rem 0 0.5rem 0; }
.tf-eyebrow { font-family: Newsreader, Georgia, serif; font-style: italic; font-size: 1.125rem;
  color: var(--tf-teal); margin: 0 0 0.5rem 0; }
.tf-home-intro .tf-h1 { color: var(--tf-ink); }
.tf-home-lede { font-size: 1.125rem; color: var(--tf-ink); margin: 0 0 1.25rem 0; }
.tf-section-head { font-family: Newsreader, Georgia, serif; font-size: 1.5rem; font-weight: 600;
  color: var(--tf-ink); margin: 3rem 0 0.25rem 0; }
.tf-section-sub { color: var(--tf-muted); margin: 0 0 1rem 0; }
.tf-tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }
a.tf-tile { display: flex; flex-direction: column; background: var(--tf-paper); border: 1px solid var(--tf-rule);
  border-radius: 4px; color: var(--tf-ink) !important; text-decoration: none !important; overflow: hidden; }
a.tf-tile:hover { border-color: var(--tf-teal); }
.tf-tile-img { width: 100%; height: 170px; object-fit: cover; display: block; border-bottom: 1px solid var(--tf-rule);
  background: var(--tf-paper-2); }
.tf-tile-crop { object-fit: contain; background: #FFFFFF; }
.tf-tile-body { padding: 0.9rem 1rem 1rem 1rem; display: flex; flex-direction: column; gap: 0.35rem; flex: 1; }
.tf-tile-title { font-family: Newsreader, Georgia, serif; font-size: 1.125rem; font-weight: 600; line-height: 1.2; }
.tf-tile-reason { font-size: 1rem; flex: 1; }
.tf-models-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 2rem;
  border-top: 1px solid var(--tf-rule); padding-top: 1rem; }
.tf-model-name { font-family: "IBM Plex Mono", Consolas, monospace; font-weight: 500; color: var(--tf-teal); }
.tf-model-role { font-family: Newsreader, Georgia, serif; font-size: 1.125rem; font-weight: 600; margin: 0.15rem 0 0.35rem 0; }
.tf-models-row p { margin: 0; }
.tf-rows { border-top: 1px solid var(--tf-rule); }
a.tf-row { display: grid; grid-template-columns: minmax(0, 1fr) auto 12rem; gap: 1rem; align-items: center;
  padding: 0.8rem 0.25rem; border-bottom: 1px solid var(--tf-rule); color: var(--tf-ink) !important;
  text-decoration: none !important; }
a.tf-row:hover { background: var(--tf-paper); }
.tf-row-main { display: flex; flex-direction: column; }
.tf-row-title { font-family: Newsreader, Georgia, serif; font-size: 1.125rem; font-weight: 600; }
.tf-row-grades .tf-badge { margin: 0 0.3rem 0 0.6rem; }
.tf-row-checked { text-align: right; }
@media (max-width: 900px) {
  .tf-tiles, .tf-models-row { grid-template-columns: minmax(0, 1fr); }
  a.tf-row { grid-template-columns: minmax(0, 1fr); gap: 0.3rem; }
  .tf-row-checked { text-align: left; }
  .tf-row-grades .tf-badge:first-child { margin-left: 0; }
}
</style>"""


def home():
    st.markdown(HOME_CSS, unsafe_allow_html=True)
    items = library_ui.entries()
    t = library.totals(items)
    st.markdown(f'<div class="tf-home-intro"><p class="tf-eyebrow tf-home-tag">{esc(TAGLINE)}</p>'
                f'<h1 class="tf-h1">{esc(PURPOSE)}</h1>'
                '<p class="tf-home-lede">TigerFish reads an Indian environmental impact report '
                "end to end with NVIDIA Nemotron models and flags what does not add up: claims "
                "that contradict each other, species that do not live there, text copied from "
                "other projects. Every flag shows the page and the exact quote, so a person can "
                "check it.</p></div>", unsafe_allow_html=True)
    a, b, _ = st.columns([2.2, 1.6, 4], gap="small", vertical_alignment="center")
    with a:
        if st.button("See the Great Nicobar audit", type="primary", key="home::showcase",
                     icon=":material/arrow_forward:"):
            open_showcase()
            st.switch_page(PAGES["library"], query_params={"report": SHOWCASE})
    with b:
        st.page_link(PAGES["upload"], label="Upload your EIA", icon=":material/upload_file:")
    st.markdown(f'<p class="tf-meta tf-home-totals">So far: {esc(library.totals_line(t))}, '
                "computed from the saved results.</p>", unsafe_allow_html=True)

    flags = hero_flags()
    tiles = ([hero_tile(flags)] if flags else []) + [finding_tile(r, f) for r, f in HOME_FINDINGS]
    st.markdown('<h2 class="tf-section-head">What it found, checked by a person</h2>'
                '<p class="tf-section-sub">Three flags from the saved audits that a person '
                "checked against the report. Open one to see the pages.</p>"
                f'<div class="tf-tiles">{"".join(x for x in tiles if x)}</div>',
                unsafe_allow_html=True)

    c = model_counts()
    if c:
        st.markdown('<h2 class="tf-section-head">Three Nemotron models, one job each</h2>'
                    f'<p class="tf-section-sub">On the {esc(c["title"])}, from the saved run.</p>'
                    + models_html(c), unsafe_allow_html=True)
        st.page_link(PAGES["how"], label="How it works", icon=":material/arrow_forward:")

    full = [e for e in items if e["audit_type"] != library.QUICK]
    st.markdown('<h2 class="tf-section-head">Reports audited in full</h2>'
                f'<p class="tf-section-sub">{len(full)} reports read with the model checks. '
                f"{t['reports'] - len(full)} more had a quick check (free checks only).</p>"
                + report_rows(full), unsafe_allow_html=True)
    st.page_link(PAGES["library"], label=f"Browse all {t['reports']} reports",
                 icon=":material/arrow_forward:")
    st.markdown(f'<p class="tf-meta" style="margin-top:3rem">{esc(BUILT_WITH)}</p>',
                unsafe_allow_html=True)


def library_page():
    view, report_id = library_ui.current()
    if view != "report":
        heading("Report library", "Every EIA TigerFish has read. Open one to see its flags, "
                "each with the page and the quote.")
        library_ui.render()
        return
    entry = library.find(library_ui.entries(), report_id)
    with st.container(key="tf-panel-report-bar"):
        a, _, b = st.columns([2, 3, 2], vertical_alignment="center")
        with a:
            library_ui.back_link()
        with b:
            library_ui.switcher(report_id)
    if entry is None:
        with st.container(key="tf-panel-missing"):
            st.error("This report is not in the library.")
            st.markdown(f"No saved report has the id `{esc(report_id)}`. The link may be old or "
                        "mistyped. Go back to the library and pick the report from the list.")
        return
    if entry["audit_type"] == library.QUICK:      # free checks only: the lighter view
        report_view.render(library.load(entry), quick=True)
    else:
        report_view.render(data.load(report_id))


def upload_page():
    heading("Upload your EIA", sub="Run the free checks on a PDF of your own, then choose pages for "
            "the model checks.")
    with st.container(key="tf-panel-upload"):
        report = upload.render()
    if report is not None:
        report_view.render(report)


def levels_table():
    rows = "".join(f"<tr><td><b>{esc(n)}</b></td><td>{esc(s)}</td><td>{esc(b)}</td></tr>"
                   for n, s, b in LEVELS)
    return ('<table class="tf-table"><thead><tr><th>Level</th><th>Scope</th><th>What runs</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>')


def _diagram():
    from tigerfish.ui.diagram import diagram_svg
    return diagram_svg()


def how_it_works_page():
    st.markdown(HOME_CSS, unsafe_allow_html=True)
    heading("How it works", "From a PDF to flags a person can check.")
    left, right = st.columns([5, 6], gap="large")
    with left, st.container(key="tf-panel-diagram"):
        st.markdown(_diagram(), unsafe_allow_html=True)
    with right, st.container(key="tf-panel-method"):
        st.markdown(method.method_text())
        st.page_link(PAGES["limitations"], label="Known limitations",
                     icon=":material/arrow_forward:")
    c = model_counts()
    with st.container(key="tf-panel-models"):
        st.markdown('<h2 class="tf-section-head">Which model does what, and why</h2>'
                    + (f'<p class="tf-section-sub">With the counts from the saved run on the '
                       f'{esc(c["title"])}.</p>' + models_html(c) if c else "")
                    + '<table class="tf-table" style="margin-top:1.5rem"><thead><tr><th>Model or '
                    "tool</th><th>Does</th><th>Why</th></tr></thead><tbody>" + "".join(
                        f'<tr><td class="tf-mono">{esc(n)}</td><td>{esc(d)}</td><td>{esc(w)}</td></tr>'
                        for n, d, w in MODELS) + "</tbody></table>", unsafe_allow_html=True)
        st.caption("NVIDIA Nemotron models run on Nebius Token Factory. Text-backed quotes "
            "are matched to source text; image-only readings are shown with their "
            "source image and labelled unverified.")
    with st.container(key="tf-panel-levels"):
        st.markdown('<h2 class="tf-section-head">Three levels</h2>' + levels_table(),
                    unsafe_allow_html=True)


def limitations():
    heading("Limitations", "Every flag is a lead for human review, not a verdict.")
    with st.container(key="tf-panel-limits"):
        st.markdown(method.limits_text())
    text = method.limitations_text()
    if text:
        with st.container(key="tf-panel-failures"):
            st.markdown('<h2 class="tf-section-head">Failure cases from our own runs</h2>'
                        '<p class="tf-section-sub">From docs/LIMITATIONS.md.</p>',
                        unsafe_allow_html=True)
            st.markdown(text.replace("$", "\\$"))      # $ pairs would render as LaTeX


# Filled by build(); the keys are used across the app (st.page_link / st.switch_page).
PAGES = {}


def build():
    """The page objects, in menu order. Call once per run, before st.navigation."""
    PAGES.update({
        "home": st.Page(home, title="Home", url_path="home", default=True),
        "library": st.Page(library_page, title="Library", url_path="library"),
        "upload": st.Page(upload_page, title="Upload", url_path="upload"),
        "how": st.Page(how_it_works_page, title="How it works", url_path="how-it-works"),
        "limitations": st.Page(limitations, title="Limitations", url_path="limitations"),
    })
    return list(PAGES.values())
