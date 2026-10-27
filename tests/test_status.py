"""Status check (IUCN + WPA schedules) with GBIF and Tavily mocked."""

import pytest

from tigerfish import copycheck, status

TABLE = {
    "title": "Table 3.16", "scientific_name_column": "Zoological name",
    "columns": ["Zoological name", "Common name", "IUCN Category", "WPA Schedule, 1972"],
    "rows": [
        {"Zoological name": "Macaca fascicularis", "Common name": "Crab eating Macaque",
         "IUCN Category": "VU", "WPA Schedule, 1972": "Sch-II"},
        {"Zoological name": "Rattus rattus", "Common name": "House rat",
         "IUCN Category": "LC", "WPA Schedule, 1972": "Sch-V"},
        {"Zoological name": "Paguma larvata", "Common name": "Civet",
         "IUCN Category": "LC", "WPA Schedule, 1972": "-"},
    ],
}
SOURCE = ("The Wild Life (Protection) Amendment Act, 2022 was passed in December. "
          "The amendment reduces the number of schedules from six to four by removing the "
          "schedule for vermin species. It also adds a schedule for CITES specimens.")


# ---------- IUCN ----------

@pytest.mark.parametrize("value, code", [("VU", "VU"), (" lc ", "LC"), ("Endangered", "EN"),
                                         ("Least Concern", "LC"), ("-", None), ("", None)])
def test_iucn_code(value, code):
    assert status.iucn_code(value) == code


CURRENT_EN = {"code": "EN", "category": "ENDANGERED", "gbif_key": 2436603,
              "accepted": "Macaca fascicularis", "name_note": None,
              "url": "https://www.gbif.org/species/2436603", "iucn_url": "https://iucn"}


def test_iucn_differs_is_orange_with_evidence():
    r = status.check_iucn("Macaca fascicularis", "VU", CURRENT_EN)
    assert r["grade"] == "ORANGE" and r["message"] == "IUCN status may be outdated. Verify."
    assert "Report says VU" in r["evidence"] and "says EN" in r["evidence"]
    assert "https://www.gbif.org/species/2436603" in r["evidence"]


def test_iucn_same_is_none_and_missing_is_grey():
    assert status.check_iucn("Macaca fascicularis", "EN", CURRENT_EN)["grade"] == "NONE"
    assert status.check_iucn("Macaca fascicularis", "VU", None)["grade"] == "GREY"
    assert status.check_iucn("Macaca fascicularis", "-", CURRENT_EN)["grade"] == "GREY"


def test_iucn_current_uses_name_resolution(monkeypatch):
    monkeypatch.setattr(status.species, "resolve_name",
                        lambda n: ({}, 7261386, "Rusa unicolor", '"Cervus unicolor" is a synonym'))
    calls = []

    def gbif_get(path, **params):
        calls.append(path)
        return {"code": "VU", "category": "VULNERABLE"}

    monkeypatch.setattr(status.species, "gbif_get", gbif_get)
    cur = status.iucn_current("Cervus unicolor")
    assert calls == ["/species/7261386/iucnRedListCategory"]
    assert cur["code"] == "VU" and cur["accepted"] == "Rusa unicolor" and "synonym" in cur["name_note"]


def test_iucn_current_none_when_gbif_has_no_category(monkeypatch):
    monkeypatch.setattr(status.species, "resolve_name", lambda n: ({}, 1, "X y", None))
    monkeypatch.setattr(status.species, "gbif_get", lambda path, **p: {})
    assert status.iucn_current("X y") is None


# ---------- WPA schedules ----------

@pytest.mark.parametrize("value, n", [("Sch-II", 2), ("Sch-III", 3), ("Sch-V", 5),
                                      ("Schedule IV", 4), ("Sch. I", 1), ("6", 6),
                                      ("-", None), ("", None)])
def test_schedule_number(value, n):
    assert status.schedule_number(value) == n


@pytest.mark.parametrize("text, count", [
    (SOURCE, 4),
    ("Schedules were rationalised from 6 to 4.", 4),
    ("It cut the six schedules to four schedules.", 4),
    ("The Act now has four schedules.", 4),
    # wordings from the official sources (PRS bill track, Bill text)
    ("The Bill reduces the total number of schedules to four by: (i) reducing the number.", 4),
    ("this clause seeks to reduce the number of Schedules from present six to four as follows.", 4),
    # sub-count first ("for protected animal species from four to two"), total later
    ("With the deletion of the Schedule for vermin, and the reduction in the number of Schedules "
     "for protected animal species from four to two, along with the addition of a Schedule for "
     "species listed on the Appendices, this clause seeks to reduce the number of Schedules from "
     "present six to four as follows.", 4),
    ("Schedules for protected animal species reduced from four to two.", None),
    ("Schedule I covers the most protected species.", None),     # no count stated
])
def test_schedule_count_from_text(text, count):
    found = status.schedule_count_from_text(text)
    assert (found[0][0] if found else None) == count
    if found:
        assert found[0][1] in status.claims_mod.normalize(text)     # quote is exact source text


class FakeTavily:
    def __init__(self, text):
        self.text, self.calls = text, []

    def search(self, **kw):
        self.calls.append("search")
        return {"results": [{"url": "https://law.example/wpa-2022", "content": "summary"}],
                "usage": {"credits": 1}}

    def extract(self, **kw):
        self.calls.append("extract")
        return {"results": [{"url": u, "raw_content": self.text} for u in kw["urls"]],
                "usage": {"credits": 1}}


@pytest.fixture
def tavily(monkeypatch, tmp_path):
    def install(text=SOURCE):
        fake = FakeTavily(text)
        monkeypatch.setattr(copycheck, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(copycheck, "client", lambda: fake)
        return fake
    return install


def test_current_schedules_quotes_retrieved_source(tavily):
    tavily()
    budget = copycheck.Budget(10)
    cur = status.current_schedules(budget)
    assert cur["count"] == 4 and cur["url"] == "https://law.example/wpa-2022"
    assert cur["quote"].startswith("The amendment reduces the number of schedules from six to four")
    assert budget.used == 2                       # 1 search + 1 extract, counted in the cap


def test_schedule_flags_only_numbers_that_no_longer_exist():
    cur = {"count": 4, "quote": "reduces the number of schedules from six to four",
           "url": "https://law.example/wpa-2022"}
    v = status.check_schedule("Rattus rattus", "Sch-V", cur)
    assert v["grade"] == "ORANGE"
    assert 'https://law.example/wpa-2022 says: "reduces the number of schedules' in v["evidence"]
    assert status.check_schedule("Macaca fascicularis", "Sch-II", cur)["grade"] == "NONE"
    assert status.check_schedule("Paguma larvata", "-", cur)["grade"] == "GREY"


def test_count_comes_from_source_not_hardcoded(tavily):
    """If the source said six to five, Sch-V would be fine and Sch-VI flagged."""
    tavily("The amendment reduced schedules from six to five.")
    cur = status.current_schedules(copycheck.Budget(10))
    assert cur["count"] == 5
    assert status.check_schedule("x", "Sch-V", cur)["grade"] == "NONE"
    assert status.check_schedule("x", "Sch-VI", cur)["grade"] == "ORANGE"


def test_no_count_in_sources_is_grey(tavily):
    tavily("The Act protects wildlife. Schedule I covers tigers.")
    cur = status.current_schedules(copycheck.Budget(10))
    assert cur is None
    assert status.check_schedule("x", "Sch-V", cur)["grade"] == "GREY"


def test_check_table_end_to_end(tavily, monkeypatch):
    tavily()
    monkeypatch.setattr(status, "iucn_current",
                        lambda n: CURRENT_EN if n == "Macaca fascicularis" else
                        {**CURRENT_EN, "code": "LC", "category": "LEAST CONCERN", "accepted": n})
    out = status.check_table(TABLE, copycheck.Budget(10))
    grades = {(r["name"], r["check"]): r["grade"] for r in out["results"]}
    assert grades[("Macaca fascicularis", "iucn")] == "ORANGE"
    assert grades[("Rattus rattus", "iucn")] == "NONE"
    assert grades[("Rattus rattus", "wpa_schedule")] == "ORANGE"
    assert grades[("Macaca fascicularis", "wpa_schedule")] == "NONE"
    assert grades[("Paguma larvata", "wpa_schedule")] == "GREY"
    assert out["columns"] == ("Zoological name", "IUCN Category", "WPA Schedule, 1972")


def test_credit_cap_stops_schedule_lookup(tavily, monkeypatch):
    tavily()
    monkeypatch.setattr(status, "iucn_current", lambda n: None)     # no GBIF calls
    out = status.check_table(TABLE, copycheck.Budget(0))
    assert "credit cap" in out["stopped"] and out["wpa_source"] is None


def test_iucn_difference_after_name_correction_is_grey():
    cur = {**CURRENT_EN, "accepted": "Pteropus vampyrus",
           "name_note": '"Pteropus giganteus" is a synonym; GBIF accepted name is Pteropus vampyrus'}
    r = status.check_iucn("Pteropus giganteus", "LC", cur)
    assert r["grade"] == "GREY" and "different taxa" in r["evidence"]


def test_markdown_removed_from_quotes():
    found = status.schedule_count_from_text("## Changes\n**2) Schedules** The Bill reduces "
                                            "the number of schedules from six to four.")
    assert found and "#" not in found[0][1] and "*" not in found[0][1]


def test_quote_prefers_official_source():
    assert status.quote_rank("cut from six to four", "https://prsindia.org/bill") >         status.quote_rank("The 2022 amendment cut schedules from six to four", "https://blog.example")
    assert status.quote_rank("cut from six to four", "https://indiacode.nic.in/act") >         status.quote_rank("The 2022 amendment cut schedules from six to four", "https://prsindia.org/b")


def test_prs_is_authoritative_not_government():
    assert status.wpa_label("https://prsindia.org/billtrack/x") == "authoritative, non-government"
    assert status.wpa_label("https://indiacode.nic.in/handle/x") == "official source"
    assert status.wpa_label("https://egazette.gov.in/WriteReadData/2022/x.pdf") == "official source"
    assert status.wpa_label("https://blog.example/x") == "non-official source"


class TieredTavily:
    """India Code / Gazette return `primary_text`, official sites + PRS return `official_text`,
    the open web returns SOURCE."""

    def __init__(self, primary_text, official_text):
        self.primary_text, self.official_text, self.searches = primary_text, official_text, []

    def search(self, **kw):
        domains = kw.get("include_domains")
        self.searches.append(domains)
        url = ("https://egazette.gov.in/wpa.pdf" if domains == status.PRIMARY_SEARCH_DOMAINS else
               "https://prsindia.org/wpa" if domains else "https://blog.example/wpa")
        return {"results": [{"url": url, "content": ""}], "usage": {"credits": 1}}

    def extract(self, **kw):
        url = kw["urls"][0]
        text = (self.primary_text if "egazette" in url else
                self.official_text if "prsindia" in url else SOURCE)
        return {"results": [{"url": u, "raw_content": text} for u in kw["urls"]]}


@pytest.fixture
def tiered(monkeypatch, tmp_path):
    def install(primary_text, official_text=""):
        fake = TieredTavily(primary_text, official_text)
        monkeypatch.setattr(copycheck, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(copycheck, "client", lambda: fake)
        return fake
    return install


NOTHING = "Nothing about how many schedules there are."


def test_india_code_and_gazette_searched_first(tiered):
    fake = tiered("The Act reduces the number of schedules from six to four.")
    cur = status.current_schedules(copycheck.Budget(10))
    assert fake.searches == [status.PRIMARY_SEARCH_DOMAINS]          # nothing else needed
    assert cur["official"] and cur["label"] == "official source"
    assert cur["url"] == "https://egazette.gov.in/wpa.pdf"
    v = status.check_schedule("Rattus rattus", "Sch-V", cur)
    assert v["grade"] == "ORANGE"
    assert "non-official" not in v["evidence"] and "authoritative" not in v["evidence"]


def test_prs_fallback_is_labelled_authoritative_non_government(tiered):
    fake = tiered(NOTHING, "The Bill reduces the number of schedules from six to four.")
    cur = status.current_schedules(copycheck.Budget(10))
    assert fake.searches == [status.PRIMARY_SEARCH_DOMAINS, status.OFFICIAL_SEARCH_DOMAINS]
    assert not cur["official"] and cur["label"] == "authoritative, non-government"
    assert [t["found"] for t in cur["tiers"]] == [False, True]
    v = status.check_schedule("Rattus rattus", "Sch-V", cur)
    assert "(authoritative, non-government)" in v["evidence"] and "official source" not in v["evidence"]
    assert v["source_label"] == "authoritative, non-government"
    assert v["source_tiers"][0] == {"tier": "India Code / Gazette",
                                    "domains": status.PRIMARY_SEARCH_DOMAINS, "found": False}


def test_open_web_fallback_is_labelled(tiered):
    fake = tiered(NOTHING, NOTHING)
    cur = status.current_schedules(copycheck.Budget(10))
    assert fake.searches == [status.PRIMARY_SEARCH_DOMAINS, status.OFFICIAL_SEARCH_DOMAINS, None]
    assert not cur["official"] and cur["label"] == "non-official source"
    v = status.check_schedule("Rattus rattus", "Sch-V", cur)
    assert "(non-official source)" in v["evidence"] and v["grade"] == "ORANGE"


def test_not_evaluated_is_grey_not_outdated():
    cur = {"code": "NE", "category": "NOT_EVALUATED", "gbif_key": 1, "accepted": "Sida acuta",
           "name_note": None, "url": "https://www.gbif.org/species/1",
           "iucn_url": "https://www.iucnredlist.org/search?query=Sida%20acuta"}
    r = status.check_iucn("Sida acuta", "LC", cur)
    assert r["grade"] == "GREY" and "not evaluated" in r["evidence"]
