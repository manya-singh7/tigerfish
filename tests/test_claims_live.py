"""Live claim-extraction checks (Nebius + GBIF). Skip offline with:  pytest -m "not live"

Run with -s to see the reports. All model replies are cached in cache/llm/, so
after the first run these tests cost nothing. Uncached, the two tests together
cost about $0.01.
"""

import difflib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import demo_table  # noqa: E402
from tigerfish import claims, pdf_reader  # noqa: E402

IMAGE = ROOT / "data" / "demo" / "indira_point_table_3_16_mammals.png"
PDF = ROOT / "data" / "eias" / "great_nicobar_2021_draft_eia.pdf"
KNOWN = json.loads((ROOT / "data" / "known_issues.json").read_text(encoding="utf-8"))
KNOWN_PAGES = [234, 392, 444, 751, 818, 851, 940, 978, 1141, 1168]

# Zoological names exactly as printed in Table 3.16 (including the report's typo).
TABLE_3_16_NAMES = [
    "Axis axis", "Cervus unicolor", "Crocidura hispida", "Felis chaus",
    "Funambulus pennantii", "Macaca fascicularis", "Muntiacus muntjak", "Paguma larvata",
    "Pteropus giganteus", "Rattus rattus", "Sus scrofa andamanensis",
    "Taupaia nicobarica nicobarica",
]
MIN_NAME_SIMILARITY = 0.85   # "Tupaia nicobarica nicobarica" still counts as "Taupaia ..."

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("NEBIUS_API_KEY") and not (ROOT / ".env").exists(),
                       reason="no Nebius key"),
]


def similar(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


@pytest.mark.skipif(not IMAGE.exists(), reason="demo image not present (kept locally)")
def test_demo_table_reads_all_12_names():
    table, results = demo_table.run(str(IMAGE), 6.75, 93.83)
    assert table is not None, "Super-VL returned no readable table"
    read = [c["value"] for c, _ in results]

    print("\n\nTable 3.16 names: printed -> read by Super-VL -> GBIF grade")
    missing = []
    for name in TABLE_3_16_NAMES:
        best = max(read, key=lambda r: similar(r, name), default="")
        ok = similar(best, name) >= MIN_NAME_SIMILARITY
        grade = next((r["grade"] for c, r in results if c["value"] == best), None) if ok else "-"
        exact = "" if best == name else "  (spelling differs from print)"
        print(f"  {name:32} -> {best if ok else 'MISSING':32} {str(grade):6}{exact}")
        if not ok:
            missing.append(name)
    assert not missing, f"not extracted: {missing}"
    assert len(read) == 12, f"expected 12 rows, got {len(read)}: {read}"


def captured(known_quote, page_claims):
    """Best claim for a known-issue quote: (claim, how) or (None, None).

    'exact' = same quote, 'contains' = one quote contains the other,
    'overlap' = the claim quote shares most words with the known quote.
    """
    kq = claims.normalize(known_quote).lower()
    words = set(kq.split())
    best, how, best_score = None, None, 0.0
    for c in page_claims:
        cq = claims.normalize(c["quote"]).lower()
        if not cq:
            continue
        if cq == kq:
            return c, "exact"
        coverage = len(words & set(cq.split())) / len(words)   # share of known words covered
        if cq in kq or kq in cq:
            score, kind = 1 + coverage, "contains"
        elif coverage >= 0.6:
            score, kind = coverage, "overlap"
        else:
            continue
        if score > best_score:
            best, how, best_score = c, kind, score
    return best, how


@pytest.mark.skipif(not PDF.exists(), reason="EIA PDF not present (kept locally)")
def test_report_known_issue_quotes_captured():
    """Report only: which known_issues.json quotes became claims. No assertions on coverage."""
    pages = [p for p in pdf_reader.read_pdf(PDF) if p["page"] in KNOWN_PAGES]
    found = claims.extract_claims(pages, pdf_stem=PDF.stem)

    print("\n\nKnown-issue quotes captured as claims (pages", KNOWN_PAGES, ")")
    total = hit = 0
    for issue in KNOWN["issues"]:
        for q in issue["quotes"]:
            total += 1
            if q["page"] not in KNOWN_PAGES:
                print(f"  {issue['id']:11} p.{q['page']:<5} NOT RUN (page not in KNOWN_PAGES)")
                continue
            c, how = captured(q["text"], [c for c in found if c["page"] == q["page"]])
            hit += c is not None
            status = (f"{how:8} verified={c['verified']}  {c['type']}={c['value']!r}"
                      if c else "MISSED")
            print(f"  {issue['id']:11} p.{q['page']:<5} {status}")
            if c is None:
                print(f"{'':20}known: {q['text'][:100]}")
    stats = claims.verified_stats(found)
    print(f"\nCaptured {hit}/{total} known quotes. Claims: {stats['claims']}, "
          f"verified quotes: {stats['verified']} ({stats['verified_rate']:.0%})")
