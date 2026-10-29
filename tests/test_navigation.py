"""Top menu, Home page and report sections (tigerfish/ui/pages.py, tigerfish/ui/report_view.py)."""

import sys
import types
from pathlib import Path

import pytest

from apptest import GN, open_app
from tigerfish import library
from tigerfish.ui import data, report_view
from tigerfish.ui import pages

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")


def labels(at):
    return [t.label.split(" (")[0] for t in at.tabs]


def test_home_is_the_landing_page(no_keys):
    at = open_app(report=None)
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    assert pages.TAGLINE in text and pages.PURPOSE in text and pages.BUILT_WITH in text
    assert pages.TIGERFISH_STORY in text and pages.SCROLL_URL in text     # the tiger fish slip
    t = library.totals(library.entries())
    assert library.totals_line(t) in text                                 # one live sentence
    assert not at.metric                                                  # no stat banner
    assert any(b.label == "Open report" for b in at.button)               # the library below
    assert not at.tabs


def test_home_search_goes_into_the_library(no_keys):
    at = open_app(report=None)
    at.text_input(key="home::q").input("Cuddalore").run()
    assert not at.exception
    assert len([b for b in at.button if b.label == "Open report"]) == 1


def test_overview_is_top_three_verified_slips_and_one_sentence(no_keys):
    at = open_app()
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    report = data.load(GN)
    assert report_view.totals_sentence(report) in text
    slips = [m.value for m in at.tabs[0].markdown if 'class="tf-slip' in m.value]
    assert len(slips) == report_view.TOP_FLAGS
    assert all("Verified by a person" in v for v in slips)


def test_old_report_link_opens_the_report(no_keys):
    at = open_app()                                        # /?report=<id>
    assert not at.exception
    assert labels(at) == list(report_view.ORDER)
    assert any(t.label.startswith("Contradictions (") for t in at.tabs)


def test_every_finding_is_in_exactly_one_section():
    for r in data.reports():
        report = data.load(r["id"])
        by = report_view.split(report["findings"])
        ids = [f["id"] for fs in by.values() for f in fs]
        assert sorted(ids) == sorted(f["id"] for f in report["findings"])


def test_sections_that_do_not_apply_are_hidden_with_a_reason():
    shown, hidden = report_view.plan(data.load("indira_point_table_3_16"))
    names = [s for s, _ in shown]
    assert report_view.CONTRA not in names and report_view.COPIED not in names
    assert all(why for _, why in hidden)
    assert {s for s, _ in hidden} | set(names) == set(report_view.ORDER)


def test_quick_check_gets_only_its_own_sections(no_keys, monkeypatch):
    monkeypatch.setenv("TIGERFISH_BATCH_DIR", str(ROOT / "tests" / "fixtures" / "library" / "batch"))
    entry = library.find(library.entries(), "sample_quick_mine_odisha_2025")
    shown, hidden = report_view.plan(library.load(entry), quick=True)
    assert {s for s, _ in shown} <= set(report_view.QUICK_SECTIONS)
    assert report_view.ACTION in {s for s, _ in hidden}


def test_counts_in_labels():
    report = data.load(GN)
    shown, _ = report_view.plan(report)
    counts = dict(shown)
    by = report_view.split(report["findings"])
    assert counts[report_view.CONTRA] == len(by[report_view.CONTRA])
    assert report_view.label(report_view.CONTRA, 1234) == "Contradictions (1,234)"
    assert report_view.label(report_view.OVERVIEW, None) == "Overview"


def test_quality_hook_uses_a_quality_module(monkeypatch):
    seen = []
    mod = types.ModuleType("tigerfish.ui.quality")
    mod.render = lambda report: seen.append(report["id"])
    monkeypatch.setitem(sys.modules, "tigerfish.ui.quality", mod)
    report_view.quality({"id": "x", "findings": []})
    assert seen == ["x"]
