# TigerFish agent notes

## Constraints worth preserving

- Read `docs/PROJECT_BRIEF.md` and the relevant block in `docs/TODO.md` before work; surface its outstanding reminders. Use Python **3.12** (`.python-version`, `pyproject.toml`).
- All model calls go through `tigerfish/llm.py`: Nebius Token Factory, NVIDIA Nemotron models. It loads the root `.env`; web-backed audit scripts also need `TAVILY_API_KEY`.
- Findings are neutral leads for human review: keep page numbers, exact quotes, evidence and grades. GREY means insufficient evidence, not a finding. PDF citations use **1-based physical pages**, not printed labels.
- `docs/TODO.md` freezes the Ultra verdict prompt in `tigerfish/contradictions.py`; preserve that evaluation baseline unless the task explicitly changes it. Grades are computed from structured answers, not the model's proposed grade.

## Local commands

Run from the repository root; uv manages `.venv`. This is a non-packaged app (`tool.uv.package = false`):

```sh
uv sync --locked
uv run --locked streamlit run app.py
```

`uv sync` includes `[dependency-groups].dev`; use `--no-dev` for runtime only. Edit dependencies via `uv add` / `uv add --dev`, commit `uv.lock`, and regenerate the hosting export with `uv export --locked --no-dev --no-hashes --no-emit-project --output-file requirements.txt` (do not hand-edit it).

```sh
# Offline suite, including Streamlit AppTest checks (~5 minutes; allow >5 minutes).
uv run --locked python -m pytest -q -m "not live" --ignore=tests/test_species_live.py
# Focused example: substitute the relevant file or node ID.
uv run --locked python -m pytest -q tests/test_claims.py::test_quote_verified_across_line_breaks
```

- Use `python -m pytest` so this non-packaged project's root is importable. Keep `--ignore`: `test_species_live.py` probes GBIF at import time even when `-m "not live"` deselects its tests. Live tests can spend API credits and require local PDFs/caches.
- Do not globally enable `TIGERFISH_MOCK` for the suite; tests configure their own mocks. `tests/conftest.py` isolates feedback via `TIGERFISH_FEEDBACK`.
- For app tests, use `tests/apptest.py:open_app`: the default opens Great Nicobar; `report=None` opens the library. Report routing uses `?report=<id>`; uploads use `?view=upload`.

## Execution and saved data

- `app.py` routes to `tigerfish/ui/`; `tigerfish/` owns audit logic, while `scripts/` orchestrates paid runs and exports. Replay uses committed `results/`, `review/` and `docs/`, without keys or source PDFs.
- `results/index.json` indexes replay reports. Keep library metadata in `results/library.json`: `scripts/export_results.py` rewrites the index. Exported image paths are relative to `results/`.
- Exports are **not** a harmless smoke check: `scripts/export_results.py` reruns pipelines and cache misses can make paid calls. `--only cuddalore` / `--only karnataka` preserve other reports.
- Source PDFs and the demo table image are intentionally untracked; see `data/eias/SOURCES.md`. Never stage `.env`, `.streamlit/secrets.toml`, `cache/`, `logs/`, `feedback/` or local source PDFs.
- Hosted visitor reviews stay in session state; committed team reviews must remain unchanged. See `tigerfish/hosted.py` and `docs/DEPLOY.md`; use `TIGERFISH_HOSTED=1` to exercise hosted behavior locally.

## Audit reproducibility

- Start with `uv run --locked python scripts/audit.py <pdf> --scope --dry-run`. A paid run requires `--run --max-cost <usd>`; `results/eval.json` supplies its estimates. `--cache-only` refuses uncached model calls.
- Preserve cached inputs and stable finding IDs. Resume with the same command; `--new-pages` adds newly extracted claims, while `--fresh` deliberately re-pairs and renumbers findings.
- Full-run contradiction results live under `cache/findings/<pdf-stem>/full_run/`; the ten-page evaluation can overwrite the ordinary `contradictions.jsonl` in the parent directory.
- Report-specific geography/applicability belongs in `tigerfish/sites.py`. When extending reports, also inspect downstream defaults (especially `copycheck.same_project`); a site profile alone does not configure every check.
- Human decisions and imports: `review/README.md`. Quick-check interchange format: `docs/REPORT_FORMAT.md`. Derive current coverage/costs from saved JSON and code: `docs/LIMITATIONS.md` and `docs/TODO.md` contain historical numbers.
