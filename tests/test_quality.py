"""Review quality: the 20-judged precision rule with Wilson intervals, one queue per report,
the CSV import of hand checks (scripts/import_reviews.py), the templates, the measured price
line and the single-table label."""

import csv
import json
import sys
from pathlib import Path

import pytest

from tigerfish import library, quality, review

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import import_reviews  # noqa: E402


def finding(fid, grade="RED", check="contradiction", pages=(1, 2)):
    return {"id": fid, "grade": grade, "check": check, "check_name": "Internal contradiction",
            "title": f"Title {fid}", "why": "why", "message": "m",
            "quotes": [{"page": p, "text": f"quote {p}"} for p in pages], "evidence": []}


REPORT = {"id": "rep", "title": "Report", "findings": [finding("ct-1"), finding("ct-2", "ORANGE"),
                                                        finding("ct-3", "INFO")]}


# ---------- precision honesty ----------

def test_wilson_interval_known_values():
    lo, hi = quality.wilson(21, 27)
    assert round(lo, 2) == 0.59 and round(hi, 2) == 0.89
    assert quality.wilson(0, 0) is None
    lo, hi = quality.wilson(20, 20)
    assert hi == 1.0 and 0.83 < lo < 0.84


def test_fewer_than_20_judged_gives_no_percentage():
    assert quality.estimate(5, 7) == "7 reviewed so far: too few to estimate precision"
    assert quality.estimate(0, 0) == "0 reviewed so far: too few to estimate precision"
    assert "%" not in quality.estimate(19, 19)


def test_20_or_more_judged_gives_percentage_and_interval():
    assert quality.estimate(21, 27) == "78% (59-89%), 27 judged"
    assert quality.estimate(20, 20).startswith("100% (84-100%)")


def test_agreement_follows_the_same_rule():
    a = {"agree": 3, "both_reviewed": 4}
    assert "too few to estimate agreement" in quality.agreement_text(a)
    a = {"agree": 18, "both_reviewed": 20}
    assert quality.agreement_text(a).startswith("90% (")


# ---------- one queue per report ----------

def test_queue_for_a_report_without_a_queue_file():
    q = review.queue_for(REPORT, base=None)
    assert [i["flag_id"] for i in q["items"]] == ["ct-1", "ct-2"]       # RED/ORANGE only
    assert q["total"] == 2 and q["report_id"] == "rep"
    assert q["items"][0]["pages"] == [1, 2] and q["items"][0]["title"] == "Title ct-1"


def test_queue_file_is_kept_and_other_findings_added():
    base = {"report_id": "rep", "order": "top", "double_review": 1,
            "items": [{"n": 1, "flag_id": "ct-9", "finding_id": "ct-1", "double_review": True,
                       "group": "top30", "pages": [1, 2], "quotes": []}]}
    q = review.queue_for(REPORT, base=base)
    assert [i["flag_id"] for i in q["items"]] == ["ct-9", "ct-2"]
    assert q["items"][1]["group"] == "other" and "then 1 flags" in q["order"]
    assert review.flag_ids(q) == {"ct-9": "ct-9", "ct-2": "ct-2", "ct-1": "ct-9"}


def test_reviews_are_kept_per_report(tmp_path):
    store = tmp_path / "reviews.jsonl"
    review.record("ct-1", "A", "real", path=store, report_id="rep")
    review.record("ct-1", "A", "false_alarm", path=store, report_id="other")
    review.record("ct-1", "B", "unsure", path=store)                  # old row: Great Nicobar
    assert review.load_reviews(store, "rep")["ct-1"]["a"]["decision"] == "real"
    assert review.load_reviews(store, "other")["ct-1"]["a"]["decision"] == "false_alarm"
    assert set(review.load_reviews(store, review.LEGACY_REPORT)["ct-1"]) == {"b"}


def test_two_reviewers_disagreeing_is_disputed_and_counts_for_agreement(tmp_path):
    store = tmp_path / "reviews.jsonl"
    q = review.queue_for(REPORT, base=None)
    review.record("ct-1", "A", "real", path=store, report_id="rep")
    review.record("ct-1", "B", "false_alarm", path=store, report_id="rep")
    r = review.load_reviews(store, "rep")
    assert review.verdict(q["items"][0], r) == "disputed"
    assert review.agreement(q, r)["both_reviewed"] == 1


def test_report_quality_counts(tmp_path):
    store = tmp_path / "reviews.jsonl"
    review.record("ct-1", "A", "real", path=store, report_id="rep")
    review.record("ct-2", "A", "unsure", path=store, report_id="rep")
    q = quality.report_quality(REPORT, review.queue_for(REPORT, base=None),
                               review.load_reviews(store, "rep"))
    assert (q["flags"], q["reviewed"], q["confirmed"], q["dismissed"], q["unsure"]) == (2, 2, 1, 0, 1)
    assert q["text"] == "1 reviewed so far: too few to estimate precision"
    o = quality.overall([q, q])
    assert o["flags"] == 4 and "All 2 reports: 4 RED/ORANGE flags, 4 reviewed" in quality.overall_line(o)


# ---------- CSV import ----------

@pytest.fixture
def fake_reports(monkeypatch):
    queues = {"rep": review.queue_for(REPORT, base=None)}
    monkeypatch.setattr(import_reviews, "reports",
                        lambda results=None: (queues, {"rep": "rep", "report": "rep"}))
    return queues


def write_csv(path, rows, cols=import_reviews.COLUMNS):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path


ROW = {"report": "rep", "flag_id": "ct-1", "pages": "1, 2", "verdict": "correct",
       "reason": "p.1 and p.2 read", "reviewer": "Manya Singh", "date": "2026-10-29"}


def test_import_writes_rows_the_app_reads(tmp_path, fake_reports):
    out = tmp_path / "reviews.jsonl"
    src = write_csv(tmp_path / "in.csv", [ROW, {**ROW, "flag_id": "ct-2", "verdict": "",
                                                 "reviewer": ""}])
    assert import_reviews.import_csv(src, out) == 0
    rows = review.load_rows(out)
    assert len(rows) == 1
    want = {"report_id": "rep", "flag_id": "ct-1", "decision": "real",
            "note": "p.1 and p.2 read", "time": "2026-10-29T00:00:00"}
    assert {k: rows[0][k] for k in want} == want
    assert review.load_reviews(out, "rep")["ct-1"]["manya singh"]["decision"] == "real"
    assert import_reviews.import_csv(src, out) == 0                    # again: nothing added
    assert len(review.load_rows(out)) == 1


def test_import_rejects_unknown_flags_and_writes_nothing(tmp_path, fake_reports, capsys):
    out = tmp_path / "reviews.jsonl"
    src = write_csv(tmp_path / "in.csv", [ROW, {**ROW, "flag_id": "ct-404"},
                                          {**ROW, "flag_id": "ct-3"},         # INFO: not a flag
                                          {**ROW, "report": "nope"},
                                          {**ROW, "verdict": "maybe"},
                                          {**ROW, "date": "29/10/2026"}])
    assert import_reviews.import_csv(src, out) == 1
    assert not out.exists()
    text = capsys.readouterr().out
    assert "unknown flag id 'ct-404'" in text and "unknown flag id 'ct-3'" in text
    assert "unknown report 'nope'" in text and "5 rejected" in text
    assert import_reviews.import_csv(src, out, skip_invalid=True) == 0
    assert len(review.load_rows(out)) == 1


def test_import_never_overwrites_another_reviewer(tmp_path, fake_reports):
    out = tmp_path / "reviews.jsonl"
    review.record("ct-1", "Teammate", "false_alarm", path=out, report_id="rep")
    src = write_csv(tmp_path / "in.csv", [ROW])
    assert import_reviews.import_csv(src, out) == 0
    by = review.load_reviews(out, "rep")["ct-1"]
    assert by["teammate"]["decision"] == "false_alarm" and by["manya singh"]["decision"] == "real"
    # the same reviewer's newer verdict counts; an older one is not imported
    write_csv(src, [{**ROW, "verdict": "wrong", "date": "2026-10-30"}])
    import_reviews.import_csv(src, out)
    write_csv(src, [{**ROW, "verdict": "unsure", "date": "2026-10-01"}])
    import_reviews.import_csv(src, out)
    assert review.load_reviews(out, "rep")["ct-1"]["manya singh"]["decision"] == "false_alarm"


def test_templates_list_every_flag(tmp_path, fake_reports):
    [path] = import_reviews.write_templates(tmp_path)
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert [r["flag_id"] for r in rows] == ["ct-1", "ct-2"]
    assert rows[0]["pages"] == "1, 2" and rows[0]["summary"] == "\"quote 1\" vs \"quote 2\""
    assert all(r["verdict"] == r["reviewer"] == "" for r in rows)
    assert list(rows[0]) == import_reviews.TEMPLATE_COLUMNS


@pytest.mark.skipif(not (ROOT / "review" / "templates").exists(), reason="no templates yet")
def test_committed_templates_match_the_queues():
    queues, _ = import_reviews.reports()
    for rid, q in queues.items():
        if not q["items"]:
            continue
        path = ROOT / "review" / "templates" / f"{rid}.csv"
        assert path.exists(), path
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
        assert [r["flag_id"] for r in rows] == [i["flag_id"] for i in q["items"]]


# ---------- library: price and labels ----------

def test_price_line_from_saved_runs():
    items = [{"pages_total": 1213, "full_run": {"cost_usd": 15.78}},
             {"pages_total": 372, "full_run": {"cost_usd": 2.404}},
             {"pages_total": 1, "full_run": None}]
    assert library.price_line(items) == ("Full audit: about $2.40 for ~370 pages to $16 for "
                                         "~1,200 pages (measured, 2 runs)")
    assert library.price_line(items, dollar="\\$").startswith("Full audit: about \\$2.40")
    assert library.price_line([]) is None


def test_upload_has_no_hard_coded_price():
    text = (ROOT / "tigerfish" / "ui" / "upload.py").read_text(encoding="utf-8")
    assert "$4-13" not in text and "FULL_AUDIT_RANGE" not in text


@pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(), reason="no results/")
def test_indira_point_is_a_single_table_check():
    e = library.find(library.entries(), "indira_point_table_3_16")
    assert e["audit_type"] == library.TABLE != library.FULL
    from tigerfish.ui import library as library_ui
    assert "1 table" in library_ui.meta_line(e)


@pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(), reason="no results/")
def test_library_home_shows_quality(monkeypatch):
    from apptest import open_app
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    at = open_app(report=None, page="library")
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    assert "#### Quality" in text and "RED/ORANGE flags" in text
    assert any(library.TABLE_NOTE in m.value for m in at.markdown)
    assert at.dataframe


@pytest.mark.skipif(not (ROOT / "results" / "index.json").exists(), reason="no results/")
def test_every_report_with_flags_has_its_review_queue(monkeypatch, tmp_path):
    from apptest import open_app
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("TIGERFISH_FEEDBACK", str(tmp_path / "feedback.json"))
    for e in library.entries():
        if e["audit_type"] == library.QUICK or not (e["grades"]["RED"] + e["grades"]["ORANGE"]):
            continue
        at = open_app(report=e["id"], timeout=120)
        assert not at.exception, e["id"]
        n = review.queue_for(library.load(e))["total"]
        text = "\n".join(m.value for m in at.markdown)
        assert f"#### Review queue: {e['title']} ({n} RED/ORANGE flags)" in text, e["id"]
        assert "**Team reviews (saved)**" in text and "Your reviews" in text
        assert not any(c.value == "No reviews saved yet." for c in at.caption)
