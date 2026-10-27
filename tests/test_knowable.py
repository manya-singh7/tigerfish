"""Knowable at the time: Tavily and both models mocked."""

import json
from datetime import date

import pytest

from tigerfish import copycheck, knowable, llm

REPORT = {"id": "great_nicobar_2021_draft", "findings": [
    {"id": "ct-239", "check": "contradiction", "title": "Pages 291 and 337 disagree",
     "verification": {"outcome": "confirmed"}},
    {"id": "ct-999", "check": "contradiction", "title": "not verified"},
]}
OLD = "https://zsi.gov.in/old.pdf"
NEW = "https://news.example/2023/05/rain"
UNDATED = "https://wiki.example/nicobar"
TEXTS = {
    OLD: "Published : March, 2008\nThe [annual rainfall](http://x) of Great Nicobar is about 3,000 to 3,500 mm.",
    NEW: "The annual rainfall of Great Nicobar is about 3,000 to 3,500 mm.",
    UNDATED: "The annual rainfall of Great Nicobar is about 3,000 to 3,500 mm.",
}
QUOTE = "The annual rainfall of Great Nicobar is about 3,000 to 3,500 mm."


class Fake:
    def __init__(self):
        self.search_kw = []

    def search(self, **kw):
        self.search_kw.append(kw)
        return {"results": [{"url": u, "title": u} for u in (OLD, NEW, UNDATED)], "usage": {"credits": 1}}

    def extract(self, **kw):
        return {"results": [{"url": u, "raw_content": TEXTS[u]} for u in kw["urls"]], "usage": {"credits": 1}}


def models(lightning_quote=QUOTE, ultra="yes"):
    def chat(model, messages, **kw):
        if model == llm.LIGHTNING:
            return json.dumps({"supports": True, "quote": lightning_quote})
        return json.dumps({"states_point": ultra, "why": "states the rainfall"})
    return chat


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = Fake()
    monkeypatch.setattr(copycheck, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(copycheck, "client", lambda: f)
    monkeypatch.setattr(llm, "chat", models())
    return f


def test_search_uses_end_date_and_prefer_mode(fake):
    knowable.run(REPORT, copycheck.Budget(10))
    kw = fake.search_kw[0]
    assert kw["end_date"] == "2021-12-27" and kw["include_domains_mode"] == "prefer"
    assert "zsi.gov.in" in kw["include_domains"] and "pib.gov.in" in kw["include_domains"]


def test_only_dated_before_report_and_verified_sources_kept(fake):
    out = knowable.run(REPORT, copycheck.Budget(10))
    [f] = out["findings"]                                   # the unverified finding is skipped
    assert [s["url"] for s in f["sources"]] == [OLD]
    assert f["sources"][0]["date"] == "2008-03-01"
    why = {d["url"]: d["why"] for d in f["dropped"]}
    assert "not before the report" in why[NEW] and why[UNDATED] == "publish date not found"
    lines = knowable.card_lines(REPORT["id"], "ct-239", out)
    assert lines[0][0] == QUOTE and lines[0][2] == "2008-03-01"
    assert out["tavily"]["credits"] == 2                   # 1 search + 1 extract


def test_quote_not_in_text_is_dropped(fake, monkeypatch):
    monkeypatch.setattr(llm, "chat", models("Great Nicobar receives 5 metres of rain every single year."))
    out = knowable.run(REPORT, copycheck.Budget(10))
    assert out["findings"][0]["sources"] == []
    assert knowable.card_lines(REPORT["id"], "ct-239", out) == []      # no badge


def test_ultra_can_reject(fake, monkeypatch):
    monkeypatch.setattr(llm, "chat", models(ultra="no"))
    assert knowable.run(REPORT, copycheck.Budget(10))["findings"][0]["sources"] == []


def test_credit_cap_stops_cleanly(fake):
    out = knowable.run(REPORT, copycheck.Budget(0))
    assert out["findings"] == [] and "cap" in out["stopped"]


@pytest.mark.parametrize("text,expected", [
    ("Published: September, 2002 ISBN", date(2002, 9, 1)),
    ("Published online 2020 Aug 20. doi", date(2020, 8, 20)),
    ("passed on the 4th August, 2023 and is hereby published for general information", date(2023, 8, 4)),
    ("Year published: 2008", date(2008, 12, 31)),
    ("no date here at all", None),
])
def test_publish_dates(text, expected):
    assert knowable.publish_date({"url": "https://x.example/a"}, text)[0] == expected


def test_tavily_published_date_wins():
    r = {"url": "u", "published_date": "Sun, 20 Feb 2022 18:00:00 GMT"}
    assert knowable.publish_date(r, "")[0] == date(2022, 2, 20)


def test_plain_text_drops_markdown_links():
    assert knowable.plain_text("the [own data](http://a.b/c.pdf), *Macaca*") == "the own data, Macaca"
