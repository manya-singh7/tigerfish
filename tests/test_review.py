"""Review queue: verdicts, precision, reviewer agreement, hidden dismissed flags, the queue
file itself, and the Review queue tab in the app (decisions written to a temp file)."""

import json
from pathlib import Path

import pytest

from tigerfish import review

ROOT = Path(__file__).resolve().parent.parent


def queue(*items):
    return {"report_id": "r", "items": [{"flag_id": fid, "double_review": dbl, "group": grp,
                                         "finding_id": fin} for fid, dbl, grp, fin in items]}


@pytest.fixture
def store(tmp_path):
    return tmp_path / "reviews.jsonl"


def test_reviewer_name_is_required(store):
    with pytest.raises(ValueError):
        review.record("ct-1", "  ", "real", path=store)
    with pytest.raises(ValueError):
        review.record("ct-1", "A", "maybe", path=store)


def test_single_review_latest_decision_counts(store):
    q = queue(("ct-1", False, "top30", "ct-1"))
    review.record("ct-1", "A", "real", path=store)
    review.record("ct-1", "A", "false_alarm", path=store)          # changed mind
    assert review.verdict(q["items"][0], review.load_reviews(store)) == "false_alarm"


def test_double_review_needs_two_reviewers_and_agreement(store):
    q = queue(("ct-1", True, "top30", "ct-1"), ("ct-2", True, "top30", "ct-2"))
    review.record("ct-1", "Manya", "real", path=store)
    r = review.load_reviews(store)
    assert review.verdict(q["items"][0], r) == "waiting"
    assert not review.needs(q["items"][0], r, "manya ")            # same person, other spelling
    assert review.needs(q["items"][0], r, "Teammate")
    review.record("ct-1", "Teammate", "real", path=store)
    review.record("ct-2", "Manya", "real", path=store)
    review.record("ct-2", "Teammate", "false_alarm", path=store)
    r = review.load_reviews(store)
    assert review.verdict(q["items"][0], r) == "real"
    assert review.verdict(q["items"][1], r) == "disputed"
    a = review.agreement(q, r)
    assert (a["both_reviewed"], a["agree"], a["rate"]) == (2, 1, 0.5)


def test_precision_leaves_out_unsure_and_disputed(store):
    q = queue(("a", False, "top30", "a"), ("b", False, "random", "b"), ("c", False, "random", "c"),
              ("d", True, "top30", "d"), ("e", False, "random", "e"))
    review.record("a", "A", "real", path=store)
    review.record("b", "A", "false_alarm", path=store)
    review.record("c", "A", "unsure", path=store)
    review.record("d", "A", "real", path=store)
    review.record("d", "B", "false_alarm", path=store)
    p = review.precision(q, review.load_reviews(store))
    assert (p["precision"], p["judged"], p["reviewed"], p["total"]) == (0.5, 2, 4, 5)
    assert (p["unsure"], p["disputed"]) == (1, 1)


def test_next_index_walks_in_order_and_wraps(store):
    q = queue(("a", False, "top30", "a"), ("b", True, "top30", "b"), ("c", False, "random", "c"))
    review.record("a", "A", "real", path=store)
    review.record("b", "B", "real", path=store)
    r = review.load_reviews(store)
    assert review.next_index(q, r, "A") == 1           # b is double review: A must judge it
    assert review.next_index(q, r, "B") == 2
    assert review.next_index(q, r, "B", start=3) == 2  # wraps around
    review.record("c", "B", "real", path=store)
    assert review.next_index(q, review.load_reviews(store), "B") is None


def test_dismissed_only_when_every_flag_of_a_finding_is_a_false_alarm(store):
    q = queue(("ct-1", False, "top30", "ct-1"), ("ct-2", False, "random", "ct-1"),
              ("ct-3", False, "random", "ct-3"))
    review.record("ct-1", "A", "false_alarm", path=store)
    review.record("ct-3", "A", "false_alarm", path=store)
    assert review.dismissed_finding_ids(q, review.load_reviews(store)) == {"ct-3"}
    review.record("ct-2", "A", "false_alarm", path=store)
    assert review.dismissed_finding_ids(q, review.load_reviews(store)) == {"ct-1", "ct-3"}


VERIFIED = {"by": "Manya Singh", "on": "2026-10-27", "decision": "real", "note": "checked"}


def test_human_verified_item_counts_as_confirmed_and_needs_no_review(store):
    q = queue(("ct-1", True, "top30", "ct-1"), ("ct-2", False, "random", "ct-2"))
    for it in q["items"]:
        it["verified"] = VERIFIED
    reviews = review.load_reviews(store)
    assert [review.verdict(it, reviews) for it in q["items"]] == ["real", "real"]
    assert not any(review.needs(it, reviews, "Teammate") for it in q["items"])
    p = review.precision(q, reviews)
    assert p["precision"] == 1.0 and p["judged"] == 2 and p["waiting"] == 0
    assert review.decisions(q["items"][0], reviews)["manya singh"]["reviewer"] == "Manya Singh"


def test_human_verified_double_review_disputed_if_teammate_disagrees(store):
    q = queue(("ct-1", True, "top30", "ct-1"))
    q["items"][0]["verified"] = VERIFIED
    review.record("ct-1", "Teammate", "false_alarm", path=store)
    reviews = review.load_reviews(store)
    assert review.verdict(q["items"][0], reviews) == "disputed"
    assert review.agreement(q, reviews)["both_reviewed"] == 1


def test_verified_entry_only_for_confirmed_findings():
    v = {"by": "Manya Singh", "on": "2026-10-27", "outcome": "confirmed_with_nuance", "note": "n"}
    f = {"known_issue": "gn-006", "verification": v}
    assert review.verified_entry(f)["decision"] == "real"
    assert review.verified_entry({**f, "verification": {**v, "outcome": "explained"}}) is None
    assert review.verified_entry(None) is None and review.verified_entry({"id": "x"}) is None


@pytest.mark.skipif(not review.QUEUE.exists(), reason="no review/review_queue.json")
def test_queue_marks_human_verified_flags_reviewed():
    q = review.load_queue()
    done = {i["flag_id"]: i["verified"] for i in q["items"] if i.get("verified")}
    assert set(done) == {"ct-071", "ct-239", "ct-979"}
    assert all(v["by"] == "Manya Singh" and v["decision"] == "real" for v in done.values())
    assert review.precision(q, {})["real"] == 3


@pytest.mark.skipif(not review.QUEUE.exists(), reason="no review/review_queue.json")
def test_queue_file_order_and_double_review():
    q = review.load_queue()
    audit = json.loads((ROOT / "results" / "audit_great_nicobar_2021_draft_eia.json").read_text(encoding="utf-8"))
    items = q["items"]
    assert len(items) == q["total"] == audit["new_flagged"]
    assert {i["flag_id"] for i in items} == {f["id"] for f in audit["flags"]}
    assert [i["group"] for i in items[:30]] == ["top30"] * 30
    assert all(i["group"] == "random" for i in items[30:])
    dbl = [i for i in items if i["double_review"]]
    assert len(dbl) == 15 and all(i["group"] == "top30" for i in dbl)
    assert all(i["finding_id"] for i in items)                # every flag is shown in the app
    assert not any("quick" in k for i in items for k in i)    # reviewers judge without our read


@pytest.mark.skipif(not review.QUEUE.exists() or not (ROOT / "results" / "index.json").exists(),
                    reason="no queue or results")
def test_review_tab_records_a_decision(tmp_path, monkeypatch):
    from apptest import open_app
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("TIGERFISH_FEEDBACK", str(tmp_path / "feedback.json"))
    monkeypatch.setattr(review, "REVIEWS", tmp_path / "reviews.jsonl")
    at = open_app(timeout=120)
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    from tigerfish.ui import data
    report = data.load(review.load_queue()["report_id"])
    q = review.queue_for(report)
    assert f"#### Review queue: {report['title']} ({q['total']} RED/ORANGE flags)" in text
    # opens on the first flag that still needs a decision (human-verified ones are reviewed)
    n, first = next((i["n"], i["flag_id"]) for i in q["items"] if not i.get("verified"))
    assert f"Flag {n} of {q['total']}" in "\n".join(str(p.proto.text) for p in at.get("progress"))
    assert "Reviewer agreement" in text
    at.text_input(key="review::name").input("Tester").run()
    at.button(key=f"review::real::{first}").click().run()
    assert not at.exception
    rows = review.load_reviews(tmp_path / "reviews.jsonl")
    assert rows[first]["tester"]["decision"] == "real"
