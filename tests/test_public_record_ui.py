"""Public record tab, knowable / photo card lines and Tavily credits on the cost card (replay)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest  # noqa: F401
from apptest import open_app

from tigerfish import knowable, public_record, species_photos
from tigerfish.ui import cards, data
from tigerfish.ui import public_record as ui

ROOT = Path(__file__).resolve().parent.parent
GN = "great_nicobar_2021_draft"
pytestmark = pytest.mark.skipif(not public_record.path(GN).exists(), reason="no public record saved")


def test_knowable_line_only_when_a_source_passed():
    k = {"findings": [{"finding_id": "x", "sources": [
        {"quote": "Q here", "title": "ZSI", "host": "zsi.gov.in", "date": "2008-03-01", "url": "https://zsi.gov.in/a"}]},
        {"finding_id": "y", "sources": []}]}
    html = ui.knowable_html(GN, "x", k)
    assert knowable.CARD_TEXT in html and "“Q here”" in html and "2008-03-01" in html
    assert ui.knowable_html(GN, "y", k) == "" and ui.knowable_html(GN, "z", k) == ""


def test_photo_has_attribution_or_nothing():
    d = {"photos": {GN: {"a": {"photo": {"species": "Axis axis", "image_url": "https://upload.wikimedia.org/x.jpg",
                                         "page": "https://commons.wikimedia.org/wiki/File:x.jpg",
                                         "licence": "CC BY-SA 4.0", "licence_url": "https://cc/by-sa",
                                         "author": "B. Person"}},
                         "b": {"photo": None}}}}
    html = ui.photo_html(GN, "a", d)
    assert "B. Person" in html and "CC BY-SA 4.0" in html and "Wikimedia Commons" in html
    assert ui.photo_html(GN, "b", d) == ""


def test_cost_card_credits_include_audit_and_new_checks():
    total, parts = cards.tavily_credits(data.load(GN))
    names = dict(parts)
    assert names["audit"] == 84 and "public record" in names and total == sum(names.values())


def test_saved_timeline_events_are_verified():
    rec = public_record.load(GN)
    for e in rec["timeline"]:
        assert e["quote"] and e["source"].startswith("http") and e["quote_check"]


def test_saved_photos_are_free_and_credited():
    for rows in species_photos.load()["photos"].values():
        for r in rows.values():
            if r["photo"]:
                assert species_photos.is_free(r["photo"]["licence"]) and r["photo"]["author"]


def test_public_record_tab_renders(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    at = open_app(timeout=60)
    assert not at.exception
    labels = [t.label for t in at.tabs]
    assert "Public record" in labels
    tab = at.tabs[labels.index("Public record")]
    text = " ".join(m.value for m in tab.markdown)
    assert "Clearance timeline" in text and "What happened next" in text
    assert "Local-language coverage" in text
