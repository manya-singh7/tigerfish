"""Start the app in Streamlit's AppTest. The home screen is the report library; a report
opens with ?report=<id> (the default here: Great Nicobar, the report most tests check)."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
GN = "great_nicobar_2021_draft"
# Each run of the full report page takes 6-20 s; on a loaded machine (the whole suite, a browser
# open) one can pass 60 s. A slow run should wait, not fail: every run gets at least this long.
# A hung app still fails, and no test measures speed.
MIN_TIMEOUT = 180


def open_app(report=GN, timeout=60, view=None):
    """report=None and view=None: the library. view="upload": the upload screen."""
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=max(timeout, MIN_TIMEOUT))
    if report:
        at.query_params["report"] = report
    elif view:
        at.query_params["view"] = view
    return at.run()
