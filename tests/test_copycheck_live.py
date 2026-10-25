"""Live copy-paste check (Tavily + Nebius) on the 10 known-issue pages plus the
Table 3.16 species source hunt. Report only: prints results, asserts nothing.

Skip offline with:  pytest -m "not live"      Run with -s to see the output.
Tavily responses are cached in cache/tavily/, so after
  python scripts/check_copypaste.py ... --table data/demo/indira_point_table_3_16_mammals.png
this test uses no Tavily credits.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_copypaste  # noqa: E402
from tigerfish import claims  # noqa: E402

PDF = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"
TABLE = ROOT / "data" / "demo" / "indira_point_table_3_16_mammals.png"
PAGES = {234, 392, 444, 751, 818, 851, 940, 978, 1141, 1168}

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not PDF.exists(), reason="EIA PDF not present (kept locally)"),
    pytest.mark.skipif(not claims.ledger_path(PDF.stem).exists(),
                       reason="no claims ledger; run scripts/extract_claims.py first"),
]


def test_report_copy_paste_and_species_source():
    out = check_copypaste.run(PDF, PAGES, table=TABLE if TABLE.exists() else None)
    print(f"\n\nPassages checked: {len(out['results'])}")
    for r in out["results"]:
        flagged = [h for h in r["hits"] if h["grade"] in ("RED", "ORANGE")]
        print(f"  p.{r['page']:<5} results={r['results']} flagged={len(flagged)}  \"{r['phrase']}\"")
        for h in flagged:
            print(f"      {h['grade']}: {h['message']} (run {h['longest_run']}, 8-gram {h['ngram']:.0%})")
    if out["names"]:
        print(f"\nSpecies source hunt ({len(out['names'])} names):")
        for m in out["hunt"][:8]:
            print(f"  {len(m['names'])}/{len(out['names'])}  {m['url']}"
                  f"{'  [same project]' if m['same_project'] else ''}")
    print(f"\nTavily credits this run: {out['credits']} (cached calls: {out['tavily_cached']}); "
          f"Nebius ${out['nebius_cost']:.4f}; stopped: {out['stopped']}")
