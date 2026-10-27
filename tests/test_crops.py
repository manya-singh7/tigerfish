"""Smoking-gun crops: find the yellow highlight on a page image and crop to it (+ margin)."""

import io

from PIL import Image, ImageDraw

from tigerfish.ui import crops, data


def page_with_highlight(box=(100, 300, 500, 340), size=(900, 1200)):
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=(255, 240, 0))                    # highlight
    d.text((110, 310), "Coral reef exists", fill=(0, 0, 0))  # text on it
    d.text((100, 800), "other text, not highlighted", fill=(0, 0, 0))
    return img


def test_box_is_highlight_plus_margin(tmp_path):
    img = page_with_highlight()
    left, top, right, bottom = crops.highlight_box(img, margin=20, side=30)
    assert (left, top, bottom) == (70, 280, 361)
    assert right == int(900 * crops.TEXT_COLUMN[1])          # widened to the text column


def test_box_is_clipped_to_the_page():
    img = page_with_highlight(box=(0, 0, 50, 20))
    assert crops.highlight_box(img, margin=40, side=40)[:2] == (0, 0)


def test_no_highlight_means_no_crop(tmp_path):
    p = tmp_path / "plain.png"
    Image.new("RGB", (300, 300), "white").save(p)
    assert crops.crop(p) is None


def test_crop_returns_png_of_the_highlighted_lines(tmp_path):
    p = tmp_path / "x_p0978.png"
    page_with_highlight().save(p)
    out = Image.open(io.BytesIO(crops.crop(p)))
    assert out.size == (int(900 * crops.TEXT_COLUMN[1]) - (100 - crops.SIDE_MARGIN_PX),
                        41 + 2 * crops.MARGIN_PX)


def test_short_and_long_highlights_share_one_scale(tmp_path):
    short, long_ = tmp_path / "a_p0001.png", tmp_path / "b_p0002.png"
    page_with_highlight(box=(500, 300, 700, 330)).save(short)
    page_with_highlight(box=(100, 300, 800, 330)).save(long_)
    w1 = Image.open(io.BytesIO(crops.crop(short))).width
    w2 = Image.open(io.BytesIO(crops.crop(long_))).width
    assert abs(w1 - w2) <= 2 * crops.SIDE_MARGIN_PX


def test_every_contradiction_page_in_results_has_a_crop():
    for r in data.reports():
        for f in data.load(r["id"])["findings"]:
            if crops.wants_crops(f):
                for rel in f["images"]:
                    png = crops.crop(data.image_path(rel))
                    assert png, rel
                    with Image.open(io.BytesIO(png)) as c, Image.open(data.image_path(rel)) as full:
                        assert c.height < full.height / 3, rel     # zoomed, not the whole page


def test_tall_highlights_are_capped_where_most_highlight_is():
    img = page_with_highlight(box=(100, 100, 800, 130))                 # one line at the top
    ImageDraw.Draw(img).rectangle((100, 700, 800, 1000), fill=(255, 240, 0))   # a tall block
    left, top, right, bottom = crops.highlight_box(img)
    assert bottom - top == int(1200 * crops.MAX_HEIGHT)
    assert top <= 700 and bottom >= 1001 and top > 130            # the whole block, not the top line
