"""Save GBIF country counts for every flagged species and write the standalone
"impossible species" map for the video.

    python scripts/species_map.py            # uses cached GBIF calls; new ones are free

Writes:
  data/gbif_country_facets.json                   replay data for the app's map
  docs/figures/impossible_species_<report>.html   interactive standalone figure
  docs/figures/impossible_species_<report>.png    static frame (needs kaleido + Chrome)
Reads the saved reports in results/ only; no model or Tavily calls.
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tigerfish.ui import data, species_map  # noqa: E402
from tigerfish.ui.investigate import REPORTS  # noqa: E402

FIGURES = ROOT / "docs" / "figures"


def main():
    facets = species_map.load_facets()
    FIGURES.mkdir(parents=True, exist_ok=True)
    for r in data.reports():
        report = data.load(r["id"])
        site = (REPORTS.get(r["id"]) or (None, None))[1]
        found = species_map.flagged_species(report, site)
        if not found:
            continue
        for s in found:
            facets[str(s["taxon_key"])] = {**species_map.fetch_facets(s["taxon_key"]),
                                           "species": s["accepted"], "fetched": date.today().isoformat()}
        title = f"{report['title']}: flagged species and where GBIF records them"
        fig = species_map.figure(found, facets, title=title, height=640)
        html = FIGURES / f"impossible_species_{r['id']}.html"
        fig.write_html(html, include_plotlyjs="cdn")
        print("wrote", html.relative_to(ROOT))
        try:
            png = html.with_suffix(".png")
            fig.write_image(png, width=1600, height=900, scale=1)
            print("wrote", png.relative_to(ROOT))
        except Exception as e:          # kaleido or Chrome missing: the HTML is enough
            print("PNG skipped:", e)
    species_map.FACETS_FILE.write_text(json.dumps(facets, indent=1, sort_keys=True), encoding="utf-8")
    print("wrote", species_map.FACETS_FILE.relative_to(ROOT), f"({len(facets)} species)")


if __name__ == "__main__":
    main()
