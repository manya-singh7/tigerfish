"""Public record: research timeline, news after the report and local-language links (mocked)."""

import pytest

from tigerfish import copycheck
from tigerfish import public_record as pr

PIB = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=1"
PCC = "https://dstpcc.andamannicobar.gov.in/hearing.pdf"
BLOG = "https://blog.example/timeline"
EVENTS = {"events": [
    {"date": "2022-01-27", "event": "Public hearing held.", "source": PCC,
     "quote": "Public Hearing scheduled to be held on 27th January 2022 at Campbell Bay."},
    {"date": "2024-11-25", "event": "Reply in Parliament.", "source": PIB,
     "quote": "Nov 25, 2024 — A detailed scrutiny of the EIA/EMP report took place."},
    {"date": "2022-05-24", "event": "EAC meeting.", "source": PIB, "quote": "Words that are not on the page at all."},
    {"date": "2023-01-01", "event": "Blog post.", "source": BLOG, "quote": "anything at all here"},
]}
TEXTS = {PCC: "Notice. Public Hearing scheduled to be held on 27th January 2022 at Campbell Bay.",
         PIB: "Reply. A detailed scrutiny of the EIA/EMP report took place during appraisal."}


class Fake:
    def __init__(self, reject_extras=False):
        self.reject_extras, self.research_kw, self.search_kw = reject_extras, [], []

    def research(self, **kw):
        self.research_kw.append(kw)
        if self.reject_extras and "include_domains" in kw:
            raise ValueError("400: unknown parameter")
        return {"request_id": "r1", "status": "pending"}

    def get_research(self, rid, include_usage=None):
        return {"status": "completed", "content": EVENTS, "usage": {"credits": 40},
                "sources": [{"url": PIB}]}

    def extract(self, **kw):
        return {"results": [{"url": u, "raw_content": TEXTS[u]} for u in kw["urls"] if u in TEXTS]}

    def search(self, **kw):
        self.search_kw.append(kw)
        return {"results": [
            {"url": "https://news.example/a", "title": "Great Nicobar coral update", "content": "",
             "published_date": "Mon, 29 Jun 2026 18:00:00 GMT"},
            {"url": "https://facebook.com/x", "title": "Great Nicobar post", "content": ""},
            {"url": "https://other.example/b", "title": "Unrelated story", "content": ""}],
            "usage": {"credits": 1}}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(pr.time, "sleep", lambda s: None)

    def install(**kw):
        f = Fake(**kw)
        monkeypatch.setattr(copycheck, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(copycheck, "client", lambda: f)
        return f
    return install


def run(credits=200):
    return pr.run("great_nicobar_2021_draft", copycheck.Budget(credits), {"ct-031", "ct-239"})


def test_research_call_and_verified_timeline(fake):
    f = fake()
    out = run()
    kw = f.research_kw[0]
    assert kw["include_domains"] == pr.TIMELINE_DOMAINS and kw["output_length"] == "short"
    assert kw["model"] == "mini" and kw["output_schema"] == pr.EVENT_SCHEMA
    assert [e["date"] for e in out["timeline"]] == ["2022-01-27", "2024-11-25"]
    assert out["timeline"][1]["quote"].startswith("A detailed scrutiny")      # snippet date stripped
    why = {e["event"]: e["why"] for e in out["timeline_dropped"]}
    assert why["EAC meeting."].startswith("quote not found")
    assert why["Blog post."].startswith("source is not an official")
    assert out["research"]["credits"] == 40 and out["tavily"]["credits"] >= 40


def test_research_is_cached(fake):
    f = fake()
    run()
    run()
    assert len(f.research_kw) == 1


def test_research_retries_without_unsupported_params(fake):
    f = fake(reject_extras=True)
    out = run()
    assert "include_domains" not in f.research_kw[-1]
    assert out["research"]["params_sent"].get("include_domains") is None


def test_research_needs_reserve_credits(fake):
    fake()
    out = run(credits=pr.RESEARCH_RESERVE - 1)
    assert "cap" in out["stopped"] and out["timeline"] == []


def test_news_after_report_and_local_language_searches(fake):
    f = fake()
    out = run()
    news = [k for k in f.search_kw if k.get("topic") == "news"]
    assert news and all(k["start_date"] == "2021-12-28" for k in news)
    assert {n["topic"] for n in out["next"]} == {"coral", "rainfall"}   # verified findings only
    local = [k for k in f.search_kw if k.get("language")]
    assert {k["language"] for k in local} == {"hi", "ta"} and all(k["filter_by_language"] for k in local)
    for n in out["next"] + out["local"]:
        assert [i["url"] for i in n["items"]] == ["https://news.example/a"]   # relevant, not social
