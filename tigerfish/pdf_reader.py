"""Read a PDF page by page: text, plus a "needs_vision" flag and PNG for hard pages.

Page numbers are 1-based physical page numbers, the same number a PDF viewer
shows in its page box (page 1 = first page of the file). Printed page labels
in the document can differ; those are kept separately as "label".

Pages are processed one at a time (iter_pages is a generator), so large PDFs
are never fully loaded into memory. A page that fails to parse is logged and
returned with an "error" instead of stopping the whole run.

read_pdf saves its result to cache/pages/<pdf_name>/pages.jsonl and reuses it
until the PDF file changes, so a 1000-page report is only parsed once.
"""

import json
import logging
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "cache" / "pages"

DPI = 150
MIN_TEXT_CHARS = 200        # fewer characters than this: probably a scanned page
MIN_IMAGE_FRACTION = 0.25   # one image covering this much of the page: map/figure/scan
MIN_TABLE_LINES = 30        # only run the (slow) table finder on pages with this many drawn lines

log = logging.getLogger(__name__)


def _largest_image_fraction(page):
    page_area = abs(page.rect)
    if not page_area:
        return 0.0
    areas = [abs(pymupdf.Rect(img["bbox"]) & page.rect) for img in page.get_image_info()]
    return max(areas, default=0.0) / page_area


def _has_table(page):
    # get_drawings is cheap; find_tables is ~0.5 s/page, so gate it on ruled lines.
    lines = sum(1 for d in page.get_drawings() for item in d["items"] if item[0] in ("l", "re"))
    if lines < MIN_TABLE_LINES:
        return False
    return len(page.find_tables().tables) > 0


def vision_reasons(page, text):
    """Why this page should go to the vision model (empty list = text is enough)."""
    reasons = []
    if len(text.strip()) < MIN_TEXT_CHARS:
        reasons.append("little_text")
    if _largest_image_fraction(page) >= MIN_IMAGE_FRACTION:
        reasons.append("large_image")
    if _has_table(page):
        reasons.append("table")
    return reasons


def render_page(page, pdf_name, number):
    """Save the page as PNG at DPI under cache/pages/<pdf_name>/ (skipped if already there)."""
    path = PAGES_DIR / pdf_name / f"page_{number}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        page.get_pixmap(dpi=DPI).save(path)
    return path


def iter_pages(pdf_path, render=True):
    """Yield one dict per page, in order:

    {"page": 1-based number, "label": printed label or "", "text": str,
     "needs_vision": bool, "reasons": [...], "image_path": str | None, "error": str | None}
    """
    pdf_path = Path(pdf_path)
    with pymupdf.open(pdf_path) as doc:
        for index in range(doc.page_count):
            number = index + 1
            result = {"page": number, "label": "", "text": "", "needs_vision": False,
                      "reasons": [], "image_path": None, "error": None}
            try:
                page = doc.load_page(index)
                result["label"] = page.get_label()
                result["text"] = page.get_text()
                result["reasons"] = vision_reasons(page, result["text"])
                result["needs_vision"] = bool(result["reasons"])
                if result["needs_vision"] and render:
                    result["image_path"] = str(render_page(page, pdf_path.stem, number))
            except Exception as e:
                log.warning("%s page %d failed: %s", pdf_path.name, number, e)
                result["error"] = str(e)
            yield result


def read_pdf(pdf_path, render=True, use_cache=True):
    """Return all pages as a list (text only in memory; images go to disk).

    Cached in cache/pages/<pdf_name>/pages.jsonl; the cache is ignored if the
    PDF is newer than it, or if it was built with render=False and we now render.
    """
    pdf_path = Path(pdf_path)
    cache = PAGES_DIR / pdf_path.stem / "pages.jsonl"
    if use_cache and cache.exists() and cache.stat().st_mtime > pdf_path.stat().st_mtime:
        with cache.open(encoding="utf-8") as f:
            pages = [json.loads(line) for line in f]
        if not render or all(p["image_path"] for p in pages if p["needs_vision"]):
            return pages

    pages = []
    cache.parent.mkdir(parents=True, exist_ok=True)
    with cache.open("w", encoding="utf-8") as f:
        for page in iter_pages(pdf_path, render=render):
            f.write(json.dumps(page, ensure_ascii=False) + "\n")
            pages.append(page)
    return pages
