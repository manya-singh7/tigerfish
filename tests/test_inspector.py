"""The "How TigerFish reads scanned pages" panel, from results/inspector/ (replay, no keys)."""

from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest  # noqa: F401
from apptest import open_app

from tigerfish.ui import inspector

ROOT = Path(__file__).resolve().parent.parent
REPORT = "great_nicobar_2021_draft"
pytestmark = pytest.mark.skipif(inspector.index() is None, reason="no results/inspector/")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    return open_app(timeout=60)


def test_saved_pages_are_complete():
    pages = inspector.pages(REPORT)
    assert 3 <= len(pages) <= 4
    assert {p["page"] for p in pages} >= {978}
    for p in pages:
        assert p["model"] == "nvidia/Nemotron-3.5-Super-VL"
        assert p["rows"] and p["claims"] and p["title"] and p["why"]
        assert p["cache_files"] and all(f.startswith("cache/llm/") for f in p["cache_files"])
        with Image.open(inspector.image_path(p)) as img:     # downscaled, portrait page
            assert img.width <= 900 and img.height > img.width
        # every row is a line Super-VL quoted; the row count is what the panel reports
        quotes = {" ".join(str(c["quote"]).split()) for c in p["claims"] if c.get("quote")}
        assert {r["read"] for r in p["rows"]} == quotes


def test_scanned_pages_have_no_usable_text_layer():
    scanned = [p for p in inspector.pages(REPORT) if not inspector.has_text_layer(p)]
    assert len(scanned) >= 2
    for p in scanned:
        assert p["text_layer"]["chars"] < 200 and "little_text" in p["vision_reasons"]
        assert p["rows_in_text_layer"] == 0
        n = inspector.note(p)
        assert f"Text extraction found {p['text_layer']['chars']} characters" in n
        assert "no usable text layer" in n and f"Super-VL read {len(p['rows'])} rows" in n
        assert "no text layer" in inspector.rows_html(p)


def test_p978_form_is_described_honestly():
    """p.978 has a text layer; the note must say so, not claim it is a scan."""
    p978 = next(p for p in inspector.pages(REPORT) if p["page"] == 978)
    assert inspector.has_text_layer(p978) and "table" in p978["vision_reasons"]
    n = inspector.note(p978)
    assert "this page has a text layer" in n and "no usable text layer" not in n
    assert f"{p978['rows_in_text_layer']} of them were found word for word" in n
    assert any("Coral reef exists" in r["read"] for r in p978["rows"])   # half of ct-003


def test_rows_html_escapes_cells():
    page = {"text_layer": {"chars": 0, "text": ""}, "vision_reasons": ["little_text"],
            "rows": [{"read": "<b>x</b> & y", "values": ["1"], "in_text_layer": False}]}
    html = inspector.rows_html(page)
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in html and "<b>x</b>" not in html


def test_other_reports_have_no_pages():
    assert inspector.pages("indira_point_table_3_16") == []
    assert inspector.pages("no_such_report") == []


def test_app_shows_scanned_pages_panel(app):
    assert not app.exception
    html = "\n".join(m.value for m in app.markdown)
    assert "How TigerFish reads scanned pages" in html
    assert "Row as read by Super-VL" in html and "Text extraction" in html
    radio = next(r for r in app.radio if any(o.startswith("p.978") for o in r.options))
    assert len(radio.options) == len(inspector.pages(REPORT))


def test_app_switches_inspector_page(app):
    radio = next(r for r in app.radio if any(o.startswith("p.978") for o in r.options))
    radio.set_value(next(o for o in radio.options if o.startswith("p.978"))).run()
    assert not app.exception
    html = "\n".join(m.value for m in app.markdown)
    assert "Coral reef exists in the proposed site" in html
    assert "this page has a text layer" in html


def test_indira_point_shows_notice(app):
    app.selectbox[0].select("Indira Point REIA, Table 3.16 (as published by Scroll.in)").run()
    assert not app.exception
    assert any("Great Nicobar EIA only" in i.value for i in app.info)
