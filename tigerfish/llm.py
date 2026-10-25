"""Single entry point for every model call: Nebius Token Factory via the openai SDK.

- Keys come from .env (NEBIUS_API_KEY).
- Every response is cached in cache/llm/ keyed by (model, messages, kwargs),
  so the same model is never called twice on the same input.
- Token usage (and cost, if prices are filled in) is appended to logs/usage.jsonl.
- MOCK mode: set TIGERFISH_MOCK=1 and chat(..., mock_key="claim_extraction")
  returns tests/fixtures/claim_extraction.json instead of calling Nebius.
- Reasoning: thinking is off by default for Lightning (see DEFAULT_THINKING),
  and any <think>...</think> block is always stripped from the returned text.
- Images: put image_part(path) in a message's content list (Super-VL). The cache
  key uses the image's sha256, not the base64 text.
- Cost: session_cost_usd adds up real (uncached) calls; is_cached() tells you
  in advance whether a call would be free.
"""

import base64
import hashlib
import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import os

from tigerfish import trace

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "llm"
USAGE_LOG = ROOT / "logs" / "usage.jsonl"
FIXTURES_DIR = ROOT / "tests" / "fixtures"
BASE_URL = "https://api.tokenfactory.nebius.com/v1/"

ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"   # whole-document reasoning, final verdicts
SUPER_VL = "nvidia/Nemotron-3.5-Super-VL"     # scanned pages, tables, maps (image input)
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"   # fast, cheap claim extraction

# Reasoning on/off per model when chat(thinking=None). Sent as
# extra_body={"chat_template_kwargs": {"enable_thinking": ...}}. Lightning
# otherwise writes its reasoning as plain text into the reply and runs out
# of tokens. Ultra and Super-VL return reasoning in a separate
# reasoning_content field, so their content is clean already.
DEFAULT_THINKING = {LIGHTNING: False}

# USD per 1M tokens as (input, output). Models left out are logged with cost_usd = None.
# Lightning and Ultra: third-party listing of Nebius Token Factory prices
# (typingmind.com, Aug 2026). Super-VL: from the Token Factory model catalog.
# All: verify on the Nebius billing page.
PRICES = {
    LIGHTNING: (0.06, 0.24),
    ULTRA: (1.00, 3.00),
    SUPER_VL: (0.30, 0.90),   # from catalog, verify on billing page
}

load_dotenv(ROOT / ".env")
_client = None
session_cost_usd = 0.0   # cost of real (uncached) API calls made by this process


def client():
    """Lazily build one shared OpenAI client pointed at Nebius."""
    global _client
    if _client is None:
        key = os.getenv("NEBIUS_API_KEY")
        if not key:
            raise RuntimeError("NEBIUS_API_KEY is missing; add it to .env")
        _client = OpenAI(base_url=BASE_URL, api_key=key)
    return _client


def image_part(path):
    """OpenAI-style image content part with the file inlined as a base64 data URL."""
    path = Path(path)
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def _hash_images(messages):
    """Copy of messages with each inline image replaced by its sha256 (for cache keys)."""
    out = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            content = [
                {"type": "image_url", "image_sha256": hashlib.sha256(
                    part["image_url"]["url"].encode("ascii")).hexdigest()}
                if part.get("type") == "image_url" else part
                for part in content]
            msg = {**msg, "content": content}
        out.append(msg)
    return out


def _cache_key(model, messages, kwargs):
    # Text-only messages hash exactly as before, so existing cache entries stay valid.
    payload = json.dumps({"model": model, "messages": _hash_images(messages), "kwargs": kwargs},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _with_thinking(model, thinking, kwargs):
    """kwargs plus the chat_template_kwargs switch for this model's thinking setting."""
    if thinking is None:
        thinking = DEFAULT_THINKING.get(model)
    if thinking is None:
        return kwargs
    extra_body = dict(kwargs.get("extra_body") or {})
    extra_body["chat_template_kwargs"] = {
        **extra_body.get("chat_template_kwargs", {}), "enable_thinking": thinking}
    return {**kwargs, "extra_body": extra_body}


def is_cached(model, messages, thinking=None, **kwargs):
    """True if chat() with these arguments would be answered from the cache (free)."""
    if is_mock():
        return True
    key = _cache_key(model, messages, _with_thinking(model, thinking, kwargs))
    return (CACHE_DIR / f"{key}.json").exists()


def cost_usd(model, prompt_tokens, completion_tokens):
    """Cost in USD from PRICES, or None if the model has no price."""
    if model not in PRICES:
        return None
    price_in, price_out = PRICES[model]
    return (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000


def is_mock():
    """True when TIGERFISH_MOCK=1 (checked on every call so tests can toggle it)."""
    return os.getenv("TIGERFISH_MOCK") == "1"


def _mock_reply(model, mock_key):
    """Return a fixture's JSON as reply text, the way a real model would send it."""
    if mock_key is None:
        reply = json.dumps({"mock": True, "note": "no mock_key given"})
    else:
        path = FIXTURES_DIR / f"{mock_key}.json"
        raw = FIXTURES_DIR / f"{mock_key}.txt"   # raw reply text, e.g. with <think>
        if path.exists():
            reply = json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False)
        elif raw.exists():
            reply = raw.read_text(encoding="utf-8")
        else:
            raise FileNotFoundError(f"MOCK mode: no fixture at {path} or {raw}")
    _log_usage(model, None, cached=False, mock=True)
    return reply


def _log_usage(model, usage, cached, mock=False, seconds=None):
    global session_cost_usd
    prompt = usage.get("prompt_tokens", 0) if usage else 0
    completion = usage.get("completion_tokens", 0) if usage else 0
    cost = cost_usd(model, prompt, completion)
    if cost is not None and not cached and not mock:
        session_cost_usd += cost
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model,
             "mode": "MOCK" if mock else "REAL", "cached": cached,
             "prompt_tokens": prompt, "completion_tokens": completion, "cost_usd": cost,
             "seconds": seconds}
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    tag = "MOCK" if mock else "cache hit" if cached else "api call"
    print(f"[llm] {model} ({tag}): {prompt} in + {completion} out tokens")


def strip_think(text):
    """Remove <think>...</think> reasoning from a reply.

    Also handles a reply that starts mid-reasoning (the chat template opened
    <think> in the prompt), by dropping everything up to a stray </think>.
    """
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


def chat(model, messages, mock_key=None, thinking=None, cache=True, **kwargs):
    """Call a chat model and return the reply text. Cached; logs token usage.

    thinking: True/False turns the model's reasoning on/off; None uses
      DEFAULT_THINKING for this model (off for Lightning, model default otherwise).
      Reasoning never ends up in the returned text either way.
    cache: False skips the cache lookup (the fresh reply is still saved).
    mock_key names the fixture used in MOCK mode (ignored in real mode).
    kwargs are passed straight to client.chat.completions.create
    (e.g. temperature, max_tokens, response_format).
    """
    if is_mock():
        return strip_think(_mock_reply(model, mock_key))

    kwargs = _with_thinking(model, thinking, kwargs)
    key = _cache_key(model, messages, kwargs)
    path = CACHE_DIR / f"{key}.json"
    trace.record("llm", path)
    if cache and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        _log_usage(model, data.get("usage"), cached=True)
        return strip_think(data["choices"][0]["message"]["content"])

    started = time.perf_counter()
    response = client().chat.completions.create(model=model, messages=messages, **kwargs)
    data = response.model_dump()
    data["_latency_s"] = round(time.perf_counter() - started, 3)   # measured, for cost reports
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _log_usage(model, data.get("usage"), cached=False, seconds=data["_latency_s"])
    if data["choices"][0]["finish_reason"] == "length":
        print(f"[llm] warning: {model} hit max_tokens; reply may be cut off")
    return strip_think(data["choices"][0]["message"]["content"])


def list_models():
    """Return the ids of all models available to this API key (not cached)."""
    if is_mock():
        return [ULTRA, SUPER_VL, LIGHTNING]
    return [m.id for m in client().models.list()]
