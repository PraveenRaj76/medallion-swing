"""
Live NSE cash quotes via Angel One SmartAPI (official broker API).

Replaces the previous Groww / Moneycontrol / Yahoo scraping approach.
Why: those were unofficial, reverse-engineered endpoints with no SLA — they
broke silently whenever the source website changed its frontend, and got
rate-limited/blocked on shared cloud IPs at 200-stock scale. Angel One's
SmartAPI is a real, documented, SEBI-regulated broker API: one authenticated
session, official rate limits, and a single batched call covers up to 50
symbols at a time (so 200 stocks = 4 requests, not 200-600).

SETUP REQUIRED (one-time):
  1. Create a free Angel One trading account if you don't have one.
  2. Go to https://smartapi.angelbroking.in/ and create an API app
     (choose "Market Feeds" app type) to get an API key.
  3. Enable TOTP-based login on your Angel One account (Angel app > Settings
     > TOTP) and save the TOTP secret shown as a QR/text code.
  4. Add these to .streamlit/secrets.toml (or Streamlit Cloud secrets):
       ANGEL_API_KEY      = "..."
       ANGEL_CLIENT_ID    = "your Angel One client code, e.g. A123456"
       ANGEL_PASSWORD     = "your Angel One login PIN"
       ANGEL_TOTP_SECRET  = "the base32 TOTP secret from step 3"
  5. pip install smartapi-python pyotp

Public functions kept identical to the previous version so nothing else in
the app needs to change:
    fetch_live_quote(ticker) -> dict
    fetch_live_quotes_batch(tickers, max_workers=16) -> dict[ticker, dict]
Both return the same field names as before (close_price, prev_close,
day_high, day_low, day_change, day_change_pct, open, volume, price_kind,
sources_checked, fetched_at) so downstream code (factor_engine, app.py,
data_pipeline.py) does not need modification.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ANGEL_API_KEY = os.environ.get("ANGEL_API_KEY", "").strip()
ANGEL_CLIENT_ID = os.environ.get("ANGEL_CLIENT_ID", "").strip()
ANGEL_PASSWORD = os.environ.get("ANGEL_PASSWORD", "").strip()
ANGEL_TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET", "").strip()
ANGEL_CONFIGURED = bool(ANGEL_API_KEY and ANGEL_CLIENT_ID and ANGEL_PASSWORD and ANGEL_TOTP_SECRET)

SCRIP_MASTER_URL = (
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
)
_SCRIP_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "angel_scrip_master.json"
)
_SCRIP_CACHE_MAX_AGE_SEC = 24 * 3600  # instrument tokens rarely change; refresh daily

_session_lock = threading.Lock()
_session: Dict[str, Any] = {"smart": None, "jwt": None, "logged_in_at": 0.0}
_scrip_lock = threading.Lock()
_scrip_map: Optional[Dict[str, str]] = None  # NSE trading symbol -> symboltoken

QUOTE_BATCH_SIZE = 50  # Angel One's documented per-call symbol limit


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _num(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Instrument master (ticker -> Angel One symboltoken)
# --------------------------------------------------------------------------
def _load_scrip_map() -> Dict[str, str]:
    """Angel One requires a numeric 'symboltoken' per instrument, not just the
    trading symbol. They publish the full instrument list as one JSON file;
    we cache it locally for a day so we don't re-download ~15MB every run."""
    global _scrip_map
    with _scrip_lock:
        if _scrip_map is not None:
            return _scrip_map

        import json

        if os.path.exists(_SCRIP_CACHE_PATH):
            age = time.time() - os.path.getmtime(_SCRIP_CACHE_PATH)
            if age < _SCRIP_CACHE_MAX_AGE_SEC:
                try:
                    with open(_SCRIP_CACHE_PATH, "r", encoding="utf-8") as fh:
                        _scrip_map = json.load(fh)
                        return _scrip_map
                except Exception:
                    pass

        import requests

        mapping: Dict[str, str] = {}
        try:
            resp = requests.get(SCRIP_MASTER_URL, timeout=60)
            resp.raise_for_status()
            for item in resp.json():
                if item.get("exch_seg") != "NSE":
                    continue
                sym = str(item.get("symbol", ""))
                if sym.endswith("-EQ"):
                    mapping[sym[:-3].upper()] = str(item.get("token"))
        except Exception as exc:
            logger.error("Angel One scrip master download failed: %s", exc)

        if mapping:
            try:
                os.makedirs(os.path.dirname(_SCRIP_CACHE_PATH), exist_ok=True)
                with open(_SCRIP_CACHE_PATH, "w", encoding="utf-8") as fh:
                    json.dump(mapping, fh)
            except Exception as exc:
                logger.warning("could not cache scrip master locally: %s", exc)

        _scrip_map = mapping
        return _scrip_map


# --------------------------------------------------------------------------
# Session (login once, reuse the JWT until it's ~near expiry)
# --------------------------------------------------------------------------
def _get_session():
    """Returns a logged-in SmartConnect client, reusing the session across
    calls within the same process. Angel One JWTs are valid for hours, so we
    only re-login if we don't have one yet."""
    with _session_lock:
        if _session["smart"] is not None:
            return _session["smart"]

        if not ANGEL_CONFIGURED:
            logger.error(
                "Angel One credentials not set (ANGEL_API_KEY / ANGEL_CLIENT_ID / "
                "ANGEL_PASSWORD / ANGEL_TOTP_SECRET) — live quotes unavailable."
            )
            return None

        try:
            import pyotp
            from SmartApi import SmartConnect
        except ImportError:
            logger.error(
                "smartapi-python / pyotp not installed. Run: "
                "pip install smartapi-python pyotp"
            )
            return None

        try:
            smart = SmartConnect(api_key=ANGEL_API_KEY)
            totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
            data = smart.generateSession(ANGEL_CLIENT_ID, ANGEL_PASSWORD, totp)
            if not data or not data.get("status"):
                logger.error("Angel One login failed: %s", data)
                return None
            _session["smart"] = smart
            _session["jwt"] = data["data"]["jwtToken"]
            _session["logged_in_at"] = time.time()
            return smart
        except Exception as exc:
            logger.error("Angel One login raised: %s", exc)
            return None


def _reset_session() -> None:
    with _session_lock:
        _session["smart"] = None
        _session["jwt"] = None


# --------------------------------------------------------------------------
# Public API (same shape as the previous scraper-based version)
# --------------------------------------------------------------------------
def _fetch_yahoo_quotes_batch(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fallback batch quotes when Angel One isn't configured/reachable.

    Reuses nse_data_provider.fetch_ohlcv (the same Yahoo path already proven
    live throughout this codebase for Search Profile / the checklist), run
    in parallel. This is deliberately the fallback, not the default: the
    module docstring's own history is that a Yahoo/scrape-based batch quote
    path got rate-limited at 200-stock scale on shared cloud IPs, which is
    exactly why Angel One replaced it. Without Angel One credentials,
    though, the alternative isn't "reliable Angel One data" vs "unreliable
    Yahoo data" — it's "unreliable Yahoo data" vs "zero data, every time,"
    since the batch refresh otherwise fails 100% of symbols outright. A
    partial, rate-limit-risked real feed is strictly better than that.
    """
    import nse_data_provider as ndp
    from concurrent.futures import ThreadPoolExecutor

    out: Dict[str, Dict[str, Any]] = {}

    def _one(sym: str) -> tuple:
        try:
            frame = ndp.fetch_ohlcv(sym, range_param="5d", interval="1d")
        except Exception as exc:
            return sym, None, str(exc)
        if frame is None or frame.empty:
            return sym, None, "no OHLCV from Yahoo"
        return sym, frame, None

    with ThreadPoolExecutor(max_workers=16) as pool:
        for sym, frame, err in pool.map(_one, symbols):
            if frame is None:
                out[sym] = {"source": "yahoo", "ok": False, "ticker": sym,
                            "price_kind": None, "error": err or "no data"}
                continue
            last = frame.iloc[-1]
            prev = float(frame["close"].iloc[-2]) if len(frame) >= 2 else None
            close = float(last["close"])
            out[sym] = {
                "source": "yahoo",
                "ok": True,
                "ticker": sym,
                "close_price": round(close, 2),
                "prev_close": round(prev, 2) if prev is not None else None,
                "day_high": float(last["high"]) if "high" in last else None,
                "day_low": float(last["low"]) if "low" in last else None,
                "open": float(last["open"]) if "open" in last else None,
                "day_change": round(close - prev, 2) if prev is not None else None,
                "day_change_pct": round((close - prev) / prev * 100, 2) if prev else None,
                "volume": float(last["volume"]) if "volume" in last else None,
                "price_kind": "LAST",  # end-of-day bar, not a true intraday LTP
                "sources_checked": ["yahoo"],
                "fetched_at": _now_iso(),
            }
    return out


def fetch_live_quotes_batch(
    tickers: List[str],
    max_workers: int = 16,  # kept for signature compatibility; unused for the
                              # Angel One path — its batched quote endpoint
                              # covers up to 50 symbols per call. Used
                              # directly by the Yahoo fallback below.
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    symbols = [t.strip().upper() for t in tickers if t and str(t).strip()]
    if not symbols:
        return out

    if not ANGEL_CONFIGURED:
        logger.info("Angel One not configured — falling back to Yahoo for %d symbols", len(symbols))
        return _fetch_yahoo_quotes_batch(symbols)

    smart = _get_session()
    if smart is None:
        logger.info("Angel One login failed — falling back to Yahoo for %d symbols", len(symbols))
        return _fetch_yahoo_quotes_batch(symbols)

    scrip_map = _load_scrip_map()
    tokens: List[str] = []
    token_to_symbol: Dict[str, str] = {}
    for sym in symbols:
        token = scrip_map.get(sym)
        if token:
            tokens.append(token)
            token_to_symbol[token] = sym
        else:
            out[sym] = {"source": "angelone", "ok": False, "ticker": sym, "price_kind": None,
                        "error": "symbol not found in Angel One instrument master"}

    # Angel One's quote endpoint accepts up to QUOTE_BATCH_SIZE tokens/call.
    for i in range(0, len(tokens), QUOTE_BATCH_SIZE):
        chunk = tokens[i : i + QUOTE_BATCH_SIZE]
        try:
            resp = smart.getMarketData(mode="FULL", exchangeTokens={"NSE": chunk})
        except Exception as exc:
            logger.warning("Angel One quote batch failed, retrying session once: %s", exc)
            _reset_session()
            smart = _get_session()
            if smart is None:
                for tok in chunk:
                    sym = token_to_symbol[tok]
                    out[sym] = {"source": "angelone", "ok": False, "ticker": sym,
                                "price_kind": None, "error": "session lost"}
                continue
            try:
                resp = smart.getMarketData(mode="FULL", exchangeTokens={"NSE": chunk})
            except Exception as exc2:
                for tok in chunk:
                    sym = token_to_symbol[tok]
                    out[sym] = {"source": "angelone", "ok": False, "ticker": sym,
                                "price_kind": None, "error": str(exc2)}
                continue

        fetched = ((resp or {}).get("data") or {}).get("fetched") or []
        seen = set()
        for row in fetched:
            token = str(row.get("symbolToken") or "")
            sym = token_to_symbol.get(token)
            if not sym:
                continue
            seen.add(sym)
            ltp = _num(row.get("ltp"))
            prev = _num(row.get("close"))  # Angel One FULL mode: "close" = prev day close
            if ltp is None or ltp <= 0:
                out[sym] = {"source": "angelone", "ok": False, "ticker": sym,
                            "price_kind": None, "error": "no LTP in response"}
                continue
            price_kind = "LIVE"
            if prev is not None and abs(ltp - prev) < 0.005:
                price_kind = "LAST"
            out[sym] = {
                "source": "angelone",
                "ok": True,
                "ticker": sym,
                "close_price": round(ltp, 2),
                "prev_close": round(prev, 2) if prev is not None else None,
                "day_high": _num(row.get("high")),
                "day_low": _num(row.get("low")),
                "open": _num(row.get("open")),
                "day_change": _num(row.get("netChange")),
                "day_change_pct": _num(row.get("percentChange")),
                "volume": _num(row.get("tradeVolume")),
                "price_kind": price_kind,
                "sources_checked": ["angelone"],
                "fetched_at": _now_iso(),
            }
        for tok in chunk:
            sym = token_to_symbol[tok]
            if sym not in seen and sym not in out:
                out[sym] = {"source": "angelone", "ok": False, "ticker": sym,
                            "price_kind": None, "error": "not in Angel One response"}

    return out


def fetch_live_quote(ticker: str) -> Dict[str, Any]:
    """Single-symbol convenience wrapper around the batch call, kept for
    backward compatibility with call sites that fetch one ticker at a time."""
    symbol = ticker.strip().upper()
    result = fetch_live_quotes_batch([symbol])
    return result.get(symbol, {"source": "none", "ok": False, "ticker": symbol, "price_kind": None})
