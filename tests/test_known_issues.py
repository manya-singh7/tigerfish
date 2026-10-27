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


STATUSES = {None, "under_review", "candidate_new_finding", "explained"}
OUTCOMES = {"confirmed", "confirmed_with_nuance", "explained"}
OTHER_CHECKS = {"species_range", "accreditation", "tor_promise"}


def test_statuses_are_valid_and_ids_unique():
    ids = [i["id"] for i in ISSUES["issues"]]
    assert len(ids) == len(set(ids))
    for issue in ISSUES["issues"]:
        assert issue.get("status") in STATUSES, issue["id"]
    by_id = {i["id"]: i for i in ISSUES["issues"]}
    assert by_id["gn-002"]["status"] == "explained"
    assert by_id["gn-002"]["expected_grade"] == "NONE"     # second negative control
    assert by_id["gn-005"].get("status") is None            # confirmed by hand: scored


def test_manual_verification_is_recorded():
    """Every issue was checked by hand on 2026-10-27; explained issues are negative controls."""
    for issue in ISSUES["issues"]:
        assert issue["verified_by"] == "Manya Singh", issue["id"]
        assert issue["verified_on"] == "2026-10-27", issue["id"]
        assert issue["verification_note"], issue["id"]
        assert issue["verification_outcome"] in OUTCOMES, issue["id"]
        if issue["verification_outcome"] == "explained":
            assert issue["expected_grade"] == "NONE", issue["id"]
        if issue["verification_outcome"] == "confirmed_with_nuance":
            assert issue.get("verified_wording"), issue["id"]


def test_other_checks_name_their_app_finding():
    by_id = {i["id"]: i for i in ISSUES["issues"]}
    for issue in ISSUES["issues"]:
        assert (issue["type"] in OTHER_CHECKS) == bool(issue.get("finding_id")), issue["id"]
    assert by_id["gn-009"]["finding_id"] == "sp-p954-001"
    assert by_id["gn-010"]["finding_id"] == "ac-01"
    assert by_id["gn-011"]["finding_id"] == "pr-06"
    assert "proposed" in by_id["gn-011"]["verified_title"]


def test_grade_ok_uses_acceptable_grades():
    by_id = {i["id"]: i for i in ISSUES["issues"]}
    assert grade_ok(by_id["gn-001"], "RED") and grade_ok(by_id["gn-001"], "ORANGE")
    assert not grade_ok(by_id["gn-001"], "GREY")
    assert grade_ok(by_id["gn-003"], "RED") and not grade_ok(by_id["gn-003"], "ORANGE")
    assert grade_ok(by_id["gn-neg-001"], "NONE") and not grade_ok(by_id["gn-neg-001"], "ORANGE")
