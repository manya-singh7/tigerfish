"""Build the TigerFish brand assets from the one chosen logo, assets/tigerfish_icon_source.png.

Run:  python scripts/build_brand.py
Needs (requirements-dev.txt): pillow, vtracer, fonttools, brotli, uharfbuzz, resvg-py

Writes:
  assets/tigerfish_icon.png          the source with its white corners made transparent
  assets/favicon-16/32/64/180/512.png, assets/favicon.ico
  assets/logo_icon.svg               two-colour SVG traced from the PNG (checked against it)
  assets/wordmark.svg, wordmark_dark.svg   icon + "TigerFish" in Newsreader, as outlines
  assets/how_it_works.svg            the pipeline diagram (also drawn inline by the app)
  docs/screenshots/brand/*.png       previews: favicon at 16/32 px on light and dark tabs,
                                     wordmarks, traced-vs-PNG comparison
The palette is docs/DESIGN.md's; the diagram shares it.
"""

from __future__ import annotations

import io
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tigerfish.ui.diagram import diagram_svg  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PREVIEW = ROOT / "docs" / "screenshots" / "brand"
SOURCE = ASSETS / "tigerfish_icon_source.png"
FONTS = ROOT / "static" / "fonts"

# Sampled from the source PNG (most common pixels of the tile and the fish).
TEAL = "#0D4242"
CREAM = "#F5EEDF"
# docs/DESIGN.md
INK = "#17302F"
PAPER = "#F2ECDF"
PAPER_DARK = "#121A19"
TEXT_DARK = "#ECE5D6"
MUTED = "#5C6564"


def rgb(hex_):
    return tuple(int(hex_[i:i + 2], 16) for i in (1, 3, 5))


# ------------------------------------------------------------------ icon ---

def transparent_icon(src: Image.Image) -> Image.Image:
    """The source with the light corners outside the rounded square made transparent.

    The corners are flood-filled from each image corner over light pixels; along the
    tile's anti-aliased edge each pixel's alpha is how much teal it holds, and its colour
    becomes pure teal, so the edge stays smooth on any background."""
    a = np.asarray(src.convert("RGB")).astype(np.float32)
    h, w, _ = a.shape
    light = a.mean(axis=2) > 120
    outside = np.zeros((h, w), bool)
    stack = [(0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)]
    while stack:                                   # 4-connected flood fill over light pixels
        y, x = stack.pop()
        if outside[y, x] or not light[y, x]:
            continue
        outside[y, x] = True
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not outside[ny, nx]:
                stack.append((ny, nx))
    # The anti-aliased band: outside pixels plus a 3 px ring around them.
    band = outside.copy()
    for _ in range(3):
        b = band.copy()
        b[1:, :] |= band[:-1, :]
        b[:-1, :] |= band[1:, :]
        b[:, 1:] |= band[:, :-1]
        b[:, :-1] |= band[:, 1:]
        band = b
    teal = np.array(rgb(TEAL), np.float32)
    white = 255.0
    cover = np.clip((white - a.mean(axis=2)) / (white - teal.mean()), 0, 1)
    out = np.dstack([a, np.full((h, w), 255, np.float32)])
    out[band, :3] = teal
    out[band, 3] = cover[band] * 255
    return Image.fromarray(out.round().astype(np.uint8), "RGBA")


def favicons(icon: Image.Image):
    for px in (16, 32, 64, 180, 512):
        icon.resize((px, px), Image.LANCZOS).save(ASSETS / f"favicon-{px}.png", optimize=True)
    icon.resize((256, 256), Image.LANCZOS).save(ASSETS / "favicon.ico",
                                                 sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])


def trace_svg(icon: Image.Image) -> str:
    """Two colours: the rounded teal square as a <rect> and the cream fish traced with vtracer
    (binary mode on a fish mask), so the SVG has exactly TEAL and CREAM."""
    import vtracer

    a = np.asarray(icon).astype(np.int32)
    cream, teal = np.array(rgb(CREAM)), np.array(rgb(TEAL))
    d_cream = np.abs(a[..., :3] - cream).sum(axis=2)
    d_teal = np.abs(a[..., :3] - teal).sum(axis=2)
    fish = (d_cream < d_teal) & (a[..., 3] > 128)
    mask = Image.fromarray(np.where(fish, 0, 255).astype(np.uint8), "L").convert("RGB")
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "mask.png", Path(tmp) / "mask.svg"
        mask.save(src)
        vtracer.convert_image_to_svg_py(str(src), str(out), colormode="binary", mode="spline",
                                        filter_speckle=8, corner_threshold=60,
                                        length_threshold=4.0, splice_threshold=45,
                                        path_precision=2)
        traced = out.read_text()
    paths = []
    for tag in re.findall(r"<path[^>]*/>", traced):
        t = re.search(r'transform="([^"]*)"', tag)
        paths.append((re.search(r' d="([^"]+)"', tag).group(1), t.group(1) if t else ""))
    w, h = icon.size
    body = "".join(f'<path d="{d}"' + (f' transform="{t}"' if t else "") + "/>" for d, t in paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="512" '
            f'height="512" role="img" aria-label="TigerFish">'
            f'<rect width="{w}" height="{h}" rx="{RADIUS}" fill="{TEAL}"/>'
            f'<g fill="{CREAM}" fill-rule="evenodd">{body}</g></svg>\n')


RADIUS = 210     # the tile's corner radius in the 1254 px source (measured along its edges)


def render(svg: str, width: int, background: str | None = None) -> Image.Image:
    import resvg_py
    kw = {"svg_string": svg, "width": width}
    if background:
        kw["background"] = background
    return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(**kw)))).convert("RGBA")


def compare(svg: str, icon: Image.Image) -> dict:
    """How closely the traced SVG matches the PNG: share of pixels whose class (transparent,
    teal, cream) agrees, and the colours used in the SVG."""
    w = icon.size[0]
    r = np.asarray(render(svg, w)).astype(np.int32)
    p = np.asarray(icon).astype(np.int32)

    def classes(x):
        cream = np.abs(x[..., :3] - np.array(rgb(CREAM))).sum(axis=2)
        teal = np.abs(x[..., :3] - np.array(rgb(TEAL))).sum(axis=2)
        c = np.where(cream < teal, 2, 1)
        return np.where(x[..., 3] < 128, 0, c)

    agree = float((classes(r) == classes(p)).mean())
    colours = sorted(set(re.findall(r"#[0-9A-Fa-f]{6}", svg)))
    return {"agree": agree, "colours": colours}


# -------------------------------------------------------------- wordmark ---

def newsreader_outline(text: str, size: float, weight=560, opsz=72):
    """(svg path d, advance width) of text set in Newsreader at this weight/optical size,
    shaped with HarfBuzz and converted to outlines (no font needed to display it)."""
    import uharfbuzz as hb
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    font = TTFont(FONTS / "Newsreader-normal-400-600-latin.woff2")
    font.flavor = None
    inst = instancer.instantiateVariableFont(font, {"wght": weight, "opsz": opsz})
    buf = io.BytesIO()
    inst.save(buf)
    blob = hb.Blob(buf.getvalue())
    hbfont = hb.Font(hb.Face(blob))
    hbuf = hb.Buffer()
    hbuf.add_str(text)
    hbuf.guess_segment_properties()
    hb.shape(hbfont, hbuf, {"kern": True, "liga": True})
    upm = inst["head"].unitsPerEm
    scale = size / upm
    glyphs = inst.getGlyphSet()
    order = inst.getGlyphOrder()
    pen = SVGPathPen(glyphs)
    x = 0
    for info, pos in zip(hbuf.glyph_infos, hbuf.glyph_positions):
        name = order[info.codepoint]
        t = TransformPen(pen, (scale, 0, 0, -scale, (x + pos.x_offset) * scale, 0))
        glyphs[name].draw(t)
        x += pos.x_advance
    cap = inst["OS/2"].sCapHeight * scale
    return pen.getCommands(), x * scale, cap


def wordmark_svg(icon_svg: str, dark: bool) -> str:
    """Icon tile + "TigerFish", baseline aligned to the tile's lower third."""
    h = 120
    d, width, cap = newsreader_outline("TigerFish", 92)
    gap = 26
    inner = icon_svg.split(">", 1)[1].rsplit("</svg>", 1)[0]
    vb = re.search(r'viewBox="([^"]+)"', icon_svg).group(1)
    total = h + gap + width + 6
    base = h / 2 + cap / 2
    colour = TEXT_DARK if dark else TEAL
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total:.1f} {h}" '
            f'width="{total:.1f}" height="{h}" role="img" aria-label="TigerFish">'
            f'<title>TigerFish</title>'
            f'<svg x="0" y="0" width="{h}" height="{h}" viewBox="{vb}">{inner}</svg>'
            f'<path transform="translate({h + gap} {base:.1f})" fill="{colour}" d="{d}"/></svg>\n')


# -------------------------------------------------------------- previews ---

def tab_preview(icon: Image.Image) -> Image.Image:
    """The favicon at 16 and 32 px (1:1 and enlarged 4x, pixelated) on a light and a dark
    browser-tab background."""
    scale = 4
    rows = [("light tab", "#E9E7E3", "#202124"), ("dark tab", "#35363A", "#E8EAED")]
    W_, H_ = 760, 2 * 190
    sheet = Image.new("RGB", (W_, H_), "#FFFFFF")
    d = ImageDraw.Draw(sheet)
    try:
        f = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        f = ImageFont.load_default()
    for r, (name, bg, fg) in enumerate(rows):
        y0 = r * 190
        d.rectangle([0, y0, W_, y0 + 190], fill=bg)
        d.text((20, y0 + 12), name, fill=fg, font=f)
        x = 20
        for px in (16, 32):
            small = Image.open(ASSETS / f"favicon-{px}.png").convert("RGBA")
            # a mock tab: icon at 1:1 next to the page title
            d.rounded_rectangle([x, y0 + 40, x + 230, y0 + 40 + max(32, px + 12)], 6,
                                fill=bg, outline=fg)
            sheet.paste(small, (x + 8, y0 + 40 + (max(32, px + 12) - px) // 2), small)
            d.text((x + px + 18, y0 + 40 + max(32, px + 12) // 2 - 8),
                   f"TigerFish: built for... ({px}px)", fill=fg, font=f)
            big = small.resize((px * scale, px * scale), Image.NEAREST)
            sheet.paste(big, (x + 250, y0 + 40), big)
            x += 250 + px * scale + 40
    return sheet


def main():
    if not SOURCE.exists():
        sys.exit(f"missing {SOURCE}: the brand step is skipped")
    PREVIEW.mkdir(parents=True, exist_ok=True)
    icon = transparent_icon(Image.open(SOURCE))
    icon.save(ASSETS / "tigerfish_icon.png", optimize=True)
    favicons(icon)
    svg = trace_svg(icon)
    (ASSETS / "logo_icon.svg").write_text(svg, encoding="utf-8")
    match = compare(svg, icon)
    print(f"traced SVG: {match['agree']:.4%} of pixels agree with the PNG; colours {match['colours']}")
    assert match["agree"] > 0.99 and match["colours"] == sorted([TEAL, CREAM]), match
    for dark, name in ((False, "wordmark.svg"), (True, "wordmark_dark.svg")):
        (ASSETS / name).write_text(wordmark_svg(svg, dark), encoding="utf-8")
    (ASSETS / "how_it_works.svg").write_text(diagram_svg(standalone=True), encoding="utf-8")

    for old in PREVIEW.glob("*.png"):
        old.unlink()
    tab_preview(icon).save(PREVIEW / "favicon_tabs.png")
    for name, bg in (("wordmark", PAPER), ("wordmark_dark", PAPER_DARK)):
        render((ASSETS / f"{name}.svg").read_text(), 900, bg).save(PREVIEW / f"{name}.png")
    side = Image.new("RGBA", (1040, 520), PAPER)
    side.paste(icon.resize((500, 500), Image.LANCZOS), (10, 10), icon.resize((500, 500), Image.LANCZOS))
    traced = render(svg, 500)
    side.paste(traced, (530, 10), traced)
    side.save(PREVIEW / "icon_png_vs_traced_svg.png")
    render(diagram_svg(standalone=True), 720).save(PREVIEW / "how_it_works.png")
    print("wrote", sorted(p.name for p in ASSETS.iterdir() if p.suffix in (".png", ".svg", ".ico")))


if __name__ == "__main__":
    main()
