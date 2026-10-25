"""Claim extraction with the model mocked (no network, no cost)."""

import json
from pathlib import Path

import pymupdf
import pytest

from tigerfish import claims, llm

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_818 = ("A number of potential and economically important species including Nypa\n"
            "fruticans and Vanilla anadamanica grows wild in the protected area; AND WHEREAS,a\n"
            "total of 330 species of fauna are recorded from the Campbell Bay National Park\n"
            "including 28 species of mammals")


class FakeChat:
    """Replaces llm.chat: returns queued replies, records calls, optionally adds cost."""

    def __init__(self, *replies, cost_per_call=0.0):
        self.replies, self.calls, self.cost = list(replies), [], cost_per_call

    def __call__(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        llm.session_cost_usd += self.cost
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(claims, "LEDGER_DIR", tmp_path / "claims")
    monkeypatch.setattr(llm, "is_cached", lambda *a, **k: False)

    def install(*replies, cost_per_call=0.0):
        f = FakeChat(*replies, cost_per_call=cost_per_call)
        monkeypatch.setattr(llm, "chat", f)
        return f
    return install


def page(n, text=PAGE_818, **extra):
    return {"page": n, "text": text, "needs_vision": False, "image_path": None, "error": None,
            **extra}


# ---------- parsing ----------

@pytest.mark.parametrize("reply", [
    '{"claims": []}',
    '```json\n{"claims": []}\n```',
    'Here are the claims:\n{"claims": []}\nHope this helps.',
])
def test_parse_json_tolerates_wrapping(reply):
    assert claims.parse_json(reply) == {"claims": []}


@pytest.mark.parametrize("reply", ["", "no json here", '{"claims": [', "[1, 2]"])
def test_parse_json_rejects_broken(reply):
    with pytest.raises(ValueError):
        claims.parse_json(reply)


# ---------- quote verification ----------

def test_quote_verified_across_line_breaks():
    assert claims.quote_on_page(
        "a total of 330 species of fauna are recorded from the Campbell Bay National Park",
        PAGE_818)


@pytest.mark.parametrize("quote", ["", "   ", "28 mammal species are found in the park",
                                   "a total of 331 species of fauna"])
def test_quote_not_verified(quote):
    assert not claims.quote_on_page(quote, PAGE_818)


def test_to_claims_verifies_and_cleans():
    raw = claims.parse_json((FIXTURES / "claims_page_reply.txt").read_text(encoding="utf-8"))
    out = claims.to_claims(raw, 818, PAGE_818, llm.LIGHTNING)
    assert [c["id"] for c in out] == ["p818-01", "p818-02", "p818-03"]
    assert [c["verified"] for c in out] == [True, False, True]
    assert out[2]["type"] == "statement"          # unknown type "habitat" falls back
    assert out[0]["value"] == 330 and out[0]["page"] == 818
    assert claims.verified_stats(out)["verified_rate"] == pytest.approx(2 / 3)


# ---------- retry and skip ----------

def test_broken_json_is_retried_once(fake):
    good = (FIXTURES / "claims_page_reply.txt").read_text(encoding="utf-8")
    chat = fake("Sorry, here you go: {claims: oops", good)
    out = claims.extract_claims([page(818)])
    assert len(chat.calls) == 2 and len(out) == 3
    retry_messages = chat.calls[1][1]
    assert retry_messages[-1]["content"] == claims.RETRY_MSG
    assert retry_messages[-2] == {"role": "assistant", "content": "Sorry, here you go: {claims: oops"}


def test_page_skipped_after_second_failure(fake, caplog):
    chat = fake("not json", "still not json")
    out = claims.extract_claims([page(818)])
    assert out == [] and len(chat.calls) == 2
    assert claims.last_run["pages_skipped"] == [818]
    assert "page 818 skipped" in caplog.text


def test_lightning_used_with_thinking_off(fake):
    chat = fake('{"claims": []}')
    claims.extract_claims([page(818)])
    model, messages, kwargs = chat.calls[0]
    assert model == llm.LIGHTNING and kwargs["thinking"] is False
    assert messages[0]["role"] == "system" and "Page 818" in messages[1]["content"]


# ---------- cost cap ----------

def test_cost_cap_stops_the_run(fake, monkeypatch):
    monkeypatch.setattr(claims, "estimate_page_cost", lambda p: 0.15)
    chat = fake('{"claims": []}', cost_per_call=0.2)
    claims.extract_claims([page(n) for n in (1, 2, 3, 4)], max_cost_usd=0.5)
    # spent 0.0 + 0.15 ok, 0.2 + 0.15 ok, 0.4 + 0.15 > 0.5 -> stop before page 3
    assert len(chat.calls) == 2
    assert claims.last_run["pages_done"] == [1, 2]
    assert "cost cap" in claims.last_run["stopped"]


def test_cached_pages_estimate_zero(monkeypatch):
    monkeypatch.setattr(llm, "is_cached", lambda *a, **k: True)
    assert claims.estimate_cost([page(1), page(2)]) == (0.0, 0)


def test_estimate_uses_prices(monkeypatch):
    monkeypatch.setattr(llm, "is_cached", lambda *a, **k: False)
    est, uncached = claims.estimate_cost([page(1)])
    assert uncached == 1 and 0 < est < 0.01     # Lightning: a page costs fractions of a cent


# ---------- vision ----------

@pytest.fixture
def png(tmp_path):
    def make(name, color):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
        pix.set_rect(pix.irect, color)
        path = tmp_path / name
        pix.save(path)
        return path
    return make


def test_vision_page_goes_to_super_vl_with_image(fake, png):
    chat = fake('{"claims": []}')
    claims.extract_claims([page(751, needs_vision=True, image_path=str(png("p.png", (0, 0, 0))))])
    model, messages, _ = chat.calls[0]
    parts = messages[0]["content"]
    assert model == llm.SUPER_VL
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "Page 751 text" in parts[0]["text"]


def test_image_cache_key_uses_image_hash(png):
    a, b = png("a.png", (0, 0, 0)), png("b.png", (255, 255, 255))
    msg = lambda p: [{"role": "user", "content": [{"type": "text", "text": "read"},
                                                  llm.image_part(p)]}]
    key_a = llm._cache_key(llm.SUPER_VL, msg(a), {})
    assert key_a == llm._cache_key(llm.SUPER_VL, msg(a), {})
    assert key_a != llm._cache_key(llm.SUPER_VL, msg(b), {})
    hashed = json.dumps(llm._hash_images(msg(a)))
    assert "base64" not in hashed and "image_sha256" in hashed


def test_text_cache_key_unchanged():
    msgs = [{"role": "user", "content": "Say hello in one line"}]
    old = llm.hashlib.sha256(json.dumps({"model": "m", "messages": msgs, "kwargs": {}},
                                        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert llm._cache_key("m", msgs, {}) == old


def test_table_to_species_claims(fake, png):
    fake((FIXTURES / "table_3_16_reply.json").read_text(encoding="utf-8"))
    table = claims.extract_table_from_image(png("t.png", (0, 0, 0)))
    assert claims.name_column(table) == "Zoological name"
    assert table["rows"][0]["Common name"] == "Chital"
    out = claims.species_claims_from_table(table, source="t.png")
    names = [c["value"] for c in out]
    assert len(names) == 12 and "Taupaia nicobarica nicobarica" in names   # typo kept as printed
    assert all(c["type"] == "species" and c["verified"] is None for c in out)


def test_name_column_guessed_from_header():
    table = {"columns": ["Sl.", "Scientific Name", "Local name"], "rows": [],
             "scientific_name_column": "wrong"}
    assert claims.name_column(table) == "Scientific Name"


# ---------- ledger ----------

def test_ledger_merges_by_page(fake):
    fake((FIXTURES / "claims_page_reply.txt").read_text(encoding="utf-8"))
    claims.extract_claims([page(818), page(851)], pdf_stem="doc")
    assert {c["page"] for c in claims.load_ledger("doc")} == {818, 851}
    fake('{"claims": []}')
    claims.extract_claims([page(851)], pdf_stem="doc")        # re-run 851 only
    ledger = claims.load_ledger("doc")
    assert {c["page"] for c in ledger} == {818} and len(ledger) == 3


# ---------- quote repair ----------

PAGE_234 = ("Submergence of West Coast Significant change occurred post tsunami resulting\n"
            "complete submergence of Megapode Island. About 550 sq.km was badly affected. Before\n"
            "Tusnami the GNI had total area of 1045 sq km which reduced to 910 sqkm after the\n"
            "Tsunami due to the submergence of part of the island.")


def test_repair_restores_report_typo():
    model_quote = ("Before Tsunami the GNI had total area of 1045 sq km which reduced to "
                   "910 sqkm after the Tsunami due to the submergence of part of the island.")
    exact, ratio = claims.repair_quote(model_quote, PAGE_234)
    assert exact.startswith("Before Tusnami the GNI")          # the report's own spelling
    assert exact in claims.normalize(PAGE_234) and ratio >= 0.9


def test_repair_rejects_paraphrase():
    exact, ratio = claims.repair_quote("The island lost a lot of land in the tsunami.", PAGE_234)
    assert exact is None and ratio < 0.9


def test_to_claims_marks_repaired_quote():
    raw = {"claims": [{"type": "area", "subject": "GNI area", "value": 910, "unit": "sq km",
                       "quote": "Before Tsunami the GNI had total area of 1045 sq km which "
                                "reduced to 910 sqkm after the Tsunami"}]}
    stats = {}
    [c] = claims.to_claims(raw, 234, PAGE_234, llm.LIGHTNING, stats=stats)
    assert c["verified"] is True and c["quote_repaired"] is True
    assert "Tusnami" in c["quote"] and "Tsunami the GNI" in c["model_quote"]
    assert stats["repaired"] == 1


def test_exact_quote_is_not_marked_repaired():
    raw = {"claims": [{"type": "area", "value": 550, "quote": "About 550 sq.km was badly affected."}]}
    [c] = claims.to_claims(raw, 234, PAGE_234, llm.LIGHTNING)
    assert c["verified"] and not c["quote_repaired"] and "model_quote" not in c


# ---------- junk filter ----------

@pytest.mark.parametrize("value, quote, ok", [
    (1045, "original notified area of 1,045 Sq.km.", True),
    (4, "Approximately 4ha of Coral restoration", True),
    (2, "it would not exceed 1-2 ha at the maximum", True),
    ("1-2", "it would not exceed 1-2 ha at the maximum", True),
    (22.73, "equivalent to 22.73%", True),
    (16610, "at Great Nicobar Island, Nicobar District", False),
    (330, "a total of 331 species of fauna", False),
    ("no coral exists in the bay portion", "As per the ZSI report, no coral exists in the bay portion of the Galathea Bay.", True),
    ("prevent collisions with turtles", "Roads are an integral part of the transport system", False),
    (None, "anything", True),
])
def test_value_in_quote(value, quote, ok):
    assert claims.value_in_quote(value, quote) is ok


def test_dedupe_merges_near_duplicates_only():
    base = {"page": 392, "type": "statement", "subject": "Road construction", "verified": False}
    a = {**base, "quote": "Roads are an integral part of the transport system for the proposed project"}
    b = {**base, "quote": "Roads are an integral part of the transport system for the proposed projects",
         "verified": True}
    other_subject = {**a, "subject": "Beach lighting"}
    other_type = {**a, "type": "quantity"}
    kept = claims.dedupe([a, b, other_subject, other_type])
    assert len(kept) == 3
    assert kept[0] is b                       # the verified duplicate wins


def test_to_claims_reports_removed_junk():
    raw = {"claims": [
        {"type": "area", "subject": "project", "value": 16610, "unit": "ha",
         "quote": "About 550 sq.km was badly affected."},                     # value not in quote
        {"type": "area", "subject": "affected area", "value": 550, "quote": "About 550 sq.km was badly affected."},
        {"type": "area", "subject": "affected area", "value": 550, "quote": "About 550 sq.km was badly affected"},
    ]}
    stats = {}
    out = claims.to_claims(raw, 234, PAGE_234, llm.LIGHTNING, stats=stats)
    assert len(out) == 1 and out[0]["id"] == "p234-01"
    assert stats["dropped_value"] == 1 and stats["dropped_duplicate"] == 1
