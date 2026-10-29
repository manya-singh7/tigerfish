"""Offline tests for the batch regexes and public result boundaries."""

from datetime import date
import json

import pytest

from tigerfish.library import validate
from tigerfish import batch
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


@pytest.mark.parametrize(
    "text",
    [
        "Study Period – October - December 2025 Report No.: OA/GPIL/071/EIA/03/2026/01 Month & Year – March 2026",
        "Baseline monitoring was conducted from October to December 2025.",
        "Baseline air monitoring period: 01/02/2025 to 30/04/2025.",
        "Baseline air monitoring period: 2025-02-01 to 2025-04-30.",
    ],
)
def test_baseline_calendar_quarter_and_shared_year(text):
    result = baseline_check([page(1, text)])
    assert result["grade"] == "OK"
    assert result["duration_months"] == 3
    assert result["requirement_verified"] is False


def test_baseline_infers_start_year_for_winter_range():
    result = baseline_check(
        [page(2, "Baseline monitoring period: December to February 2025.")]
    )
    assert result["start_date"] == "2024-12-01"
    assert result["end_date"] == "2025-02-01"
    assert result["duration_months"] == 3


@pytest.mark.parametrize(
    "text",
    [
        "EIA study application submitted on 28/04/2025. The proposal was considered in the EAC meeting held on 18-19 June 2025.",
        "Study area traffic counts: 25/10/2012 and 26/10/2012. A traffic survey was conducted for one day.",
        "Traffic study was conducted from 25/10/2012 to 26/10/2012.",
        "Baseline monitoring will be conducted from October to December 2025.",
        "Baseline monitoring frequency: samples collected every 2 months.",
        "Baseline study: report dated March 2025, certificate valid until April 2025.",
        "Baseline monitoring covered 01/04/2025 and 31/05/2025, but no study period is stated.",
        "Baseline monitoring was conducted for one season.",
    ],
)
def test_baseline_does_not_infer_period_from_unrelated_or_ambiguous_dates(text):
    result = baseline_check([page(1, text)])
    assert result["grade"] == "GREY"
    assert not result.get("start_date")


def test_baseline_searches_beyond_administrative_dates():
    result = baseline_check(
        [
            page(
                1,
                "EIA study application submitted on 28/04/2025; EAC meeting 19/06/2025.",
            ),
            page(
                4, "Baseline monitoring was carried out from October to December 2025."
            ),
        ]
    )
    assert result["grade"] == "OK"
    assert result["quotes"][0]["page"] == 4
    assert all(
        q["text"]
        in "Baseline monitoring was carried out from October to December 2025."
        for q in result["quotes"]
    )


def test_baseline_preserves_conflicting_intervals_instead_of_accepting_first():
    result = baseline_check(
        [
            page(1, "Baseline air monitoring period: October to December 2025."),
            page(3, "Baseline air monitoring period: November to December 2025."),
        ]
    )
    assert result["grade"] == "GREY"
    assert {q["page"] for q in result["quotes"]} == {1, 3}
    assert len(result["periods"]) == 2


def test_baseline_keeps_topics_separate_and_accepts_explicit_duration():
    result = baseline_check(
        [
            page(1, "Baseline air monitoring was carried out for three months."),
            page(
                2,
                "Terrestrial ecology baseline survey was conducted from 14 to 22 December 2020.",
            ),
        ]
    )
    assert result["grade"] == "INFO"
    assert {p["topic"] for p in result["periods"]} == {"air", "terrestrial ecology"}
    assert result["requirement_verified"] is False


def test_baseline_rejects_reversed_or_invalid_day_ranges():
    for text in (
        "Baseline monitoring: 31/02/2025 to 31/03/2025.",
        "Baseline monitoring: December 2025 to October 2025.",
    ):
        assert baseline_check([page(1, text)])["grade"] == "GREY"


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


def test_baseline_refresh_preserves_other_checks_and_discovery_costs(
    tmp_path, monkeypatch
):
    old_flag = {
        "check": "baseline_season",
        "grade": "INFO",
        "message": "wrong two months",
    }
    certificate = {
        "check": "accreditation",
        "grade": "OK",
        "message": "saved certificate",
        "quotes": [],
    }
    species = {"check": "species_iucn", "status": "OK", "rows": [], "flags": []}
    quick = _quick_report(
        {
            "id": "demo",
            "project_name": "Demo",
            "state": "Goa",
            "pages": 1,
            "checks": {
                "accreditation": certificate,
                "species_iucn": species,
                "baseline_season": old_flag,
            },
            "flags": [old_flag],
        }
    )
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(quick))
    monkeypatch.setattr(batch, "BATCH_RESULTS", tmp_path)
    for name, filename in (
        ("QUICK_INDEX", "index.json"),
        ("PUBLIC_CORPUS_INDEX", "corpus_index.json"),
        ("SUMMARY_JSON", "batch_summary.json"),
        ("SUMMARY_MD", "batch_summary.md"),
    ):
        monkeypatch.setattr(batch, name, tmp_path / filename)
    batch.QUICK_INDEX.write_text(json.dumps({"reports": [{"file": "demo.json"}]}))
    batch.PUBLIC_CORPUS_INDEX.write_text(
        json.dumps({"documents": [{"document_id": "demo", "sha256": "sourcehash"}]})
    )
    tavily = {"credits": 41, "calls": 14, "cap": 400}
    batch.SUMMARY_JSON.write_text(
        json.dumps({"tavily": tavily, "reports_requested": 50})
    )
    monkeypatch.setattr(
        batch,
        "_baseline_source_pages",
        lambda *args: [page(1, "Study period: October to December 2025.")],
    )
    summary = batch.refresh_baselines()
    result = json.loads(path.read_text())
    assert result["batch_checks"]["baseline_season"]["grade"] == "OK"
    assert result["batch_flags"] == []
    assert result["batch_checks"]["accreditation"] == certificate
    assert (
        result["batch_checks"]["species_iucn"] == quick["batch_checks"]["species_iucn"]
    )
    assert result["findings"] == quick["findings"]
    assert result["baseline_refresh"]["source_sha256"] == "sourcehash"
    assert summary["tavily"] == tavily and summary["reports_requested"] == 50
    assert validate(result) == []


def test_baseline_source_rejects_changed_pdf_before_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "BATCH_DATA", tmp_path)
    (tmp_path / "demo.pdf").write_bytes(b"%PDF-changed")
    with pytest.raises(ValueError, match="hash"):
        batch._baseline_source_pages(
            {"document_id": "demo", "sha256": "original"}, False
        )
