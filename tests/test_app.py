"""The Streamlit app in replay mode: runs with no API keys, loads both saved reports,
and the letter builds from confirmed findings. Uses Streamlit's AppTest (no browser)."""

import io
import json
from pathlib import Path

import pytest
from docx import Document
from streamlit.testing.v1 import AppTest

from tigerfish.ui import data, letter

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(),
                                reason="no results/ (run scripts/export_results.py)")


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")     # set-but-empty: load_dotenv won't override
    monkeypatch.setenv("TAVILY_API_KEY", "")


def test_app_runs_without_api_keys(no_keys):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert not at.toggle                                  # no live mode without a key
    assert any("Sees clearly in murky waters." in m.value for m in at.markdown)


@pytest.mark.parametrize("report", [r["title"] for r in data.reports()])
def test_each_saved_report_renders(no_keys, report):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.selectbox[0].select(report).run()
    assert not at.exception
    assert any("What would clear this" in m.value for m in at.markdown)


def test_results_have_no_pdfs_keys_or_scroll_image():
    files = list((ROOT / "results").rglob("*"))
    assert not [f for f in files if f.suffix.lower() == ".pdf"]
    assert not [f for f in files if "indira_point_table_3_16_mammals" in f.name]
    for f in files:
        if f.suffix == ".json":
            text = f.read_text(encoding="utf-8")
            assert "API_KEY" not in text and "tvly-" not in text


BANNED = ("lie", "liar", "fraud", "fake", "fabricat", "dishonest", "cheat")


def test_letter_is_neutral_and_cites_pages():
    report = data.load("great_nicobar_2021_draft")
    body = letter.build_letter(report, report["findings"][:2])
    text = "\n".join(p.text for p in Document(io.BytesIO(body)).paragraphs).lower()
    assert "page 392" in text and "page 978" in text
    assert "clarification requested" in text
    words = set(text.replace(".", " ").replace(",", " ").split())
    assert not any(w.startswith(b) for w in words for b in BANNED)


def test_every_finding_has_card_fields():
    for r in data.reports():
        for f in data.load(r["id"])["findings"]:
            assert f["grade"] in ("RED", "ORANGE", "INFO")
            assert f["why"] and f["clear"] and f["quotes"] and f["message"]
            for rel in f["images"]:
                assert data.image_path(rel) is not None, rel


@pytest.mark.skipif(not (ROOT / "results" / "eval.json").exists(), reason="no results/eval.json")
def test_method_tab_shows_evaluation(no_keys):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    text = "\n".join(m.value for m in at.markdown)
    assert "#### Evaluation" in text and "Planted contradictions" in text
    assert "1 USD = 84 INR" in text
