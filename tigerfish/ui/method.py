"""The "Method & limits" tab."""

import json
from pathlib import Path

import streamlit as st

from tigerfish import claims, contradictions, copycheck, promises, species
from tigerfish.ui import costs

LIMITATIONS_URL = "https://github.com/manya-singh7/tigerfish/blob/main/docs/LIMITATIONS.md"

METHOD = f"""
#### What TigerFish checks

**Claims.** Each page is read by NVIDIA Nemotron models on Nebius Token Factory: Lightning for
text pages, Super-VL for scanned pages and tables. Every quote is checked against the page text;
a quote that cannot be found on its page is never shown as evidence.

**Internal contradictions.** Figures and statements about the same subject on different pages are
paired by rule (compatible units, similar subject, values differing by more than
{contradictions.MIN_DIFFERENCE:.0%}), then Nemotron Ultra reads both full pages and decides whether
they are about the same thing, directly incompatible, and unexplained. A smaller figure for a
component is not treated as contradicting a larger total.

**Recycled figures.** The same figure with the same breakdown used for different places (for
example, one species count given for two national parks and the whole island).

**Species out of range.** Each species name is matched in the GBIF taxonomy (old names and
spelling mistakes are resolved and reported), then GBIF occurrence records are counted within
{species.LOCAL_KM} km and {species.REGIONAL_KM} km of the site and worldwide, together with how
well the area has been surveyed at all.

**Status.** IUCN Red List categories are compared with GBIF's current IUCN data. Wild Life
(Protection) Act schedules are compared with the current schedule structure, read from retrieved
sources and quoted: India Code and the Gazette first, then official sites (PIB, MoEFCC, Sansad)
and PRS Legislative Research, which is labelled authoritative but non-government.

**Copied and borrowed text.** Distinctive, site-specific sentences are searched on the web with
Tavily. A match with a document about a different place is flagged. Long verbatim runs from
generic guidance without a citation are listed as INFO.

**Terms of Reference promises.** Every measurable number in the project's Terms of Reference
(ToR) is found by regex (durations, numbers of sampling locations, depths, sampling frequency);
Nemotron Lightning says which are commitments and names the topic. The report is then searched
(BM25 over page texts, the same search the Investigate agent uses) and the matching numbers are
read by regex, only from sentences that name the topic and not from future monitoring plans.
Durations come from the dated field studies in the report (the survey timeline). Lightning
gives a first verdict; Nemotron Ultra re-reads the cited pages for possible shortfalls
(at most {promises.MAX_ULTRA} per report). ORANGE needs Ultra's confirmation and verified quotes
from both documents; a shortfall only the first pass saw, or a promise not found in the report
text, is INFO.

#### Grades

| Grade | Meaning |
|---|---|
| RED | Strong: the same subject, directly incompatible, and not explained in the report |
| ORANGE | Likely: worth checking, but the scope or the data is less certain |
| INFO | Not an inconsistency, e.g. borrowed text without a citation |
| GREY | Not enough data to judge, or a copied-text self-match (the matching document is this report's own: a paper-trail document, or an official or lender portal page naming the project; news pages are graded normally). Never shown as a finding; self-matches are listed under \"Excluded matches\" |

Every finding is phrased as something to verify. TigerFish does not say why a statement is
wrong, only that it does not agree with another statement or with public records.

#### Known limits

The full list of limitations and failure cases, with evidence from our own runs, is in
[docs/LIMITATIONS.md]({LIMITATIONS_URL}) (also shown below this section). Every flag is a lead
for human review, not a verdict.

- **GBIF sampling gaps.** Absence of GBIF records does not prove absence of a species. Areas with
  fewer than {species.MIN_EFFORT} records of the same class within {species.LOCAL_KM} km count as
  too little surveyed (GREY), unless the wider {species.REGIONAL_KM} km region is surveyed
  ({species.MIN_REGIONAL_EFFORT} records) or the species has no records within
  {species.FAR_KM:,} km at all.
- **GBIF coverage of the Nicobar Islands is sparse; for mobile species TigerFish only flags
  those absent from the whole region.** Birds, marine species and plants recorded anywhere
  in the Andaman & Nicobar Islands, or within {species.FAR_KM:,} km, are not flagged.
  Terrestrial mammals, amphibians and land reptiles keep the strict distance rules.
- **Consultant accreditation.** The consultant's NABET sectors and categories come from the
  official QCI/NABET list (quoted). That list may predate the report; when it states no
  validity date, status at the report date cannot be confirmed from it.
- **Omissions.** Threatened species recorded by GBIF near the site but never mentioned are
  listed. GBIF coverage is sparse, and a missing mention is a question for the reviewer, not
  proof of a gap in the assessment. Pages without usable text (scans) are not searched.
- **Taxonomy.** GBIF's synonyms can differ from current usage (for example, it maps *Pteropus
  giganteus* to *P. vampyrus*). Status differences after a name correction are graded GREY.
- **Hindi pages are skipped.** The text layer of the Hindi summary does not extract cleanly.
- **Models.** Models can misread tables or silently correct spelling; quotes are verified against
  the page, and table names keep the spelling the model read.
- **Terms of Reference.** Only the proposed ToR document is compared (data/eias); the ToR
  granted by MoEFCC (25 May 2021) may differ, and a committee can approve changes. A promise that
  says "3 months" for a list of attributes is read as applying to each; the timeline shows dates
  only where the report states them, so a study without stated dates has no bar. Regex can miss
  numbers written in tables split across pages. An ORANGE finding is a question for the reviewer,
  not a finding of non-compliance.
- **Thresholds.** Lower thresholds find more and flag more noise; higher ones miss weaker cases.
  Current values: contradiction difference {contradictions.MIN_DIFFERENCE:.0%}; quote match
  {claims.MIN_QUOTE_SIMILARITY:.0%}; borrowed text {copycheck.BORROWED_RUN}+ words; candidate cap
  {contradictions.MAX_CANDIDATES} per run.
- **Coverage.** The replay shows the pages audited so far, not the whole report.
"""


EVAL_FILE = Path(__file__).resolve().parents[2] / "results" / "eval.json"
LIMITATIONS_FILE = Path(__file__).resolve().parents[2] / "docs" / "LIMITATIONS.md"


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _eval():
    return json.loads(EVAL_FILE.read_text(encoding="utf-8")) if EVAL_FILE.exists() else None


def render_costs():
    """The cost card (cost per full audit by triage mode, and context efficiency)."""
    e = _eval()
    if e:
        costs.render(e)


def render_evaluation(with_costs=True):
    """The Evaluation section, from results/eval.json (written by scripts/evaluate.py)."""
    e = _eval()
    if not e:
        return
    k, s, t = e["known"], e["species"], e["table"]
    sc = e["planted"].get("score", {})
    x = e["cost"]["extrapolation"]
    neg_ok = all(r["ok"] for r in k["rows"] if r["id"] == "gn-neg-001")
    st.markdown("#### Evaluation")
    st.markdown(_table(["Test", "Result"], [
        ["Known issues in the Great Nicobar EIA", f"{k['passed']} of {k['scored']} scored issues found"],
        ["Negative control (explained 1045 vs 910 sq km)", "not flagged" if neg_ok else "flagged"],
        ["Planted contradictions", f"{sc.get('planted_caught')} of {sc.get('planted_total')} caught"],
        ["Planted differences the text explains",
         f"{sc.get('explained_wrongly_flagged')} of {sc.get('explained_total')} wrongly flagged"],
        ["Planted out-of-place species", f"{s['out_of_place_flagged']} of {s['out_of_place_total']} flagged"],
        ["Species recorded at the site", f"{s['real_wrongly_flagged']} of {s['real_total']} wrongly flagged"],
        ["Table 3.16, species judged plausible", f"{len(t['plausible'])} of 12 (Scroll.in: three)"],
    ]))
    st.markdown(
        f"**Full 1,213-page audit, estimated:** about ${x['usd']:.2f} (Rs {x['inr']:,} at "
        f"1 USD = 84 INR) and about {x['api_minutes_sequential']} minutes of model time if run "
        f"one call at a time. Estimate from the audited pages: `{x['formula']}`.")
    st.caption(f"Generated {e['generated']} by scripts/evaluate.py (seed {e['seed']}). "
               f"Full tables in results/eval.md.")
    if with_costs:
        costs.render(e)


def limitations_text():
    """docs/LIMITATIONS.md without its title line, or "" if the file is missing."""
    if not LIMITATIONS_FILE.exists():
        return ""
    lines = LIMITATIONS_FILE.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[1:] if lines and lines[0].startswith("# ") else lines).strip()


def render_limitations():
    text = limitations_text()
    if text:
        with st.expander("Known limitations and failure cases (docs/LIMITATIONS.md)"):
            st.markdown(text.replace("$", "\\$"))      # $ pairs would render as LaTeX


KNOWN_LIMITS = "#### Known limits"


def method_text():
    """What TigerFish checks and the grades (METHOD up to the known limits)."""
    return METHOD.split(KNOWN_LIMITS)[0]


def limits_text():
    """The known-limits list of METHOD (with its link to docs/LIMITATIONS.md)."""
    return KNOWN_LIMITS + METHOD.split(KNOWN_LIMITS, 1)[1]


def render():
    st.markdown(METHOD)
    render_limitations()
    render_evaluation()
