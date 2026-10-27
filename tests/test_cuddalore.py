"""Cuddalore as a second report: site profile, its own checks, the partial-audit label, the
resume's cost totals, the Tamil letter and the app in replay mode (no keys)."""

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audit  # noqa: E402
import export_results as ex  # noqa: E402
from tigerfish import accreditation, llm, sites, status_pages  # noqa: E402
from tigerfish.ui import letter  # noqa: E402

REPORT_JSON = ROOT / "results" / "cuddalore_port_2026_draft.json"


# ---------- site profile ----------

def test_cuddalore_profile_is_mainland_tamil_nadu():
    p = sites.profile(sites.CUDDALORE)
    assert p["archipelago_gadm"] is None                       # no A&N archipelago rule
    assert p["state"] == "Tamil Nadu"
    lat, lon = p["site"]
    assert abs(lat - 11.70) < 0.05 and abs(lon - 79.78) < 0.05  # the report's own coordinates
    assert sites.profile(sites.GREAT_NICOBAR)["archipelago_gadm"] == "IND.1_1"


# ---------- partial-audit label ----------

def test_audit_status_partial_then_complete():
    run = {"candidates": 1589, "stopped": "cost cap $7.41 reached (spent $7.4056); stopped at "
                                          "candidate 1077 of 1589; about 481 candidates not judged"}
    s = ex.audit_status(run)
    assert s["label"] == "Audit partial: 1,077 of 1,589 candidate pairs judged" and not s["complete"]
    s = ex.audit_status({"candidates": 1589, "stopped": None})       # after the resume run
    assert s["complete"] and s["label"] == "Audit complete: all 1,589 candidate pairs judged"


# ---------- resume keeps the first sitting's cost ----------

def test_resume_carries_the_first_sittings_totals():
    prev = {"cost_usd": 10.0006, "wall_clock_s": 3900.8, "stopped": "cost cap ...",
            "tavily": {"credits": 47},
            "calls_per_model": {"nvidia/X": {"api_calls": 5, "prompt_tokens": 10,
                                             "completion_tokens": 2, "cost_usd": 10.0}}}
    report = {"cost_usd": 2.5, "wall_clock_s": 600.0, "tavily": {"credits": 0},
              "calls_per_model": {"nvidia/X": {"api_calls": 3, "prompt_tokens": 4,
                                               "completion_tokens": 1, "cost_usd": 2.5}}}
    tot = audit.add_sitting(audit.first_totals(prev), report, SimpleNamespace(new_pages=None))
    assert tot["cost_usd"] == pytest.approx(12.5006)
    assert tot["per_model"]["X"]["api_calls"] == 8
    assert "resume sitting" in tot["note"] and tot["sittings"][0]["new_pages"] is None


def test_measured_pass_rate():
    assert audit.measured_pass_rate({"triage_answers": {"yes": 685, "no": 514, "unsure": 1}}) \
        == pytest.approx(686 / 1200)
    assert audit.measured_pass_rate({}) is None


# ---------- certificate numbers, tables, dedupe ----------

def test_two_certificate_numbers_are_found_and_same_number_is_one():
    pages = [{"page": 8, "text": "NABET Certificate Number: NABET/EIA/23-26/SA 0236 issued on March 18, 2025."},
             {"page": 9, "text": "Certificate No.: NABET/EIA/2326/SA 0236 dated March 18, 2025"},
             {"page": 469, "text": "accredited FRICS with certificate no. NABET/EIA/2326/IA 0123 valid up to August 16, 2026."}]
    found = accreditation.certificate_numbers(pages)
    assert [c["page"] for c in found] == [8, 469]
    assert found[0]["also_on"] == [9]                     # hyphen/spacing ignored


TABLE = "\n".join(["S.No", "Scientific Name", "Common", "Name", "Order", "Family", "IUCN", "IWPA",
                   "Vernacular Name(Tamil)",
                   "8", "Ptyas mucosa", "Common rat", "snake", "Squamata", "Colubridae", "LC", "ll", "Sarai pambu",
                   "9", "Varanus bengalensis", "Common", "Indian monitor", "Squamata", "Varanidae", "NT", "I", "Udumbu",
                   "10", "Egretta garzetta", "Little Egret", "Pelecaniformes", "Ardeidae", " ", "II", "Kokku"])


def test_status_table_parser_reads_cells_and_never_guesses():
    rows = status_pages.tables_from_pages([{"page": 737, "text": TABLE}])[0]["rows"]
    by = {r["Scientific name"]: r for r in rows}
    assert by["Varanus bengalensis"]["IUCN"] == "NT" and by["Varanus bengalensis"]["IWPA Schedule"] == "I"
    assert by["Ptyas mucosa"]["IWPA Schedule"] is None               # "ll" is not read as "II"
    assert by["Egretta garzetta"]["IUCN"] is None                    # blank cell stays blank


def test_omission_summary_lines_are_not_merged():
    a = {"check": "omission", "quotes": [{"page": None, "text": "Mobula mobular: 1 record(s) within 25 km of X, latest 2020"}]}
    b = {"check": "omission", "quotes": [{"page": None, "text": "Alopias pelagicus: 1 record(s) within 25 km of X, latest 2020"}]}
    assert not ex.same_finding(a, b) and ex.same_finding(a, a)


# ---------- Tamil letter ----------

FINDINGS = [{"check_name": "Internal contradiction", "title": "Pages 239 and 433 disagree",
             "quotes": [{"page": 239, "text": "Among the 107 plant species reported from the study area"}],
             "why": "107 vs 187 plant species.", "evidence": [], "clear": "A correction."}]


def fake_tamil(model, messages, **kw):
    texts = json.loads(messages[1]["content"])["texts"]
    assert "Tamil" in messages[0]["content"]
    return json.dumps({"translations": ["தமிழ்: " + t for t in texts]}, ensure_ascii=False)


def test_tamil_offered_for_tamil_nadu_only():
    assert letter.state_language({"state": "Tamil Nadu"}) == "ta"
    assert letter.state_language({"state": "Andaman and Nicobar Islands"}) is None
    assert letter.parts("both") == ["en", "hi"] and letter.parts("en+ta") == ["en", "ta"]


def test_tamil_letter_keeps_quotes_and_pages(monkeypatch):
    monkeypatch.setattr(llm, "chat", fake_tamil)
    body = letter.build_letter({"title": "Cuddalore", "source": "Draft"}, FINDINGS, "en+ta")
    doc = Document(io.BytesIO(body))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert text.index("Sir / Madam,") < text.index("தமிழ்: Sir / Madam,")
    assert "தமிழ்: The report states (page 239):" in text
    assert text.count("“Among the 107 plant species reported from the study area”") == 2
    tags = {e.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
            for e in doc.element.body.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}lang")}
    assert "ta-IN" in tags


# ---------- exported report and the app (replay, no keys) ----------

needs_export = pytest.mark.skipif(not REPORT_JSON.exists(), reason="run scripts/export_results.py")


@needs_export
def test_exported_report_is_labelled_and_neutral():
    d = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert d["state"] == "Tamil Nadu" and d["human_reviewed"] is False
    assert any(n.startswith("Audit partial: ") or n.startswith("Audit complete: ") for n in d["notices"])
    assert any("not yet human-reviewed" in n for n in d["notices"])
    text = json.dumps(d["findings"]).lower()
    for word in (" fraud", " fake", " lied", " liar"):
        assert word not in text
    for f in d["findings"]:
        for img in f["images"]:
            assert not img.startswith("cache") and (ROOT / "results" / img).exists()


@needs_export
def test_app_shows_cuddalore_notices_and_tamil(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    title = json.loads(REPORT_JSON.read_text(encoding="utf-8"))["title"]
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    at.selectbox[0].select(title).run()
    assert not at.exception
    warnings = [w.value for w in at.warning]
    assert any("candidate pairs judged" in w for w in warnings)
    assert any("not yet human-reviewed" in w for w in warnings)
    assert "Tamil" in at.radio[0].options and "English + Tamil" in at.radio[0].options
