from __future__ import annotations

from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


def _load_exchange_config(workspace_root: str) -> Dict[str, Any]:
    try:
        from .config_service import get_user_account_config
        acc = get_user_account_config(workspace_root)
        ex = (acc or {}).get("exchange") or {}
        return ex if isinstance(ex, dict) else {}
    except Exception:
        return {}


def _build_ccxt_client(ex_cfg: Dict[str, Any], trading_mode: str | None = None):
    try:
        import ccxt  # type: ignore
    except Exception as e:
        raise RuntimeError(f"ccxt is not installed: {e}")
    name = str(ex_cfg.get("name") or "").strip().lower()
    if not name:
        raise RuntimeError("Exchange name is not configured (exchange.name)")
    if not hasattr(ccxt, name):
        raise RuntimeError(f"Unsupported exchange '{name}' in ccxt")
    clazz = getattr(ccxt, name)
    params: Dict[str, Any] = {
        "apiKey": ex_cfg.get("key"),
        "secret": ex_cfg.get("secret"),
        "password": ex_cfg.get("password"),
        "uid": ex_cfg.get("uid"),
        "enableRateLimit": True,
    }
    # Merge optional ccxt per-user config overrides
    try:
        ccxt_conf = ex_cfg.get("ccxt_config") or {}
        if isinstance(ccxt_conf, dict):
            params.update(ccxt_conf)
    except Exception:
        pass
    # Respect trading mode to avoid permission errors (-2015) when keys are futures-only
    try:
        mode = (trading_mode or "spot").lower()
        opts = params.setdefault("options", {})
        if isinstance(opts, dict):
            if mode == "futures":
                opts.setdefault("defaultType", "future")
            else:
                opts.setdefault("defaultType", "spot")
    except Exception:
        pass
    client = clazz(params)
    # Sandbox support when available
    try:
        sandbox = bool(ex_cfg.get("sandbox", False))
        if hasattr(client, "setSandboxMode"):
            client.setSandboxMode(sandbox)
    except Exception:
        pass
    return client


def fetch_exchange_balance(workspace_root: str, trading_mode: str | None = None) -> Dict[str, Any] | None:
    """Fetch account balances from the configured exchange via ccxt.

    Returns a normalized payload compatible with the frontend expectations.
    Shape:
      {
        "assets": [ { "currency": "USDT", "available": 100.0, "free": 100.0, "used": 0.0, "total": 100.0 } ],
        "balance": { "USDT": { "free": 100.0, "used": 0.0, "total": 100.0 } },
      }
    """
    ex_cfg = _load_exchange_config(workspace_root)
    if not ex_cfg or not ex_cfg.get("name"):
        # No exchange configured
        return None
    try:
        client = _build_ccxt_client(ex_cfg, trading_mode=trading_mode)
    except Exception as e:
        logger.warning(f"Failed to initialize ccxt client: {e}")
        raise
    try:
        raw = client.fetch_balance()
    except Exception as e:
        logger.warning(f"Failed to fetch balance via ccxt: {e}")
        raise
    # ccxt balance includes 'free', 'used', 'total' dicts keyed by currency
    free_map = raw.get("free") or {}
    used_map = raw.get("used") or {}
    total_map = raw.get("total") or {}
    assets: List[Dict[str, Any]] = []
    currencies_map: Dict[str, Any] = {}
    try:
        keys = set(list(free_map.keys()) + list(used_map.keys()) + list(total_map.keys()))
        for c in sorted(keys):
            # Skip zero-only entries to reduce noise
            free = float(free_map.get(c) or 0.0)
            used = float(used_map.get(c) or 0.0)
            total = float(total_map.get(c) or 0.0)
            if free == 0.0 and used == 0.0 and total == 0.0:
                continue
            assets.append({
                "currency": c,
                "available": free,
                "free": free,
                "used": used,
                "total": total,
                # 'in_usdt' not computed here; frontend displays '-' when absent
            })
            currencies_map[c] = {"available": free, "free": free, "used": used, "total": total}
    except Exception:
        # Fallback to raw balances when mapping fails
        pass
    payload: Dict[str, Any] = {
        "assets": assets,
        "balance": currencies_map,
        "data": {"raw": raw},
    }
    return payload


def _read_composed_config(user_root: str, bot_userdir: str) -> Dict[str, Any]:
    """Compose and read the bot's effective config JSON."""
    try:
        from .config_service import compose_bot_config, compose_runtime_config
        import json
        path = compose_bot_config(user_root, bot_userdir, mode=None, active_strategy=None)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            pass
        # Fallback
        path2 = compose_runtime_config(bot_userdir)
        with open(path2, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def fetch_dryrun_balance(user_root: str, bot_userdir: str) -> Dict[str, Any]:
    """Return a dryrun balance that reflects closed trade profits and open trade reservations.

    - Start with 'dry_run_wallet' (dict or number) from composed config; default stake currency with 0 if missing.
    - Add sum of realized profits from closed trades in tradesv3/4.dryrun.sqlite.
    - Subtract reserved stake from open trades (sum of stake_amount for open rows).
    """
    import sqlite3
    from pathlib import Path
    cfg = _read_composed_config(user_root, bot_userdir)
    currency = str((cfg.get("stake_currency") or "USDT") or "USDT")
    wallet = cfg.get("dry_run_wallet")
    # Initial funds for stake currency
    initial_total: float = 0.0
    if isinstance(wallet, dict):
        try:
            initial_total = float(wallet.get(currency) or 0.0)
        except Exception:
            initial_total = 0.0
    elif isinstance(wallet, (int, float)):
        initial_total = float(wallet)
    # Gather dryrun trades from SQLite
    bot_dir = Path(bot_userdir).resolve()
    dry_candidates = [
        bot_dir / "tradesv3.dryrun.sqlite",
        bot_dir / "tradesv4.dryrun.sqlite",
    ]
    dry_db = next((p for p in dry_candidates if p.exists()), dry_candidates[0])
    realized_sum = 0.0
    reserved_sum = 0.0
    if dry_db.exists():
        try:
            uri = f"file:{dry_db.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # Detect columns present
            cur.execute("PRAGMA table_info('trades')")
            cols = [r[1] for r in cur.fetchall()]
            has = lambda c: c in cols
            # Build query to get needed fields
            fields = [
                *( ["realized_profit"] if has("realized_profit") else [] ),
                *( ["close_profit_abs"] if has("close_profit_abs") else [] ),
                *( ["stake_amount"] if has("stake_amount") else [] ),
                *( ["is_open"] if has("is_open") else [] ),
                *( ["close_date"] if has("close_date") else [] ),
            ]
            if not fields:
                fields = ["id"]
            sql = f"SELECT {', '.join(fields)} FROM trades"
            rows = cur.execute(sql).fetchall()
            for r in rows:
                d = dict(r)
                # Closed trades contribute profit
                is_open = d.get("is_open")
                close_date = d.get("close_date")
                closed = not (is_open == 1 or is_open is True) and close_date not in (None, "")
                if closed:
                    rp = d.get("realized_profit")
                    pa = d.get("close_profit_abs")
                    try:
                        realized_sum += float((rp if rp is not None else pa) or 0.0)
                    except Exception:
                        pass
                else:
                    # Open trade: reserve stake amount
                    try:
                        reserved_sum += float(d.get("stake_amount") or 0.0)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Failed to read dryrun trades: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
    # Compute available and total
    available = initial_total + realized_sum - reserved_sum
    if available < 0:
        available = available  # allow negative to reflect losses exceeding initial
    total = initial_total + realized_sum
    assets: List[Dict[str, Any]] = [
        {"currency": currency, "available": float(available), "free": float(available), "used": float(reserved_sum), "total": float(total)}
    ]
    balance: Dict[str, Any] = {
        currency: {"available": float(available), "free": float(available), "used": float(reserved_sum), "total": float(total)}
    }
    return {"assets": assets, "balance": balance, "data": {"source": "dryrun", "initial": initial_total, "realized_sum": realized_sum, "reserved_sum": reserved_sum}}
