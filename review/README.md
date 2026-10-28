# Team reviews

The app shows these as "Team reviews (saved)", on the hosted app too. A visitor's own
reviews stay in their browser session and are never counted here.

- `review_queue.json`: Great Nicobar's full-audit flags in review order (top 30, then a
  random order), built by `scripts/build_review_queue.py`. Every other report's queue is
  built from its RED/ORANGE findings in `results/<report>.json`.
- `reviews.jsonl`: one line per decision (`report_id`, `flag_id`, `reviewer`, `decision`,
  `note`, `time`). Lines without `report_id` are Great Nicobar's.
- `templates/<report>.csv`: one row per RED/ORANGE flag (id, pages, check, one-line summary),
  with empty `verdict`, `reason`, `reviewer` and `date` columns.

## Adding hand checks

1. Copy a template, fill in the rows you checked against the PDF: `verdict` is `correct`,
   `wrong` or `unsure`; `date` is `YYYY-MM-DD`. Leave unchecked rows blank.
2. `python scripts/import_reviews.py my_checks.csv --dry-run`, then without `--dry-run`.
   Unknown reports or flag ids are rejected and nothing is written. Two reviewers' verdicts
   on the same flag are both kept (for reviewer agreement); if they differ the flag counts
   as disputed.
3. Regenerate the templates after a new export: `python scripts/import_reviews.py --templates`.

Precision is shown as a percentage only once 20 flags are judged, with a 95% Wilson interval.
