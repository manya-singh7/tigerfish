"""The official-record section and the "Evidence from the web" tab, in replay with no keys."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tigerfish.ui import official, web_evidence

ROOT = Path(__file__).resolve().parent.parent
HAS_RECORD = official.path("great_nicobar_2021_draft").exists()
pytestmark = pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(), reason="no results/")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()


def test_collect_covers_every_tavily_backed_check():
    rows = web_evidence.collect()
    checks = {r["check"] for r in rows}
    assert {"Borrowed text", "Consultant accreditation", "WPA schedule", "Investigate agent"} <= checks
    if HAS_RECORD:
        assert "Official record" in checks
    for r in rows:
        assert r["url"].startswith("http") and r["verified"] and r["label"]
        assert r["official"] == (r["label"] != "open web (not an official source)")


def test_stats_add_up():
    rows = web_evidence.collect()
    s = web_evidence.stats(rows)
    assert s["credits"] == sum(r["credits"] for r in s["rows"])
    assert 0 <= s["official_share"] <= 1 and s["sources"] == len({r["url"] for r in rows})
    if HAS_RECORD:
        rec = official.load("great_nicobar_2021_draft")
        row = next(r for r in s["rows"] if r["what"].endswith("official record"))
        assert (row["searches"], row["extracts"], row["credits"]) == (
            rec["tavily"]["searches"], rec["tavily"]["extracts"], rec["tavily"]["credits"])


def test_table_hides_grey_rows():
    data = {"comparisons": [
        {"label": "Project cost", "grade": "GREY", "report": {}, "official": {}},
        {"label": "Port capacity", "grade": "NONE",
         "report": {"value": 14.2, "unit": "Million TEU", "page": 1148},
         "official": {"value": 14.2, "unit": "million TEU", "url": "https://pib.gov.in/x",
                      "title": "PIB", "label": "official source", "date": "2026-05-01"}}]}
    html = official.table_html([r for r in data["comparisons"] if r["grade"] in official.SHOWN])
    assert "Port capacity" in html and "Project cost" not in html and "Matches" in html
    assert official.counts(data)["GREY"] == 1


@pytest.mark.skipif(not HAS_RECORD, reason="no saved official-record result")
def test_app_shows_official_record_section_and_web_tab(app):
    assert not app.exception
    html = "\n".join(m.value for m in app.markdown)
    assert "Does it match the official record?" in html
    assert "tf-table" in html and "Found via Tavily" in html
    assert "Evidence from the web" in html and "How the quote was verified" in html
    assert "Stated officially, not found in the report pages read" in html


def test_indira_point_has_no_official_record_section(app):
    app.selectbox[0].select("Indira Point REIA, Table 3.16 (as published by Scroll.in)").run()
    assert not app.exception
    html = "\n".join(m.value for m in app.markdown)
    assert "Does it match the official record?" not in html
    assert "Evidence from the web" in html                     # the tab covers all reports
