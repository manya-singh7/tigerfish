"""Read-only presentation of batch checks, distinct from full-audit findings.

The same adapter supplies report views, library cards and aggregate counts. Species
flags already mapped into standard findings are not counted twice as extra observations.
"""

CHECK_NAMES = {
    "accreditation": "Certificate-date screen",
    "baseline_season": "Baseline-period screen",
    "species_iucn": "Species and IUCN screen",
}
OBSERVATION_CHECKS = {"accreditation", "baseline_season"}
LEAD_GRADES = ("RED", "ORANGE", "INFO")


def checks(report):
    return report.get("batch_checks") or {}


def observations(report):
    """Additional batch leads only; GREY is a check result, never a finding."""
    return [
        f
        for f in report.get("batch_flags") or []
        if f.get("check") in OBSERVATION_CHECKS and f.get("grade") in LEAD_GRADES
    ]


def summary(report):
    results = list(checks(report).values())
    if not results:
        return None
    leads = observations(report)
    return {
        "checks": len(results),
        "undetermined": sum(r.get("grade", r.get("status")) == "GREY" for r in results),
        "observations": len(leads),
        "grades": {g: sum(f.get("grade") == g for f in leads) for g in LEAD_GRADES},
    }


def summary_line(value):
    noun = "observation" if value["observations"] == 1 else "observations"
    result_noun = "result" if value["undetermined"] == 1 else "results"
    return (
        f"Batch screening: {value['checks']} checks, {value['observations']} additional "
        f"{noun}, {value['undetermined']} undetermined {result_noun}."
    )


def totals(entries):
    rows = [e["screening"] for e in entries if e.get("screening")]
    return {
        "reports": len(rows),
        **{
            k: sum(r[k] for r in rows)
            for k in ("checks", "observations", "undetermined")
        },
    }


def observation_finding(flag, index=1):
    """Adapt a batch observation to the evidence-slip shape without changing its schema."""
    check = flag["check"]
    return {
        "id": f"batch-{check}-{index}",
        "check": check,
        "check_name": CHECK_NAMES.get(check, check),
        "grade": flag["grade"],
        "title": CHECK_NAMES.get(check, check),
        "message": flag.get("message", ""),
        "why": flag.get("message", ""),
        "quotes": flag.get("quotes") or [],
        "evidence": flag.get("evidence") or [],
        "images": [],
    }
