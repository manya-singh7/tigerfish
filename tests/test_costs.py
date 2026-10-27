"""Cost per audit by triage mode: every number comes from results/eval.json (or llm.PRICES),
and the safe / no-triage totals match the evaluation's own extrapolation."""

import json
from pathlib import Path

import pytest

from tigerfish import llm
from tigerfish.ui import costs

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "results" / "eval.json"
pytestmark = pytest.mark.skipif(not EVAL.exists(), reason="no results/eval.json")


@pytest.fixture
def e():
    return json.loads(EVAL.read_text(encoding="utf-8"))


def test_matches_the_evaluations_own_totals(e):
    rows = {r["mode"]: r for r in costs.modes(e)}
    x = e["cost"]["extrapolation"]
    # eval.json stores per-unit costs rounded to 6 decimals, its totals from unrounded ones
    assert rows["Safe triage (default)"]["usd"] == pytest.approx(x["usd"], abs=0.01)
    assert rows["No triage"]["usd"] == pytest.approx(x["without_triage"]["usd"], abs=0.01)
    assert rows["Safe triage (default)"]["verdicts"] == x["verdicts"]
    assert rows["No triage"]["verdicts"] == x["without_triage"]["verdicts"]


def test_fast_triage_is_cheapest_and_never_keeps_more(e):
    rows = {r["mode"]: r for r in costs.modes(e)}
    safe, fast, none = rows["Safe triage (default)"], rows["Fast triage (quotes only)"], rows["No triage"]
    assert fast["usd"] < safe["usd"] and fast["usd"] < none["usd"]
    # safe triage saves money only when it drops pairs: safe - none = triage cost - verdicts saved
    x, u = e["cost"]["extrapolation"], e["cost"]["extrapolation"]["per_unit"]
    cand = x["candidates"]
    assert safe["usd"] - none["usd"] == pytest.approx(
        cand * u["triage_usd_per_candidate"] - cand * (1 - u["triage_pass_rate"]) * u["verdict_usd"])
    assert fast["recall"][0] <= safe["recall"][0] == safe["recall"][1]


def test_recall_comes_from_triage_validation(e):
    flagged = sum(1 for tv in (e["known"]["triage_validation"], e["planted"]["triage_validation"])
                  for r in tv["rows"] if r.get("ultra_grade") in ("RED", "ORANGE"))
    fast_missed = e["known"]["triage_validation"]["fast_violations"] + e["planted"]["triage_validation"]["fast_violations"]
    rc = costs.recall(e)
    assert rc["safe"] == (flagged, flagged) and rc["fast"] == (flagged - fast_missed, flagged)


def test_ultra_every_page_uses_measured_tokens_and_ultra_prices(e):
    row = next(r for r in costs.modes(e) if r["mode"].startswith("Ultra"))
    x, u = e["cost"]["extrapolation"], e["cost"]["extrapolation"]["per_unit"]
    t = next(r for r in e["cost"]["rows"] if r["stage"].startswith("Claim extraction, text pages"))
    v = next(r for r in e["cost"]["rows"] if r["stage"].startswith("Claim extraction, vision pages"))
    pin, pout = llm.PRICES[llm.ULTRA]
    expected = (x["pages_text"] * (t["in_tokens"] / 8 * pin + t["out_tokens"] / 8 * pout) / 1e6
                + x["pages_vision"] * (v["in_tokens"] / 2 * pin + v["out_tokens"] / 2 * pout) / 1e6
                + x["candidates"] * u["verdict_usd"])
    assert row["usd"] == pytest.approx(expected)
    assert row["recall"] is None and row["recall_note"] == "not measured"
    assert "/ 1M" in row["formula"] and f"${pin}" in row["formula"]


def test_figure_labels_cost_and_recall(e):
    fig = costs.figure(costs.modes(e))
    labels = list(fig.data[0].text)
    kept, of = costs.recall(e)["safe"]
    assert any(f"recall {kept} of {of}" in s for s in labels)
    assert any("recall not measured" in s for s in labels)
    assert all(s.startswith("$") for s in labels)
