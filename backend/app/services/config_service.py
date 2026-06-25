from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
import tempfile
import socket
import secrets


def _ensure_group_writable_dir(path: Path) -> None:
    """Ensure directory exists with group-writable permissions.
    
    This allows both the backend (ftbot user) and Docker containers (UID 1000)
    to read/write files when they're in the same group (ftgroup).
    Directories should be owned by UID 1000:ftgroup for proper Docker access.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        # Set permissions: 775 = rwxrwxr-x (owner and group both have full access)
        os.chmod(path, 0o775)
    except Exception:
        pass  # Best effort


def _resolve_config_path(workspace_root: str) -> Path:
    ws = Path(workspace_root)
    # Prefer new structured config under configs/ for meta-only fallback
    # This function remains for legacy freqtrade config resolution.
    # prefer config.live.json; fallback to config.futures.json; then any config.*.json
    for name in ["config.live.json", "config.futures.json", "config.json"]:
        p = ws / name
        if p.is_file():
            return p
    # fallback: pick first config.*.json
    candidates = sorted(ws.glob("config*.json"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError("No Freqtrade config found in workspace")


DEFAULT_META: Dict[str, Any] = {
    "decision_log": {"enable": True, "path": None},
    "strategy_paths": [],
    "strategies": {},
    # Regime & DCA removed to keep meta minimal; strategies own these concerns if needed.
}


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            _deep_merge(a[k], v)
        else:
            a[k] = v
    return a


def _extract_meta_view(cfg: Dict[str, Any]) -> Dict[str, Any]:
    # Priority: custom_info.meta -> strategy_parameters.meta -> top-level meta -> {}
    ci = (cfg or {}).get("custom_info", {}) or {}
    sp = (cfg or {}).get("strategy_parameters", {}) or {}
    return ci.get("meta") or sp.get("meta") or cfg.get("meta") or {}


def _meta_file_path(workspace_root: str) -> Path:
    return Path(workspace_root) / "configs" / "meta.json"


def _account_file_path(workspace_root: str) -> Path:
    return Path(workspace_root) / "configs" / "account.json"


def _bot_file_path(workspace_root: str) -> Path:
    return Path(workspace_root) / "configs" / "bot.json"


# Mode-specific config filenames under bot configs directory
MODE_FILENAMES = {
    "live": "live.json",
    "dryrun": "dryrun.json",
    "backstage": "backstage.json",
}


def _bot_mode_file_path(bot_root: str, mode: str) -> Path:
    fname = MODE_FILENAMES.get(mode.lower())
    if not fname:
        raise ValueError(f"Unsupported bot mode '{mode}'. Expected one of: {', '.join(MODE_FILENAMES)}")
    return Path(bot_root) / "configs" / fname


def load_meta_config(workspace_root: str) -> Dict[str, Any]:
    # Prefer new meta.json under configs/
    meta_path = _meta_file_path(workspace_root)
    if meta_path.exists():
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f) or {}
        except Exception:
            meta = {}
        merged = json.loads(json.dumps(DEFAULT_META))
        return _deep_merge(merged, meta)
    # Legacy: read from freqtrade config
    try:
        cfg_path = _resolve_config_path(workspace_root)
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        meta = _extract_meta_view(cfg)
    except FileNotFoundError:
        meta = {}
    merged = json.loads(json.dumps(DEFAULT_META))
    return _deep_merge(merged, meta)


def save_meta_config(meta: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
    # Prefer writing to new configs/meta.json
    meta_path = _meta_file_path(workspace_root)
    _ensure_group_writable_dir(meta_path.parent)
    try:
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta or {}, f, indent=2, ensure_ascii=False)
        merged = json.loads(json.dumps(DEFAULT_META))
        return _deep_merge(merged, meta or {})
    except Exception:
        # Fallback to legacy freqtrade config path if meta.json cannot be written
        cfg_path = _resolve_config_path(workspace_root)
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("custom_info", {})
        cfg["custom_info"]["meta"] = meta or {}
        cfg["meta"] = meta or {}
        with cfg_path.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        merged = json.loads(json.dumps(DEFAULT_META))
        return _deep_merge(merged, meta or {})


# --- Account config CRUD ---
def load_account_config(workspace_root: str) -> Dict[str, Any]:
    p = _account_file_path(workspace_root)
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    return {}


def save_account_config(data: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
    p = _account_file_path(workspace_root)
    _ensure_group_writable_dir(p.parent)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data or {}, f, indent=2, ensure_ascii=False)
    return data or {}


# --- Bot config CRUD ---
def _parse_first_json_object(text: str) -> Dict[str, Any] | None:
    """Best-effort: extract the first complete JSON object from a text that may contain trailing garbage.

    This protects against concurrent writes producing concatenated JSON objects.
    """
    try:
        # Fast path
        return json.loads(text)
    except Exception:
        pass
    # Streaming brace counter (ignores braces inside strings)
    in_str = False
    esc = False
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        try:
                            candidate = text[start:i+1]
                            return json.loads(candidate)
                        except Exception:
                            return None
    return None


def load_bot_config(workspace_root: str) -> Dict[str, Any]:
    p = _bot_file_path(workspace_root)
    if p.exists():
        raw = p.read_text(encoding="utf-8", errors="ignore")
        try:
            return json.loads(raw) or {}
        except Exception:
            # Try to salvage the first JSON object and rewrite atomically
            obj = _parse_first_json_object(raw)
            if obj is not None:
                try:
                    save_bot_config(obj, workspace_root)
                except Exception:
                    pass
                return obj
            # As a last resort, return empty dict (caller may decide to reset)
            return {}
    return {}


def save_bot_config(data: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
    """Atomically write bot.json to avoid corruption during concurrent writes."""
    p = _bot_file_path(workspace_root)
    _ensure_group_writable_dir(p.parent)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="bot.json.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data or {}, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, p)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return data or {}


# ---- High-level CRUD / Validation integration ----
from .config_validation import (
    USER_PLACEHOLDER,
    BOT_PLACEHOLDER,
    validate_user_config,
    validate_bot_config,
    aggregate_mode_validation,
)


def get_user_account_config(user_root: str) -> Dict[str, Any]:
    return load_account_config(user_root)


def update_user_account_config(user_root: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    cur = load_account_config(user_root)
    # shallow merge for now; deep merge for nested 'exchange'
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(cur.get(k), dict):
            cur[k].update(v)
        else:
            cur[k] = v
    return save_account_config(cur, user_root)


def reset_user_account_config(user_root: str) -> Dict[str, Any]:
    return save_account_config(USER_PLACEHOLDER, user_root)


def get_bot_config(bot_userdir: str) -> Dict[str, Any]:
    return load_bot_config(bot_userdir)


def update_bot_config(bot_userdir: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    cur = load_bot_config(bot_userdir)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(cur.get(k), dict):
            cur[k].update(v)
        else:
            cur[k] = v
    return save_bot_config(cur, bot_userdir)


def reset_bot_config(bot_userdir: str) -> Dict[str, Any]:
    # Keep any existing pair_whitelist if user already customized one
    existing = load_bot_config(bot_userdir)
    base = json.loads(json.dumps(BOT_PLACEHOLDER))
    if existing.get("pair_whitelist"):
        base["pair_whitelist"] = existing["pair_whitelist"]
    return save_bot_config(base, bot_userdir)


def validate_user_and_bot(user_root: str, bot_userdir: str, mode: str | None = None) -> Dict[str, Any]:
    ucfg = load_account_config(user_root)
    bcfg = load_bot_config(bot_userdir)
    if mode is None:
        mode = bcfg.get("mode") if isinstance(bcfg, dict) else None
    return aggregate_mode_validation(ucfg, bcfg, mode)


# --- Compose runtime Freqtrade config from account+bot+meta ---
def compose_runtime_config(workspace_root: str) -> Path:  # Legacy wrapper
    """Deprecated: kept for backward compatibility with pre Big Bang layout.
    Generates config inside the same workspace root (user-centric design).
    """
    return _compose_config_simple(workspace_root)


def _compose_config_simple(workspace_root: str) -> Path:
    """Original single-root composition used before per-bot separation."""
    account = load_account_config(workspace_root)
    bot = load_bot_config(workspace_root)
    meta = load_meta_config(workspace_root)
    cfg: Dict[str, Any] = {}
    cfg.update(bot or {})
    if account.get("exchange"):
        cfg["exchange"] = account["exchange"]
    return _finalize_and_write_cfg(cfg, meta, Path(workspace_root) / "configs" / "config.generated.json", sources=[("bot", _bot_file_path(workspace_root)), ("account", _account_file_path(workspace_root)), ("meta", _meta_file_path(workspace_root))])


def _load_json_if(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}
    return {}


SYSTEM_DEFAULTS: Dict[str, Any] = {
    "dry_run": True,
    "trading_mode": "spot",
    "stake_currency": "USDT",
    "leverage": 1,  # default leverage (spot ignored)
    "entry_pricing": {"price_side": "ask", "use_order_book": False, "order_book_top": 1, "price_last_balance": 0.0},
    "exit_pricing": {"price_side": "bid", "use_order_book": False, "order_book_top": 1, "price_last_balance": 0.0},
    # Ensure bot auto-starts trading loop unless explicitly overridden.
    # Freqtrade defaults to STOPPED in recent versions if not provided.
    "initial_state": "running",
}


def compose_bot_config(user_workspace_root: str, bot_user_data_root: str, mode: str | None = None, active_strategy: dict | None = None) -> Path:
    """Compose layered config for a bot.

    Layers (low -> high precedence):
      1. System defaults
      2. User-level defaults (configs/user/*.json) if directory exists
      3. User account.json (exchange creds, etc.)
      4. User meta.json (strategy meta injection)
      5. Bot bot.json (overrides)
      6. Runtime injections (pairlists, pairs alias, strategy fallback)
    """
    user_root = Path(user_workspace_root).resolve()
    bot_root = Path(bot_user_data_root).resolve()
    user_configs_dir = user_root / "configs" / "user"
    bot_configs_dir = bot_root / "configs"

    sources: List[Tuple[str, Path]] = []
    cfg: Dict[str, Any] = {}
    # 1. system defaults
    cfg = _deep_merge(cfg, json.loads(json.dumps(SYSTEM_DEFAULTS)))
    # 2. user-level defaults directory
    if user_configs_dir.is_dir():
        for jf in sorted(user_configs_dir.glob("*.json")):
            data = _load_json_if(jf)
            if data:
                cfg = _deep_merge(cfg, data)
                sources.append((f"user:{jf.name}", jf))
    # 3. user account.json (deferred override applied again after mode merge to avoid placeholders winning)
    account = _load_json_if(user_root / "configs" / "account.json")
    if account:
        cfg = _deep_merge(cfg, {"exchange": account.get("exchange", {})})
        sources.append(("account", user_root / "configs" / "account.json"))
    # 4. meta.json (handled separately for injection later)
    meta = load_meta_config(str(user_root))
    sources.append(("meta", user_root / "configs" / "meta.json"))
    # 5. bot.json base (may contain 'mode' override)
    bot_cfg_path = bot_configs_dir / "bot.json"
    bot_cfg = _load_json_if(bot_cfg_path)
    if bot_cfg:
        cfg = _deep_merge(cfg, bot_cfg)
        sources.append(("bot", bot_cfg_path))
        # If mode not explicitly passed, derive from bot.json
        if mode is None:
            mode = bot_cfg.get("mode")
    # 5b. mode-specific file merge (live.json / dryrun.json / backstage.json)
    if mode:
        try:
            mode_path = _bot_mode_file_path(str(bot_root), mode)
            if mode_path.exists():
                mode_cfg = _load_json_if(mode_path)
                if mode_cfg:
                    # Prevent mode templates from overriding user exchange credentials
                    try:
                        ex = mode_cfg.get("exchange")
                        if isinstance(ex, dict):
                            for k in ("key", "secret", "password", "uid"):
                                if k in ex:
                                    ex.pop(k, None)
                    except Exception:
                        pass
                    cfg = _deep_merge(cfg, mode_cfg)
                    sources.append((f"mode:{mode}", mode_path))
        except Exception:
            pass
    # Re-apply account exchange after mode merge so user credentials override any placeholders
    try:
        if account:
            cfg = _deep_merge(cfg, {"exchange": account.get("exchange", {})})
    except Exception:
        pass
    # 5c. sane defaults for backstage when no explicit mode file provided
    try:
        if (mode or "").lower() == "backstage":
            # Ensure non-trading startup unless overridden explicitly
            cfg.setdefault("initial_state", "stopped")
            # Backstage must be non-live
            cfg["dry_run"] = True
    except Exception:
        pass
    # 6. strategy_path resolution - unify to <user_workspace_root>/strategies
    unified_dir_candidates = [
        user_root / "strategies",
        user_root / "user" / "strategies",  # fallback for older code paths
    ]
    unified_dir = next((p for p in unified_dir_candidates if p.exists()), unified_dir_candidates[0])
    chosen_path: str | None = None
    # Attempt to locate the concrete strategy file under the unified dir
    try:
        strategy_name = cfg.get("strategy")
        if isinstance(strategy_name, str) and strategy_name:
            target = f"{strategy_name}.py"
            basep = Path(unified_dir)
            if basep.exists():
                for cand in basep.rglob(target):
                    chosen_path = str(cand.parent)
                    break
    except Exception:
        chosen_path = None
    # Fallback to unified dir itself
    if not chosen_path:
        chosen_path = str(unified_dir)
    cfg["strategy_path"] = chosen_path

    # 7. finalize & write
    out_path = bot_configs_dir / "config.generated.json"
    return _finalize_and_write_cfg(cfg, meta, out_path, sources=sources)


def _finalize_and_write_cfg(cfg: Dict[str, Any], meta: Dict[str, Any], out_path: Path, sources: List[Tuple[str, Path]]):
    # Do not infer or inject strategy. If missing, start validation will fail explicitly.
    # Ensure initial_state default if still missing after layering
    cfg.setdefault("initial_state", SYSTEM_DEFAULTS.get("initial_state", "running"))
    # Ensure local API server is enabled for backend proxying (single entrypoint)
    def _pick_free_port(start: int = 18080, max_tries: int = 500) -> int:
        p = start
        for _ in range(max_tries):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("127.0.0.1", p))
                    return p
                except OSError:
                    p += 1
        return start

    api = cfg.get("api_server") or {}
    if not api.get("enabled"):
        cfg["api_server"] = {
            "enabled": True,
            # Inside docker, Freqtrade webserver must listen on 0.0.0.0 to accept connections via port publishing
            "listen_ip_address": "0.0.0.0",
            "listen_port": _pick_free_port(),
            "verbosity": "error",
            "enable_openapi": False,
            "jwt_secret_key": secrets.token_hex(24),
            "CORS_origins": [],
            "username": "ftproxy",
            "password": secrets.token_urlsafe(18),
            "ws_token": secrets.token_urlsafe(24),
        }
    else:
        # Ensure port and host defaults
        api.setdefault("listen_ip_address", "0.0.0.0")
        api.setdefault("listen_port", _pick_free_port())
        api.setdefault("verbosity", "error")
        api.setdefault("enable_openapi", False)
        api.setdefault("jwt_secret_key", secrets.token_hex(24))
        api.setdefault("CORS_origins", [])
        api.setdefault("username", "ftproxy")
        api.setdefault("password", secrets.token_urlsafe(18))
        api.setdefault("ws_token", secrets.token_urlsafe(24))
        cfg["api_server"] = api

    # Ensure persistent local SQLite DB path is set explicitly.
    # Recent Freqtrade versions may not create the default DB unless a db_url is provided.
    try:
        if not isinstance(cfg.get("db_url"), str) or not cfg.get("db_url"):
            # Use container paths – config is consumed inside docker.
            is_dry = bool(cfg.get("dry_run"))
            dbfile = "/freqtrade/user_data/tradesv3.dryrun.sqlite" if is_dry else "/freqtrade/user_data/tradesv3.sqlite"
            cfg["db_url"] = f"sqlite:///{dbfile}"
    except Exception:
        # Best-effort only – fall back to Freqtrade defaults if anything goes wrong.
        pass

    # Make sure a logfile is defined so we also get on-disk logs for troubleshooting.
    try:
        if not isinstance(cfg.get("logfile"), str) or not cfg.get("logfile"):
            cfg["logfile"] = "/freqtrade/user_data/logs/freqtrade.log"
    except Exception:
        pass

    # Remove any parameters that must live in the strategy (not config)
    strategy_owned = [
        "minimal_roi",
        "timeframe",
        "stoploss",
        "max_open_trades",
        "trailing_stop",
        "trailing_stop_positive",
        "trailing_stop_positive_offset",
        "trailing_only_offset_is_reached",
        "use_custom_stoploss",
        "process_only_new_candles",
        "order_types",
        "order_time_in_force",
        "unfilledtimeout",
        "disable_dataframe_checks",
        "use_exit_signal",
        "exit_profit_only",
        "exit_profit_offset",
        "ignore_roi_if_entry_signal",
        "ignore_buying_expired_candle_after",
        "position_adjustment_enable",
        "max_entry_position_adjustment",
    ]
    for k in strategy_owned:
        if k in cfg:
            cfg.pop(k, None)
    # Spot/Futures mode filtering
    tmode = (cfg.get("trading_mode") or "spot").lower()
    if tmode == "spot":
        for k in ("liquidation_buffer", "margin_mode"):
            cfg.pop(k, None)
        cfg.pop("leverage", None)
    # Ensure sane pricing on futures: avoid ticker-only pricing (which may be unavailable) by enabling orderbook pricing
    if tmode == "futures":
        try:
            cfg.setdefault("entry_pricing", {})
            cfg.setdefault("exit_pricing", {})
            # Force orderbook pricing for both entry and exit to avoid 'Ticker pricing not available' errors
            cfg["entry_pricing"]["use_order_book"] = True
            cfg["exit_pricing"]["use_order_book"] = True
            # Preserve existing price_side and other fields; defaults are merged below if missing
            # Clamp leverage to sane bounds (1-50)
            try:
                lev_raw = cfg.get("leverage", 1)
                lev = int(lev_raw) if not isinstance(lev_raw, bool) else 1
                if lev < 1:
                    lev = 1
                if lev > 50:
                    lev = 50
                cfg["leverage"] = lev
            except Exception:
                cfg["leverage"] = 1
        except Exception:
            pass
    # Merge pricing defaults without overwriting existing keys
    for block in ("entry_pricing", "exit_pricing"):
        defaults = SYSTEM_DEFAULTS[block]
        if not isinstance(cfg.get(block), dict):
            cfg[block] = defaults
        else:
            for k, v in defaults.items():
                cfg[block].setdefault(k, v)
    # Meta injection
    cfg.setdefault("custom_info", {})
    cfg["custom_info"]["meta"] = meta
    cfg["meta"] = meta
    cfg.setdefault("strategy_parameters", {})
    cfg["strategy_parameters"]["meta"] = meta
    # Pairlists injection
    if "pair_whitelist" in cfg and "pairlists" not in cfg:
        cfg["pairlists"] = [{"method": "StaticPairList"}]
    if "pair_whitelist" in cfg and "pairs" not in cfg:
        pw = cfg["pair_whitelist"]
        if isinstance(pw, list):
            cfg["pairs"] = list(pw)
        else:
            cfg["pairs"] = pw
    _ensure_group_writable_dir(out_path.parent)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    # Optional sources map for debugging
    if out_path.parent.joinpath("..", "..").exists() and bool(int(os.environ.get("FT_CONFIG_DEBUG", "0"))):  # type: ignore
        src_manifest = {label: str(path) for label, path in sources}
        with (out_path.parent / "config.generated.sources.json").open("w", encoding="utf-8") as sf:
            json.dump(src_manifest, sf, indent=2)
    return out_path
