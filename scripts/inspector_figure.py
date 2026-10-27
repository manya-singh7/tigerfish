"""Render docs/figures/supervl_inspector.png (1920x1080, for the video): a scanned page next to
the rows Nemotron Super-VL read from it, with the text-extraction count.

    python scripts/inspector_figure.py [--page 901]

Reads results/inspector/ only (see scripts/build_inspector.py). No API calls.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tigerfish.ui import inspector  # noqa: E402
from tigerfish.ui.style import ACCENT, BORDER, MUTED, TEXT  # noqa: E402

OUT = ROOT / "docs" / "figures" / "supervl_inspector.png"
W, H, PAD = 1920, 1080, 56
BG, PANEL, ZEBRA = "#FFFFFF", "#F4F7F7", "#FAFBFB"
FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]
FONTS = {"regular": ["segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf"],
         "bold": ["segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"]}


def font(size, weight="regular"):
    for d in FONT_DIRS:
        for name in FONTS[weight]:
            if (d / name).exists():
                return ImageFont.truetype(str(d / name), size)
    return ImageFont.load_default(size)


def fit(draw, text, f, width):
    """text, shortened with an ellipsis to fit width pixels."""
    if draw.textlength(text, font=f) <= width:
        return text
    while text and draw.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(draw, text, f, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=f) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def stat(draw, x, y, w, label, value, sub, colour):
    draw.rounded_rectangle((x, y, x + w, y + 128), 12, fill=BG, outline=BORDER, width=2)
    draw.text((x + 24, y + 16), label.upper(), font=font(20, "bold"), fill=MUTED)
    draw.text((x + 24, y + 44), value, font=font(44, "bold"), fill=colour)
    draw.text((x + 24, y + 98), sub, font=font(19), fill=MUTED)


def render(page_no):
    page = next(p for p in inspector.pages("great_nicobar_2021_draft") if p["page"] == page_no)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # title
    d.text((PAD, 34), "How TigerFish reads scanned pages", font=font(46, "bold"), fill=TEXT)
    d.text((PAD, 96), f"Great Nicobar draft EIA (2021), p.{page['page']}: {page['title']}",
           font=font(24), fill=ACCENT)

    # left: the page image
    top = 150
    with Image.open(inspector.image_path(page)) as scan:
        scan = scan.convert("RGB")
        scale = (H - top - 70) / scan.height
        scan = scan.resize((round(scan.width * scale), round(scan.height * scale)), Image.LANCZOS)
    d.rectangle((PAD - 2, top - 2, PAD + scan.width + 1, top + scan.height + 1), outline=BORDER, width=2)
    img.paste(scan, (PAD, top))
    d.text((PAD, top + scan.height + 12), "The page image sent to Nemotron Super-VL",
           font=font(19), fill=MUTED)

    # right: counts, then the rows
    x0 = PAD + scan.width + 48
    width = W - PAD - x0
    half = (width - 24) // 2
    chars = page["text_layer"]["chars"]
    stat(d, x0, top, half, "Text extraction (PyMuPDF)", f"{chars:,} characters",
         "no usable text layer" if not inspector.has_text_layer(page) else "text layer present",
         "#9B1C1C" if not inspector.has_text_layer(page) else TEXT)
    stat(d, x0 + half + 24, top, half, "Nemotron Super-VL", f"{len(page['rows'])} rows read",
         f"{len(page['claims'])} values and statements", ACCENT)

    y = top + 128 + 30
    head, cell = font(19, "bold"), font(22)
    col2 = x0 + int(width * 0.64)
    d.rectangle((x0, y, x0 + width, y + 40), fill=PANEL)
    d.text((x0 + 14, y + 9), "ROW AS READ BY SUPER-VL", font=head, fill=MUTED)
    d.text((col2 + 14, y + 9), "VALUES", font=head, fill=MUTED)
    y += 40
    footer_y = H - 70 - 66
    row_h = min(44, (footer_y - y) // max(1, len(page["rows"])))
    for i, r in enumerate(page["rows"]):
        if y + row_h > footer_y:
            d.text((x0 + 14, y + 6), f"… {len(page['rows']) - i} more rows", font=cell, fill=MUTED)
            break
        if i % 2:
            d.rectangle((x0, y, x0 + width, y + row_h), fill=ZEBRA)
        ty = y + (row_h - 26) // 2
        d.text((x0 + 14, ty), fit(d, r["read"], cell, col2 - x0 - 28), font=cell, fill=TEXT)
        d.text((col2 + 14, ty), fit(d, ", ".join(r["values"]), cell, x0 + width - col2 - 28),
               font=cell, fill=TEXT)
        d.line((x0, y + row_h, x0 + width, y + row_h), fill=BORDER, width=1)
        y += row_h

    # footer note
    note = ("A text-only reader sees nothing on this page. Super-VL reads the image; the rows cannot be "
            "matched to a text layer, so TigerFish marks them unverified and shows the image beside them."
            if not inspector.has_text_layer(page) else inspector.note(page))
    for k, line in enumerate(wrap(d, note, font(21), width)):
        d.text((x0, footer_y + 14 + k * 28), line, font=font(21), fill=MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--page", type=int, default=901)
    render(ap.parse_args().page)
