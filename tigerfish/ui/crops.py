"""Zoomed "smoking gun" crops: cut each highlighted page image down to its highlighted lines.

The page images in results/pages/ are rendered with PyMuPDF highlight annotations, which
show as yellow (high red, high green, low blue) where they cover white paper. We find those
pixels, take their bounding box, add a margin and crop. No PDF needed, replay data only.
"""

import io

import numpy as np
from PIL import Image

CROP_CHECKS = ("contradiction", "recycled_figure")
MARGIN_PX = 28              # above and below the highlighted lines (page images are 110 dpi)
SIDE_MARGIN_PX = 60         # left and right, for a little more context
MIN_PIXELS = 30             # fewer yellow pixels than this: no highlight on the page
TEXT_COLUMN = (0.08, 0.92)  # crops span at least this share of the page width
MAX_HEIGHT = 0.3            # crops are at most this share of the page height


def highlight_mask(img):
    """Boolean array: True where the pixel is highlight yellow."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (r > 200) & (g > 190) & (b < 150) & (r - b > 90)


def highlight_box(img, margin=MARGIN_PX, side=SIDE_MARGIN_PX):
    """(left, top, right, bottom) of all highlighted pixels plus margin, clipped to the image;
    None when the page has no highlight.

    Highlights spread down a page (a shared page image with several quotes, or a long
    table) would give a crop as tall as the page: the crop is then capped at MAX_HEIGHT of
    the page, placed where it covers the most highlighted pixels."""
    mask = highlight_mask(img)
    if mask.sum() < MIN_PIXELS:
        return None
    rows, cols = np.where(mask.any(axis=1))[0], np.where(mask.any(axis=0))[0]
    w, h = img.size
    # At least the page's text column wide, so crops shown side by side share one scale.
    left = min(int(cols[0]) - side, int(w * TEXT_COLUMN[0]))
    right = max(int(cols[-1]) + 1 + side, int(w * TEXT_COLUMN[1]))
    top, bottom = max(0, int(rows[0]) - margin), min(h, int(rows[-1]) + 1 + margin)
    cap = int(h * MAX_HEIGHT)
    if bottom - top > cap:
        per_row = np.concatenate([[0], np.cumsum(mask.sum(axis=1)[top:bottom])])
        covered = per_row[cap:] - per_row[:-cap]      # highlighted pixels in each window
        top += int(np.argmax(covered))
        bottom = top + cap
    return max(0, left), top, min(w, right), bottom


def crop(path, margin=MARGIN_PX, side=SIDE_MARGIN_PX):
    """PNG bytes of the highlighted lines on one page image, or None without a highlight."""
    with Image.open(path) as img:
        box = highlight_box(img, margin, side)
        if box is None:
            return None
        buf = io.BytesIO()
        img.crop(box).save(buf, format="PNG")
        return buf.getvalue()


def wants_crops(finding):
    return finding["check"] in CROP_CHECKS and len(finding.get("images") or []) >= 1
