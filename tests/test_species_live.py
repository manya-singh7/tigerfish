"""Live GBIF check on real cases. Skip offline with:  pytest -m "not live"

Run with -s to see the results tables. Responses are cached in cache/gbif/,
so re-runs make no network calls.
"""

import pytest
import requests

from tigerfish import species

INDIRA_POINT = (6.75, 93.83)    # Great Nicobar
SATNA = (24.58, 80.83)          # Madhya Pradesh

# (site, name, lat, lon, expectation): "RED", "not RED", "not flagged", or None (just report)
CASES = [
    ("Indira Point", "Hydrocynus vittatus", *INDIRA_POINT, "RED"),
    ("Indira Point", "Semaprochilodus insignis", *INDIRA_POINT, "RED"),
    ("Indira Point", "Dermochelys coriacea", *INDIRA_POINT, "not RED"),
    ("Indira Point", "Rusa unicolor", *INDIRA_POINT, None),
    ("Indira Point", "Muntiacus muntjak", *INDIRA_POINT, None),
    ("Indira Point", "Scolopax rusticola", *INDIRA_POINT, None),
    ("Satna", "Nilgiritragus hylocrius", *SATNA, "RED"),
]

# Table 3.16 (mammals) of the Indira Point REIA, names exactly as printed.
TABLE_3_16 = [
    ("Axis axis", None),
    ("Cervus unicolor", None),          # old name of Rusa unicolor
    ("Crocidura hispida", None),
    ("Felis chaus", None),
    ("Funambulus pennantii", None),
    ("Macaca fascicularis", "not flagged"),
    ("Muntiacus muntjak", None),
    ("Paguma larvata", None),
    ("Pteropus giganteus", None),
    ("Rattus rattus", None),
    ("Sus scrofa andamanensis", None),
    ("Taupaia nicobarica", "not flagged"),   # typo for Tupaia nicobarica
]
TABLE_CASES = [("Indira Point", name, *INDIRA_POINT, expect) for name, expect in TABLE_3_16]


def gbif_reachable():
    try:
        requests.get(f"{species.API}/species/match?name=Puma", timeout=5)
        return True
    except requests.RequestException:
        return False


pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not gbif_reachable(), reason="GBIF not reachable (offline?)")]


def run(cases, title):
    out = {name: species.check_species(name, lat, lon) for _, name, lat, lon, _ in cases}
    print_table(cases, out, title)
    return out


@pytest.fixture(scope="module")
def results():
    return run(CASES, "Known cases")


@pytest.fixture(scope="module")
def table_results():
    return run(TABLE_CASES, "Indira Point REIA, Table 3.16 (mammals)")


def fmt(n):
    return "-" if n is None else f"{n:,}"


def print_table(cases, out, title):
    print(f"\n\n=== {title}")
    print(f"{'species (as written)':26} {'GBIF name':22} {'grade':6} {'local':>6} {'region':>7} "
          f"{'effort':>7} {'reg.eff':>8} {'far':>6} {'global':>8}  expect")
    for _, name, _, _, expect in cases:
        r = out[name]
        print(f"{name:26} {str(r['matched_name']):22} {str(r['grade']):6} "
              f"{fmt(r['local_count']):>6} {fmt(r['regional_count']):>7} "
              f"{fmt(r['effort_count']):>7} {fmt(r['regional_effort_count']):>8} "
              f"{fmt(r['far_count']):>6} {fmt(r['global_count']):>8}  {expect or '-'}")
    print()
    for _, name, *_ in cases:
        r = out[name]
        note = f"  [name: {r['name_note']}]" if r["name_note"] else ""
        print(f"- {name}: {r['evidence']}{note}")


def check(r, expect):
    if expect == "not RED":
        assert r["grade"] != "RED", r["evidence"]
    elif expect == "not flagged":
        assert r["grade"] in (None, "GREY"), r["evidence"]
    else:
        assert r["grade"] == expect, r["evidence"]


@pytest.mark.parametrize("name, expect", [(n, e) for _, n, _, _, e in CASES if e])
def test_expected_grades(results, name, expect):
    check(results[name], expect)


@pytest.mark.parametrize("name, expect", [(n, e) for n, e in TABLE_3_16 if e])
def test_table_3_16(table_results, name, expect):
    check(table_results[name], expect)


def test_table_3_16_names_resolved(table_results):
    assert table_results["Cervus unicolor"]["matched_name"] == "Rusa unicolor"
    assert table_results["Taupaia nicobarica"]["matched_name"] == "Tupaia nicobarica"
    assert table_results["Cervus unicolor"]["name_note"]
    assert table_results["Taupaia nicobarica"]["name_note"]
