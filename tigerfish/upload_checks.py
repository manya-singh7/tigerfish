"""Checks on an uploaded EIA the app has never seen. Nothing here is per report: the site,
state and consultant come from tigerfish/detect.py (edited by the visitor if needed).

Free checks (no Nebius call, no Tavily credit; GBIF is free):
  number_pair     numbers + units about a similar subject that differ (rule, not judged)
  species_range   Latin names in the report's species tables vs GBIF records near the site
  iucn_status     IUCN categories in the report's tables vs GBIF's current category
  omission        threatened species recorded near the site that no page mentions
                  (only when the whole report was read: on part of a report, a species named
                  on a later page would be flagged wrongly)
All four read the whole report (its text layer); scanned pages without text need Super-VL
(paid) and are only counted.
Need a Nebius key (server key or the visitor's own):
  contradiction   claim extraction (Lightning / Super-VL) + contradiction check (Ultra)
Run locally only (need Tavily credits, the full report, or a second document):
  copy_paste, accreditation, legal_schedule, promise

run_free() returns (findings, statuses); every status says "ran", "not available for this
upload" (with the missing piece) or which key / setup it needs.
"""

from functools import partial

from tigerfish import free_checks, omissions, species, status_pages
from tigerfish.report import finding

RAN = "ran"
NOT_AVAILABLE = "not available for this upload"
FAILED = "failed"
NEEDS_KEY = "needs a Nebius key"
LOCAL_ONLY = "run locally"

FREE = [
    ("number_pair", "Number pairs: the same subject with different figures (rule, free)"),
    ("species_range", "Species in the report's tables vs GBIF records near the site (free)"),
    ("iucn_status", "IUCN categories in the report's tables vs GBIF (free)"),
    ("omission", "Threatened species recorded near the site but never mentioned (GBIF, free)"),
]
KEYED = [
    ("contradiction", "Internal contradictions and recycled figures (Nemotron Lightning reads "
                      "the claims, Nemotron Ultra judges each pair)"),
]
LOCAL = [
    ("copy_paste", "Copied text from documents about other places (Tavily web search + Lightning)",
     "uses Tavily web-search credits; run locally with a Tavily key"),
    ("accreditation", "Consultant's NABET accreditation at the report date (Lightning + Tavily)",
     "uses Tavily web-search credits; run locally with a Tavily key"),
    ("legal_schedule", "Wild Life (Protection) Act schedules in the report's tables (Tavily)",
     "the current schedule list is looked up with Tavily; run locally with a Tavily key"),
    ("promise", "Terms of Reference promises vs what the report did (Lightning + Ultra)",
     "needs the project's Terms of Reference as a second PDF; run locally"),
]
ANDAMAN_NICOBAR = "Andaman and Nicobar Islands"


def status(check, name, state, detail="", count=None):
    return {"check": check, "name": name, "status": state, "detail": detail, "count": count}


def state_gadm(state):
    """GBIF's GADM id for an Indian state (free GBIF lookup, cached), or None."""
    if not state:
        return None
    try:
        data = species.gbif_get("/geocode/gadm/search", gadmLevel=1, gadmGid="IND", q=state,
                                limit=3)
    except Exception:
        return None
    for r in data.get("results") or []:
        names = [r.get("name", "")] + list(r.get("variantName") or [])
        if any(n.lower().replace("&", "and") == state.lower() for n in names) \
                or state.lower().startswith(r.get("name", "~").lower()):
            return r["id"]
    return None


def species_check_fn(meta):
    """species.check_species with the island rule only for A&N sites and, when the site is
    only approximate (the midpoint of a stated range: a statewide or district-wide report),
    the statewide-list rule for the detected state."""
    state = meta.get("state")
    archipelago = species.ANDAMAN_NICOBAR_GADM if state == ANDAMAN_NICOBAR else None
    region = state_gadm(state) if meta.get("site_approximate") else None
    return partial(species.check_species, archipelago_gadm=archipelago, region_gadm=region,
                   region_label=state if region else None), region


def omission_findings(result, site_label):
    out = []
    n_pages, n_empty = result["pages_searched"], len(result["pages_without_text"])
    for i, r in enumerate([r for r in result["rows"] if r["grade"]], 1):
        latest = r["latest_year"] or "unknown"
        ev = [{"label": "GBIF records (IUCN " + r["category"] + ")",
               "value": f"{r['near']} within 10 km ({r['near_since_2000']} since 2000), "
                        f"{r['wide']} within 25 km; latest {latest}"},
              {"label": "Names searched for",
               "value": ", ".join(dict.fromkeys(s.split(": ", 1)[-1] for s in r["searched_for"]))},
              {"label": "Pages searched", "value": f"{n_pages - n_empty} of {n_pages} with usable text"},
              {"label": "GBIF map of these records", "value": r["name"], "url": r["map"]}]
        out.append(finding(f"om-{i:02d}", "omission", r["grade"],
                           f"{r['name']} (IUCN {r['category']}) not mentioned", r["message"],
                           [{"page": None, "where": "GBIF, near the site",
                             "text": f"{r['name']}: {r['wide']} record(s) within 25 km of "
                                     f"{site_label}, latest {latest}"}],
                           ev, f"GBIF has {r['wide']} record(s) of this IUCN {r['category']} "
                               f"species within 25 km of the site; no page of the report names it."))
    return out


def iucn_findings(result):
    """ORANGE IUCN results; one finding per name and printed category, citing every page."""
    groups = {}
    for r in result["results"]:
        if r.get("check") == "iucn" and r.get("grade") == "ORANGE":
            groups.setdefault((r["name"], str(r["report_value"])), []).append(r)
    out = []
    for (name, value), rs in groups.items():
        s, pages = rs[0], sorted({r["page"] for r in rs})
        where = ", ".join(f"p.{n}" for n in pages)
        out.append(finding(f"st-{len(out) + 1:02d}", "iucn_status", "ORANGE",
                           f"{name}: IUCN category {value} ({where})", s["message"],
                           [{"page": n, "text": name} for n in pages],
                           [{"label": "Report says", "value": value},
                            {"label": "Current", "value": str(s.get("current_value"))},
                            {"label": "GBIF / IUCN Red List", "value": s.get("gbif_name"),
                             "url": s.get("url")}],
                           s["evidence"]))
    return out


MAX_SPECIES = 150       # Latin names checked against GBIF per upload (whole report)
MAX_IUCN_NAMES = 300    # names in IUCN tables checked per upload
GBIF_WORKERS = 8        # parallel GBIF requests while prefetching (each still waits REQUEST_DELAY)


def table_names(pages):
    """Latin names on the species-table pages, in page order, each once. GBIF's name matcher
    confirms them later (free_checks.species_findings), so a few non-names may be here."""
    from tigerfish import species_pages
    names = []
    for p in pages:
        if species_pages.is_species_page(p.get("text", "")):
            names += species_pages.candidate_names(p["text"])
    return list(dict.fromkeys(names))


def free_status(pages, max_names=None):
    """IUCN categories of the rows in the report's IUCN tables (text layer), at most
    MAX_IUCN_NAMES distinct names, in page order. The GBIF answers are fetched GBIF_WORKERS at
    a time first (cached per URL); then status.check_table runs from the cache. No Tavily: the
    WPA schedule part only replays cached sources (a credit cap of 0).
    Returns status_pages.check_pages' shape plus "names" and "names_checked"."""
    from tigerfish import claims as claims_mod
    from tigerfish import copycheck, status
    from tigerfish.species_pages import _parallel
    max_names = max_names or MAX_IUCN_NAMES
    tables = status_pages.tables_from_pages(pages)
    all_names, kept = [], []
    for t in tables:
        col = claims_mod.name_column(t)
        rows = []
        for r in t["rows"]:
            n = claims_mod.normalize(r.get(col, "")) if col else ""
            if n and n not in all_names:
                all_names.append(n)
            if n and all_names.index(n) < max_names:
                rows.append(r)
        if rows:
            kept.append({**t, "rows": rows})
    _parallel(lambda n: status.iucn_current(n), all_names[:max_names], workers=GBIF_WORKERS)
    budget = copycheck.Budget(0)
    results = []
    for t in kept:
        got = status.check_table(t, budget)
        results += [{**r, "page": t["page"]} for r in got["results"]]
    return {"tables": [{"page": t["page"], "rows": len(t["rows"])} for t in tables],
            "results": results, "names": len(all_names),
            "names_checked": min(len(all_names), max_names)}


def scanned_pages(pages):
    """Pages a free check cannot read: no usable text layer."""
    return [p["page"] for p in pages if len((p.get("text") or "").strip()) < 50]


def run_free(pages, meta, species_fn=None, omission_fn=None, status_fn=None):
    """Every free check that can run on these pages with this metadata.

    meta: {"site": (lat, lon) | None, "site_approximate": bool, "site_label": str,
           "state": str | None, "pages_total": int}
    species_fn / omission_fn / status_fn: replacements for tests (no network).
    Returns (findings, statuses)."""
    found, out = [], []
    site, total = meta.get("site"), meta.get("pages_total") or len(pages)
    whole = len(pages) >= total
    names = dict(FREE)

    scanned = scanned_pages(pages)
    unread = (f"; {len(scanned)} scanned page(s) without a text layer are not read (reading "
              "them needs Super-VL, a paid model)") if scanned else ""
    pairs = free_checks.number_pair_findings(pages)
    found += pairs
    out.append(status("number_pair", names["number_pair"], RAN,
                      f"{len(pages) - len(scanned):,} of {len(pages):,} pages read (text layer){unread}", len(pairs)))

    if site:
        try:
            found += _species(pages, site, meta, species_fn, unread, names, out)
        except Exception as e:      # GBIF down: say so, keep the other checks
            out.append(status("species_range", names["species_range"], FAILED,
                              f"GBIF lookup failed ({type(e).__name__}); try again later"))
    else:
        out.append(status("species_range", names["species_range"], NOT_AVAILABLE,
                          "no project site: enter the site's latitude and longitude to run it"))
    _status_and_omission(pages, meta, site, whole, total, status_fn, omission_fn, names, found, out)
    return found, out


def _species(pages, site, meta, species_fn, unread, names, out):
    fn, region = (species_fn, None) if species_fn else species_check_fn(meta)
    listed = table_names(pages)
    if not species_fn:      # fetch the GBIF answers a few at a time first (cached per URL)
        from tigerfish.species_pages import _parallel
        done = _parallel(lambda n: fn(n, *site), listed[:MAX_SPECIES])
        fn = lambda name, lat, lon, _done=done, _fn=fn: _done.get(name) or _fn(name, lat, lon)
    sp = free_checks.species_findings(pages, site, max_species=MAX_SPECIES, check=fn)
    for f in sp:
        f["evidence"][0] = {"label": "Checked at",
                            "value": f"{meta.get('site_label') or 'site'} ({site[0]}, {site[1]}), "
                                     "detected from the report or entered by you"}
    detail = (f"{min(len(listed), MAX_SPECIES)} of {len(listed)} Latin names in the species "
              "tables checked" + (f" (at most {MAX_SPECIES} per upload)" if len(listed) > MAX_SPECIES
                                  else "") + unread)
    if region:
        detail += f"; a species with GBIF records anywhere in {meta.get('state')} is not flagged"
    out.append(status("species_range", names["species_range"], RAN, detail, len(sp)))
    return sp


def _status_and_omission(pages, meta, site, whole, total, status_fn, omission_fn, names, found, out):
    try:
        st = (status_fn or free_status)(pages)
        iu = iucn_findings(st)
        found += iu
        checked = (f"; {st['names_checked']} of {st['names']} names checked (at most "
                   f"{MAX_IUCN_NAMES} per upload)" if st.get("names", 0) > st.get("names_checked", 0)
                   else "")
        out.append(status("iucn_status", names["iucn_status"], RAN,
                          f"{len(st['tables'])} IUCN table(s) found in the text{checked}", len(iu)))
    except Exception as e:          # GBIF down: say so, keep the other checks
        out.append(status("iucn_status", names["iucn_status"], FAILED,
                          f"GBIF lookup failed ({type(e).__name__}); try again later"))

    if not site:
        out.append(status("omission", names["omission"], NOT_AVAILABLE,
                          "no project site: enter the site's latitude and longitude"))
    elif meta.get("site_approximate"):
        out.append(status("omission", names["omission"], NOT_AVAILABLE,
                          "the site is the midpoint of a stated range (a statewide or district-"
                          "wide report), not one project site; the check looks within 25 km of one site"))
    elif not whole:
        out.append(status("omission", names["omission"], NOT_AVAILABLE,
                          f"only {len(pages)} of {total} pages were read; a species named on a "
                          "later page would be flagged wrongly. Run locally on the full report"))
    else:
        try:
            res = (omission_fn or omissions.check)(pages, lat=site[0], lon=site[1])
        except Exception as e:      # GBIF down
            out.append(status("omission", names["omission"], FAILED,
                              f"GBIF lookup failed ({type(e).__name__}); try again later"))
            return
        om = omission_findings(res, meta.get("site_label") or "the site")
        found += om
        out.append(status("omission", names["omission"], RAN,
                          f"{len(res['rows'])} threatened species recorded near the site", len(om)))


def keyed_statuses(has_key, ran=False, cost_usd=None):
    """Statuses for the model checks and the local-only ones."""
    out = []
    for check, name in KEYED:
        if ran:
            out.append(status(check, name, RAN, f"cost ${cost_usd:.3f}" if cost_usd is not None else ""))
        elif has_key:
            out.append(status(check, name, "ready", "press “Run the model checks” to run it"))
        else:
            out.append(status(check, name, NEEDS_KEY, "add a Nebius key (yours, or the site's if set)"))
    out += [status(check, name, LOCAL_ONLY, why) for check, name, why in LOCAL]
    return out
