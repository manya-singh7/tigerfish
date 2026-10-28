# Quick-check report format (`tigerfish-report/1`)

This is the format for the batch of quick checks: free checks only, about 90 EIAs. The app's
report library (home screen) reads it. One small JSON file per report goes under
`results/batch/`, plus one index file. Nothing else is needed: the library computes its
totals, filters and counts from these files.

Validator: `tigerfish.library.validate(report)` returns a list of problems (`[]` = valid).
Samples: `tests/fixtures/library/batch/` (made-up reports, used by the tests).

## Files

```
results/batch/index.json          the list of reports
results/batch/<id>.json           one report (keep each under 200 KB)
```

`<id>`: lowercase letters, digits and `_` only, e.g. `cuddalore_port_2026_draft`. Use the
same id in the index and in the report.

Do not put page images, PDFs or cached API responses under `results/batch/`. The hosted
app reads only `results/`, and the PDFs (`data/eias/*.pdf`) are never committed.

## `results/batch/index.json`

```json
{
  "format": "tigerfish-report/1",
  "generated": "2026-10-28T12:00:00",
  "tool_version": "<git commit of the batch run>",
  "reports": [
    {"id": "sample_quick_mine_odisha_2025", "file": "sample_quick_mine_odisha_2025.json"}
  ]
}
```

## `results/batch/<id>.json`

| Field | Type | Notes |
|---|---|---|
| `format` | string | always `"tigerfish-report/1"` |
| `id` | string | same as in the index |
| `audit_type` | string | always `"quick"` (free checks only) |
| `title` | string | short display name |
| `project` | string | project name as the report writes it (the library search uses it) |
| `state` | string or null | Indian state / UT, spelled as in `tigerfish.detect.STATES` |
| `sector` | string or null | one of `tigerfish.library.SECTORS` (below) |
| `year` | int or null | year on the report's cover |
| `consultant` | string or null | EIA consultant as named in the report |
| `source` | object | `{"url", "portal", "proposal_no"}`: where the PDF came from (e.g. PARIVESH) |
| `pages_total` | int | pages in the PDF |
| `pages_read` | int | pages the checks read (`<= pages_total`) |
| `site` | object or null | `{"lat", "lon", "how", "page", "quote"}` from `tigerfish.detect`, or null |
| `checks_run` | list | one entry per free check, **including the ones that did not run** (below) |
| `findings` | list | same shape as every other TigerFish finding (below) |
| `cost` | object | `{"nebius_usd": 0, "tavily_credits": 0, "gbif_calls": n, "approx_seconds": s}` |
| `generated` | string | ISO time of the run |
| `tool_version` | string | git commit |
| `human_reviewed` | object, optional | `{"reviewed": x, "of": y}` once anyone has reviewed flags |

Sectors: `Ports and harbours`, `Airports`, `Highways and roads`, `Railways`, `Mining`,
`Thermal power`, `Hydro power`, `River valley and irrigation`, `Industrial projects`,
`Infrastructure and townships`, `Nuclear`, `Other`.

### `checks_run`

Only the four free checks may appear (they need no Nebius key and no Tavily credit):

| `check` | What it is | Code |
|---|---|---|
| `number_pair` | same subject, different figures (rule; never judged by a model) | `free_checks.number_pair_findings` |
| `species_range` | Latin names in species tables vs GBIF near the site (up to 150 names; IUCN up to 300 names) | `free_checks.species_findings` |
| `iucn_status` | IUCN category in the report's tables vs GBIF today | `upload_checks.free_status` |
| `omission` | threatened species recorded near the site, never mentioned | `omissions.check` |

```json
{"check": "species_range", "name": "Species in the report's tables vs GBIF (free)",
 "status": "ran", "count": 1}
{"check": "omission", "name": "...", "status": "not_available",
 "reason": "no project site found in the report text"}
```

`status` is `"ran"`, `"not_available"` (a missing input: no site, part of the report only)
or `"failed"` (e.g. GBIF was down). Anything but `"ran"` needs a `reason`, which the app
shows to the reader. The easiest way to fill this list, the site and the findings is
`tigerfish.upload_checks.run_free(pages, meta)`, the same code the app runs on an upload. It
returns `(findings, statuses)`. Map its status `"ran"` to `"ran"`, anything else to
`"not_available"`, and its `detail` to `reason`.

Rules the validator enforces:
- every finding's `check` is listed in `checks_run` with status `"ran"`;
- `number_pair` findings are `INFO` only (no model judged them);
- grades are `RED`, `ORANGE` or `INFO`.

### A finding

The same shape as `tigerfish.report.finding()`:

```json
{"id": "np-001", "check": "number_pair", "check_name": "Number pair (not judged)",
 "grade": "INFO", "title": "Pages 12 and 88: 45 vs 54 ha",
 "message": "Similar subject, different figures. Not judged by a model: inconsistency possible, verify.",
 "quotes": [{"page": 12, "text": "..."}, {"page": 88, "text": "..."}],
 "evidence": [{"label": "Found by", "value": "...", "url": null}],
 "why": "...", "clear": "...", "known_issue": null, "images": []}
```

Keep `images` empty (no page images in the batch), quotes verbatim from the page, and the
wording neutral ("flagged, verify"; never "false" or "fraud").

## Suggested per-report steps

```python
from tigerfish import detect, pdf_reader, upload_checks
pages = pdf_reader.read_pdf(pdf, render=False)
facts = detect.detect(pages)                 # text search only: no key needed
site = (facts["site"] or {}).get("value")
meta = {"site": site, "site_approximate": "midpoint" in (facts["site"] or {}).get("how", ""),
        "site_label": "site detected from the report", "state": (facts["state"] or {}).get("value"),
        "pages_total": len(pages)}
findings, statuses = upload_checks.run_free(pages, meta)
```

Then check the result with `tigerfish.library.validate(report)`, write the file and add it to
the index. To see the batch in the app locally before committing, put the files in
`results/batch/`, or point `TIGERFISH_BATCH_DIR` at another folder.
