"""Live contradiction check on the 10 known-issue pages. Skip offline with:  pytest -m "not live"

Uses the claims ledger and cached Ultra verdicts from
  python scripts/check_contradictions.py data/eias/great_nicobar_2021_draft_eia.pdf --pages ...
so a re-run costs nothing. Uncached, the full run costs about $0.25.

Hard test: the negative control gn-neg-001 (1045 vs 910 sq km, explained by the tsunami)
must NOT be flagged, both in the normal pipeline and when sent to Ultra directly.
Everything else is reported, not asserted. Run with -s to see the tables.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_contradictions  # noqa: E402
from tigerfish import claims  # noqa: E402

PDF = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"
PAGES = {234, 392, 444, 751, 818, 851, 940, 978, 1141, 1168}

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not PDF.exists(), reason="EIA PDF not present (kept locally)"),
    pytest.mark.skipif(not claims.ledger_path(PDF.stem).exists(),
                       reason="no claims ledger; run scripts/extract_claims.py first"),
]


@pytest.fixture(scope="module")
def result():
    out = check_contradictions.run(PDF, PAGES)
    print("\n\nissue       expected        found  grade   ok")
    for r in out["evaluation"]:
        print(f"{r['id']:11} {'/'.join(r['expected']):15} {'yes' if r['found'] else 'no':6} "
              f"{str(r['grade']):7} {'PASS' if r['ok'] else 'FAIL'}")
    matched = {r["finding_id"] for r in out["evaluation"] if r["finding_id"]}
    others = [f for f in out["findings"] if f["id"] not in matched and f["grade"] != "NONE"]
    print(f"\nOther flags for review by hand: {len(others)}")
    for f in others:
        print(f"  {f['id']} {f['grade']} pages {f['pages']}: {f['reason']}")
    return out


def test_negative_control_not_flagged(result):
    row = next(r for r in result["evaluation"] if r["id"] == "gn-neg-001")
    assert row["ok"], f"gn-neg-001 flagged as {row['grade']} ({row['finding_id']})"


def test_negative_control_pair_judged_explained(result):
    """The 1045-vs-910 quotes sent to Ultra directly must come back NONE."""
    assert result["control_findings"], "negative-control pair was not checked"
    for f in result["control_findings"]:
        assert f["grade"] == "NONE", f"control pair graded {f['grade']}: {f['reason']}"


def test_report_known_issues(result):
    """Report only: per-issue outcome is printed above (run with -s)."""
    assert result["evaluation"]
