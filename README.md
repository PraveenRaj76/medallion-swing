# Medallion Swing Engine

NSE (India) + US quantamental swing-trading screener and forward-test tracker.

> "We do data. We don't have opinions." — Jim Simons

Scores stocks on a fundamental + technical checklist, shows exactly which
filters passed and why, and lets you open a real paper position from the
suggested trade levels — then tracks whether the checklist actually has
positive expectancy over time.

## Stack

- **Backend** — FastAPI (`backend/`), SQLite locally / [Turso](https://turso.tech) in production
- **Frontend** — React + TypeScript + Vite (`frontend/`)
- **Data sources** — Angel One SmartAPI + Yahoo Finance (India), SEC EDGAR + Yahoo Finance (US), NSE bhavcopy (delivery %)

## Structure

```
backend/
  main.py                 FastAPI app entry point
  routes/                 API route handlers (screener, profile, forward-test, auth, ...)
  database_engine.py      Persistence (SQLite locally, Turso in production)
  data_pipeline.py        Refresh orchestration, trade-level math, signal validation
  factor_engine.py        India fundamental + technical checklist scoring
  factor_engine_us.py     US fundamental + technical checklist scoring
  nse_data_provider.py    India price/fundamentals fetching
  us_data_provider.py     US price/fundamentals fetching (SEC EDGAR)
  e2e_regression.py       Backend engine regression suite
frontend/
  src/pages/               Screener (India/US), Search Profile, Forward-Test, Login
  src/components/, src/api/
```

## Running locally

**Prerequisites**: [Python 3.11+](https://www.python.org/downloads/) and [Node.js 18+](https://nodejs.org/) on your PATH. No `.env` file is needed to get started — the app runs in live mode against real data out of the box.

**Quickest way (Windows)**: double-click **`start medallion swing.bat`** in the repo root. First run installs everything automatically (Python virtual environment, pip packages, npm packages — takes a few minutes); every run after that starts in seconds. It opens the backend and frontend each in their own window and opens the app in your browser once both are ready.

**Manual way (any OS):**

Backend:
```bash
cd backend
python -m venv venv
venv/bin/pip install -r requirements.txt   # Windows: venv\Scripts\pip.exe
venv/bin/python main.py                     # Windows: venv\Scripts\python.exe
```

Frontend (separate terminal):
```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000` in dev — open `http://localhost:5173`.

Optional: copy `backend/.env.example` to `backend/.env` and fill in Angel One SmartAPI credentials for the live India price cross-check on Search Profile, or Turso credentials to persist data across restarts instead of using a local SQLite file. Neither is required for normal use.

## Testing

```bash
cd backend
python e2e_regression.py
```

Exercises the engine directly (auth, schema, buy/close/trailing-stop lifecycle,
checklist scoring, multi-user isolation) — not through HTTP.

## Deployment

- **Backend** → [SnapDeploy](https://snapdeploy.dev) (Docker-based; `backend/Dockerfile` at the repo, root directory `backend`, port `8000`). `render.yaml` is also included and works for [Render](https://render.com)'s free tier as an alternative — Render's own no-card policy doesn't apply consistently to new accounts in practice, which is why this project ended up on SnapDeploy instead.
- **Frontend** → [Cloudflare Pages](https://pages.cloudflare.com) (root directory `frontend`, build `npm run build`, output `dist`) — use the "legacy Pages" flow if Cloudflare defaults you into their newer Workers-first flow, which expects a `wrangler.toml` this repo doesn't have.
- **Database** → [Turso](https://turso.tech) (free tier) — required in production since the backend host has no persistent disk; `database_engine.py` transparently switches to it when `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN` are set, and falls back to local SQLite otherwise. Uses `turso_serverless` (Turso's current official driver) — not `libsql_client`, which Turso archived in June 2025 and no longer works reliably against current servers.
- **Keep-alive** → `.github/workflows/keep-backend-awake.yml` pings the backend's `/health` every 10 minutes so free-tier idle-sleep doesn't cold-start it on the next real request.

See `render.yaml` / your chosen host's dashboard for the full list of environment variables the backend needs (`MEDALLION_MARKET_MODE`, `MEDALLION_SSL_VERIFY`, `MEDALLION_DEFAULT_USER_ID`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, and optionally the four `ANGEL_*` variables).
