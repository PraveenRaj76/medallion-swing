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

**Backend:**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in Angel One / Turso credentials, or leave blank for local SQLite + mock mode
uvicorn main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000` in dev — open `http://localhost:5173`.

## Testing

```bash
cd backend
python e2e_regression.py
```

Exercises the engine directly (auth, schema, buy/close/trailing-stop lifecycle,
checklist scoring, multi-user isolation) — not through HTTP.

## Deployment

- **Backend** → [Render](https://render.com) (`render.yaml` blueprint at repo root, free tier)
- **Frontend** → [Cloudflare Pages](https://pages.cloudflare.com) (root directory `frontend`, build `npm run build`, output `dist`)
- **Database** → [Turso](https://turso.tech) (free tier) — required in production since Render's free tier has no persistent disk; `database_engine.py` transparently switches to it when `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN` are set, and falls back to local SQLite otherwise

See `render.yaml` for the full list of environment variables the backend needs.
