"""Offline tests for the batch regexes and public result boundaries."""

from datetime import date

from tigerfish.library import validate
from tigerfish.batch import (accreditation_check, baseline_check, date_tokens, make_summary,
                             parse_date_token, period_months, public_index, summary_markdown,
                             _quick_report)


def page(number, text):
    return {"page": number, "text": text}


def test_date_parser_covers_common_indian_formats():
    assert parse_date_token("31/03/2024")[0] == date(2024, 3, 31)
    assert parse_date_token("31-03-24")[0] == date(2024, 3, 31)
    assert parse_date_token("2024-03-31")[0] == date(2024, 3, 31)
    assert parse_date_token("March 31, 2024")[0] == date(2024, 3, 31)
    assert parse_date_token("31st March 2024")[0] == date(2024, 3, 31)
    assert parse_date_token("March 2024")[1] == "month"
    assert [x["text"] for x in date_tokens("valid till 31st March 2024; report dated April 2024")] == [
        "31st March 2024", "April 2024"
    ]


def test_accreditation_expired_is_orange_with_all_quotes():
    result = accreditation_check([
        page(1, "DRAFT ENVIRONMENTAL IMPACT ASSESSMENT\nReport dated April 2024"),
        page(2, "Consultant: ABC. NABET / EIA / 1720 / SA 088. Certificate valid till 31/03/2024."),
    ])
    assert result["grade"] == "ORANGE"
    assert {q["label"] for q in result["quotes"]} == {"NABET certificate", "Validity date", "Report date"}
    assert {q["page"] for q in result["quotes"]} == {1, 2}


def test_accreditation_within_three_months_is_info():
    result = accreditation_check([
        page(1, "Environmental Impact Assessment\nMay 2024"),
        page(2, "NABET/EIA/2022/RA-123 valid up to 31 July 2024"),
    ])
    assert result["grade"] == "INFO"


def test_accreditation_grey_when_a_date_is_unreadable():
    result = accreditation_check([
        page(1, "Environmental Impact Assessment\nApril 2024"),
        page(2, "NABET/EIA/2022/RA-123; validity shown on certificate."),
    ])
    assert result["grade"] == "GREY"


def test_baseline_season_uses_inclusive_months():
    result = baseline_check([page(7, "Baseline monitoring was carried out from October 2022 to December 2022.")])
    assert result["grade"] == "OK"
    assert result["duration_months"] == 3


def test_short_baseline_is_info_and_date_ranges_are_day_aware():
    result = baseline_check([page(8, "Baseline air monitoring period: 01/04/2022 to 31/05/2022.")])
    assert result["grade"] == "INFO"
    assert result["duration_months"] < 3
    assert period_months(date(2022, 4, 1), date(2022, 5, 31)) < 3


def test_summary_and_public_index_never_expose_local_path():
    report = {"id": "r1", "state": "Goa", "project_name": "Demo", "checks": {
        "accreditation": {"grade": "INFO"}}, "flags": [{
            "check": "accreditation", "grade": "INFO", "message": "verify",
            "quotes": [{"page": 2, "text": "valid till July 2024"}]}]}
    summary = make_summary([report])
    assert summary["per_state_counts"] == {"Goa": 1}
    assert summary["flag_counts"]["INFO"] == 1
    assert "valid till July 2024" in summary_markdown(summary)
    public = public_index({"documents": [{"local_path": "data/eias/batch/x.pdf", "url": "https://example.test/x.pdf"}]})
    assert "local_path" not in public["documents"][0]


def test_quick_report_is_discoverable_by_library_and_keeps_batch_flags():
    report = _quick_report({
        "id": "demo_001",
        "state": "Goa",
        "project_name": "Demo port expansion",
        "url": "https://example.test/demo.pdf",
        "source_page": "https://example.test/hearings",
        "pages": 12,
        "checks": {
            "accreditation": {"check": "accreditation", "grade": "ORANGE", "quotes": []},
            "baseline_season": {"check": "baseline_season", "grade": "INFO", "quotes": []},
            "species_iucn": {"check": "species_iucn", "status": "OK", "rows": [{
                "page": 4, "name": "Panthera leo", "report_iucn": "VU", "gbif_iucn": "EN"
            }], "location": {"lat": 15.49, "lon": 73.83, "label": "Goa", "source": "named site"},
                "flags": [{"check": "species_iucn", "grade": "ORANGE", "name": "Panthera leo",
                           "page": 4, "title": "Panthera leo (p.4)", "message": "verify",
                           "quotes": [{"page": 4, "text": "Panthera leo VU"}],
                           "evidence": [{"label": "GBIF", "value": "current EN"}],
                           "report_iucn": "VU", "gbif_iucn": "EN"}]},
        },
        "flags": [{"check": "accreditation", "grade": "ORANGE", "message": "verify",
                   "quotes": [{"page": 2, "text": "NABET certificate"}]}],
    })
    assert validate(report) == []
    assert report["findings"][0]["check"] == "iucn_status"
    assert report["batch_flags"][0]["check"] == "accreditation"


def test_batch_summary_structure_and_tavily_stats():
    import json
    from tigerfish.batch import SUMMARY_JSON
    assert SUMMARY_JSON.exists(), "results/batch/batch_summary.json must exist"
    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    assert summary.get("reports_processed", 0) >= 80
    assert len(summary.get("per_state_counts", {})) >= 4
    tavily = summary.get("tavily", {})
    assert tavily.get("calls", 0) > 0
    assert tavily.get("credits", 0) > 0
    assert "by_endpoint" in tavily


def test_batch_page_registered_in_nav():
    from tigerfish.ui import pages
    page_list = pages.build()
    assert "batch" in pages.PAGES
    assert pages.PAGES["batch"] in page_list


def test_extract_proposal_and_project_matches_regex():
    from tigerfish.batch import extract_proposal_and_project
    pages = [
        {"page": 1, "text": "EXECUTIVE SUMMARY\nProject: Solar Plant"},
        {"page": 2, "text": "File No. SIA/MH/IND1/564190/2026 dated 23.01.2026"},
    ]
    prop, proj, p, q = extract_proposal_and_project(pages)
    assert prop == "SIA/MH/IND1/564190/2026"
    assert p == 2
    assert "SIA/MH/IND1/564190/2026" in q


def test_public_record_check_appends_info_on_court_docket():
    from tigerfish.batch import public_record_check
    class MockClient:
        def search(self, **kwargs):
            return {
                "results": [
                    {"url": "https://www.greentribunal.gov.in/Ejournal/uploads/case-123.pdf",
                     "title": "National Green Tribunal Order"}
                ]
            }

    pages = [{"page": 1, "text": "Application IA/OR/CMIN/579355/2026"}]
    res = public_record_check(pages, {"project_name": "Test Mine"}, client=MockClient())
    assert res["check"] == "public_record"
    assert res["grade"] == "INFO"
    assert res["message"] == "Prior tribunal docket indexed; verify status."
    assert res["court_url"] == "https://www.greentribunal.gov.in/Ejournal/uploads/case-123.pdf"
    assert res["page"] == 1
    assert res["quotes"][0]["page"] == 1
    assert any(e.get("url") == res["court_url"] for e in res["evidence"])
