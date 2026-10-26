"""Save replay files for the "How TigerFish reads scanned pages" panel.

    python scripts/build_inspector.py --cache ../tigerfish/cache

For a few pages of the Great Nicobar draft EIA that went to Nemotron Super-VL, reads (never
writes) from the given cache directory:
  pages/<pdf>/pages.jsonl   the page's text layer, as PyMuPDF extracted it in the audit run
  pages/<pdf>/page_N.png    the 150-dpi page image sent to Super-VL
  llm/<sha256>.json         Super-VL's cached reply; the file name is recomputed from the exact
                            request the audit made (claims.page_request), so it is that reply
and writes, under results/inspector/:
  <report>_pNNNN.jpg        the page image, downscaled
  <report>_pNNNN.json       the rows Super-VL read, the text-layer count, and the raw claims
  index.json                the pages in display order
No model, Tavily or GBIF calls.
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tigerfish import claims, llm  # noqa: E402

OUT = ROOT / "results" / "inspector"
REPORT_ID = "great_nicobar_2021_draft"
PDF_STEM = "great_nicobar_2021_draft_eia"
IMAGE_WIDTH = 900            # px; the cached renders are 1240 px wide (150 dpi)

# page -> (title, why it matters). Chosen because each holds facts that only exist as an image
# (or, for p.978, a ruled form) and that a reviewer would want to check.
PAGES = {
    896: ("Health environment data, Campbell Bay Primary Health Centre (photographed form)",
          "The baseline for public health (doctors, beds, staff, patients treated in 2020) is a "
          "photograph of a handwritten form. Text search finds nothing on this page."),
    901: ("Patients treated and medical intelligence data, PHC Gandhinagar, 2020 (handwritten table)",
          "Monthly patient numbers and outpatient / inpatient counts are handwritten in a table "
          "that was photographed. Text search finds nothing on this page."),
    909: ("Great Nicobar Island land map, legend with areas (scanned)",
          "The project area (166.104 sq km) and the areas taken from the biosphere reserve, tribal "
          "reserve and forest appear here only inside a scanned map."),
    978: ("Table 1, environmental characteristics of the project site (MoEFCC criteria form)",
          "States \"Coral reef exists in the proposed site for Transshipment / Port\", one half of "
          "the p.392 vs p.978 contradiction (ct-003)."),
}


def page_records(cache):
    want = set(PAGES)
    out = {}
    with open(cache / "pages" / PDF_STEM / "pages.jsonl", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            if p["page"] in want:
                out[p["page"]] = p
    return out


def _cached(cache, model, messages, tokens):
    kwargs = llm._with_thinking(model, False, {"max_tokens": tokens, "temperature": 0})
    path = cache / "llm" / f"{llm._cache_key(model, messages, kwargs)}.json"
    return (json.loads(path.read_text(encoding="utf-8")), path.name) if path.exists() else (None, None)


def _reply_text(data):
    return llm.strip_think(data["choices"][0]["message"]["content"])


def cached_reply(cache, page):
    """(parsed reply, cache file names, max_tokens) for the Super-VL request the audit made.

    Follows claims.chat_json / extract_claims: a reply cut off at max_tokens was re-asked with
    VISION_LONG_MAX_TOKENS; a reply that was not valid JSON was retried once with RETRY_MSG."""
    model, messages, max_tokens = claims.page_request(page)
    if model != llm.SUPER_VL:
        raise ValueError(f"p.{page['page']} did not go to Super-VL")
    data, name = _cached(cache, model, messages, max_tokens)
    if data is None:
        raise FileNotFoundError(f"no cached Super-VL reply for p.{page['page']}")
    tokens, names = max_tokens, [name]
    if data["choices"][0].get("finish_reason") == "length":
        long, long_name = _cached(cache, model, messages, claims.VISION_LONG_MAX_TOKENS)
        if long is not None:
            data, tokens, names = long, claims.VISION_LONG_MAX_TOKENS, [long_name]
    try:
        return claims.parse_json(_reply_text(data)), names, tokens
    except ValueError:
        pass
    retry = messages + [{"role": "assistant", "content": _reply_text(data)},
                        {"role": "user", "content": claims.RETRY_MSG}]
    again, again_name = _cached(cache, model, retry, tokens)
    if again is None:
        raise FileNotFoundError(f"p.{page['page']}: broken JSON and no cached retry")
    return claims.parse_json(_reply_text(again)), names + [again_name], tokens


def text_chars(text):
    """Characters found by text extraction, not counting whitespace."""
    return len("".join((text or "").split()))


def rows_from_claims(raw_claims, page_text):
    """One row per distinct line Super-VL quoted, in reply order, with the values it read."""
    rows = {}
    for c in raw_claims:
        quote = claims.normalize(str(c.get("quote") or ""))
        if not quote:
            continue
        row = rows.setdefault(quote, {"read": quote, "values": [], "types": [], "subjects": [],
                                      "in_text_layer": claims.quote_on_page(quote, page_text)})
        value = c.get("value")
        shown = f"{value} {c['unit']}" if c.get("unit") and c.get("unit") != "species" else str(value)
        if shown not in row["values"]:
            row["values"].append(shown)
        for key, field in (("types", "type"), ("subjects", "subject")):
            if c.get(field) and c[field] not in row[key]:
                row[key].append(c[field])
    return list(rows.values())


def build(cache):
    OUT.mkdir(parents=True, exist_ok=True)
    records = page_records(cache)
    index = []
    for n, (title, why) in PAGES.items():
        page = dict(records[n])
        page["image_path"] = str(cache / "pages" / PDF_STEM / f"page_{n}.png")
        raw, cache_names, tokens = cached_reply(cache, page)
        raw_claims = raw.get("claims") or []
        rows = rows_from_claims(raw_claims, page["text"])
        stem = f"{REPORT_ID}_p{n:04d}"
        with Image.open(page["image_path"]) as img:
            img = img.convert("RGB")
            size = img.size
            img.thumbnail((IMAGE_WIDTH, IMAGE_WIDTH * 2))
            img.save(OUT / f"{stem}.jpg", quality=82, optimize=True)
        record = {
            "report_id": REPORT_ID, "page": n, "label": page.get("label") or "",
            "title": title, "why": why, "image": f"{stem}.jpg", "image_source_px": list(size),
            "text_layer": {"chars": text_chars(page["text"]),
                           "text": claims.normalize(page["text"])[:200],
                           "how": "PyMuPDF page.get_text(), non-whitespace characters"},
            "vision_reasons": page.get("reasons") or [],
            "model": llm.SUPER_VL, "max_tokens": tokens,
            "cache_files": [f"cache/llm/{name}" for name in cache_names],
            "rows": rows,
            "rows_in_text_layer": sum(r["in_text_layer"] for r in rows),
            "claims": raw_claims,
        }
        (OUT / f"{stem}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
        index.append({"page": n, "file": f"{stem}.json", "title": title})
        print(f"p.{n}: {record['text_layer']['chars']} text chars, {len(rows)} rows read "
              f"({record['rows_in_text_layer']} found in the text layer)")
    (OUT / "index.json").write_text(json.dumps({"report_id": REPORT_ID, "pages": index},
                                               indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(ROOT / "cache"),
                    help="cache directory holding pages/ and llm/ from the audit run (read only)")
    build(Path(ap.parse_args().cache).resolve())
