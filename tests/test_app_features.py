"""The new UI pieces appear in the replay app (AppTest, no API keys, no network)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest  # noqa: F401
from apptest import open_app

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(), reason="no results/")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    return open_app(timeout=60)


def plotly_titles(at):
    return [c.proto.spec for c in at.get("plotly_chart")]


def test_map_crops_cost_chart_and_pack_button(app):
    assert not app.exception
    text = "\n".join(m.value for m in app.markdown)
    assert "Where the flagged species are actually recorded" in text
    assert "Highlighted lines, zoomed" in text
    assert "Cost per full audit, by triage mode" in text
    charts = plotly_titles(app)
    assert any("Scattergeo" in c or "scattergeo" in c for c in charts)       # species map
    assert any('"type":"bar"' in c.replace(" ", "") for c in charts)         # cost chart
    labels = [b.proto.label for b in app.get("download_button")]
    assert "RTI + public hearing pack (.zip)" in labels


def test_indira_point_map_shows_all_five_mammals(app):
    app.selectbox[0].select("Indira Point REIA, Table 3.16 (as published by Scroll.in)").run()
    assert not app.exception
    geo = [c for c in plotly_titles(app) if "scattergeo" in c]
    assert geo and all(name in geo[0] for name in
                       ("Axis axis", "Felis chaus", "Funambulus pennantii", "Muntiacus muntjak", "Rusa unicolor"))
