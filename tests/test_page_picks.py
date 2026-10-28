"""Choosing up to 30 pages for the deep audit: ranges, quick picks from headings, the default."""

from tigerfish import page_picks as pp


def page(no, text):
    return {"page": no, "text": text}


def report():
    pages = [page(1, "CONTENTS\nIntroduction ........ 3\nBaseline ........ 5\nImpacts ....... 8\n"
                     "Flora ........ 6\nFauna ....... 6\nMore ....... 9")]
    pages.append(page(2, "Draft EIA Report\nINTRODUCTION\nThe project is a port."))
    for n in range(3, 5):
        pages.append(page(n, "Draft EIA Report\nSome general text about the port."))
    pages.append(page(5, "Draft EIA Report\nCHAPTER 4: DESCRIPTION OF THE ENVIRONMENT\n"
                         "The site area is 45 ha. Rainfall is 3000 mm a year."))
    for n in range(6, 8):
        pages.append(page(n, "Draft EIA Report\nPanthera tigris and Elephas maximus were seen. "
                             "The forest covers 12 ha and the river is 3 km away."))
    pages.append(page(8, "Draft EIA Report\n5.1 Anticipated Impacts and Mitigation\n"
                         "Noise rises by 5 dB at 100 m."))
    pages.append(page(9, "Draft EIA Report\nNoise rises by 6 dB at 200 m."))
    return pages


def test_parse_range():
    assert pp.parse_range("2-4, 7", 10) == ([2, 3, 4, 7], None)
    assert pp.parse_range("4-2", 10) == ([2, 3, 4], None)
    assert pp.parse_range("1-11", 10)[1] == "pages must be between 1 and 10"
    assert "could not read" in pp.parse_range("abc", 10)[1]
    got, err = pp.parse_range("1-40", 50)
    assert len(got) == pp.MAX_PAGES and "first 30" in err


def test_headings_skip_contents_and_running_headers():
    heads = pp.headings(report())
    assert (5, "DESCRIPTION OF THE ENVIRONMENT") in heads
    assert (8, "Anticipated Impacts and Mitigation") in heads
    assert not [h for _, h in heads if h == "Draft EIA Report"]      # on every page
    assert not [n for n, _ in heads if n == 1]                       # contents page


def test_quick_picks_follow_the_report_headings():
    picks = {p["label"]: p for p in pp.quick_picks(report())}
    assert picks["Baseline"]["pages"] == [5, 6, 7]
    assert "DESCRIPTION OF THE ENVIRONMENT" in picks["Baseline"]["how"]
    assert picks["Impacts"]["pages"] == [8, 9]


def test_default_pick_prefers_figures_and_species():
    got = pp.default_pick(report(), limit=3)
    assert {6, 7} <= set(got)                      # species names weigh most
    assert not {1, 2, 3, 4} & set(got)             # no figures, no names


def test_fmt_pages():
    assert pp.fmt_pages([9, 3, 4, 5]) == "3-5, 9"
