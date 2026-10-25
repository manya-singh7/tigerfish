"""The "Method & limits" tab."""

import streamlit as st

from tigerfish import claims, contradictions, copycheck, species

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
(Protection) Act schedules are compared with the current schedule structure, read from official
sources (India Code, the Gazette, PRS, PIB, MoEFCC, Sansad) and quoted.

**Copied and borrowed text.** Distinctive, site-specific sentences are searched on the web with
Tavily. A match with a document about a different place is flagged. Long verbatim runs from
generic guidance without a citation are listed as INFO.

#### Grades

| Grade | Meaning |
|---|---|
| RED | Strong: the same subject, directly incompatible, and not explained in the report |
| ORANGE | Likely: worth checking, but the scope or the data is less certain |
| INFO | Not an inconsistency, e.g. borrowed text without a citation |
| GREY | Not enough data to judge. Never shown as a finding |

Every finding is phrased as something to verify. TigerFish does not say why a statement is
wrong, only that it does not agree with another statement or with public records.

#### Known limits

- **GBIF sampling gaps.** Absence of GBIF records does not prove absence of a species. Areas with
  fewer than {species.MIN_EFFORT} records of the same class within {species.LOCAL_KM} km count as
  too little surveyed (GREY), unless the wider {species.REGIONAL_KM} km region is surveyed
  ({species.MIN_REGIONAL_EFFORT} records) or the species has no records within
  {species.FAR_KM:,} km at all.
- **Taxonomy.** GBIF's synonyms can differ from current usage (for example, it maps *Pteropus
  giganteus* to *P. vampyrus*). Status differences after a name correction are graded GREY.
- **Hindi pages are skipped.** The text layer of the Hindi summary does not extract cleanly.
- **Models.** Models can misread tables or silently correct spelling; quotes are verified against
  the page, and table names keep the spelling the model read.
- **Thresholds.** Lower thresholds find more and flag more noise; higher ones miss weaker cases.
  Current values: contradiction difference {contradictions.MIN_DIFFERENCE:.0%}; quote match
  {claims.MIN_QUOTE_SIMILARITY:.0%}; borrowed text {copycheck.BORROWED_RUN}+ words; candidate cap
  {contradictions.MAX_CANDIDATES} per run.
- **Coverage.** The replay shows the pages audited so far, not the whole report.
"""


def render():
    st.markdown(METHOD)
