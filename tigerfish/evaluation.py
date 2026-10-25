"""Evaluation helpers: planted contradictions, planted species, scoring, usage tables.

Everything here is deterministic for a given seed. Pages are modified in memory only;
the PDF is never touched.
"""

import json
import random
import re
from pathlib import Path

from tigerfish import claims as claims_mod
from tigerfish import contradictions, llm

NUMERIC_TYPES = ("quantity", "count", "area", "distance")


# ---------- planted contradictions ----------

def pick_source_claims(ledger, n, rng, exclude_ids=()):
    """n verified numeric claims with distinct subjects and values, chosen with rng."""
    usable = [c for c in ledger
              if c.get("verified") and c["type"] in NUMERIC_TYPES and c["id"] not in exclude_ids
              and isinstance(c["value"], (int, float)) and not isinstance(c["value"], bool)
              and c["value"] >= 4 and c.get("unit")]
    usable.sort(key=lambda c: c["id"])                # stable order before shuffling
    rng.shuffle(usable)
    picked, seen_values, seen_words = [], set(), set()
    for c in usable:
        words = contradictions.keywords(c["subject"])
        if c["value"] in seen_values or (words & seen_words):
            continue                                  # keep subjects clearly apart
        picked.append(c)
        seen_values.add(c["value"])
        seen_words |= words
        if len(picked) == n:
            break
    return picked


def changed_value(value, factor):
    new = value * factor
    if float(value).is_integer():
        new = int(round(new))
    else:
        new = round(new, 2)
    return new


def fmt_value(v):
    return f"{v:g}" if isinstance(v, float) else str(v)


def planted_sentence(claim, new_value):
    """A sentence restating the claim's subject with a different value."""
    return (f"As per the field survey, the figure for {claim['subject']} is "
            f"{fmt_value(new_value)} {claim['unit']}.")


def explained_sentence(claim, new_value):
    """Same subject, a different value, and the report's own explanation of the change."""
    return (f"As per the field survey, the figure for {claim['subject']} was revised from "
            f"{fmt_value(claim['value'])} {claim['unit']} to {fmt_value(new_value)} "
            f"{claim['unit']} after the 2021 survey.")


def insert_sentence(text, sentence, rng):
    """Insert a sentence after a random sentence boundary (never before the first)."""
    parts = re.split(r"(?<=\.)\s+", text.strip())
    at = rng.randint(1, max(1, len(parts) - 1)) if len(parts) > 1 else 1
    return " ".join(parts[:at] + [sentence] + parts[at:])


def target_pool(pages, exclude_pages, min_chars=1200, max_chars=3000, max_digits=40):
    """Narrative English pages: plain text, few numbers, not in exclude_pages."""
    return sorted(p["page"] for p in pages.values()
                  if p["page"] not in exclude_pages and not p.get("needs_vision")
                  and not p.get("error") and min_chars <= len(p["text"]) <= max_chars
                  and sum(ch.isdigit() for ch in p["text"]) < max_digits
                  and not re.search(r"[ऀ-ॿ]", p["text"]))   # skip Hindi pages


def make_plants(ledger, pages, seed=42, n_planted=10, n_explained=5, exclude_pages=()):
    """Plants: [{kind: planted|explained, source claim, target page, sentence, values}].

    Each plant goes into a different target page, never the source claim's page.
    """
    rng = random.Random(seed)
    sources = pick_source_claims(ledger, n_planted + n_explained, rng)
    if len(sources) < n_planted + n_explained:
        raise ValueError(f"only {len(sources)} usable source claims")
    pool = target_pool(pages, set(exclude_pages) | {c["page"] for c in ledger})
    targets = rng.sample(pool, len(sources))
    plants = []
    for i, (src, target) in enumerate(zip(sources, targets)):
        kind = "planted" if i < n_planted else "explained"
        new = changed_value(src["value"], rng.choice((0.5, 1.5)))
        sentence = planted_sentence(src, new) if kind == "planted" else explained_sentence(src, new)
        plants.append({"id": f"{kind[:2]}-{i + 1:02d}", "kind": kind, "source_id": src["id"],
                       "source_page": src["page"], "source_quote": src["quote"],
                       "source_value": src["value"], "new_value": new, "unit": src["unit"],
                       "subject": src["subject"], "target_page": target, "sentence": sentence})
    return plants


def modified_pages(pages, plants, seed=42):
    """{page: page dict with the plant's sentence inserted} (copies; originals untouched)."""
    rng = random.Random(seed + 1)
    out = {}
    for p in plants:
        base = pages[p["target_page"]]
        out[p["target_page"]] = {**base, "text": insert_sentence(base["text"], p["sentence"], rng),
                                 "needs_vision": False}
    return out


# ---------- scoring ----------

def finding_hits_plant(f, plant):
    """A finding is about a plant if it quotes the planted sentence and the source page."""
    on_target = [q for q in f["quotes"] if q["page"] == plant["target_page"]]
    has_sentence = any(contradictions.quotes_match(q["text"], plant["sentence"]) for q in on_target)
    return has_sentence and plant["source_page"] in f["pages"]


def score_plants(plants, findings, extracted=None, candidates=None):
    """Per plant: extracted?, paired?, grade; plus totals and other new flags.

    extracted: claims from the modified pages (to see where a miss happened).
    candidates: the candidate pairs that were checked.
    """
    flagged = [f for f in findings if f["grade"] in ("RED", "ORANGE")]
    rows, matched = [], set()
    for p in plants:
        hit = [f for f in findings if finding_hits_plant(f, p)]
        best = min(hit, key=lambda f: {"RED": 0, "ORANGE": 1, "NONE": 2}[f["grade"]], default=None)
        for f in hit:
            matched.add(f["id"])
        got = [c for c in (extracted or []) if c["page"] == p["target_page"]
               and contradictions.quotes_match(c["quote"], p["sentence"])]
        paired = any(any(c["id"] == p["source_id"] for c in cand["claims"])
                     and any(c["page"] == p["target_page"] for c in cand["claims"])
                     for cand in (candidates or []))
        grade = best["grade"] if best else None
        caught = grade in ("RED", "ORANGE")
        rows.append({**{k: p[k] for k in ("id", "kind", "source_page", "target_page", "subject",
                                           "source_value", "new_value", "unit")},
                     "extracted": bool(got), "paired": paired, "grade": grade,
                     "ok": caught if p["kind"] == "planted" else not caught,
                     "stage_missed": None if caught or p["kind"] == "explained" else
                     ("extraction" if not got else "pairing" if not paired else "verdict")})
    planted = [r for r in rows if r["kind"] == "planted"]
    explained = [r for r in rows if r["kind"] == "explained"]
    others = [f for f in flagged if f["id"] not in matched]
    return {"rows": rows,
            "planted_caught": sum(r["ok"] for r in planted), "planted_total": len(planted),
            "explained_wrongly_flagged": sum(not r["ok"] for r in explained),
            "explained_total": len(explained),
            "other_new_flags": [{"id": f["id"], "grade": f["grade"], "pages": f["pages"],
                                 "reason": f["reason"]} for f in others]}


def score_species(results, out_of_place, real):
    """results: {name: species result}. Flagged = RED/ORANGE; GREY is reported separately."""
    def flagged(n):
        return results[n]["grade"] in ("RED", "ORANGE")
    return {"out_of_place_flagged": sum(flagged(n) for n in out_of_place),
            "out_of_place_total": len(out_of_place),
            "out_of_place_grey": sum(results[n]["grade"] == "GREY" for n in out_of_place),
            "real_wrongly_flagged": sum(flagged(n) for n in real), "real_total": len(real),
            "rows": [{"name": n, "group": "out of place" if n in out_of_place else "recorded locally",
                      "grade": results[n]["grade"], "local": results[n]["local_count"],
                      "regional": results[n]["regional_count"], "global": results[n]["global_count"],
                      "gbif_name": results[n]["matched_name"]}
                     for n in list(out_of_place) + list(real)]}


# ---------- cost, tokens, time (cookbook-style table rows) ----------

def usage_row(name, used, gap_estimates=None):
    """Calls, tokens, cost and API time for the LLM cache files a stage used.

    Time is the measured latency (_latency_s) when recorded, else the estimate from
    gap_estimates ({path: seconds}); `time_measured` says which.
    """
    calls = tin = tout = 0
    cost = secs = 0.0
    measured = True
    for kind, path in dict.fromkeys(used):
        if kind != "llm" or not Path(path).exists():
            continue
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        u = data.get("usage") or {}
        calls += 1
        tin += u.get("prompt_tokens", 0)
        tout += u.get("completion_tokens", 0)
        cost += llm.cost_usd(data.get("model"), u.get("prompt_tokens", 0),
                             u.get("completion_tokens", 0)) or 0
        if "_latency_s" in data:
            secs += data["_latency_s"]
        else:
            measured = False
            secs += (gap_estimates or {}).get(path, 0)
    return {"stage": name, "calls": calls, "in_tokens": tin, "out_tokens": tout,
            "total_tokens": tin + tout, "seconds": round(secs, 1), "time_measured": measured,
            "cost_usd": round(cost, 5)}


def other_calls(used, kind):
    return len({p for k, p in used if k == kind})


USD_TO_INR = 84


def inr(usd):
    return usd * USD_TO_INR


def quote_text(text):
    return claims_mod.normalize(text)
