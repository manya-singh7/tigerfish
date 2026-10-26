"""Does Nemotron Ultra on Token Factory take the whole report in one call? Measures it.

    python scripts/ultra_context.py --cache ../tigerfish/cache [--step 200k|full]

200k: the first ~200k tokens of page text. full: every in-scope page, with the SAME system
message that memo.py and ask.py use (so this call also fills the prompt cache for them).
The question is tiny: name the first and last page markers and the first words of the last
page, which shows the model saw the end of the context. Writes results/ultra_context_test.json.
Reads the page cache only; no edits to it.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tigerfish import fulltext  # noqa: E402

OUT = ROOT / "results" / "ultra_context_test.json"
TEST_MAX_CHARS = 720_000      # ~200k tokens; fixed so a re-run replays the same call
QUESTION = ("Context check, answer in JSON only: {\"first_page\": <number of the first [p.N] "
            "marker>, \"last_page\": <number of the last [p.N] marker>, \"last_page_opening\": "
            "\"<the first 8 words of the last page, copied exactly>\"}")


def run(cache, step):
    pages = fulltext.load_pages(cache)
    limit = TEST_MAX_CHARS if step == "200k" else None
    rt = fulltext.report_text(pages, max_chars=limit)
    msgs = fulltext.messages(rt["text"], QUESTION)
    reply = fulltext.call(msgs, max_tokens=400, label=f"context test {step}", thinking=False)
    try:
        answer = fulltext.parse_json(reply["content"])
    except ValueError:      # e.g. an unterminated string: read the fields one by one
        answer = {"_raw_reply": reply["content"], "_not_valid_json": True}
        for key in ("first_page", "last_page"):
            m = re.search(rf'"{key}"\s*:\s*(\d+)', reply["content"])
            answer[key] = int(m.group(1)) if m else None
        m = re.search(r'"last_page_opening"\s*:\s*"([^"]*)', reply["content"])
        answer["last_page_opening"] = m.group(1) if m else ""
    last = rt["pages"][-1]
    opening = " ".join(next(p for p in pages if p["page"] == last)["text"].split()[:8])
    words = str(answer.get("last_page_opening", "")).split()
    result = {
        "step": step, "pages_included": len(rt["pages"]), "first_page": rt["pages"][0],
        "last_page": last, "chars": rt["chars"], "skipped": {k: len(v) for k, v in rt["skipped"].items()},
        "answer": answer,
        "correct_last_page": answer.get("last_page") == last,
        "correct_opening_words": sum(a == b for a, b in zip(words, opening.split())),
        "expected_opening": opening,
        "chars_per_token": round(rt["chars"] / reply["cost"]["prompt_tokens"], 3),
        "latency_s": reply.get("seconds"), **reply["cost"],
    }
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    data[step] = result
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(ROOT / "cache"), help="cache dir with pages/ (read only)")
    ap.add_argument("--step", choices=["200k", "full"], default="200k")
    a = ap.parse_args()
    run(Path(a.cache), a.step)
