"""Whole-report Ultra features (fulltext, memo, ask, the app tab). All mocked: no API calls."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tigerfish import ask, fulltext, llm, memo
from tigerfish.ui import memo_ask

ROOT = Path(__file__).resolve().parent.parent
REPORT = "great_nicobar_2021_draft"

PAGES = [
    {"page": 1, "text": ""},                                                    # scanned
    {"page": 2, "text": "पर्यावरण प्रभाव आकलन रिपोर्ट का सारांश हिंदी में यहाँ लिखा है और यह पूरा पृष्ठ है"},
    {"page": 3, "text": "The survey was carried out\n for  seven days from 15th through 21st December 2020."},
    {"page": 4, "text": "No coral exists in the bay portion of the Galathea Bay. Turtles nest here."},
    {"page": 5, "text": "Coral reef exists in the proposed site for Transshipment / Port."},
    {"page": 9, "text": "The report was prepared by Vimta Labs Ltd, a QCI-NABET accredited consultant."},
]
TEXTS = fulltext.page_texts(PAGES)


# ---------- report text ----------

def test_report_text_prefixes_pages_and_says_what_was_skipped():
    rt = fulltext.report_text(PAGES)
    assert rt["pages"] == [3, 4, 5, 9]
    assert rt["skipped"] == {"no text layer (scanned or photographed page)": [1], "Hindi page": [2]}
    assert rt["text"].startswith("[p.3] The survey was carried out for seven days")   # whitespace collapsed
    assert "[p.9] The report was prepared" in rt["text"]


def test_report_text_max_chars_stops_at_a_page_boundary():
    rt = fulltext.report_text(PAGES, max_chars=170)
    assert rt["pages"] == [3, 4] and rt["chars"] <= 170


# ---------- quote verification ----------

def test_quote_verified_on_cited_page_with_whitespace_and_quote_marks_normalised():
    v = fulltext.verify({"page": 3, "quote": "carried out for seven days from 15th through 21st December 2020"}, TEXTS)
    assert v["verified"] and v["page"] == 3 and "cited_page" not in v
    v = fulltext.verify({"page": "p.4", "quote": "No coral exists in the bay portion … Turtles nest here."}, TEXTS)
    assert v["verified"]                       # '...' joins parts that appear in order


def test_quote_on_a_nearby_page_is_corrected_far_away_is_not_verified():
    near = fulltext.verify({"page": 6, "quote": "Coral reef exists in the proposed site"}, TEXTS)
    assert near["verified"] and near["page"] == 5 and near["cited_page"] == 6
    far = fulltext.verify({"page": 40, "quote": "Coral reef exists in the proposed site"}, TEXTS)
    assert not far["verified"] and far["found_on"] == [5]


def test_invented_or_altered_quote_is_not_verified():
    assert not fulltext.verify({"page": 4, "quote": "Corals cover 116 hectares of the bay."}, TEXTS)["verified"]
    assert not fulltext.verify({"page": 4, "quote": "No coral exists in the whole of Galathea Bay."}, TEXTS)["verified"]
    assert not fulltext.verify({"page": 4, "quote": "coral"}, TEXTS)["verified"]          # too short


def test_string_citations_are_parsed():
    v = fulltext.verify("[p.9] The report was prepared by Vimta Labs Ltd", TEXTS)
    assert v["verified"] and v["page"] == 9


# ---------- memo ----------

def test_memo_issue_without_verified_quote_goes_to_unverified_reasoning():
    raw = {"issues": [
        {"title": "Coral presence differs", "category": "contradiction", "summary": "p.4 vs p.5.",
         "reasoning": "Port site.", "citations": [{"page": 4, "quote": "No coral exists in the bay portion"},
                                                   {"page": 5, "quote": "Coral reef exists in the proposed site"},
                                                   {"page": 5, "quote": "Corals were deliberately hidden."}]},
        {"title": "Invented", "category": "other", "summary": "x", "reasoning": "y",
         "citations": [{"page": 3, "quote": "The survey lasted three months."}]}]}
    m = memo.check(raw, TEXTS)
    assert [i["title"] for i in m["issues"]] == ["Coral presence differs"]
    assert len(m["issues"][0]["citations"]) == 2 and len(m["issues"][0]["unverified_citations"]) == 1
    assert [i["title"] for i in m["unverified_reasoning"]] == ["Invented"]
    assert m["stats"] == {"issues_returned": 2, "issues_verified": 1, "moved_to_unverified": 1,
                          "citations": 4, "citations_verified": 2, "page_corrected": 0}


def test_memo_flags_accusatory_wording():
    raw = {"issues": [{"title": "Figures deliberately misleading", "summary": "", "reasoning": "",
                       "citations": [{"page": 5, "quote": "Coral reef exists in the proposed site"}]}]}
    assert memo.check(raw, TEXTS)["issues"][0]["wording_flags"] == ["deliberately", "misleading"]


# ---------- ask ----------

def test_identical_prefix_and_question_last():
    text = fulltext.report_text(PAGES)["text"]
    a, b = ask.request(text, "Who prepared it?"), ask.request(text, "What about corals?")
    m = fulltext.messages(text, memo.TASK)
    assert a[0] == b[0] == m[0]                                    # byte-identical system prefix
    assert a[0]["role"] == "system" and a[0]["content"].endswith(text + fulltext.SUFFIX)
    assert a[-1]["role"] == "user" and a[-1]["content"].startswith("Question about this report: Who prepared it?")
    assert "Who prepared it?" not in a[0]["content"]


def test_answer_without_verified_quote_becomes_does_not_say():
    out = ask.check({"answer": "Corals cover 116 ha.", "report_says": True,
                     "citations": [{"page": 4, "quote": "Corals cover 116 hectares."}]}, TEXTS)
    assert out["answer"] == ask.DOES_NOT_SAY and not out["report_says"] and out["citations"] == []
    assert out["model_answer_unverified"] == "Corals cover 116 ha." and len(out["unverified_citations"]) == 1
    out = ask.check({"answer": ask.DOES_NOT_SAY, "citations": [], "report_says": False}, TEXTS)
    assert out["answer"] == ask.DOES_NOT_SAY and "model_answer_unverified" not in out


def test_answer_with_a_verified_quote_is_kept():
    out = ask.check({"answer": "Seven days.", "report_says": True,
                     "citations": [{"page": 3, "quote": "for seven days from 15th through 21st December 2020"}]}, TEXTS)
    assert out["report_says"] and out["answer"] == "Seven days." and out["citations"][0]["verified"]


def test_salvage_reads_prose_and_cut_off_json():
    prose = 'It lasted a week: “for seven days from 15th through 21st December 2020” as stated [p.3].'
    s = ask.salvage(prose)
    assert s["citations"] == [{"page": 3, "quote": "for seven days from 15th through 21st December 2020"}]
    cut = '{"answer": "Coral exists at the port site.", "citations": [{"page": 5, "quote": "Coral reef exists'
    s = ask.salvage(cut)
    assert s["answer"] == "Coral exists at the port site." and s["citations"] == []
    assert ask.salvage("no quotes, no JSON") is None


# ---------- costs and caps ----------

def usage(prompt, cached, out):
    return {"prompt_tokens": prompt, "completion_tokens": out,
            "prompt_tokens_details": {"cached_tokens": cached}}


def test_cost_uses_cached_input_price():
    usd, d = fulltext.cost(usage(545_436, 539_648, 652))
    assert usd == pytest.approx((5_788 * 1.00 + 539_648 * 0.12 + 652 * 3.00) / 1e6, abs=1e-6)
    assert d["cost_if_uncached_usd"] == pytest.approx((545_436 + 652 * 3) / 1e6, abs=1e-6)
    assert d["saving_usd"] == pytest.approx(d["cost_if_uncached_usd"] - usd, abs=1e-6)


@pytest.fixture
def fake_ultra(monkeypatch, tmp_path):
    """llm.chat_message replaced by a queue of replies; spend log in tmp."""
    monkeypatch.setattr(fulltext, "SPEND_LOG", tmp_path / "spend.jsonl")
    monkeypatch.setattr(llm, "is_cached", lambda *a, **k: False)
    monkeypatch.setattr(llm, "client", lambda: type("C", (), {"with_options": lambda self, **k: self})())
    calls = []

    def install(*replies):
        queue = list(replies)

        def chat_message(model, messages, **kw):
            calls.append({"messages": messages, **kw})
            content, finish, u = queue.pop(0)
            return {"content": content, "usage": u, "cached": False, "seconds": 1.0,
                    "finish_reason": finish, "tool_calls": [], "cost_usd": 0}
        monkeypatch.setattr(llm, "chat_message", chat_message)
        return calls
    return install


def test_cap_refuses_before_calling(fake_ultra, monkeypatch):
    calls = fake_ultra(("{}", "stop", usage(10, 0, 1)))
    fulltext.SPEND_LOG.write_text(json.dumps({"cost_usd": 2.90}) + "\n", encoding="utf-8")
    msgs = fulltext.messages("x" * 400_000, "q")             # ~106k tokens: worst case ~$0.13
    with pytest.raises(fulltext.CapReached):
        fulltext.call(msgs, 8000, "test", log=lambda *_: None)
    assert calls == []                                       # nothing was sent
    assert fulltext.spent() == pytest.approx(2.90)


def test_call_records_spend_and_restores_retries(fake_ultra):
    fake_ultra(("{}", "stop", usage(1000, 800, 10)))
    before = llm.MAX_RETRIES
    r = fulltext.call(fulltext.messages("abc", "q"), 100, "test", log=lambda *_: None)
    assert llm.MAX_RETRIES == before
    assert r["cost"]["cached_tokens"] == 800 and fulltext.spent() == pytest.approx(r["cost"]["cost_usd"])


def test_ask_retries_cut_off_reply_then_salvages(fake_ultra):
    calls = fake_ultra(
        ("", "length", usage(1000, 900, 8000)),                                           # reasoning ran out
        ('The survey: "for seven days from 15th through 21st December 2020" [p.4]', "stop", usage(1000, 900, 50)))
    a = ask.ask("How long was the survey?", PAGES, log=lambda *_: None)
    assert [c["max_tokens"] for c in calls] == [ask.MAX_TOKENS, ask.LONG_MAX_TOKENS]
    assert a["report_says"] and a["citations"][0]["page"] == 3 and a["citations"][0]["cited_page"] == 4
    assert a["calls"] == 2 and a["cost"]["prompt_tokens"] == 2000 and a["salvaged_from_invalid_json"]


def test_ask_json_retry_keeps_the_prefix(fake_ultra):
    calls = fake_ultra(('{"answer": "Coral exists at the port', "stop", usage(1000, 900, 40)),
                       ('{"answer": "Coral reef at the port site.", "citations": '
                        '[{"page": 5, "quote": "Coral reef exists in the proposed site"}]}', "stop", usage(1100, 900, 40)))
    a = ask.ask("Coral?", PAGES, log=lambda *_: None)
    assert len(calls) == 3 - 1 and calls[1]["messages"][0] == calls[0]["messages"][0]
    assert calls[1]["messages"][-1]["content"] == ask.RETRY_MSG
    assert a["report_says"] and a["answer"] == "Coral reef at the port site."


def test_ask_does_not_say_when_nothing_verifies(fake_ultra):
    fake_ultra(('{"answer": "Dugongs are assessed in Chapter 9.", "report_says": true, '
                '"citations": [{"page": 4, "quote": "Impacts on dugongs are assessed."}]}', "stop", usage(1000, 900, 30)))
    a = ask.ask("Dugongs?", PAGES, log=lambda *_: None)
    assert a["answer"] == ask.DOES_NOT_SAY and a["citations"] == []


def test_estimate_worst_case_includes_the_long_retry():
    rt = fulltext.report_text(PAGES)
    e = ask.estimate("Who prepared it?", rt)
    one = fulltext.estimate(ask.request(rt["text"], "Who prepared it?"), ask.MAX_TOKENS)
    assert e["worst_usd"] > one["worst_usd"] and e["expected_usd"] <= e["worst_usd"]


def test_question_is_trimmed_and_capped():
    assert len(ask.task("x" * 5000)) < len(ask.TASK) + ask.MAX_QUESTION_CHARS
    with pytest.raises(ValueError):
        ask.task("   ")


# ---------- saved results ----------

saved = pytest.mark.skipif(memo_ask.memo(REPORT) is None or memo_ask.answers(REPORT) is None,
                           reason="no saved memo / answers")


@saved
def test_saved_memo_quotes_are_checked():
    m = memo_ask.memo(REPORT)
    assert 1 <= len(m["issues"]) <= memo.MAX_ISSUES
    for i in m["issues"]:
        assert i["citations"] and all(c["verified"] for c in i["citations"]) and not i["wording_flags"]
    assert m["cost"]["cached_tokens"] > 0.9 * m["cost"]["prompt_tokens"]


@saved
def test_saved_answers_cover_the_six_questions_with_costs():
    rec = memo_ask.answers(REPORT)
    assert len(rec["answers"]) == 6
    for a in rec["answers"]:
        assert a["answer"] == ask.DOES_NOT_SAY or a["citations"]
        assert a["cost"]["cost_usd"] < a["cost"]["cost_if_uncached_usd"]
    t = rec["totals"]
    assert t["cost_usd"] == pytest.approx(sum(a["cost"]["cost_usd"] for a in rec["answers"]), abs=1e-5)


# ---------- the app ----------

@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()


@saved
def test_app_shows_memo_and_recorded_answers_without_a_key(app):
    assert not app.exception
    html = "\n".join(m.value for m in app.markdown)
    assert "Reviewer's memo" in html and "Ask the report" in html
    assert "Unverified reasoning (not checked)" in html
    assert "of them served from Token Factory" in html and "prompt cache (" in html
    labels = [e.label for e in app.expander]
    assert sum(q in labels for q in (a["question"] for a in memo_ask.answers(REPORT)["answers"])) == 6
    assert not any("Ask your own question" in t.label for t in app.text_input)    # no key: no live box
    assert any("needs NEBIUS_API_KEY" in c.value for c in app.caption)


@saved
def test_live_box_shows_estimate_and_stops_after_three(monkeypatch, tmp_path):
    pages = tmp_path / "cache" / "pages" / fulltext.PDF_STEM
    pages.mkdir(parents=True)
    pages.joinpath("pages.jsonl").write_text("\n".join(json.dumps(p) for p in PAGES), encoding="utf-8")
    monkeypatch.setattr(memo_ask, "ROOT", tmp_path)
    monkeypatch.setattr(fulltext, "SPEND_LOG", tmp_path / "spend.jsonl")
    sent = []
    monkeypatch.setattr(ask, "ask", lambda q, *a, **k: sent.append(q) or {
        "question": q, "answer": ask.DOES_NOT_SAY, "report_says": False, "citations": [],
        "unverified_citations": [], "cost": {"prompt_tokens": 1, "cached_tokens": 0, "completion_tokens": 1,
                                             "cost_usd": 0.0, "cost_if_uncached_usd": 0.0, "saving_usd": 0.0}})
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    for n in range(3):
        box = next(t for t in at.text_input if "Ask your own question" in t.label)
        box.set_value(f"Question {n}?").run()
        assert any("Estimated cost" in c.value for c in at.caption)          # shown before sending
        next(b for b in at.button if b.label == "Send to Nemotron Ultra").click().run()
    assert sent == ["Question 0?", "Question 1?", "Question 2?"]
    box = next(t for t in at.text_input if "Ask your own question" in t.label)
    assert box.disabled and "0 of 3 left" in box.label
