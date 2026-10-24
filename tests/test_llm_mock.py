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


def test_think_block_is_stripped_in_mock_mode(mock_mode):
    reply = llm.chat(llm.LIGHTNING, MSGS, mock_key="think_wrapped")
    assert "<think>" not in reply and "The user wants" not in reply
    assert json.loads(reply)["claims"][0]["page"] == 12


@pytest.mark.parametrize("raw, clean", [
    ("<think>plan</think>\nHello!", "Hello!"),
    ("<think>a</think>Hi <think>b</think>there", "Hi there"),
    ("reasoning with no opening tag...</think>\nHello!", "Hello!"),  # template opened <think>
    ("Hello!", "Hello!"),
    (None, ""),
])
def test_strip_think(raw, clean):
    assert llm.strip_think(raw) == clean


def test_thinking_off_by_default_for_lightning(monkeypatch, tmp_path):
    """Real-mode path with a fake client: checks what would be sent to the API."""
    monkeypatch.delenv("TIGERFISH_MOCK", raising=False)
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "usage.jsonl")
    sent = []

    class FakeResponse:
        def model_dump(self):
            return {"choices": [{"finish_reason": "stop",
                                 "message": {"content": "<think>x</think>Hello!"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    sent.append(kw)
                    return FakeResponse()

    monkeypatch.setattr(llm, "client", lambda: FakeClient)
    assert llm.chat(llm.LIGHTNING, MSGS) == "Hello!"
    assert sent[-1]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    llm.chat(llm.ULTRA, MSGS)
    assert "extra_body" not in sent[-1]                      # Ultra: model default
    llm.chat(llm.ULTRA, MSGS, thinking=True)
    assert sent[-1]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True
