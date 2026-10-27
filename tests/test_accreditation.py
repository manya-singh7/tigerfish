"""Accreditation check: extraction parsing, entry/sector parsing, comparison and the
official-domain preference (all offline, Tavily and LIGHTNING mocked)."""

import pytest

from tigerfish import accreditation as ac

PAGES = {
    5: "Prepared by Vimta Labs Ltd, Hyderabad. December 2021",
    18: "The project falls under category ‘A’ of the EIA Notification.",
    44: "Vimta Labs Ltd is accredited by QCI-NABET, Certificate No NABET/EIA/1720/SA 088.",
    60: "Schedule items 7(a), 7(e) and 8(b) of the EIA Notification apply to this project.",
}


# ---------- 1. extraction parsing ----------

def test_parse_details_verifies_quotes_and_finds_other_page():
    raw = {"consultant_name": {"value": "Vimta Labs Ltd", "quote": "Prepared by Vimta Labs Ltd",
                               "page": 44},            # wrong page: found on p.5 instead
           "certificate_number": {"value": "NABET/EIA/1720/SA 088",
                                  "quote": "Certificate No NABET/EIA/1720/SA 088", "page": 44},
           "report_date": {"value": "December 2021", "quote": "December 2021", "page": 5},
           "project_category": {"value": "A", "quote": "falls under category ‘A’", "page": 18}}
    d = ac.parse_details(raw, PAGES)
    assert d["consultant_name"]["page"] == 5 and d["consultant_name"]["verified"]
    assert d["certificate_number"]["verified"] and d["certificate_number"]["page"] == 44
    assert d["project_category"]["value"] == "A"
    assert d["certificate_validity"] is None and d["accredited_sectors"] is None


def test_parse_details_unverified_quote_is_marked():
    raw = {"consultant_name": {"value": "X Ltd", "quote": "Prepared by Someone Else Entirely", "page": 5}}
    d = ac.parse_details(raw, PAGES)
    assert d["consultant_name"]["verified"] is False


def test_parse_details_rejects_fields_the_quote_does_not_support():
    raw = {"accredited_sectors": {"value": ["7(a)", "7(e)"], "page": 60,
                                  "quote": "Schedule items 7(a), 7(e) and 8(b) of the EIA Notification"},
           "accreditation_category": {"value": "QCI-NABET", "page": 44,
                                      "quote": "accredited by QCI-NABET"},
           "certificate_validity": {"value": "2021", "quote": "December 2021", "page": 5}}
    d = ac.parse_details(raw, PAGES)
    assert d["accredited_sectors"] is None          # project schedule items, not accreditation
    assert d["accreditation_category"] is None      # not A or B
    assert d["certificate_validity"] is None        # quote says nothing about validity


@pytest.mark.parametrize("raw", [None, [], "oops", {"consultant_name": None},
                                 {"consultant_name": {"value": "", "quote": "x", "page": 1}}])
def test_parse_details_tolerates_bad_json(raw):
    assert ac.parse_details(raw, PAGES)["consultant_name"] is None


def test_candidate_pages_skip_hindi_and_unrelated():
    pages = [{"page": 1, "text": "NABET accredited consultant"},
             {"page": 2, "text": "NABET प्रमाणपत्र"}, {"page": 3, "text": "Baseline soil data"}]
    assert [p["page"] for p in ac.candidate_pages(pages)] == [1]


# ---------- 2. official entry parsing ----------

SOURCE = ("Scheme for Accreditation of EIA Consultant Organizations Rev. 78, July 10, 2019 "
          "153 Other Labs Private Limited Address: Pune 1 Mining of minerals A 1 (a) (i) "
          "154 Vimta Labs Limited Address: Hyderabad Conditions apply "
          "4 Thermal power plants A 1 (d) "
          "29 Air ports A 7 (a) "
          "33 Ports, harbours, break waters and dredging B 7 (e) "
          "38 Building and construction projects B 8 (a) "
          "39 Townships and Area development projects B 8 (b) "
          "155 Wapcos Limited Address: Delhi 33 Ports, harbours, break waters and dredging A 7 (e)")


def test_find_entry_and_parse_sectors():
    entry = ac.find_entry(SOURCE, "Vimta Labs Ltd")
    assert entry.startswith("154 Vimta Labs") and "Wapcos" not in entry
    rows = ac.parse_sectors(entry)
    assert [(r["number"], r["category"], r["schedule"]) for r in rows] == [
        (4, "A", "1 (d)"), (29, "A", "7 (a)"), (33, "B", "7 (e)"), (38, "B", "8 (a)"), (39, "B", "8 (b)")]
    assert rows[2]["name"] == "Ports, harbours, break waters and dredging"
    assert ac.source_revision(SOURCE) == "Rev. 78, July 10, 2019"


def test_find_entry_missing_consultant():
    assert ac.find_entry(SOURCE, "Nobody Consultants") == ""


@pytest.mark.parametrize("component, key", [
    ("International Container Transshipment Terminal", "port"),
    ("Greenfield International Airport", "airport"),
    ("Township & Area Development", "township"),
    ("450 MVA Gas and Solar based Power Plant", "power plant"),
])
def test_component_key(component, key):
    assert ac.component_key(component) == key


def test_matching_sector_port_vs_airport_and_township_priority():
    sectors = ac.parse_sectors(ac.find_entry(SOURCE, "Vimta Labs"))
    assert ac.matching_sector("port", sectors)["number"] == 33          # not "Air ports"
    assert ac.matching_sector("airport", sectors)["number"] == 29
    assert ac.matching_sector("township", sectors)["number"] == 39      # before "Building and..."
    assert ac.matching_sector("industrial estate", sectors) is None


def test_queries_expand_company_form_and_trim_certificate():
    q = ac.queries("Vimta Labs Ltd", "NABET/EIA/1720/SA 088")
    assert q == ["Vimta Labs Limited NABET/EIA/1720 accreditation validity sectors",
                 "List of Accredited EIA Consultant Organizations Vimta Labs Limited"]
    assert ac.queries("ABC Pvt. Ltd.") == ["List of Accredited EIA Consultant Organizations ABC Private Limited"]


# ---------- 3. comparison ----------

def details(sectors, category="A", report="December 2021"):
    f = lambda v: {"value": v, "quote": "q", "page": 1, "verified": True}
    return {"project_sectors": f(sectors), "project_category": f(category), "report_date": f(report)}


def entry(validity=None, revision="AC meeting, October 26, 2021", label="official source"):
    return {"sectors": ac.parse_sectors(ac.find_entry(SOURCE, "Vimta Labs")), "validity": validity,
            "revision": revision, "url": "https://nabet.qci.org.in/x.pdf", "label": label}


def test_compare_category_b_does_not_cover_category_a_project():
    out = ac.compare(details(["ICTT port", "Airport"]), entry("31.12.2023"))
    assert out["grade"] == "ORANGE"
    assert [r["covered"] for r in out["rows"]] == [False, True]
    assert out["messages"] == ["Accreditation could not be confirmed for ICTT port (port) at the report date. Verify."]


def test_compare_covered_and_valid_is_none():
    out = ac.compare(details(["Airport", "Power Plant"]), entry("31.12.2023"))
    assert out["grade"] == "NONE" and not out["messages"]
    assert out["validity"] == "valid until 2023-12-31"


def test_compare_category_b_project_is_covered_by_b():
    assert ac.compare(details(["Harbour"], category="B"), entry("31.12.2023"))["grade"] == "NONE"


def test_compare_expired_before_report_date():
    out = ac.compare(details(["Airport"]), entry("10.07.2020"))
    assert out["grade"] == "ORANGE" and out["validity"].startswith("expired on 2020-07-10")


def test_compare_sector_not_listed():
    out = ac.compare(details(["Industrial Estate"]), entry("31.12.2023"))
    assert out["grade"] == "ORANGE" and out["rows"][0]["why"] == "no accredited sector matches"


def test_compare_no_entry_is_grey():
    out = ac.compare(details(["Airport"]), None)
    assert out["grade"] == "GREY" and out["validity"] and not out["messages"]


def test_compare_covered_but_validity_unknown_is_grey():
    out = ac.compare(details(["Airport"]), entry(None))
    assert out["grade"] == "GREY"
    assert "predates the report date (December 2021)" in out["validity"]


def test_gap_in_record_older_than_12_months_is_info():
    out = ac.compare(details(["ICTT port", "Airport"]), entry(None, revision="Rev. 78, July 10, 2019"))
    assert out["grade"] == "INFO" and out["recent"] is False
    assert out["messages"] == ["Latest official list found (Rev. 78, July 10, 2019) shows Category B for "
                               "ICTT port (port); status at the report date could not be confirmed."]


def test_gap_in_non_official_record_is_info():
    out = ac.compare(details(["ICTT port"]), entry(None, label=ac.NON_OFFICIAL))
    assert out["grade"] == "INFO" and ac.NON_OFFICIAL in out["messages"][0]


def test_gap_within_12_months_is_orange():
    out = ac.compare(details(["ICTT port"]), {**entry(None, revision="Rev. 80"),
                                               "date": ac.to_date("January 15, 2021")})
    assert out["grade"] == "ORANGE" and out["recent"]


# ---------- dated records (Accreditation Committee minutes) ----------

MINUTES = ("Supplementary Assessment: 61st AC Meeting held Through Video Conferencing on October 26, 2021 "
           "1.4 Vimta Labs Ltd., Hyderabad The case of Vimta Labs Ltd. was discussed in RA AC meeting "
           "minutes dated June 15, 2021 wherein ACO was accredited for sectors 4(A), 29(A), 33(B) and 39(B). "
           "1.5 Other Labs ... accredited for sectors 33(A)")
RA_MINUTES = ("Accreditation Committee Meeting for Re-Accreditation held on June 15, 2021 1.1 Vimta Labs Ltd., "
              "Hyderabad 1.1.2 Scope of Accreditation: S. No NABET Scheme Sectors 1. 4 Thermal power plants A 1 (d) "
              "1.1.3 Sectors approved for EIA Coordinators 1 Chandra Sekhar 4 A Renewed A "
              "2. 33 Ports, harbours, break waters and dredging B 7 (e) 3. 28 Isolated storage B - "
              "1.1.4 Functional Areas (FA) approved 1. 39 Fake row A 8 (b)")
LISTING = """## EIA Accreditation Committee Meetings : Supplementary Assessment (Year 2021)
* [064 / 2021 : 17-12-2021](meetings/MoM Supple-dt_Dec 17_ 2021.pdf)   ![](x.png)
  1. In Situ Enviro Care, Bhopal
* [061 / 2021 : 26-10-2021](meetings/MOM-Supple(Website upload)- dt Oct 26, 2021_15.11.2021.pdf)   ![](x.png)
  1. Shree Green Consultants, Surat
  3. Udaipur Mintech, Udaipur Vimta Labs Ltd., Hyderabad
* [043 / 2021 : 15-01-2021](meetings/MOM Supple- dt Jan 15, 2021.pdf)   ![](x.png)
  1. Vimta Labs Ltd., Hyderabad"""


def test_record_sectors_compact_names_from_list():
    rows = ac.record_sectors(MINUTES, "Vimta Labs Ltd", names={33: "Ports, harbours", 4: "Thermal power plants"})
    assert [(r["number"], r["category"], r["name"]) for r in rows] == [
        (4, "A", "Thermal power plants"), (29, "A", "sector 29"), (33, "B", "Ports, harbours"), (39, "B", "sector 39")]


def test_record_sectors_scope_table_skips_other_tables():
    rows = ac.record_sectors(RA_MINUTES, "Vimta Labs Ltd")
    assert [(r["number"], r["category"], r["schedule"]) for r in rows] == [(4, "A", "1 (d)"), (28, "B", "-"),
                                                                           (33, "B", "7 (e)")]


def test_meeting_links_name_the_consultant():
    links = ac.meeting_links(LISTING, "https://eiameeting.qci.org.in/Environment/meeting_list.asp?year=2021", "Vimta Labs Ltd")
    assert [(d.isoformat(), t) for d, t, _ in links] == [("2021-10-26", "AC meeting 061/2021"),
                                                          ("2021-01-15", "AC meeting 043/2021")]
    assert links[0][2] == ("https://eiameeting.qci.org.in/Environment/meetings/"
                           "MOM-Supple%28Website%20upload%29-%20dt%20Oct%2026%2C%202021_15.11.2021.pdf")


def test_closest_record_to_report_date():
    recs = [{"date": ac.to_date("July 10, 2019")}, {"date": ac.to_date("June 15, 2021")},
            {"date": ac.to_date("October 26, 2021")}, {"date": ac.to_date("March 1, 2022")}]
    assert ac.closest_record(recs, ac.to_date("December 2021"))["date"].isoformat() == "2021-10-26"
    assert ac.closest_record([{"date": None, "x": 1}], ac.to_date("December 2021")) == {"date": None, "x": 1}


def test_dated_records_follow_the_closest_listed_meeting(monkeypatch):
    listing = "https://eiameeting.qci.org.in/Environment/meeting_list.asp?year=2021&id=7"
    ra = "https://eiameeting.qci.org.in/Environment/meetings/RA.pdf"
    oct26 = ac.meeting_links(LISTING, listing, "Vimta")[0][2]
    calls = []

    def search(query, budget, exact=False, include_domains=None):
        calls.append(include_domains)
        return {"results": [{"url": listing}, {"url": ra}]}

    def extract(urls, budget, max_chars=None):
        pages = {listing: LISTING, ra: RA_MINUTES, oct26: MINUTES}
        return {u: pages[u] for u in urls if u in pages}

    monkeypatch.setattr(ac.copycheck, "search", search)
    monkeypatch.setattr(ac.copycheck, "extract", extract)
    recs = ac.dated_records("Vimta Labs Ltd", ac.to_date("December 2021"), budget=None)
    assert calls == [ac.OFFICIAL_DOMAINS]
    assert [(r["date"].isoformat(), r["url"]) for r in recs] == [("2021-06-15", ra), ("2021-10-26", oct26)]
    assert ac.closest_record(recs, ac.to_date("December 2021"))["url"] == oct26


def test_to_date():
    from datetime import date
    assert ac.to_date("10.07.2019") == date(2019, 7, 10)
    assert ac.to_date("Rev. 78, July 10, 2019") == date(2019, 7, 10)
    assert ac.to_date("December 2021") == date(2021, 12, 1)
    assert ac.to_date("soon") is None


# ---------- official-domain preference ----------

class FakeTavily:
    """include_domains_mode="prefer": official results first, then the open web."""

    def __init__(self, official, web):
        self.official, self.web, self.calls, self.depths = official, web, [], []

    def search(self, query, budget, exact=False, include_domains=None, include_domains_mode=None):
        self.calls.append((include_domains, include_domains_mode))
        if include_domains_mode == "prefer":
            pool = self.official + self.web
        else:
            pool = self.official if include_domains else self.web
        return {"results": [{"url": u} for u in pool]}

    def extract(self, urls, budget, max_chars=None, depth="basic"):
        self.depths.append(depth)
        pages = {"https://nabet.qci.org.in/list.pdf": SOURCE, "https://blog.example/list": SOURCE,
                 "https://nabet.qci.org.in/scheme.pdf": "Scheme documents only"}
        return {u: pages.get(u, "") for u in urls}


def use(monkeypatch, fake, legacy=False):
    monkeypatch.setattr(ac.copycheck, "search", fake.search)
    monkeypatch.setattr(ac.copycheck, "extract", fake.extract)
    monkeypatch.setattr(ac, "legacy_cached", lambda *a, **k: legacy)


def test_official_domain_is_preferred_in_one_search(monkeypatch):
    fake = FakeTavily(official=["https://nabet.qci.org.in/scheme.pdf", "https://nabet.qci.org.in/list.pdf"],
                      web=["https://blog.example/list"])
    use(monkeypatch, fake)
    e = ac.official_entry("Vimta Labs Ltd", budget=None, certificate="NABET/EIA/1720/SA 088")
    assert e["label"] == "official source" and e["url"] == "https://nabet.qci.org.in/list.pdf"
    assert fake.calls == [(ac.OFFICIAL_DOMAINS, "prefer")]     # one search, no open-web step
    assert fake.depths == ["advanced"]                          # official PDF tables


def test_open_web_result_is_labelled_non_official(monkeypatch):
    fake = FakeTavily(official=["https://nabet.qci.org.in/scheme.pdf"], web=["https://blog.example/list"])
    use(monkeypatch, fake)
    e = ac.official_entry("Vimta Labs Ltd", budget=None, certificate="NABET/EIA/1720/SA 088")
    assert e["label"] == ac.NON_OFFICIAL and e["url"] == "https://blog.example/list"
    assert all(mode == "prefer" for _, mode in fake.calls)


def test_cached_two_step_run_is_replayed_the_old_way(monkeypatch):
    fake = FakeTavily(official=["https://nabet.qci.org.in/scheme.pdf"], web=["https://blog.example/list"])
    use(monkeypatch, fake, legacy=True)
    e = ac.official_entry("Vimta Labs Ltd", budget=None, certificate="NABET/EIA/1720/SA 088")
    assert e["label"] == ac.NON_OFFICIAL
    assert fake.calls[:2] == [(ac.OFFICIAL_DOMAINS, None)] * 2 and fake.calls[2] == (None, None)
    assert set(fake.depths) == {"basic"}


def test_nothing_found_anywhere(monkeypatch):
    use(monkeypatch, FakeTavily(official=[], web=[]))
    assert ac.official_entry("Vimta Labs Ltd", budget=None) is None


def test_check_end_to_end_mocked(monkeypatch):
    raw = {"consultant_name": {"value": "Vimta Labs Ltd", "quote": "Vimta Labs Ltd is accredited", "page": 44},
           "project_sectors": {"value": ["port", "airport"], "quote": "December 2021", "page": 5},
           "project_category": {"value": "A", "quote": "falls under category ‘A’", "page": 18},
           "report_date": {"value": "December 2021", "quote": "December 2021", "page": 5}}
    monkeypatch.setattr(ac.claims_mod, "chat_json", lambda *a, **k: raw)
    use(monkeypatch, FakeTavily(official=["https://nabet.qci.org.in/list.pdf"], web=[]))
    pages = [{"page": p, "text": t + " NABET"} for p, t in PAGES.items()]
    out = ac.check(pages, max_credits=0)
    # only the 2019 list is found: a gap more than 12 months before the report is INFO
    assert out["grade"] == "INFO" and out["entry"]["label"] == "official source"
    assert [r["covered"] for r in out["rows"]] == [False, True]
    assert out["messages"][0].startswith("Latest official list found (Rev. 78, July 10, 2019) shows Category B")


def test_credit_cap_gives_grey(monkeypatch):
    monkeypatch.setattr(ac.claims_mod, "chat_json", lambda *a, **k: {
        "consultant_name": {"value": "Vimta Labs Ltd", "quote": "Vimta Labs Ltd is accredited", "page": 44}})

    def capped(*a, **k):
        raise ac.copycheck.CreditCapReached("cap")
    monkeypatch.setattr(ac.copycheck, "search", capped)
    pages = [{"page": p, "text": t + " NABET"} for p, t in PAGES.items()]
    assert ac.check(pages, max_credits=0)["grade"] == "GREY"
