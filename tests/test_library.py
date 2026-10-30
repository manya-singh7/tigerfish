"""Report library (home screen), the quick-check format, and the app's navigation:
library -> report -> back, quick-check view, upload screen with no key. No API keys, no network."""

import copy
import json
from pathlib import Path

import pytest

from apptest import GN, open_app
from tigerfish import library
from tigerfish.ui import library as library_ui

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "library" / "batch"
SAMPLES = sorted(p for p in FIXTURES.glob("*.json") if p.name != "index.json")
has_results = pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(), reason="no results/")


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")


@pytest.fixture
def batch(monkeypatch):
    monkeypatch.setenv("TIGERFISH_BATCH_DIR", str(FIXTURES))


def fake_results(tmp_path):
    """A results/ folder with one full audit and the two sample quick checks."""
    full = {"id": "r1", "title": "Report one", "pages_read": 10, "pages_total": 12,
            "findings": [{"id": "a", "grade": "RED", "verification": {"by": "x", "on": "y"}},
                         {"id": "b", "grade": "ORANGE"}, {"id": "c", "grade": "INFO"}]}
    (tmp_path / "r1.json").write_text(json.dumps(full), encoding="utf-8")
    (tmp_path / "index.json").write_text(json.dumps([{"id": "r1", "title": "Report one",
                                                      "file": "r1.json"}]), encoding="utf-8")
    (tmp_path / "library.json").write_text(json.dumps({"r1": {"state": "Goa", "sector": "Mining",
                                                              "year": 2020, "project": "Mine one"}}),
                                           encoding="utf-8")
    (tmp_path / "batch").mkdir()
    for p in FIXTURES.glob("*.json"):
        (tmp_path / "batch" / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


# ---------- library logic ----------


def test_entries_totals_and_filters(tmp_path):
    items = library.entries(fake_results(tmp_path), queue={}, reviews={})
    assert [e["id"] for e in items] == ["r1", "sample_quick_mine_odisha_2025",
                                        "sample_quick_highway_kerala_2024"]
    r1 = items[0]
    assert r1["project"] == "Mine one" and r1["state"] == "Goa" and r1["audit_type"] == library.FULL
    assert r1["grades"] == {"RED": 1, "ORANGE": 1, "INFO": 1}
    assert r1["reviewed"] == (1, 2)                     # hand-verified 1 of 2 RED/ORANGE
    t = library.totals(items)
    assert t == {"reports": 3, "pages": 10 + 212 + 90, "flags": 2 + 1 + 1, "red": 2,
                 "orange": 2, "info": 1 + 2 + 1, "full": 1, "quick": 2, "table": 0}
    assert library.totals_line(t).startswith("3 EIAs checked, 312 pages read, 4 flags")
    f = library.filter_entries
    assert [e["id"] for e in f(items, has_red=True)] == ["r1", "sample_quick_mine_odisha_2025"]
    assert [e["id"] for e in f(items, states=["Kerala"])] == ["sample_quick_highway_kerala_2024"]
    assert [e["id"] for e in f(items, audit_types=[library.FULL])] == ["r1"]
    assert [e["id"] for e in f(items, years=[2025])] == ["sample_quick_mine_odisha_2025"]
    assert [e["id"] for e in f(items, sectors=["Mining"])] == ["r1", "sample_quick_mine_odisha_2025"]
    assert [e["id"] for e in f(items, query="highway widening")] == ["sample_quick_highway_kerala_2024"]
    assert f(items, query="no such project") == []
    assert library.options(items, "year") == [2025, 2024, 2020]


def test_review_counts_from_the_queue():
    findings = [{"id": "x", "grade": "RED"}, {"id": "y", "grade": "ORANGE"}, {"id": "z", "grade": "INFO"}]
    queue = {"items": [{"flag_id": "x"}, {"flag_id": "y"}]}
    reviews = {"x": {"asha": {"flag_id": "x", "reviewer": "Asha", "decision": "false_alarm",
                              "time": "2026-10-28T10:00:00"}}}
    assert library.review_counts(findings, queue, reviews) == (1, 2)
    assert library.review_counts(findings) is None  # no reviews, no queue: not shown


@has_results
def test_totals_are_computed_from_the_saved_results():
    items = library.entries()
    saved = json.loads((ROOT / "results" / "index.json").read_text(encoding="utf-8"))
    assert len([e for e in items if e["kind"] == "saved"]) == len(saved)
    pages = sum(json.loads((ROOT / "results" / s["file"]).read_text(encoding="utf-8"))["pages_read"]
                for s in saved)
    assert sum(e["pages"] for e in items if e["kind"] == "saved") == pages


# ---------- the quick-check format ----------


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_sample_quick_checks_are_valid(path):
    raw = path.read_bytes()
    assert library.validate(json.loads(raw), raw) == []


def test_validate_rejects_bad_reports():
    good = json.loads(SAMPLES[0].read_text(encoding="utf-8"))
    bad = copy.deepcopy(good)
    bad["findings"][0]["grade"] = "RED"                       # number pair judged RED
    assert any("INFO only" in p for p in library.validate(bad))
    bad = copy.deepcopy(good)
    bad["checks_run"][0]["status"] = "not_available"          # findings of a check that did not run
    assert any("needs a reason" in p for p in library.validate(bad))
    assert any("not listed as ran" in p for p in library.validate(bad))
    bad = copy.deepcopy(good)
    bad["checks_run"].append({"check": "contradiction", "status": "ran"})   # a paid check
    assert any("not a free check" in p for p in library.validate(bad))
    bad = copy.deepcopy(good)
    del bad["pages_total"]
    assert library.validate(bad) == ["missing pages_total"]


def test_format_doc_matches_the_code():
    doc = (ROOT / "docs" / "REPORT_FORMAT.md").read_text(encoding="utf-8")
    assert library.FORMAT in doc and "results/batch/index.json" in doc
    for key in library.REQUIRED:
        assert f"`{key}`" in doc
    for check in library.QUICK_CHECKS:
        assert f"`{check}`" in doc
    for sector in library.SECTORS:
        assert sector in doc


# ---------- the app ----------


@pytest.fixture
def binder_library(monkeypatch):
    """More than 30 mixed reports: main renders all matches in separate binders."""
    items = [
        {
            "id": f"report_{i:02d}",
            "title": f"Report {i:02d}",
            "project": f"Project {i:02d}",
            "state": "Goa" if i % 2 == 0 else "Kerala",
            "sector": "Mining",
            "year": 2025,
            "pages": 1,
            "pages_total": 1,
            "unit": "table" if i == 2 else "page",
            "audit_type": library.FULL
            if i < 2
            else library.TABLE
            if i == 2
            else library.QUICK,
            "grades": {"RED": 0, "ORANGE": 0, "INFO": 0},
            "verified": int(i < 5),
            "reviewed": None,
            "kind": "saved" if i < 3 else "batch",
            "path": "unused",
            "full_run": None,
        }
        for i in range(35)
    ]
    monkeypatch.setattr(library_ui, "entries", lambda: items)
    monkeypatch.setattr(library_ui, "_preview", lambda *args: None)
    return items


def visible_reports(at):
    return [
        b.key.removeprefix("tf::open::") for b in at.button if b.label == "Open report"
    ]


def test_library_binders_render_every_match_and_reset_all_filters(
    no_keys, binder_library
):
    at = open_app(report=None, page="library")
    expected = [e["id"] for e in binder_library]
    assert visible_reports(at) == expected
    assert len(set(visible_reports(at))) == 35
    assert not any(b.key == "lib::more" for b in at.button)
    text = " ".join(m.value for m in at.markdown)
    assert "Deep Investigation Audits (3 Benchmark Reports)" in text
    assert "Automated Batch Triage (32 State Pollution Board Filings)" in text

    full_option = next(
        o for o in at.radio(key="lib::type").options if o.startswith("Full")
    )
    at.radio(key="lib::type").set_value(full_option).run()
    assert (
        visible_reports(at) == expected[:3]
    )  # full binder includes the standalone table
    assert "Automated Batch Triage" not in " ".join(m.value for m in at.markdown)
    quick_option = next(
        o for o in at.radio(key="lib::type").options if o.startswith("Quick")
    )
    at.radio(key="lib::type").set_value(quick_option).run()
    assert visible_reports(at) == expected[3:]  # 32 matches, not a hidden PAGE_SIZE cap
    assert "Deep Investigation Audits" not in " ".join(m.value for m in at.markdown)
    at.multiselect(key="lib::state").select("Goa").run()
    assert visible_reports(at) == [
        e["id"] for e in binder_library[3:] if e["state"] == "Goa"
    ]
    at.text_input(key="lib::q").input("Project 34").run()
    assert visible_reports(at) == [expected[-1]]
    at.checkbox(key="lib::verified").check().run()
    assert visible_reports(at) == []
    at.button(key="lib::reset-empty").click().run()
    assert not at.exception
    assert not at.checkbox(key="lib::verified").value
    assert at.text_input(key="lib::q").value == ""
    assert at.multiselect(key="lib::state").value == []
    assert at.radio(key="lib::type").value == "All (35)"
    assert visible_reports(at) == expected
    assert not any("Has human-verified findings" in m.value for m in at.markdown)


@has_results
def test_library_home_shows_totals_filters_and_upload(no_keys):
    at = open_app(report=None, page="library")
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    line = library.totals_line(library.totals(library.entries()))
    assert line in text  # totals computed, not hard-coded
    assert any(b.label == "Upload your EIA" for b in at.button)
    assert any("Saved audits are full runs" in c.value for c in at.caption)
    assert {m.label for m in at.multiselect} == {"State", "Sector", "Year"}
    assert any(r.label == "Audit type" for r in at.radio)
    n = len([b for b in at.button if b.label == "Open report"])
    at.checkbox(key="lib::red").check().run()
    red = len([b for b in at.button if b.label == "Open report"])
    assert red == sum(e["grades"]["RED"] > 0 for e in library.entries()) and red <= n
    at.text_input(key="lib::q").input("Cuddalore").run()
    assert len([b for b in at.button if b.label == "Open report"]) == 1


@has_results
def test_library_filter_has_human_verified_findings(no_keys, binder_library):
    at = open_app(report=None, page="library")
    at.checkbox(key="lib::verified").check().run()
    assert not at.exception
    shown = len([b for b in at.button if b.label == "Open report"])
    assert shown == sum(1 for e in binder_library if e["verified"]) >= 1
    assert any(
        "Has human-verified findings" in m.value for m in at.markdown
    )  # its chip
    at.button(key="lib::reset").click().run()  # Reset filters
    assert visible_reports(at) == [e["id"] for e in binder_library]
    assert not at.checkbox(key="lib::verified").value


@has_results
def test_open_a_report_and_go_back(no_keys):
    at = open_app(report=None, page="library")
    at.button(key=f"tf::open::{GN}").click().run()
    assert not at.exception
    assert at.query_params.get("report") in (GN, [GN])
    assert [t.label.split(" (")[0] for t in at.tabs][:2] == ["Overview", "Contradictions"]
    assert any(b.label == "Back to library" for b in at.button)
    at.button(key="tf::back").click().run()
    assert not at.exception
    assert not at.tabs and any(b.label == "Upload your EIA" for b in at.button)


@has_results
def test_quick_check_opens_in_the_lighter_view(no_keys, batch):
    at = open_app(report=None, page="library")
    text = "\n".join(m.value for m in at.markdown)
    assert "5 EIAs checked" in text or "EIAs checked" in text
    opt = next(o for o in at.radio(key="lib::type").options if "Quick" in o)
    at.radio(key="lib::type").set_value(opt).run()
    assert len([b for b in at.button if b.label == "Open report"]) == 2
    at.button(key="tf::open::sample_quick_mine_odisha_2025").click().run()
    assert not at.exception
    assert any(library.QUICK_NOTICE in w.value for w in at.warning)
    labels = [t.label.split(" (")[0] for t in at.tabs]  # only the quick check's sections
    assert labels[0] == "Overview" and set(labels) <= {"Overview", "Contradictions", "Species & nature"}
    text = "\n".join(m.value for m in at.markdown)
    assert "Checks that ran" in text and "Not run for this report" in text
    assert "GBIF not called" in text  # the reason a check did not run


@has_results
def test_upload_screen_without_a_key(no_keys):
    at = open_app(report=None, view="upload")
    assert not at.exception
    assert any("up to 30 pages you choose" in c.value for c in at.caption)
    text = "\n".join(m.value for m in at.markdown)
    for level in ("Quick check (free, whole report)", "Deep audit (chosen pages, live)",
                  "Full audit (your own key or run locally"):
        assert level in text
    assert any("No key: the free checks run" in c.value for c in at.caption)
    text = "\n".join(m.value for m in at.markdown)
    assert "Without a key" in text and "With a key" in text
    assert any(b.label == "Back to library" for b in at.button)
