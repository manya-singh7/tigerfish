"""Start the app in Streamlit's AppTest. The app opens on Home; page="library" opens the report
library; a report opens with ?report=<id> (the default here: Great Nicobar, the report most tests
check), which the app sends on to the Library page."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
GN = "great_nicobar_2021_draft"
# Each run of the full report page takes 6-20 s; on a loaded machine (the whole suite, a browser
# open) one can pass 60 s. A slow run should wait, not fail: every run gets at least this long.
# A hung app still fails, and no test measures speed.
MIN_TIMEOUT = 180


def open_app(report=GN, timeout=60, view=None, page=None):
    """report=None and view=None: Home (or page="library" etc., by its url_path).
    view="upload": the upload screen."""
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=max(timeout, MIN_TIMEOUT))
    if report:
        at.query_params["report"] = report
    elif view:
        at.query_params["view"] = view
    at.run()
    if page:
        return switch_to(at, page)
    return at


def switch_to(at, url_path):
    """Open a page of the top menu. AppTest.switch_page only takes page files, and the app's
    pages are functions (tigerfish/ui/pages.py), so pick the registered page by its url_path."""
    hashes = [h for h, info in at._registered_pages.items() if info.get("url_pathname") == url_path]
    assert hashes, f"no page {url_path!r}"
    at._page_hash = hashes[0]
    return at.run()


def section_picker(at, report=GN):
    """The selector of the sections under the Findings tab."""
    return at.button_group(key=f"sec::{report}::pick")


def show_section(at, section, report=GN):
    """Draw one section under Findings (only the chosen one is drawn)."""
    section_picker(at, report).set_value(section).run()
    return at


def every_section(at, report=GN):
    """Draw each section under Findings in turn; yield the app after each."""
    for section in section_picker(at, report).options:
        yield show_section(at, section.split(" (")[0], report)


def findings_text(at, report=GN):
    """The markdown of every section under Findings, drawn one after the other."""
    return "\n".join(m.value for a in every_section(at, report) for m in a.markdown)
