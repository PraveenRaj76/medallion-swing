"""FastAPI entry point — Phase 1 of the Streamlit-to-React rebuild.

Thin JSON wrapper around the existing pipeline (database_engine,
data_pipeline, factor_engine, nse_data_provider). No business logic lives
here; see routes/ for the endpoint handlers and MEDALLION_CONTEXT_FOR_CLAUDE_CODE.md
for the rebuild rationale.
"""

from __future__ import annotations

import logging
import os

import math
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

logging.basicConfig(level=os.environ.get("MEDALLION_LOG_LEVEL", "INFO"))
logger = logging.getLogger("medallion.api")

from db import database_engine as db  # noqa: E402  (after load_dotenv/logging setup)


def _sanitize_nan(obj: Any) -> Any:
    """NaN/Infinity have no JSON representation — Starlette's default
    JSONResponse correctly refuses them (allow_nan=False) rather than
    emitting non-standard tokens a browser's JSON.parse would choke on. But
    "correctly refuses" means a 500 for the whole request the moment a NaN
    reaches here, however it got there — found via a live /api/sectors crash
    traced to a NaN closing price in a fetched OHLCV series (real gap-day
    data, not a code bug in the usual sense) slipping past a `is not None`
    check that doesn't catch NaN (float('nan') is not None → True). Fixed
    that specific source (sector_valuation.py), but the same shape of bug —
    a live-data NaN reaching a numeric field nothing downstream expected to
    need a NaN check — can occur anywhere real market data flows through a
    calculation. This is the backstop: convert to JSON's actual equivalent
    of "no value" (null) here, once, rather than requiring every call site
    that touches live data to individually remember to guard for it.
    """
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return super().render(_sanitize_nan(content))


app = FastAPI(
    title="Medallion Swing Engine",
    description="Quantamental swing-trading validator for NSE equities",
    version="2.0.0",
    default_response_class=SafeJSONResponse,
)

# Extra production origins (e.g. the Cloudflare Pages deployment URL) come
# from an env var, comma-separated — the dev-server defaults below always
# stay allowed so local development never needs this set.
_extra_origins = [
    o.strip() for o in os.environ.get("MEDALLION_ALLOWED_ORIGINS", "").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        *_extra_origins,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    db.init_database()
    logger.info("Database ready — %s stocks in leaderboard.", db.leaderboard_count())


from routes import auth, forward_test, profile, refresh, screener, sectors  # noqa: E402

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(screener.router, prefix="/api", tags=["screener"])
app.include_router(sectors.router, prefix="/api", tags=["sectors"])
app.include_router(profile.router, prefix="/api", tags=["profile"])
app.include_router(forward_test.router, prefix="/api", tags=["forward-test"])
app.include_router(refresh.router, prefix="/api", tags=["operations"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
