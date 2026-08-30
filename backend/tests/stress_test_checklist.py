"""
Adversarial stress test for the fundamental + technical checklist scoring
engine (engine/factor_engine.py, engine/factor_engine_us.py) and the trade-
level/buy-gate math in engine/data_pipeline.py.

Unlike e2e_regression.py (which exercises the HAPPY PATH end-to-end through
realistic mock data), this file feeds deliberately broken/extreme inputs —
NaN, Infinity, None, negative numbers, zeros, boundary values — straight
into the scoring functions to answer one question: does a bad or extreme
number ever produce a wrong PASS/score instead of either (a) being cleanly
treated as missing, or (b) crashing loudly where a human would notice,
rather than (c) silently scoring a stock as good when the input was
garbage. (c) is the dangerous failure mode for a tool a real trader acts
on with real money.

Run with (from backend/tests/): python stress_test_checklist.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from engine import factor_engine as fe  # noqa: E402
from engine import factor_engine_us as feus  # noqa: E402
from engine import data_pipeline as pipe  # noqa: E402
from providers import nse_data_provider as nse  # noqa: E402

PASS = 0
FAIL = 0
FINDINGS: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"[PASS] {label}" + (f"\n        {detail}" if detail else ""))
    else:
        FAIL += 1
        FINDINGS.append(f"{label} — {detail}")
        print(f"[FAIL] {label}\n        {detail}")


def run_no_crash(label: str, fn, *args, **kwargs):
    """Call fn; report a FAIL if it raises instead of degrading gracefully."""
    try:
        result = fn(*args, **kwargs)
        check(label, True, "no exception")
        return result
    except Exception as exc:
        check(label, False, f"raised {type(exc).__name__}: {exc}")
        return None


print("=== 1. Empty / None row — must not crash ===")
run_no_crash("evaluate_fundamental_checklist(None)", fe.evaluate_fundamental_checklist, None)
run_no_crash("evaluate_fundamental_checklist({})", fe.evaluate_fundamental_checklist, {})
run_no_crash("evaluate_technical_checklist({})", fe.evaluate_technical_checklist, {})
run_no_crash("evaluate_us_fundamental_checklist({})", feus.evaluate_us_fundamental_checklist, {})
run_no_crash("evaluate_us_technical_checklist({})", feus.evaluate_us_technical_checklist, {})

empty_result = fe.evaluate_fundamental_checklist({})
check(
    "Empty row scores as MISSING, not a silent pass",
    empty_result.get("data_quality") == "MISSING" and empty_result.get("total_marks") == 0.0,
    f"got data_quality={empty_result.get('data_quality')} total_marks={empty_result.get('total_marks')}",
)

print("\n=== 2. NaN in every numeric field — must not crash, must not silently score ===")
nan_row = {
    "data_quality": "SOURCED",
    "sector": "Information Technology",
    "roic": float("nan"),
    "roe": float("nan"),
    "net_debt_ebitda": float("nan"),
    "peg_ratio": float("nan"),
    "yoy_profit_growth": float("nan"),
    "interest_coverage": float("nan"),
    "promoter_pledge_pct": float("nan"),
    "pe_ratio": float("nan"),
    "pb_ratio": float("nan"),
    "close_price": float("nan"),
    "sma_50": float("nan"),
    "sma_200": float("nan"),
    "rsi_14": float("nan"),
    "atr_value": float("nan"),
    "alpha_3m": float("nan"),
    "delivery_pct_10d": float("nan"),
}
nan_fund = run_no_crash("evaluate_fundamental_checklist(all-NaN row)", fe.evaluate_fundamental_checklist, nan_row)
nan_tech = run_no_crash("evaluate_technical_checklist(all-NaN row)", fe.evaluate_technical_checklist, nan_row)
if nan_fund:
    bad_items = [i for i in nan_fund["items"] if i["passed"] and "nan" in str(i["value"]).lower()]
    check(
        "No fundamental item PASSES while displaying 'nan'",
        len(bad_items) == 0,
        f"{len(bad_items)} offending item(s): {[i['name'] for i in bad_items]}",
    )
if nan_tech:
    bad_items = [i for i in nan_tech["items"] if i["passed"] and "nan" in str(i["value"]).lower()]
    check(
        "No technical item PASSES while displaying 'nan'",
        len(bad_items) == 0,
        f"{len(bad_items)} offending item(s): {[i['name'] for i in bad_items]}",
    )

print("\n=== 3. Infinity — NOT caught by the isnan() guards in _f()/_optional() ===")
inf_row = {
    "data_quality": "SOURCED",
    "sector": "Information Technology",
    "roic": float("inf"),
    "net_debt_ebitda": 1.0,
    "peg_ratio": 0.5,
    "yoy_profit_growth": 25.0,
    "interest_coverage": float("inf"),
    "promoter_pledge_pct": 0.0,
    "pe_ratio": 10.0,
    "pb_ratio": 1.0,
}
inf_result = run_no_crash("evaluate_fundamental_checklist(Infinity ROIC/interest-coverage)", fe.evaluate_fundamental_checklist, inf_row)
if inf_result:
    roic_item = next((i for i in inf_result["items"] if "ROCE" in i["name"] or "ROIC" in i["name"] or "ROE" in i["name"]), None)
    ic_item = next((i for i in inf_result["items"] if "Interest Coverage" in i["name"]), None)

    def awarded_real_credit(item) -> bool:
        # An item can be passed=True with max_marks=0 (the "N/A — skipped,
        # doesn't block" pattern used throughout this file for genuinely
        # inapplicable metrics) — that's a neutral no-op, not credit. Real
        # false-positive credit is passed=True AND max_marks>0 AND marks>0.
        if item is None:
            return False
        return bool(item["passed"]) and float(item["max_marks"]) > 0 and float(item["marks"]) > 0

    check(
        "Infinite ROIC/ROE does NOT get scored as a real pass",
        not awarded_real_credit(roic_item),
        f"item={roic_item}",
    )
    check(
        "Infinite Interest Coverage does NOT get scored as a real pass",
        not awarded_real_credit(ic_item),
        f"item={ic_item}",
    )

print("\n=== 4. Negative values where only positive is meaningful ===")
neg_row = {
    "data_quality": "SOURCED",
    "close_price": -50.0,
    "sma_50": 100.0,
    "sma_200": 100.0,
    "rsi_14": 50.0,
    "atr_value": -5.0,
    "alpha_3m": 0.0,
}
neg_result = run_no_crash("evaluate_technical_checklist(negative close_price/ATR)", fe.evaluate_technical_checklist, neg_row)
if neg_result:
    atr_item = next((i for i in neg_result["items"] if "ATR" in i["name"]), None)
    check(
        "Negative ATR% doesn't get scored as a healthy 1-4.5% band",
        atr_item is None or not atr_item["passed"],
        f"item={atr_item}",
    )

print("\n=== 5. build_trade_levels — degenerate close/ATR combinations ===")
levels_zero_atr = run_no_crash("build_trade_levels(close=100, atr=0)", pipe.build_trade_levels, 100.0, 0.0)
if levels_zero_atr:
    check(
        "ATR=0 doesn't produce a divide-by-zero quantity crash",
        levels_zero_atr["quantity"] >= 0 and levels_zero_atr["recommended_quantity_at_1pct_risk"] >= 0,
        f"levels={levels_zero_atr}",
    )

levels_penny = run_no_crash("build_trade_levels(close=5, atr=3) — thin/penny-stock ATR wider than price", pipe.build_trade_levels, 5.0, 3.0)
if levels_penny:
    check(
        "Stop-loss for a low-priced, high-ATR stock is marked invalid, not a negative/nonsensical price",
        levels_penny.get("valid") is False and levels_penny.get("stop_loss") is None,
        f"levels={levels_penny}",
    )

levels_nan_atr = run_no_crash("build_trade_levels(close=100, atr=NaN)", pipe.build_trade_levels, 100.0, float("nan"))
if levels_nan_atr:
    check(
        "NaN ATR is rejected as invalid, not silently turned into a NaN-based stop/target",
        levels_nan_atr.get("valid") is False and levels_nan_atr.get("stop_loss") is None,
        f"levels={levels_nan_atr}",
    )

print("\n=== 6. RSI boundary values — off-by-one at the exact gate threshold ===")
for rsi_val in (64.9, 65.0, 65.01, 45.0, 44.99):
    row = {"close_price": 100.0, "sma_200": 90.0, "rsi_14": rsi_val}
    buyable, msg = pipe.check_buyability(row)
    print(f"        RSI={rsi_val}: buyable={buyable} — {msg}")
check(
    "RSI exactly at 65.0 is still buyable (gate is strict '>', not '>=')",
    pipe.check_buyability({"close_price": 100.0, "sma_200": 90.0, "rsi_14": 65.0})[0] is True,
)
check(
    "RSI at 65.01 is blocked",
    pipe.check_buyability({"close_price": 100.0, "sma_200": 90.0, "rsi_14": 65.01})[0] is False,
)

print("\n=== 7. Zero/negative price feeding the buyability + ATR% path together ===")
zero_price_row = {"close_price": 0.0, "sma_200": 100.0, "rsi_14": 50.0}
run_no_crash("check_buyability(close_price=0)", pipe.check_buyability, zero_price_row)

print("\n=== 8. Missing history for momentum / technical scorecard ===")
run_no_crash("evaluate_technical_checklist(row, history=None)", fe.evaluate_technical_checklist, {"close_price": 100, "sma_200": 90}, None)
import pandas as pd  # noqa: E402
run_no_crash("evaluate_technical_checklist(row, history=empty DataFrame)", fe.evaluate_technical_checklist, {"close_price": 100, "sma_200": 90}, pd.DataFrame())

print("\n=== 9. String-typed numeric fields (bad upstream data / DB round-trip) ===")
string_row = {
    "data_quality": "SOURCED",
    "close_price": "104.5",
    "sma_200": "90.0",
    "rsi_14": "not_a_number",
}
run_no_crash("evaluate_technical_checklist(string-typed close/sma, garbage rsi)", fe.evaluate_technical_checklist, string_row)

print("\n=== 10. 52-Week Range Position item (Minervini gap #2) ===")
strong_range_row = {"close_price": 100.0, "sma_200": 90.0, "week52_high": 105.0, "week52_low": 60.0}
weak_range_row = {"close_price": 62.0, "sma_200": 90.0, "week52_high": 105.0, "week52_low": 60.0}
missing_range_row = {"close_price": 100.0, "sma_200": 90.0}

strong_item = fe._week52_range_item(strong_range_row, 100.0)
weak_item = fe._week52_range_item(weak_range_row, 62.0)
missing_item = fe._week52_range_item(missing_range_row, 100.0)

check(
    "Strong 52-week position (67% off low, 5% off high) scores full marks",
    strong_item["passed"] is True and strong_item["marks"] == 6.0,
    f"item={strong_item}",
)
check(
    "Weak 52-week position (3% off low) does NOT score full marks",
    weak_item["passed"] is False and weak_item["marks"] < 6.0,
    f"item={weak_item}",
)
check(
    "Missing week52 data is skipped (max_marks=0), not scored good or bad",
    missing_item["max_marks"] == 0 and missing_item["passed"] is True,
    f"item={missing_item}",
)
check(
    "Both India and US technical checklists include the item when data is present",
    any(i["name"] == "52-Week Range Position" for i in fe.evaluate_technical_checklist(strong_range_row)["items"])
    and any(i["name"] == "52-Week Range Position" for i in feus.evaluate_us_technical_checklist(strong_range_row)["items"]),
)

print("\n=== 11. Market regime gate (CANSLIM 'M' gap #1) ===")
import importlib
db_mod = importlib.import_module("db.database_engine")

# This is the one section of this file that touches persistent state (the
# real dev DB, not an isolated test DB — unlike e2e_regression.py). Save
# and restore whatever was cached before this test ran so a stress-test
# run never leaves the live regime cache in a stale/test state for the
# actual app to read until the next real refresh recomputes it.
_regime_before = db_mod.get_meta(db_mod.META_MARKET_REGIME_IN)

# Directly exercise the gate logic (not the live index fetch — that needs
# network access this test suite shouldn't depend on) by writing a known
# regime straight into the same cache evaluate_buy_signal reads from.
db_mod.set_meta(db_mod.META_MARKET_REGIME_IN, '{"risk_on": false, "index": "^NSEI", "index_close": 100, "index_sma200": 110, "as_of": "2026-08-30"}')
regime_off = pipe.get_market_regime("IN")
check("get_market_regime reads back a cached RISK_OFF regime", regime_off is not None and regime_off["risk_on"] is False, f"regime={regime_off}")

db_mod.set_meta(db_mod.META_MARKET_REGIME_IN, '{"risk_on": true, "index": "^NSEI", "index_close": 120, "index_sma200": 110, "as_of": "2026-08-30"}')
regime_on = pipe.get_market_regime("IN")
check("get_market_regime reads back a cached RISK_ON regime", regime_on is not None and regime_on["risk_on"] is True, f"regime={regime_on}")

db_mod.set_meta(db_mod.META_MARKET_REGIME_IN, "")
check("Uncomputed regime (no refresh yet) reads back as None, not a false block", pipe.get_market_regime("IN") is None)

# Now exercise it through the real gate list, not just the cache reader.
sample_row = {
    "ticker": "TESTCO", "data_quality": "SOURCED", "close_price": 100.0, "sma_200": 90.0,
    "rsi_14": 50.0, "pe_peer_percentile": 10.0, "peg_ratio": 0.8,
}
sample_scorecard = {"composite_pct": 80.0, "fundamental": {"pct": 80.0}}

db_mod.set_meta(db_mod.META_MARKET_REGIME_IN, '{"risk_on": false, "index": "^NSEI", "index_close": 100, "index_sma200": 110, "as_of": "2026-08-30"}')
signal_regime_off = pipe.evaluate_buy_signal(sample_row, sample_scorecard, user_id=999999, market="IN")
gate_off = next((g for g in signal_regime_off["gates"] if g["gate"] == "market_regime"), None)
check(
    "RISK_OFF regime blocks the market_regime gate even when every stock-level gate passes",
    gate_off is not None and gate_off["passed"] is False,
    f"gate={gate_off}",
)

db_mod.set_meta(db_mod.META_MARKET_REGIME_IN, '{"risk_on": true, "index": "^NSEI", "index_close": 120, "index_sma200": 110, "as_of": "2026-08-30"}')
signal_regime_on = pipe.evaluate_buy_signal(sample_row, sample_scorecard, user_id=999999, market="IN")
gate_on = next((g for g in signal_regime_on["gates"] if g["gate"] == "market_regime"), None)
check(
    "RISK_ON regime passes the market_regime gate",
    gate_on is not None and gate_on["passed"] is True,
    f"gate={gate_on}",
)

db_mod.set_meta(db_mod.META_MARKET_REGIME_IN, "")
signal_no_regime = pipe.evaluate_buy_signal(sample_row, sample_scorecard, user_id=999999, market="IN")
gate_none = next((g for g in signal_no_regime["gates"] if g["gate"] == "market_regime"), None)
check(
    "Uncomputed regime does not block a signal (graceful degradation, not a false negative)",
    gate_none is not None and gate_none["passed"] is True,
    f"gate={gate_none}",
)

db_mod.set_meta(db_mod.META_MARKET_REGIME_IN, _regime_before or "")

print("\n=== 12. NaN-close trailing bar (real, observed live-data quirk) ===")
# Found live during this session's market-regime work: yfinance sometimes
# returns a most-recent bar with a real Date but a NaN close (not yet
# settled at fetch time). sma_50/sma_200 tolerated it silently (pandas
# .mean() skips NaN by default) while close_price/RSI did not — this is
# what made an earlier /api/profile/AAPL?live=true 500 look transient and
# unreproducible; it wasn't transient, it was this exact shape of row.
good_frame = pd.DataFrame({
    "open": [100.0, 101.0, 102.0],
    "high": [101.0, 102.0, 103.0],
    "low": [99.0, 100.0, 101.0],
    "close": [100.5, 101.5, 102.5],
    "volume": [1000, 1100, 1200],
})
broken_frame = pd.DataFrame({
    "open": [100.0, 101.0, 102.0],
    "high": [101.0, 102.0, 103.0],
    "low": [99.0, 100.0, 101.0],
    "close": [100.5, 101.5, float("nan")],
    "volume": [1000, 1100, 1200],
})
cleaned = nse._clean_ohlcv(broken_frame)
check(
    "_clean_ohlcv drops the trailing NaN-close bar",
    len(cleaned) == 2 and not cleaned["close"].isna().any(),
    f"cleaned closes={cleaned['close'].tolist()}",
)
check(
    "_clean_ohlcv leaves a fully-clean frame untouched",
    len(nse._clean_ohlcv(good_frame)) == 3,
)
check(
    "close_price extraction on the cleaned frame is the last REAL close, not NaN",
    float(cleaned["close"].iloc[-1]) == 101.5,
    f"got {cleaned['close'].iloc[-1]}",
)

print("\n" + "=" * 60)
print(f"STRESS TEST SUMMARY: {PASS}/{PASS + FAIL} PASSED | {FAIL} FAILED")
if FINDINGS:
    print("\nFAILURES (real findings — not yet fixed):")
    for f in FINDINGS:
        print(f"  - {f}")
print("=" * 60)

sys.exit(1 if FAIL else 0)
