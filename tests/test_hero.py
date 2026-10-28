"""The "aha first" hero card: one configurable finding above everything else."""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest  # noqa: F401
from apptest import open_app

from tigerfish.ui import data, hero

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(),
                                reason="no results/ (run scripts/export_results.py)")
BANNED = ("lie", "liar", "fraud", "fake", "fabricat", "dishonest", "cheat", "violat")


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")


def app():
    return open_app(timeout=60)


def test_configured_finding_exists_in_saved_results():
    report = data.load(hero.HERO_REPORT_ID)
    f = hero.hero_finding(report)
    assert f is not None and f["id"] == hero.HERO_FINDING_ID
    assert f["images"]                                    # the hero shows page images


def test_headline_is_one_neutral_sentence():
    text = hero.HERO_HEADLINE
    assert text.endswith(".") and not re.search(r"[.!?]\s+[A-Z]", text)
    words = set(re.findall(r"[a-z]+", text.lower()))
    assert not any(w.startswith(b) for w in words for b in BANNED)
    assert "3 months" in text and "December 2020" in text and "February 2021" in text


def test_headline_matches_the_finding_evidence():
    f = hero.hero_finding(data.load(hero.HERO_REPORT_ID))
    assert "3 months" in f["quotes"][0]["text"]
    assert "14 to 22 December 2020" in f["quotes"][1]["text"]
    assert hero.headline(f) == hero.HERO_HEADLINE


def test_other_reports_and_missing_ids_have_no_hero(monkeypatch):
    assert hero.hero_finding(data.load("indira_point_table_3_16")) is None
    assert hero.hero_finding(None) is None
    monkeypatch.setattr(hero, "HERO_FINDING_ID", "no-such-id")
    assert hero.hero_finding(data.load(hero.HERO_REPORT_ID)) is None


def test_headline_falls_back_to_the_finding_message(monkeypatch):
    monkeypatch.setattr(hero, "HERO_HEADLINE", None)
    f = hero.hero_finding(data.load(hero.HERO_REPORT_ID))
    assert hero.headline(f) == f["message"]


def test_hero_is_the_first_thing_on_the_page(no_keys):
    at = app()
    assert not at.exception
    values = [m.value for m in at.markdown]
    first = next(i for i, v in enumerate(values) if "<style>" not in v)
    assert "TigerFish found this in the" in values[first]
    assert hero.HERO_HEADLINE.split(";")[0] in values[first]
    assert "Judged by Ultra" in values[first]                     # model badges on the hero
    title = next(i for i, v in enumerate(values) if 'class="tf-title"' in v)
    assert first < title
    assert at.button(key="hero_see_all").label == "See all findings"


def test_see_all_findings_closes_the_hero(no_keys):
    at = app()
    at.button(key="hero_see_all").click().run()
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    assert "TigerFish found this in the" not in text
    assert "What would clear this" in text                        # findings are still shown


def test_hero_hidden_for_another_report(no_keys):
    at = app()
    at.selectbox[0].select(data.reports()[1]["title"]).run()
    assert not at.exception
    assert not any("TigerFish found this in the" in m.value for m in at.markdown)


def test_app_runs_when_the_hero_id_is_wrong(no_keys, monkeypatch):
    monkeypatch.setattr(hero, "HERO_FINDING_ID", "no-such-id")
    at = app()
    assert not at.exception
    assert not any("TigerFish found this in the" in m.value for m in at.markdown)
