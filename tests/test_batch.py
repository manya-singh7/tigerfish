"""Offline tests for the batch regexes and public result boundaries."""

from datetime import date

from tigerfish.batch import (accreditation_check, baseline_check, date_tokens, make_summary,
                             parse_date_token, period_months, public_index, summary_markdown)


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
