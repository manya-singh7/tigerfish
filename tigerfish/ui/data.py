"""Load saved results (replay mode) from results/."""

import json
from pathlib import Path

from tigerfish.report import sort_findings

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def reports():
    """[{id, title, file}] in display order."""
    path = RESULTS / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def load(report_id):
    data = json.loads((RESULTS / f"{report_id}.json").read_text(encoding="utf-8"))
    data["findings"] = sort_findings(data["findings"])
    return data


def image_path(path):
    """Page image path: relative to results/ (replay) or absolute (live mode). None if missing."""
    p = Path(path)
    p = p if p.is_absolute() else RESULTS / p
    return p if p.exists() else None


def counts(findings):
    return {g: sum(f["grade"] == g for f in findings) for g in ("RED", "ORANGE", "INFO")}


def filter_findings(findings, grades, checks):
    return [f for f in findings if f["grade"] in grades and f["check_name"] in checks]
