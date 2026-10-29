"""Copy-paste check with Tavily and the model mocked (no network, no credits)."""

import json

import pytest

from tigerfish import copycheck as cc

SITE = ("A total of 330 species of fauna are recorded from the whole GNI area including 28 "
        "species of mammals, 97 species of birds and 23 species of reptiles.")
BOILER = ("Ambient air quality was monitored as per CPCB guidelines and the National Ambient "
          "Air Quality Standards at eight locations around the site.")
LEGAL = ("Land will be acquired under the Right to Fair Compensation and Transparency in Land "
         "Acquisition, Rehabilitation and Resettlement Act, 2013 for the project.")


# ---------- passage selection ----------

def test_site_score():
    assert cc.site_score(SITE) > 0
    assert cc.site_score(BOILER) == 0
    assert cc.site_score(LEGAL) == 0
    assert cc.site_score("Only 330 species here.") == 0            # too short


def test_species_names_raise_score():
    text = ("Crab eating Macaque, Nicobar Megapode and Nicobar Tree Shrew were noticed in "
            "the project area during the surveys.")
    assert cc.site_score(text, {"Nicobar Megapode", "Nicobar Tree Shrew"}) > cc.site_score(text)


def ledger_and_pages():
    pages = {1168: "Intro. " + SITE + " Other text.", 300: BOILER, 301: LEGAL,
             940: "A total of 695 species of fauna with the endemism of 158 species, which is "
                  "equivalent to 22.73% have been reported from Great Nicobar Island."}
    ledger = [
        {"id": "a", "page": 1168, "type": "count", "value": 330, "verified": True,
         "quote": "A total of 330 species of fauna are recorded from the whole GNI area"},
        {"id": "b", "page": 1168, "type": "count", "value": 28, "verified": True,
         "quote": "including 28 species of mammals"},                  # same sentence as "a"
        {"id": "c", "page": 300, "type": "quantity", "value": 8, "verified": True,
         "quote": "at eight locations around the site"},
        {"id": "d", "page": 301, "type": "statement", "value": None, "verified": True,
         "quote": "Land will be acquired under the Right to Fair Compensation"},
        {"id": "e", "page": 940, "type": "quantity", "value": 695, "verified": True,
         "quote": "A total of 695 species of fauna with the endemism of 158 species"},
        {"id": "f", "page": 940, "type": "quantity", "value": 22.73, "verified": False,
         "quote": "paraphrase that is not on the page"},
    ]
    return ledger, pages


def test_select_passages_filters_and_merges(monkeypatch):
    seen = {}

    def fake_chat_json(model, messages, max_tokens, thinking=False):
        seen["listing"] = messages[1]["content"]
        return {"site_specific": [1, 2]}

    monkeypatch.setattr(cc.claims_mod, "chat_json", fake_chat_json)
    ledger, pages = ledger_and_pages()
    out = cc.select_passages(ledger, pages)
    assert sorted(p["page"] for p in out) == [940, 1168]
    by_page = {p["page"]: p for p in out}
    assert by_page[1168]["claim_ids"] == ["a", "b"]          # one passage per sentence
    assert "CPCB" not in seen["listing"] and "Act, 2013" not in seen["listing"]


def only_passages_with(word):
    """Fake LIGHTNING: calls the passages containing `word` site-specific."""
    def fake(model, messages, max_tokens, thinking=False):
        lines = messages[1]["content"].splitlines()
        return {"site_specific": [i for i, line in enumerate(lines, 1) if word in line]}
    return fake


def test_lightning_can_reject_and_cap_applies(monkeypatch):
    monkeypatch.setattr(cc.claims_mod, "chat_json", only_passages_with("695"))
    ledger, pages = ledger_and_pages()
    assert [p["page"] for p in cc.select_passages(ledger, pages)] == [940]
    monkeypatch.setattr(cc.claims_mod, "chat_json", lambda *a, **k: {"site_specific": [1, 2]})
    assert len(cc.select_passages(ledger, pages, max_passages=1)) == 1


def test_site_specific_is_asked_in_small_batches(monkeypatch):
    # 45 passages -> batches of 20, 20, 5. The middle batch's reply is broken: its passages
    # are kept (not judged), and the other batches' answers still filter.
    calls = []

    def fake(model, messages, max_tokens, thinking=False):
        lines = messages[1]["content"].splitlines()
        calls.append(len(lines))
        if len(calls) == 2:
            return None
        return {"site_specific": [i for i, line in enumerate(lines, 1) if "keep" in line]}

    monkeypatch.setattr(cc.claims_mod, "chat_json", fake)
    passages = [("keep " if i % 3 == 0 else "drop ") + "x" * 2000 for i in range(45)]
    got = cc.lightning_site_specific(passages)
    assert calls == [20, 20, 5]
    assert got == ({i for i in range(45) if i % 3 == 0} | set(range(20, 40)))
    monkeypatch.setattr(cc.claims_mod, "chat_json", lambda *a, **k: None)
    assert cc.lightning_site_specific(passages) is None


def test_broken_lightning_answer_keeps_phrase_filter(monkeypatch):
    monkeypatch.setattr(cc.claims_mod, "chat_json", lambda *a, **k: None)
    ledger, pages = ledger_and_pages()
    assert len(cc.select_passages(ledger, pages)) == 2


def test_distinctive_phrase_is_contiguous_and_has_data():
    phrase = cc.distinctive_phrase(SITE)
    assert phrase in SITE and len(phrase.split()) <= cc.PHRASE_WORDS
    assert "330" in phrase


# ---------- overlap ----------

def test_overlap_identical_and_unrelated():
    full = cc.overlap(SITE, "Some intro. " + SITE + " Outro.")
    assert full["longest_run"] == len(cc.tokens(SITE)) and full["ngram"] == 1.0
    none = cc.overlap(SITE, "Completely unrelated text about rainfall in a desert town.")
    assert none["longest_run"] < 3 and none["ngram"] == 0.0


def test_overlap_with_place_swapped():
    other = SITE.replace("GNI area", "Kutch district")
    ov = cc.overlap(SITE, other)
    assert ov["longest_run"] >= 8 and 0.3 < ov["ngram"] < 1.0


def test_matching_snippet_uses_original_text():
    text = "Intro words. A total of 330 Species of FAUNA are recorded from the region. End."
    ov = cc.overlap("A total of 330 species of fauna are recorded", text)
    assert "330 Species of FAUNA" in cc.matching_snippet(ov["run_words"], text)


# ---------- grading ----------

OTHER_PLACE = ("Baseline study, Kutch district, Gujarat. " + SITE.replace("whole GNI area", "study area"))


def test_grade_red_when_data_matches_another_place():
    ov = cc.overlap(SITE, OTHER_PLACE)
    grade, why = cc.grade_hit(SITE, OTHER_PLACE, ov, is_same_project=False)
    assert grade == "RED" and "330" in why


CORALS = ("The island has plates of dead and live corals and in few areas new coral recruits "
          "were also observed along the rocky coastal stretches near Galathea Bay.")


def test_grade_orange_when_only_place_names_change():
    text = "Site description. " + CORALS.replace("Galathea Bay", "Mandvi creek") + " More."
    ov = cc.overlap(CORALS, text)
    grade, _ = cc.grade_hit(CORALS, text, ov, is_same_project=False)
    assert grade == "ORANGE"


def test_grade_none_when_numbers_differ_in_template_prose():
    """Same sentence template, different figures: generic wording, not copied data."""
    text = SITE.replace("330", "412").replace("28", "31").replace("97", "120").replace("23", "40")
    ov = cc.overlap(SITE, text)
    assert cc.grade_hit(SITE, text, ov, is_same_project=False)[0] in (None, "NONE")


def test_grade_none_for_same_project_and_generic():
    ov = cc.overlap(SITE, SITE)
    assert cc.grade_hit(SITE, SITE, ov, is_same_project=True)[0] == "NONE"
    generic = "species of fauna are recorded from the whole area including mammals and birds"
    gv = cc.overlap(SITE, generic)
    assert cc.grade_hit(SITE, generic, gv, is_same_project=False)[0] in (None, "NONE")


def test_grade_none_when_no_overlap():
    text = "Rainfall data for Rajasthan."
    assert cc.grade_hit(SITE, text, cc.overlap(SITE, text), False)[0] is None


def test_same_project_detection():
    assert cc.same_project("https://scroll.in/article/1", "")
    assert cc.same_project("https://x.org", "The Great Nicobar project ...")
    assert not cc.same_project("https://x.org", "An EIA for a port in Kutch")



# ---------- self-match: this report's own document (GREY, never a flag) ----------

KA_OWN = {"ident": {"name_groups": [["karnataka rural road"], ["improvement project", "krrip", "59160"]],
                    "proposals": ["59160-001"], "number_label": "project number"},
          "urls": {cc._url_key("https://www.adb.org/projects/59160-001/main")}}
CUD_OWN = {"ident": {"name_groups": [["cuddalore port"], ["expansion", "mahathi", "mcpmpl"]],
                     "proposals": ["IA/TN/INFRA1/564208/2026"]},
           "urls": {cc._url_key("https://www.tnpcb.gov.in/PDF/Citizen_corner/ph/ExeSumEngMCPMPL2626.pdf")}}


def test_self_match_paper_trail_or_official_portal_naming_the_project():
    adb = "https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf"
    assert "project number in its URL" in cc.self_match(adb, None, "", KA_OWN)
    assert "paper-trail" in cc.self_match("https://www.adb.org/projects/59160-001/main/", None, "", KA_OWN)
    assert "paper-trail" in cc.self_match(
        "https://www.tnpcb.gov.in/PDF/Citizen_corner/ph/ExeSumEngMCPMPL2626.pdf", None, "", CUD_OWN)
    assert "title" in cc.self_match("https://www.tnpcb.gov.in/PDF/other.pdf",
                                    "Executive summary: Expansion of Cuddalore Port", "", CUD_OWN)
    assert "text" in cc.self_match("https://parivesh.nic.in/a.pdf", "Report",
                                   "Proposal no. IA/TN/INFRA1/564208/2026 for the port.", CUD_OWN)
    assert cc.self_match("https://documents.worldbank.org/x.pdf", "Karnataka Rural Roads "
                         "Improvement Project", "", KA_OWN)
    # an official portal that does not name the project is not a self-match
    assert cc.self_match("https://moef.gov.in/x.pdf", "Coastal guidelines", "Ports in general.",
                         CUD_OWN) is None


def test_portal_matching_is_by_host():
    assert cc.on_portal("https://www.tnpcb.gov.in/a.pdf", cc.SELF_MATCH_PORTALS)
    assert cc.on_portal("https://adb.org/a", cc.SELF_MATCH_PORTALS)
    assert not cc.on_portal("https://notgov.in.example.com/a", cc.SELF_MATCH_PORTALS)
    assert not cc.on_portal("https://example.com/gov.in/a.pdf", cc.SELF_MATCH_PORTALS)
    # a report's own official sites (paper-trail identity) extend the list
    assert cc.on_portal("https://krrda.example.org/a", ("krrda.example.org",))


NEWS = ("https://www.hindustantimes.com/india-news/public-hearing-on-january-27-for-great-"
        "nicobar-development-project-101640943466176.html")


def test_news_page_naming_the_project_is_graded_normally_not_self_match():
    """Identical text on a news page that names the project: normal rules, never GREY."""
    own = {"ident": KA_OWN["ident"], "urls": set()}
    title = "Karnataka Rural Roads Improvement Project (59160-001) explained"
    text = "Karnataka Rural Roads Improvement Project 59160-001. " + OTHER_PLACE
    reason = cc.self_match(NEWS, title, text, own)
    assert reason is None
    ov = cc.overlap(SITE, text)
    assert cc.grade_hit(SITE, text, ov, False, self_reason=reason) ==         cc.grade_hit(SITE, text, ov, False)                      # exactly the rules without it
    assert cc.grade_hit(SITE, text, ov, False, self_reason=reason)[0] == "RED"


def test_self_match_none_for_other_documents():
    # same district, different document: not this report
    assert cc.self_match("https://cuddalore.nic.in/fisheries", "Fisheries | Cuddalore District",
                         "Fish landings in Cuddalore district were 235 tonnes.", CUD_OWN) is None
    assert cc.self_match("https://x.org", "Road EIA", "A road project in Kutch.", KA_OWN) is None
    # a blog naming the project in its title and text: not a self-match
    assert cc.self_match("https://blog.example.com/krrip", "Karnataka Rural Roads Improvement "
                         "Project", "the 59160-001 loan", KA_OWN) is None
    assert cc.self_match("https://x.org", "t", "text", None) is None       # no paper trail


def test_grade_grey_for_self_match_before_red():
    ov = cc.overlap(SITE, SITE)
    grade, why = cc.grade_hit(SITE, SITE, ov, is_same_project=False,
                              self_reason="one of this report's paper-trail documents")
    assert grade == "GREY" and why.startswith(cc.SELF_MATCH)
    # without the self-match the same text is RED (the other rules are unchanged)
    assert cc.grade_hit(SITE, OTHER_PLACE, cc.overlap(SITE, OTHER_PLACE), False)[0] == "RED"
    # a self-match with no real overlap is not a match at all
    text = "Rainfall data for Rajasthan."
    assert cc.grade_hit(SITE, text, cc.overlap(SITE, text), False, self_reason="x")[0] is None


def test_self_matches_listed_not_flagged(monkeypatch):
    own_url = "https://www.adb.org/sites/default/files/project-documents/59160/59160-001-eia-1164971-en.pdf"
    other = "https://example.org/kutch.pdf"
    monkeypatch.setattr(cc, "search", lambda q, b: {"results": [
        {"url": own_url, "title": "Karnataka Rural Roads Improvement Project Part 1 of 4", "content": SITE},
        {"url": other, "title": "Kutch baseline", "content": OTHER_PLACE}]})
    monkeypatch.setattr(cc, "extract", lambda urls, b: {})
    monkeypatch.setattr(cc, "describe_place", lambda url, text: "Kutch, Gujarat")
    r = cc.check_passage({"page": 17, "text": SITE, "claim_ids": []}, cc.Budget(0), own=KA_OWN)
    grade, hits = cc.flagged_hits(r)
    assert grade == "RED" and [h["url"] for h in hits] == [other]     # the own copy is not a flag
    ex = cc.excluded_matches([r])
    assert len(ex) == 1 and ex[0]["url"] == own_url and ex[0]["grade"] == "GREY"
    assert ex[0]["label"] == cc.SELF_MATCH and ex[0]["page"] == 17


def test_own_documents_from_paper_trail(tmp_path, monkeypatch):
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "paper_trail_r1.json").write_text(json.dumps({
        "identity": KA_OWN["ident"], "documents": [{"url": "https://www.adb.org/projects/59160-001/main"}]}))
    monkeypatch.setattr(cc, "ROOT", tmp_path)
    own = cc.own_documents("r1")
    assert own["ident"]["proposals"] == ["59160-001"] and own["urls"] == KA_OWN["urls"]
    assert own["portals"][:len(cc.SELF_MATCH_PORTALS)] == cc.SELF_MATCH_PORTALS
    assert cc.own_documents("missing") is None


# ---------- Tavily cache and credit cap ----------

class FakeTavily:
    def __init__(self):
        self.calls = []

    def search(self, **kw):
        self.calls.append(("search", kw))
        return {"results": [{"url": "https://other.org/eia", "title": "Kutch EIA",
                             "content": OTHER_PLACE}], "usage": {"credits": 1}}

    def extract(self, **kw):
        self.calls.append(("extract", kw))
        return {"results": [{"url": u, "raw_content": OTHER_PLACE} for u in kw["urls"]]}


@pytest.fixture
def fake_tavily(monkeypatch, tmp_path):
    fake = FakeTavily()
    monkeypatch.setattr(cc, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cc, "client", lambda: fake)
    monkeypatch.setattr(cc, "describe_place", lambda url, text: "Kutch district, Gujarat")
    return fake


def test_calls_are_cached_and_credits_counted(fake_tavily):
    budget = cc.Budget(10)
    cc.search('"x"', budget)
    cc.search('"x"', budget)                       # cached: free
    cc.extract(["https://a", "https://b"], budget)  # no usage field: 1 credit per 5 URLs
    assert budget.used == 2 and budget.calls == 2 and budget.cached == 1
    assert len(fake_tavily.calls) == 2
    assert all(kw["include_usage"] for _, kw in fake_tavily.calls)


def test_extract_cost_is_per_five_urls(fake_tavily):
    budget = cc.Budget(10)
    cc.extract([f"https://u{i}" for i in range(6)], budget)
    assert budget.used == 2


def test_credit_cap_stops_run(fake_tavily):
    passages = [{"page": n, "text": SITE.replace("330", str(330 + n)), "claim_ids": []}
                for n in range(5)]                     # different phrases: no cache hits
    out, stopped = cc.check_passages(passages, cc.Budget(3))
    assert "credit cap" in stopped
    # passage 1: search 1 + extract 1; passage 2: search 1 + extract (same URL: cached, free);
    # passage 3: search would make 4 > 3 -> refused before calling Tavily
    assert len(out) == 2
    assert sum(1 for c in fake_tavily.calls if c[0] == "search") == 2


def test_check_passage_end_to_end(fake_tavily):
    budget = cc.Budget(10)
    r = cc.check_passage({"page": 1168, "text": SITE, "claim_ids": ["a"]}, budget)
    [hit] = r["hits"]
    assert hit["grade"] == "RED"
    assert hit["message"] == ("Text closely matches https://other.org/eia, which describes "
                              "Kutch district, Gujarat. Verify.")
    search_kw = fake_tavily.calls[0][1]
    assert search_kw["exact_match"] and search_kw["query"].startswith('"')
    assert "scroll.in" in search_kw["exclude_domains"]


# ---------- species source hunt ----------

NAMES = ["Axis axis", "Funambulus pennantii", "Paguma larvata", "Muntiacus muntjak",
         "Taupaia nicobarica nicobarica", "Rattus rattus"]


def test_name_overlap_uses_binomial():
    text = "Mammals: Funambulus pennantii, Paguma larvata and Taupaia nicobarica were seen."
    assert cc.name_overlap(NAMES, text) == ["Funambulus pennantii", "Paguma larvata",
                                            "Taupaia nicobarica nicobarica"]


RARE = ["Taupaia nicobarica nicobarica", "Paguma larvata", "Funambulus pennantii",
        "Muntiacus muntjak", "Axis axis", "Rattus rattus"]


def test_hunt_queries_rarest_first():
    qs = cc.hunt_queries(NAMES, RARE)
    assert qs[0] == '"Taupaia nicobarica" "Paguma larvata" "Funambulus pennantii"'
    assert len(qs) <= cc.HUNT_QUERIES and all(q.count('"') >= 6 for q in qs)


def test_hunt_queries_flagged_first_then_mixed():
    flagged = ["Funambulus pennantii", "Muntiacus muntjak", "Axis axis"]
    qs = cc.hunt_queries(NAMES, RARE, flagged)
    assert qs[0] == '"Funambulus pennantii" "Muntiacus muntjak" "Axis axis"'
    assert qs[-1] == ('"Funambulus pennantii" "Muntiacus muntjak" '
                      '"Taupaia nicobarica" "Paguma larvata"')
    assert len(qs) == cc.HUNT_QUERIES


def test_hunt_ranks_by_names_found(fake_tavily, monkeypatch):
    def search(**kw):
        return {"results": [
            {"url": "https://a.org", "content": "Funambulus pennantii and Paguma larvata"},
            {"url": "https://b.org", "content": "Axis axis"}], "usage": {"credits": 1}}
    monkeypatch.setattr(fake_tavily, "search", search)
    monkeypatch.setattr(fake_tavily, "extract", lambda **kw: {"results": []})
    ranked, stopped = cc.hunt_species_source(NAMES, cc.Budget(50))
    assert stopped is None and ranked[0]["url"] == "https://a.org"
    assert len(ranked[0]["names"]) == 2


# ---------- borrowed text (INFO) ----------

GUIDE = ("Maintaining wildlife habitat connectivity is the first step in avoiding impacts from "
         "road construction on animal movement, and crossing structures should be placed where "
         "animals already move across the landscape between patches of habitat. Fencing is "
         "used to guide animals towards these structures and away from the road surface.")


def generic_hit(url="https://www.fhwa.dot.gov/clas/ctip/ch_3.aspx", title="Wildlife Crossing Structures"):
    # The source shares a 22-word run with our 40-word passage (like the real p.392 match:
    # a long verbatim run inside a longer sentence), so the hit is generic NONE, not ORANGE.
    text = ("Federal guidance. " + " ".join(GUIDE.split()[:22]) +
            " and should be planned with state agencies before design begins.")
    ov = cc.overlap(GUIDE, text)
    grade, why = cc.grade_hit(GUIDE, text, ov, is_same_project=False)
    hit = {"url": url, "title": title, "grade": grade, "why": why,
           "longest_run": ov["longest_run"], "snippet": cc.matching_snippet(ov["run_words"], text)}
    return hit, ov


def test_borrowed_text_flagged_as_info_when_uncited():
    hit, ov = generic_hit()
    assert hit["grade"] == "NONE"                     # generic guidance: never RED/ORANGE
    b = cc.borrowed_text({"page": 392, "text": GUIDE}, "Page 392 text. " + GUIDE, hit, ov["run_words"])
    assert b["type"] == "borrowed_text" and b["grade"] == "INFO"
    assert b["longest_run"] >= 20 and b["quote"] in GUIDE
    assert "fhwa.dot.gov" in b["message"] and "no citation" in b["message"]


@pytest.mark.parametrize("citation", ["(FHWA, 2011)", "see Wildlife Crossing Structures guidance"])
def test_borrowed_text_not_flagged_when_cited(citation):
    hit, ov = generic_hit()
    page = GUIDE + " " + citation
    assert cc.borrowed_text({"page": 392, "text": GUIDE}, page, hit, ov["run_words"]) is None


def test_borrowed_text_needs_long_run():
    hit, ov = generic_hit()
    hit["longest_run"] = 19
    assert cc.borrowed_text({"page": 392, "text": GUIDE}, GUIDE, hit, ov["run_words"]) is None


@pytest.mark.parametrize("grade, why", [("RED", "data"), ("ORANGE", "near-identical"),
                                        ("NONE", "same project or coverage of it")])
def test_borrowed_text_only_for_generic_hits(grade, why):
    hit, ov = generic_hit()
    hit.update(grade=grade, why=why)
    assert cc.borrowed_text({"page": 392, "text": GUIDE}, GUIDE, hit, ov["run_words"]) is None


def test_citation_terms():
    assert cc.citation_terms("https://www.fhwa.dot.gov/x", "Chapter 3: Wildlife crossings") == \
        ["fhwa", "Chapter 3: Wildlife crossings"]


def test_one_shared_number_in_a_stock_sentence_is_not_red():
    # p.327 vs a ZSI book on Vembanad Lake (Kerala): same sentence template, same "10".
    passage = ("A total of 10 species of amphibians have been reported from the island including "
               "the endemic Nicobar Tree Frog")
    other = ("AMPHIBIA A total of 10 species of amphibians have been reported from the Vembanad "
             "Lake area. The Malabar Gliding Frog was rarely sighted.")
    grade, _ = cc.grade_hit(passage, other, cc.overlap(passage, other), is_same_project=False)
    assert grade in (None, "NONE", "ORANGE")
