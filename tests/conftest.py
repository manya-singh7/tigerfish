import pytest


@pytest.fixture(autouse=True)
def feedback_file(tmp_path, monkeypatch):
    """Every test gets its own reviewer-feedback file, never feedback/feedback.json."""
    path = tmp_path / "feedback.json"
    monkeypatch.setenv("TIGERFISH_FEEDBACK", str(path))
    return path
