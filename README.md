# FT Bot Workspace (Backend + Frontend)

Minimal, production-oriented repo for the multi-user FastAPI backend and React frontend to orchestrate Freqtrade bots. Local user workspaces, data caches, and build artifacts are excluded to keep the repository lean.

## Prerequisites
- Python 3.12+ (default on Ubuntu 24.04)
- Node.js 20+ LTS
- Docker (for running Freqtrade bots)
- Optional: Nginx (static frontend hosting / reverse proxy)


## Repo Layout
- `backend/` — FastAPI service. Configure via env vars; persists its own DB.
- `frontend/tradingg_bot_front/` — Vite + React UI.
- `scripts/` — Utility scripts (e.g., backtest helpers).
- `config/` — Project-level configs if needed.




