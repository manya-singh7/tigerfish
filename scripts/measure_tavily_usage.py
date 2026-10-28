"""Context efficiency of Tavily: characters returned vs. characters used, per feature.

Usage: python scripts/measure_tavily_usage.py

Replays the Tavily-backed checks from the cache with a Tavily credit cap of 0 and model calls
cache-only, so nothing paid can run (a check that would need a new call is listed as "not
measured"). While it runs, tigerfish.tavily_usage counts:
- returned: characters of web content in every Tavily response the check reads;
- sent to model: Tavily text found in the messages actually sent to a model (each line of a
  message that is contained in a returned text);
- shown as evidence: Tavily text kept in the check's saved output and shown in the app
  (quotes, titles, timeline events).
The paper trail's numbers come from results/paper_trail_<report>.json (counted during its run).
Saves results/tavily_usage.json.
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import (copycheck, knowable, llm, official_record, paper_trail,  # noqa: E402
                       public_record, species_photos, tavily_usage)
from tigerfish.ui import data  # noqa: E402

SHOWN_KEYS = ("quote", "title", "event")
OUT = ROOT / "results" / "tavily_usage.json"


def count_sent(messages):
    for m in messages or []:
        content = m.get("content")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        for line in str(content or "").split("\n"):
            if len(line.strip()) >= 12:
                tavily_usage.used_text(line, "sent to model")


def count_shown(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SHOWN_KEYS and isinstance(v, str):
                tavily_usage.used_text(v, "shown as evidence")
            else:
                count_shown(v)
    elif isinstance(obj, list):
        for v in obj:
            count_shown(v)


def measure(name, fn):
    """Run fn() with the ledger reset; returns (snapshot, error)."""
    tavily_usage.reset()
    try:
        out = fn()
    except (copycheck.CreditCapReached, llm.CacheMiss) as e:
        return None, f"needs a call that is not cached ({type(e).__name__})"
    count_shown(out)
    return tavily_usage.snapshot(), None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    llm.CACHE_ONLY = True
    real_chat = llm.chat

    def chat(model, messages, *a, **k):
        count_sent(messages)
        return real_chat(model, messages, *a, **k)
    llm.chat = chat

    zero = lambda: copycheck.Budget(0)   # noqa: E731 (any uncached Tavily call stops the replay)
    reports = {r["id"]: data.load(r["id"]) for r in data.reports()}
    runs = {}
    for rid in reports:
        if rid in public_record.PROJECTS:
            runs[f"Public record / {rid}"] = lambda rid=rid: public_record.run(
                rid, zero(), {f["id"] for f, _, _ in knowable.verified_findings(reports[rid])})
        if any(f["id"] for f in reports[rid]["findings"]) and rid in knowable.REPORT_DATES:
            runs[f"Knowable at the time / {rid}"] = lambda rid=rid: knowable.run(reports[rid], zero())
    runs["Species photos / all reports"] = lambda: species_photos.run(zero())
    pages = paper_trail.load_pages("great_nicobar_2021_draft_eia")
    if pages:
        runs["Official record / great_nicobar_2021_draft"] = lambda: official_record.run(pages, budget=zero())

    checks, not_measured = {}, {}
    for name, fn in runs.items():
        snap, err = measure(name, fn)
        if snap:
            checks[name] = snap
            t = snap["total"]
            print(f"{name:55} returned {t['returned']:>10,}  used {t['used']:>8,}  ({(t['share'] or 0):.2%})")
        else:
            not_measured[name] = err
            print(f"{name:55} not measured: {err}")
    for rid in reports:
        trail = paper_trail.load(rid)
        if trail and trail.get("efficiency"):
            checks[f"Paper trail / {rid}"] = trail["efficiency"]
            t = trail["efficiency"]["total"]
            print(f"{'Paper trail / ' + rid:55} returned {t['returned']:>10,}  used {t['used']:>8,}  ({(t['share'] or 0):.2%})")
    not_measured["Copy-paste, accreditation and WPA schedule checks (full audit)"] = (
        "their Tavily calls ran inside the full audit before this logging existed; re-run the "
        "audit to measure them")
    overall = tavily_usage.merge(checks.values())
    OUT.write_text(json.dumps({"measured_on": date.today().isoformat(), "overall": overall,
                               "checks": checks, "not_measured": not_measured},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    t = overall["total"]
    print(f"\nOverall: Tavily returned {t['returned']:,} characters; we used {t['used']:,} "
          f"({(t['share'] or 0):.2%}): {t['sent to model']:,} sent to a model, "
          f"{t['shown as evidence']:,} shown as evidence")
    for f, r in overall["features"].items():
        print(f"  {f:28} returned {r['returned']:>10,}  used {r['used']:>8,}  ({(r['share'] or 0):.2%})")
    print("saved", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
