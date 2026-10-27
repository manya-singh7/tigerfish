""""How TigerFish reads scanned pages": the page image next to the rows Nemotron Super-VL read
from it, with how much text a plain text extraction found on the same page.

Replay only: results/inspector/ (written by scripts/build_inspector.py from the cached
Super-VL replies of the audit run). No keys needed.
"""

import json
from pathlib import Path

from tigerfish.pdf_reader import MIN_TEXT_CHARS

INSPECTOR = Path(__file__).resolve().parents[2] / "results" / "inspector"
REASONS = {"little_text": "almost no extractable text", "large_image": "one image covers most of the page",
           "table": "a ruled table"}


def index():
    """{"report_id", "pages": [{page, file, title}]} or None."""
    p = INSPECTOR / "index.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pages(report_id):
    """Saved inspector pages for a report, in display order ([] if none)."""
    idx = index()
    if not idx or idx["report_id"] != report_id:
        return []
    return [json.loads((INSPECTOR / p["file"]).read_text(encoding="utf-8")) for p in idx["pages"]]


def image_path(page):
    return INSPECTOR / page["image"]


def has_text_layer(page):
    return page["text_layer"]["chars"] >= MIN_TEXT_CHARS


def short_label(page):
    """'p.896 · Health environment data' for the page picker."""
    return f"p.{page['page']} · {page['title'].split(',')[0].split(' (')[0]}"


def note(page):
    """Plain-language comparison: characters found by text extraction vs rows read by Super-VL."""
    chars, rows = page["text_layer"]["chars"], len(page["rows"])
    why = ", ".join(REASONS.get(r, r) for r in page["vision_reasons"])
    if has_text_layer(page):
        return (f"Text extraction found {chars:,} characters: this page has a text layer. It went to "
                f"Super-VL because it is {why}. Super-VL read {rows} rows; "
                f"{page['rows_in_text_layer']} of them were found word for word in the text layer.")
    found = page["text_layer"]["text"]
    what = f" (only “{found}”, a scanner watermark)" if found else ""
    return (f"Text extraction found {chars} characters{what}: this page has no usable text layer, "
            f"so a text-only reader sees nothing here. Super-VL read {rows} rows from the image. "
            f"They cannot be matched to a text layer, so TigerFish marks them unverified: "
            f"check them against the image.")


def rows_html(page):
    from tigerfish.ui.style import esc
    text_layer = has_text_layer(page)
    body = []
    for r in page["rows"]:
        if text_layer:
            check = "yes" if r["in_text_layer"] else "<b>no</b>"
        else:
            check = "<span class='tf-ev-label'>no text layer</span>"
        body.append(f"<tr><td>{esc(r['read'])}</td><td>{esc(', '.join(r['values']))}</td>"
                    f"<td>{check}</td></tr>")
    return ("<table class='tf-table'><tr><th>Row as read by Super-VL</th><th>Values</th>"
            "<th>In text layer?</th></tr>" + "".join(body) + "</table>")


def stat_html(label, value, sub):
    return (f"<div class='tf-stat'><div class='tf-stat-label'>{label}</div>"
            f"<div class='tf-stat-value'>{value}</div><div class='tf-stat-note'>{sub}</div></div>")


def render(report_id):
    import streamlit as st
    from tigerfish.ui.style import esc
    st.markdown("#### How TigerFish reads scanned pages")
    saved = pages(report_id)
    if not saved:
        st.info("The scanned-page inspector has saved pages for the Great Nicobar EIA only.")
        return
    st.markdown("<div class='tf-message'>Many EIA pages are photographs or scans: a text extractor "
                "finds nothing on them. TigerFish sends those pages to Nemotron Super-VL, which reads "
                "the image. Below: the page on the left, the rows Super-VL read on the right.</div>",
                unsafe_allow_html=True)
    labels = [short_label(p) for p in saved]
    pick = st.radio("Page", labels, horizontal=True, label_visibility="collapsed")
    page = saved[labels.index(pick)]

    st.markdown(f"<div class='tf-card-title'>p.{page['page']}: {esc(page['title'])}</div>"
                f"<div class='tf-ev'><span class='tf-ev-label'>Why it matters:</span> "
                f"{esc(page['why'])}</div>", unsafe_allow_html=True)
    a, b = st.columns(2)
    a.markdown(stat_html("Text extraction", f"{page['text_layer']['chars']:,} characters",
                         "PyMuPDF, whitespace not counted"), unsafe_allow_html=True)
    b.markdown(stat_html("Super-VL", f"{len(page['rows'])} rows read",
                         f"{len(page['claims'])} values and statements"), unsafe_allow_html=True)
    st.markdown(f"<div class='tf-quote' style='margin:0.7rem 0'>{esc(note(page))}</div>",
                unsafe_allow_html=True)

    left, right = st.columns([1, 1.15])
    left.image(str(image_path(page)), caption=f"p.{page['page']} as sent to Super-VL (downscaled)",
               width="stretch")
    right.markdown(rows_html(page), unsafe_allow_html=True)
    st.caption(f"Model: {page['model']}. Rows are the lines Super-VL quoted, grouped; the full "
               f"reply is saved in results/inspector/{page['image'].rsplit('.', 1)[0]}.json.")
