# Path-based reverse proxy for multiple Freqtrade bots

This setup proxies multiple bots under one domain using path prefixes.
- Keeps the domain the same (e.g., `http://localhost:8088`) and isolates sessions per bot via `proxy_cookie_path`.
- Switch bots by changing only the path: `/bot/test10/`, `/bot/test8/`, etc.

## Files
- `backend/nginx/nginx.conf` — Nginx config with two example bots.
- `backend/nginx/run-nginx.ps1` — Run Nginx via Docker on Windows.

## Quick start (Windows + Docker)

1. Adjust ports and prefixes in `backend/nginx/nginx.conf`:
   - Replace `18082` with the published host port of your `Test10` bot.
   - Replace `18081` with the published host port of your other bot.
   - Duplicate the `location /bot/<name>/` blocks per bot.

2. Run Nginx:

```powershell
# From the repo root or from backend/nginx
.\backend
ginx


















```docker rm -f ft-nginx-proxy```powershell## Stop Nginx- Published ports: If you start bots with the same `listen_port`, the backend may assign a different free host port. Use the backend runtime info or `docker inspect` to find the actual published host port.- Absolute paths in UI: If the UI uses root-absolute URLs (like `/api/v1`, `/assets/`), uncomment the `sub_filter` rules in the config for that bot to rewrite them to the prefixed path.- WebSockets: upgrade headers are set; if live charts don’t connect, ensure the `/ws` blocks are present.- Cookie isolation: each bot's auth cookie is rewritten to its prefix path, so concurrent logins won’t collide.## Notes- Test8: `http://localhost:8088/bot/test8/`- Test10: `http://localhost:8088/bot/test10/`3. Open the proxy:```un-nginx.ps1