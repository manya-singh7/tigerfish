"""Hosted-app safety (Streamlit Community Cloud / Hugging Face Spaces).

Hosted mode is on when TIGERFISH_HOSTED=1, or when the app runs on Streamlit Community Cloud
(repo mounted under /mount/src) or a Hugging Face Space (SPACE_ID is set). In hosted mode:

- Nothing is read from gitignored folders (cache/, data/eias/, logs/, feedback/): the saved
  reports come from results/, review/ and docs/, which are committed.
- Reviews made by visitors stay in their browser session (with export); the committed review
  decisions are shown read-only and never overwritten.
- Without NEBIUS_API_KEY (Streamlit secrets): replay only.
- With it: an uploaded PDF (at most MAX_UPLOAD_PAGES pages, MAX_UPLOADS_PER_SESSION per
  session) always gets the free checks; the paid checks (Nemotron) run only within the caps:
  MAX_RUN_USD per upload, MAX_ASKS_PER_SESSION "Ask the report" questions per session, and
  DAILY_BUDGET_USD for the whole app per UTC day on the owner's key.
- A visitor may paste their own Nebius key: it is kept in their session only (never written
  to disk or logged), their calls are not counted against the daily budget, and the
  per-session caps still apply.

The daily total is kept in memory and in a small file in the system temp folder, so it
survives app reruns and most restarts. A cold restart of the container resets it.
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path

MAX_UPLOAD_PAGES = 30
MAX_UPLOADS_PER_SESSION = 3
MAX_ASKS_PER_SESSION = 3
MAX_RUN_USD = 0.50            # paid checks on one upload
DAILY_BUDGET_USD = 1.00       # all visitors together, on the owner's key, per UTC day
BUDGET_FILE = Path(tempfile.gettempdir()) / "tigerfish_daily_spend.json"

BYOK_KEY = "hosted::byok"     # session_state key of the visitor's own key


def is_hosted():
    if os.getenv("TIGERFISH_HOSTED", "").strip() == "1":
        return True
    if os.getenv("TIGERFISH_HOSTED", "").strip() == "0":
        return False
    return Path("/mount/src").is_dir() or bool(os.getenv("SPACE_ID"))


def owner_key():
    """NEBIUS_API_KEY from the environment or Streamlit secrets ("" if none)."""
    key = os.getenv("NEBIUS_API_KEY", "").strip()
    if key:
        return key
    try:
        import streamlit as st
        return str(st.secrets.get("NEBIUS_API_KEY", "")).strip()
    except Exception:          # no secrets file, or not running in Streamlit
        return ""


class BudgetExceeded(RuntimeError):
    pass


def today():
    return time.strftime("%Y-%m-%d", time.gmtime())


class DailyBudget:
    """USD spent today on the owner's key, with a hard cap."""

    def __init__(self, cap=DAILY_BUDGET_USD, path=BUDGET_FILE):
        self.cap, self.path = cap, Path(path) if path else None
        self._lock = threading.Lock()
        self._day, self._usd = today(), 0.0
        self._load()

    def _load(self):
        if not self.path:
            return
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if d.get("day") == self._day:
                self._usd = float(d.get("usd", 0.0))
        except (OSError, ValueError, TypeError):
            pass

    def _roll(self):
        if self._day != today():
            self._day, self._usd = today(), 0.0

    def spent(self):
        with self._lock:
            self._roll()
            return self._usd

    def remaining(self):
        return max(0.0, self.cap - self.spent())

    def ensure_room(self, est_usd=0.0):
        """Raise BudgetExceeded if spending est_usd more would pass the cap (or nothing is left)."""
        with self._lock:
            self._roll()
            if self._usd >= self.cap or self._usd + est_usd > self.cap:
                raise BudgetExceeded(
                    f"The demo's daily budget of ${self.cap:.2f} for model calls is used up "
                    f"(${self._usd:.2f} spent today, UTC). Try again tomorrow, or use your own "
                    f"Nebius key.")

    def add(self, usd):
        with self._lock:
            self._roll()
            self._usd += float(usd or 0.0)
            if self.path:
                try:
                    self.path.write_text(json.dumps({"day": self._day, "usd": round(self._usd, 6)}),
                                         encoding="utf-8")
                except OSError:
                    pass


budget = DailyBudget()


# ---------- per session ----------

def visitor_key(state):
    return str(state.get(BYOK_KEY) or "").strip()


def paid_key(state):
    """The key paid calls use in this session: the visitor's own, else the owner's ("" = none)."""
    return visitor_key(state) or owner_key()


def uses_owner_budget(state):
    return not visitor_key(state)


def count(state, name):
    return int(state.get(f"hosted::{name}", 0))


def bump(state, name):
    state[f"hosted::{name}"] = count(state, name) + 1


def uploads_left(state):
    return max(0, MAX_UPLOADS_PER_SESSION - count(state, "uploads"))


def asks_left(state):
    return max(0, MAX_ASKS_PER_SESSION - count(state, "asks"))


def run_cap(state):
    """Max USD for the paid checks of one upload in this session."""
    if uses_owner_budget(state):
        return min(MAX_RUN_USD, budget.remaining())
    return MAX_RUN_USD


class paid_calls:
    """Context manager for paid model calls in a session: the session's key, and the daily
    budget when that key is the owner's.

        with hosted.paid_calls(st.session_state):
            ...llm calls...
    """

    def __init__(self, state):
        from tigerfish import llm
        self._key = llm.use_key(paid_key(state))
        self._budget = llm.use_budget(budget if uses_owner_budget(state) else None)

    def __enter__(self):
        self._key.__enter__()
        self._budget.__enter__()
        return self

    def __exit__(self, *exc):
        self._budget.__exit__(*exc)
        return self._key.__exit__(*exc)
