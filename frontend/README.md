# Medallion Swing — React Frontend

React + TypeScript (Vite) frontend for the FastAPI backend in `../main.py`. Mirrors the Streamlit app's four pages (Screener, Search Profile, Sectors, Forward-Test) as a real SPA, talking to the same live pipeline through `/api/*`.

## Run it

Two servers, both from the repo root's `venv`:

```bash
# Terminal 1 — API backend (port 8000)
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — frontend dev server (port 5173)
cd frontend
npm install   # first time only
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api/*` and `/health` to `http://127.0.0.1:8000` (see `vite.config.ts`), so no CORS setup or `.env` is needed in dev.

## What's real vs. not yet built

- All data shown is pulled live through the same `nse_data_provider` / `factor_engine` / `multi_source_data` pipeline the Streamlit app uses — nothing here is mocked.
- Auth is username/password only, no session cookie/JWT yet (`routes/auth.py` returns a bare `user_id` the frontend holds in `localStorage`). Fine for local single-user testing; not for multi-user deployment as-is.
- The Screener's "Refresh universe" button hits `POST /api/refresh` synchronously — a full 200-stock pull can take several minutes and the request will hang open for that whole time. A job-queue + polling endpoint (sketched in `PHASE_1_FASTAPI_STARTER.md`) would fix this; not built yet.
- Opening/closing forward-test trades from the UI (`POST /api/trade`, `POST /api/trade/close`) isn't wired into a page yet — the backend routes exist and work (see `routes/refresh.py`), only the Forward-Test page's UI for it is still to build.

## Structure

```
src/
  api/client.ts        typed fetch wrapper for every /api/* route
  types.ts              response shapes, hand-matched against live API output
  context/AuthContext   localStorage-backed user_id/username
  components/           Nav, ChecklistTable
  pages/                Login, Screener, SearchProfile, Sectors, ForwardTest
```
