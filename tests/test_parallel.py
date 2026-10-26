"""Parallel calls, retries and resumable cache (no network, no cost)."""

import json
import random
import threading
import time

import httpx
import openai
import pytest

from tigerfish import claims, contradictions as ct, llm


def jitter_sleep():
    time.sleep(random.uniform(0, 0.02))   # make threads finish out of order


# ---------- run_parallel ----------

def test_results_keep_input_order():
    items = list(range(40))
    out, stop = llm.run_parallel(lambda x: (jitter_sleep(), x * x)[1], items, workers=6)
    assert out == [x * x for x in items] and stop is None


def test_no_more_than_workers_at_once():
    lock, now, peak = threading.Lock(), [0], [0]

    def fn(_):
        with lock:
            now[0] += 1
            peak[0] = max(peak[0], now[0])
        time.sleep(0.01)
        with lock:
            now[0] -= 1
    llm.run_parallel(fn, range(30), workers=6)
    assert 1 < peak[0] <= 6


@pytest.mark.parametrize("workers", [1, 6])
def test_cost_cap_stops_where_sequential_stops(monkeypatch, workers):
    monkeypatch.setattr(llm, "session_cost_usd", 0.0)

    def fn(x):
        jitter_sleep()
        with llm._lock:
            llm.session_cost_usd += 0.2     # real cost above the 0.15 estimate
        return x
    out, stop = llm.run_parallel(fn, list(range(10)), workers=workers,
                                 estimate=lambda x: 0.15, max_cost_usd=0.5)
    # sequential rule: 0+.15 ok, .2+.15 ok, .4+.15 > .5 -> stop at item 2
    assert stop == 2 and out[:2] == [0, 1] and out[2:] == [None] * 8


def test_worker_error_is_raised():
    def fn(x):
        if x == 3:
            raise ValueError("boom")
        return x
    with pytest.raises(ValueError):
        llm.run_parallel(fn, range(10), workers=4)


# ---------- retries ----------

def _error(status, headers=None):
    req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    resp = httpx.Response(status, request=req, headers=headers or {})
    cls = openai.RateLimitError if status == 429 else openai.InternalServerError \
        if status >= 500 else openai.BadRequestError
    return cls("err", response=resp, body=None)


class FlakyClient:
    def __init__(self, errors):
        self.errors, self.calls = list(errors), 0
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def test_retries_429_and_5xx_with_backoff(monkeypatch):
    fake = FlakyClient([_error(429, {"retry-after": "7"}), _error(503), _error(500)])
    monkeypatch.setattr(llm, "client", lambda: fake)
    slept = []
    assert llm._create("m", [], {}, sleep=slept.append) == "ok"
    assert fake.calls == 4 and len(slept) == 3
    assert slept[0] >= 7                        # Retry-After respected
    assert 1.0 <= slept[1] <= 4.0 and 2.0 <= slept[2] <= 8.0   # base 2s x 2^k x [0.5, 1]


def test_client_errors_are_not_retried(monkeypatch):
    fake = FlakyClient([_error(400)])
    monkeypatch.setattr(llm, "client", lambda: fake)
    with pytest.raises(openai.BadRequestError):
        llm._create("m", [], {}, sleep=lambda s: None)
    assert fake.calls == 1


def test_gives_up_after_max_retries(monkeypatch):
    fake = FlakyClient([_error(503)] * (llm.MAX_RETRIES + 1))
    monkeypatch.setattr(llm, "client", lambda: fake)
    with pytest.raises(openai.InternalServerError):
        llm._create("m", [], {}, sleep=lambda s: None)
    assert fake.calls == llm.MAX_RETRIES + 1


def test_backoff_is_capped():
    assert all(llm.backoff_seconds(20) <= llm.BACKOFF_MAX_S for _ in range(50))


# ---------- resumable cache ----------

def test_broken_cache_file_is_a_miss(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    path = tmp_path / "x.json"
    path.write_text('{"choices": [', encoding="utf-8")    # half-written by an old crash
    assert llm._read_cache(path) is None
    llm._write_cache(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert not list(tmp_path.glob("*.tmp"))


# ---------- pipeline: parallel == sequential ----------

PAGE = ("A total of 330 species of fauna are recorded from the Campbell Bay National Park. "
        "The project area is 166 sq km. Mangroves cover 12 ha near the bay.")


def fake_chat(model, messages, **kwargs):
    """Deterministic reply per prompt, finishing out of order."""
    jitter_sleep()
    text = json.dumps(messages)
    if model == llm.LIGHTNING and "Page " in text:
        n = int(text.split("Page ")[1].split(":")[0].split(" ")[0])
        return json.dumps({"claims": [{"type": "count", "subject": "Campbell Bay fauna",
                                       "value": 330 + n % 3, "unit": "species",
                                       "quote": "330 species of fauna", "context": "x"}]})
    return '{"answers": []}'


def test_extract_claims_parallel_matches_sequential(monkeypatch, tmp_path):
    monkeypatch.setattr(claims, "LEDGER_DIR", tmp_path)
    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(llm, "is_cached", lambda *a, **k: True)
    pages = [{"page": n, "text": PAGE, "needs_vision": False, "image_path": None,
              "error": None} for n in range(1, 25)]
    monkeypatch.setattr(llm, "WORKERS", 1)
    seq = claims.extract_claims(pages)
    monkeypatch.setattr(llm, "WORKERS", 6)
    par = claims.extract_claims(pages)
    assert par == seq and len(seq) > 24


def test_triage_parallel_matches_sequential(monkeypatch):
    cands = [{"kind": "numeric", "claims": [
        {"id": f"a{i}", "page": i, "quote": f"q{i}", "subject": "s", "value": i, "unit": "ha"},
        {"id": f"b{i}", "page": i + 100, "quote": f"r{i}", "subject": "s", "value": i + 1,
         "unit": "ha"}]} for i in range(30)]

    def answers(model, messages, **kwargs):   # depends only on the prompt
        jitter_sleep()
        text = json.dumps(messages)
        return json.dumps({"answers": [{"pair": k, "answer": ("yes", "no", "unsure")[
            sum(map(ord, text + str(k))) % 3]} for k in range(1, ct.TRIAGE_QUOTE_BATCH + 1)]})
    monkeypatch.setattr(llm, "chat", answers)
    monkeypatch.setattr(llm, "WORKERS", 1)
    seq = ct._triage_pass(cands, None, ct.TRIAGE_QUOTE_BATCH)
    monkeypatch.setattr(llm, "WORKERS", 6)
    par = ct._triage_pass(cands, None, ct.TRIAGE_QUOTE_BATCH)
    assert par == seq
