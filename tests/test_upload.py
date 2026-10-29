"""Upload of a report the app has never seen: facts detected from the report's own text, and
the free checks with no key. No API keys, no network (GBIF and the model are replaced)."""

import pymupdf
import pytest

from tigerfish import detect, pdf_reader, upload_checks


def page(no, text):
    return {"page": no, "text": text}


COVER = page(1, "Annex 2 to Sample Port Project\nEnvironmental Impact Assessment\nJuly 2026\n"
                "India: Sample Coastal Port Expansion Project\n"
                "Prepared by Sample Enviro Consultants Pvt. Ltd. for the Port Authority.")
STATE = page(2, "The project lies in Cuddalore district, Tamil Nadu. Tamil Nadu has a long coast. "
                "Kerala is not involved.")
SITE_DMS = page(3, "The site is located at latitude 11°42'22.43\" N, longitude 79°46'30.52\" E.")
SITE_RANGE = page(3, "The state lies between 11.5° N and 18.5° N latitudes and between 74° E and "
                     "78.5° E longitudes.")


def test_text_search_finds_the_facts():
    got = detect.detect([COVER, STATE, SITE_DMS])
    assert got["project"]["value"] == "Sample Coastal Port Expansion Project"
    assert got["project"]["page"] == 1
    assert got["state"]["value"] == "Tamil Nadu" and got["state"]["page"] == 2
    lat, lon = got["site"]["value"]
    assert abs(lat - 11.7062) < 1e-3 and abs(lon - 79.7751) < 1e-3 and got["site"]["page"] == 3
    assert got["consultant"]["value"].startswith("Sample Enviro Consultants Pvt. Ltd")
    assert got["year"]["value"] == 2026
    assert got["letter_language"] == {"value": "English, Hindi, Tamil", "regional": "Tamil",
                                      "translated": True}
    assert got["model_error"] is None


def test_a_range_gives_its_midpoint_and_says_so():
    got = detect.detect([COVER, SITE_RANGE])
    assert got["site"]["value"] == (15.0, 76.25)
    assert "midpoint" in got["site"]["how"]


def test_nothing_found_is_none_not_a_guess():
    got = detect.detect([page(1, "Chapter 1. General text with no names or numbers at all.")])
    assert all(got[k] is None for k in detect.FIELDS)
    assert got["letter_language"]["value"] == "English, Hindi"


def test_state_names_inside_other_words_do_not_match():
    got = detect.detect([page(1, "Nagaland and Jharkhand. Nagaland again.")])
    assert got["state"]["value"] == "Nagaland"


def test_model_values_need_a_quote_on_the_cited_page(monkeypatch):
    from tigerfish import claims
    reply = {"project": {"value": "Real Project", "page": 1, "quote": "Sample Coastal Port Expansion Project"},
             "consultant": {"value": "Invented Ltd", "page": 1, "quote": "words not on the page"},
             "state": {"value": "Tamil Nadu", "page": 2, "quote": "Tamil Nadu has a long coast"},
             "site": None, "year": {"value": "2026", "page": 1, "quote": "July 2026"}}
    monkeypatch.setattr(claims, "chat_json", lambda *a, **k: reply)
    got = detect.detect([COVER, STATE], use_model=True)
    assert got["project"]["value"] == "Real Project" and "model" in got["project"]["how"]
    # the model's consultant quote is not on the page: the text-search value stays
    assert got["consultant"]["how"] == "text search"
    assert got["year"]["value"] == 2026


def test_model_failure_keeps_the_text_search(monkeypatch):
    from tigerfish import claims

    def boom(*a, **k):
        raise RuntimeError("NEBIUS_API_KEY is missing")
    monkeypatch.setattr(claims, "chat_json", boom)
    got = detect.detect([COVER, STATE], use_model=True)
    assert got["state"]["value"] == "Tamil Nadu" and "RuntimeError" in got["model_error"]


# ---------- free checks ----------

NO_TABLES = lambda pages: {"tables": [], "results": []}


def statuses_by_check(out):
    return {s["check"]: s for s in out}


def test_no_site_says_not_available():
    pages = [COVER, STATE]
    found, out = upload_checks.run_free(pages, {"site": None, "pages_total": 2}, status_fn=NO_TABLES)
    s = statuses_by_check(out)
    assert s["number_pair"]["status"] == upload_checks.RAN
    assert s["iucn_status"]["status"] == upload_checks.RAN
    assert s["species_range"]["status"] == upload_checks.NOT_AVAILABLE
    assert s["omission"]["status"] == upload_checks.NOT_AVAILABLE
    assert "no project site" in s["omission"]["detail"]


def test_part_of_a_report_does_not_run_the_omission_check():
    meta = {"site": (11.7, 79.8), "pages_total": 300, "site_label": "the site"}
    found, out = upload_checks.run_free([COVER, STATE], meta, species_fn=lambda *a: {"grade": None},
                                        omission_fn=lambda *a, **k: pytest.fail("must not run"),
                                        status_fn=NO_TABLES)
    s = statuses_by_check(out)
    assert s["species_range"]["status"] == upload_checks.RAN
    assert s["omission"]["status"] == upload_checks.NOT_AVAILABLE
    assert "only 2 of 300 pages" in s["omission"]["detail"]


def test_an_approximate_site_does_not_run_the_omission_check():
    meta = {"site": (15.0, 76.25), "site_approximate": True, "pages_total": 2}
    _, out = upload_checks.run_free([COVER, STATE], meta, species_fn=lambda *a: {"grade": None},
                                    omission_fn=lambda *a, **k: pytest.fail("must not run"),
                                    status_fn=NO_TABLES)
    assert "midpoint" in statuses_by_check(out)["omission"]["detail"]


def test_whole_report_with_a_site_runs_the_omission_check():
    rows = [{"grade": "RED", "category": "EN", "name": "Panthera tigris", "near": 3,
             "near_since_2000": 2, "wide": 5, "latest_year": 2024, "searched_for": ["name: Panthera tigris"],
             "map": "https://www.gbif.org/x", "message": "Recorded near the project site (GBIF) "
                                                         "but not mentioned in the report. Verify."}]
    fake = lambda pages, lat, lon: {"rows": rows, "pages_searched": 2, "pages_without_text": []}
    meta = {"site": (11.7, 79.8), "pages_total": 2, "site_label": "the site"}
    found, out = upload_checks.run_free([COVER, STATE], meta, species_fn=lambda *a: {"grade": None},
                                        omission_fn=fake, status_fn=NO_TABLES)
    assert statuses_by_check(out)["omission"]["count"] == 1
    om = [f for f in found if f["check"] == "omission"]
    assert om[0]["grade"] == "RED" and "Verify" in om[0]["message"]


def test_island_rule_only_for_andaman_and_nicobar(monkeypatch):
    from tigerfish import species
    fn, _ = upload_checks.species_check_fn({"state": "Tamil Nadu"})
    assert fn.keywords["archipelago_gadm"] is None and fn.keywords["region_gadm"] is None
    fn, _ = upload_checks.species_check_fn({"state": "Andaman and Nicobar Islands"})
    assert fn.keywords["archipelago_gadm"] == species.ANDAMAN_NICOBAR_GADM
    monkeypatch.setattr(species, "gbif_get", lambda path, **p: {"results": [
        {"id": "IND.16_1", "name": "Karnataka", "variantName": ["Mysore"]}]})
    fn, region = upload_checks.species_check_fn({"state": "Karnataka", "site_approximate": True})
    assert region == "IND.16_1" and fn.keywords["region_label"] == "Karnataka"


def test_keyed_statuses_list_what_needs_a_key():
    out = upload_checks.keyed_statuses(has_key=False)
    s = statuses_by_check(out)
    assert s["contradiction"]["status"] == upload_checks.NEEDS_KEY
    for check in ("copy_paste", "accreditation", "legal_schedule", "promise"):
        assert s[check]["status"] == upload_checks.LOCAL_ONLY and s[check]["detail"]
    assert statuses_by_check(upload_checks.keyed_statuses(True, ran=True, cost_usd=0.01))[
        "contradiction"]["status"] == upload_checks.RAN


def test_no_key_upload_end_to_end(tmp_path, monkeypatch):
    """A new PDF, no key: facts detected, every free check accounted for, nothing paid."""
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setattr(pdf_reader, "PAGES_DIR", tmp_path / "pages")
    doc = pymupdf.open()
    for p in (COVER, STATE, SITE_DMS,
              page(4, "The total project area is 45 ha of reclaimed land at the port."),
              page(5, "The total project area is 60 ha of reclaimed land at the port.")):
        doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), p["text"], fontsize=10)
    pdf = tmp_path / "new_upload.pdf"
    doc.save(pdf)
    pages = pdf_reader.read_pdf(pdf, render=False)
    got = detect.detect(pages)
    assert got["state"]["value"] == "Tamil Nadu" and got["site"] is not None
    meta = {"site": got["site"]["value"], "pages_total": len(pages), "state": "Tamil Nadu",
            "site_label": "the site detected from the report"}
    found, out = upload_checks.run_free(pages, meta, species_fn=lambda *a: {"grade": None},
                                        omission_fn=lambda pages, lat, lon: {
                                            "rows": [], "pages_searched": 5, "pages_without_text": []},
                                        status_fn=NO_TABLES)
    assert {s["check"] for s in out} == {c for c, _ in upload_checks.FREE}
    assert all(s["status"] == upload_checks.RAN for s in out)
    assert all(f["grade"] == "INFO" for f in found if f["check"] == "number_pair")


def test_gbif_down_fails_one_check_not_the_upload():
    """An outage (no DNS) marks the GBIF checks as failed; the other checks still report."""
    def down(*a, **k):
        raise ConnectionError("api.gbif.org unreachable")
    meta = {"site": (11.7, 79.8), "pages_total": 2, "site_label": "the site"}
    found, out = upload_checks.run_free([COVER, STATE], meta, species_fn=down, omission_fn=down,
                                        status_fn=down)
    s = statuses_by_check(out)
    assert s["number_pair"]["status"] == upload_checks.RAN
    for check in ("iucn_status", "omission"):
        assert s[check]["status"] == upload_checks.FAILED and "GBIF" in s[check]["detail"]
