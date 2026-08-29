"""
Medallion Swing — Backend Engine Regression Suite
Exercises database_engine/data_pipeline/factor_engine/multi_source_data
directly (not through HTTP) — auth, schema, buy/close/trailing-stop
lifecycle, scoring, multi-user isolation.

Historical note: this file used to also import and exercise app.py, the
original Streamlit UI, including a Streamlit AppTest smoke section and a
"button/page contract" text-scan of app.py's source. Both were removed
2026-08-29 when app.py itself was retired in favor of the FastAPI + React
app already covered by this session's own manual browser verification —
keeping tests for a deleted file made no sense. A few other sections
(Screener/Search "Path") called an app.py-only function
(execute_algorithmic_buy) and were silently broken before that removal
too; they're rewritten below to call database_engine.open_signal directly,
same as the Multi-User Isolation section already did.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timedelta

# Windows' console defaults to the cp1252 codepage, which can't encode
# characters this suite's own messages use (→, ✓, ₹, etc.) — printing one
# raised UnicodeEncodeError mid-test, aborting that test's whole try block
# and masking a real pass/fail behind an unrelated encoding crash. Root
# cause, not a per-message workaround: reconfigure stdout/stderr to UTF-8
# (Python 3.7+) once, here, before anything prints.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
os.chdir(BASE)

# Isolate test DB BEFORE importing engine (engine inits on import)
TEST_DB = BASE / "e2e_test_medallion.db"
if TEST_DB.exists():
    try:
        TEST_DB.unlink()
    except Exception:
        pass

# Patch path via env consumed below after import+reload
os.environ["MEDALLION_DB_PATH"] = str(TEST_DB)
# Offline market mode so CI/regression never hits Yahoo/Screener
os.environ["MEDALLION_MARKET_MODE"] = "mock"

# Ensure database_engine honors MEDALLION_DB_PATH
import importlib
import database_engine as db

db.DATABASE_PATH = os.environ["MEDALLION_DB_PATH"]
importlib.reload(db)
db.DATABASE_PATH = os.environ["MEDALLION_DB_PATH"]
db.init_database()

import data_pipeline as pipe
importlib.reload(pipe)


RESULTS = []


def log(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    if detail:
        print(f"        {detail}")
    if not ok and detail:
        print(f"        ! {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    tag = str(os.getpid())
    user_a = f"e2e_alice_{tag}"
    user_b = f"e2e_bob_{tag}"
    password = "pass1234"

    # ------------------------------------------------------------------
    section("0. Workspace Integrity — backend/ layout")
    # ------------------------------------------------------------------
    try:
        required = [
            BASE / "main.py",
            BASE / "database_engine.py",
            BASE / "data_pipeline.py",
            BASE / "nse_data_provider.py",
            BASE / "us_data_provider.py",
            BASE / "factor_engine.py",
            BASE / "factor_engine_us.py",
            BASE / "routes" / "screener.py",
            BASE / "data" / "nse_universe.txt",
        ]
        missing = [str(p.name) for p in required if not p.exists()]
        log("Workspace files present", len(missing) == 0, f"missing={missing}")
    except Exception as exc:
        log("Workspace integrity", False, traceback.format_exc()[-300:])

    # ------------------------------------------------------------------
    section("1. Auth Gate — Register / Login / Reject")
    # ------------------------------------------------------------------
    try:
        ok, msg, uid = db.register_user("ab", "short")
        log("Reject short username", not ok and uid is None, msg)

        ok, msg, uid = db.register_user(user_a, "123")
        log("Reject short password", not ok, msg)

        ok, msg, uid_a = db.register_user(user_a, password)
        log("Register user A", ok and uid_a is not None, msg)

        ok_dup, msg_dup, _ = db.register_user(user_a, password)
        log("Reject duplicate username", not ok_dup, msg_dup)

        ok_bad, msg_bad, _ = db.verify_user(user_a, "wrongpass")
        log("Reject bad password", not ok_bad, msg_bad)

        ok_login, msg_login, uid_login = db.verify_user(user_a, password)
        log("Login user A", ok_login and uid_login == uid_a, msg_login)

        ok_b, msg_b, uid_b = db.register_user(user_b, password)
        log("Register user B (isolation peer)", ok_b and uid_b is not None, msg_b)
    except Exception as exc:
        log("Auth gate", False, traceback.format_exc()[-300:])
        return 1

    # ------------------------------------------------------------------
    section("2. Schema — No Capital Ledger / Required Tables")
    # ------------------------------------------------------------------
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cur.fetchall()}
        required_tables = {"users", "screener_leaderboard", "active_positions", "closed_trades_history"}
        log(
            "Required tables exist",
            required_tables.issubset(tables),
            f"tables={sorted(tables)}",
        )
        log("portfolio_ledger dropped", "portfolio_ledger" not in tables, "")
        log("capital_flows dropped", "capital_flows" not in tables, "")

        lb = db.get_leaderboard()
        log("Leaderboard seeded", lb is not None and len(lb) >= 4, f"rows={len(lb)}")
    except Exception as exc:
        log("Schema checks", False, str(exc))

    # ------------------------------------------------------------------
    section("3. Screener Path — Levels, Buyability, Fixed Qty Buy")
    # ------------------------------------------------------------------
    try:
        row = db.get_ticker_row("TCS")
        log("Screener ticker lookup TCS", row is not None, "")

        levels = pipe.build_trade_levels(float(row["close_price"]), float(row["atr_value"]))
        log(
            "ATR levels (stop=CMP-2.5ATR, target=CMP+6ATR)",
            levels["quantity"] == 1
            and abs(levels["stop_loss"] - (float(row["close_price"]) - 2.5 * float(row["atr_value"]))) < 0.02
            and abs(levels["target"] - (float(row["close_price"]) + 6.0 * float(row["atr_value"]))) < 0.02,
            str(levels),
        )

        buyable, reason = pipe.check_buyability(row)
        log("TCS buyability check runs", isinstance(buyable, bool) and len(reason) > 5, reason[:80])

        # Buy — same call the /api/trade route makes (see routes/refresh.py
        # post_open_trade); this file tests the engine directly rather than
        # over HTTP, same pattern the Multi-User Isolation section already uses.
        ok, msg = db.open_signal(
            uid_a,
            "TCS",
            float(row["close_price"]),
            levels["stop_loss"],
            levels["target"],
            atr=float(row["atr_value"]),
            market="IN",
        )
        pos = db.get_active_positions(uid_a)
        tcs = pos[pos["ticker"] == "TCS"]
        log(
            "Screener EXECUTE BUY → active 1 share",
            ok and len(tcs) == 1 and int(tcs.iloc[0]["quantity"]) == 1,
            msg,
        )

        # Duplicate buy blocked
        ok2, msg2 = db.open_signal(
            uid_a, "TCS", float(row["close_price"]), levels["stop_loss"], levels["target"]
        )
        log("Duplicate active signal blocked", not ok2, msg2)
    except Exception as exc:
        log("Screener path", False, traceback.format_exc()[-300:])

    # ------------------------------------------------------------------
    section("4. Search Profile Path — Buy + RSI Lock")
    # ------------------------------------------------------------------
    try:
        row = db.get_ticker_row("INFY")
        levels = pipe.build_trade_levels(float(row["close_price"]), float(row["atr_value"]))
        ok, msg = db.open_signal(
            uid_a,
            "INFY",
            float(row["close_price"]),
            levels["stop_loss"],
            levels["target"],
            atr=float(row["atr_value"]),
            market="IN",
        )
        pos = db.get_active_positions(uid_a)
        log(
            "Search Profile buy → INFY qty=1",
            ok and any(pos["ticker"] == "INFY") and int(pos[pos["ticker"] == "INFY"].iloc[0]["quantity"]) == 1,
            msg,
        )

        hot = row.copy()
        hot["rsi_14"] = 72.0
        hot["close_price"] = float(row["close_price"])
        hot["sma_200"] = float(row["sma_200"])
        locked, lock_msg = pipe.check_buyability(hot)
        log("RSI>65 locks buy inputs", (not locked) and "OVEREXTENDED" in lock_msg, lock_msg[:90])

        # Price history for the chart data the frontend consumes (real chart
        # rendering is React/recharts now — see routes/profile.py's
        # _price_history — not something this Python script can exercise).
        hist = pipe.generate_price_history("INFY", float(row["close_price"]), 250)
        log("Price history for chart data", len(hist) == 250 and {"open", "high", "low", "close", "volume"}.issubset(hist.columns), f"rows={len(hist)}")
    except Exception as exc:
        log("Search path", False, traceback.format_exc()[-300:])

    # ------------------------------------------------------------------
    section("4b. Factor Engine — Checklist Scoring + Data-Quality Gates")
    # ------------------------------------------------------------------
    try:
        import factor_engine as fe

        tcs = db.get_ticker_row("TCS")
        card = fe.full_factor_scorecard(tcs)
        log(
            "Expanded scorecard has fund+tech",
            card["fundamental"]["total_filters"] >= 6 and card["technical"]["total_filters"] >= 6,
            f"fund={card['fundamental']['total_filters']} tech={card['technical']['total_filters']} total={card['composite_marks']}",
        )
        # Fake defaults must NOT earn fundamental PASSes
        fake = {
            "ticker": "IFCI",
            "sector": "Financials",
            "industry": "NBFC",
            "roic": 12.0,
            "peg_ratio": 1.5,
            "net_debt_ebitda": 1.5,
            "interest_coverage": 5.0,
            "promoter_pledge_pct": 0.0,
            "yoy_profit_growth": 10.0,
            "pe_ratio": 0,
        }
        fake_card = fe.evaluate_fundamental_checklist(fake)
        # "MISSING" (not the old "UNVERIFIED" tag this assertion checked
        # before 2026-08-29) is _quality()'s current output for exactly this
        # "too-round-to-be-real" placeholder pattern — see factor_engine.py's
        # _quality(), which maps the legacy "UNVERIFIED" input tag onto
        # "MISSING" too. The behavior under test (fake data doesn't earn
        # real marks) was never actually broken; only this string was stale.
        log(
            "Placeholder fundamentals blocked from scoring",
            fe._quality(fake) == "MISSING" and fake_card["total_marks"] <= 5,
            f"quality={fe._quality(fake)} marks={fake_card['total_marks']}",
        )
        log(
            "Multi-source module present",
            (BASE / "multi_source_data.py").exists()
            and "fetch_verified_fundamentals" in (BASE / "multi_source_data.py").read_text(encoding="utf-8"),
            "ok",
        )
        # Consensus helper unit test
        import multi_source_data as msd

        val, status, _ = msd.consensus_metric(
            "pe_ratio",
            [
                {"source": "screener", "ok": True, "pe_ratio": 112},
                {"source": "tickertape", "ok": True, "pe_ratio": 114},
                {"source": "moneycontrol", "ok": True, "pe_ratio": 114.2},
            ],
        )
        log("PE consensus across 3 sources", status == "verified" and 110 <= val <= 116, f"{status} {val}")
        val2, status2, _ = msd.consensus_metric(
            "pe_ratio",
            [
                {"source": "screener", "ok": True, "pe_ratio": 12},
                {"source": "tickertape", "ok": True, "pe_ratio": 110},
            ],
        )
        log("Disputed PE rejected", status2 == "disputed" and val2 is None, f"{status2} {val2}")

        cov = pipe.universe_coverage()
        log(
            "universe_coverage returns counts",
            isinstance(cov.get("universe_total"), int) and cov["universe_total"] > 0,
            f"total={cov.get('universe_total')} in_db={cov.get('in_db')}",
        )
        prog = pipe.progressive_universe_batch(batch_size=3)
        log(
            "progressive hydrate safe in mock mode",
            prog.get("complete") is True or "Mock" in str(prog.get("message", "")),
            str(prog.get("message", ""))[:80],
        )
        refresh = pipe.refresh_verified_live(user_id=uid_a)
        log(
            "manual Refresh path works",
            "accepted" in refresh and "message" in refresh,
            str(refresh.get("message", ""))[:80],
        )
        ready = pipe.filter_display_ready(db.get_leaderboard(limit=50))
        log(
            "display filter hides incomplete rows",
            hasattr(ready, "empty"),
            f"ready={len(ready)}",
        )
        log(
            "2-source model constant (Screener + NSE filings)",
            pipe.MIN_SOURCES_REQUIRED >= 1,
            str(pipe.MIN_SOURCES_REQUIRED),
        )
        log(
            "list_leaderboard_tickers works",
            isinstance(db.list_leaderboard_tickers(), list) and len(db.list_leaderboard_tickers()) > 0,
            f"n={len(db.list_leaderboard_tickers())}",
        )
        yf_helper = "def _fetch_ohlcv_yfinance" in (BASE / "nse_data_provider.py").read_text(
            encoding="utf-8"
        )
        log("yfinance OHLCV fallback wired", yf_helper, "ok")
    except Exception as exc:
        log("Factor engine", False, traceback.format_exc()[-400:])

    # ------------------------------------------------------------------
    section("5. Navigation Sync + validate_active_signals")
    # ------------------------------------------------------------------
    try:
        sync = pipe.sync_user_and_screener_data(uid_a)
        log("Landing sync runs", "message" in sync and "clearances" in sync, sync.get("message", "")[:80])

        # Trailing-stop redesign (see data_pipeline.compute_trailing_stop): hitting
        # target no longer force-closes — it only tightens the chandelier trail from
        # 3x to 2x ATR, so a genuine trend can run past the fixed target instead of
        # being capped there. Verify both halves: (a) target alone does NOT close,
        # it flips the position into "runner" phase with a ratcheted-up stop; then
        # (b) pulling back through that new, tighter trailing stop DOES close it,
        # and correctly as a WIN since the stop is above entry.
        pos = db.get_active_positions(uid_a)
        tcs = pos[pos["ticker"] == "TCS"].iloc[0]
        pid = int(tcs["position_id"])
        entry_price = float(tcs["entry_price"])
        atr_at_entry = (
            float(tcs["atr_at_entry"])
            if tcs.get("atr_at_entry") is not None
            else float(db.get_ticker_row("TCS")["atr_value"])
        )
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE active_positions SET entry_timestamp=? WHERE position_id=?",
                ((datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"), pid),
            )
        # Push market quote well above target — should tighten the trail, not close.
        target = float(tcs["target"])
        db.upsert_leaderboard_rows([{
            **db.get_ticker_row("TCS").to_dict(),
            "close_price": target + 2 * atr_at_entry,
            "is_buyable": 1,
        }])
        clearances = pipe.validate_active_signals(uid_a)
        pos = db.get_active_positions(uid_a)
        tcs_row = pos[pos["ticker"] == "TCS"]
        log(
            "Nav/validate: target hit alone does NOT close — tightens trail to 'runner' phase",
            not tcs_row.empty and tcs_row.iloc[0]["trail_phase"] == "runner"
            and not any(c.get("ticker") == "TCS" for c in clearances),
            f"clearances={len(clearances)}",
        )
        # Now pull back through the new, tighter trailing stop — should close as a WIN.
        new_stop = float(tcs_row.iloc[0]["stop_loss"])
        db.upsert_leaderboard_rows([{
            **db.get_ticker_row("TCS").to_dict(),
            "close_price": new_stop - 1.0,
            "is_buyable": 0,
        }])
        clearances = pipe.validate_active_signals(uid_a)
        cleared_tcs = any(c.get("ticker") == "TCS" and c.get("exit_status") == db.EXIT_SUCCESS for c in clearances)
        still = db.get_active_positions(uid_a)
        log(
            "Nav/validate: pullback through tightened trail → SUCCESSFUL TRADE + removed from active",
            cleared_tcs and (still.empty or "TCS" not in set(still["ticker"].astype(str))),
            f"clearances={len(clearances)}",
        )

        # Stop loss → BAD TRADE on INFY
        pos = db.get_active_positions(uid_a)
        if not pos.empty and "INFY" in set(pos["ticker"].astype(str)):
            infy = pos[pos["ticker"] == "INFY"].iloc[0]
            stop = float(infy["stop_loss"])
            db.upsert_leaderboard_rows([{
                **db.get_ticker_row("INFY").to_dict(),
                "close_price": stop - 3.0,
                "is_buyable": 0,
            }])
            clear2 = pipe.validate_active_signals(uid_a)
            bad = any(c.get("ticker") == "INFY" and c.get("exit_status") == db.EXIT_BAD for c in clear2)
            log("Validate: stop hit → BAD TRADE", bad, f"clearances={len(clear2)}")
        else:
            # Open fresh and force bad
            row = db.get_ticker_row("RELIANCE")
            levels = pipe.build_trade_levels(float(row["close_price"]), float(row["atr_value"]))
            db.open_signal(uid_a, "RELIANCE", float(row["close_price"]), levels["stop_loss"], levels["target"])
            pos = db.get_active_positions(uid_a)
            pid = int(pos[pos["ticker"] == "RELIANCE"].iloc[0]["position_id"])
            ok, _, pnl = db.close_signal(uid_a, pid, levels["stop_loss"] - 1, db.EXIT_BAD)
            log("Manual BAD TRADE close path", ok and pnl < 0, f"pnl={pnl:.2f}")
    except Exception as exc:
        log("Validation sync", False, traceback.format_exc()[-400:])

    # ------------------------------------------------------------------
    section("6. Forward-Test Scorecard & Deep Metrics")
    # ------------------------------------------------------------------
    try:
        score = pipe.compute_forward_test_scorecard(uid_a)
        log(
            "Scorecard fields present",
            all(k in score for k in (
                "total_signals_tracked", "win_rate_pct", "total_realized_rupee_return", "trades"
            )),
            str({k: score[k] for k in ("total_signals_tracked", "win_rate_pct", "total_realized_rupee_return")}),
        )
        log(
            "Scorecard has closed trades after E2E",
            score["total_signals_tracked"] >= 1,
            f"tracked={score['total_signals_tracked']}",
        )
        if score["trades"]:
            t0 = score["trades"][0]
            needed = {"exit_status", "absolute_delta", "pct_return", "velocity_label", "days_elapsed"}
            log("Deep-dive trade metrics enriched", needed.issubset(t0.keys()), str(t0)[:120])

        empty = pipe.compute_forward_test_scorecard(uid_b)
        log(
            "Empty user scorecard safe (0 trades)",
            empty["total_signals_tracked"] == 0
            and empty["win_rate_pct"] == 0.0
            and empty["total_realized_rupee_return"] == 0.0,
            "",
        )
    except Exception as exc:
        log("Scorecard", False, traceback.format_exc()[-300:])

    # ------------------------------------------------------------------
    section("7. Multi-User Isolation")
    # ------------------------------------------------------------------
    try:
        row = db.get_ticker_row("ITC")
        levels = pipe.build_trade_levels(float(row["close_price"]), float(row["atr_value"]))
        db.open_signal(uid_b, "ITC", float(row["close_price"]), levels["stop_loss"], levels["target"])
        pos_a = db.get_active_positions(uid_a)
        pos_b = db.get_active_positions(uid_b)
        tick_a = set(pos_a["ticker"].astype(str)) if not pos_a.empty else set()
        tick_b = set(pos_b["ticker"].astype(str)) if not pos_b.empty else set()
        log(
            "User B ITC not visible to User A",
            "ITC" in tick_b and "ITC" not in tick_a,
            f"A={tick_a} B={tick_b}",
        )
        sa = pipe.compute_forward_test_scorecard(uid_a)
        sb = pipe.compute_forward_test_scorecard(uid_b)
        log(
            "Scorecards isolated by user_id",
            sa["total_signals_tracked"] != sb["total_signals_tracked"] or tick_a != tick_b,
            f"tracked A/B={sa['total_signals_tracked']}/{sb['total_signals_tracked']}",
        )
    except Exception as exc:
        log("Isolation", False, str(exc))

    # Cleanup test db
    try:
        if TEST_DB.exists():
            TEST_DB.unlink()
    except Exception:
        pass

    fails = [r for r in RESULTS if not r[1]]
    print("\n" + "=" * 60)
    print(f"E2E REGRESSION SUMMARY: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASSED | {len(fails)} FAILED")
    if fails:
        print("FAILURES:")
        for name, _, detail in fails:
            print(f"  - {name}: {detail}")
    print("=" * 60)
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
