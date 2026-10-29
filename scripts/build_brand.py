"""Build TigerFish brand assets: SVG logos, diagram, PNG exports and previews.

Run:  python scripts/build_brand.py
Needs: pip install resvg-py   (pure wheel; cairosvg needs a Cairo DLL on Windows)

Writes assets/*.svg, assets/*.png and docs/screenshots/brand/*.png.
Edit the palette or shapes here and re-run rather than hand-editing the SVGs.
"""

from __future__ import annotations

from pathlib import Path

import resvg_py

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PREVIEW = ROOT / "docs" / "screenshots" / "brand"

# Palette (deep water -> shallow water), shared with assets/theme_proposal.toml.
ABYSS = "#082A33"      # darkest: tile bottom, outlines
DEEP = "#0F4C57"       # tile top, wordmark on light
TEAL = "#0F5E5E"       # primary (light theme)
REEF = "#1FA39A"       # fish body, accents
SHALLOW = "#5FD4C6"    # highlights, "Fish" on dark
FOAM = "#E6F7F4"       # lens glass, text on dark
SAND = "#F2B544"       # single warm accent: the lens glint
INK = "#12303A"        # body text on light

FONT = "'Segoe UI', Inter, 'Helvetica Neue', Arial, sans-serif"


def fish_icon(tile: bool = True) -> str:
    """The icon's inner markup in a 512x512 box.

    A tiger-striped fish whose eye is a magnifying lens, on a deep-water tile.
    The tile makes the icon readable on both light and dark backgrounds.
    """
    tile_markup = f"""
  <defs>
    <linearGradient id="tf-water" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{DEEP}"/>
      <stop offset="1" stop-color="{ABYSS}"/>
    </linearGradient>
    <linearGradient id="tf-body" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{SHALLOW}"/>
      <stop offset="1" stop-color="{REEF}"/>
    </linearGradient>
    <clipPath id="tf-body-clip">
      <path d="M402 256 C352 156 222 150 162 256 C222 362 352 356 402 256 Z"/>
    </clipPath>
  </defs>
  <rect x="8" y="8" width="496" height="496" rx="112" fill="url(#tf-water)"
        stroke="{REEF}" stroke-opacity="0.55" stroke-width="6"/>
  <!-- light rays from the surface -->
  <path d="M150 8 L210 8 L120 504 L80 504 Z" fill="{FOAM}" opacity="0.05"/>
  <path d="M290 8 L320 8 L250 504 L225 504 Z" fill="{FOAM}" opacity="0.04"/>""" if tile else """
  <defs>
    <linearGradient id="tf-body" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3CC2B4"/>
      <stop offset="1" stop-color="#178A82"/>
    </linearGradient>
    <clipPath id="tf-body-clip">
      <path d="M402 256 C352 156 222 150 162 256 C222 362 352 356 402 256 Z"/>
    </clipPath>
  </defs>"""
    return f"""{tile_markup}
  <g transform="translate(256 258) scale(1.12) translate(-272 -250)">
    <!-- tail -->
    <path d="M176 256 L92 176 Q118 256 92 336 Z" fill="{SHALLOW}"
          stroke="{ABYSS}" stroke-width="10" stroke-linejoin="round"/>
    <!-- dorsal and belly fins -->
    <path d="M250 175 Q282 128 330 150 Q300 160 292 182 Z" fill="{SHALLOW}"
          stroke="{ABYSS}" stroke-width="8" stroke-linejoin="round"/>
    <path d="M262 334 Q284 368 318 360 Q300 348 298 330 Z" fill="{SHALLOW}"
          stroke="{ABYSS}" stroke-width="8" stroke-linejoin="round"/>
    <!-- body -->
    <path d="M402 256 C352 156 222 150 162 256 C222 362 352 356 402 256 Z"
          fill="url(#tf-body)"/>
    <!-- tiger stripes, clipped to the body -->
    <g clip-path="url(#tf-body-clip)" fill="none" stroke="{ABYSS}"
       stroke-width="15" stroke-linecap="round">
      <path d="M208 190 Q194 256 208 322"/>
      <path d="M248 172 Q232 256 248 340"/>
      <path d="M288 174 Q274 230 282 262"/>
    </g>
    <path d="M402 256 C352 156 222 150 162 256 C222 362 352 356 402 256 Z"
          fill="none" stroke="{ABYSS}" stroke-width="10" stroke-linejoin="round"/>
    <!-- magnifier handle -->
    <path d="M326 262 L296 296" stroke="{ABYSS}" stroke-width="16" stroke-linecap="round"/>
    <!-- lens eye -->
    <circle cx="346" cy="238" r="31" fill="{FOAM}" stroke="{ABYSS}" stroke-width="11"/>
    <circle cx="353" cy="238" r="10" fill="{ABYSS}"/>
    <path d="M330 224 A20 20 0 0 1 344 216" fill="none" stroke="{SAND}"
          stroke-width="6" stroke-linecap="round"/>
    <!-- bubbles -->
    <circle cx="430" cy="196" r="10" fill="none" stroke="{SHALLOW}" stroke-width="6"/>
    <circle cx="452" cy="160" r="6" fill="none" stroke="{SHALLOW}" stroke-width="5"/>
  </g>"""


def icon_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512"'
        ' role="img" aria-label="TigerFish">\n  <title>TigerFish</title>'
        f"{fish_icon()}\n</svg>\n"
    )


def logo_svg(dark: bool) -> str:
    tiger, fish = (FOAM, SHALLOW) if dark else (DEEP, REEF)
    tag = "#9FC9C3" if dark else "#3E6670"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 990 320" width="990" height="320" role="img" aria-label="TigerFish">
  <title>TigerFish</title>
  <svg x="24" y="24" width="272" height="272" viewBox="0 0 512 512">{fish_icon()}
  </svg>
  <text x="330" y="190" font-family="{FONT}" font-size="150" font-weight="700"
        letter-spacing="-3"><tspan fill="{tiger}">Tiger</tspan><tspan fill="{fish}">Fish</tspan></text>
  <text x="336" y="252" font-family="{FONT}" font-size="38" font-weight="500"
        fill="{tag}" letter-spacing="1">sees clearly in murky waters</text>
</svg>
"""


# ---------------------------------------------------------------- diagram ---

W = 720


def _box(y, h, title, lines, model=None, fill="#FFFFFF", stroke=REEF, x=32, w=W - 64):
    out = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="2.5"/>'
    ]
    ty = y + 40
    out.append(
        f'<text x="{x + 24}" y="{ty}" font-size="26" font-weight="700" fill="{INK}">{title}</text>'
    )
    if model:
        mw = 22 + 12.5 * len(model)
        out.append(
            f'<rect x="{x + w - 20 - mw}" y="{y + 16}" width="{mw}" height="34" rx="17" fill="{TEAL}"/>'
            f'<text x="{x + w - 20 - mw / 2}" y="{y + 40}" font-size="19" font-weight="700" '
            f'fill="#FFFFFF" text-anchor="middle">{model}</text>'
        )
    for i, line in enumerate(lines):
        out.append(
            f'<text x="{x + 24}" y="{ty + 34 + i * 30}" font-size="21" fill="#2E4F58">{line}</text>'
        )
    return "\n".join(out)


def _arrow(y1, y2, x=W / 2):
    return (
        f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2 - 12}" stroke="{TEAL}" stroke-width="4"/>'
        f'<path d="M{x - 11} {y2 - 16} L{x} {y2} L{x + 11} {y2 - 16} Z" fill="{TEAL}"/>'
    )


def diagram_svg() -> str:
    parts = []
    y = 150
    gap = 46
    stages = [
        ("1  EIA report (PDF)", ["Hundreds of pages: text, scans, tables, maps"], None, 108),
        ("2  Read every page", ["Text pages: text layer, read by Lightning",
                                "Scans, tables, maps: Super-VL looks at the image"],
         "Lightning · Super-VL", 140),
        ("3  Extract claims", ["Each factual statement, with its page number"],
         "Lightning", 108),
        ("4  Pair claims", ["Match statements on the same topic",
                            "that could disagree with each other"], None, 140),
        ("5  Triage", ["Quickly drop pairs that clearly agree"], "Lightning", 108),
        ("6  Verdicts", ["Read both passages in full; decide",
                         "contradiction or not, and say why"], "Ultra", 140),
    ]
    for i, (title, lines, model, h) in enumerate(stages):
        if i:
            parts.append(_arrow(y - gap, y))
        parts.append(_box(y, h, title, lines, model))
        y += h + gap

    # Side checks band
    band_y = y
    band_h = 352
    parts.append(
        f'<rect x="20" y="{band_y}" width="{W - 40}" height="{band_h}" rx="22" fill="#EAF6F4" '
        f'stroke="{REEF}" stroke-width="2" stroke-dasharray="8 7"/>'
        f'<text x="44" y="{band_y + 40}" font-size="24" font-weight="700" fill="{INK}">'
        f'Side checks (run in parallel with steps 2–6)</text>'
    )
    checks = [
        ("Species", ["GBIF records vs.", "species the report lists"]),
        ("Web evidence", ["Tavily search +", "paper trail (ToR, EC)"]),
        ("Accreditation", ["Is the consultant", "NABET-accredited?"]),
        ("ToR promises", ["Did the report do", "what the ToR asked?"]),
    ]
    cw, ch = (W - 40 - 24 * 3) // 2, 132
    for i, (t, lines) in enumerate(checks):
        cx = 44 + (i % 2) * (cw + 24)
        cy = band_y + 64 + (i // 2) * (ch + 20)
        parts.append(_box(cy, ch, t, lines, x=cx, w=cw))
    parts.append(_arrow(band_y - gap, band_y))
    y = band_y + band_h + gap

    outputs = [
        ("7  Flags", ["Each one quotes the report, with page", "numbers, so anyone can check it"],
         None, 140, "#FFF7E6", SAND),
        ("8  Human review", ["A person confirms or rejects every flag"], None, 108,
         "#FFFFFF", REEF),
        ("9  Letter / RTI pack", ["Objection letter and RTI requests,",
                                  "built only from confirmed flags"], None, 140,
         "#FFFFFF", REEF),
    ]
    for title, lines, model, h, fill, stroke in outputs:
        parts.append(_arrow(y - gap, y))
        parts.append(_box(y, h, title, lines, model, fill=fill, stroke=stroke))
        y += h + gap

    total = y - gap + 70
    legend = (
        f'<text x="32" y="{total - 34}" font-size="18" fill="#3E6670">'
        f'Models: Nemotron Lightning (fast reading), Super-VL (images),</text>'
        f'<text x="32" y="{total - 10}" font-size="18" fill="#3E6670">'
        f'Ultra (final verdicts). Nothing is sent until a person approves it.</text>'
    )
    header = f"""
<rect width="{W}" height="{total}" fill="#F7FBFA"/>
<svg x="32" y="30" width="84" height="84" viewBox="0 0 512 512">{fish_icon()}</svg>
<text x="134" y="68" font-size="34" font-weight="700" fill="{DEEP}">How TigerFish works</text>
<text x="134" y="102" font-size="21" fill="#3E6670">From an EIA report to checked, quotable flags</text>"""
    body = "\n".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {total}" width="{W}" '
        f'height="{total}" font-family="{FONT}" role="img" '
        f'aria-label="TigerFish pipeline diagram">\n<title>How TigerFish works</title>'
        f"{header}\n{body}\n{legend}\n</svg>\n"
    )


# ----------------------------------------------------------------- render ---

def render(svg: str, out: Path, width: int | None = None, background: str | None = None):
    kw = {"svg_string": svg}
    if width:
        kw["width"] = width
    if background:
        kw["background"] = background
    out.write_bytes(bytes(resvg_py.svg_to_bytes(**kw)))


def main():
    ASSETS.mkdir(exist_ok=True)
    PREVIEW.mkdir(parents=True, exist_ok=True)

    files = {
        "logo_icon.svg": icon_svg(),
        "logo.svg": logo_svg(dark=False),
        "logo_dark.svg": logo_svg(dark=True),
        "how_it_works.svg": diagram_svg(),
    }
    for name, svg in files.items():
        (ASSETS / name).write_text(svg, encoding="utf-8")

    for px in (32, 64, 180, 512):
        render(files["logo_icon.svg"], ASSETS / f"favicon-{px}.png", width=px)

    # Previews: each logo on light and dark, the favicon sizes, and the diagram.
    for bg_name, bg in (("light", "#FFFFFF"), ("dark", "#0E1117")):
        render(files["logo.svg"], PREVIEW / f"logo_on_{bg_name}.png", 990, bg)
        render(files["logo_dark.svg"], PREVIEW / f"logo_dark_on_{bg_name}.png", 990, bg)
        render(files["logo_icon.svg"], PREVIEW / f"icon_on_{bg_name}.png", 512, bg)
    render(files["how_it_works.svg"], PREVIEW / "how_it_works.png", 1440)
    render(files["how_it_works.svg"], PREVIEW / "how_it_works_phone.png", 390)

    sheet = _sizes_sheet(files["logo_icon.svg"])
    render(sheet, PREVIEW / "favicon_sizes.png", 1200)
    print("wrote", sorted(p.name for p in ASSETS.iterdir()))
    print("previews", sorted(p.name for p in PREVIEW.iterdir()))


def _sizes_sheet(icon: str) -> str:
    """Icon at 32/64/180 px on light and dark, to judge small-size legibility."""
    inner = icon.split(">", 1)[1].rsplit("</svg>", 1)[0]
    cells = []
    for row, bg in enumerate(("#FFFFFF", "#0E1117")):
        y0 = row * 300
        cells.append(f'<rect x="0" y="{y0}" width="600" height="300" fill="{bg}"/>')
        x = 30
        for s in (32, 64, 180):
            cells.append(
                f'<svg x="{x}" y="{y0 + (300 - s) / 2}" width="{s}" height="{s}" '
                f'viewBox="0 0 512 512">{inner}</svg>'
            )
            x += s + 60
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="600" height="600">'
        + "".join(cells)
        + "</svg>"
    )


if __name__ == "__main__":
    main()
