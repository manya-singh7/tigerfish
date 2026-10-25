"""Contradiction check with the model mocked (no network, no cost)."""

import json

import pytest

from tigerfish import contradictions as ct
from tigerfish import llm


def claim(cid, page, ctype, value, unit, subject, quote, verified=True):
    return {"id": cid, "page": page, "type": ctype, "value": value, "unit": unit,
            "subject": subject, "quote": quote, "verified": verified}


CORAL_LOSS = claim("p444-01", 444, "area", 2, "ha", "maximum coral loss during construction",
                   "it would not exceed 1-2 ha at the maximum")
CORAL_RESTORE = claim("p751-01", 751, "area", 4, "ha", "coral restoration",
                      "Approximately 4ha of Coral restoration has been considered.")


# ---------- step 1: numeric pairs ----------

def test_numeric_pair_found():
    [cand] = ct.numeric_pairs([CORAL_LOSS, CORAL_RESTORE])
    assert cand["kind"] == "numeric"
    assert {c["id"] for c in cand["claims"]} == {"p444-01", "p751-01"}


def test_units_are_converted():
    a = claim("a", 1, "area", 910, "sq km", "island area", "910 sq km")
    b = claim("b", 2, "area", 91000, "ha", "island area", "91000 ha")
    c = claim("c", 3, "area", 1045, "Sq.km.", "island area", "1045 Sq.km.")
    pairs = ct.numeric_pairs([a, b, c])
    assert {frozenset(x["id"] for x in p["claims"]) for p in pairs} == \
        {frozenset({"a", "c"}), frozenset({"b", "c"})}      # 910 sq km == 91000 ha


@pytest.mark.parametrize("b, why", [
    (claim("x", 444, "area", 4, "ha", "coral restoration", "4 ha"), "same page"),
    (claim("x", 751, "area", 2.05, "ha", "coral restoration", "2.05 ha"), "within 5%"),
    (claim("x", 751, "distance", 4, "km", "coral restoration", "4 km"), "different type"),
    (claim("x", 751, "area", 4, "km", "coral restoration", "4 km"), "length vs area unit"),
    (claim("x", 751, "area", 4, "ha", "airport runway", "4 ha"), "unrelated subject"),
    (claim("x", 751, "area", 4, "ha", "coral restoration", "4 ha", verified=False), "unverified"),
])
def test_numeric_pair_not_found(b, why):
    assert ct.numeric_pairs([CORAL_LOSS, b]) == [], why


def test_count_and_quantity_compare_as_one_kind():
    a = claim("a", 1168, "count", 330, "species", "fauna species recorded from GNI",
              "A total of 330 species of fauna")
    b = claim("b", 940, "quantity", 695, "species", "fauna species reported from Great Nicobar Island",
              "A total of 695 species of fauna")
    assert len(ct.numeric_pairs([a, b])) == 1


# ---------- step 1: statement pairs ----------

NO_CORAL = claim("p392-01", 392, "statement", "no coral exists in the bay portion", None,
                 "coral presence in Galathea Bay",
                 "As per the ZSI report, no coral exists in the bay portion of the Galathea Bay.")
CORAL_EXISTS = claim("p978-03", 978, "statement", "exists", None, "coral reefs at port site",
                     "Coral reef exists in the proposed site for Transshipment / Port")


def test_absence_vs_presence_pair():
    [cand] = ct.statement_pairs([NO_CORAL, CORAL_EXISTS])
    assert cand["claims"] == [NO_CORAL, CORAL_EXISTS]


def test_absence_topic():
    assert ct.absence_topic(NO_CORAL) == {"coral"}
    not_done = claim("x", 940, "statement", "not completed", None, "hatchling estimation",
                     "estimation of the number of hatchlings is not completed")
    assert ct.absence_topic(not_done) is None          # not an absence of a thing


@pytest.mark.parametrize("quote", [
    "No coral reef exists in the proposed site",          # also an absence
    "Mangrove patches are existing in the Galathea riverine region.",   # different topic
])
def test_statement_pair_not_found(quote):
    other = {**CORAL_EXISTS, "quote": quote}
    assert ct.statement_pairs([NO_CORAL, other]) == []


# ---------- step 1: recycled figures ----------

def park_page(page, place, total=330):
    figures = [(total, "fauna"), (28, "mammal"), (97, "bird"), (23, "reptile")]
    return [claim(f"p{page}-{i}", page, "count", v, "species",
                  f"{what} species recorded from {place}",
                  f"{v} species of {what}") for i, (v, what) in enumerate(figures)]


def test_recycled_figure_found_once_with_breakdown():
    cl = park_page(818, "Campbell Bay National Park") + park_page(851, "Galathea National Park") \
        + park_page(1168, "GNI")
    [rec] = ct.recycled_figures(cl)
    assert rec["value"] == 330 and rec["breakdown"] == [23.0, 28.0, 97.0]
    assert sorted(c["page"] for c in rec["claims"]) == [818, 851, 1168]


def test_recycled_needs_different_subjects():
    cl = park_page(818, "Campbell Bay National Park") + park_page(851, "Campbell Bay National Park")
    assert ct.recycled_figures(cl) == []


def test_recycled_needs_breakdown(monkeypatch):
    monkeypatch.setattr(ct, "MIN_BREAKDOWN", 4)
    cl = park_page(818, "Campbell Bay National Park") + park_page(851, "Galathea National Park")
    assert ct.recycled_figures(cl) == []


def test_candidate_cap_logs_dropped(caplog):
    cl = park_page(818, "Campbell Bay National Park") + park_page(851, "Galathea National Park") \
        + [NO_CORAL, CORAL_EXISTS, CORAL_LOSS, CORAL_RESTORE]
    cands = ct.candidate_pairs(cl, max_candidates=2)
    assert len(cands) == 2 and ct.last_run["candidates_dropped"] >= 1
    assert "dropped by MAX_CANDIDATES" in caplog.text
    assert cands[0]["kind"] == "recycled"


# ---------- step 2: explanation search ----------

PAGE_234 = ("Some unrelated text about roads. " * 40 + "Before Tusnami the GNI had total area of "
            "1045 sq km which reduced to 910 sqkm after the Tsunami. " + "Filler sentence here. " * 60
            + "A revised map is attached.")


def test_explanation_hits_near_and_far():
    c = claim("a", 234, "area", 910, "sq km", "GNI area",
              "Before Tusnami the GNI had total area of 1045 sq km")
    hits = ct.explanation_hits({"kind": "numeric", "claims": [c]}, {234: PAGE_234})
    words_near = {h["word"] for h in hits if h["near_quote"]}
    assert {"before", "total", "reduced", "after", "tsunami"} <= words_near
    far = [h for h in hits if not h["near_quote"]]
    assert any(h["word"] == "revised" for h in far)
    assert hits[0]["near_quote"]                      # near hits come first


# ---------- step 3: verdict parsing ----------

CAND = {"kind": "numeric", "claims": [
    claim("a", 234, "area", 910, "sq km", "GNI area", "910 sqkm"),
    claim("b", 1141, "area", 910, "sq km", "GNI area", "910 sq.km")]}
PAGES = {234: PAGE_234, 1141: "The GNI, with an area of 910 sq.km (original notified area of 1045 Sq.km.)"}


def test_parse_verdict_valid_and_verified_explanation():
    raw = {"grade": "none", "reason": "The report explains the change.",
           "explanation_quote": "Before Tsunami the GNI had total area of 1045 sq km which "
                                "reduced to 910 sqkm after the Tsunami.",
           "explanation_page": 234, "same_subject": True, "incompatible": False, "explained": True}
    v = ct.parse_verdict(raw, CAND, PAGES)
    assert v["grade"] == "NONE"
    assert v["explanation_page"] == 234
    assert v["explanation_quote"].startswith("Before Tusnami")       # repaired to page text


def test_parse_verdict_ignores_unverifiable_explanation():
    raw = {"grade": "RED", "reason": "Different areas.", "explanation_quote": "Nothing like this."}
    v = ct.parse_verdict(raw, CAND, PAGES)
    assert v["grade"] == "RED" and v["explanation_quote"] is None


@pytest.mark.parametrize("raw", [None, [], {"grade": "MAYBE"}, {"reason": "x"}])
def test_parse_verdict_rejects_bad(raw):
    assert ct.parse_verdict(raw, CAND, PAGES) is None


def test_parse_verdict_enforces_neutral_wording():
    v = ct.parse_verdict({"grade": "RED", "reason": "The consultant appears to lie about it."},
                         CAND, PAGES)
    assert "lie" not in v["reason"].lower()


def test_finding_message_is_neutral():
    v = {"grade": "RED", "reason": "r", "explanation_quote": None, "explanation_page": None,
         "same_subject": True, "incompatible": True, "explained": False}
    f = ct.finding(CAND, v, [], 1)
    assert f["message"] == "Inconsistency flagged, verify." and f["type"] == "contradiction"


# ---------- cost cap ----------

def test_cost_cap_stops_verdicts(monkeypatch):
    monkeypatch.setattr(ct, "estimate_cost", lambda cands, pages: (0.15, 1))
    calls = []

    def fake_chat(model, messages, **kw):
        calls.append(model)
        llm.session_cost_usd += 0.2
        return json.dumps({"grade": "ORANGE", "reason": "Scope unclear."})

    monkeypatch.setattr(llm, "chat", fake_chat)
    out = ct.check([CAND, CAND, CAND, CAND], PAGES, max_cost_usd=0.5)
    assert len(calls) == 2 and len(out) == 2
    assert calls == [llm.ULTRA, llm.ULTRA]
    assert "cost cap" in ct.last_run["stopped"]


def test_ultra_called_with_thinking_on(monkeypatch):
    seen = {}

    def fake_chat(model, messages, **kw):
        seen.update(kw, model=model)
        return '{"grade": "NONE", "reason": "Explained."}'

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(llm, "is_cached", lambda *a, **k: True)
    ct.check([CAND], PAGES)
    assert seen["model"] == llm.ULTRA and seen["thinking"] is None   # model default: reasoning on


# ---------- step 4: evaluation ----------

Q = {392: "no coral exists in the bay portion of the Galathea Bay.",
     978: "Coral reef exists in the proposed site for Transshipment / Port",
     818: "a total of 330 species of fauna are recorded from the Campbell Bay National Park",
     851: "a total of 330 species of fauna are recorded from the Galathea National Park",
     1168: "A total of 330 species of fauna are recorded from the whole GNI area",
     234: "Before Tusnami the GNI had total area of 1045 sq km which reduced to 910 sqkm",
     1141: "The GNI, with an area of 910 sq.km (original notified area of 1045 Sq.km.)"}


def issue(iid, itype, pages, grade, **extra):
    return {"id": iid, "type": itype, "pages": pages, "expected_grade": grade,
            "quotes": [{"page": p, "text": Q[p]} for p in pages], **extra}


ISSUES = [
    issue("gn-001", "contradiction", [392, 978], "RED", acceptable_grades=["RED", "ORANGE"]),
    issue("gn-003", "recycled_figure", [818, 851, 1168], "RED"),
    issue("gn-neg-001", "negative_control", [234, 1141], "NONE"),
]


def f(fid, ftype, pages, grade, quotes=None):
    """A finding; by default its quotes are the known-issue quotes for those pages."""
    quotes = quotes or {p: Q[p] for p in pages}
    return {"id": fid, "type": ftype, "pages": pages, "grade": grade,
            "quotes": [{"page": p, "text": t} for p, t in quotes.items()]}


def test_evaluate_uses_acceptable_grades():
    rows = ct.evaluate([f("ct-1", "contradiction", [392, 978], "ORANGE"),
                        f("rf-1", "recycled_figure", [818, 851, 1168], "ORANGE")], ISSUES)
    by = {r["id"]: r for r in rows}
    assert by["gn-001"]["ok"] and by["gn-001"]["grade"] == "ORANGE"
    assert not by["gn-003"]["ok"]                  # ORANGE not acceptable for gn-003
    assert by["gn-neg-001"]["ok"] and not by["gn-neg-001"]["found"]


def test_evaluate_fails_flagged_negative_control():
    rows = ct.evaluate([f("ct-9", "contradiction", [234, 1141], "RED")], ISSUES)
    assert not {r["id"]: r for r in rows}["gn-neg-001"]["ok"]


def test_evaluate_negative_control_ok_when_graded_none():
    rows = ct.evaluate([f("ct-9", "contradiction", [234, 1141], "NONE")], ISSUES)
    assert {r["id"]: r for r in rows}["gn-neg-001"]["ok"]


def test_evaluate_requires_right_type():
    rows = ct.evaluate([f("ct-1", "contradiction", [818, 851, 1168], "RED")], ISSUES)
    assert not {r["id"]: r for r in rows}["gn-003"]["found"]


def test_evaluate_needs_matching_quotes_not_just_pages():
    """p.234/1141 also hold an unrelated distance pair: it must not count as the control."""
    distances = f("ct-15", "contradiction", [234, 1141], "RED",
                  quotes={234: "It is approximately 163 km by sea from Sumatra, Indonesia.",
                          1141: "Indira Point is about 25-40 km from the major international sea route"})
    row = {r["id"]: r for r in ct.evaluate([distances], ISSUES)}["gn-neg-001"]
    assert not row["found"] and row["ok"]


def test_quotes_match():
    assert ct.quotes_match("no coral exists in the bay portion", Q[392])
    assert not ct.quotes_match("It is approximately 163 km by sea from Sumatra", Q[234])


@pytest.mark.parametrize("reason, kept", [
    ("Sumatra lies farther south than the shipping lane.", True),
    ("The two figures lying on different pages differ.", True),
    ("The consultant appears to lie about the area.", False),
    ("This looks like fabricated data.", False),
    ("The figures are fake.", False),
])
def test_banned_words(reason, kept):
    v = ct.parse_verdict({"grade": "ORANGE", "reason": reason}, CAND, PAGES)
    assert (v["reason"] == reason) is kept
