"""Hosted-app safety (tigerfish/hosted.py): replay reads only committed files, caps and the daily
budget on paid calls, a visitor's own key stays in memory, visitor reviews stay in the session.
All mocked: no Nebius, Tavily or GBIF calls."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest  # noqa: F401
from apptest import open_app

from tigerfish import free_checks, hosted, llm, review
from tigerfish.ui import data, memo_ask

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = [ROOT / "cache", ROOT / "data" / "eias", ROOT / "logs", ROOT / "feedback"]
OPENED = {"on": False, "paths": []}


def _audit(event, args):
    if OPENED["on"] and event in ("open", "os.listdir", "os.scandir") and args:
        target = args[0]
        if isinstance(target, (str, bytes, Path)):
            OPENED["paths"].append(str(target))


sys.addaudithook(_audit)        # cannot be removed; only records while OPENED["on"]


def forbidden(paths):
    out = []
    for p in paths:
        try:
            resolved = Path(p).resolve()
        except (OSError, ValueError):
            continue
        if any(resolved == f or f in resolved.parents for f in FORBIDDEN):
            out.append(str(resolved))
    return sorted(set(out))


@pytest.fixture
def hosted_no_key(monkeypatch):
    monkeypatch.setenv("TIGERFISH_HOSTED", "1")
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")


# ---------- replay on the hosted app ----------

needs_results = pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(),
                                   reason="no results/")


@needs_results
def test_hosted_replay_opens_no_gitignored_files(hosted_no_key):
    OPENED["paths"].clear()
    OPENED["on"] = True
    try:
        home = open_app(report=None, timeout=90, page="library")   # the library, no key
        assert not home.exception
        assert any("Saved audits are full runs" in c.value for c in home.caption)
        at = open_app(timeout=90)
        assert not at.exception
        assert not [t for t in at.toggle if not t.key.startswith("action::")]  # no live mode without a key
        assert any(b.label in ("Back to library", "← Back to library") for b in at.button)
        for title in [r["title"] for r in data.reports()]:
            at.selectbox[0].select(title).run()
            assert not at.exception
    finally:
        OPENED["on"] = False
    opened = {Path(p).resolve() for p in OPENED["paths"]}
    assert (ROOT / "results" / "index.json").resolve() in opened     # the hook does record reads
    assert forbidden(OPENED["paths"]) == []


@needs_results
def test_hosted_review_decisions_stay_in_session(hosted_no_key, monkeypatch, tmp_path):
    committed = tmp_path / "reviews.jsonl"
    row = {"flag_id": "x-1", "reviewer": "Owner", "decision": "real", "note": "", "time": "2026-10-27T00:00:00"}
    committed.write_text(json.dumps(row) + "\n", encoding="utf-8")
    before = committed.read_bytes()
    monkeypatch.setattr(review, "REVIEWS", committed)
    monkeypatch.setenv("TIGERFISH_FEEDBACK", str(tmp_path / "feedback.json"))

    from tigerfish.ui import data
    queue = review.queue_for(data.load(review.load_queue()["report_id"]))
    at = open_app(timeout=90)
    at.text_input(key="review::name").input("Visitor").run()
    pos = at.session_state["review::pos"]
    flag = queue["items"][pos]["flag_id"]
    at.button(key=f"review::false_alarm::{flag}").click().run()
    assert not at.exception

    assert committed.read_bytes() == before                     # committed decisions untouched
    assert not (tmp_path / "feedback.json").exists()            # card reviews not written either
    rows = at.session_state["review::session_rows"]
    assert [(r["flag_id"], r["reviewer"], r["decision"]) for r in rows] == [(flag, "Visitor", "false_alarm")]
    assert any("Download your decisions" in b.label for b in at.get("download_button"))


def test_with_rows_never_changes_committed_reviews():
    committed = {"a": {"owner": {"flag_id": "a", "reviewer": "Owner", "decision": "real", "time": "1"}}}
    merged = review.with_rows(committed, [review.make_row("a", "Visitor", "false_alarm")])
    assert set(merged["a"]) == {"owner", "visitor"}
    assert set(committed["a"]) == {"owner"}
    assert review.rows_jsonl([{"flag_id": "a"}]) == '{"flag_id": "a"}\n'


def test_ask_on_saved_report_is_local_only_when_hosted(monkeypatch):
    monkeypatch.setenv("TIGERFISH_HOSTED", "1")
    pages, why = memo_ask.live_pages("great_nicobar_2021_draft", {})
    assert pages is None and "only locally" in why
    up = {"live_pages": {"id": "upload_abc", "pages": [{"page": 1, "text": "x"}]}}
    assert memo_ask.live_pages("upload_abc", up) == ([{"page": 1, "text": "x"}], None)


# ---------- caps and the daily budget ----------

def test_daily_budget_caps_and_resets(tmp_path, monkeypatch):
    b = hosted.DailyBudget(cap=1.00, path=tmp_path / "spend.json")
    b.ensure_room(0.60)
    b.add(0.70)
    with pytest.raises(hosted.BudgetExceeded):
        b.ensure_room(0.40)                    # 0.70 + 0.40 > 1.00
    b.add(0.30)
    with pytest.raises(hosted.BudgetExceeded):
        b.ensure_room()                        # nothing left
    assert hosted.DailyBudget(cap=1.00, path=tmp_path / "spend.json").spent() == pytest.approx(1.00)
    monkeypatch.setattr(hosted, "today", lambda: "2999-01-01")
    assert b.remaining() == pytest.approx(1.00)                 # a new UTC day


def test_constants_match_the_brief():
    assert hosted.MAX_UPLOAD_PAGES == 30
    assert hosted.MAX_UPLOADS_PER_SESSION == 3
    assert hosted.MAX_ASKS_PER_SESSION == 3
    assert hosted.DAILY_BUDGET_USD == 1.00


def test_session_caps_and_own_key(monkeypatch, tmp_path):
    monkeypatch.setenv("NEBIUS_API_KEY", "owner-key")
    monkeypatch.setattr(hosted, "budget", hosted.DailyBudget(cap=1.00, path=tmp_path / "b.json"))
    s = {}
    for _ in range(3):
        hosted.bump(s, "uploads")
    assert hosted.uploads_left(s) == 0 and hosted.asks_left(s) == 3
    assert hosted.paid_key(s) == "owner-key" and hosted.uses_owner_budget(s)
    hosted.budget.add(0.80)
    assert hosted.run_cap(s) == pytest.approx(0.20)             # min(0.50 per run, 0.20 left today)
    s[hosted.BYOK_KEY] = "  visitor-key "
    assert hosted.paid_key(s) == "visitor-key" and not hosted.uses_owner_budget(s)
    assert hosted.run_cap(s) == hosted.MAX_RUN_USD              # their key: daily budget not used


def test_hosted_detection(monkeypatch):
    monkeypatch.setenv("TIGERFISH_HOSTED", "1")
    assert hosted.is_hosted()
    monkeypatch.setenv("TIGERFISH_HOSTED", "0")
    monkeypatch.setenv("SPACE_ID", "someone/tigerfish")
    assert not hosted.is_hosted()                               # an explicit 0 wins
    monkeypatch.delenv("TIGERFISH_HOSTED")
    assert hosted.is_hosted()


# ---------- llm: budget hook, own key, context in worker threads ----------

def fake_response(prompt=1_000_000, completion=0):
    data = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}
    return SimpleNamespace(model_dump=lambda: data)


@pytest.fixture
def fake_api(monkeypatch, tmp_path):
    monkeypatch.delenv("TIGERFISH_MOCK", raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")      # dummy: _create is faked, nothing is sent
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "llm")
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "usage.jsonl")
    sent = []

    def create(model, messages, kwargs, sleep=None):
        sent.append({"model": model, "key": llm.client().api_key})
        return fake_response()
    monkeypatch.setattr(llm, "_create", create)
    return sent


def test_budget_hook_counts_and_refuses(fake_api, tmp_path):
    b = hosted.DailyBudget(cap=0.10, path=tmp_path / "b.json")
    with llm.use_budget(b):
        llm.chat(llm.LIGHTNING, [{"role": "user", "content": "one"}])     # 1M tokens x $0.06
        assert b.spent() == pytest.approx(0.06)
        llm.chat(llm.LIGHTNING, [{"role": "user", "content": "one"}])     # cache hit: free
        assert b.spent() == pytest.approx(0.06)
        llm.chat(llm.LIGHTNING, [{"role": "user", "content": "two"}])
        with pytest.raises(hosted.BudgetExceeded):
            llm.chat(llm.LIGHTNING, [{"role": "user", "content": "three"}])
    assert len(fake_api) == 2                                   # the refused call was never sent
    llm.chat(llm.LIGHTNING, [{"role": "user", "content": "four"}])        # outside: no budget
    assert b.spent() == pytest.approx(0.12) and len(fake_api) == 3


def test_own_key_is_used_and_never_written(fake_api, tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "owner-key")
    monkeypatch.setattr(llm, "_client", None)
    secret = "visitor-SECRET-key-123"
    with llm.use_key(secret):
        llm.chat(llm.LIGHTNING, [{"role": "user", "content": "q"}])
    llm.chat(llm.LIGHTNING, [{"role": "user", "content": "q2"}])
    assert [s["key"] for s in fake_api] == [secret, "owner-key"]
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert secret not in f.read_text(encoding="utf-8", errors="ignore")


def test_paid_calls_uses_session_key_and_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("NEBIUS_API_KEY", "owner-key")
    monkeypatch.setattr(hosted, "budget", hosted.DailyBudget(path=tmp_path / "b.json"))
    with hosted.paid_calls({}):
        assert llm.client().api_key == "owner-key" and llm._budget.get() is hosted.budget
    with hosted.paid_calls({hosted.BYOK_KEY: "mine"}):
        assert llm.client().api_key == "mine" and llm._budget.get() is None
    assert llm._key_client.get() is None and llm._budget.get() is None


def test_run_parallel_workers_see_the_budget_and_key():
    b = hosted.DailyBudget(path=None)
    with llm.use_budget(b), llm.use_key("k-1"):
        got, stop = llm.run_parallel(lambda i: (llm._budget.get(), llm.client().api_key),
                                     list(range(8)), workers=4)
    assert stop is None and all(x is b and k == "k-1" for x, k in got)


# ---------- free checks on an upload ----------

PAGES = [
    {"page": 1, "text": "The total project area of the port is 166 ha. Other text follows here."},
    {"page": 2, "text": "The project area of the port is 244 ha. More words on this page."},
]


def test_number_pairs_are_info_leads_not_graded():
    found = free_checks.number_pair_findings(PAGES)
    assert len(found) == 1
    f = found[0]
    assert f["grade"] == "INFO" and f["check"] == "number_pair"
    assert {q["page"] for q in f["quotes"]} == {1, 2}
    assert "verify" in f["message"].lower()


def test_species_check_uses_given_site(monkeypatch):
    text = ("Scientific name of species recorded: Panthera tigris, Elephas maximus, "
            "Rusa unicolor, Macaca fascicularis. Family Felidae, Elephantidae, Cervidae.")
    monkeypatch.setattr(free_checks.species_pages, "confirm", lambda n: {"ok": True})
    seen = []

    def check(name, lat, lon):
        seen.append((name, lat, lon))
        grade = "RED" if name == "Panthera tigris" else "NONE"
        return {"grade": grade, "evidence": "0 records nearby", "local_count": 0,
                "regional_count": 0, "global_count": 9, "matched_name": name,
                "gbif_links": {"species": "https://www.gbif.org/species/1"}}
    found = free_checks.species_findings([{"page": 3, "text": text}], (6.83, 93.87), check=check)
    assert seen and all(s[1:] == (6.83, 93.87) for s in seen)
    assert [f["title"] for f in found] == ["Panthera tigris (p.3)"]


@pytest.mark.parametrize("text,site", [("6.83, 93.87", (6.83, 93.87)), ("", None),
                                       ("6.83", None), ("abc, 1", None), ("95, 10", None)])
def test_parse_site(text, site):
    assert free_checks.parse_site(text) == site
