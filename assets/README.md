# TigerFish brand assets

Everything here comes from `scripts/build_brand.py`. Change the palette or shapes
there and run `python scripts/build_brand.py` instead of editing the SVGs by hand.
You need `pip install resvg-py` (cairosvg needs a Cairo DLL that Windows doesn't
have). The script also writes PNG previews to `docs/screenshots/brand/`.

**Wired into the app:** `favicon-64.png` is the page icon and `logo.svg` / `logo_dark.svg`
(with `logo_icon.svg`) the top-bar logo (`app.py`); the lockup heads the Home page and
`how_it_works.svg` the How it works page (`tigerfish/ui/pages.py`); the theme is in
`.streamlit/config.toml`. Screenshots of every page: `docs/screenshots/ui/`.

**`logo_icon.svg`**: the square icon. It's an original design: a tiger-striped fish
whose eye is a magnifying lens ("sees clearly in murky waters"), with bubbles and
faint light rays, on a deep-water rounded tile. The tile has its own dark background
and a thin teal rim, so one version works on both light and dark pages. The single
amber glint on the lens is the only warm colour.

**`favicon-32.png`, `favicon-64.png`, `favicon-180.png`, `favicon-512.png`**: the icon
exported at those sizes. Use 32/64 for the browser tab, 180 as an Apple touch icon,
and 512 for social cards or app stores.

**`logo.svg`**: the icon plus the wordmark "Tiger**Fish**" and the tagline "sees
clearly in murky waters", for light backgrounds ("Tiger" in deep teal, "Fish" in reef
teal). The text uses system fonts (Segoe UI, then Inter, Helvetica or Arial), so it
can look slightly different on each machine. If it must look the same everywhere,
convert the text to outlines first.

**`logo_dark.svg`**: the same lockup for dark backgrounds, with near-white "Tiger",
bright teal "Fish" and a lighter tagline. Use `logo.svg` on light pages and this one
on dark pages.

**`how_it_works.svg`**: the pipeline as one vertical column, 720 units wide, so it
stays readable on a phone (see `docs/screenshots/brand/how_it_works_phone.png`). The
steps are: PDF → read pages (Lightning / Super-VL) → extract claims (Lightning) →
pair → triage (Lightning) → verdicts (Ultra). Next comes a dashed band of side checks
(GBIF species, Tavily web evidence and paper trail, NABET accreditation, ToR
promises), then flags with quotes and page numbers (highlighted in amber) → human
review → letter / RTI pack. Pills on the right of each step name the model that
runs it.

**`theme_proposal.toml`**: a proposed Streamlit theme with separate `[theme.light]`
and `[theme.dark]` sections in the logo palette. The contrast ratios for each pair
are listed in the file's comments, and all of them pass WCAG AA. I checked every key
against Streamlit 1.66.1's config options. `.streamlit/config.toml` now carries the same
sections; change both together.

## How it is wired in (Streamlit 1.66.1)

```python
import streamlit as st

# Must be the first Streamlit call in app.py.
st.set_page_config(
    page_title="TigerFish",
    page_icon="assets/favicon-64.png",
    layout="wide",
)

# Sidebar / top-left logo. The full lockup shows when the sidebar is open and the
# square icon when it is collapsed. The light/dark pick reads the user's theme.
is_dark = st.context.theme.type == "dark"
st.logo(
    "assets/logo_dark.svg" if is_dark else "assets/logo.svg",
    icon_image="assets/logo_icon.svg",
    size="large",
)

# "How it works" section on the home screen.
st.image(
    "assets/how_it_works.svg",
    width="stretch",
    alt="TigerFish pipeline: PDF to flags, human review and letter",
)
# Or, for a fixed width that suits phones and desktops:
# st.image("assets/how_it_works.svg", width=720)
```

`st.context.theme.type` can be wrong for one rerun right after the page loads or
after the user switches theme (Streamlit says so in its docs). The icon tile looks
fine either way, so the worst case is a wordmark in the wrong colour for one rerun.
If even that is too much, use `st.logo("assets/logo_icon.svg")` alone.
