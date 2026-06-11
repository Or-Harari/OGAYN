# FT Bot Workspace (Backend + Frontend)

Minimal, production-oriented repo for the multi-user FastAPI backend and React frontend to orchestrate Freqtrade bots. Local user workspaces, data caches, and build artifacts are excluded to keep the repository lean.

## Prerequisites
- Python 3.12+ (default on Ubuntu 24.04)
- Node.js 20+ LTS
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

**For production deployment to Linux servers, see the complete deployment package:**
- **[deployment/START_HERE.md](deployment/START_HERE.md)** - Complete overview
- **[deployment/QUICKSTART.md](deployment/QUICKSTART.md)** - Fast deployment (20 minutes)
- **[deployment/DEPLOYMENT_GUIDE.md](deployment/DEPLOYMENT_GUIDE.md)** - Comprehensive guide
- **[deployment/SECURITY_CHECKLIST.md](deployment/SECURITY_CHECKLIST.md)** - Security hardening

The deployment package includes:
- Systemd service configuration with security sandboxing
- Nginx configuration with SSL/HTTPS and security headers
- Automated deployment, backup, and health check scripts
- Complete documentation and security checklists
- Environment-based CORS configuration

Quick overview:
- Build frontend static assets:
  ```powershell
  cd frontend/tradingg_bot_front
  npm ci
  npm run build
  ```
  The output lives under `frontend/tradingg_bot_front/dist`.
- Serve frontend via Nginx (config in `deployment/nginx/`)
- Run backend as systemd service (config in `deployment/systemd/`)
- Ensure `FT_JWT_SECRET` and `ENVIRONMENT=production` are set
- Freqtrade bots run in Docker containers managed by backend

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
- `ENVIRONMENT` — Set to `production` for production deployment (affects CORS behavior).
- `FT_BACKEND_DB` — Optional path for backend SQLite DB.
- `FT_WS_BASE` — Optional base directory for user workspaces.
- `FT_BACKTEST_MUTATE_BOT` — If `true`, backtest endpoints mutate bot status (default `false`).
- `CORS_ORIGINS` — Optional comma-separated list of allowed origins (production only).

## Updating Production
1. Bump `VERSION`, commit and tag.
2. Push to GitHub.
3. On server:
   - `git pull`
   - Restart backend service
   - Rebuild frontend and deploy static files
4. Verify health via `/auth/login`, `/users/{id}/bots`, and UI.

