"""Review counts and precision per report, computed from saved files only.

A report's flags are its review queue (tigerfish/review.py queue_for): every RED/ORANGE flag.
Team reviews are the committed files (review/reviews.jsonl, hand verifications in the
queue); a visitor's own reviews are never counted here.

Precision is only shown as a number once enough flags are judged: below MIN_JUDGED it reads
"N reviewed so far: too few to estimate precision"; from MIN_JUDGED on, the percentage with a
95% Wilson interval, e.g. "78% (62-89%), 27 judged". The same rule applies to the random
sample and to reviewer agreement.
"""

import math

from tigerfish import review

MIN_JUDGED = 20
Z95 = 1.959964


def wilson(k, n, z=Z95):
    """95% Wilson score interval (low, high) for k successes in n; None if n == 0."""
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def estimate(k, n, what="precision", unit="judged", so_far="reviewed so far",
             min_n=MIN_JUDGED):
    """"78% (62-89%), 27 judged", or "5 reviewed so far: too few to estimate precision"."""
    if n < min_n:
        return f"{n} {so_far}: too few to estimate {what}"
    lo, hi = wilson(k, n)
    return f"{k / n:.0%} ({lo * 100:.0f}-{hi * 100:.0f}%), {n} {unit}"


def precision_text(p):
    """For a review.precision() dict."""
    return estimate(p["real"], p["judged"])


def agreement_text(a):
    """For a review.agreement() dict."""
    return estimate(a["agree"], a["both_reviewed"], what="agreement", unit="flags judged by two people",
                    so_far="judged by two people so far")


def report_quality(report, queue=None, reviews=None):
    """Counts for one report from its saved files: {"id", "title", "flags", "reviewed",
    "confirmed", "dismissed", "unsure", "disputed", "waiting", "judged", "precision", "text"}."""
    queue = review.queue_for(report) if queue is None else queue
    reviews = review.load_reviews(report_id=report["id"]) if reviews is None else reviews
    p = review.precision(queue, reviews)
    return {"id": report["id"], "title": report.get("title") or report["id"],
            "flags": p["total"], "reviewed": p["reviewed"], "confirmed": p["real"],
            "dismissed": p["false_alarm"], "unsure": p["unsure"], "disputed": p["disputed"],
            "waiting": p["waiting"], "judged": p["judged"], "precision": p["precision"],
            "text": precision_text(p)}


def overall(rows):
    """Sums over the reports, with one precision estimate over every judged flag."""
    keys = ("flags", "reviewed", "confirmed", "dismissed", "unsure", "disputed", "waiting", "judged")
    out = {k: sum(r[k] for r in rows) for k in keys}
    out["text"] = estimate(out["confirmed"], out["judged"])
    out["reports"] = len(rows)
    return out


def overall_line(o):
    rep = "report" if o["reports"] == 1 else "reports"
    return (f"All {o['reports']} {rep}: {o['flags']:,} RED/ORANGE flags, {o['reviewed']:,} reviewed "
            f"({o['confirmed']:,} confirmed, {o['dismissed']:,} dismissed, {o['unsure']:,} unsure"
            + (f", {o['disputed']:,} disputed" if o["disputed"] else "")
            + f"). Precision: {o['text']}.")
