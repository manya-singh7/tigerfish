"""Model badges: which model or tool produced each piece of a finding (offline, saved data)."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tigerfish.ui import badges, data, memo_ask

ROOT = Path(__file__).resolve().parent.parent
GN = "great_nicobar_2021_draft"
saved = pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(),
                           reason="no results/ (run scripts/export_results.py)")

RD = {"pages": {392: badges.READ_LIGHTNING, 978: badges.READ_SUPER_VL,
                818: badges.READ_LIGHTNING, 851: badges.READ_LIGHTNING}, "table": None}


def finding(check, pages=(), evidence=(), where=None):
    quotes = [{"page": p, "text": "q"} for p in pages] or [{"page": None, "where": where, "text": "q"}]
    return {"id": "x-1", "check": check, "quotes": quotes, "evidence": list(evidence)}


ULTRA = {"label": "Checked by", "value": "Nemotron Ultra, reading both full pages"}


def labels(b):
    return [label for label, _ in b]


def test_contradiction_shows_reader_per_page_then_triage_then_ultra():
    b = badges.finding_badges(finding("contradiction", [978, 392], [ULTRA]), RD)
    assert b == [(badges.READ_SUPER_VL, "p.978"), (badges.READ_LIGHTNING, "p.392"),
                 (badges.SCREENED_LIGHTNING, ""), (badges.JUDGED_ULTRA, "")]


def test_human_verified_badge_last_and_manual_sources_not_tavily():
    f = {"check": "accreditation", "quotes": [{"page": 18, "text": "q"}],
         "evidence": [{"label": "Certificate", "value": "33 B", "url": "https://x/c.pdf", "manual": True}],
         "verification": {"by": "Manya Singh", "on": "2026-10-27"}}
    got = badges.finding_badges(f)
    assert got[-1] == (badges.HUMAN_VERIFIED, "Manya Singh, 2026-10-27")
    assert badges.TAVILY not in [label for label, _ in got]     # the only link was added by hand
    unverified = badges.finding_badges({**f, "verification": None})
    assert badges.HUMAN_VERIFIED not in [label for label, _ in unverified]


@saved
def test_saved_human_verified_findings():
    """The findings checked by hand (data/known_issues.json) carry the badge and the wording."""
    found = {f["known_issue"]: f for f in data.load(GN)["findings"] if f.get("verification")}
    assert set(found) == {"gn-001", "gn-003", "gn-004", "gn-005", "gn-006", "gn-007", "gn-008",
                          "gn-009", "gn-010", "gn-011"}
    assert found["gn-001"]["title"] == "Inconsistent about coral at the port site"
    assert "in and around Galathea Bay" in found["gn-006"]["title"]
    assert "proposed Terms of Reference" in found["gn-011"]["title"]
    assert found["gn-011"]["id"] == "pr-06" and found["gn-010"]["id"] == "ac-01"
    assert any(e.get("manual") and "NABET-Certificate-2023-2026" in e["url"]
               for e in found["gn-010"]["evidence"])
    for f in found.values():
        assert f["verification"]["by"] == "Manya Singh" and f["verification"]["note"]


def test_pages_are_grouped_and_sorted():
    b = badges.finding_badges(finding("recycled_figure", [851, 818], [ULTRA]), RD)
    assert b[0] == (badges.READ_LIGHTNING, "pp.818, 851")


def test_recycled_figures_are_not_triaged():
    assert badges.SCREENED_LIGHTNING not in labels(
        badges.finding_badges(finding("recycled_figure", [818, 851], [ULTRA]), RD))


def test_unknown_page_gets_no_reader_badge():
    b = badges.finding_badges(finding("contradiction", [5], [ULTRA]), RD)
    assert labels(b) == [badges.SCREENED_LIGHTNING, badges.JUDGED_ULTRA]


def test_promise_judged_by_ultra_only_when_ultra_checked_it():
    by_ultra = finding("promise", [292], [{"label": "Verdict",
                                           "value": "not met, checked by Nemotron Ultra, reading"}])
    first_pass = finding("promise", [292], [{"label": "Verdict", "value": "not found, checked by "
                                             "Nemotron Lightning (first pass only; not confirmed by Ultra)"}])
    assert labels(badges.finding_badges(by_ultra, RD)) == [badges.SCREENED_LIGHTNING, badges.JUDGED_ULTRA]
    assert labels(badges.finding_badges(first_pass, RD)) == [badges.SCREENED_LIGHTNING]


def test_tavily_needs_a_linked_source():
    linked = finding("borrowed_text", [392], [{"label": "Source", "value": "s", "url": "https://x.org"}])
    unlinked = finding("borrowed_text", [392], [{"label": "Verbatim run", "value": "25 words"}])
    assert labels(badges.finding_badges(linked, RD)) == [badges.TAVILY]
    assert badges.finding_badges(unlinked, RD) == []


def test_gbif_checks_and_table_image():
    rd = {"pages": {}, "table": badges.READ_SUPER_VL}
    b = badges.finding_badges(finding("species_range", where="Table 3.16"), rd)
    assert b == [(badges.READ_SUPER_VL, "table image"), (badges.GBIF, "")]
    assert labels(badges.finding_badges(finding("omission", where="GBIF"), RD)) == [badges.GBIF]


def test_accreditation_pages_read_by_lightning_and_sources_from_tavily():
    f = finding("accreditation", [44, 18], [{"label": "Official", "value": "v", "url": "https://qci.org.in"}])
    assert badges.finding_badges(f, RD) == [(badges.READ_LIGHTNING, "pp.18, 44"), (badges.TAVILY, "")]


def test_html_is_plain_text_escaped_and_has_hover_text():
    out = badges.html([(badges.READ_SUPER_VL, "p.978"), (badges.GBIF, "<b>")])
    assert "Read by Super-VL" in out and "p.978" in out and "&lt;b&gt;" in out
    assert 'title="Nemotron 3.5 Super-VL' in out
    assert out.isascii()                     # plain text labels, no emojis
    assert badges.html([]) == ""


def test_every_label_has_a_style_and_ascii_text():
    for label, (kind, tip) in badges.INFO.items():
        assert kind in ("nemotron", "tavily", "gbif", "human") and tip
        assert label.isascii() and tip.isascii()


def test_readers_from_page_file_inspector_fallback_and_table(tmp_path):
    badges.readers.cache_clear()
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "page_readers_a.json").write_text(
        json.dumps({"super_vl": [978], "lightning": [392]}), encoding="utf-8")
    assert badges.readers("a", tmp_path)["pages"] == {978: badges.READ_SUPER_VL, 392: badges.READ_LIGHTNING}

    (tmp_path / "inspector").mkdir()
    (tmp_path / "inspector" / "index.json").write_text(
        json.dumps({"report_id": "b", "pages": [{"page": 896}]}), encoding="utf-8")
    assert badges.readers("b", tmp_path)["pages"] == {896: badges.READ_SUPER_VL}

    (tmp_path / "c.json").write_text(json.dumps(
        {"unit": "table", "checks": ["Table reading (Nemotron Super-VL)"]}), encoding="utf-8")
    assert badges.readers("c", tmp_path) == {"pages": {}, "table": badges.READ_SUPER_VL}
    assert badges.readers("missing", tmp_path) == {"pages": {}, "table": None}
    badges.readers.cache_clear()


def test_memo_and_ask_badges():
    assert badges.memo_badges({"pages_included": 1071}) == [(badges.JUDGED_ULTRA, "1,071 pages, one call")]
    a = {"report_says": False, "unverified_citations": []}
    assert "Answered by Ultra" in memo_ask.answer_html(a)


# ---------- saved results ----------

@saved
def test_saved_coral_contradiction_badges():
    rd = badges.readers(GN)
    f = next(f for f in data.load(GN)["findings"] if f.get("known_issue") == "gn-001")
    assert badges.finding_badges(f, rd) == [
        (badges.READ_LIGHTNING, "p.392"), (badges.READ_SUPER_VL, "p.978"),
        (badges.SCREENED_LIGHTNING, ""), (badges.JUDGED_ULTRA, ""),
        (badges.HUMAN_VERIFIED, "Manya Singh, 2026-10-27")]


@saved
def test_every_saved_finding_has_a_badge():
    for r in data.reports():
        rd = badges.readers(r["id"])
        for f in data.load(r["id"])["findings"]:
            assert badges.finding_badges(f, rd), f["id"]


@saved
def test_page_readers_file_matches_inspector_pages():
    rd = badges.readers(GN)["pages"]
    for p in json.loads((ROOT / "results" / "inspector" / "index.json").read_text(encoding="utf-8"))["pages"]:
        assert rd.get(p["page"]) == badges.READ_SUPER_VL, p["page"]


@saved
def test_app_shows_badges_on_cards_memo_and_answers(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    for label in (badges.READ_LIGHTNING, badges.READ_SUPER_VL, badges.SCREENED_LIGHTNING,
                  badges.JUDGED_ULTRA, badges.TAVILY, badges.GBIF, badges.ANSWERED_ULTRA):
        assert f">{label}" in text, label
