# FT Bot Workspace (Backend + Frontend)

Minimal, production-oriented repo for the multi-user FastAPI backend and React frontend to orchestrate Freqtrade bots. Local user workspaces, data caches, and build artifacts are excluded to keep the repository lean.

## Prerequisites
- Python 3.11+
- Node.js 18+
- Docker (for running Freqtrade bots)
- Optional: Nginx (static frontend hosting / reverse proxy)

## Quick Start (Dev)

Backend:
1. Create a virtual environment and install deps:
   ```bash
   python -m venv .venv
   .venv/Scripts/Activate.ps1  # Windows PowerShell
   pip install -r backend/requirements.txt
   ```
2. Set env vars (PowerShell):
   ```powershell
   $env:FT_JWT_SECRET = "replace-with-strong-secret"
   # Optional: SQLite path (backend defaults to backend/data/backend.db)
   # $env:FT_BACKEND_DB = "c:\\path\\to\\backend.db"
   ```
3. Run FastAPI:
   ```powershell
   python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
   ```

Frontend:
1. Install deps and run dev server:
   ```powershell
   cd frontend/tradingg_bot_front
   npm ci
   npm run dev
   ```
2. Visit http://127.0.0.1:5173 (default Vite dev port).

## Production
- Build frontend static assets:
  ```powershell
  cd frontend/tradingg_bot_front
  npm ci
  npm run build
  ```
  The output lives under `frontend/tradingg_bot_front/dist`.
- Serve frontend via Nginx or any static server. A sample config is under `backend/nginx/`.
- Run backend as a service (e.g., `uvicorn` behind a process manager like `systemd`/`nssm`). Ensure `FT_JWT_SECRET` is set.
- Freqtrade bots run in Docker containers. Backend composes per-bot configs and proxies REST to containers.

## Versioning & Releases
- Repo has a plain `VERSION` file; bump it when releasing.
- Tag releases:
  ```powershell
  git add VERSION
  git commit -m "chore(release): v0.1.0"
  git tag v0.1.0
  git push origin HEAD --tags
  ```
- Deploy procedure: `git pull` on server, restart backend service, update frontend with new `dist` build.

## Repo Layout
- `backend/` — FastAPI service. Configure via env vars; persists its own DB.
- `frontend/tradingg_bot_front/` — Vite + React UI.
- `scripts/` — Utility scripts (e.g., backtest helpers).
- `config/` — Project-level configs if needed.

## What’s intentionally not versioned
- `workspaces/**` — per-user runtime content (configs, strategies, user_data).
- `bt-userdir/**` — isolated backtest workspace artifacts.
- Build outputs (`dist/`) and `node_modules/`.
- Local databases (`backend/data/*.db`).

## Environment Variables
- `FT_JWT_SECRET` — Backend JWT signing key (required).
- `FT_BACKEND_DB` — Optional path for backend SQLite DB.
- `FT_WS_BASE` — Optional base directory for user workspaces.
- `FT_BACKTEST_MUTATE_BOT` — If `true`, backtest endpoints mutate bot status (default `false`).

## Updating Production
1. Bump `VERSION`, commit and tag.
2. Push to GitHub.
3. On server:
   - `git pull`
   - Restart backend service
   - Rebuild frontend and deploy static files
4. Verify health via `/auth/login`, `/users/{id}/bots`, and UI.

