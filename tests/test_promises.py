"""Promises check (ToR vs EIA): date parsing, duration maths, location counting, depths,
verdicts and grading. Offline: no model calls (TIGERFISH_MOCK=1 for the one LLM path)."""

from datetime import date

import pytest

from tigerfish import promises as pr


def ranges(text, year=None):
    return [(r["start"], r["end"]) for r in pr.parse_date_ranges(text, year)]


# ---------- date ranges ----------

@pytest.mark.parametrize("text, start, end", [
    ("winter season (1st December 2020 to 28th February 2021) of", date(2020, 12, 1), date(2021, 2, 28)),
    ("Study period (December 2020 to February 2021)", date(2020, 12, 1), date(2021, 2, 28)),
    ("Study Period (December 2020 – February 2021)", date(2020, 12, 1), date(2021, 2, 28)),
    ("during January 2021 and February 2021 of the", date(2021, 1, 1), date(2021, 2, 28)),
    ("sampled 15.12.2020 - 22.12.2020 at", date(2020, 12, 15), date(2020, 12, 22)),
    ("sampled 15/12/20 to 22/12/20 at", date(2020, 12, 15), date(2020, 12, 22)),
    ("during December 2020 (14 to 22 December 2020).", date(2020, 12, 14), date(2020, 12, 22)),
    ("carried out from 14th to 19th April, 2021 to", date(2021, 4, 14), date(2021, 4, 19)),
    ("nests on 15-16 April, 2021.", date(2021, 4, 15), date(2021, 4, 16)),
    ("On 15th and 16th April, 2021, the beach", date(2021, 4, 15), date(2021, 4, 16)),
    ("from 5th March 2021 to 29th March 2021.", date(2021, 3, 5), date(2021, 3, 29)),
    ("conducted during February-March 2021.", date(2021, 2, 1), date(2021, 3, 31)),
    ("from Dec. 2020 to Feb. 2021", date(2020, 12, 1), date(2021, 2, 28)),
    ("from 4th Sept 2020 to 2nd Oct 2020", date(2020, 9, 4), date(2020, 10, 2)),
    ("the baseline study was conducted during March 2021.", date(2021, 3, 1), date(2021, 3, 31)),
])
def test_date_range_formats(text, start, end):
    assert (start, end) in ranges(text)


def test_day_month_without_year_uses_default_year():
    assert ranges("from 4th to 11th January", 2021) == [(date(2021, 1, 4), date(2021, 1, 11))]
    assert ranges("from 4th to 11th January") == []          # no year known: skipped


def test_range_across_new_year_puts_start_in_previous_year():
    assert ranges("from 14 December to 2 January 2021") == [(date(2020, 12, 14), date(2021, 1, 2))]
    assert ranges("December to February 2021") == [(date(2020, 12, 1), date(2021, 2, 28))]


def test_overlapping_patterns_do_not_double_count():
    found = pr.parse_date_ranges("winter season (1st December 2020 to 28th February 2021)")
    assert len(found) == 1 and found[0]["days"] == 90


def test_invalid_or_reversed_dates_are_ignored():
    assert ranges("31.02.2021 - 05.03.2021") == []
    assert ranges("22.12.2020 - 15.12.2020") == []
    assert ranges("between 1986 and 2012") == []


# ---------- durations ----------

def test_duration_maths():
    assert pr.days_between(date(2020, 12, 1), date(2021, 2, 28)) == 90
    assert pr.days_between(date(2020, 12, 14), date(2020, 12, 22)) == 9      # inclusive
    assert pr.days_between(date(2021, 4, 15), date(2021, 4, 15)) == 1
    assert pr.months(90) == 3.0
    assert pr.days_between(date(2024, 2, 1), date(2024, 2, 29)) == 29        # leap year


@pytest.mark.parametrize("text, days", [
    ("for a period of three months", 90), ("3 months", 90), ("8 days", 8),
    ("for four days", 4), ("two weeks", 14), ("one year", 365), ("a month", 30),
])
def test_parse_durations(text, days):
    assert pr.parse_durations(text)[0][0] == days


# ---------- locations, depths, frequency ----------

@pytest.mark.parametrize("text, count", [
    ("Water samples were collected from sixteen locations.", 16),
    ("noise levels at twenty locations during", 20),
    ("20 locations within study area were selected", 20),
    ("A total of 10 numbers of samples were collected", 10),
    ("collected from 6 appropriate locations within", 6),
    ("Eight ground water sources were examined", 8),
    ("at 6 monitoring stations", 6),
    ("Location UOM S11 S12 S13 S14 S15 S16 S17 S18 S19 S20 1 pH", 20),
    ("Station Code AAQ1 AAQ2 AAQ3 AAQ4 AAQ5 AAQ6", 6),
])
def test_count_locations(text, count):
    assert count in [n for n, _ in pr.count_locations(text)]


def test_non_consecutive_codes_and_chemicals_are_not_stations():
    assert pr.count_locations("PM10 PM2.5 SO2 NO2 O3") == []
    assert pr.count_locations("S1 S5 S9 results") == []
    assert pr.count_locations("for 3 months at a single location") == []


@pytest.mark.parametrize("text, metres", [
    ("up to a depth of about 40 m through", 40), ("deeper reef-16-30m (English", 30),
    ("up to a depth of 90 cm and", 0.9), ("deployed at a depth of 3-5 meter", 5),
])
def test_parse_depths(text, metres):
    assert pr.parse_depths(text)[0][0] == metres


def test_depth_needs_depth_context():
    assert pr.parse_depths("a road 40 m wide") == []


@pytest.mark.parametrize("text, n", [
    ("twice a week for three months", 2), ("two days per week at each location", 2),
    ("twice in a week for 24 hours", 2), ("once a week", 1), ("3 times a week", 3),
])
def test_parse_frequency(text, n):
    assert pr.parse_frequency(text)[0][0] == n


@pytest.mark.parametrize("kind, measure, value", [
    ("duration", "3 months", 90), ("duration", "three months", 90),
    ("locations", "20 locations", 20), ("locations", "6", 6), ("locations", "twenty", 20),
    ("depth", "40 m", 40), ("depth", "90 cm", 0.9), ("frequency", "twice a week", 2),
    ("duration", "a season", None), ("other", "20", None),
])
def test_parse_measure(kind, measure, value):
    assert pr.parse_measure(kind, measure) == value


# ---------- verdicts and grading ----------

@pytest.mark.parametrize("promised, found, verdict", [
    (90, 90, "met"), (90, 82, "met"), (20, 20, "met"), (20, 24, "met"),
    (20, 16, "partly met"), (40, 30, "partly met"),
    (90, 9, "not met"), (20, 8, "not met"), (0.9, 0.3, "not met"),
    (20, None, "not found"),
])
def test_compare(promised, found, verdict):
    assert pr.compare(promised, found) == verdict


@pytest.mark.parametrize("verdict, tor_ok, eia_ok, grade", [
    ("met", True, True, "NONE"),
    ("partly met", True, True, "ORANGE"),
    ("not met", True, True, "ORANGE"),
    ("not met", True, False, "INFO"),         # no verified report quote: not shown as ORANGE
    ("not met", False, True, "INFO"),
    ("not found", True, False, "INFO"),
])
def test_grade(verdict, tor_ok, eia_ok, grade):
    assert pr.grade(verdict, tor_ok, eia_ok) == grade


def test_message_is_neutral_and_cites_both_documents():
    msg = pr.message({"commitment": "collect water samples at 20 locations", "page": 3,
                      "report_describes": "water samples from sixteen locations", "eia_page": 279})
    assert msg == ("The ToR commits to collect water samples at 20 locations (ToR p.3); the report "
                   "describes water samples from sixteen locations (EIA p.279). Verify.")
    assert not any(w in msg.lower() for w in ("lie", "false", "fake", "fraud", "violat"))


# ---------- evidence and timeline (no model) ----------

def test_single_value_needs_no_model(monkeypatch):
    monkeypatch.setenv("TIGERFISH_MOCK", "1")
    cand = [{"page": 279, "value": 16, "quote": "collected from sixteen locations", "hit": "sixteen locations"}]
    assert pr.choose({}, cand) == (cand[0], "regex")
    assert pr.choose({}, []) == (None, "none")


def test_sentences_keep_titles_together():
    s = pr.sentences("Survey by Prof. K.B Reddy during 14 to 22 December 2020. Next one.")
    assert s[0] == "Survey by Prof. K.B Reddy during 14 to 22 December 2020."


def test_timeline_bars_window_and_context_labels():
    pages = [
        {"page": 44, "text": "Baseline environmental monitoring has been carried out in winter "
                             "season (1st December 2020 to 28th February 2021) of the study area."},
        {"page": 292, "text": "Quick primary survey of the Ecology and biodiversity was carried out "
                              "during December 2020 (14 to 22 December 2020). Primary survey of "
                              "Leatherback Turtles was done by Mr. Ravinder during 12 to 18 February 2021."},
        {"page": 985, "text": "The intertidal and marine surveys were conducted from Campbell Bay. "
                              "The baseline study was conducted during March 2021."},
        {"page": 367, "text": "The health data from January 2020 to December 2020 is given in Annexure-IX."},
    ]
    window, bars = pr.timeline(pages)
    assert (window["start"], window["end"], window["days"], window["page"]) == ("2020-12-01", "2021-02-28", 90, 44)
    got = {(b["study"], b["start"], b["end"], b["page"]) for b in bars}
    assert got == {("Flora & fauna (ecology)", "2020-12-14", "2020-12-22", 292),
                   ("Turtles", "2021-02-12", "2021-02-18", 292),
                   ("Marine sampling (ZSI)", "2021-03-01", "2021-03-31", 985)}
    assert all(b["url"].endswith(f"#page={b['page']}") for b in bars)


@pytest.mark.parametrize("text", [
    "monitored at 6 locations twice a week for", "a frequency of two days per week at each",
    "a) Primary productivity, mg C/m3 day", "twice in a week for 24 hours",
])
def test_frequencies_and_units_are_not_durations(text):
    assert pr.parse_durations(text) == []


def test_tor_items_one_per_value():
    tor = [{"page": 3, "text": "The baseline air quality will be monitored at 6 locations twice a "
                               "week for three months during one non-monsoon season."}]
    got = {(it["kind"], it["value"]) for it in pr.tor_items(tor)}
    assert got == {("locations", 6), ("frequency", 2), ("duration", 90)}


@pytest.mark.parametrize("topic, sentence, ok", [
    ("marine ecology", "Water samples were collected from sixteen locations.", False),
    ("marine ecology", "Marine water samples were collected at 9 stations.", True),
    ("soil", "A total of 10 numbers of samples were collected.", False),
])
def test_evidence_sentence_must_name_the_topic(topic, sentence, ok):
    assert pr.on_topic(topic, sentence) is ok


def test_soil_context_from_previous_sentence():
    assert pr.on_topic("soil", "A total of 10 numbers of samples were collected.",
                       "The samples were collected by ramming a core-cutter into the soil.")


def test_shortfall_only_seen_by_first_pass_is_info():
    assert pr.grade("not met", True, True, confirmed=False) == "INFO"
    assert pr.grade("not met", True, True, confirmed=True) == "ORANGE"
    assert pr.grade("met", True, True, confirmed=False) == "NONE"


@pytest.mark.parametrize("rule, first, ultra, expected", [
    ("not met", "met", "not met", ("not met", "ultra")),          # Ultra decides when it ran
    ("met", "partly met", None, ("met", "regex")),                # report's own number meets it
    ("not found", "not met", None, ("not met", "lightning")),     # stays a first-pass verdict (INFO)
    ("partly met", None, None, ("partly met", "regex")),
    ("met", "garbage", None, ("met", "regex")),
])
def test_resolve_verdict(rule, first, ultra, expected):
    assert pr.resolve(rule, first, ultra) == expected


def test_saved_results_build_table_and_chart():
    from tigerfish.ui import promises as ui
    data = ui.load("great_nicobar_2021_draft")
    if data is None:
        pytest.skip("no results/great_nicobar_2021_draft_promises.json (run scripts/check_promises.py)")
    rows = ui.table_rows(data)
    assert rows and rows[0]["Grade"] == "ORANGE"
    spec = ui.chart(data).to_dict()
    assert len(spec["layer"]) == 3                       # window band, its label, the bars
    assert all(b["url"].endswith(f"#page={b['page']}") for b in data["timeline"])
