"""Human review of the full audit's RED/ORANGE flags: the queue, decisions, precision.

review/review_queue.json   built by scripts/build_review_queue.py: every new RED/ORANGE flag
                           of the full run, in review order (top 30 first, then a seeded
                           random order); some flags are marked double_review
review/reviews.jsonl       one line per decision: {flag_id, reviewer, decision, note, time};
                           a reviewer's latest line for a flag is the one that counts

A flag's verdict:
  single review: the latest decision by anyone
  double review: both reviewers' decisions (judged independently); the verdict is theirs
                 when they agree, "disputed" when they do not, "waiting" until two reviewers
                 have decided
Precision = real / (real + false alarm) over flags with a verdict; "unsure" and disputed
flags are left out (and counted).
"""

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = ROOT / "review"
QUEUE = REVIEW_DIR / "review_queue.json"
REVIEWS = REVIEW_DIR / "reviews.jsonl"

DECISIONS = {"real": "Confirm (real issue)", "false_alarm": "Dismiss (false alarm)",
             "unsure": "Unsure"}
AS_FEEDBACK = {"real": "Confirm", "false_alarm": "Dismiss", "unsure": "Unsure"}  # card wording


def load_queue(path=None):
    path = Path(path or QUEUE)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_reviews(path=None):
    """{flag_id: {reviewer: latest decision row}}."""
    out = {}
    p = Path(path or REVIEWS)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out.setdefault(row["flag_id"], {})[name_key(row["reviewer"])] = row
    return out


def name_key(name):
    return " ".join(str(name or "").split()).lower()


def record(flag_id, reviewer, decision, note="", path=None):
    """Append one decision. reviewer is required (double review needs two names)."""
    reviewer = " ".join(str(reviewer or "").split())
    if not reviewer:
        raise ValueError("reviewer name is required")
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {list(DECISIONS)}")
    row = {"flag_id": flag_id, "reviewer": reviewer, "decision": decision,
           "note": note.strip(), "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    path = Path(path or REVIEWS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def verdict(item, reviews):
    """"real" | "false_alarm" | "unsure" | "disputed" | "waiting" | None (not reviewed)."""
    by = reviews.get(item["flag_id"], {})
    if not by:
        return None
    if not item.get("double_review"):
        return max(by.values(), key=lambda r: r["time"])["decision"]
    if len(by) < 2:
        return "waiting"
    decided = {r["decision"] for r in by.values()}
    return decided.pop() if len(decided) == 1 else "disputed"


def needs(item, reviews, reviewer):
    """Does this item still need a decision from this reviewer?"""
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
    """On double-review flags decided by two reviewers: how often they agree.

    kappa is Cohen's kappa over the three decisions (None with fewer than 2 pairs or when
    chance agreement is 1)."""
    pairs = []
    for it in queue["items"]:
        by = reviews.get(it["flag_id"], {})
        if it.get("double_review") and len(by) >= 2:
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
