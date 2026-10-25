"""Investigate agent: tool dispatch, step cap, cost cap, quote verification, JSON fallback.
All offline: the model (llm.chat_message), Tavily and GBIF are mocked."""

import json

import pytest

from tigerfish import agent

PAGES = [{"page": 1, "text": "Executive summary of the port project."},
         {"page": 392, "text": "As per the ZSI report, no coral exists in the bay portion of the Galathea Bay. "
                               "Corals occur on the eastern flank of the bay."},
         {"page": 978, "text": "Coral reef exists in the proposed site for Transshipment / Port."}]
FINDING = {"id": "ct-003", "title": "Pages 392 and 978 disagree", "grade": "RED", "message": "m",
           "quotes": [], "evidence": [], "why": "w", "clear": "c", "check_name": "Internal contradiction"}


def reply(calls=(), content="", tokens=(1000, 100)):
    return {"content": content, "cached": False, "seconds": 0.5, "finish_reason": "tool_calls",
            "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]},
            "tool_calls": [{"id": f"c{i}", "name": n, "arguments": json.dumps(a)} for i, (n, a) in enumerate(calls)]}


class Script:
    """Fake llm.chat_message: returns scripted replies, records what tools were offered."""

    def __init__(self, replies):
        self.replies, self.offered, self.messages = list(replies), [], []

    def __call__(self, model, messages, **kw):
        self.offered.append([t["function"]["name"] for t in kw.get("tools", [])])
        self.messages.append(list(messages))
        return self.replies.pop(0) if self.replies else reply([("search_report", {"query": "x", "reason": "r"})])


def run(monkeypatch, replies, **kw):
    s = Script(replies)
    monkeypatch.setattr(agent.llm, "chat_message", s)
    out = agent.investigate(FINDING, PAGES, site=(6.83, 93.87), use_tools=kw.pop("use_tools", True), **kw)
    return out, s


FINISH = ("finish", {"checked": ["read both pages"], "conclusion": "weakens",
                     "reasons": ["Page 392 limits its statement to the bay portion."],
                     "evidence": [{"page": 392, "quote": "no coral exists in the bay portion of the Galathea Bay",
                                   "note": "scope is the bay portion"}]})


# ---------- tool dispatch ----------

def test_search_report_ranks_pages_with_snippets():
    ctx = agent.Context(PAGES)
    res, summary = agent.dispatch(ctx, "search_report", {"query": "coral eastern flank", "reason": "r"})
    assert res["hits"][0]["page"] == 392 and "eastern flank" in res["hits"][0]["snippet"]
    assert {h["page"] for h in res["hits"]} == {392, 978} and "p.392" in summary


def test_read_page_truncates_and_records(monkeypatch):
    monkeypatch.setattr(agent, "PAGE_CHARS", 20)
    ctx = agent.Context(PAGES)
    res, _ = agent.dispatch(ctx, "read_page", {"n": "978"})
    assert res["truncated"] and len(res["text"]) == 20 and ctx.read_pages == {978}
    assert "error" in agent.dispatch(ctx, "read_page", {"n": 5000})[0]


def test_dispatch_errors_never_crash():
    ctx = agent.Context(PAGES)
    assert "unknown tool" in agent.dispatch(ctx, "delete_everything", {})[0]["error"]
    assert "missing args" in agent.dispatch(ctx, "read_page", {"reason": "r"})[0]["error"]
    assert "bad arguments" in agent.dispatch(ctx, "read_page", {"n": "seven"})[0]["error"]
    assert agent.dispatch(ctx, "read_page", {"n": 1, "evil": 1})[0]["page"] == 1     # extra args dropped


def test_web_tools_use_budget_and_official_domains(monkeypatch):
    seen = {}

    def search(query, budget, exact=True, include_domains=None):
        seen["domains"] = include_domains
        budget.check(1)
        budget.add(1)
        return {"results": [{"url": "https://moef.gov.in/x", "title": "t", "content": "c"}]}

    monkeypatch.setattr(agent.copycheck, "search", search)
    monkeypatch.setattr(agent.copycheck, "extract", lambda urls, budget, max_chars=None: {urls[0]: "Full text here."})
    ctx = agent.Context(PAGES, max_credits=1)
    res, _ = agent.dispatch(ctx, "web_search", {"query": "q", "official_only": True})
    assert seen["domains"] == agent.OFFICIAL_DOMAINS and res["results"][0]["url"] == "https://moef.gov.in/x"
    assert agent.dispatch(ctx, "web_search", {"query": "q2"})[0]["error"].startswith("web credit limit")
    assert agent.dispatch(ctx, "read_url", {"url": "https://moef.gov.in/x"})[0]["text"] == "Full text here."
    assert ctx.sources == {"https://moef.gov.in/x": "Full text here."}


def test_check_species_tool(monkeypatch):
    monkeypatch.setattr(agent.species, "check_species", lambda n, lat, lon: {
        "name": n, "matched_name": n, "grade": "RED", "local_count": 0, "global_count": 9,
        "gbif_links": {"species": "https://www.gbif.org/species/1"}})
    res, summary = agent.dispatch(agent.Context(PAGES), "check_species",
                                  {"name": "Panulirus interruptus", "lat": 7.0, "lon": 93.93})
    assert res["grade"] == "RED" and res["gbif_page"].endswith("/1") and "0 within" in summary


# ---------- the loop ----------

def test_full_run_with_finish(monkeypatch):
    out, s = run(monkeypatch, [reply([("read_page", {"n": 392, "reason": "check scope"})]), reply([FINISH])])
    assert out["memo"]["conclusion"] == "weakens" and out["memo"]["evidence"][0]["page"] == 392
    assert [t["tool"] for t in out["trace"]] == ["read_page", "finish"]
    assert out["trace"][0]["reason"] == "check scope" and out["trace"][0]["args"] == {"n": 392}
    tool_msg = s.messages[1][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c0"


def test_step_cap_offers_only_finish_at_the_last_step(monkeypatch):
    out, s = run(monkeypatch, [], max_steps=3)
    assert len(s.offered) == 3 and s.offered[-1] == ["finish"] and "finish" in s.offered[0]
    assert out["memo"]["conclusion"] == "inconclusive" and out["memo"]["stopped"] == "step cap 3"
    assert out["totals"]["steps"] == 3


def test_cost_cap_stops_cleanly(monkeypatch):
    big = (60_000, 1000)                       # $0.063 per reply at Ultra prices
    out, s = run(monkeypatch, [reply([("search_report", {"query": "coral", "reason": "r"})], tokens=big)] * 5,
                 max_cost=0.10)
    assert out["totals"]["cost_usd"] <= 0.10 + 1e-9
    assert len(s.offered) == 1 and out["memo"]["stopped"] == "cost cap $0.10"


def test_last_affordable_step_is_finish_only(monkeypatch):
    out, s = run(monkeypatch, [reply([("search_report", {"query": "coral", "reason": "r"})], tokens=(30_000, 500)),
                               reply([FINISH], tokens=(1000, 100))], max_cost=0.08)
    assert s.offered[1] == ["finish"] and out["memo"]["conclusion"] == "weakens"


# ---------- quote verification ----------

def test_unverified_quotes_are_dropped():
    ctx = agent.Context(PAGES)
    ctx.sources["https://zsi.gov.in/r"] = "The survey recorded 116 coral species in Galathea Bay."
    memo = agent.build_memo(ctx, {"conclusion": "strengthens", "reasons": ["r"], "checked": [], "evidence": [
        {"page": 978, "quote": "Coral reef exists in the proposed site", "note": "ok"},
        {"page": 1, "quote": "Coral reef exists in the proposed site", "note": "wrong page, still found"},
        {"page": 392, "quote": "Corals are abundant everywhere", "note": "invented"},
        {"url": "https://zsi.gov.in/r", "quote": "recorded 116 coral species", "note": "ok"},
        {"url": "https://zsi.gov.in/r", "quote": "no corals were recorded", "note": "invented"},
        {"url": "https://never-read.org", "quote": "anything", "note": "url not read"}]})
    # the p.1 quote is really on p.978, but p.978 was never read in this context: dropped
    assert [(e.get("page"), e.get("url")) for e in memo["evidence"]] == [(978, None), (None, "https://zsi.gov.in/r")]
    assert len(memo["dropped_quotes"]) == 4


def test_quote_found_on_another_page_only_if_it_was_read():
    ctx = agent.Context(PAGES)
    e = {"page": 1, "quote": "Corals occur on the eastern flank of the bay", "note": "n"}
    assert agent.build_memo(ctx, {"evidence": [e]})["evidence"] == []     # page 1 text lacks it, p.392 unread?
    ctx.read_pages.add(392)
    assert agent.build_memo(ctx, {"evidence": [e]})["evidence"][0]["page"] == 392


def test_bad_conclusion_becomes_inconclusive():
    memo = agent.build_memo(agent.Context(PAGES), {"conclusion": "proves fraud", "reasons": ["x"]})
    assert memo["conclusion"] == "inconclusive"


# ---------- JSON fallback ----------

def test_json_action_loop(monkeypatch):
    actions = [reply(content='{"reason": "find coral pages", "tool": "search_report", "args": {"query": "coral"}}'),
               reply(content="```json\n" + json.dumps({"tool": "finish", "args": FINISH[1]}) + "\n```")]
    out, s = run(monkeypatch, actions, use_tools=False)
    assert s.offered[0] == [] and "Tool calling is not available" in s.messages[0][0]["content"]
    assert [t["tool"] for t in out["trace"]] == ["search_report", "finish"]
    assert out["mode"] == "JSON actions" and out["memo"]["conclusion"] == "weakens"
    assert s.messages[1][-1]["content"].startswith("Result of search_report:")


def test_json_fallback_one_retry_then_stop(monkeypatch):
    out, s = run(monkeypatch, [reply(content="I think the finding is fine."), reply(content="still prose")],
                 use_tools=False)
    assert len(s.offered) == 2 and s.messages[1][-1]["content"] == agent.RETRY_MSG
    assert out["memo"]["stopped"] == "no valid action after one retry"


def test_json_retry_recovers(monkeypatch):
    out, _ = run(monkeypatch, [reply(content="prose"), reply(content=json.dumps({"tool": "finish", "args": FINISH[1]}))],
                 use_tools=False)
    assert out["memo"]["conclusion"] == "weakens" and out["memo"]["stopped"] is None


@pytest.mark.parametrize("text", ['{"tool": "rm", "args": {}}', '{"tool": "read_page", "args": [1]}', "[]", "nope"])
def test_parse_action_is_strict(text):
    assert agent.parse_action(text) is None


def test_supports_tools_probe(monkeypatch):
    monkeypatch.setattr(agent.llm, "chat_message", lambda *a, **k: reply([("read_page", {"n": 3})]))
    assert agent.supports_tools()
    monkeypatch.setattr(agent.llm, "chat_message", lambda *a, **k: reply(content="I will read page 3."))
    assert not agent.supports_tools()

    def broken(*a, **k):
        raise RuntimeError("400 tools not supported")
    monkeypatch.setattr(agent.llm, "chat_message", broken)
    assert not agent.supports_tools()


def test_cut_off_reply_is_retried_once_with_more_room(monkeypatch):
    cut = {**reply([("finish", {"checked": []})], tokens=(2000, 1500)), "finish_reason": "length"}
    out, s = run(monkeypatch, [cut, reply([FINISH])])
    assert len(s.offered) == 2 and out["memo"]["conclusion"] == "weakens"
    assert out["trace"][0]["retried_cut_off"] and out["trace"][0]["tokens_out"] == 1600


def test_species_results_are_attached_as_data(monkeypatch):
    monkeypatch.setattr(agent.species, "check_species", lambda n, lat, lon: {
        "name": n, "grade": "RED", "evidence": "0 GBIF records within 3,000 km", "gbif_links": {"species": "u"}})
    ctx = agent.Context(PAGES)
    agent.dispatch(ctx, "check_species", {"name": "Panulirus interruptus", "lat": 7, "lon": 93.93})
    memo = agent.build_memo(ctx, {"conclusion": "strengthens"})
    assert memo["data"] == [{"id": "D1", "source": "GBIF (TigerFish species check)", "about": "Panulirus interruptus at 7, 93.93",
                             "value": "0 GBIF records within 3,000 km", "url": "u"}]


def test_full_length_tool_call_counts_as_cut_off(monkeypatch):
    cut = reply([("finish", {"checked": []})], tokens=(2000, agent.MAX_TOKENS))   # finish_reason "tool_calls"
    out, s = run(monkeypatch, [cut, reply([FINISH])])
    assert len(s.offered) == 2 and out["trace"][0]["retried_cut_off"] and out["memo"]["conclusion"] == "weakens"


@pytest.mark.parametrize("value, expected", [
    ("- Read page 954\n- Checked GBIF", ["Read page 954", "Checked GBIF"]),
    ("- GBIF shows 0 records - The report gives no source", ["GBIF shows 0 records", "The report gives no source"]),
    (["a", " ", "- b"], ["a", "b"]), (None, []), (5, []),
])
def test_memo_lists_accept_strings(value, expected):
    assert agent.lines(value) == expected


# ---------- reasons must point to verified evidence ----------

EVIDENCE = [{"id": "E1", "page": 392, "quote": "no coral exists in the bay portion of the Galathea Bay", "note": ""},
            {"id": "E3", "url": "https://x.qci.org.in/MoM%20dt%20Oct%2026%2C%202021.pdf",
             "quote": "ACO was accredited for sectors 29(A), 33(B) and 39(B)", "note": ""}]
DATA = [{"id": "D1", "source": "GBIF (TigerFish species check)", "about": "Panulirus interruptus at 7, 93.93",
         "value": "0 GBIF records within 3,000 km; 294,577 worldwide", "url": "u"}]


@pytest.mark.parametrize("reason, ids", [
    ("Page 392 limits the statement to the bay portion [E1]", ["E1"]),          # explicit id
    ("Both sources agree [E1, E3]", ["E1", "E3"]),
    ("The ZSI report (pages 392, 738) finds no coral in the bay", ["E1"]),       # names the page
    ("Minutes of Oct 26, 2021 show Category B", ["E3"]),                         # names the source date
    ("Sector 33(B) is Category B only", ["E3"]),                                 # code from the quote
    ('The report says "no coral exists in the bay portion"', ["E1"]),           # quoted phrase
    ("GBIF shows no nearby records", ["D1"]),                                    # GBIF data attached
    ("294,577 records worldwide, none nearby", ["D1"]),
])
def test_reason_linked_to_verified_evidence(reason, ids):
    supported, unverified = agent.link_reasons([reason], EVIDENCE, DATA)
    assert unverified == [] and supported[0]["evidence"] == ids and "[" not in supported[0]["text"]


@pytest.mark.parametrize("reason", [
    "Independent research indicates other Panulirus species occur here",         # nothing cited
    "Cites a dropped quote [E2]",                                                # id of a dropped item
    "Page 978 says coral exists",                                                # page not in evidence
    "The report was published in 2021",                                         # a year is not a code
    'It says "something the source never says"',
])
def test_reason_without_verified_support_is_unverified(reason):
    supported, unverified = agent.link_reasons([reason], EVIDENCE, DATA)
    assert supported == [] and unverified == [agent.CITED_ID.sub("", reason).strip()]


def test_build_memo_ids_follow_model_numbering(monkeypatch):
    ctx = agent.Context(PAGES)
    memo = agent.build_memo(ctx, {"conclusion": "weakens", "evidence": [
        {"page": 392, "quote": "invented text", "note": "dropped"},
        {"page": 392, "quote": "no coral exists in the bay portion of the Galathea Bay", "note": "kept"}],
        "reasons": ["The scope is the bay portion [E2]", "Unsupported claim [E1]", "No citation at all"]})
    assert [e["id"] for e in memo["evidence"]] == ["E2"]
    assert memo["reasons"] == [{"text": "The scope is the bay portion", "evidence": ["E2"]}]
    assert memo["unverified_reasons"] == ["Unsupported claim", "No citation at all"]


def test_relink_saved_memo_is_idempotent():
    old = {"conclusion": "strengthens", "reasons": ["The ZSI report (pages 392, 738) says no coral",
                                                    "The two statements cannot both be right"],
           "evidence": [{"page": 392, "quote": "no coral exists", "note": ""}], "data": [], "checked": []}
    once = agent.relink_memo(old)
    assert once["evidence"][0]["id"] == "E1"
    assert once["reasons"] == [{"text": "The ZSI report (pages 392, 738) says no coral", "evidence": ["E1"]}]
    assert once["unverified_reasons"] == ["The two statements cannot both be right"]
    assert agent.relink_memo(once) == once
