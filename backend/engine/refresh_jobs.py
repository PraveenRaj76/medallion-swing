"""Background job tracking for POST /api/refresh.

Root cause this exists to fix (2026-09-11): a full-universe refresh (up to
~200 tickers, each several HTTP fetches) used to run as one long-lived
synchronous HTTP request. That meant (a) navigating away from the Screener
page lost all track of it — the "Refreshing…" state was just local React
state, reset on remount, so returning to the page looked like nothing had
happened even if the job was still running or had already finished, and
(b) the whole refresh lived or died with that one HTTP connection — a
client disconnect, a tab navigation in some browsers, or (very plausibly in
production) a hosting platform's own reverse-proxy request timeout would
silently kill a refresh that was otherwise still making progress, with no
server-side record that it had been cut off.

This tracks one job per market (IN/US) in memory, run in a background
thread so it keeps going regardless of any client connection, with a
status a poller can check independently of who started it — including a
real, data-derived ETA (done/elapsed rate, not a guessed constant).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("medallion.refresh_jobs")

_LOCK = threading.Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}


def _new_state(market: str, total: int) -> Dict[str, Any]:
    return {
        "market": market,
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
        "total": max(int(total), 0),
        "done": 0,
        "message": "Starting…",
        "result": None,
        "error": None,
    }


def is_running(market: str) -> bool:
    with _LOCK:
        state = _JOBS.get(market.upper())
        return bool(state and state["status"] == "running")


def get_status(market: str) -> Dict[str, Any]:
    market = market.upper()
    with _LOCK:
        state = _JOBS.get(market)
        out = dict(state) if state else None
    if out is None:
        return {"market": market, "status": "idle", "done": 0, "total": 0, "eta_sec": None, "elapsed_sec": None}

    now = out.get("finished_at") or time.time()
    elapsed = max(now - out["started_at"], 0.0)
    out["elapsed_sec"] = round(elapsed, 1)

    eta_sec = None
    if out["status"] == "running" and out["done"] > 0 and elapsed > 0:
        rate = out["done"] / elapsed  # tickers/sec, observed so far — not a guessed constant
        remaining = max(out["total"] - out["done"], 0)
        eta_sec = round(remaining / rate, 1) if rate > 0 else None
    out["eta_sec"] = eta_sec
    return out


def _set_progress(market: str, done: int, total: Optional[int], message: Optional[str]) -> None:
    with _LOCK:
        state = _JOBS.get(market)
        if state is None or state["status"] != "running":
            return
        state["done"] = done
        if total is not None:
            state["total"] = total
        if message is not None:
            state["message"] = message


def start(market: str, total_estimate: int, fn: Callable[..., Dict[str, Any]], *args: Any, **kwargs: Any) -> bool:
    """Run fn(*args, progress_cb=..., **kwargs) in a background thread for
    this market, unless a refresh for that market is already running (a
    second click while one is in flight joins the existing job's status
    instead of starting a redundant, overlapping refresh). Returns whether
    a new job was actually started."""
    market = market.upper()
    with _LOCK:
        existing = _JOBS.get(market)
        if existing and existing["status"] == "running":
            return False
        _JOBS[market] = _new_state(market, total_estimate)

    def progress_cb(done: int, total: Optional[int] = None, message: Optional[str] = None) -> None:
        _set_progress(market, done, total, message)

    def _run() -> None:
        try:
            result = fn(*args, progress_cb=progress_cb, **kwargs)
            with _LOCK:
                state = _JOBS[market]
                state["status"] = "done"
                state["finished_at"] = time.time()
                state["result"] = result
                state["message"] = (result or {}).get("message") or "Refresh complete."
                if result is not None:
                    state["done"] = state["total"]
        except Exception as exc:
            logger.error("Background refresh failed for %s: %s", market, exc)
            with _LOCK:
                state = _JOBS[market]
                state["status"] = "error"
                state["finished_at"] = time.time()
                state["error"] = str(exc)
                state["message"] = f"Refresh failed: {exc}"

    threading.Thread(target=_run, daemon=True, name=f"refresh-{market}").start()
    return True
