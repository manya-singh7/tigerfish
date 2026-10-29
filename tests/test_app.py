"""The Streamlit app in replay mode: runs with no API keys, loads both saved reports,
and the letter builds from confirmed findings. Uses Streamlit's AppTest (no browser)."""

import io
import json
from pathlib import Path

import pytest
from docx import Document
from streamlit.testing.v1 import AppTest  # noqa: F401
from apptest import open_app

from tigerfish.ui import data, letter

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(),
                                reason="no results/ (run scripts/export_results.py)")


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")     # set-but-empty: load_dotenv won't override
    monkeypatch.setenv("TAVILY_API_KEY", "")


def test_app_runs_without_api_keys(no_keys):
    at = open_app(timeout=60)
    assert not at.exception
    assert not at.toggle                                  # no live mode without a key
    assert any(t.label.startswith("Contradictions (") for t in at.tabs)
    home = open_app(report=None, timeout=60)
    assert not home.exception
    assert any("Built for murky water." in m.value for m in home.markdown)


@pytest.mark.parametrize("report", [r["title"] for r in data.reports()])
def test_each_saved_report_renders(no_keys, report):
    at = open_app(timeout=60)
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
    gn001 = [f for f in report["findings"] if f.get("known_issue") == "gn-001"]
    body = letter.build_letter(report, gn001)
    text = "\n".join(p.text for p in Document(io.BytesIO(body)).paragraphs).lower()
    assert "page 392" in text and "page 978" in text
    assert "clarification requested" in text
    # "the port site lies within the bay" (Ultra's reason for gn-001) is about location
    words = set(text.replace("lies within", " ").replace(".", " ").replace(",", " ").split())
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
    at = open_app(timeout=60)
    text = "\n".join(m.value for m in at.markdown)
    assert "#### Evaluation" in text and "Planted contradictions" in text
    assert "1 USD = 84 INR" in text


def test_prerecorded_investigations_replay(no_keys):
    at = open_app(timeout=60)
    assert not at.exception
    labels = [e.label for e in at.expander if e.label.startswith("Investigation:")]
    assert len(labels) == 3                                    # gn-001 (recorded as ct-003), ac-01, sp-p954-001
    html = "\n".join(m.value for m in at.markdown)
    assert 'class="tf-timeline"' in html and "READ PAGE" in html and "Evidence memo" in html
    assert "Unverified reasoning (not checked)" in html and 'class="tf-ref"' in html
    # findings without a recording get an Investigate button, disabled without a key
    buttons = [b for b in at.button if b.label == "Investigate"]
    assert buttons and all(b.disabled for b in buttons)


def test_saved_investigations_are_neutral_and_verified():
    from tigerfish import agent, claims
    from tigerfish.pdf_reader import read_pdf
    pdf = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"
    pages = {p["page"]: p["text"] for p in read_pdf(pdf, render=False)} if pdf.exists() else {}
    for p in (ROOT / "results" / "investigations").glob("*.json"):
        inv = json.loads(p.read_text(encoding="utf-8"))
        memo = inv["memo"]
        assert memo["conclusion"] in agent.CONCLUSIONS and inv["totals"]["cost_usd"] <= agent.MAX_COST_USD
        assert inv["totals"]["steps"] <= agent.MAX_STEPS and inv["totals"]["tavily_credits"] <= agent.MAX_CREDITS
        ids = {i["id"] for i in memo["evidence"] + memo["data"]}
        assert all(r["evidence"] and set(r["evidence"]) <= ids for r in memo["reasons"]), p.name
        text = " ".join([r["text"] for r in memo["reasons"]] + memo["unverified_reasons"] + memo["checked"]
                        + [e["note"] for e in memo["evidence"]]).lower()
        assert not any(w.startswith(b) for w in text.split() for b in BANNED), p.name
        for e in memo["evidence"]:
            if e.get("page") and pages:
                assert claims.quote_on_page(e["quote"], pages[e["page"]]), (p.name, e["quote"][:60])
