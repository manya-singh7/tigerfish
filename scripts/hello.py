"""Smoke test: list Nemotron models on Nebius, then say hello with each of our three models."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import llm  # noqa: E402

print("Nemotron models available:")
for model_id in sorted(llm.list_models()):
    if "nemotron" in model_id.lower():
        print("  ", model_id)

print()
for name, model in [("Ultra", llm.ULTRA), ("Super-VL", llm.SUPER_VL), ("Lightning", llm.LIGHTNING)]:
    try:
        reply = llm.chat(model, [{"role": "user", "content": "Say hello in one line"}],
                         max_tokens=200)
        print(f"{name}: {reply}")
    except Exception as e:
        print(f"{name} ({model}) FAILED: {e}")
