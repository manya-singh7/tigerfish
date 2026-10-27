"""Re-runs of scripts/audit.py reuse the last run's --new-pages (no re-pairing), and
CACHE_ONLY never makes a paid call."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audit  # noqa: E402
from tigerfish import llm  # noqa: E402


def args(**kw):
    base = {"new_pages": None, "reuse_passages": False, "fresh": False}
    return SimpleNamespace(**{**base, **kw})


def test_rerun_reuses_saved_new_pages_and_passages():
    prev = {"claims": 10463, "new_pages": "539,939"}
    assert audit.resolve_rerun(args(), prev, 10463) == ("539,939", True)


def test_rerun_finds_new_pages_in_older_reports_sittings():
    prev = {"claims": 10463, "run_totals": {"sittings": [{"new_pages": "539,1166"}]}}
    assert audit.resolve_rerun(args(), prev, 10463) == ("539,1166", True)


def test_changed_claims_without_new_pages_stop_before_any_call():
    with pytest.raises(SystemExit, match="claims changed"):
        audit.resolve_rerun(args(), {"claims": 10297}, 10463)


def test_fresh_and_explicit_flags_win():
    prev = {"claims": 10297, "new_pages": "539"}
    assert audit.resolve_rerun(args(fresh=True), prev, 10463) == (None, False)
    assert audit.resolve_rerun(args(new_pages="7"), prev, 10463) == ("7", False)
    assert audit.resolve_rerun(args(), None, 10463) == (None, False)


def test_cache_only_raises_instead_of_calling(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "CACHE_ONLY", True)
    monkeypatch.setattr(llm, "_create", lambda *a, **k: pytest.fail("API called"))
    with pytest.raises(llm.CacheMiss):
        llm._call("m", [], {}, tmp_path / "x.json")
