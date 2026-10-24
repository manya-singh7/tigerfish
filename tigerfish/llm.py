"""Single entry point for every model call: Nebius Token Factory via the openai SDK.

- Keys come from .env (NEBIUS_API_KEY).
- Every response is cached in cache/llm/ keyed by (model, messages, kwargs),
  so the same model is never called twice on the same input.
- Token usage (and cost, if prices are filled in) is appended to logs/usage.jsonl.
- MOCK mode: set TIGERFISH_MOCK=1 and chat(..., mock_key="claim_extraction")
  returns tests/fixtures/claim_extraction.json instead of calling Nebius.
"""

import hashlib
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import os

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "llm"
USAGE_LOG = ROOT / "logs" / "usage.jsonl"
FIXTURES_DIR = ROOT / "tests" / "fixtures"
BASE_URL = "https://api.tokenfactory.nebius.com/v1/"

ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"   # whole-document reasoning, final verdicts
SUPER_VL = "nvidia/Nemotron-3.5-Super-VL"     # scanned pages, tables, maps (image input)
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"   # fast, cheap claim extraction

# USD per 1M tokens as (input, output). Fill in from the Nebius pricing page;
# models left out are logged with cost_usd = None.
PRICES = {}

load_dotenv(ROOT / ".env")
_client = None


def client():
    """Lazily build one shared OpenAI client pointed at Nebius."""
    global _client
    if _client is None:
        key = os.getenv("NEBIUS_API_KEY")
        if not key:
            raise RuntimeError("NEBIUS_API_KEY is missing; add it to .env")
        _client = OpenAI(base_url=BASE_URL, api_key=key)
    return _client


def _cache_key(model, messages, kwargs):
    payload = json.dumps({"model": model, "messages": messages, "kwargs": kwargs},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_mock():
    """True when TIGERFISH_MOCK=1 (checked on every call so tests can toggle it)."""
    return os.getenv("TIGERFISH_MOCK") == "1"


def _mock_reply(model, mock_key):
    """Return a fixture's JSON as reply text, the way a real model would send it."""
    if mock_key is None:
        reply = json.dumps({"mock": True, "note": "no mock_key given"})
    else:
        path = FIXTURES_DIR / f"{mock_key}.json"
        if not path.exists():
            raise FileNotFoundError(f"MOCK mode: no fixture at {path}")
        reply = json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False)
    _log_usage(model, None, cached=False, mock=True)
    return reply


def _log_usage(model, usage, cached, mock=False):
    prompt = usage.get("prompt_tokens", 0) if usage else 0
    completion = usage.get("completion_tokens", 0) if usage else 0
    cost = None
    if model in PRICES:
        price_in, price_out = PRICES[model]
        cost = (prompt * price_in + completion * price_out) / 1_000_000
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model,
             "mode": "MOCK" if mock else "REAL", "cached": cached,
             "prompt_tokens": prompt, "completion_tokens": completion, "cost_usd": cost}
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    tag = "MOCK" if mock else "cache hit" if cached else "api call"
    print(f"[llm] {model} ({tag}): {prompt} in + {completion} out tokens")


def chat(model, messages, mock_key=None, **kwargs):
    """Call a chat model and return the reply text. Cached; logs token usage.

    mock_key names the fixture used in MOCK mode (ignored in real mode).
    kwargs are passed straight to client.chat.completions.create
    (e.g. temperature, max_tokens, response_format).
    """
    if is_mock():
        return _mock_reply(model, mock_key)

    key = _cache_key(model, messages, kwargs)
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        _log_usage(model, data.get("usage"), cached=True)
        return data["choices"][0]["message"]["content"]

    response = client().chat.completions.create(model=model, messages=messages, **kwargs)
    data = response.model_dump()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _log_usage(model, data.get("usage"), cached=False)
    return data["choices"][0]["message"]["content"]


def list_models():
    """Return the ids of all models available to this API key (not cached)."""
    if is_mock():
        return [ULTRA, SUPER_VL, LIGHTNING]
    return [m.id for m in client().models.list()]
