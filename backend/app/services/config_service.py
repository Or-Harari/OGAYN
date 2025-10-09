from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple


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
    meta_path.parent.mkdir(parents=True, exist_ok=True)
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
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data or {}, f, indent=2, ensure_ascii=False)
    return data or {}


# --- Bot config CRUD ---
def load_bot_config(workspace_root: str) -> Dict[str, Any]:
    p = _bot_file_path(workspace_root)
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    return {}


def save_bot_config(data: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
    p = _bot_file_path(workspace_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data or {}, f, indent=2, ensure_ascii=False)
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
    "timeframe": "1m",
    "stake_currency": "USDT",
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
    # 3. user account.json
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
                    cfg = _deep_merge(cfg, mode_cfg)
                    sources.append((f"mode:{mode}", mode_path))
        except Exception:
            pass
    # Inject active_strategy if provided (overrides meta active strategy spec)
    if active_strategy:
        meta.setdefault("active_strategy", {})
        for k, v in active_strategy.items():
            if v is not None:
                meta.setdefault("active_strategy", {})[k] = v
    # 6. finalize & write
    out_path = bot_configs_dir / "config.generated.json"
    return _finalize_and_write_cfg(cfg, meta, out_path, sources=sources)


def _finalize_and_write_cfg(cfg: Dict[str, Any], meta: Dict[str, Any], out_path: Path, sources: List[Tuple[str, Path]]):
    # Ensure strategy
    cfg.setdefault("strategy", "MainStrategy")
    # Ensure initial_state default if still missing after layering
    cfg.setdefault("initial_state", SYSTEM_DEFAULTS.get("initial_state", "running"))
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    # Optional sources map for debugging
    if out_path.parent.joinpath("..", "..").exists() and bool(int(os.environ.get("FT_CONFIG_DEBUG", "0"))):  # type: ignore
        src_manifest = {label: str(path) for label, path in sources}
        with (out_path.parent / "config.generated.sources.json").open("w", encoding="utf-8") as sf:
            json.dump(src_manifest, sf, indent=2)
    return out_path
