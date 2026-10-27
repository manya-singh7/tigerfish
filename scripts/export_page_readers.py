"""Which model read each page during claim extraction, for the app's model badges.

Reads the cached claims ledger (no API calls) and writes results/page_readers_<report>.json:
{"report_id", "source", "super_vl": [pages], "lightning": [pages]}. A page read by
Super-VL (scanned page or table) is listed there only; pages with no model claims are left out.

  python scripts/export_page_readers.py [--ledger cache/claims/great_nicobar_2021_draft_eia/claims.jsonl]
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_ID = "great_nicobar_2021_draft"
LEDGER = ROOT / "cache" / "claims" / "great_nicobar_2021_draft_eia" / "claims.jsonl"
SUPER_VL = "nvidia/Nemotron-3.5-Super-VL"
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"


def page_readers(claims):
    """{"super_vl": [...], "lightning": [...]} from claims with a "page" and a "model"."""
    vision, text = set(), set()
    for c in claims:
        if c.get("model") == SUPER_VL:
            vision.add(c["page"])
        elif c.get("model") == LIGHTNING:
            text.add(c["page"])
    return {"super_vl": sorted(vision), "lightning": sorted(text - vision)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    args = ap.parse_args()
    claims = [json.loads(line) for line in args.ledger.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    out = {"report_id": REPORT_ID, "source": "claims ledger (cached claim extraction)",
           **page_readers(claims)}
    path = ROOT / "results" / f"page_readers_{REPORT_ID}.json"
    lines = [f" {json.dumps(k)}: {json.dumps(v)}" for k, v in out.items()]   # one line per key
    path.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    print(f"{path.name}: {len(out['super_vl'])} Super-VL pages, {len(out['lightning'])} Lightning pages")


if __name__ == "__main__":
    main()
