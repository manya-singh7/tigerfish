"""Paper trail, authority contacts, granted-ToR pages and Tavily context efficiency (no API calls)."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tigerfish import authority, copycheck, paper_trail as pt, tavily_usage
from tigerfish.ui import data, efficiency, letter, rti
from tigerfish.ui import paper_trail as trail_ui

ROOT = Path(__file__).resolve().parent.parent
GN, IP = "great_nicobar_2021_draft", "indira_point_table_3_16"
GN_PAGES = {45: "As the Minutes ... the recommended TOR for the proposal no: IA/AN/NCP/201159/2021 given in Annexure-I.",
            44: "The EIA report is prepared based on the TOR conditions issued by MoEF&CC vide "
                "F.No.10/17/2021-IA.III dated 25th May 2021. Baseline",
            49: "ANIIDCO propose Holistic Development of Great Nicobar Island in Andaman and Nicobar Islands. More."}
IP_REPORT = {"title": "Indira Point REIA, Table 3.16 (as published by Scroll.in)",
             "source": "Table 3.16 of the WAPCOS Indira Point REIA (Apr 2026), as published by Scroll.in"}


# ---------- identity: only from the report's own text ----------

def test_identity_reads_facts_from_the_report_pages():
    i = pt.identity(GN, pages=GN_PAGES)
    assert i["proposals"] == ["IA/AN/NCP/201159/2021"] and i["state"] == "Andaman and Nicobar Islands"
    assert not i["unchecked"]


def test_identity_drops_facts_not_on_their_page():
    pages = {**GN_PAGES, 45: "no proposal number on this page"}
    i = pt.identity(GN, pages=pages)
    assert i["proposals"] == [] and any(f["fact"] == "proposal" for f in i["unchecked"])


def test_nothing_carries_over_between_reports():
    i = pt.identity(IP, IP_REPORT)
    assert i["proposals"] == [] and i["state"] is None
    assert pt.sites_for(i) == pt.CENTRAL_SITES                       # no state board guessed
    assert "IA/AN/NCP/201159/2021" not in json.dumps(i)


def test_cuddalore_profile_is_tamil_nadu():
    p = pt.PROFILES["cuddalore_port_2026_draft"]
    assert pt.STATE_SITES["Tamil Nadu"] == ["tnpcb.gov.in"]
    assert any(f["fact"] == "state" and f["value"] == "Tamil Nadu" for f in p["facts"])


# ---------- reading documents ----------

GN_ID = {"proposals": ["IA/AN/NCP/201159/2021"], "name_groups": pt.PROFILES[GN]["name_groups"]}


def test_names_project_by_proposal_or_both_name_groups():
    how, q = pt.names_project("File No. 10/17. Proposal No. IA/AN/NCP/201159/2021 Page 1 of 18.", GN_ID)
    assert how == "proposal number" and "IA/AN/NCP/201159/2021" in q
    how, q = pt.names_project("The ICTT at Great Nicobar is planned. Other text.", GN_ID)
    assert how == "project name" and "Great Nicobar" in q
    assert pt.names_project("Great Nicobar is an island. The ICTT is elsewhere.", GN_ID) == (None, None)
    assert pt.names_project("A port in Gujarat.", GN_ID) == (None, None)


def test_stated_date_only_after_a_date_label():
    assert pt.stated_date("Government of India Dated: 25 th May, 2021 To The General Manager")[0] == "2021-05-25"
    assert pt.stated_date("submitted under Notification No. S.O.804(E) dated 14.03.2017 ?No")[0] is None
    assert pt.stated_date("No date at all here.") == (None, None)
    assert pt.stated_date("meeting held on 5th - 6th April, 2021 via VC")[0] == "2021-04-05"


@pytest.mark.parametrize("url,title,text,kind", [
    ("https://environmentclearance.nic.in/x", "", "Subject: ICTT - Terms of Reference. Dated: 25 May 2021", "ToR letter"),
    ("https://environmentclearance.nic.in/auth/ECReport_New.aspx", "Report Part 1",
     "Form-2 APPLICATION FOR PRIOR ENVIRONMENTAL CLEARANCE ... minutes of EAC", "Application (Form 1 / Form 2)"),
    ("https://dstpcc.andamannicobar.gov.in/145-COMPILATION OF THE PROCEEDING OF PUBLIC HEARING.pdf", "", "text",
     "Public hearing proceedings"),
    ("https://parivesh.nic.in/m.pdf", "", "Minutes of the 260th meeting of the Expert Appraisal Committee", "EAC/SEAC minutes"),
    ("https://pib.gov.in/p", "", "text", "Press release"),
    ("https://sansad.in/q", "", "Lok Sabha unstarred question", "Parliament reply"),
])
def test_doc_type(url, title, text, kind):
    assert pt.doc_type(url, title, text) == kind


def test_classify_keeps_only_official_documents_that_name_the_project():
    found = {pt.canonical(u): {"url": u, "via": v, "detail": "", "title": ""} for u, v in [
        ("https://environmentclearance.nic.in/tor.pdf", "search"),
        ("https://example.com/news", "search"),
        ("https://dstpcc.andamannicobar.gov.in/other.pdf", "map"),
        ("https://moef.gov.in/js", "crawl")]}
    raw = {pt.canonical("https://environmentclearance.nic.in/tor.pdf"):
           "Subject: Terms of Reference. Dated: 25th May, 2021. Proposal No. IA/AN/NCP/201159/2021. "
           "The prescribed TOR would be valid for a period of four years.",
           pt.canonical("https://example.com/news"): "Proposal No. IA/AN/NCP/201159/2021 in the news.",
           pt.canonical("https://dstpcc.andamannicobar.gov.in/other.pdf"): "Public hearing notice for a hotel at Port Blair."}
    docs, dropped = pt.classify(found, raw, GN_ID)
    assert [d["url"] for d in docs] == ["https://environmentclearance.nic.in/tor.pdf"]
    d = docs[0]
    assert d["type"] == "ToR letter" and d["date"] == "2021-05-25" and d["granted_tor"]
    assert d["quote"] in pt.plain(raw[pt.canonical(d["url"])])          # quote checked on the page
    assert pt.count_by(dropped, "why") == {"not an official site": 1,
                                           "does not name the project or its proposal number": 1,
                                           "no readable text (JavaScript-only page or scan)": 1}


def test_split_pages_drops_headers_and_splits_conditions():
    text = ("Proposal No. IA/AN/NCP/201159/2021 Page 1 of 2 intro. xxxvi) health checks every two to "
            "three years. Proposal No. IA/AN/NCP/201159/2021 Page 2 of 2 xxxvii) One complete season of AAQ data.")
    pages = pt.split_pages(text)
    assert [p["page"] for p in pages] == [1, 2]
    assert all("Page" not in p["text"] and "Proposal No" not in p["text"] for p in pages)
    from tigerfish import promises
    sents = [s for p in pages for s in promises.sentences(p["text"])]
    season = next(s for s in sents if "season" in s)
    assert "years" not in season                                       # one condition per item


# ---------- Tavily calls: map / crawl, errors ----------

def test_tavily_call_dispatches_map_and_counts_usage(monkeypatch, tmp_path):
    monkeypatch.setattr(copycheck, "CACHE_DIR", tmp_path)

    class Fake:
        def map(self, **k):
            return {"results": ["https://a.gov.in/x.pdf"], "usage": {"credits": 2}}
    monkeypatch.setattr(copycheck, "client", lambda: Fake())
    tavily_usage.reset()
    b = copycheck.Budget(5)
    d = copycheck.tavily_call("map", b, 4, url="https://a.gov.in", instructions="docs")
    assert d["results"] and b.used == 2
    assert tavily_usage.snapshot()["features"]["map"]["returned"] == len("https://a.gov.in/x.pdf")
    copycheck.tavily_call("map", b, 4, url="https://a.gov.in", instructions="docs")   # cached: free
    assert b.used == 2 and b.cached == 1


def test_failed_crawl_is_logged_not_fatal(monkeypatch):
    calls = []

    def boom(endpoint, budget, est, **params):
        calls.append(endpoint)
        raise ConnectionError("reset")
    monkeypatch.setattr(copycheck, "tavily_call", boom)
    r = pt.Run(pt.identity(IP, IP_REPORT), copycheck.Budget(10))
    r.crawl_site("moef.gov.in")
    assert calls == ["crawl", "crawl"] and r.steps[-1]["results"] == 0 and r.steps[-1]["error"]


def test_credit_cap_stops_before_a_call(monkeypatch, tmp_path):
    monkeypatch.setattr(copycheck, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(copycheck, "client", lambda: pytest.fail("no call may be sent"))
    with pytest.raises(copycheck.CreditCapReached):
        copycheck.tavily_call("map", copycheck.Budget(3), 4, url="https://x.gov.in")


# ---------- authority contacts ----------

DIRECTORY = ("| 1 | Shri A, IAS | Secretary cum Chairman ANPCC | Dept of S&T, Dollygunj, Sri Vijay Puram. | "
             "x@and.nic.in |\n| 2 | Shri B, DANICS | Director cum Member Secretary ANPCC | Department of Science "
             "and Technology, Andaman and Nicobar Administration, Dollygunj, Sri Vijay Puram. | dstpcc-andamans@and.nic.in |")


def test_member_secretary_row_gives_address_and_published_email():
    quote, address, email = authority._row_contact(DIRECTORY)
    assert "Member Secretary" in quote and quote in " ".join(DIRECTORY.split())
    assert address.startswith("Department of Science") and "Shri" not in address
    assert email == "dstpcc-andamans@and.nic.in"


def test_no_email_is_invented():
    quote, address, email = authority._row_contact("The Member Secretary, Some Board, 12 Road, Chennai 600 032.")
    assert email == "" and "600 032" in quote


def test_board_name_must_name_the_state():
    texts = ["as per Central Pollution Control Board norms. Central Pollution Control Board again.",
             "# Andaman & Nicobar Pollution Control Committee"]
    assert authority.board_name(texts, "Andaman and Nicobar Islands") == "Andaman & Nicobar Pollution Control Committee"
    assert authority.board_name(texts, "Tamil Nadu") == ""


def test_letter_keeps_placeholder_without_a_contact():
    ip = data.load(IP)
    to = letter.blocks(ip, ip["findings"][:1])[1]
    assert "[address]" in to[1]


@pytest.mark.skipif(not pt.path(GN).exists(), reason="no paper trail saved")
def test_letter_and_rti_use_saved_contacts_with_check_note():
    gn = data.load(GN)
    blocks = letter.blocks(gn, gn["findings"][:1])
    text = " ".join(str(b[1]) for b in blocks[:5])
    c = authority.contact(GN, "clearance")
    assert c["address"] in text and authority.CHECK in text and "[address]" not in text
    hearing = " ".join(str(b[1]) for b in letter.blocks(gn, gn["findings"][:1], "public_consultation")[:5])
    h = authority.contact(GN, "hearing")
    assert h["email"] in hearing and h["address"] in hearing
    assert authority.CHECK in rti.application_blocks(gn, gn["findings"][0])[1][1]


# ---------- saved results (what the hosted app reads) ----------

@pytest.mark.skipif(not pt.path(GN).exists(), reason="no paper trail saved")
def test_saved_paper_trail_is_verified_and_official():
    for rid in (GN, IP):
        t = pt.load(rid)
        if not t:
            continue
        assert sum(t["drop_counts"].values()) == len(t["dropped"])
        for d in t["documents"]:
            assert pt.is_official(d["url"]) and d["quote"] and d["found_via"] in pt.FOUND_VIA
            assert d["match"] in ("proposal number", "project name")
        for c in (t.get("contacts") or {}).values():
            if c.get("found"):
                assert pt.is_official(c["source"]) and c["quote"]
    assert pt.load(IP)["identity"]["proposals"] == []


def test_paper_trail_reads_only_results():
    assert pt.path(GN).parent.name == "results" and efficiency.PATH.parent.name == "results"


# ---------- context efficiency ----------

def test_feature_names():
    f = tavily_usage.feature_of
    assert f("search", {"topic": "news"}) == "search: news"
    assert f("search", {"exact_match": True}) == "search: exact match"
    assert f("search", {"include_images": True}) == "search: images"
    assert f("extract", {"extract_depth": "advanced"}) == "extract (advanced)"
    assert f("crawl", {}) == "crawl" and f("map", {}) == "map"


def test_used_text_counts_only_text_tavily_returned():
    tavily_usage.reset()
    tavily_usage.returned("extract", {}, {"results": [{"url": "u", "raw_content": "Alpha **beta** [gamma](x) delta epsilon"}]})
    assert tavily_usage.used_text("beta gamma delta", "shown as evidence") == "extract"
    assert tavily_usage.used_text("not in any returned text", "sent to model") is None
    s = tavily_usage.snapshot()["total"]
    assert s["shown as evidence"] == len("beta gamma delta") and s["sent to model"] == 0
    assert s["share"] == pytest.approx(s["used"] / s["returned"])


def test_merge_adds_up():
    a = {"features": {"map": {"calls": 1, "returned": 10, "sent to model": 0, "shown as evidence": 1}}}
    b = {"features": {"map": {"calls": 2, "returned": 30, "sent to model": 3, "shown as evidence": 0}}}
    t = tavily_usage.merge([a, b])["total"]
    assert (t["calls"], t["returned"], t["used"]) == (3, 40, 4) and t["share"] == 0.1


@pytest.mark.skipif(not efficiency.PATH.exists(), reason="no usage measured")
def test_saved_efficiency_is_consistent():
    d = efficiency.load()
    feats = d["overall"]["features"]
    assert d["overall"]["total"]["returned"] == sum(r["returned"] for r in feats.values())
    for r in feats.values():
        assert r["used"] == r["sent to model"] + r["shown as evidence"] <= r["returned"]
    assert efficiency.line(d["overall"]["total"]).startswith("Tavily returned ")


# ---------- the app (replay, no keys) ----------

@pytest.mark.skipif(not pt.path(GN).exists(), reason="no paper trail saved")
def test_public_record_and_efficiency_render_without_keys(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Documents found" in md and "Found via Tavily" in md and "Who to write to" in md
    assert "Context efficiency" in md and "Tavily returned" in md
    assert "Granted ToR" in md


def test_granted_tor_line_when_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(pt, "RESULTS", tmp_path)
    (tmp_path / "paper_trail_x.json").write_text(json.dumps(
        {"granted_tor": {"found": False}, "sites": ["parivesh.nic.in"], "searched_on": "2026-10-28"}))
    assert trail_ui.granted_tor_line("x") == ("Granted ToR not found on official sites "
                                             "(searched: parivesh.nic.in, 2026-10-28)")
