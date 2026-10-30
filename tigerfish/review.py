"""Human review of the full audit's RED/ORANGE flags: the queue, decisions, precision.

review/review_queue.json   built by scripts/build_review_queue.py: every new RED/ORANGE flag
                           of the full run, in review order (top 30 first, then a seeded
                           random order); some flags are marked double_review
review/reviews.jsonl       one line per decision: {report_id, flag_id, reviewer, decision, note,
                           time}; a reviewer's latest line for a flag is the one that counts.
                           Lines without report_id (written before reviews carried one) belong
                           to LEGACY_REPORT. scripts/import_reviews.py adds hand checks from a CSV.

Every report has a queue (queue_for): Great Nicobar's is the file above (its full-audit flags
in review order) plus its other RED/ORANGE findings; any other report's is its RED/ORANGE
findings in grade order, built from results/<report>.json.

A flag's verdict:
  single review: the decision; "disputed" if two people decided differently
  double review: both reviewers' decisions (judged independently); the verdict is theirs
                 when they agree, "disputed" when they do not, "waiting" until two reviewers
                 have decided
Precision = real / (real + false alarm) over flags with a verdict; "unsure" and disputed
flags are left out (and counted).

A queue item with "verified" was checked by hand against the PDF (data/known_issues.json): it
counts as that person's decision ("real", i.e. Confirm) and needs no further review. For a
double-review flag the hand check is the verdict, unless another reviewer disagrees
("disputed"). A later decision by the same person in reviews.jsonl replaces it.
"""

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = ROOT / "review"
QUEUE = REVIEW_DIR / "review_queue.json"
REVIEWS = REVIEW_DIR / "reviews.jsonl"
TEMPLATES = REVIEW_DIR / "templates"
LEGACY_REPORT = "great_nicobar_2021_draft"      # owner of rows without a report_id
FLAG_GRADES = ("RED", "ORANGE")

DECISIONS = {"real": "Confirm (real issue)", "false_alarm": "Dismiss (false alarm)",
             "unsure": "Unsure"}
AS_FEEDBACK = {"real": "Confirm", "false_alarm": "Dismiss", "unsure": "Unsure"}  # card wording


def load_queue(path=None):
    path = Path(path or QUEUE)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_rows(path=None):
    """Every decision row in the file, in file order ([] if there is no file)."""
    p = Path(path or REVIEWS)
    if not p.exists():
        return []
    return [normalized(json.loads(line))
            for line in p.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def normalized(row):
    """A row with the schema's note and time keys. Hand-written lines may say "comment" and
    "reviewed_at" instead; the file is left as written."""
    row = dict(row)
    row.setdefault("note", row.pop("comment", "") or "")
    row.setdefault("time", row.pop("reviewed_at", "") or "")
    return row


def row_report(row):
    return row.get("report_id") or LEGACY_REPORT


def load_reviews(path=None, report_id=None):
    """{flag_id: {reviewer: latest decision row}}, for one report if report_id is given."""
    rows = load_rows(path)
    if report_id:
        rows = [r for r in rows if row_report(r) == report_id]
    return with_rows({}, rows)


def with_rows(reviews, rows):
    """A copy of reviews ({flag_id: {reviewer: row}}) with these decision rows added on top
    (a later row by the same reviewer replaces theirs). The hosted app adds the visitor's
    session decisions this way; the committed ones are never changed."""
    out = {fid: dict(by) for fid, by in reviews.items()}
    for row in rows:
        out.setdefault(row["flag_id"], {})[name_key(row["reviewer"])] = row
    return out


def make_row(flag_id, reviewer, decision, note="", report_id=None):
    """One decision row (validated), not saved anywhere."""
    reviewer = " ".join(str(reviewer or "").split())
    if not reviewer:
        raise ValueError("reviewer name is required")
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {list(DECISIONS)}")
    row = {"flag_id": flag_id, "reviewer": reviewer, "decision": decision,
           "note": note.strip(), "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    return {"report_id": report_id, **row} if report_id else row


def rows_jsonl(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def name_key(name):
    return " ".join(str(name or "").split()).lower()


def record(flag_id, reviewer, decision, note="", path=None, report_id=None):
    """Append one decision. reviewer is required (double review needs two names)."""
    row = make_row(flag_id, reviewer, decision, note, report_id)
    path = Path(path or REVIEWS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def verified_entry(finding):
    """The queue's "verified" record for an app finding checked by hand, or None. Explained
    issues are not findings, so only confirmed ones count (as "real")."""
    v = (finding or {}).get("verification")
    if not v or v.get("outcome") == "explained":
        return None
    return {"by": v["by"], "on": v["on"], "decision": "real", "outcome": v.get("outcome"),
            "note": v.get("note") or "", "known_issue": finding.get("known_issue")}


def decisions(item, reviews):
    """{reviewer key: decision row} for one item, with a hand verification as a row."""
    by = dict(reviews.get(item["flag_id"], {}))
    v = item.get("verified")
    if v and name_key(v["by"]) not in by:
        by[name_key(v["by"])] = {"flag_id": item["flag_id"], "reviewer": v["by"],
                                 "decision": v["decision"], "note": v.get("note", ""),
                                 "time": f"{v['on']}T00:00:00", "verified": True}
    return by


def verdict(item, reviews):
    """"real" | "false_alarm" | "unsure" | "disputed" | "waiting" | None (not reviewed)."""
    by = decisions(item, reviews)
    if not by:
        return None
    if not item.get("double_review"):
        if len({r["decision"] for r in by.values()}) > 1:     # two people disagree
            return "disputed"
        return next(iter(by.values()))["decision"]
    if len(by) < 2:
        return next(iter(by.values()))["decision"] if item.get("verified") else "waiting"
    decided = {r["decision"] for r in by.values()}
    return decided.pop() if len(decided) == 1 else "disputed"


def needs(item, reviews, reviewer):
    """Does this item still need a decision from this reviewer? (Not once verified by hand.)"""
    if item.get("verified"):
        return False
    by = reviews.get(item["flag_id"], {})
    if item.get("double_review"):
        return name_key(reviewer) not in by
    return not by


def next_index(queue, reviews, reviewer, start=0):
    """First item at or after start (wrapping) that needs this reviewer; None if done."""
    items = queue["items"]
    for k in range(len(items)):
        i = (start + k) % len(items)
        if needs(items[i], reviews, reviewer):
            return i
    return None


def precision(queue, reviews, items=None):
    """Precision over flags with a real/false_alarm verdict, with the counts behind it."""
    items = queue["items"] if items is None else items
    counts = {"real": 0, "false_alarm": 0, "unsure": 0, "disputed": 0, "waiting": 0, None: 0}
    for it in items:
        counts[verdict(it, reviews)] += 1
    judged = counts["real"] + counts["false_alarm"]
    return {"precision": counts["real"] / judged if judged else None, "judged": judged,
            "reviewed": len(items) - counts[None], "total": len(items),
            **{k: v for k, v in counts.items() if k}}


def agreement(queue, reviews):
    """On flags decided by two reviewers (double-review flags, and any other flag two people
    judged): how often they agree.

    kappa is Cohen's kappa over the three decisions (None with fewer than 2 pairs or when
    chance agreement is 1)."""
    pairs = []
    for it in queue["items"]:
        by = decisions(it, reviews)
        if len(by) >= 2:
            a, b = sorted(by.values(), key=lambda r: r["time"])[:2]
            pairs.append((a["decision"], b["decision"]))
    n = len(pairs)
    agree = sum(a == b for a, b in pairs)
    kappa = None
    if n >= 2:
        po = agree / n
        pe = sum((sum(a == d for a, _ in pairs) / n) * (sum(b == d for _, b in pairs) / n)
                 for d in DECISIONS)
        kappa = (po - pe) / (1 - pe) if pe < 1 else None
    return {"double_total": sum(1 for it in queue["items"] if it.get("double_review")),
            "both_reviewed": n, "agree": agree, "rate": agree / n if n else None, "kappa": kappa}


def dismissed_finding_ids(queue, reviews):
    """App finding ids whose flags were all judged false alarms (hidden by default)."""
    by_finding = {}
    for it in (queue or {}).get("items", []):
        if it.get("finding_id"):
            by_finding.setdefault(it["finding_id"], []).append(verdict(it, reviews))
    return {fid for fid, vs in by_finding.items() if vs and all(v == "false_alarm" for v in vs)}


# ---------- one queue per report ----------

def finding_item(f, n):
    """A queue item for an app finding (for flags with no full-audit queue entry)."""
    quotes = f.get("quotes") or []
    pages = sorted({q["page"] for q in quotes if isinstance(q.get("page"), int)})
    item = {"n": n, "flag_id": f["id"], "group": "findings", "double_review": False,
            "grade": f["grade"], "check": f.get("check"),
            "check_name": f.get("check_name") or f.get("check"), "pages": pages,
            "quotes": [{k: q[k] for k in ("page", "text", "where", "also_on") if k in q} for q in quotes],
            "title": f.get("title"), "reason": f.get("why") or f.get("message") or "",
            "answers": {}, "urls": [e["url"] for e in f.get("evidence") or [] if e.get("url")],
            "finding_id": f["id"]}
    v = verified_entry(f)
    if v:
        item["verified"] = v
    return item


def queue_for(report, base="file"):
    """The review queue of one report (a dict like review_queue.json): every RED/ORANGE flag.
    base: a queue dict to start from, None for none, or "file" for review/review_queue.json
    when it belongs to this report. Findings no queue item covers are added in grade order."""
    rid = report["id"]
    base = load_queue() if base == "file" else base
    own = bool(base and base.get("report_id") == rid)
    items = [dict(it) for it in base["items"]] if own else []
    covered = {it.get("finding_id") for it in items} | {it["flag_id"] for it in items}
    extra = [f for f in report.get("findings") or []
             if f.get("grade") in FLAG_GRADES and f["id"] not in covered]
    for f in extra:
        items.append(finding_item(f, len(items) + 1))
        if own:
            items[-1]["group"] = "other"
    if own:
        q = {k: v for k, v in base.items() if k != "items"}
        if extra:
            q["order"] = (base.get("order", "") + f"; then {len(extra)} flags from the other "
                          "checks (species, status, ToR, accreditation) in grade order")
    else:
        q = {"report_id": rid, "source": f"{rid}.json", "double_review": 0,
             "order": "grade order (RED first), as on the Findings tab"}
    q.update({"report_id": rid, "items": items, "total": len(items)})
    return q


def confirmed_findings(report, reviews=None):
    """{finding id: [decision rows]} of the findings that reviewers in reviews.jsonl confirmed
    (every reviewer of the flag said "real"). Hand verifications (known issues) are not rows
    here: they are the finding's own "verification"."""
    reviews = load_reviews(report_id=report["id"]) if reviews is None else reviews
    out = {}
    for it in queue_for(report)["items"]:
        by = reviews.get(it["flag_id"], {})
        if it.get("finding_id") and by and all(r["decision"] == "real" for r in by.values()):
            out.setdefault(it["finding_id"], []).extend(by.values())
    return out


def flag_ids(queue):
    """{name: flag_id}: each item's flag id, plus the app finding id that points to it (when
    only one item has that finding), so either id can name a flag."""
    out = {it["flag_id"]: it["flag_id"] for it in queue["items"]}
    by_finding = {}
    for it in queue["items"]:
        if it.get("finding_id"):
            by_finding.setdefault(it["finding_id"], []).append(it["flag_id"])
    for fid, flags in by_finding.items():
        if len(flags) == 1:
            out.setdefault(fid, flags[0])
    return out


def summary(item, width=70):
    """One line for a template: the quotes side by side for contradictions and copied text
    (their titles only name the pages), else the finding's title."""
    quoted = item.get("check") in ("contradiction", "recycled_figure", "copy_paste")
    if item.get("title") and not (quoted and item.get("quotes")):
        return item["title"]
    cut = lambda t: (t[:width] + "...") if len(t) > width else t
    quotes = [" ".join(q["text"].split()) for q in item.get("quotes") or []]
    return " vs ".join(f'"{cut(q)}"' for q in quotes[:2])
