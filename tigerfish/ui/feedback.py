"""Persistent reviewer feedback: Confirm / Dismiss / Unsure, reviewer name and a note per
finding, saved to feedback/feedback.json (gitignored), with export / import and a
precision summary per check.

File format (version 1):
  {"version": 1, "entries": {"<report_id>::<finding_id>": {
      "report_id", "finding_id", "check", "check_name", "grade",
      "decision", "reviewer", "note", "updated"}}}
"updated" is an ISO timestamp (UTC); on import, the newer entry for a finding wins.
Set TIGERFISH_FEEDBACK to use another file (tests do).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = ROOT / "feedback" / "feedback.json"
DECISIONS = ("Confirm", "Dismiss", "Unsure")
VERSION = 1


def path():
    return Path(os.getenv("TIGERFISH_FEEDBACK") or DEFAULT_FILE)


def key(report_id, finding_id):
    return f"{report_id}::{finding_id}"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- file ----------

def load(file=None):
    """{key: entry}. A missing or unreadable file is an empty store."""
    file = Path(file or path())
    if not file.exists():
        return {}
    try:
        return valid_entries(json.loads(file.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return {}


def save(entries, file=None):
    file = Path(file or path())
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".tmp")
    tmp.write_text(dump(entries), encoding="utf-8")
    tmp.replace(file)                      # write then rename: never a half-written file


def dump(entries):
    return json.dumps({"version": VERSION, "entries": entries}, ensure_ascii=False, indent=1,
                      sort_keys=True)


def valid_entries(raw):
    """Entries from a parsed file, keeping only well-formed ones. Raises ValueError if the
    file is not a TigerFish feedback file at all."""
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), dict):
        raise ValueError("not a TigerFish feedback file (no 'entries')")
    out = {}
    for k, e in raw["entries"].items():
        if (isinstance(e, dict) and e.get("decision") in DECISIONS and e.get("report_id")
                and e.get("finding_id") and k == key(e["report_id"], e["finding_id"])):
            out[k] = {**e, "reviewer": str(e.get("reviewer") or ""), "note": str(e.get("note") or ""),
                      "updated": str(e.get("updated") or "")}
    return out


# ---------- changes ----------

def record(entries, report_id, finding, decision, reviewer="", note=""):
    """Set (or with decision None, clear) one finding's review. Returns the new entries."""
    out = dict(entries)
    k = key(report_id, finding["id"])
    if decision is None:
        out.pop(k, None)
        return out
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    out[k] = {"report_id": report_id, "finding_id": finding["id"], "check": finding.get("check", ""),
              "check_name": finding.get("check_name", finding.get("check", "")),
              "grade": finding.get("grade", ""), "decision": decision,
              "reviewer": reviewer.strip(), "note": note.strip(), "updated": now()}
    return out


def merge(current, incoming):
    """Imported entries win when newer (or new). Returns (merged, number of entries taken)."""
    out, taken = dict(current), 0
    for k, e in incoming.items():
        if k not in out or e["updated"] > out[k]["updated"]:
            out[k] = e
            taken += 1
    return out, taken


def parse_import(data):
    """Entries from uploaded bytes or text. Raises ValueError on a bad file."""
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig")
    return valid_entries(json.loads(data))


# ---------- summaries ----------

def decision(entries, report_id, finding_id):
    e = entries.get(key(report_id, finding_id))
    return e["decision"] if e else None


def precision(entries, report_id=None):
    """Per check: confirmed, dismissed, unsure, reviewed, precision. precision =
    confirmed / (confirmed + dismissed); Unsure is counted but left out of the ratio
    (None when nothing is decided). Sorted by check name."""
    rows = {}
    for e in entries.values():
        if report_id and e["report_id"] != report_id:
            continue
        r = rows.setdefault(e["check_name"] or e["check"],
                            {"check": e["check_name"] or e["check"], "Confirm": 0, "Dismiss": 0, "Unsure": 0})
        r[e["decision"]] += 1
    out = []
    for r in sorted(rows.values(), key=lambda r: r["check"]):
        decided = r["Confirm"] + r["Dismiss"]
        out.append({"check": r["check"], "confirmed": r["Confirm"], "dismissed": r["Dismiss"],
                    "unsure": r["Unsure"], "reviewed": decided + r["Unsure"],
                    "precision": r["Confirm"] / decided if decided else None})
    return out


def precision_table(rows):
    """Markdown table for the Precision panel."""
    lines = ["| Check | Confirmed | Dismissed | Unsure | Precision |", "|---|---:|---:|---:|---:|"]
    for r in rows:
        p = ("-" if r["precision"] is None else
             f"{r['precision']:.0%} ({r['confirmed']} of {r['confirmed'] + r['dismissed']})")
        lines.append(f"| {r['check']} | {r['confirmed']} | {r['dismissed']} | {r['unsure']} | {p} |")
    return "\n".join(lines)


# ---------- Streamlit widgets ----------

REVIEWER_KEY = "feedback::reviewer"


def widget_key(report_id, finding_id):
    return f"review::{report_id}::{finding_id}"


def note_key(report_id, finding_id):
    return f"note::{report_id}::{finding_id}"


def _seed(report_id, findings):
    """Fill session state from the file once, before the widgets are drawn."""
    import streamlit as st
    entries = load()
    if REVIEWER_KEY not in st.session_state:
        latest = max(entries.values(), key=lambda e: e["updated"], default=None)
        st.session_state[REVIEWER_KEY] = latest["reviewer"] if latest else ""
    for f in findings:
        e = entries.get(key(report_id, f["id"]))
        st.session_state.setdefault(widget_key(report_id, f["id"]), e["decision"] if e else None)
        st.session_state.setdefault(note_key(report_id, f["id"]), e["note"] if e else "")


def _save_one(report_id, finding):
    import streamlit as st
    s = st.session_state
    save(record(load(), report_id, finding, s.get(widget_key(report_id, finding["id"])),
                s.get(REVIEWER_KEY, ""), s.get(note_key(report_id, finding["id"]), "")))


def reviewer_input(report_id, findings):
    import streamlit as st
    _seed(report_id, findings)
    st.text_input("Reviewer name", key=REVIEWER_KEY, placeholder="Your name",
                  help="Saved with each review in feedback/feedback.json on this computer.")


def review_widgets(report_id, finding):
    """Confirm / Dismiss / Unsure and a note, saved to the file on every change."""
    import streamlit as st
    c1, c2 = st.columns([2, 3])
    c1.segmented_control("Reviewer", DECISIONS, key=widget_key(report_id, finding["id"]),
                         label_visibility="collapsed", on_change=_save_one, args=(report_id, finding))
    c2.text_input("Note", key=note_key(report_id, finding["id"]), label_visibility="collapsed",
                  placeholder="Reviewer note (optional)", on_change=_save_one, args=(report_id, finding))


def _import(report_id, findings, uploader_key):
    import streamlit as st
    up = st.session_state.get(uploader_key)
    if up is None:
        return
    try:
        merged, taken = merge(load(), parse_import(up.getvalue()))
    except ValueError as e:
        st.session_state["feedback::import_msg"] = f"Import failed: {e}"
        return
    save(merged)
    for f in findings:                     # callbacks run before the rerun: safe to set widgets
        e = merged.get(key(report_id, f["id"]))
        st.session_state[widget_key(report_id, f["id"])] = e["decision"] if e else None
        st.session_state[note_key(report_id, f["id"])] = e["note"] if e else ""
    st.session_state["feedback::import_msg"] = f"Imported {taken} review(s)."


def panel(report_id, findings):
    """Precision panel, plus export / import of the feedback file."""
    import streamlit as st
    entries = load()
    st.markdown("#### Precision")
    scope = st.radio("Precision for", ["This report", "All reports"], horizontal=True,
                     key="feedback::scope", label_visibility="collapsed")
    rows = precision(entries, report_id if scope == "This report" else None)
    if rows:
        st.markdown(precision_table(rows))
    else:
        st.caption("No reviews saved yet.")
    st.caption("Precision = confirmed / (confirmed + dismissed): the share of flags a reviewer "
               "kept. Unsure reviews are counted but left out of the ratio. Saved in "
               "feedback/feedback.json on this computer.")
    from tigerfish.ui import review          # here: tigerfish.ui.review imports this module
    review.queue_section(report_id)
    e1, e2 = st.columns(2)
    e1.download_button("Export reviews (.json)", data=dump(entries), mime="application/json",
                       file_name="tigerfish_feedback.json", disabled=not entries)
    up_key = "feedback::upload"
    e2.file_uploader("Import reviews", type=["json"], key=up_key, label_visibility="collapsed",
                     on_change=_import, args=(report_id, findings, up_key))
    if msg := st.session_state.pop("feedback::import_msg", None):
        st.caption(msg)
