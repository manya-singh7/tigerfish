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
- Speed: run_parallel() runs calls on a thread pool (WORKERS threads), results in input
  order, with an optional cost cap. 429 / 5xx / connection errors are retried with
  exponential backoff + jitter (MAX_RETRIES). Cache files are written atomically, so an
  interrupted run resumes from the cache without paying for any call twice.
"""

import base64
import hashlib
import json
import os
import random
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import openai
from dotenv import load_dotenv
from openai import OpenAI

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

WORKERS = 6              # parallel API calls in run_parallel()
MAX_RETRIES = 6          # retries of one call on 429 / 5xx / connection errors
BACKOFF_BASE_S = 2.0     # wait before retry k: random(0.5, 1) x min(BACKOFF_MAX_S, base x 2^k)
BACKOFF_MAX_S = 60.0
REQUEST_TIMEOUT_S = 600  # Ultra with reasoning can take minutes on long pages
RESERVE_FACTOR = 2.0     # cost cap: a running call is counted as this x its estimate

load_dotenv(ROOT / ".env")
_client = None
_lock = threading.Lock()  # guards session_cost_usd, retry_stats, the usage log and the client
session_cost_usd = 0.0   # cost of real (uncached) API calls made by this process
retry_stats = {"retries": 0, "rate_limited": 0, "server_errors": 0, "connection_errors": 0}
call_stats = {}   # model -> {api_calls, cache_hits, prompt_tokens, completion_tokens, cost_usd, api_seconds}


def client():
    """Lazily build one shared OpenAI client pointed at Nebius."""
    global _client
    with _lock:
        if _client is None:
            key = os.getenv("NEBIUS_API_KEY")
            if not key:
                raise RuntimeError("NEBIUS_API_KEY is missing; add it to .env")
            # Retries are ours (_create), so the SDK's own are off.
            _client = OpenAI(base_url=BASE_URL, api_key=key, max_retries=0,
                             timeout=REQUEST_TIMEOUT_S)
        return _client


def _retry_kind(error):
    """'rate_limited' | 'server_errors' | 'connection_errors' if worth retrying, else None."""
    if isinstance(error, openai.RateLimitError):
        return "rate_limited"
    if isinstance(error, openai.APIStatusError) and error.status_code >= 500:
        return "server_errors"
    if isinstance(error, openai.APIConnectionError):   # includes timeouts
        return "connection_errors"
    return None


def backoff_seconds(attempt, retry_after=None):
    """Exponential backoff with jitter; never shorter than the server's Retry-After."""
    wait_s = min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** attempt) * random.uniform(0.5, 1.0)
    return max(wait_s, retry_after or 0)


def _retry_after(error):
    try:
        return float(error.response.headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return None


def _create(model, messages, kwargs, sleep=time.sleep):
    """client.chat.completions.create with retries on 429 / 5xx / connection errors."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return client().chat.completions.create(model=model, messages=messages, **kwargs)
        except Exception as e:   # noqa: BLE001 (re-raised unless retryable)
            kind = _retry_kind(e)
            if kind is None or attempt == MAX_RETRIES:
                raise
            delay = backoff_seconds(attempt, _retry_after(e))
            with _lock:
                retry_stats["retries"] += 1
                retry_stats[kind] += 1
            print(f"[llm] {model}: {type(e).__name__}; retry {attempt + 1}/{MAX_RETRIES} "
                  f"in {delay:.1f}s")
            sleep(delay)


def _read_cache(path):
    """Cached response dict, or None (missing, or a broken file left by an old crash)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"[llm] ignoring broken cache file {path.name}")
        return None


def _write_cache(path, data):
    """Write to a temp file, then rename: a killed run never leaves half a file behind."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _call(model, messages, kwargs, path):
    """Real API call, timed and cached. Returns the response dict."""
    started = time.perf_counter()
    response = _create(model, messages, kwargs)
    data = response.model_dump()
    data["_latency_s"] = round(time.perf_counter() - started, 3)   # measured, incl. retries
    _write_cache(path, data)
    return data


def run_parallel(fn, items, workers=None, estimate=None, max_cost_usd=None):
    """fn(item) for every item on a thread pool. Returns (results in input order, stop).

    Cost cap (estimate and max_cost_usd both given): an item starts only if
    real spend since this call + RESERVE_FACTOR x the estimates of the items still
    running + estimate(item) stays within max_cost_usd (estimates can be low, so running
    calls are counted generously). If it does not fit, wait for the running items; if it
    still does not fit with nothing running, stop: `stop` is that item's index, and its
    result and all later ones are None. That is the sequential rule (spent + estimate >
    cap -> stop), so a cached re-run stops at the same place.
    workers=1 runs in this thread, one item at a time (the old sequential behaviour).
    Ctrl+C: no new calls start; calls already running finish and are cached.
    """
    workers = workers or WORKERS
    results, start = [None] * len(items), session_cost_usd
    capped = estimate is not None and max_cost_usd is not None

    def fits(est, reserved):
        return session_cost_usd - start + reserved + est <= max_cost_usd

    if workers == 1:
        for i, item in enumerate(items):
            if capped and not fits(estimate(item), 0):
                return results, i
            results[i] = fn(item)
        return results, None

    pool = ThreadPoolExecutor(max_workers=workers)
    running = {}   # future -> (index, estimate)
    stop = None
    try:
        for i, item in enumerate(items):
            est = estimate(item) if capped else 0.0
            while running and (len(running) >= workers or
                               (capped and not fits(est, RESERVE_FACTOR * sum(e for _, e in running.values())))):
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for f in done:
                    results[running.pop(f)[0]] = f.result()
            if capped and not fits(est, 0):
                stop = i
                break
            running[pool.submit(fn, item)] = (i, est)
        for f in list(running):
            results[running.pop(f)[0]] = f.result()
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        print("[llm] stopping: no new calls start; running calls finish and are cached")
        raise
    pool.shutdown()
    return results, stop


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
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model,
             "mode": "MOCK" if mock else "REAL", "cached": cached,
             "prompt_tokens": prompt, "completion_tokens": completion, "cost_usd": cost,
             "seconds": seconds}
    tag = "MOCK" if mock else "cache hit" if cached else "api call"
    with _lock:
        if cost is not None and not cached and not mock:
            session_cost_usd += cost
        st = call_stats.setdefault(model, {"api_calls": 0, "cache_hits": 0, "prompt_tokens": 0,
                                           "completion_tokens": 0, "cost_usd": 0.0,
                                           "api_seconds": 0.0})
        if cached:
            st["cache_hits"] += 1
        elif not mock:
            st["api_calls"] += 1
            st["prompt_tokens"] += prompt
            st["completion_tokens"] += completion
            st["cost_usd"] += cost or 0.0
            st["api_seconds"] += seconds or 0.0
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
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
    data = _read_cache(path) if cache else None
    if data is not None:
        _log_usage(model, data.get("usage"), cached=True)
        return strip_think(data["choices"][0]["message"]["content"])

    data = _call(model, messages, kwargs, path)
    _log_usage(model, data.get("usage"), cached=False, seconds=data["_latency_s"])
    if data["choices"][0]["finish_reason"] == "length":
        print(f"[llm] warning: {model} hit max_tokens; reply may be cut off")
    return strip_think(data["choices"][0]["message"]["content"])


def chat_message(model, messages, thinking=None, cache=True, **kwargs):
    """Like chat(), but returns the whole reply for agent loops:
    {"content", "tool_calls" (list of {id, name, arguments}), "usage", "cost_usd", "cached",
    "seconds", "finish_reason"}. kwargs may include tools=[...] (OpenAI tool calling).
    Cached and logged exactly like chat(); cost_usd is 0 for a cache hit."""
    kwargs = _with_thinking(model, thinking, kwargs)
    key = _cache_key(model, messages, kwargs)
    path = CACHE_DIR / f"{key}.json"
    trace.record("llm", path)
    data = _read_cache(path) if cache else None
    cached = data is not None
    if not cached:
        data = _call(model, messages, kwargs, path)
    usage = data.get("usage") or {}
    _log_usage(model, usage, cached=cached, seconds=None if cached else data["_latency_s"])
    choice = data["choices"][0]
    msg = choice["message"]
    calls = [{"id": c.get("id"), "name": c["function"]["name"], "arguments": c["function"]["arguments"]}
             for c in (msg.get("tool_calls") or []) if c.get("function")]
    cost = cost_usd(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)) or 0.0
    return {"content": strip_think(msg.get("content") or ""), "tool_calls": calls, "usage": usage,
            "cost_usd": 0.0 if cached else cost, "cached": cached,
            "seconds": data.get("_latency_s"), "finish_reason": choice.get("finish_reason")}


def list_models():
    """Return the ids of all models available to this API key (not cached)."""
    if is_mock():
        return [ULTRA, SUPER_VL, LIGHTNING]
    return [m.id for m in client().models.list()]
