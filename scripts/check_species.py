"""Quick manual species plausibility check against GBIF.

Usage: python scripts/check_species.py "Hydrocynus vittatus" 6.75 93.83
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import species  # noqa: E402

if len(sys.argv) != 4:
    sys.exit(__doc__)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

name, lat, lon = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
r = species.check_species(name, lat, lon)

print(f"{r['name']}  ->  GBIF: {r['matched_name']} (key {r['gbif_key']}), class: {r['class_name']}")
print(f"grade:    {r['grade'] or 'None (plausible, not a finding)'}")
rows = [
    ("local", "local_count", f"this species within {species.LOCAL_KM} km"),
    ("regional", "regional_count", f"this species within {species.REGIONAL_KM} km"),
    ("effort", "effort_count", f"all {r['class_name']} within {species.LOCAL_KM} km"),
    ("far", "far_count", f"this species within {species.FAR_KM} km"),
    ("global", "global_count", "this species worldwide"),
]
for label, field, note in rows:
    value = "-" if r[field] is None else f"{r[field]:,}"
    print(f"{label + ':':9} {value:>9}   {note}")
print(f"evidence: {r['evidence']}")
for label, url in r["gbif_links"].items():
    print(f"  {label}: {url}")
