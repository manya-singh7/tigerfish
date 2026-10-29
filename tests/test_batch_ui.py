"""Batch results remain inspectable without promoting uncertainty into audit findings."""

import json

import pytest

from apptest import open_app
from tigerfish import batch_results, copycheck, library, llm, species
from tigerfish.batch import _quick_report


@pytest.fixture
def screening_report(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("TIGERFISH_BATCH_DIR", str(tmp_path))

    def no_network(*args, **kwargs):
        pytest.fail("Saved batch UI must not make model, GBIF or Tavily calls")

    monkeypatch.setattr(llm, "chat", no_network)
    monkeypatch.setattr(species, "gbif_get", no_network)
    monkeypatch.setattr(copycheck, "tavily_call", no_network)
    baseline = {
        "check": "baseline_season",
        "grade": "INFO",
        "message": "Two months stated; compare with the applicable ToR.",
        "quotes": [
            {"page": 4, "text": "Baseline air monitoring: November to December 2025."}
        ],
        "periods": [
            {
                "topic": "air",
                "page": 4,
                "precision": "month",
                "start_date": "2025-11-01",
                "end_date": "2025-12-01",
                "duration_months": 2,
            }
        ],
        "evidence": [{"label": "Method", "value": "text rules; no model call"}],
    }
    report = _quick_report(
        {
            "id": "batch_demo",
            "project_name": "Demo screening",
            "state": "Goa",
            "url": "https://example.test/eia.pdf",
            "pages": 12,
            "checks": {
                "accreditation": {
                    "grade": "GREY",
                    "message": "No readable expiry date.",
                    "quotes": [],
                },
                "baseline_season": baseline,
                "species_iucn": {
                    "status": "GREY",
                    "message": "No readable species rows.",
                    "rows": [],
                },
            },
            "flags": [baseline],
        }
    )
    (tmp_path / "batch_demo.json").write_text(json.dumps(report))
    (tmp_path / "index.json").write_text(
        json.dumps({"reports": [{"file": "batch_demo.json"}]})
    )
    return report


def test_adapter_keeps_grey_out_of_observations_and_species_out_of_extra_counts(
    screening_report,
):
    report = screening_report
    report["batch_flags"] += [
        {"check": "accreditation", "grade": "GREY"},
        {"check": "species_iucn", "grade": "ORANGE"},
    ]
    summary = batch_results.summary(report)
    assert summary == {
        "checks": 3,
        "undetermined": 2,
        "observations": 1,
        "grades": {"RED": 0, "ORANGE": 0, "INFO": 1},
    }
    assert report["findings"] == []
    assert library.validate(report) == []


def test_quick_report_exposes_all_checks_and_source_evidence(screening_report):
    at = open_app(report="batch_demo")
    assert not at.exception
    tab = next(t for t in at.tabs if t.label.startswith("Batch screening"))
    assert (
        tab.label == "Batch screening (3)"
    )  # count check results, including uncertainty
    text = "\n".join(m.value for m in tab.markdown)
    assert "Certificate-date screen" in text and "No readable expiry date" in text
    assert "Baseline-period screen" in text and "November 2025 to December 2025" in text
    assert "Species and IUCN screen" in text and "No readable species rows" in text
    assert "Baseline air monitoring: November to December 2025." in text
    assert "https://example.test/eia.pdf#page=4" in text
    assert "3 checks, 1 additional observation, 2 undetermined" in text
    captions = " ".join(c.value for c in tab.caption)
    assert (
        "not official NABET verification" in captions
        and "not a compliance verdict" in captions
    )
    assert "no NVIDIA model calls" in captions


def test_library_and_summary_expose_the_same_additional_observation_count(
    screening_report,
):
    items = library.entries()
    entry = library.find(items, "batch_demo")
    assert entry["screening"]["observations"] == 1
    at = open_app(report=None, page="library")
    assert not at.exception
    text = " ".join(m.value for m in at.markdown) + " ".join(
        c.value for c in at.caption
    )
    assert "Batch screening results" in text
    assert "3 check results; Additional observations: 1; 2 undetermined results" in text
    table = next(
        d.value for d in at.dataframe if "Additional observations" in d.value.columns
    )
    assert table["Additional observations"].tolist() == [1]
    assert table["Report"].tolist() == ["/library?report=batch_demo"]
