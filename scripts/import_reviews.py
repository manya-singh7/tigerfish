"""Import hand checks from a CSV into the committed review file the app reads, so team
reviews show up on the hosted app.

Usage: python scripts/import_reviews.py <file.csv> [--dry-run] [--skip-invalid]
       python scripts/import_reviews.py --templates     (blank CSVs, one per report)

CSV columns: report, flag_id, pages, verdict, reason, reviewer, date
  report    the report id (e.g. great_nicobar_2021_draft) or its title in the library
  flag_id   a flag in that report's review queue (the queue id, or the app finding id)
  pages     the pages you checked, e.g. "738, 1085" (a mismatch with the flag is a warning)
  verdict   correct | wrong | unsure  (a blank verdict is skipped: not reviewed yet)
  reason    why, in a line (saved as the note)
  reviewer  your name (required)
  date      YYYY-MM-DD
Other columns (the templates' check and summary) are ignored.

Writes review/reviews.jsonl (one row per decision; tigerfish/review.py). Rules:
  - unknown reports or flag ids, bad verdicts or dates, and missing names are rejected; with
    any rejected row nothing is written, unless --skip-invalid
  - a different reviewer's verdict is never overwritten: both are kept (reviewer agreement)
  - the same reviewer's newer verdict on a flag is added after the old one and counts; an
    identical one is skipped, an older one is not imported
No API calls.
"""

import argparse
import csv
import io
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tigerfish import library, review  # noqa: E402

VERDICTS = {"correct": "real", "wrong": "false_alarm", "unsure": "unsure"}
COLUMNS = ["report", "flag_id", "pages", "verdict", "reason", "reviewer", "date"]
TEMPLATE_COLUMNS = ["report", "flag_id", "pages", "check", "summary", "verdict", "reason",
                    "reviewer", "date"]


def reports(results=None):
    """{report id: queue}, and {lower-case id or title: report id}."""
    queues, names = {}, {}
    for e in library.entries(results):
        try:
            rep = library.load(e)
        except (OSError, ValueError):
            continue
        queues[e["id"]] = review.queue_for(rep)
        for n in (e["id"], e["title"], e["project"]):
            names[" ".join(str(n).split()).lower()] = e["id"]
    return queues, names


def parse_date(text):
    text = (text or "").strip()
    try:
        return date.fromisoformat(text[:10]).isoformat() if re.match(r"^\d{4}-\d{2}-\d{2}", text) else None
    except ValueError:
        return None


def pages_of(text):
    return sorted({int(n) for n in re.findall(r"\d+", str(text or ""))})


def check_rows(rows, queues, names):
    """(valid decision rows, rejected [(line, why)], warnings [(line, text)], blank count)."""
    valid, rejected, warnings, blank = [], [], [], 0
    for line, r in rows:
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        if not r.get("verdict"):
            blank += 1
            continue
        rid = names.get(" ".join(r.get("report", "").split()).lower())
        if not rid:
            rejected.append((line, f"unknown report {r.get('report')!r}"))
            continue
        ids = review.flag_ids(queues[rid])
        flag = ids.get(r.get("flag_id", ""))
        if not flag:
            rejected.append((line, f"unknown flag id {r.get('flag_id')!r} in {rid}"))
            continue
        decision = VERDICTS.get(r["verdict"].lower())
        if not decision:
            rejected.append((line, f"verdict must be correct, wrong or unsure (got {r['verdict']!r})"))
            continue
        reviewer = " ".join(r.get("reviewer", "").split())
        if not reviewer:
            rejected.append((line, "reviewer is required"))
            continue
        day = parse_date(r.get("date"))
        if not day:
            rejected.append((line, f"date must be YYYY-MM-DD (got {r.get('date')!r})"))
            continue
        item = next(i for i in queues[rid]["items"] if i["flag_id"] == flag)
        pages = pages_of(r.get("pages"))
        if pages and item.get("pages") and not set(pages) & set(item["pages"]):
            warnings.append((line, f"{flag}: pages {pages} do not match the flag's pages {item['pages']}"))
        valid.append({"report_id": rid, "flag_id": flag, "reviewer": reviewer,
                      "decision": decision, "note": r.get("reason", ""),
                      "time": f"{day}T00:00:00", "pages": pages or item.get("pages") or [],
                      "source": "csv"})
    return valid, rejected, warnings, blank


def merge(existing, incoming):
    """(rows to append, counts). Keyed by report, flag and reviewer: other reviewers' rows are
    never touched; the same reviewer's identical verdict is skipped, an older one ignored."""
    latest = {}
    for r in existing:
        latest[(review.row_report(r), r["flag_id"], review.name_key(r["reviewer"]))] = r
    add, counts = [], {"added": 0, "updated": 0, "unchanged": 0, "older": 0}
    for r in incoming:
        key = (r["report_id"], r["flag_id"], review.name_key(r["reviewer"]))
        old = latest.get(key)
        if old and (old["decision"], old.get("note", "")) == (r["decision"], r["note"]):
            counts["unchanged"] += 1
            continue
        if old and old["time"] > r["time"]:
            counts["older"] += 1
            continue
        counts["updated" if old else "added"] += 1
        latest[key] = r
        add.append(r)
    return add, counts


def read_csv(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in COLUMNS if c not in [h.strip().lower() for h in reader.fieldnames or []]]
    if missing:
        sys.exit(f"{path}: missing column(s) {', '.join(missing)}")
    return [(n, r) for n, r in enumerate(reader, 2)]       # line 1 is the header


def import_csv(path, out=None, dry_run=False, skip_invalid=False, results=None):
    out = Path(out or review.REVIEWS)
    queues, names = reports(results)
    valid, rejected, warnings, blank = check_rows(read_csv(path), queues, names)
    for line, why in rejected:
        print(f"REJECTED line {line}: {why}")
    for line, text in warnings:
        print(f"warning line {line}: {text}")
    add, counts = merge(review.load_rows(out), valid)
    print(f"{len(valid)} valid, {len(rejected)} rejected, {blank} blank (not reviewed yet); "
          + ", ".join(f"{v} {k}" for k, v in counts.items()))
    if rejected and not skip_invalid:
        print("Nothing written: fix the rejected rows or pass --skip-invalid.")
        return 1
    if dry_run or not add:
        print("Nothing written" + (" (dry run)." if dry_run else ": no new verdicts."))
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(review.rows_jsonl(add))
    print(f"Wrote {len(add)} row(s) to {out}")
    return 0


def write_templates(folder=None, results=None):
    folder = Path(folder or review.TEMPLATES)
    folder.mkdir(parents=True, exist_ok=True)
    queues, _ = reports(results)
    written = []
    for rid, q in queues.items():
        if not q["items"]:
            print(f"{rid}: no RED/ORANGE flags, no template")
            continue
        path = folder / f"{rid}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(TEMPLATE_COLUMNS)
            for it in q["items"]:
                w.writerow([rid, it["flag_id"], ", ".join(map(str, it.get("pages") or [])),
                            it.get("check_name") or it.get("check"), review.summary(it),
                            "", "", "", ""])
        written.append(path)
        print(f"Wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: "
              f"{len(q['items'])} flags")
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("csv", nargs="?")
    parser.add_argument("--templates", action="store_true", help="write blank CSVs, one per report")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-invalid", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.templates:
        write_templates()
        return 0
    if not args.csv:
        parser.error("give a CSV file, or --templates")
    return import_csv(args.csv, dry_run=args.dry_run, skip_invalid=args.skip_invalid)


if __name__ == "__main__":
    sys.exit(main())
