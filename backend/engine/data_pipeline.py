"""
Medallion Swing — Forward-Test Signal Validation Pipeline
Live NSE quotes · Fixed Quantity = 1 · SUCCESSFUL TRADE / BAD TRADE clearance
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from db import database_engine as db
from providers import nse_data_provider as nse

logger = logging.getLogger(__name__)

SYNC_COOLDOWN_MINUTES = 15
FUNDAMENTAL_REFRESH_HOURS = 24
RSI_OVERBOUGHT = 65.0
FIXED_QUANTITY = 1

# Trailing-stop design (chandelier exit, Chuck LeBeau): trail = highest high
# since entry - multiplier x ATR. Wider (3x) before the original target is
# reached so a normal pullback doesn't shake the trade out early; tighter
# (2x) once price has proven the trend by reaching target, to lock in more
# of the gain while still letting a genuine trend run past the fixed target
# instead of force-closing there. The stop only ever ratchets up, never down.
CHANDELIER_MULTIPLIER_INITIAL = 3.0
CHANDELIER_MULTIPLIER_RUNNER = 2.0
# Informational only (does not change FIXED_QUANTITY=1 forward-test sizing) —
# what a real position would size to at 1% account risk, Turtle/Zerodha-Varsity
# convention. Override via MEDALLION_CAPITAL_BASE.
DEFAULT_CAPITAL_BASE = float(os.environ.get("MEDALLION_CAPITAL_BASE", "25000"))
RISK_PCT_PER_TRADE = 0.01

# BUY signal confluence gate (Decision Engine Blueprint 1.1). Starting
# numbers, not final — flagged in the blueprint as needing sign-off before
# they gate real signals. A composite score alone is a weak gate: it lets a
# pure-momentum name with no fundamental backing qualify, or a fundamentally
# sound name at a terrible entry qualify too. Every gate below must pass
# simultaneously.
BUY_COMPOSITE_FLOOR_PCT = float(os.environ.get("MEDALLION_BUY_COMPOSITE_FLOOR_PCT", "65"))
BUY_FUNDAMENTAL_FLOOR_PCT = float(os.environ.get("MEDALLION_BUY_FUNDAMENTAL_FLOOR_PCT", "50"))
BUY_PE_PEER_PERCENTILE_MAX = float(os.environ.get("MEDALLION_BUY_PE_PEER_PERCENTILE_MAX", "60"))
BUY_PEG_MAX = float(os.environ.get("MEDALLION_BUY_PEG_MAX", "2.0"))
MAX_CONCURRENT_POSITIONS = int(os.environ.get("MEDALLION_MAX_CONCURRENT_POSITIONS", "5"))


def should_skip_heavy_sync() -> Tuple[bool, Optional[datetime]]:
    last_updated = db.get_leaderboard_last_updated()
    if last_updated is None:
        return False, None
    if datetime.utcnow() - last_updated < timedelta(minutes=SYNC_COOLDOWN_MINUTES):
        return True, last_updated
    return False, last_updated


def _fundamentals_stale() -> bool:
    last = db.get_leaderboard_last_updated()
    if last is None:
        return True
    # Re-scrape fundamentals at most once per day; prices still refresh every SYNC_COOLDOWN
    # We use a lightweight flag via max(last_updated) age > FUNDAMENTAL_REFRESH_HOURS
    # when caller requests include_fundamentals.
    return datetime.utcnow() - last >= timedelta(hours=FUNDAMENTAL_REFRESH_HOURS)


def refresh_screener_quotes(
    force: bool = False,
    include_fundamentals: Optional[bool] = None,
    fast: bool = False,
) -> int:
    """
    Refresh screener from live NSE (+ Screener.in fundamentals).
    fast=True → bootstrap liquid names only, prices/technicals, hard deadline (~45s).
    """
    try:
        if not nse.is_live_mode():
            db.ensure_mock_leaderboard()
            return _refresh_mock_jitter()

        if include_fundamentals is None:
            include_fundamentals = (
                (not fast)
                and (force or _fundamentals_stale() or db.leaderboard_is_empty())
            )

        # Local full load: MEDALLION_LOCAL_FULL=1 → entire universe, no short deadline
        local_full = os.environ.get("MEDALLION_LOCAL_FULL", "").strip() in {"1", "true", "yes"}
        if fast and not local_full:
            tickers = list(nse.BOOTSTRAP_TICKERS)
            deadline = 45.0
        elif local_full or (not fast and force):
            tickers = nse.load_universe()
            deadline = None  # allow full swing universe locally
        else:
            tickers = nse.load_universe()
            deadline = 180.0 if include_fundamentals else 90.0

        rows = nse.refresh_universe_live(
            tickers=tickers,
            max_workers=6 if fast else 5,
            include_fundamentals=bool(include_fundamentals) and not fast,
            deadline_sec=deadline,
        )
        if not rows:
            logger.error("Live universe refresh returned 0 rows — keeping DB as-is (no mock seed in live mode)")
            return 0

        # When skipping fundamentals scrape, merge prior fund fields from DB
        if not include_fundamentals or fast:
            merged = []
            for row in rows:
                prior = db.get_ticker_row(row["ticker"])
                if prior is not None:
                    for key in (
                        "company_name",
                        "description",
                        "sector",
                        "industry",
                        "roic",
                        "net_debt_ebitda",
                        "peg_ratio",
                        "interest_coverage",
                        "promoter_pledge_pct",
                        "yoy_profit_growth",
                        "fundamental_score",
                    ):
                        if prior.get(key) is not None:
                            row[key] = prior.get(key)
                    row["technical_score"] = nse._score_technical(row)
                    row["composite_score"] = round(
                        float(row.get("fundamental_score") or 0) + float(row["technical_score"]),
                        1,
                    )
                merged.append(row)
            rows = merged

        db.upsert_leaderboard_rows(rows)
        return len(rows)
    except Exception as exc:
        logger.error("refresh_screener_quotes failed: %s", exc)
        # Live mode: never inject mock rows
        if not nse.is_live_mode() and db.leaderboard_is_empty():
            db.ensure_mock_leaderboard()
        return 0


def _refresh_mock_jitter() -> int:
    """Offline test path — small jitter on seeded mock rows."""
    import random

    frame = db.get_leaderboard(limit=500)
    if frame is None or frame.empty:
        db.ensure_mock_leaderboard()
        frame = db.get_leaderboard(limit=500)
    if frame is None or frame.empty:
        return 0
    refreshed: List[Dict[str, Any]] = []
    for _, row in frame.iterrows():
        payload = row.to_dict()
        base = float(payload.get("close_price", 0) or 0)
        atr = float(payload.get("atr_value", 1) or 1)
        payload["close_price"] = round(max(1.0, base * (1 + random.uniform(-0.01, 0.01))), 2)
        payload["atr_value"] = round(max(0.05, atr * random.uniform(0.95, 1.05)), 2)
        rsi = float(np.clip(float(payload.get("rsi_14", 50) or 50) + random.uniform(-1.5, 1.5), 20, 80))
        payload["rsi_14"] = round(rsi, 2)
        payload["is_buyable"] = _recompute_buyable(
            payload["close_price"], float(payload.get("sma_200", 0) or 0), rsi
        )
        refreshed.append(payload)
    db.upsert_leaderboard_rows(refreshed)
    return len(refreshed)


def _recompute_buyable(close_price: float, sma_200: float, rsi_14: float) -> int:
    if close_price <= sma_200 or rsi_14 > RSI_OVERBOUGHT:
        return 0
    return 1


def ensure_ticker_live(
    ticker: str,
    include_fundamentals: bool = True,
    force_refresh: bool = True,
) -> Optional[pd.Series]:
    """
    Resolve any NSE ticker on demand (Search Profile) and cache into leaderboard.
    force_refresh=True (default) always hits live feeds — never stale cache-only.
    """
    ticker = nse.normalize_ticker(ticker)
    if not nse.is_live_mode():
        return db.get_ticker_row(ticker)

    prior = db.get_ticker_row(ticker)
    prior_dict = prior.to_dict() if prior is not None else None
    if not force_refresh and prior is not None:
        return prior
    try:
        bench = nse.fetch_ohlcv(nse.BENCHMARK, range_param="6mo", interval="1d")
        row = nse.build_live_row(
            ticker,
            bench_frame=bench if bench is not None and not bench.empty else None,
            include_fundamentals=include_fundamentals,
            prior=prior_dict,
        )
        if row:
            ok = db.upsert_leaderboard_rows([row])
            if not ok:
                logger.error("upsert failed after live fetch for %s", ticker)
            return pd.Series(row)
        # Last resort: return prior rather than hard-failing the UI
        if prior is not None:
            logger.warning("live fetch empty for %s — returning cached row", ticker)
            return prior
    except Exception as exc:
        logger.error("ensure_ticker_live failed for %s: %s", ticker, exc)
        if prior is not None:
            return prior
    return None


def validate_active_signals(user_id: int) -> List[Dict[str, Any]]:
    """
    Clearance loop: mark 1-share signals to market and ratchet a chandelier
    trailing stop (see compute_trailing_stop) every cycle.

    There is no separate "hit target -> auto-close" branch anymore — reaching
    the original target only tightens the trail (3x ATR -> 2x ATR) instead of
    forcing an exit, so a genuine trend isn't capped at a fixed R:R (this was
    the main finding from the cross-market checklist review: a fixed target
    fights the trend-following premise of the technical checklist). The
    position closes only when price actually trades through the current
    trailing stop. Whether that's a win or a loss is decided by where the
    stop ended up relative to entry, not by which fixed level was crossed.
    """
    clearances: List[Dict[str, Any]] = []
    try:
        positions = db.get_active_positions(user_id)
        if positions is None or positions.empty:
            return clearances

        for _, pos in positions.iterrows():
            if int(pos["user_id"]) != int(user_id):
                continue
            position_id = int(pos["position_id"])
            ticker = str(pos["ticker"]).upper()
            pos_market = str(pos.get("market") or "IN").upper()
            entry_price = float(pos["entry_price"])
            target = float(pos["target"])
            quantity = int(pos.get("quantity") or FIXED_QUANTITY)
            initial_stop = float(pos.get("initial_stop_loss") or pos["stop_loss"])
            highest_price_since_entry = float(pos.get("highest_price_since_entry") or entry_price)
            trail_phase = str(pos.get("trail_phase") or "initial")
            atr_at_entry = pos.get("atr_at_entry")

            market = db.get_ticker_row(ticker, market=pos_market)
            if market is None and nse.is_live_mode():
                # Cached row missing (ticker aged out of the leaderboard, or
                # never refreshed) — resolve live through the SAME provider
                # the position's own market uses. Using the India-only path
                # for a US ticker (or vice versa) would either find nothing
                # or, worse, misresolve a coincidentally-matching symbol.
                if pos_market == "US":
                    from providers import us_data_provider as usdp

                    try:
                        market = usdp.build_live_row(ticker)
                    except Exception as exc:
                        logger.warning("US live resolve failed for %s: %s", ticker, exc)
                        market = None
                else:
                    market = ensure_ticker_live(ticker, include_fundamentals=False)

            if market is not None:
                current_price = float(market.get("close_price", entry_price))
                atr_current = _num(market, "atr_value") or (
                    float(atr_at_entry) if atr_at_entry is not None else None
                )
            else:
                current_price = float(pos.get("current_price") or entry_price)
                atr_current = float(atr_at_entry) if atr_at_entry is not None else None

            unrealized = (current_price - entry_price) * quantity
            db.update_position_mark(position_id, current_price, unrealized)

            trail = compute_trailing_stop(
                entry_price=entry_price,
                initial_stop=initial_stop,
                atr_current=atr_current or 0.0,
                highest_price_since_entry=highest_price_since_entry,
                current_price=current_price,
                target=target,
                trail_phase=trail_phase,
            )
            stop_loss = trail["stop_loss"]
            db.update_position_trailing(
                position_id, trail["highest_price_since_entry"], stop_loss, trail["trail_phase"]
            )

            exit_status = None
            if current_price <= stop_loss:
                # Win if the ratcheted stop locked in a price at/above entry;
                # a genuine loss only if it's still below entry (stop never
                # loosens, so this only happens before the trail has caught up).
                exit_status = db.EXIT_SUCCESS if stop_loss >= entry_price else db.EXIT_BAD

            if exit_status:
                ok, message, pnl = db.close_signal(
                    user_id=user_id,
                    position_id=position_id,
                    exit_price=current_price,
                    exit_status=exit_status,
                )
                clearances.append(
                    {
                        "ticker": ticker,
                        "position_id": position_id,
                        "exit_status": exit_status,
                        "exit_price": current_price,
                        "final_pnl": pnl,
                        "success": ok,
                        "message": message,
                    }
                )
        return clearances
    except Exception as exc:
        logger.error("validate_active_signals failed for user %s: %s", user_id, exc)
        return clearances


def _looks_like_legacy_mock_board() -> bool:
    """Detect old mock-only leaderboard so live mode upgrades force a real NSE pull."""
    try:
        frame = db.get_leaderboard(limit=200)
        if frame is None or frame.empty:
            return True
        mock_set = {str(m["ticker"]).upper() for m in db.MOCK_LEADERBOARD}
        tickers = {str(t).upper() for t in frame["ticker"].tolist()}
        return tickers.issubset(mock_set) and len(tickers) <= len(mock_set)
    except Exception:
        return False


FIXED_QUANTITY = 1
MIN_SOURCES_REQUIRED = 3


def _num(row: Any, key: str) -> Optional[float]:
    try:
        if hasattr(row, "get"):
            val = row.get(key)
        else:
            return None
        if val is None or val == "" or (isinstance(val, float) and math.isnan(val)):
            return None
        return float(val)
    except Exception:
        return None


def row_has_live_price(row: Any) -> bool:
    close = _num(row, "close_price")
    return close is not None and close > 0


def row_has_technicals(row: Any) -> bool:
    # delivery_pct_10d is deliberately NOT required here: since the bhavcopy
    # fix (2026-08-24) it's a real NSE figure that's honestly None when that
    # ticker genuinely has no delivery data in the scan window — the same
    # factor_engine.py checklist already treats that as a non-blocking
    # skip (0/0 marks), not a failure. Requiring it here predates that fix
    # and was silently keeping otherwise fully-scored, real rows out of
    # "Ready Today" forever whenever delivery data happened to be missing.
    sma50 = _num(row, "sma_50")
    sma200 = _num(row, "sma_200")
    rsi = _num(row, "rsi_14")
    atr = _num(row, "atr_value")
    return (
        sma50 is not None
        and sma200 is not None
        and sma200 > 0
        and rsi is not None
        and atr is not None
        and atr > 0
    )


def _row_is_financial(row: Any) -> bool:
    blob = " ".join(
        str(x or "")
        for x in (
            row.get("sector") if hasattr(row, "get") else "",
            row.get("industry") if hasattr(row, "get") else "",
        )
    ).lower()
    return any(k in blob for k in ("bank", "finance", "nbfc", "financial", "insurance", "housing finance"))


def row_has_checklist_fields(row: Any) -> bool:
    """
    Company/sector identity must be present, and technicals must be fully
    computable (we always have OHLCV for that, so this stays a hard
    requirement). Individual FUNDAMENTAL metrics (ROE, PEG, growth, pledge)
    are deliberately NOT all hard-required here — when Screener.in doesn't
    publish one for a given stock, the checklist in factor_engine.py already
    scores that specific line as FAIL/0 rather than crashing or needing to
    block the row. Requiring every single ratio here duplicated that gate
    more strictly than necessary and hid real, scored stocks from the table
    just because one ratio was thin — inconsistent with the Search Profile
    page, which already shows exactly this kind of partial row successfully.
    """
    if not hasattr(row, "get"):
        return False
    company = str(row.get("company_name") or "").strip()
    sector = str(row.get("sector") or "").strip()
    if not company or company in {"—", "-", "nan"}:
        return False
    if not sector or sector in {"—", "-", "nan"}:
        return False
    if not row_has_technicals(row):
        return False
    if _num(row, "alpha_3m") is None:
        return False
    # Require at least ONE real fundamental signal so the row isn't a
    # completely blank fundamentals shell — but not all of them.
    has_some_fundamentals = any(
        _num(row, k) is not None
        for k in ("roic", "roe", "pe_ratio", "peg_ratio", "yoy_profit_growth", "promoter_pledge_pct")
    )
    return has_some_fundamentals


def row_is_display_ready(row: Any) -> bool:
    """Screener table: only fully loaded names (price + fund + tech + checklist)."""
    return row_is_fully_verified(row)


def row_is_fully_verified(row: Any) -> bool:
    """Strict gate — CMP + 3-site fund + OHLCV tech + checklist fields."""
    if not row_has_live_price(row):
        return False
    if not hasattr(row, "get"):
        return False
    if not bool(row.get("ohlcv_ready")):
        return False
    if not row_has_technicals(row):
        return False
    fund = _num(row, "fundamental_score")
    tech = _num(row, "technical_score")
    if fund is None or fund <= 0 or tech is None or tech <= 0:
        return False
    quality = str((row.get("data_quality") or "")).upper()
    verified = bool(row.get("fundamentals_verified"))
    sources = int(_num(row, "sources_ok_count") or 0)
    src_list = row.get("fundamentals_sources") or []
    if sources < 1 and isinstance(src_list, (list, tuple)):
        sources = max(sources, len(src_list))
    # SOURCED/CACHED = Screener resolved (or a fresh cache of a prior Screener
    # success) — full confidence. FALLBACK = only NSE's own filing came
    # through — real data, just thinner; still allowed to count as loaded
    # rather than being treated as a failure (its score is separately
    # discounted 30% in factor_engine, not blocked here).
    if quality not in ("SOURCED", "CACHED", "FALLBACK") or sources < 1:
        return False
    if not row_has_checklist_fields(row):
        return False
    return True


def count_fully_complete(frame: Optional[pd.DataFrame] = None) -> int:
    universe = {nse.normalize_ticker(t) for t in nse.load_universe()}
    if frame is None:
        frame = db.get_leaderboard(limit=2000)
    if frame is None or frame.empty:
        return 0
    n = 0
    for _, r in frame.iterrows():
        sym = nse.normalize_ticker(str(r.get("ticker") or ""))
        if sym not in universe:
            continue
        if row_is_fully_verified(r):
            n += 1
    return n


def list_incomplete_tickers(limit: int = 40, *, skip_exhausted: bool = True) -> List[str]:
    """Universe tickers not yet fully ready (includes names missing from DB)."""
    universe = [nse.normalize_ticker(t) for t in nse.load_universe()]
    exhausted = db.exhausted_ticker_set() if skip_exhausted else set()
    frame = db.get_leaderboard(limit=2000)
    by_ticker: Dict[str, Any] = {}
    if frame is not None and not frame.empty:
        for _, r in frame.iterrows():
            by_ticker[nse.normalize_ticker(str(r.get("ticker") or ""))] = r
    out: List[str] = []
    for sym in universe:
        if skip_exhausted and sym in exhausted:
            continue
        row = by_ticker.get(sym)
        if row is None or not row_is_fully_verified(row):
            out.append(sym)
            if len(out) >= max(1, int(limit)):
                break
    return out


def filter_display_ready(frame: Optional[pd.DataFrame], market: str = "IN") -> pd.DataFrame:
    """Empty unless today's refresh; only fully complete swing-universe rows.

    market picks which universe list a ticker must belong to — without
    this, a US row would always fail the India universe membership check
    (and vice versa), so calling this on a mixed or US-only frame with the
    old India-only default silently zeroed out every US row regardless of
    how complete its data actually was.
    """
    if frame is None or frame.empty:
        return pd.DataFrame()
    if not db.screener_is_today():
        return pd.DataFrame()
    if market.upper() == "US":
        from providers import us_data_provider as usdp

        # load_universe() returns dicts (ticker, company_name, sector, ...),
        # not plain strings like nse.load_universe() — pull the ticker out.
        universe = {u["ticker"] for u in usdp.load_universe()}
        normalize = usdp.normalize_ticker
    else:
        universe = {nse.normalize_ticker(t) for t in nse.load_universe()}
        normalize = nse.normalize_ticker
    mask = frame.apply(
        lambda r: normalize(str(r.get("ticker") or "")) in universe
        and row_is_fully_verified(r),
        axis=1,
    )
    out = frame.loc[mask].copy()
    if "composite_score" in out.columns:
        out["composite_score"] = pd.to_numeric(out["composite_score"], errors="coerce").fillna(0)
        out = out.sort_values("composite_score", ascending=False)
    return out.reset_index(drop=True)


_pending_cursor = 0


def _next_pending_window(size: int) -> List[str]:
    """
    Rotating slice of the pending list.

    Without this every batch retries the same alphabetical head, so names far
    down the universe never get attempted before the retry budget runs out.
    """
    global _pending_cursor

    pending = list_incomplete_tickers(limit=10_000, skip_exhausted=True)
    if not pending:
        _pending_cursor = 0
        return []
    size = max(1, min(int(size), len(pending)))
    start = _pending_cursor % len(pending)
    window = pending[start : start + size]
    if len(window) < size:
        window += pending[: size - len(window)]
    _pending_cursor = (start + size) % len(pending)
    return window


def purge_non_universe_rows() -> Dict[str, int]:
    """Drop any leftover Nifty-500 / large-cap rows not in Mid150+Small50."""
    universe = [nse.normalize_ticker(t) for t in nse.load_universe()]
    return db.purge_outside_universe(universe)


def _build_price_row_from_live(
    ticker: str,
    quote: Dict[str, Any],
    prior: Optional[Dict[str, Any]] = None,
    hist: Optional[pd.DataFrame] = None,
    bench: Optional[pd.DataFrame] = None,
) -> Optional[Dict[str, Any]]:
    prior = prior or {}
    px = quote.get("close_price")
    if px is None:
        return None
    px = float(px)
    has_ohlcv = hist is not None and not hist.empty
    if has_ohlcv:
        tech = nse.compute_technicals(hist, bench)
        tech["close_price"] = round(px, 2)
    elif prior.get("ohlcv_ready"):
        # Keep previously computed real technicals; only refresh LTP
        tech = {
            "close_price": round(px, 2),
            "sma_50": float(prior.get("sma_50") or px),
            "sma_200": float(prior.get("sma_200") or px),
            "rsi_14": float(prior.get("rsi_14") or 50.0),
            "atr_value": float(prior.get("atr_value") or max(px * 0.02, 0.05)),
            "alpha_3m": float(prior.get("alpha_3m") or 0.0),
            "delivery_pct_10d": float(prior.get("delivery_pct_10d") or 45.0),
        }
        has_ohlcv = True
    else:
        # Price-only: do NOT invent RSI=50 tech scores (that showed fake Tech=48)
        day_high = float(quote.get("day_high") or px)
        day_low = float(quote.get("day_low") or px)
        atr_est = max(abs(day_high - day_low), px * 0.015, 0.05)
        tech = {
            "close_price": round(px, 2),
            "sma_50": round(px, 2),
            "sma_200": round(px, 2),
            "rsi_14": 50.0,
            "atr_value": round(atr_est, 2),
            "alpha_3m": 0.0,
            "delivery_pct_10d": 0.0,
        }
    src = str(quote.get("source") or "live")
    price_kind = str(quote.get("price_kind") or "LIVE").upper()
    company = quote.get("company_name") or prior.get("company_name") or ticker
    fetched = quote.get("fetched_at") or quote.get("exchange_ts") or ""
    kind_label = {
        "LIVE": "Live LTP",
        "LAST": "Last traded (≈ prev close)",
        "PREV_CLOSE": "Prev close",
    }.get(price_kind, price_kind)
    row: Dict[str, Any] = {
        "ticker": ticker,
        "company_name": company,
        "description": (
            f"{kind_label} via {src}"
            + (f" @ {fetched}" if fetched else "")
            + f". CMP ₹{px:,.2f}."
            + (f" Prev close ₹{quote['prev_close']}." if quote.get("prev_close") else "")
        ),
        "sector": prior.get("sector") or "—",
        "industry": prior.get("industry") or "—",
        "close_price": tech["close_price"],
        "atr_value": tech["atr_value"],
        "sma_50": tech["sma_50"],
        "sma_200": tech["sma_200"],
        "rsi_14": tech["rsi_14"],
        "delivery_pct_10d": tech["delivery_pct_10d"],
        "alpha_3m": tech["alpha_3m"],
        "roic": prior.get("roic"),
        "net_debt_ebitda": prior.get("net_debt_ebitda"),
        "peg_ratio": prior.get("peg_ratio"),
        "interest_coverage": prior.get("interest_coverage"),
        "promoter_pledge_pct": prior.get("promoter_pledge_pct"),
        "yoy_profit_growth": prior.get("yoy_profit_growth"),
        "pe_ratio": prior.get("pe_ratio"),
        "fundamentals_verified": bool(prior.get("fundamentals_verified")),
        "data_quality": prior.get("data_quality") or "UNVERIFIED",
        "sources_ok_count": int(prior.get("sources_ok_count") or 0),
        "price_source": src,
        "price_kind": price_kind,
        "prev_close": quote.get("prev_close") if quote.get("prev_close") is not None else prior.get("prev_close"),
        "ohlcv_ready": bool(has_ohlcv),
    }
    try:
        row["fundamental_score"] = float(prior.get("fundamental_score") or 0)
        if prior.get("fundamentals_verified"):
            row["fundamental_score"] = float(nse._score_fundamental(row))
        if has_ohlcv:
            row["technical_score"] = float(nse._score_technical(row))
        else:
            row["technical_score"] = 0.0
    except Exception:
        row["fundamental_score"] = float(prior.get("fundamental_score") or 0)
        row["technical_score"] = float(prior.get("technical_score") or 0) if has_ohlcv else 0.0
    row["composite_score"] = round(
        float(row["fundamental_score"]) + float(row["technical_score"]), 1
    )
    row["is_buyable"] = (
        1
        if has_ohlcv
        and row["close_price"] > row["sma_200"]
        and row["rsi_14"] <= nse.RSI_OVERBOUGHT
        else 0
    )
    return row


def fill_fundamentals_batch(
    batch_size: int = 12,
    with_ohlcv: bool = True,
    per_ticker_retries: int = 1,
    max_workers: int = 10,
) -> Dict[str, Any]:
    """
    Fetch the next incomplete tickers in parallel.
    Upserts and bumps Ready X/target as soon as each stock becomes fully ready.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    result: Dict[str, Any] = {
        "attempted": 0,
        "filled": 0,
        "newly_complete": 0,
        "failed": [],
        "exhausted": [],
        "message": "",
        "coverage": db.fundamentals_coverage(),
        "elapsed_sec": 0.0,
        "batch_rate_per_min": 0.0,
    }
    if not nse.is_live_mode():
        result["message"] = "Mock mode — fundamentals fill skipped."
        return result

    target = max(len(nse.load_universe()), 1)
    label = nse.universe_label()
    pending = _next_pending_window(max(1, min(int(batch_size), 40)))
    result["attempted"] = len(pending)
    if not pending:
        complete_n = count_fully_complete()
        uni = {nse.normalize_ticker(t) for t in nse.load_universe()}
        failed_n = len(
            [
                f
                for f in db.list_exhausted_load_failures(limit=1000)
                if nse.normalize_ticker(f.get("ticker") or "") in uni
            ]
        )
        result["coverage"] = {
            **db.fundamentals_coverage(),
            "complete": complete_n,
            "failed": failed_n,
        }
        result["message"] = (
            f"No pending retries — ready {complete_n}/{target}, exhausted failures {failed_n}."
        )
        return result

    t0 = time.time()
    bench = nse.fetch_ohlcv(nse.BENCHMARK, range_param="6mo", interval="1d") if with_ohlcv else None
    bench_ok = bench is not None and not getattr(bench, "empty", True)
    filled_n = 0
    failed: List[str] = []
    exhausted: List[str] = []
    newly = 0

    def _load_one(sym: str) -> Tuple[str, Optional[Dict[str, Any]], str]:
        last_err = ""
        row: Optional[Dict[str, Any]] = None
        for _try in range(max(1, int(per_ticker_retries))):
            try:
                prior = db.get_ticker_row(sym)
                prior_dict = prior.to_dict() if prior is not None else {}
                live_px = float(prior_dict.get("close_price") or 0) if prior_dict else 0.0
                row = nse.build_live_row(
                    sym,
                    bench_frame=bench if bench_ok else None,
                    include_fundamentals=True,
                    prior=prior_dict or None,
                )
                if not row:
                    last_err = "build_live_row returned empty"
                    continue
                if live_px > 0:
                    row["close_price"] = live_px
                for k in ("price_kind", "price_source", "prev_close"):
                    if prior_dict.get(k) is not None:
                        row[k] = prior_dict.get(k)
                row["composite_score"] = round(
                    float(row.get("fundamental_score") or 0)
                    + float(row.get("technical_score") or 0),
                    1,
                )
                if row_is_fully_verified(row):
                    return sym, row, ""
                last_err = "incomplete checklist after fetch"
            except Exception as exc:
                last_err = str(exc)
                logger.warning("fill fundamentals failed %s: %s", sym, exc)
                row = None
        return sym, row, last_err or "fetch failed"

    workers = max(2, min(int(max_workers), len(pending), 12))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_load_one, sym) for sym in pending]
        for fut in as_completed(futures):
            try:
                sym, row, last_err = fut.result()
            except Exception as exc:
                logger.warning("parallel fill future failed: %s", exc)
                continue
            if row:
                db.upsert_leaderboard_rows([row])
                filled_n += 1
                if row_is_fully_verified(row):
                    db.record_load_attempt(sym, ok=True)
                    newly += 1
                    complete_n = count_fully_complete()
                    eta_min = db.compute_refresh_eta_minutes(complete_n, target)
                    eta_txt = ""
                    if eta_min is not None and complete_n < target:
                        hrs = int(eta_min // 60)
                        mins = int(round(eta_min % 60))
                        eta_txt = f" · ETA ~{hrs}h {mins}m" if hrs else f" · ETA ~{mins} min"
                    db.set_screener_refresh_state(
                        status="running",
                        message=f"{label}: Ready {complete_n}/{target} (+1 {sym}){eta_txt}",
                    )
                else:
                    meta = db.record_load_attempt(sym, ok=False, error=last_err or "incomplete checklist")
                    failed.append(sym)
                    if meta.get("exhausted"):
                        exhausted.append(sym)
            else:
                meta = db.record_load_attempt(sym, ok=False, error=last_err or "fetch failed")
                failed.append(sym)
                if meta.get("exhausted"):
                    exhausted.append(sym)

    elapsed = max(time.time() - t0, 0.001)
    complete_n = count_fully_complete()
    result["filled"] = filled_n
    result["newly_complete"] = newly
    result["failed"] = failed
    result["exhausted"] = exhausted
    result["elapsed_sec"] = round(elapsed, 1)
    result["batch_rate_per_min"] = round(newly / elapsed * 60.0, 2) if newly else 0.0
    uni = {nse.normalize_ticker(t) for t in nse.load_universe()}
    failed_n = len(
        [
            f
            for f in db.list_exhausted_load_failures(limit=1000)
            if nse.normalize_ticker(f.get("ticker") or "") in uni
        ]
    )
    missing = max(0, target - complete_n)
    eta_min = db.compute_refresh_eta_minutes(complete_n, target)
    result["eta_minutes"] = eta_min
    result["coverage"] = {
        **db.fundamentals_coverage(),
        "complete": complete_n,
        "failed": failed_n,
        "missing": missing,
        "target": target,
    }
    eta_txt = ""
    if eta_min is not None and missing > 0:
        hrs = int(eta_min // 60)
        mins = int(round(eta_min % 60))
        eta_txt = f" ETA ~{hrs}h {mins}m." if hrs else f" ETA ~{mins} min."
    result["message"] = (
        f"+{newly} ready in {result['elapsed_sec']}s "
        f"({label} {complete_n}/{target}, failed {failed_n}).{eta_txt}"
    )
    return result


DAILY_INTERNAL_BATCH = 12


def daily_load_status() -> Dict[str, Any]:
    """
    UI status for today's full load — one truthful counter:
    +1 only when price + fund + tech + checklist are all present.
    """
    # Avoid purging on every status poll (UI refreshes often) — only when board is dirty.
    try:
        have = set(db.list_leaderboard_tickers())
        universe_preview = {nse.normalize_ticker(t) for t in nse.load_universe()}
        if have - universe_preview:
            purge_non_universe_rows()
    except Exception:
        pass

    universe = [nse.normalize_ticker(t) for t in nse.load_universe()]
    universe_set = set(universe)
    target = max(len(universe), 1)
    as_of = db.screener_as_of()
    today = db.today_ist()
    status = db.get_meta(db.META_SCREENER_STATUS, "idle") or "idle"
    message = db.get_meta(db.META_SCREENER_MSG, "") or ""
    is_today = bool(as_of) and as_of == today
    failures = []
    if is_today:
        failures = [
            f
            for f in db.list_exhausted_load_failures(limit=500)
            if nse.normalize_ticker(f.get("ticker") or "") in universe_set
        ]

    if not is_today:
        return {
            "as_of": as_of,
            "today": today,
            "is_today": False,
            "status": "stale" if as_of else "idle",
            "message": message or "New day — click Refresh to load today's data.",
            "target": target,
            "complete": 0,
            "missing": target,
            "failed": 0,
            "failures": [],
            "pct": 0.0,
            "running": False,
            "eta_minutes": None,
        }

    complete = min(count_fully_complete(), target)
    failed_n = len(failures)
    pending = list_incomplete_tickers(limit=target, skip_exhausted=True)
    running = status == "running"
    paused = status == "paused"
    missing = max(0, target - complete)
    eta_min = db.compute_refresh_eta_minutes(complete, target) if (running or missing > 0) else (
        0.0 if complete >= target else None
    )
    # Finished when every name is ready, or only exhausted failures remain
    load_finished = complete >= target or (len(pending) == 0 and not running and complete + failed_n > 0)

    return {
        "as_of": as_of,
        "today": today,
        "is_today": True,
        "status": status,
        "message": message,
        "target": target,
        "complete": complete,
        "missing": missing,
        "failed": failed_n,
        "failures": failures,
        "pending": len(pending),
        "pct": round(100.0 * complete / target, 1),
        "running": running,
        "paused": paused,
        "eta_minutes": eta_min,
        "day_complete": bool(load_finished and complete >= target),
        "load_finished": bool(load_finished),
    }


def begin_daily_refresh(user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    New trading day start: refresh Mid150+Small50 list, wipe screener table, begin full load.
    """
    today = db.today_ist()
    universe: List[str] = []
    if nse.is_live_mode():
        universe = nse.ensure_swing_universe()
    cleared = db.clear_leaderboard()
    db.clear_load_attempts()
    db.start_refresh_eta_clock(complete0=0)
    if not nse.is_live_mode():
        db.ensure_mock_leaderboard()
        # Tag mock rows as fully ready for today's session
        frame = db.get_leaderboard(limit=500)
        if frame is not None and not frame.empty:
            tagged = []
            for _, r in frame.iterrows():
                d = r.to_dict()
                d["data_quality"] = "SOURCED"
                d["fundamentals_verified"] = True
                d["sources_ok_count"] = 2
                d["ohlcv_ready"] = True
                if (d.get("fundamental_score") or 0) <= 0:
                    d["fundamental_score"] = 40.0
                if (d.get("technical_score") or 0) <= 0:
                    d["technical_score"] = 40.0
                tagged.append(d)
            db.upsert_leaderboard_rows(tagged)
        db.set_screener_refresh_state(
            as_of=today,
            status="complete",
            message=f"Mock daily refresh complete for {today}.",
        )
        return {
            "cleared": cleared,
            "as_of": today,
            "status": "complete",
            "message": f"Mock mode — seeded and marked complete for {today}.",
            "user_id": user_id,
        }

    target = max(len(universe) or len(nse.load_universe()), 1)
    label = nse.universe_label()
    db.set_screener_refresh_state(
        as_of=today,
        status="running",
        message=(
            f"Daily refresh started — {label} ({target} names). "
            f"Cleared {cleared} stale rows. Loading prices…"
        ),
    )
    return {
        "cleared": cleared,
        "as_of": today,
        "status": "running",
        "target": target,
        "universe": label,
        "message": (
            f"Reset complete ({cleared} rows cleared). "
            f"Loading {label} ({target}) for {today}…"
        ),
        "user_id": user_id,
    }


def run_daily_refresh_step(
    user_id: Optional[int] = None,
    batch_size: int = DAILY_INTERNAL_BATCH,
) -> Dict[str, Any]:
    """
    One step of today's refresh: fully load the next incomplete swing-universe
    ticker(s). Progress Ready X/target increments as soon as each stock is ready.
    """
    status = daily_load_status()
    result: Dict[str, Any] = {
        "phase": "",
        "done": False,
        "message": "",
        "status": status,
    }
    if not status["is_today"]:
        result["message"] = "Not today's session — click Refresh first."
        return result

    target = int(status["target"])
    complete = int(status["complete"])
    pending_n = int(status.get("pending") or 0)
    step_n = max(8, min(int(batch_size), 16))

    if pending_n > 0 and complete < target:
        result["phase"] = "load"
        fill = fill_fundamentals_batch(
            batch_size=step_n,
            with_ohlcv=True,
            max_workers=10,
        )
        status = daily_load_status()
        result["status"] = status
        result["fill"] = fill
        result["message"] = fill.get("message") or (
            f"Ready {status['complete']}/{target}."
        )
        if status.get("complete", 0) >= target:
            result["done"] = True
            db.set_screener_refresh_state(
                status="complete",
                message=f"{nse.universe_label()} ready — {target}/{target} stocks fully loaded.",
            )
        elif int(status.get("pending") or 0) == 0:
            result["done"] = True
            failed_n = int(status.get("failed") or 0)
            db.set_screener_refresh_state(
                status="complete" if failed_n == 0 else "failed",
                message=(
                    f"Load finished — {status['complete']}/{target} ready"
                    + (f", {failed_n} could not load after retries." if failed_n else ".")
                ),
            )
        return result

    result["phase"] = "done"
    result["done"] = True
    failed_n = int(status.get("failed") or 0)
    result["message"] = (
        f"{nse.universe_label()} ready — {complete}/{target}"
        + (f" ({failed_n} failed after retries)." if failed_n else ".")
    )
    db.set_screener_refresh_state(
        status="complete" if failed_n == 0 else "failed",
        message=result["message"],
    )
    result["status"] = daily_load_status()
    return result


def refresh_verified_live(
    tickers: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    full_universe: bool = True,
    with_ohlcv: bool = True,
    with_fundamentals: bool = False,
) -> Dict[str, Any]:
    """Refresh latest live CMP for full swing universe (Groww/MC/Yahoo)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from providers import live_price_feed as lpf

    result: Dict[str, Any] = {
        "attempted": 0,
        "accepted": 0,
        "rejected": [],
        "reject_reasons": {},
        "clearances": [],
        "message": "",
        "live_mode": nse.is_live_mode(),
        "price_ok": 0,
        "ohlcv_ok": 0,
    }
    if not nse.is_live_mode():
        db.ensure_mock_leaderboard()
        frame = db.get_leaderboard(limit=500)
        if frame is not None and not frame.empty:
            tagged = []
            for _, r in frame.iterrows():
                d = r.to_dict()
                d["data_quality"] = "SOURCED"
                d["fundamentals_verified"] = True
                d["sources_ok_count"] = 2
                d["ohlcv_ready"] = True
                if (d.get("fundamental_score") or 0) <= 0:
                    d["fundamental_score"] = 40.0
                if (d.get("technical_score") or 0) <= 0:
                    d["technical_score"] = 40.0
                tagged.append(d)
            if tagged:
                from engine import factor_engine as factors

                peer_df = factors.compute_peer_relative_valuation(pd.DataFrame(tagged))
                if peer_df is not None and "pe_peer_percentile" in peer_df.columns:
                    tagged = peer_df.to_dict("records")
            db.upsert_leaderboard_rows(tagged)
        db.set_screener_refresh_state(
            as_of=db.today_ist(),
            status="complete",
            message="Mock refresh complete for today.",
        )
        result["accepted"] = db.leaderboard_count()
        result["price_ok"] = result["accepted"]
        result["ohlcv_ok"] = result["accepted"]
        result["message"] = f"Mock refresh — {result['accepted']} rows ready."
        if user_id is not None:
            result["clearances"] = validate_active_signals(int(user_id))
        return result

    if tickers:
        symbols = [nse.normalize_ticker(t) for t in tickers]
    elif full_universe:
        symbols = [nse.normalize_ticker(t) for t in nse.load_universe()]
    else:
        symbols = list(nse.BOOTSTRAP_TICKERS)

    result["attempted"] = len(symbols)
    t0 = time.time()
    try:
        quotes = lpf.fetch_live_quotes_batch(symbols, max_workers=16)
        price_ok = sum(1 for q in quotes.values() if q.get("ok"))
        result["price_ok"] = price_ok

        bench = nse.fetch_ohlcv(nse.BENCHMARK, range_param="6mo", interval="1d") if with_ohlcv else None
        live_syms = [s for s, q in quotes.items() if q.get("ok")]
        hist_map: Dict[str, pd.DataFrame] = {}
        ohlcv_ok = 0
        if with_ohlcv and live_syms:
            def _hist(sym: str):
                try:
                    frame = nse.fetch_ohlcv(sym, range_param="1y", interval="1d")
                    return sym, frame if frame is not None and not frame.empty else None
                except Exception:
                    return sym, None

            with ThreadPoolExecutor(max_workers=10) as pool:
                for fut in as_completed([pool.submit(_hist, s) for s in live_syms]):
                    sym, frame = fut.result()
                    if frame is not None:
                        hist_map[sym] = frame
                        ohlcv_ok += 1
        result["ohlcv_ok"] = ohlcv_ok

        accepted_rows: List[Dict[str, Any]] = []
        rejected: List[str] = []
        reasons: Dict[str, str] = {}
        bench_ok = bench is not None and not getattr(bench, "empty", True)
        for sym in symbols:
            q = quotes.get(sym) or {}
            if not q.get("ok"):
                rejected.append(sym)
                reasons[sym] = "no price (LTP or prev close)"
                continue
            prior = db.get_ticker_row(sym)
            prior_dict = prior.to_dict() if prior is not None else None
            hist = hist_map.get(sym)
            if with_fundamentals:
                row = nse.build_live_row(
                    sym,
                    bench_frame=bench if bench_ok else None,
                    include_fundamentals=True,
                    prior=prior_dict,
                )
                if row:
                    row["close_price"] = float(q["close_price"])
                    row["price_source"] = q.get("source")
                    row["price_kind"] = q.get("price_kind") or "LIVE"
                    if q.get("prev_close") is not None:
                        row["prev_close"] = q.get("prev_close")
            else:
                row = _build_price_row_from_live(
                    sym, q, prior=prior_dict, hist=hist, bench=bench if bench_ok else None
                )
            if row and row_has_live_price(row):
                accepted_rows.append(row)
            else:
                rejected.append(sym)
                reasons[sym] = "row build failed"

        # Peer-relative PE percentile only means anything computed across the
        # whole batch at once (rank against sector-pack peers), so this runs
        # once here — before the upsert is split into 50-row chunks purely
        # for SQL statement size, not for this calculation. See
        # factor_engine.compute_peer_relative_valuation(); rows whose pack
        # has fewer than 5 peers in this batch simply get no percentile
        # (upsert's COALESCE keeps whatever value was already stored, so a
        # small/partial refresh doesn't blank out a good value from an
        # earlier full-universe refresh).
        if accepted_rows:
            from engine import factor_engine as factors

            peer_df = factors.compute_peer_relative_valuation(pd.DataFrame(accepted_rows))
            if peer_df is not None and "pe_peer_percentile" in peer_df.columns:
                accepted_rows = peer_df.to_dict("records")

        for i in range(0, len(accepted_rows), 50):
            db.upsert_leaderboard_rows(accepted_rows[i : i + 50])

        result["accepted"] = len(accepted_rows)
        result["rejected"] = rejected
        result["reject_reasons"] = reasons
        if user_id is not None:
            result["clearances"] = validate_active_signals(int(user_id))
        # Bug fixed 2026-08-26: this live-mode path saved real rows but never
        # updated META_SCREENER_AS_OF, so screener_is_today() (and therefore
        # filter_display_ready/"Ready Today") stayed permanently 0 no matter
        # how much fresh data actually loaded — only the mock-mode branch
        # above and the separate job-queue refresh function called this.
        db.set_screener_refresh_state(
            as_of=db.today_ist(),
            status="complete",
            message=f"Live refresh — {len(accepted_rows)}/{len(symbols)} stocks saved.",
        )
        ready_n = len(filter_display_ready(db.get_leaderboard(limit=1000)))
        elapsed = round(time.time() - t0, 1)
        result["message"] = (
            f"Live Nifty refresh in {elapsed}s — LTP {price_ok}/{len(symbols)} "
            f"(Groww/MC/Yahoo), OHLCV tech {ohlcv_ok}, saved {len(accepted_rows)}, "
            f"table showing {ready_n}."
        )
    except Exception as exc:
        logger.error("refresh_verified_live failed: %s", exc)
        result["message"] = f"Refresh failed: {exc}"
    return result


def refresh_us_verified_live(tickers: Optional[List[str]] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Real, live US refresh — SEC EDGAR fundamentals + Yahoo Finance
    price/technicals, scored through factor_engine_us, then saved with
    market='US'. Mirrors refresh_verified_live's shape (attempted/accepted/
    rejected/message) so the same frontend refresh-status handling works
    for both markets."""
    from providers import us_data_provider as usdp

    result: Dict[str, Any] = {
        "attempted": 0,
        "accepted": 0,
        "rejected": [],
        "reject_reasons": {},
        "clearances": [],
        "message": "",
        "market": "US",
    }
    try:
        outcome = usdp.refresh_universe(tickers=tickers)
        rows = outcome.pop("rows", [])
        result.update(outcome)
        for i in range(0, len(rows), 50):
            db.upsert_leaderboard_rows(rows[i : i + 50])
        if user_id is not None:
            result["clearances"] = validate_active_signals(int(user_id))
        db.set_screener_refresh_state(as_of=db.today_ist(), status="complete", message=result["message"])
        ready_n = len(filter_display_ready(db.get_leaderboard(limit=1000, market="US"), market="US"))
        result["message"] += f" table showing {ready_n}."
    except Exception as exc:
        logger.error("refresh_us_verified_live failed: %s", exc)
        result["message"] = f"US refresh failed: {exc}"
    return result


def universe_coverage() -> Dict[str, Any]:
    """How much of the swing Screener universe is already in the live DB."""
    universe = [nse.normalize_ticker(t) for t in nse.load_universe()]
    have = {nse.normalize_ticker(t) for t in db.list_leaderboard_tickers()}
    missing = [t for t in universe if t not in have]
    return {
        "universe_total": len(universe),
        "in_db": len(have),
        "missing": len(missing),
        "pct": round(100.0 * len(have) / max(len(universe), 1), 1),
        "complete": len(missing) == 0 and len(universe) > 0,
        "missing_tickers": missing,
    }


def progressive_universe_batch(
    batch_size: Optional[int] = None,
    include_fundamentals: bool = False,
    skip_tickers: Optional[List[str]] = None,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Hydrate the next slice of the swing universe into SQLite.
    Safe for Streamlit Cloud: short batches + rerun/fragment — no CLI required.
    """
    if batch_size is None:
        batch_size = int(os.environ.get("MEDALLION_HYDRATE_BATCH", "12"))
    batch_size = max(1, min(int(batch_size), 40))

    coverage = universe_coverage()
    result: Dict[str, Any] = {
        **coverage,
        "batch_attempted": 0,
        "batch_ok": 0,
        "rows_this_batch": 0,
        "attempted_tickers": [],
        "next_offset": 0,
        "message": "",
        "live_mode": nse.is_live_mode(),
    }
    if not nse.is_live_mode():
        db.ensure_mock_leaderboard()
        result["message"] = "Mock mode — progressive live hydrate skipped."
        result["complete"] = True
        return result

    skip = {nse.normalize_ticker(t) for t in (skip_tickers or [])}
    missing = [t for t in coverage["missing_tickers"] if t not in skip]
    if not missing:
        # Either complete, or everything left is temporarily skipped
        if coverage["missing"] == 0:
            result["message"] = (
                f"Universe complete — {coverage['in_db']}/{coverage['universe_total']} names live."
            )
            return result
        result["message"] = (
            f"{coverage['missing']} names temporarily skipped after fetch failures — "
            f"{coverage['in_db']} live. Clear skip / retry later."
        )
        result["complete"] = False
        return result

    start = int(offset) % len(missing)
    rotated = missing[start:] + missing[:start]
    batch = rotated[:batch_size]
    result["batch_attempted"] = len(batch)
    result["attempted_tickers"] = list(batch)
    try:
        rows = nse.refresh_universe_live(
            tickers=batch,
            max_workers=min(6, len(batch)),
            include_fundamentals=include_fundamentals,
            deadline_sec=55.0,
        )
        if rows:
            db.upsert_leaderboard_rows(rows)
        result["batch_ok"] = len(rows)
        result["rows_this_batch"] = len(rows)
        # Advance past this window when nothing landed (avoid hot-looping same symbols)
        result["next_offset"] = 0 if rows else (start + len(batch))
        coverage = universe_coverage()
        result.update({k: coverage[k] for k in (
            "universe_total", "in_db", "missing", "pct", "complete", "missing_tickers"
        )})
        result["message"] = (
            f"Hydrated +{len(rows)} → {coverage['in_db']}/{coverage['universe_total']} "
            f"({coverage['pct']}%)."
        )
    except Exception as exc:
        logger.error("progressive_universe_batch failed: %s", exc)
        result["message"] = f"Hydrate batch error: {exc}"
        result["next_offset"] = start + len(batch)
    return result


def progressive_fundamentals_batch(batch_size: Optional[int] = None) -> Dict[str, Any]:
    """Fill multi-source fundamentals for price-only rows already in DB."""
    if batch_size is None:
        batch_size = int(os.environ.get("MEDALLION_FUND_BATCH", "4"))
    batch_size = max(1, min(int(batch_size), 15))
    result: Dict[str, Any] = {
        "batch_attempted": 0,
        "batch_ok": 0,
        "message": "",
        "remaining_estimate": 0,
    }
    if not nse.is_live_mode():
        result["message"] = "Mock mode — fundamentals hydrate skipped."
        return result

    pending = db.tickers_missing_fundamentals(limit=batch_size)
    # Also estimate remaining
    result["remaining_estimate"] = len(db.tickers_missing_fundamentals(limit=500))
    if not pending:
        result["message"] = "No price-only rows left — fundamentals catch-up idle."
        return result

    result["batch_attempted"] = len(pending)
    ok = 0
    for sym in pending:
        try:
            prior = db.get_ticker_row(sym)
            prior_dict = prior.to_dict() if prior is not None else None
            row = nse.build_live_row(
                sym,
                include_fundamentals=True,
                prior=prior_dict,
            )
            if row:
                db.upsert_leaderboard_rows([row])
                ok += 1
        except Exception as exc:
            logger.warning("fundamentals batch failed %s: %s", sym, exc)
    result["batch_ok"] = ok
    result["remaining_estimate"] = len(db.tickers_missing_fundamentals(limit=500))
    result["message"] = f"Fundamentals filled {ok}/{len(pending)}; ~{result['remaining_estimate']} left."
    return result


def sync_user_and_screener_data(
    user_id: int,
    force: bool = False,
    fast: bool = False,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "skipped_heavy_sync": False,
        "last_updated": None,
        "rows_refreshed": 0,
        "clearances": [],
        "message": "",
        "live_mode": nse.is_live_mode(),
        "fast": fast,
    }
    try:
        db.init_database()
        if nse.is_live_mode() and _looks_like_legacy_mock_board():
            force = True
            fast = True  # first upgrade: bootstrap only so UI is usable quickly
        skip, last_updated = should_skip_heavy_sync()
        result["last_updated"] = last_updated.isoformat(sep=" ") if last_updated else None

        if skip and not force and not db.leaderboard_is_empty():
            result["skipped_heavy_sync"] = True
            result["clearances"] = validate_active_signals(user_id)
            mode = "LIVE NSE" if nse.is_live_mode() else "MOCK"
            result["message"] = (
                f"{mode} cache hit — quotes fresh within {SYNC_COOLDOWN_MINUTES} minutes."
            )
            return result

        result["rows_refreshed"] = refresh_screener_quotes(force=force, fast=fast)
        result["clearances"] = validate_active_signals(user_id)
        fresh_ts = db.get_leaderboard_last_updated()
        result["last_updated"] = fresh_ts.isoformat(sep=" ") if fresh_ts else None
        mode = "LIVE NSE" if nse.is_live_mode() else "MOCK"
        kind = "fast bootstrap" if fast else "full"
        result["message"] = (
            f"{mode} {kind} — refreshed {result['rows_refreshed']} rows, "
            f"{len(result['clearances'])} clearance(s)."
        )
        return result
    except Exception as exc:
        logger.error("sync_user_and_screener_data failed: %s", exc)
        if not nse.is_live_mode() and db.leaderboard_is_empty():
            db.ensure_mock_leaderboard()
        result["message"] = f"Sync degraded: {exc}"
        result["clearances"] = validate_active_signals(user_id)
        return result


def check_buyability(row: pd.Series) -> Tuple[bool, str]:
    close_price = float(row.get("close_price", row.get("cmp", 0.0)))
    sma_200 = float(row.get("sma_200", 0.0))
    rsi_14 = float(row.get("rsi_14", 50.0))
    if close_price <= sma_200:
        return (
            False,
            f"SIGNAL BLOCKED: Price below 200-day SMA "
            f"(₹{close_price:.2f} ≤ ₹{sma_200:.2f}).",
        )
    if rsi_14 > RSI_OVERBOUGHT:
        return (
            False,
            f"⚠️ OVEREXTENDED: 14-Day RSI at {rsi_14:.1f}% "
            f"(threshold {RSI_OVERBOUGHT:.0f}). Signal entry locked.",
        )
    return True, "SIGNAL CLEAR: Passes 200 SMA / RSI filters."


def evaluate_buy_signal(row: Dict[str, Any], scorecard: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    """Multi-gate BUY confluence check (Decision Engine Blueprint 1.1).

    `row` is a leaderboard/live row (dict or Series); `scorecard` is
    factor_engine.full_factor_scorecard(row) — this function doesn't score
    anything itself, it just gates on scores/data already computed elsewhere.
    Every gate must pass; there is no partial-credit BUY. Returns the full
    per-gate breakdown, not just the verdict, so a caller (or a UI) can show
    exactly which condition blocked a signal instead of a bare yes/no.
    """
    ticker = str(row.get("ticker", "")).upper()

    quality = str(row.get("data_quality") or "MISSING").upper()
    gates = [
        {
            "gate": "data_quality",
            "passed": quality in ("SOURCED", "CACHED"),
            "detail": quality,
        }
    ]

    composite_pct = float(scorecard.get("composite_pct") or 0.0)
    gates.append({
        "gate": "composite_floor",
        "passed": composite_pct >= BUY_COMPOSITE_FLOOR_PCT,
        "detail": f"{composite_pct}% (floor {BUY_COMPOSITE_FLOOR_PCT}%)",
    })

    fund_pct = float((scorecard.get("fundamental") or {}).get("pct") or 0.0)
    gates.append({
        "gate": "fundamental_floor",
        "passed": fund_pct >= BUY_FUNDAMENTAL_FLOOR_PCT,
        "detail": f"{fund_pct}% (floor {BUY_FUNDAMENTAL_FLOOR_PCT}%)",
    })

    close = float(row.get("close_price") or 0.0)
    sma_200 = float(row.get("sma_200") or 0.0)
    rsi_14 = float(row.get("rsi_14") or 50.0)
    trend_ok = close > sma_200 and rsi_14 <= RSI_OVERBOUGHT
    gates.append({
        "gate": "technical_trend",
        "passed": trend_ok,
        "detail": f"close={close:.2f} vs 200SMA={sma_200:.2f}, RSI={rsi_14:.1f}",
    })

    pe_pctl = row.get("pe_peer_percentile")
    peg = row.get("peg_ratio")
    pe_pctl_f = float(pe_pctl) if pe_pctl is not None else None
    peg_f = float(peg) if peg is not None else None
    valuation_ok = (pe_pctl_f is not None and pe_pctl_f <= BUY_PE_PEER_PERCENTILE_MAX) or (
        peg_f is not None and peg_f <= BUY_PEG_MAX
    )
    gates.append({
        "gate": "relative_valuation",
        "passed": valuation_ok,
        "detail": f"PE percentile={pe_pctl_f}, PEG={peg_f}",
    })

    active = db.get_active_positions(user_id)
    open_count = 0 if active is None or active.empty else len(active)
    already_open = bool(
        active is not None and not active.empty
        and ticker in set(active["ticker"].astype(str).str.upper())
    )
    gates.append({
        "gate": "position_budget",
        "passed": (not already_open) and open_count < MAX_CONCURRENT_POSITIONS,
        "detail": f"{open_count}/{MAX_CONCURRENT_POSITIONS} open, already_open={already_open}",
    })

    all_passed = all(g["passed"] for g in gates)
    return {
        "ticker": ticker,
        "signal": "BUY" if all_passed else "NO_SIGNAL",
        "gates": gates,
        "blocked_by": [g["gate"] for g in gates if not g["passed"]],
    }


def _invalid_trade_levels() -> Dict[str, Any]:
    return {
        "stop_loss": None,
        "target": None,
        "risk": None,
        "reward": None,
        "rrr": None,
        "quantity": 0,
        "recommended_quantity_at_1pct_risk": 0,
        "valid": False,
    }


def build_trade_levels(close_price: float, atr: float) -> Dict[str, Any]:
    """Initial stop/target only — see compute_trailing_stop() for what
    actually manages the position after entry. 2.5x ATR sits at the upper
    edge of the well-documented 1.5-2.5x swing-trade band (Turtle system
    uses 2N = 2x); kept as-is, it's defensible. The 6.0x target is no longer
    a forced exit (see validate_active_signals) — it's the level that flips
    the trailing stop from its wider 3x-ATR "initial" band to a tighter
    2x-ATR "runner" band, so a genuine trend isn't capped at a fixed R:R.

    Returns valid=False (all levels None) rather than a nonsensical result
    when the inputs can't support a real trade: non-finite close/ATR (a
    stress test caught NaN ATR silently producing a NaN "stop_loss" that
    looks like a real number until it hits JSON serialization), or a
    close price low enough / ATR wide enough that a 2.5x-ATR stop would
    sit at or below zero — not a sellable price. Callers should treat
    valid=False the same as "no trade levels available", matching how
    routes/profile.py already treats a missing/zero ATR.
    """
    if not (
        isinstance(close_price, (int, float))
        and isinstance(atr, (int, float))
        and math.isfinite(close_price)
        and math.isfinite(atr)
        and close_price > 0
        and atr > 0
    ):
        return _invalid_trade_levels()

    stop_loss = close_price - (2.5 * atr)
    if stop_loss <= 0:
        return _invalid_trade_levels()

    target = close_price + (6.0 * atr)
    risk = close_price - stop_loss
    reward = target - close_price
    rrr = (reward / risk) if risk > 0 else 0.0
    recommended_quantity = (
        math.floor((DEFAULT_CAPITAL_BASE * RISK_PCT_PER_TRADE) / risk) if risk > 0 else 0
    )
    return {
        "stop_loss": round(stop_loss, 2),
        "target": round(target, 2),
        "risk": round(risk, 2),
        "reward": round(reward, 2),
        "rrr": round(rrr, 2),
        "quantity": FIXED_QUANTITY,
        "recommended_quantity_at_1pct_risk": recommended_quantity,
        "valid": True,
    }


def compute_trailing_stop(
    entry_price: float,
    initial_stop: float,
    atr_current: float,
    highest_price_since_entry: float,
    current_price: float,
    target: float,
    trail_phase: str = "initial",
) -> Dict[str, Any]:
    """Chandelier-style ratcheting stop layered on the fixed initial stop.

    Never loosens: the effective stop is always max(initial_stop, trail).
    Once the high-water mark has ever reached the original target, phase
    flips to 'runner' and the trail tightens from 3x to 2x ATR — this is
    what replaces the old "hit target -> force close" behaviour, so a
    trend-following checklist isn't fighting its own fixed-target exit.
    """
    highest = max(float(highest_price_since_entry or entry_price), float(current_price))
    phase = "runner" if (trail_phase == "runner" or highest >= target) else "initial"
    multiplier = CHANDELIER_MULTIPLIER_RUNNER if phase == "runner" else CHANDELIER_MULTIPLIER_INITIAL
    if atr_current and atr_current > 0:
        trailing_stop = highest - (multiplier * atr_current)
    else:
        trailing_stop = initial_stop
    effective_stop = max(float(initial_stop), trailing_stop)
    return {
        "highest_price_since_entry": round(highest, 2),
        "stop_loss": round(effective_stop, 2),
        "trail_phase": phase,
    }


def generate_price_history(ticker: str, close_price: float, periods: int = 250) -> pd.DataFrame:
    """Prefer live NSE OHLC; fall back to synthetic series only in mock mode / total failure."""
    if nse.is_live_mode():
        live = nse.fetch_chart_history(ticker, periods=periods)
        if live is not None and not live.empty:
            return live

    dates = pd.date_range(end=datetime.now(), periods=periods, freq="D")
    seed = abs(hash(str(ticker).upper())) % (2**32)
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0005, 0.015, periods)
    prices = close_price * np.exp(np.cumsum(returns))
    if prices[-1] != 0:
        prices = prices * (close_price / prices[-1])
    opens = prices * (1.0 + rng.uniform(-0.01, 0.01, periods))
    highs = np.maximum(prices, opens) * (1.0 + np.abs(rng.normal(0, 0.008, periods)))
    lows = np.minimum(prices, opens) * (1.0 - np.abs(rng.normal(0, 0.008, periods)))
    volumes = rng.lognormal(mean=16.0, sigma=0.5, size=periods).astype(int)
    return pd.DataFrame(
        {"date": dates, "open": opens, "high": highs, "low": lows, "close": prices, "volume": volumes}
    )


def compute_sma(prices: np.ndarray, period: int) -> np.ndarray:
    if len(prices) < period:
        return np.array([])
    return np.convolve(prices, np.ones(period) / period, mode="valid")


def compute_rsi_series(prices: np.ndarray, period: int = 14) -> Tuple[np.ndarray, np.ndarray]:
    if len(prices) <= period:
        return np.array([]), np.array([])
    deltas = np.diff(prices)
    rsi_values: List[float] = []
    for i in range(period, len(prices)):
        window = deltas[i - period : i]
        gains = window[window >= 0].sum() / period
        losses = -window[window < 0].sum() / period
        rsi = 100.0 if losses == 0 else 100.0 - (100.0 / (1.0 + gains / losses))
        rsi_values.append(float(rsi))
    return np.arange(period, len(prices)), np.asarray(rsi_values, dtype=float)


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime()
        except Exception:
            pass
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def enrich_closed_trade_row(row: pd.Series) -> Dict[str, Any]:
    entry = float(row.get("entry_price", 0.0) or 0.0)
    exit_px = float(row.get("exit_price", 0.0) or 0.0)
    qty = int(row.get("quantity") or FIXED_QUANTITY)
    pnl = float(row.get("final_pnl") if row.get("final_pnl") is not None else (exit_px - entry) * qty)
    pct = ((exit_px - entry) / entry * 100.0) if entry > 0 else 0.0
    entry_dt = _parse_dt(row.get("entry_timestamp") or row.get("entry_date"))
    exit_dt = _parse_dt(row.get("exit_timestamp") or row.get("exit_date"))
    days = 0
    if entry_dt and exit_dt:
        days = max(int((exit_dt - entry_dt).total_seconds() // 86400), 0)
    status = str(row.get("exit_status") or row.get("exit_reason") or "")
    return {
        "ticker": str(row.get("ticker", "")),
        "exit_status": status,
        "absolute_delta": round(pnl, 2),
        "pct_return": round(pct, 2),
        "days_elapsed": days,
        "velocity_label": f"Achieved in {days} Day{'s' if days != 1 else ''}",
        "entry_price": entry,
        "exit_price": exit_px,
        "entry_timestamp": row.get("entry_timestamp"),
        "exit_timestamp": row.get("exit_timestamp"),
    }


def _wilson_interval(successes: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval on a win rate, in percent. A raw win rate
    with no interval is a misleading number at forward-test sample sizes —
    see Decision Engine Blueprint 1.3. Returns (0, 0) for n=0."""
    if n <= 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    lower = max(0.0, (center - margin) / denom)
    upper = min(1.0, (center + margin) / denom)
    return (round(lower * 100, 1), round(upper * 100, 1))


def _equity_curve_max_drawdown(trade_rows: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Walks closed trades in exit order, tracks the running cumulative P&L
    peak, and returns the worst peak-to-trough drop. This is the number that
    actually answers "can I survive running this strategy live" — the
    scorecard previously only had aggregate totals, no running curve."""
    dated = [
        t for t in trade_rows
        if t.get("exit_timestamp") and t.get("absolute_delta") is not None
    ]
    dated.sort(key=lambda t: str(t["exit_timestamp"]))
    if not dated:
        return {"max_drawdown_rupee": None, "max_drawdown_pct": None}

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    max_dd_pct = 0.0
    for t in dated:
        cumulative += float(t["absolute_delta"])
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_dd = max(max_dd, drawdown)
        if peak > 0:
            max_dd_pct = max(max_dd_pct, drawdown / peak * 100)
    return {"max_drawdown_rupee": round(max_dd, 2), "max_drawdown_pct": round(max_dd_pct, 1)}


def compute_forward_test_scorecard(user_id: int, market: Optional[str] = None) -> Dict[str, Any]:
    closed = db.get_closed_trades(user_id, market=market)
    active = db.get_active_positions(user_id, market=market)
    total = 0 if closed is None or closed.empty else len(closed)
    successful = 0
    bad = 0
    total_rupee = 0.0
    hold_days: List[float] = []
    trade_rows: List[Dict[str, Any]] = []
    velocity_buckets = {"FAST": 0, "NORMAL": 0, "SLOW": 0, "OTHER": 0}

    if total > 0:
        for _, row in closed.iterrows():
            if int(row.get("user_id", user_id)) != int(user_id):
                continue
            enriched = enrich_closed_trade_row(row)
            trade_rows.append(enriched)
            status = enriched["exit_status"].upper()
            if status == db.EXIT_SUCCESS.upper() or status == "TARGET_HIT":
                successful += 1
            elif status == db.EXIT_BAD.upper() or "STOP" in status:
                bad += 1
            total_rupee += float(enriched["absolute_delta"])
            vel = str(enriched.get("velocity_label") or "OTHER").upper()
            if "FAST" in vel:
                velocity_buckets["FAST"] += 1
            elif "SLOW" in vel:
                velocity_buckets["SLOW"] += 1
            elif "NORMAL" in vel or "MED" in vel:
                velocity_buckets["NORMAL"] += 1
            else:
                velocity_buckets["OTHER"] += 1
            # holding period if timestamps exist
            try:
                entry_ts = enriched.get("entry_timestamp") or row.get("entry_timestamp")
                exit_ts = enriched.get("exit_timestamp") or row.get("exit_timestamp")
                if entry_ts and exit_ts:
                    from datetime import datetime as _dt

                    def _parse(x):
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                            try:
                                return _dt.strptime(str(x)[:19], fmt)
                            except Exception:
                                continue
                        return None

                    a, b = _parse(entry_ts), _parse(exit_ts)
                    if a and b and b >= a:
                        hold_days.append((b - a).total_seconds() / 86400.0)
            except Exception:
                pass

    win_rate = (successful / total * 100.0) if total > 0 else 0.0
    win_rate_ci = _wilson_interval(successful, total)
    avg_hold = round(sum(hold_days) / len(hold_days), 1) if hold_days else None
    expectancy = round(total_rupee / total, 2) if total > 0 else 0.0
    open_n = 0 if active is None or active.empty else len(active[active["user_id"] == user_id]) if "user_id" in active.columns else len(active)

    gross_wins = sum(float(t["absolute_delta"]) for t in trade_rows if float(t.get("absolute_delta") or 0) > 0)
    gross_losses = abs(sum(float(t["absolute_delta"]) for t in trade_rows if float(t.get("absolute_delta") or 0) < 0))
    # None (not Infinity) when there are wins and zero losses yet — "undefined
    # so far", not a JSON-illegal float. A JSON encoder would happily emit
    # literal `Infinity` here, which isn't valid JSON for any strict parser.
    profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else None
    drawdown = _equity_curve_max_drawdown(trade_rows)

    # Score-bucket style placeholder using % return terciles of closed trades
    buckets = {"high_return": 0, "mid_return": 0, "low_return": 0}
    if trade_rows:
        rets = sorted(float(t.get("pct_return") or 0) for t in trade_rows)
        if len(rets) >= 3:
            q1 = rets[len(rets) // 3]
            q2 = rets[(2 * len(rets)) // 3]
            for t in trade_rows:
                r = float(t.get("pct_return") or 0)
                if r >= q2:
                    buckets["high_return"] += 1
                elif r >= q1:
                    buckets["mid_return"] += 1
                else:
                    buckets["low_return"] += 1

    return {
        "total_signals_tracked": total,
        "successful_trades": successful,
        "bad_trades": bad,
        "open_signals": open_n,
        "win_rate_pct": round(win_rate, 2),
        "win_rate_ci_95": {"low": win_rate_ci[0], "high": win_rate_ci[1]},
        "total_realized_rupee_return": round(total_rupee, 2),
        "expectancy_rupee": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown_rupee": drawdown["max_drawdown_rupee"],
        "max_drawdown_pct": drawdown["max_drawdown_pct"],
        "avg_hold_days": avg_hold,
        "velocity_buckets": velocity_buckets,
        "return_buckets": buckets,
        "trades": trade_rows,
    }
