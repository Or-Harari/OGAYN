# FT Multi-User Backend

This is a standalone FastAPI service for managing users, their workspaces, and bot lifecycle.

- Users have a workspace_root that points to their Freqtrade `user_data` folder (or parent containing it).
- Endpoints let you list/create strategies, edit meta config, and start/stop bot instances per user.

See `user_data/backend/README.md` for run instructions (identical here). Set `FT_BACKEND_DB` and `FT_JWT_SECRET` as needed.

Strategies should be defined per-bot (Freqtrade best practice). Each bot selects a concrete strategy class via its config (e.g., `"strategy": "MomentumPullbackStrategy"`). There is no shared global orchestrator. If you need regime/decision logic, implement it inside your bot's strategy class.
