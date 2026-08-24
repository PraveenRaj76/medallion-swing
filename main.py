"""FastAPI entry point — Phase 1 of the Streamlit-to-React rebuild.

Thin JSON wrapper around the existing pipeline (database_engine,
data_pipeline, factor_engine, nse_data_provider). No business logic lives
here; see routes/ for the endpoint handlers and MEDALLION_CONTEXT_FOR_CLAUDE_CODE.md
for the rebuild rationale.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(level=os.environ.get("MEDALLION_LOG_LEVEL", "INFO"))
logger = logging.getLogger("medallion.api")

import database_engine as db  # noqa: E402  (after load_dotenv/logging setup)

app = FastAPI(
    title="Medallion Swing Engine",
    description="Quantamental swing-trading validator for NSE equities",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
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
