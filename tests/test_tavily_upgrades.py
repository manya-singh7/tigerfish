"""Tavily quality upgrades: project tagging, exact match, prefer mode, advanced extract."""

import json

from tigerfish import copycheck


class Fake:
    def __init__(self):
        self.calls = []

    def search(self, **kw):
        self.calls.append(("search", kw))
        return {"results": [], "usage": {"credits": 1}}

    def extract(self, **kw):
        self.calls.append(("extract", kw))
        return {"results": []}


def install(monkeypatch, tmp_path):
    f = Fake()
    monkeypatch.setattr(copycheck, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(copycheck, "client", lambda: f)
    return f


def test_client_is_tagged_with_project_id(monkeypatch):
    import tavily
    seen = {}

    class T:
        def __init__(self, api_key=None, project_id=None, **kw):
            seen["project_id"] = project_id
    monkeypatch.setattr(tavily, "TavilyClient", T)
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    monkeypatch.setattr(copycheck, "_client", None)
    copycheck.client()
    assert seen["project_id"] == "tigerfish" == copycheck.PROJECT_ID


def test_copy_paste_phrase_hunt_uses_exact_match(monkeypatch, tmp_path):
    f = install(monkeypatch, tmp_path)
    copycheck.check_passage({"page": 1, "claim_ids": [],
                             "text": "A total of 330 species of fauna were recorded at the site in 2020."},
                            copycheck.Budget(5))
    kind, kw = f.calls[0]
    assert kind == "search" and kw["exact_match"] is True and kw["query"].startswith('"')


def test_prefer_mode_is_one_search(monkeypatch, tmp_path):
    f = install(monkeypatch, tmp_path)
    copycheck.search("q", copycheck.Budget(5), exact=False, include_domains=["qci.org.in"],
                     include_domains_mode="prefer")
    kw = f.calls[0][1]
    assert kw["include_domains_mode"] == "prefer" and kw["include_domains"] == ["qci.org.in"]


def test_default_params_unchanged_so_old_cache_still_hits(monkeypatch, tmp_path):
    f = install(monkeypatch, tmp_path)
    copycheck.search("q", copycheck.Budget(5), exact=False, include_domains=["a.gov.in"])
    assert "include_domains_mode" not in f.calls[0][1]
    copycheck.extract(["https://a.gov.in/x.pdf"], copycheck.Budget(5))
    assert f.calls[1][1]["extract_depth"] == "basic"


def test_advanced_extract_is_budgeted_at_two_credits(monkeypatch, tmp_path):
    f = install(monkeypatch, tmp_path)
    b = copycheck.Budget(5)
    copycheck.extract(["https://nabet.qci.org.in/list.pdf"], b, depth="advanced")
    assert f.calls[0][1]["extract_depth"] == "advanced" and b.used == 2


def test_is_cached(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path)
    assert not copycheck.is_cached("search", query="q")
    copycheck._cache_path("search", {"query": "q"}).write_text(json.dumps({"data": {}}))
    assert copycheck.is_cached("search", query="q")
