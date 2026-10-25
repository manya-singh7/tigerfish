"""Planting (seeded, deterministic) and scoring for the evaluation, all offline."""

import json
import random

import pytest

from tigerfish import evaluation as ev


def claim(cid, page, value, unit, subject, ctype="count", verified=True):
    return {"id": cid, "page": page, "type": ctype, "value": value, "unit": unit,
            "subject": subject, "quote": f"{value} {unit} of {subject}", "verified": verified}


LEDGER = [
    claim("p1-01", 1, 330, "species", "fauna species recorded from GNI"),
    claim("p1-02", 1, 97, "species", "bird species recorded from GNI"),
    claim("p2-01", 2, 194, "ha", "reclaimed land for airport runway", "area"),
    claim("p2-02", 2, 4, "ha", "coral restoration", "area"),
    claim("p3-01", 3, 163, "km", "Indira Point to Sumatra", "distance"),
    claim("p3-02", 3, 45.91, "%", "work participation rate", "quantity"),
    claim("p4-01", 4, 648, "species", "flora species reported from Campbell Bay"),
    claim("p4-02", 4, 2, "ha", "maximum coral loss", "area"),                 # value < 4: skipped
    claim("p4-03", 4, 999, "species", "unverified count", verified=False),   # unverified: skipped
    claim("p5-01", 5, 1087, "number", "Nicobarese population"),
]
NARRATIVE = ("The island has dense forest. Rivers drain to the sea. The coast is rocky in "
             "places. Local communities fish near the shore. ") * 10


def pages(n=40):
    out = {i: {"page": i, "text": NARRATIVE, "needs_vision": False, "error": None}
           for i in range(1, n + 1)}
    out[7]["needs_vision"] = True                    # never a target
    out[8]["text"] = "1 2 3 4 5 " * 20 + NARRATIVE   # too many digits: never a target
    return out


# ---------- planting ----------

def test_same_seed_same_plants_and_pages():
    a = ev.make_plants(LEDGER, pages(), seed=7, n_planted=4, n_explained=2)
    b = ev.make_plants(LEDGER, pages(), seed=7, n_planted=4, n_explained=2)
    assert a == b
    assert ev.modified_pages(pages(), a, seed=7) == ev.modified_pages(pages(), b, seed=7)
    c = ev.make_plants(LEDGER, pages(), seed=8, n_planted=4, n_explained=2)
    assert [p["target_page"] for p in c] != [p["target_page"] for p in a]


def test_plants_go_to_other_pages_with_changed_values():
    plants = ev.make_plants(LEDGER, pages(), seed=1, n_planted=4, n_explained=2)
    assert [p["kind"] for p in plants] == ["planted"] * 4 + ["explained"] * 2
    targets = [p["target_page"] for p in plants]
    assert len(set(targets)) == len(targets)                       # one plant per page
    ledger_pages = {c["page"] for c in LEDGER}
    for p in plants:
        assert p["target_page"] not in ledger_pages and p["target_page"] not in (7, 8)
        ratio = p["new_value"] / p["source_value"]
        assert ratio == pytest.approx(0.5, abs=0.02) or ratio == pytest.approx(1.5, abs=0.02)
        assert p["source_id"] not in ("p4-02", "p4-03")             # small / unverified skipped


def test_explained_sentence_names_both_values():
    plants = ev.make_plants(LEDGER, pages(), seed=1, n_planted=4, n_explained=2)
    for p in plants:
        if p["kind"] == "explained":
            assert "revised from" in p["sentence"] and "after the 2021 survey" in p["sentence"]
            assert ev.fmt_value(p["source_value"]) in p["sentence"]
        assert ev.fmt_value(p["new_value"]) in p["sentence"]


def test_insert_sentence_keeps_original_text():
    rng = random.Random(3)
    new = ev.insert_sentence(NARRATIVE, "PLANTED SENTENCE.", rng)
    assert "PLANTED SENTENCE." in new
    assert " ".join(new.replace(" PLANTED SENTENCE.", "").split()) == " ".join(NARRATIVE.split())
    assert not new.startswith("PLANTED")


def test_modified_pages_do_not_touch_originals():
    original = pages()
    snapshot = json.dumps(original, sort_keys=True)
    plants = ev.make_plants(LEDGER, original, seed=2, n_planted=2, n_explained=1)
    mod = ev.modified_pages(original, plants, seed=2)
    assert json.dumps(original, sort_keys=True) == snapshot
    for p in plants:
        assert p["sentence"] in mod[p["target_page"]]["text"]


def test_pick_source_claims_keeps_subjects_apart():
    picked = ev.pick_source_claims(LEDGER, 10, random.Random(0))
    values = [c["value"] for c in picked]
    assert len(values) == len(set(values))
    assert "p4-02" not in {c["id"] for c in picked} and "p4-03" not in {c["id"] for c in picked}


def test_changed_value_keeps_type():
    assert ev.changed_value(330, 1.5) == 495 and isinstance(ev.changed_value(330, 1.5), int)
    assert ev.changed_value(45.91, 0.5) == pytest.approx(22.955, abs=0.006)   # 2 decimals


# ---------- scoring ----------

PLANTS = [
    {"id": "pl-01", "kind": "planted", "source_id": "p1-01", "source_page": 1, "target_page": 20,
     "sentence": "As per the field survey, the figure for fauna species recorded from GNI is 495 species.",
     "subject": "fauna", "source_value": 330, "new_value": 495, "unit": "species"},
    {"id": "pl-02", "kind": "planted", "source_id": "p2-01", "source_page": 2, "target_page": 21,
     "sentence": "As per the field survey, the figure for reclaimed land for airport runway is 97 ha.",
     "subject": "land", "source_value": 194, "new_value": 97, "unit": "ha"},
    {"id": "ex-03", "kind": "explained", "source_id": "p3-01", "source_page": 3, "target_page": 22,
     "sentence": "As per the field survey, the figure for Indira Point to Sumatra was revised from "
                 "163 km to 82 km after the 2021 survey.",
     "subject": "distance", "source_value": 163, "new_value": 82, "unit": "km"},
]


def finding(fid, grade, pages_, quotes):
    return {"id": fid, "grade": grade, "pages": pages_, "reason": "r",
            "quotes": [{"page": p, "text": t} for p, t in quotes]}


def test_score_plants():
    findings = [
        finding("ct-1", "RED", [1, 20], [(1, "330 species"), (20, PLANTS[0]["sentence"])]),
        finding("ct-2", "ORANGE", [3, 22], [(3, "163 km"), (22, PLANTS[2]["sentence"])]),
        finding("ct-3", "ORANGE", [20, 9], [(20, "The coast is rocky"), (9, "x")]),   # unrelated
    ]
    extracted = [{"id": "p20-01", "page": 20, "quote": "the figure for fauna species recorded from GNI is 495 species"}]
    cands = [{"claims": [{"id": "p1-01", "page": 1}, {"id": "p20-01", "page": 20}]}]
    s = ev.score_plants(PLANTS, findings, extracted, cands)
    rows = {r["id"]: r for r in s["rows"]}
    assert rows["pl-01"]["ok"] and rows["pl-01"]["grade"] == "RED" and rows["pl-01"]["paired"]
    assert not rows["pl-02"]["ok"] and rows["pl-02"]["stage_missed"] == "extraction"
    assert not rows["ex-03"]["ok"]                          # explained but flagged ORANGE
    assert (s["planted_caught"], s["planted_total"]) == (1, 2)
    assert (s["explained_wrongly_flagged"], s["explained_total"]) == (1, 1)
    assert [o["id"] for o in s["other_new_flags"]] == ["ct-3"]


def test_explained_graded_none_is_ok_and_miss_stages():
    findings = [finding("ct-1", "NONE", [3, 22], [(3, "163 km"), (22, PLANTS[2]["sentence"])])]
    extracted = [{"id": "p21-01", "page": 21, "quote": PLANTS[1]["sentence"]}]
    cands = [{"claims": [{"id": "p2-01", "page": 2}, {"id": "p21-01", "page": 21}]}]
    rows = {r["id"]: r for r in ev.score_plants(PLANTS, findings, extracted, cands)["rows"]}
    assert rows["ex-03"]["ok"] and rows["ex-03"]["grade"] == "NONE"
    assert rows["pl-02"]["stage_missed"] == "verdict"       # extracted and paired, not flagged
    assert rows["pl-01"]["stage_missed"] == "extraction"


def test_score_species():
    def r(grade, local=0):
        return {"grade": grade, "local_count": local, "regional_count": 0, "global_count": 9,
                "matched_name": "x"}
    results = {"A": r("RED"), "B": r("ORANGE"), "C": r("GREY"), "D": r(None, 5), "E": r("ORANGE", 2)}
    s = ev.score_species(results, ["A", "B", "C"], ["D", "E"])
    assert (s["out_of_place_flagged"], s["out_of_place_grey"]) == (2, 1)
    assert (s["real_wrongly_flagged"], s["real_total"]) == (1, 2)


# ---------- usage rows ----------

def test_usage_row_measured_and_estimated(tmp_path):
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"model": ev.llm.LIGHTNING, "_latency_s": 1.5,
                             "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}))
    b = tmp_path / "b.json"
    b.write_text(json.dumps({"model": ev.llm.ULTRA,
                             "usage": {"prompt_tokens": 2000, "completion_tokens": 1000}}))
    row = ev.usage_row("x", [("llm", a), ("llm", a), ("llm", b), ("gbif", a)], {b: 20.0})
    assert row["calls"] == 2 and row["total_tokens"] == 4500
    assert row["seconds"] == 21.5 and row["time_measured"] is False
    expected = (1000 * 0.06 + 500 * 0.24 + 2000 * 1.0 + 1000 * 3.0) / 1e6
    assert row["cost_usd"] == pytest.approx(expected, abs=1e-5)


def test_inr_rate_is_labelled_constant():
    assert ev.USD_TO_INR == 84 and ev.inr(1.0) == 84
