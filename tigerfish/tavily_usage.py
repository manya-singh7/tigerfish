"""Context efficiency of Tavily: characters of web content Tavily returned vs. characters we
actually used (sent to a model, or shown as evidence in the app). Counted, not estimated.

returned(endpoint, params, data)  every Tavily response (fresh or from the cache) adds the
                                   characters of web content in it to its feature, and
                                   remembers which feature delivered each URL's text.
used(chars, how, url=, feature=)   code that sends text to a model or keeps it as evidence
                                   adds its length; with url= it counts for the feature that
                                   delivered that URL (the last one that returned it).
used_text(text, how)               the same for a piece of text: it counts for the feature whose
                                   returned text contains it (whitespace and markdown ignored);
                                   text found in no returned content is not counted.

Features are named from the call itself (feature_of): "search: news", "extract (advanced)",
"map", "crawl", "research", ... A run resets the ledger, does its work and saves
snapshot() into its results file, so the app reads only saved numbers.
"""

import hashlib
import json
import re

HOW = ("sent to model", "shown as evidence")

_rows = {}      # feature -> {"calls", "returned", "sent to model", "shown as evidence"}
_by_url = {}    # url -> feature that last returned its text
_texts = {}     # url -> (feature, normalized text): in memory only, for used_text


def reset():
    _rows.clear()
    _by_url.clear()
    _texts.clear()


def norm(text):
    """Plain text for matching: markdown links/images/emphasis dropped, whitespace collapsed."""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text or "")
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1), t)
    t = re.sub(r"(\*\*|\*|__)", "", t)
    return " ".join(t.split()).lower()


def feature_of(endpoint, params):
    p = params or {}
    if endpoint in ("research", "map", "crawl"):
        return endpoint
    if endpoint == "extract":
        return "extract (advanced)" if p.get("extract_depth") == "advanced" else "extract"
    if p.get("include_images"):
        return "search: images"
    if p.get("topic") == "news":
        return "search: news"
    if p.get("language"):
        return "search: language filter"
    if p.get("exact_match"):
        return "search: exact match"
    if p.get("end_date") or p.get("start_date"):
        return "search: date filter"
    if p.get("include_domains_mode"):
        return "search: prefer domains"
    if p.get("include_domains"):
        return "search: official domains"
    return "search"


def _text(value):
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def content_chars(endpoint, data):
    """{url: characters of web content} in one Tavily response ("" key: content not tied to a
    URL, e.g. a research report). Titles count; other metadata does not."""
    out = {}
    if not isinstance(data, dict):
        return out
    if endpoint == "research":
        out[""] = len(_text(data.get("content")))
        return out
    if endpoint == "map":
        for u in data.get("results") or []:
            if isinstance(u, str):
                out[u] = out.get(u, 0) + len(u)
        return out
    for r in data.get("results") or []:
        if not isinstance(r, dict):
            continue
        n = (len(r.get("title") or "") + len(r.get("content") or "")
             + len(r.get("raw_content") or ""))
        url = r.get("url") or ""
        out[url] = out.get(url, 0) + n
    for img in data.get("images") or []:
        if isinstance(img, dict):
            out[img.get("url") or ""] = len(img.get("description") or "") + len(img.get("url") or "")
        elif isinstance(img, str):
            out[img] = len(img)
    return out


def _row(feature):
    return _rows.setdefault(feature, {"calls": 0, "returned": 0, HOW[0]: 0, HOW[1]: 0})


def texts_of(endpoint, data):
    """{key: text} of the web content in a response (for used_text)."""
    if not isinstance(data, dict):
        return {}
    if endpoint == "research":
        content = _text(data.get("content"))
        return {"research:" + hashlib.sha256(content.encode()).hexdigest()[:12]: content}
    out = {}
    for r in data.get("results") or []:
        if isinstance(r, dict) and r.get("url"):
            out[r["url"]] = " ".join(x for x in (r.get("title"), r.get("content"), r.get("raw_content")) if x)
    return out


def returned(endpoint, params, data):
    feature = feature_of(endpoint, params)
    row = _row(feature)
    row["calls"] += 1
    for url, n in content_chars(endpoint, data).items():
        row["returned"] += n
        if url:
            _by_url[url] = feature
    for key, text in texts_of(endpoint, data).items():
        _texts[key] = (feature, norm(text))
    return feature


def used(chars, how, url=None, feature=None):
    """Count `chars` characters of Tavily text as used. Text whose source is unknown to the
    ledger (and no feature given) is not counted."""
    assert how in HOW, how
    feature = feature or _by_url.get(url or "")
    if not feature or not chars:
        return
    _row(feature)[how] += int(chars)


def source_of(text):
    """Feature whose returned text contains `text` (after norm), else None."""
    t = norm(text)
    if len(t) < 12:
        return None
    for feature, body in _texts.values():
        if t in body:
            return feature
    return None


def used_text(text, how):
    """Count a piece of text sent to a model or shown, if Tavily returned it; returns its feature."""
    feature = source_of(text)
    if feature:
        used(len(norm(text)), how, feature=feature)
    return feature


def snapshot():
    """{"features": {name: {...}}, "total": {...}} with used = sent + shown and its share."""
    feats = {}
    tot = {"calls": 0, "returned": 0, HOW[0]: 0, HOW[1]: 0}
    for name, r in sorted(_rows.items()):
        feats[name] = summarize(r)
        for k in tot:
            tot[k] += r[k]
    return {"features": feats, "total": summarize(tot)}


def summarize(r):
    use = r[HOW[0]] + r[HOW[1]]
    return {**r, "used": use, "share": (use / r["returned"]) if r["returned"] else None}


def merge(snapshots):
    """Add several snapshot() dicts together (e.g. one per check and report)."""
    rows = {}
    for s in snapshots:
        for name, r in (s or {}).get("features", {}).items():
            acc = rows.setdefault(name, {"calls": 0, "returned": 0, HOW[0]: 0, HOW[1]: 0})
            for k in acc:
                acc[k] += r.get(k, 0)
    feats = {n: summarize(r) for n, r in sorted(rows.items())}
    tot = {"calls": 0, "returned": 0, HOW[0]: 0, HOW[1]: 0}
    for r in rows.values():
        for k in tot:
            tot[k] += r[k]
    return {"features": feats, "total": summarize(tot)}
