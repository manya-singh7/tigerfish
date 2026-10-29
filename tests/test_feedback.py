"""Persistent reviewer feedback: file round trip, import merge, precision per check, and the
app saving a review to the file (AppTest, no API keys)."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest  # noqa: F401
from apptest import open_app

from tigerfish.ui import feedback

ROOT = Path(__file__).resolve().parent.parent
F1 = {"id": "ct-003", "check": "contradiction", "check_name": "Internal contradiction", "grade": "RED"}
F2 = {"id": "ct-004", "check": "contradiction", "check_name": "Internal contradiction", "grade": "RED"}
F3 = {"id": "sp-1", "check": "species_range", "check_name": "Species out of range", "grade": "ORANGE"}


def test_record_save_load_round_trip(feedback_file):
    e = feedback.record({}, "gn", F1, "Confirm", " Asha ", "checked p.392 ")
    feedback.save(e)
    got = feedback.load()
    entry = got["gn::ct-003"]
    assert entry["decision"] == "Confirm" and entry["reviewer"] == "Asha" and entry["note"] == "checked p.392"
    assert entry["check_name"] == "Internal contradiction" and entry["updated"]
    assert json.loads(feedback_file.read_text(encoding="utf-8"))["version"] == 1


def test_clearing_a_decision_removes_the_entry():
    e = feedback.record({}, "gn", F1, "Confirm")
    assert feedback.record(e, "gn", F1, None) == {}


def test_bad_decision_rejected():
    with pytest.raises(ValueError):
        feedback.record({}, "gn", F1, "Maybe")


def test_missing_or_broken_file_is_empty(feedback_file):
    assert feedback.load() == {}
    feedback_file.write_text("{not json", encoding="utf-8")
    assert feedback.load() == {}


def test_import_newer_wins_and_bad_files_are_rejected():
    old = {"gn::ct-003": {**feedback.record({}, "gn", F1, "Dismiss")["gn::ct-003"], "updated": "2026-10-01T00:00:00+00:00"}}
    new = {"gn::ct-003": {**old["gn::ct-003"], "decision": "Confirm", "updated": "2026-10-20T00:00:00+00:00"},
           "gn::sp-1": feedback.record({}, "gn", F3, "Unsure")["gn::sp-1"]}
    merged, taken = feedback.merge(old, feedback.parse_import(feedback.dump(new).encode()))
    assert taken == 2 and merged["gn::ct-003"]["decision"] == "Confirm"
    merged2, taken2 = feedback.merge(merged, old)                 # older import changes nothing
    assert taken2 == 0 and merged2 == merged
    with pytest.raises(ValueError):
        feedback.parse_import(b'{"something": 1}')
    junk = {"entries": {"gn::x": {"decision": "Nope", "report_id": "gn", "finding_id": "x"}}}
    assert feedback.parse_import(json.dumps(junk)) == {}


def test_precision_per_check_ignores_unsure():
    e = {}
    e = feedback.record(e, "gn", F1, "Confirm")
    e = feedback.record(e, "gn", F2, "Dismiss")
    e = feedback.record(e, "gn", F3, "Unsure")
    e = feedback.record(e, "other", {**F3, "id": "sp-2"}, "Confirm")
    rows = {r["check"]: r for r in feedback.precision(e)}
    assert rows["Internal contradiction"]["precision"] == 0.5
    assert rows["Internal contradiction"]["reviewed"] == 2
    assert rows["Species out of range"] == {"check": "Species out of range", "confirmed": 1,
                                            "dismissed": 0, "unsure": 1, "reviewed": 2, "precision": 1.0}
    only_gn = {r["check"]: r for r in feedback.precision(e, "gn")}
    assert only_gn["Species out of range"]["precision"] is None
    table = feedback.precision_table(feedback.precision(e))
    # fewer than 20 judged: no percentage (tigerfish/quality.py)
    assert "2 reviewed so far: too few to estimate precision" in table
    assert "1 reviewed so far: too few to estimate precision" in table and "%" not in table


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")


@pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(), reason="no results/")
def test_app_saves_a_review_and_shows_precision(no_keys, feedback_file):
    at = open_app(timeout=60)
    at.text_input(key=feedback.REVIEWER_KEY).input("Asha").run()
    from tigerfish.ui import data
    fid = next(f["id"] for f in data.load("great_nicobar_2021_draft")["findings"]
               if f.get("known_issue") == "gn-001")
    key = feedback.widget_key("great_nicobar_2021_draft", fid)
    at.button_group(key=key).set_value("Confirm").run()     # click Confirm: saved by its callback
    assert json.loads(feedback_file.read_text(encoding="utf-8"))["entries"][
        f"great_nicobar_2021_draft::{fid}"]["decision"] == "Confirm"
    at.text_input(key=feedback.note_key("great_nicobar_2021_draft", fid)).input("p.392 read").run()
    assert not at.exception
    saved = json.loads(feedback_file.read_text(encoding="utf-8"))["entries"]
    e = saved[f"great_nicobar_2021_draft::{fid}"]
    assert e["decision"] == "Confirm" and e["reviewer"] == "Asha" and e["note"] == "p.392 read"
    reviews_file = feedback_file.parent / "reviews.jsonl"
    assert reviews_file.exists()
    lines = [json.loads(line) for line in reviews_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 2
    assert lines[0]["report_id"] == "great_nicobar_2021_draft" and lines[0]["flag_id"] == fid
    assert lines[0]["verdict"] == "confirm"
    assert lines[1]["note"] == "p.392 read"
    captions = "\n".join(c.value for c in at.caption)
    assert "Community feedback is saved as a reviewer suggestion and does not modify the verified finding without audit review." in captions
    text = "\n".join(m.value for m in at.markdown)
    assert "#### Precision" in text and "**Team reviews (saved)**" in text
    assert "1 reviewed so far: too few to estimate precision" in text

    # a fresh session reads the decision back from the file
    at2 = open_app(timeout=60)
    assert at2.session_state[key] == "Confirm"
    assert at2.text_input(key=feedback.REVIEWER_KEY).value == "Asha"
