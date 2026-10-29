# TigerFish brand assets

One logo: `tigerfish_icon_source.png`, the chosen icon (a tiger-striped fish whose eye is a
magnifying lens, cream on the deep teal tile). Everything else here is built from it by
`scripts/build_brand.py` (palette and rules: `docs/DESIGN.md`). Re-run the script instead
of editing the outputs by hand. It needs pillow, vtracer, fonttools, brotli, uharfbuzz and
resvg-py (requirements-dev.txt; vtracer crashes on Python 3.14 for Windows, so run the
script with Python 3.12).

| File | What it is | Used by |
|---|---|---|
| `tigerfish_icon.png` | the source with its white corners made transparent (1254 px) | favicons, previews |
| `favicon-16/32/64/180/512.png`, `favicon.ico` | the icon at tab, touch-icon and social sizes | `favicon-64.png` is the page icon (`app.py`) |
| `logo_icon.svg` | two-colour SVG traced from the PNG (teal `#0D4242`, cream `#F5EEDF`); the build checks it against the PNG (99.7% of pixels agree) | the wordmarks |
| `wordmark.svg`, `wordmark_dark.svg` | icon + "TigerFish" in Newsreader 560, converted to outlines, for light and dark backgrounds | the top bar (`st.logo` in `app.py`) |
| `bg_pattern.svg` | the hand-drawn background tile: fish, reeds, mangrove roots, coral, ripples, a survey stake, a magnifier, a loose report page, a stamp; one ink colour | the app background (`tigerfish/ui/style.py` recolours it for light and dark) |
| `how_it_works.svg` | the pipeline diagram, standalone | the app draws the same diagram inline (`tigerfish/ui/diagram.py`) |

Previews in `docs/screenshots/brand/`: `favicon_tabs.png` (the favicon at 16 and 32 px on a
light and a dark tab), `wordmark.png`, `wordmark_dark.png`, `icon_png_vs_traced_svg.png`,
`how_it_works.png`.

Fonts are not here: they are self-hosted in `static/fonts/` (Streamlit serves only a folder
named `static/`) and declared in `.streamlit/config.toml`.
