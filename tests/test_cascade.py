"""Triage cascade, recall fixes (numeric statements, rule pass), scope filter: all mocked."""

import json
import sys
from pathlib import Path

import pytest

from tigerfish import claims, contradictions as ct, evaluation as ev, llm, scope

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit  # noqa: E402


def claim(cid, page, ctype, value, unit, subject, quote=None, **extra):
    return {"id": cid, "page": page, "type": ctype, "value": value, "unit": unit,
            "subject": subject, "quote": quote or f"{subject} {value} {unit}",
            "verified": True, **extra}


def cand(kind, a, b):
    return {"kind": kind, "claims": [a, b]}


A = claim("a", 1, "area", 2, "ha", "coral loss")
B = claim("b", 2, "area", 4, "ha", "coral restoration")


# ---------- triage ----------

class FakeLightning:
    """Answers triage batches from a {pair text fragment: answer} rule list."""

    def __init__(self, answer_for, broken=False):
        self.answer_for, self.broken, self.batches = answer_for, broken, []

    def __call__(self, model, messages, **kw):
        assert model == llm.LIGHTNING
        lines = messages[1]["content"].splitlines()
        # each pair is an "N. A ..." line followed by its "   B ..." line
        pairs = [line + " " + lines[i + 1] for i, line in enumerate(lines) if line[:1].isdigit()]
        self.batches.append(len(pairs))
        if self.broken:
            return "not json"
        return json.dumps({"answers": [{"pair": i, "answer": self.answer_for(line)}
                                       for i, line in enumerate(pairs, 1)]})


def test_triage_batches_and_answers(monkeypatch):
    fake = FakeLightning(lambda line: "no" if "restoration 9" in line else "yes")
    monkeypatch.setattr(llm, "chat", fake)
    cands = [cand("numeric", A, claim(f"x{i}", 3, "area", 9, "ha", f"restoration {i}"))
             for i in range(10)]
    answers = ct.triage(cands)
    b = ct.TRIAGE_QUOTE_BATCH          # no page texts: quotes-only view
    assert fake.batches == [min(b, 10 - i) for i in range(0, 10, b)]
    assert answers == ["yes"] * 9 + ["no"]


def test_triage_unclear_answers_are_unsure(monkeypatch):
    monkeypatch.setattr(llm, "chat", FakeLightning(lambda l: "", broken=True))
    assert ct.triage([cand("numeric", A, B)]) == ["unsure"]
    monkeypatch.setattr(llm, "chat", FakeLightning(lambda l: "maybe"))
    assert ct.triage([cand("numeric", A, B)]) == ["unsure"]


def test_recycled_figures_skip_triage(monkeypatch):
    fake = FakeLightning(lambda l: "no")
    monkeypatch.setattr(llm, "chat", fake)
    assert ct.triage([cand("recycled", A, B)]) == ["yes"] and fake.batches == []


def test_check_skips_triaged_out_and_keeps_ids_stable(monkeypatch):
    c1, c2, c3 = cand("numeric", A, B), cand("numeric", A, B), cand("numeric", A, B)
    monkeypatch.setattr(ct, "triage", lambda cands, pages=None: ["yes", "no", "unsure"])
    verdicts = []

    def fake_chat(model, messages, **kw):
        verdicts.append(model)
        return '{"grade": "ORANGE", "reason": "Scope unclear."}'

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(llm, "is_cached", lambda *a, **k: True)
    out = ct.check([c1, c2, c3], {1: "x", 2: "y"}, use_triage=True)
    assert verdicts == [llm.ULTRA, llm.ULTRA]                 # the "no" never reaches Ultra
    assert [f["id"] for f in out] == ["ct-001", "ct-003"]      # ids follow the full list
    assert ct.last_run["triage"] == {"yes": 1, "no": 1, "unsure": 1}


# ---------- recall fix A: numeric statements, currency ----------

def test_statement_with_number_and_unit_pairs_with_quantity():
    src = claim("s", 1, "quantity", 63.7, "%", "male literacy percentage")
    stmt = claim("t", 2, "statement", 95.55, "%", "male literacy percentage")
    assert len(ct.numeric_pairs([src, stmt])) == 1
    no_unit = claim("u", 2, "statement", 95.55, None, "male literacy percentage")
    assert ct.numeric_pairs([src, no_unit]) == []


@pytest.mark.parametrize("a, b, same", [
    ("INR Lacs/ Yr", "INR Lacs", True), ("Rs. lakh", "lacs", True),
    ("crore", "INR Lacs", True), ("INR Lacs", "ha", False),
])
def test_currency_units(a, b, same):
    assert (ct.unit_key(a)[0] == ct.unit_key(b)[0]) is same
    assert ct.unit_key("crore")[1] == 100 * ct.unit_key("lakh")[1]


# ---------- recall fix B: rule pass ----------

PAGE = ("The proposed airport is described here. As per the field survey, the figure for "
        "airport runway reclamation is 106 Ha. The coral restoration cost is 1600 INR Lacs per "
        "year. The island is about 25 km from the shipping lane. Nothing numeric here at all.")


def test_rule_claims_fill_gaps():
    covered = [claim("p5-01", 5, "distance", 25, "km", "shipping lane",
                     "The island is about 25 km from the shipping lane.")]
    out = claims.rule_claims(5, PAGE, covered)
    assert [(c["type"], c["value"], c["unit"]) for c in out] == [
        ("area", 106, "Ha"), ("quantity", 1600, "INR Lacs")]
    for c in out:
        assert c["source"] == "rule" and c["verified"] and c["id"].startswith("p5-r")
        assert claims.quote_on_page(c["quote"], PAGE)                 # exact page text
    assert "runway reclamation" in out[0]["subject"]


def test_rule_claims_skip_long_and_numberless_sentences():
    long = " ".join(["word"] * 70) + " 5 ha."
    assert claims.rule_claims(1, long, []) == []
    assert claims.rule_claims(1, "No numbers in this sentence at all.", []) == []


def test_extract_claims_rule_pass_flag(monkeypatch):
    monkeypatch.setattr(claims, "chat_json", lambda *a, **k: {"claims": []})
    page = {"page": 5, "text": PAGE, "needs_vision": False, "image_path": None, "error": None}
    assert len(claims.extract_claims([page])) == 3
    assert claims.extract_claims([page], rule_pass=False) == []


def test_rule_claims_are_not_planted_sources():
    import random
    ledger = [claim("p1-01", 1, "count", 330, "species", "fauna", source="page"),
              claim("p1-r01", 1, "area", 900, "ha", "rule area", source="rule")]
    picked = ev.pick_source_claims(ledger, 5, random.Random(0))
    assert [c["id"] for c in picked] == ["p1-01"]


# ---------- scope ----------

@pytest.mark.parametrize("text, reason", [
    ("परियोजना क्षेत्र में वन क्षेत्र है और यह द्वीप पर स्थित है। " * 5, "hindi"),
    ("Test report. Sample ID 12. Sampling date 01.02.2021. pH 7.2 mg/l 0.01 BDL NABL "
     + "12 34 56 78 90 " * 20, "lab_report"),
    ("Name: ________ Address: ________ Village: ________ District: ________ "
     "Phone: ________ Signature: ________ Date: ________", "blank_form"),
    ("ANNEXURE-I APPLICABLE ENVIRONMENT STANDARDS AI-1 National Ambient Air Quality", "annexure"),
    ("ANNEXURE II THE GAZETTE OF INDIA. A total of 330 species of fauna are recorded from "
     "the Galathea National Park.", None),                         # notifications are kept
    ("A total of 695 species of fauna have been reported from Great Nicobar Island.", None),
])
def test_scope_skip_reason(text, reason):
    assert scope.skip_reason({"page": 1, "text": text}) == reason


def test_select_pages():
    pages = [{"page": 1, "text": "A normal English page about the site."},
             {"page": 2, "text": "परियोजना क्षेत्र " * 10},
             {"page": 3, "text": "", "error": "broken"}]
    kept, skipped = scope.select_pages(pages)
    assert [p["page"] for p in kept] == [1]
    assert skipped == {"hindi": [2], "error": [3]}


def test_audit_estimate_formula():
    per = {"text_page_usd": 0.001, "vision_page_usd": 0.01, "verdicts_per_page": 2.0,
           "triage_pass_rate": 0.5, "triage_usd_per_candidate": 0.0001, "verdict_usd": 0.01,
           "text_page_s": 1, "vision_page_s": 2, "triage_s_per_candidate": 0.1, "verdict_s": 3}
    kept = [{"page": i, "needs_vision": i < 10} for i in range(100)]
    e = audit.estimate(kept, per, top_passages=100)
    # 90 text + 10 vision; 200 candidates; 100 verdicts
    assert e["candidates"] == 200 and e["ultra_verdicts"] == 100
    assert e["usd"] == {"claims": 0.19, "triage": 0.02, "verdicts": 1.0}
    assert e["tavily_credits"] == 200


# ---------- triage context ----------

LONG_PAGE = ("Intro sentence. " * 100 + "The total reclaimed land will be 194 ha. "
             + "Later sentence. " * 100)


def test_quote_context_window():
    c = claim("t", 444, "area", 194, "ha", "reclaimed land", "The total reclaimed land will be 194 ha.")
    ctx = ct.quote_context(c, {444: LONG_PAGE})
    assert "The total reclaimed land will be 194 ha." in ctx
    assert len(ctx) <= ct.TRIAGE_CONTEXT_CHARS + 10 and ctx.startswith("...") and ctx.endswith("...")
    assert ct.quote_context(c, {}) == ""


def test_triage_messages_include_context_only_with_pages():
    t = claim("t", 444, "area", 194, "ha", "reclaimed land", "The total reclaimed land will be 194 ha.")
    p = claim("p", 751, "area", 71, "ha", "airport", "needs 71 ha")
    plain = ct.triage_messages([cand("numeric", t, p)])
    rich = ct.triage_messages([cand("numeric", t, p)], {444: LONG_PAGE, 751: "It needs 71 ha for the runway."})
    assert "Context of A" not in plain[1]["content"]
    assert "Context of A" in rich[1]["content"] and "It needs 71 ha for the runway." in rich[1]["content"]
    assert "page text around both quotes" in rich[0]["content"]


# ---------- two-view ensemble ----------

@pytest.mark.parametrize("a, b, out", [
    ("no", "no", "no"), ("no", "yes", "yes"), ("yes", "no", "yes"), ("no", "unsure", "unsure"),
    ("unsure", "unsure", "unsure"), ("yes", "unsure", "yes"),
])
def test_combine_triage(a, b, out):
    assert ct.combine_triage(a, b) == out


def test_triage_with_pages_drops_only_when_both_views_say_no(monkeypatch):
    """Quotes-only says no to both pairs; the context view rescues pair 2."""
    def fake(model, messages, **kw):
        with_context = "Context of A" in messages[1]["content"]
        n = sum(1 for l in messages[1]["content"].splitlines() if l[:1].isdigit())
        answers = ["no", "yes"] if with_context and n == 2 else ["no"] * n
        return json.dumps({"answers": [{"pair": i, "answer": a} for i, a in enumerate(answers, 1)]})

    monkeypatch.setattr(llm, "chat", fake)
    t = claim("t", 1, "area", 194, "ha", "land", "total land 194 ha")
    p = claim("p", 2, "area", 71, "ha", "airport", "airport 71 ha")
    pages = {1: "total land 194 ha", 2: "airport 71 ha"}
    assert ct.triage([cand("numeric", t, p), cand("numeric", p, t)], pages) == ["no", "yes"]
