from pathlib import Path

import pymupdf
import pytest

from tigerfish import pdf_reader

LONG_TEXT = "The proposed project area is 166.10 sq km on Great Nicobar Island. " * 6


@pytest.fixture
def tiny_pdf(tmp_path, monkeypatch):
    """Three pages: plain text, nearly empty (scan-like), and a ruled table."""
    monkeypatch.setattr(pdf_reader, "PAGES_DIR", tmp_path / "pages")
    doc = pymupdf.open()

    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 400), LONG_TEXT)

    page = doc.new_page()
    page.insert_text((50, 50), "Fig 3.1")

    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 20, 550, 140), LONG_TEXT)
    for row in range(8):
        for col in range(5):
            x, y = 50 + col * 100, 150 + row * 30
            page.draw_rect(pymupdf.Rect(x, y, x + 100, y + 30))
            page.insert_text((x + 5, y + 20), f"r{row}c{col}")

    path = tmp_path / "tiny.pdf"
    doc.save(path)
    doc.close()
    return path


def test_page_numbers_are_one_based_and_in_order(tiny_pdf):
    pages = pdf_reader.read_pdf(tiny_pdf)
    assert [p["page"] for p in pages] == [1, 2, 3]
    assert "166.10 sq km" in pages[0]["text"]
    assert "Fig 3.1" in pages[1]["text"]


def test_needs_vision_flags(tiny_pdf):
    pages = pdf_reader.read_pdf(tiny_pdf)
    assert not pages[0]["needs_vision"]
    assert "little_text" in pages[1]["reasons"]
    assert "table" in pages[2]["reasons"]


def test_vision_pages_rendered_with_matching_number(tiny_pdf):
    pages = pdf_reader.read_pdf(tiny_pdf)
    assert pages[0]["image_path"] is None
    for p in pages[1:]:
        assert p["image_path"].endswith(f"tiny\\page_{p['page']}.png") or \
               p["image_path"].endswith(f"tiny/page_{p['page']}.png")
        assert pdf_reader.PAGES_DIR.joinpath("tiny", f"page_{p['page']}.png").exists()


def test_bad_page_is_logged_and_skipped(tiny_pdf, monkeypatch):
    real = pdf_reader.vision_reasons

    def flaky(page, text):
        if page.number == 1:
            raise RuntimeError("corrupt page")
        return real(page, text)

    monkeypatch.setattr(pdf_reader, "vision_reasons", flaky)
    pages = pdf_reader.read_pdf(tiny_pdf)
    assert [p["page"] for p in pages] == [1, 2, 3]
    assert pages[1]["error"] == "corrupt page"
    assert pages[2]["error"] is None


def test_second_read_comes_from_cache(tiny_pdf, monkeypatch):
    first = pdf_reader.read_pdf(tiny_pdf)
    monkeypatch.setattr(pdf_reader, "iter_pages", lambda *a, **k: iter(()))  # would return []
    assert pdf_reader.read_pdf(tiny_pdf) == first
