"""Smoke test: list Nemotron models on Nebius, then say hello with each of our three models.

Usage: python scripts/hello.py [--only lightning|ultra|super-vl] [--no-cache]
  --only      call just one model and skip the model listing (saves API calls)
  --no-cache  ignore cached replies and call the API again
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tigerfish import llm  # noqa: E402

MODELS = {"ultra": ("Ultra", llm.ULTRA), "super-vl": ("Super-VL", llm.SUPER_VL),
          "lightning": ("Lightning", llm.LIGHTNING)}

parser = argparse.ArgumentParser()
parser.add_argument("--only", choices=MODELS)
parser.add_argument("--no-cache", action="store_true")
args = parser.parse_args()

if not args.only:
    print("Nemotron models available:")
    for model_id in sorted(llm.list_models()):
        if "nemotron" in model_id.lower():
            print("  ", model_id)
    print()

for key, (name, model) in MODELS.items():
    if args.only and key != args.only:
        continue
    try:
        reply = llm.chat(model, [{"role": "user", "content": "Say hello in one line"}],
                         max_tokens=200, cache=not args.no_cache)
        print(f"{name}: {reply}")
    except Exception as e:
        print(f"{name} ({model}) FAILED: {e}")
