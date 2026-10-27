"""Free checks on an uploaded PDF: no model calls, no Tavily, so they always run.

1. Number pairs: sentences with a number + unit (claims.rule_claims) about a similar subject
   on different pages whose figures differ by more than 5% (contradictions.candidate_pairs,
   deterministic). They are not judged by a model, so they are shown as INFO leads to verify,
   never as RED or ORANGE.
2. Species: on pages that look like species tables (species_pages.is_species_page), Latin
   names confirmed by GBIF's name matcher, then species.check_species at the project site the
   visitor gives (free GBIF API). Without a site this check is skipped.
"""

from tigerfish import claims, contradictions, species, species_pages
from tigerfish.report import finding

MAX_PAIRS = 15            # number-pair leads shown per upload
MAX_SPECIES = 40          # names checked against GBIF per upload (each takes a few requests)


def number_pair_findings(pages, max_pairs=MAX_PAIRS):
    found = []
    for p in pages:
        if p.get("text"):
            found += claims.rule_claims(p["page"], p["text"], [])
    cands = [c for c in contradictions.candidate_pairs(found, max_candidates=10_000)
             if c["kind"] == "numeric" and not c.get("part_total")][:max_pairs]
    out = []
    for i, cand in enumerate(cands, 1):
        a, b = cand["claims"]
        out.append(finding(
            f"np-{i:03d}", "number_pair", "INFO",
            f"Pages {a['page']} and {b['page']}: {a['value']:g} vs {b['value']:g} {b['unit']}",
            "Similar subject, different figures. Not judged by a model: inconsistency possible, verify.",
            [{"page": a["page"], "text": a["quote"]}, {"page": b["page"], "text": b["quote"]}],
            [{"label": "Found by", "value": "a rule (number + unit, similar words before it); "
                                            "no model call, free"},
             {"label": "Subjects", "value": f"“{a['subject']}” / “{b['subject']}”"}],
            "The two sentences use similar words before the number but give figures that "
            "differ by more than 5%."))
    return out


def species_findings(pages, site, max_species=MAX_SPECIES, check=None):
    """RED/ORANGE species findings at site (lat, lon). check: species.check_species (tests)."""
    check = check or species.check_species
    lat, lon = site
    names = []
    for p in pages:
        if species_pages.is_species_page(p.get("text", "")):
            names += [(p["page"], n) for n in species_pages.candidate_names(p["text"])]
    seen, out = set(), []
    for page, name in names:
        if name in seen or len(seen) >= max_species:
            continue
        seen.add(name)
        if not species_pages.confirm(name):
            continue
        r = check(name, lat, lon)
        if r["grade"] not in ("RED", "ORANGE"):
            continue
        ev = [{"label": "Checked at", "value": f"project site given by the user ({lat}, {lon})"},
              {"label": "GBIF records of this species",
               "value": f"{r['local_count']} within 100 km, {r['regional_count']} within 500 km, "
                        f"{r['global_count']} worldwide"},
              {"label": "GBIF species page", "value": r["matched_name"],
               "url": (r.get("gbif_links") or {}).get("species")}]
        out.append(finding(f"sp-p{page}-{len(out) + 1:03d}", "species_range", r["grade"],
                           f"{name} (p.{page})", r["evidence"], [{"page": page, "text": name}],
                           ev, r["evidence"]))
    return out


def parse_site(text):
    """"6.83, 93.87" -> (6.83, 93.87); None if empty or not two valid coordinates."""
    parts = [x for x in str(text or "").replace(";", ",").split(",") if x.strip()]
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None
