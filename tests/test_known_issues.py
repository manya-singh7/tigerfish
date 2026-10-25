"""Every quote in data/known_issues.json must appear verbatim on its page.

Needs the page cache from scripts/inspect_pdf.py; skipped if it is not there.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ISSUES = json.loads((ROOT / "data" / "known_issues.json").read_text(encoding="utf-8"))
CACHE = ROOT / "cache" / "pages" / Path(ISSUES["document"]).stem / "pages.jsonl"


@pytest.mark.skipif(not CACHE.exists(), reason="run scripts/inspect_pdf.py first")
def test_quotes_are_exact():
    with CACHE.open(encoding="utf-8") as f:
        pages = {p["page"]: " ".join(p["text"].split()) for p in map(json.loads, f)}
    for issue in ISSUES["issues"]:
        for q in issue["quotes"]:
            assert q["page"] in issue["pages"], issue["id"]
            assert q["text"] in pages[q["page"]], f'{issue["id"]} p.{q["page"]}: {q["text"]}'


GRADES = {"RED", "ORANGE", "GREY", "NONE"}
VERIFY_FIELDS = ("verified_by", "verified_on", "verification_note")


def grade_ok(issue, grade):
    """A grade passes if it is in acceptable_grades (when given), else if it equals expected_grade."""
    return grade in issue.get("acceptable_grades", [issue["expected_grade"]])


def test_grades_are_valid():
    for issue in ISSUES["issues"]:
        assert issue["expected_grade"] in GRADES, issue["id"]
        acceptable = issue.get("acceptable_grades")
        if acceptable is not None:
            assert set(acceptable) <= GRADES, issue["id"]
            assert issue["expected_grade"] in acceptable, issue["id"]


def test_every_issue_has_verification_fields():
    for issue in ISSUES["issues"]:
        assert all(field in issue for field in VERIFY_FIELDS), issue["id"]


STATUSES = {None, "under_review", "candidate_new_finding"}


def test_statuses_are_valid_and_ids_unique():
    ids = [i["id"] for i in ISSUES["issues"]]
    assert len(ids) == len(set(ids))
    for issue in ISSUES["issues"]:
        assert issue.get("status") in STATUSES, issue["id"]
    by_id = {i["id"]: i for i in ISSUES["issues"]}
    assert by_id["gn-002"]["status"] == "under_review"
    assert by_id["gn-005"]["status"] == "candidate_new_finding"
    assert by_id["gn-005"]["verified_by"] is None


def test_grade_ok_uses_acceptable_grades():
    by_id = {i["id"]: i for i in ISSUES["issues"]}
    assert grade_ok(by_id["gn-001"], "RED") and grade_ok(by_id["gn-001"], "ORANGE")
    assert not grade_ok(by_id["gn-001"], "GREY")
    assert grade_ok(by_id["gn-003"], "RED") and not grade_ok(by_id["gn-003"], "ORANGE")
    assert grade_ok(by_id["gn-neg-001"], "NONE") and not grade_ok(by_id["gn-neg-001"], "ORANGE")
