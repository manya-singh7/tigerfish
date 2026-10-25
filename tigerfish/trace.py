"""Which cached API responses did a run use? (for audit cost and time in replay mode)

llm.chat, copycheck.tavily_call and species.gbif_get call record(kind, path) for every
response they serve, from cache or fresh. scripts/export_results.py resets this, runs
one report's pipeline from cache, and turns the list into cost and time.
"""

used = []   # (kind, Path) in order: kind is "llm", "tavily" or "gbif"


def record(kind, path):
    used.append((kind, path))


def reset():
    used.clear()
