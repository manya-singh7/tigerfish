"""'Found via Tavily' tags: on evidence from Tavily-backed checks and on web sources in
investigation memos, each linking to the source; never on GBIF or report-page links."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest  # noqa: F401
from apptest import open_app

from tigerfish.ui import cards, data, investigate

ROOT = Path(__file__).resolve().parent.parent


def test_tag_only_on_linked_evidence_of_tavily_checks():
    items = [{"label": "Source", "value": "FHWA", "url": "https://www.fhwa.dot.gov/x"},
             {"label": "Verbatim run", "value": "25 words"}]
    html = cards.evidence_html(items, "borrowed_text")
    assert html.count("Found via Tavily") == 1
    assert 'class="tf-tavily" href="https://www.fhwa.dot.gov/x"' in html
    gbif = [{"label": "GBIF species page", "value": "Axis axis", "url": "https://www.gbif.org/species/1"}]
    assert "Found via Tavily" not in cards.evidence_html(gbif, "species_range")
    eia = [{"label": "Report page", "value": "EIA p.292", "url": "https://example.org/eia.pdf#page=292"}]
    assert "Found via Tavily" not in cards.evidence_html(eia, "promise")
    by_hand = [{"label": "Certificate", "value": "33 B", "url": "https://x/c.pdf", "manual": True}]
    assert "Found via Tavily" not in cards.evidence_html(by_hand, "accreditation")


def test_verification_box_shows_who_outcome_wording_and_note():
    html = cards.verification_html({"by": "Manya Singh", "on": "2026-10-27",
                                    "outcome": "confirmed_with_nuance", "note": "p.978 <form>",
                                    "wording": "inconsistent about coral at the port site"})
    assert "Human-verified" in html and "Manya Singh, 2026-10-27" in html
    assert "Confirmed, with nuance" in html and "inconsistent about coral at the port site" in html
    assert "&lt;form&gt;" in html                          # escaped
    assert cards.verification_html(None) == ""


def test_memo_web_evidence_is_tagged_but_page_evidence_is_not():
    memo = {"conclusion": "strengthens", "reasons": [], "evidence": [
        {"id": "E1", "page": 44, "quote": "q", "note": "n"},
        {"id": "E2", "url": "https://eiameeting.qci.org.in/a.pdf", "quote": "q", "note": "n"}]}
    html = investigate.memo_html(memo)
    assert html.count("Found via Tavily") == 1 and 'href="https://eiameeting.qci.org.in/a.pdf"' in html


@pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(), reason="no results/")
def test_every_tavily_source_in_saved_results_gets_a_tag():
    for r in data.reports():
        for f in data.load(r["id"])["findings"]:
            linked = [e for e in f["evidence"] if e.get("url") and not e.get("manual")]
            html = cards.evidence_html(f["evidence"], f["check"])
            want = len(linked) if f["check"] in cards.TAVILY_CHECKS else 0
            assert html.count("Found via Tavily") == want, f["id"]


@pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(), reason="no results/")
def test_app_shows_tags(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    at = open_app(timeout=60)
    html = "\n".join(m.value for m in at.markdown)
    assert "Found via Tavily" in html
