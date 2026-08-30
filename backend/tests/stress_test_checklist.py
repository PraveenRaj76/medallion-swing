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

print("\n" + "=" * 60)
print(f"STRESS TEST SUMMARY: {PASS}/{PASS + FAIL} PASSED | {FAIL} FAILED")
if FINDINGS:
    print("\nFAILURES (real findings — not yet fixed):")
    for f in FINDINGS:
        print(f"  - {f}")
print("=" * 60)

sys.exit(1 if FAIL else 0)
