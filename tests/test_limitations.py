"""docs/LIMITATIONS.md exists, covers the known failure cases and is linked from Method & limits."""

from pathlib import Path

from tigerfish.ui import method

ROOT = Path(__file__).resolve().parent.parent
TOPICS = ("GBIF", "mobile", "False alarms", "p.1143", "proposed", "Hindi", "Part vs total",
          "Thresholds", "Triage", "26 October 2021", "non-government", "not a verdict")


def test_limitations_file_covers_each_topic():
    text = (ROOT / "docs" / "LIMITATIONS.md").read_text(encoding="utf-8")
    for topic in TOPICS:
        assert topic in text, topic


def test_method_tab_links_and_shows_the_file():
    assert "docs/LIMITATIONS.md" in method.METHOD and method.LIMITATIONS_URL in method.METHOD
    shown = method.limitations_text()
    assert shown and not shown.startswith("# ")           # title line dropped inside the tab
    assert "not a verdict" in shown
