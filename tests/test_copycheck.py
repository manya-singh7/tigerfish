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
