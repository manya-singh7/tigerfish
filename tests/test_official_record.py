"""Official-record check, fully offline: unit normalisation, document dates, grading,
official-domain preference, figure matching and a mocked end-to-end run (fake Tavily, fake
LIGHTNING). No network, no keys."""

import json
from datetime import date
from pathlib import Path

import pytest

from tigerfish import claims as claims_mod
from tigerfish import copycheck, llm
from tigerfish import official_record as off

ROOT = Path(__file__).resolve().parent.parent
RESULT = ROOT / "results" / "official_record_great_nicobar_2021_draft.json"


# ---------- units ----------

@pytest.mark.parametrize("value,unit,expected", [
    (166.1, "sq.km", (16610.0, "area")),
    (166.10, "sq. km", (16610.0, "area")),
    (130.75, "km2", (13075.0, "area")),
    (16610, "hectares", (16610.0, "area")),
    (16610, "ha", (16610.0, "area")),
    (100, "acres", (pytest.approx(40.4686), "area")),
    (72000, "Crores", (72000.0, "money")),
    (72000, "crore rs", (72000.0, "money")),
    (0.72, "lakh crore", (72000.0, "money")),
    (14.2, "Million TEU", (14_200_000.0, "teu")),
    (14.2, "MTEU", (14_200_000.0, "teu")),
    (4000, "Peak Hour Passengers", (4000.0, "pax_peak_hour")),
    (4000, "PHP", (4000.0, "pax_peak_hour")),
    (10, "million passengers per annum", (10_000_000.0, "pax_annual")),
    (450, "MVA", (450.0, "power_mva")),
    (450, "MW", (450.0, "power_mw")),
    (43, "MLD", (43.0, "water_mld")),
    (43000, "KLD", (43.0, "water_mld")),
    (3.3, "lakh persons", (330000.0, "count")),
    (7.11, "lakh trees", (711000.0, "count")),
])
def test_normalize(value, unit, expected):
    assert off.normalize(value, unit) == expected


def test_mw_and_mva_are_different_quantities():
    rf = {"dimension": "power_mva", "normalized": 450.0}
    o = {"dimension": "power_mw", "normalized": 300.0, "quote": "300 MW", "date": date(2021, 6, 1)}
    assert off.grade(rf, o)[0] == "NOT_COMPARABLE"


def test_to_number_and_relative_difference():
    assert off.to_number("3.3 lakh") == 330000.0
    assert off.to_number("72,000 crore") == 72000 * 1e7
    assert off.to_number("none") is None
    assert off.relative_difference(100, 105) == pytest.approx(0.0476, abs=1e-3)
    assert off.relative_difference(5, 5) == 0.0


# ---------- dates ----------

@pytest.mark.parametrize("text,url,expected", [
    ("Ministry of Ports Posted On: 05 NOV 2025 3:41PM by PIB Delhi", "", date(2025, 11, 5)),
    ("RAJYA SABHA UNSTARRED QUESTION NO. 12 ANSWERED ON 07.12.2023 trees", "", date(2023, 12, 7)),
    ("Letter dated 25.05.2021 granting ToR", "", date(2021, 5, 25)),
    ("Great Nicobar Project Strategic Importance 1 May , 2026 Key Takeaways", "", date(2026, 5, 1)),
    ("INTERNAL WORK STUDY UNIT December 2021 induction", "", date(2021, 12, 1)),
    ("no date here", "https://niti.gov.in/sites/default/files/2023-03/x.pdf", date(2023, 3, 1)),
])
def test_document_date(text, url, expected):
    assert off.document_date(text, url)[0] == expected


def test_body_dates_are_not_document_dates():
    text = "x " * 400 + "The project received environmental clearance on November 11, 2022."
    assert off.document_date(text, "https://pib.gov.in/PressRelease?PRID=1") == (None, "")


def test_date_relation():
    assert off.date_relation(None) == "unknown"
    assert off.date_relation(date(2011, 9, 1)) == "before_project"
    assert off.date_relation(date(2021, 5, 25)) == "comparable"
    assert off.date_relation(date(2022, 5, 1)) == "comparable"       # within ~6 months
    assert off.date_relation(date(2022, 11, 11)) == "later"


# ---------- grading ----------

RF = {"value": 166.1, "unit": "sq.km", "normalized": 16610.0, "dimension": "area", "page": 1143}


def official(normalized, d, quote="It covers a total area of 200 sq km.", value=200.0):
    return {"value": value, "unit": "sq km", "normalized": normalized, "dimension": "area",
            "quote": quote, "url": "https://pib.gov.in/x", "title": "PIB", "date": d}


def test_grades():
    assert off.grade(RF, official(16610.0 * 1.04, date(2021, 6, 1)))[0] == "NONE"     # within 5%
    assert off.grade(RF, official(20000.0, date(2021, 6, 1)))[0] == "ORANGE"
    assert off.grade(RF, official(20000.0, date(2023, 6, 1)))[0] == "INFO"            # later revision
    assert off.grade(RF, official(20000.0, None))[0] == "GREY"
    explained = official(20000.0, date(2021, 6, 1), quote="The area was revised to 200 sq km.")
    assert off.grade(RF, explained)[0] == "INFO"


def test_messages_are_neutral_and_dated():
    g = off.grade(RF, official(20000.0, date(2023, 3, 1)))[0]
    m = off.message(RF, official(20000.0, date(2023, 3, 1)), g)
    assert m.startswith("The report states 166.1 sq.km (p.1143); PIB (pib.gov.in, 01 March 2023) states")
    assert "Verify which applies." in m and "changed after the EIA, dated 01 March 2023" in m
    words = m.lower().split()
    assert not any(w.startswith(b) for w in words for b in ("lie", "fraud", "fake", "false", "wrong"))


# ---------- official domains ----------

def test_official_labels():
    assert off.is_official("https://www.pib.gov.in/PressReleasePage.aspx?PRID=1")
    assert off.is_official("https://static.pib.gov.in/doc.pdf")
    assert off.is_official("https://apwd.and.nic.in/x.pdf")
    assert not off.is_official("https://en.wikipedia.org/wiki/X")
    assert off.source_label("https://parivesh.nic.in/x") == "official source"
    assert off.source_label("https://apwd.and.nic.in/x") == "government website"
    assert off.source_label("https://thewire.in/x") == off.OPEN_WEB_LABEL


def test_rank_results_puts_official_first():
    ranked = off.rank_results([{"url": "https://thewire.in/a"}, {"url": "https://apwd.and.nic.in/b"},
                               {"url": "https://pib.gov.in/c"}])
    assert [r["url"] for r in ranked] == ["https://pib.gov.in/c", "https://apwd.and.nic.in/b",
                                          "https://thewire.in/a"]


def test_prefer_official_drops_open_web_when_official_exists():
    a = {"official": False, "label": off.OPEN_WEB_LABEL, "date": None}
    b = {"official": True, "label": "government website", "date": None}
    c = {"official": True, "label": "official source", "date": date(2026, 5, 1)}
    assert off.prefer_official([a, b, c]) == [c, b]
    assert off.prefer_official([a]) == [a]


# ---------- figures in source text ----------

GNI_DOC = ("Great Nicobar Project. The Great Nicobar Island development is a holistic project. "
           "GNI is strategic. ")


def figs(key, text, report_quote=""):
    return [(f["value"], f["unit"]) for f in off.official_figures(key, text, "https://pib.gov.in/x", report_quote)]


def test_forest_diversion_needs_diversion_not_diverse():
    assert figs("forest_diversion", GNI_DOC + "It needs diversion of 130.75 sq. km of forest land.") == [(130.75, "sq. km")]
    assert figs("forest_diversion", GNI_DOC + "The island of 1045.1 km2 is covered by rainforest and diverse wildlife.") == []


def test_component_cost_is_not_the_whole_project_cost():
    text = GNI_DOC + ("Shri Sonowal visited the proposed International Container Transhipment Port. "
                      "With an estimated cost of about ₹44,000 Crores ICTP will play a crucial role.")
    assert figs("project_cost", text) == []
    whole = GNI_DOC + "The total project cost is estimated at Rs. 72,000 crore."
    assert figs("project_cost", whole) == [(72000.0, "crore")]


def test_other_places_and_far_away_mentions_are_skipped():
    assert figs("total_project_area", GNI_DOC + "Little Andaman Island has a total development area of 731.6 km².") == []
    many = ("Agenda of the Standing Committee. " + "Item about a road in Kerala. " * 200
            + "The total development area of the project is 485.3 ha. " + "x " * 500
            + "Great Nicobar is mentioned much later.")
    assert figs("total_project_area", many) == []


def test_trees_felled_and_no_displacement():
    text = GNI_DOC + ("The estimated number of trees in this area is 18.65 lakh, though the maximum number "
                      "expected to be felled is 7.11 lakh within 49.86 sq. km of forest. The Nicobarese and "
                      "Shompen tribes are not displaced.")
    assert (7.11, "lakh trees") in figs("trees_felled", text)
    assert (18.65, "lakh trees") not in figs("trees_felled", text)
    d = off.official_figures("displacement", text, "https://pib.gov.in/x")
    assert d and d[0]["value"] == 0 and "not displaced" in d[0]["quote"]


def test_potable_qualifier_excludes_non_potable():
    text = GNI_DOC + "Water demand: 45 MLD from Non- Potable Water. The water demand of 42 MLD potable water by 2047."
    report_quote = "Potable and non-potable water demand are estimated at 43 and 40 MLD"
    assert figs("water_demand", text, report_quote) == [(42.0, "MLD")]


def test_quote_is_an_exact_substring_and_keeps_abbreviations():
    flat = " ".join((GNI_DOC + "The maximum to be felled is 7.11 lakh within 49.86 sq. km of forest. Next.").split())
    i = flat.index("7.11")
    q = off.quote_for(flat, i, i + 4)
    assert q in flat and q.endswith("sq. km of forest.")


# ---------- report facts ----------

PAGE = "1.1 Development approach The holistic development of GNI requires diversion of 130.75 sq. km of forest land."


def test_report_fact_quotes_are_verified():
    raw = {"facts": [
        {"key": "forest_diversion", "value": 130.75, "unit": "sq. km", "scope": "whole project",
         "quote": "diversion of 130.75 sq. km of forest land"},
        {"key": "forest_diversion", "value": 999, "unit": "sq. km", "quote": "diversion of 130.75 sq. km"},  # number not in quote
        {"key": "trees_felled", "value": 0, "unit": "number", "scope": "not stated", "quote": "0"},
        {"key": "port_capacity", "value": 14.2, "unit": "MTEU", "quote": "a port of 14.2 MTEU at Galathea"},  # not on page
        {"key": "made_up", "value": 1, "unit": "x", "quote": "development"},
    ]}
    got = off.report_facts_from_page(1145, PAGE, raw)
    assert len(got) == 1 and got[0]["normalized"] == 13075.0 and got[0]["quote_check"] == "verbatim on the page"


def test_population_ignores_employment():
    page = "The island is designed for resident population of around 3.3 lakh persons and 17,347 jobs."
    raw = {"facts": [{"key": "township_population", "value": 17347, "unit": "jobs", "quote": "17,347 jobs"},
                     {"key": "township_population", "value": 3.3, "unit": "lakh persons", "scope": "whole project",
                      "quote": "resident population of around 3.3 lakh persons"}]}
    got = off.report_facts_from_page(159, page, raw)
    assert [g["value"] for g in got] == [3.3]


def test_report_facts_respects_the_nebius_cap(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "is_cached", lambda *a, **k: False)
    monkeypatch.setattr(claims_mod, "chat_json", lambda *a, **k: calls.append(1) or {"facts": []})
    pages = {n: "word " * 400 for n in off.REPORT_PAGES}
    off.report_facts(pages, max_usd=0.0)
    assert calls == []                                      # nothing fits a $0 cap
    off.report_facts(pages, max_usd=1.0)
    assert len(calls) == len(off.REPORT_PAGES)


# ---------- end to end, mocked ----------

PIB_TEXT = ("Great Nicobar Project Strategic Importance 1 May , 2026 Key Takeaways. The Great Nicobar Project "
            "includes a 14.2 million TEU International Container Transhipment Terminal. It covers a total area "
            "of 166.10 sq. km, which includes 130.75 sq. km of forest land. GNI is strategic.")
WIRE_TEXT = "Great Nicobar news. The Great Nicobar project cost is estimated at Rs 90,000 crore overall. GNI GNI."


class FakeTavily:
    def __init__(self):
        self.calls = []

    def __call__(self, endpoint, budget, est, **params):
        self.calls.append((endpoint, params))
        budget.check(est)
        budget.add(est)
        if endpoint == "search":
            if params.get("include_domains"):
                return {"results": [{"url": "https://static.pib.gov.in/doc.pdf", "title": "PIB fact sheet"}],
                        "usage": {"credits": 1}}
            return {"results": [{"url": "https://thewire.in/a", "title": "The Wire"}], "usage": {"credits": 1}}
        texts = {"https://static.pib.gov.in/doc.pdf": PIB_TEXT, "https://thewire.in/a": WIRE_TEXT}
        return {"results": [{"url": u, "raw_content": texts[u]} for u in params["urls"]],
                "usage": {"credits": 1}}


@pytest.fixture
def fake_run(monkeypatch):
    replies = {
        1143: {"facts": [{"key": "total_project_area", "value": 166.1, "unit": "sq.km", "scope": "whole project",
                          "quote": "The total project area is 166.1 sq.km."}]},
        24: {"facts": [{"key": "project_cost", "value": 72000, "unit": "Crores", "scope": "whole project",
                        "quote": "An amount of ~Rs. 72,000 Crores is proposed"}]},
    }
    pages = {1143: "Summary. The total project area is 166.1 sq.km. More text here for length " * 3,
             24: "1.6.3 Costs. An amount of ~Rs. 72,000 Crores is proposed to invest on facilities. " * 3}

    def chat(model, messages, max_tokens, thinking=False):
        text = messages[1]["content"]
        return next((r for n, r in replies.items() if " ".join(pages[n].split())[:40] in text), {"facts": []})
    monkeypatch.setattr(claims_mod, "chat_json", chat)
    monkeypatch.setattr(llm, "is_cached", lambda *a, **k: True)
    fake = FakeTavily()
    monkeypatch.setattr(copycheck, "tavily_call", fake)
    return pages, fake


def test_run_end_to_end(fake_run):
    pages, fake = fake_run
    budget = copycheck.Budget(off.MAX_TAVILY_CREDITS)
    result = off.run(pages, budget=budget)
    searches = [p for e, p in fake.calls if e == "search"]
    assert searches[0].get("include_domains") == off.OFFICIAL_DOMAINS     # official first
    area = [r for r in result["comparisons"] if r["fact"] == "total_project_area"]
    assert area and area[0]["grade"] == "NONE" and area[0]["official"]["official"]
    assert area[0]["official"]["quote"] in " ".join(PIB_TEXT.split())
    cost = [r for r in result["comparisons"] if r["fact"] == "project_cost"]
    # no official cost figure -> open web fallback, labelled, undated -> GREY (not shown)
    assert cost and cost[0]["official"]["label"] == off.OPEN_WEB_LABEL and cost[0]["grade"] == "GREY"
    assert any(not p.get("include_domains") for p in searches)
    t = result["tavily"]
    assert t["credits"] == budget.used <= off.MAX_TAVILY_CREDITS
    assert t["searches"] == len(searches) and 0 < t["official_share"] < 1
    assert result["research_endpoint"]["used"] is False


def test_run_stops_at_the_credit_cap(fake_run):
    pages, fake = fake_run
    budget = copycheck.Budget(2)
    off.run(pages, budget=budget)
    assert budget.used <= 2


# ---------- the saved result ----------

@pytest.mark.skipif(not RESULT.exists(), reason="no saved official-record result")
def test_saved_result_is_well_formed_and_neutral():
    r = json.loads(RESULT.read_text(encoding="utf-8"))
    assert r["report_id"] == "great_nicobar_2021_draft"
    assert r["cost"]["nebius_usd"] <= off.MAX_NEBIUS_USD and r["cost"]["tavily_credits"] <= off.MAX_TAVILY_CREDITS
    for c in r["comparisons"]:
        assert c["grade"] in ("ORANGE", "INFO", "NONE", "GREY")
        assert c["report"]["dimension"] == c["official"]["dimension"]
        assert c["official"]["url"].startswith("http") and c["official"]["quote"]
        assert "Verify which applies." in c["message"]
        if c["grade"] in ("ORANGE", "INFO"):
            assert c["official"]["date"]
    pdf_pages = ROOT.parent / "tigerfish" / "cache" / "pages" / "great_nicobar_2021_draft_eia" / "pages.jsonl"
    if pdf_pages.exists():
        pages = {p["page"]: p["text"] for p in map(json.loads, pdf_pages.open(encoding="utf-8"))}
        for f in r["facts"].values():
            assert claims_mod.quote_on_page(f["quote"], pages[f["page"]]), f["key"]


def test_qci_is_labelled_official_but_not_searched():
    assert off.source_label("https://eiameeting.qci.org.in/x.pdf") == "official source"
    assert "qci.org.in" not in off.OFFICIAL_DOMAINS
