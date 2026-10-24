import json

import pytest

from tigerfish import llm

MSGS = [{"role": "user", "content": "anything"}]


@pytest.fixture
def mock_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("TIGERFISH_MOCK", "1")
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "usage.jsonl")
    return tmp_path


def test_claim_extraction_fixture(mock_mode):
    data = json.loads(llm.chat(llm.LIGHTNING, MSGS, mock_key="claim_extraction"))
    assert all({"page", "quote", "type"} <= c.keys() for c in data["claims"])


def test_contradiction_fixture(mock_mode):
    data = json.loads(llm.chat(llm.ULTRA, MSGS, mock_key="contradiction_check"))
    assert {f["grade"] for f in data["findings"]} <= {"RED", "ORANGE", "GREY"}


def test_mock_is_logged(mock_mode):
    llm.chat(llm.ULTRA, MSGS, mock_key="contradiction_check")
    entry = json.loads((mock_mode / "usage.jsonl").read_text().splitlines()[-1])
    assert entry["mode"] == "MOCK"


def test_missing_fixture_raises(mock_mode):
    with pytest.raises(FileNotFoundError):
        llm.chat(llm.ULTRA, MSGS, mock_key="nope")


def test_real_mode_is_default(monkeypatch):
    monkeypatch.delenv("TIGERFISH_MOCK", raising=False)
    assert not llm.is_mock()
