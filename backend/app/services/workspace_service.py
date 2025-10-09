from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _project_root() -> Path:
    # backend/app/services -> project root at ../../..
    return Path(__file__).resolve().parents[3]


def default_workspaces_base() -> str:
    """Return default base folder for user workspaces.
    Env override: FT_WS_BASE. Defaults to '<project_root>/workspaces'.
    """
    env = os.environ.get("FT_WS_BASE")
    if env:
        return str(Path(env).expanduser().resolve())
    return str((_project_root() / "workspaces").resolve())


def create_workspace(name: str, base_dir: Optional[str] = None) -> str:
    """Create a user workspace (authoring layer, not a runnable bot).

    Layout:
      <base>/<name>/user/ (user root)
        configs/
          account.json
          meta.json
          user/  (optional layered defaults)
        strategies/
        shared/

    Returns absolute path to the user root (NOT the old user_data path).
    """
    base = Path(base_dir or default_workspaces_base()).expanduser().resolve()
    user_root = base / name / "user"
    (user_root / "configs" / "user").mkdir(parents=True, exist_ok=True)
    (user_root / "strategies").mkdir(parents=True, exist_ok=True)
    (user_root / "shared").mkdir(parents=True, exist_ok=True)
    # Seed base configs if missing
    account_path = user_root / "configs" / "account.json"
    meta_path = user_root / "configs" / "meta.json"
    if not account_path.exists():
        # Use placeholder scaffold from config_validation to ensure consistency
        try:
            from .config_validation import USER_PLACEHOLDER  # type: ignore
            import json as _json
            account_path.write_text(_json.dumps(USER_PLACEHOLDER, indent=2), encoding="utf-8")
        except Exception:
            account_path.write_text(
                '{"exchange": {"name": "binance", "key": "", "secret": "", "password": "", "sandbox": false}}',
                encoding="utf-8",
            )
    if not meta_path.exists():
        meta_path.write_text(
            '{"strategy_paths": ["./strategies"], "decision_log": {"enable": true, "path": null}, "regime": {"enable": true, "tf": "1h", "ema_len": 200, "adx_thresh": 20}, "strategies": {}, "dca": {"enable": true, "total_budget": 2000.0, "mode": "martingale", "thresholds": [3.0, 6.0, 10.0], "max_adds": 3}}',
            encoding="utf-8",
        )
    return str(user_root)


def create_bot_workspace(user_root: str, bot_name: str) -> str:
    """Create a bot runtime workspace.

    Layout:
      <user_root>/../bots/<bot_name>/user_data/
        configs/bot.json
        strategies/MainStrategy.py (shim only)
        logs/
        data/

    Returns absolute path to the bot's user_data root.
    """
    uroot = Path(user_root).expanduser().resolve()
    bots_root = uroot.parent / "bots" / bot_name / "user_data"
    (bots_root / "configs").mkdir(parents=True, exist_ok=True)
    (bots_root / "logs").mkdir(parents=True, exist_ok=True)
    (bots_root / "data").mkdir(parents=True, exist_ok=True)
    (bots_root / "strategies").mkdir(parents=True, exist_ok=True)
    # Seed bot.json if missing
    bot_cfg = bots_root / "configs" / "bot.json"
    if not bot_cfg.exists():
        try:
            from .config_validation import BOT_PLACEHOLDER  # type: ignore
            import json as _json
            bot_cfg.write_text(_json.dumps(BOT_PLACEHOLDER, indent=2), encoding="utf-8")
        except Exception:
            bot_cfg.write_text(
                '{"dry_run": true, "stake_currency": "USDT", "timeframe": "1m", "pair_whitelist": ["BTC/USDT", "ETH/USDT"], "strategy": "MainStrategy"}',
                encoding="utf-8",
            )
    # Seed mode-specific templates if absent
    live_cfg = bots_root / "configs" / "live.json"
    dry_cfg = bots_root / "configs" / "dryrun.json"
    back_cfg = bots_root / "configs" / "backstage.json"
    if not live_cfg.exists():
        live_cfg.write_text(
            '{"dry_run": false, "exchange": {"key": "__REQUIRED__", "secret": "__REQUIRED__"}}',
            encoding="utf-8",
        )
    if not dry_cfg.exists():
        dry_cfg.write_text(
            '{"dry_run": true}',
            encoding="utf-8",
        )
    if not back_cfg.exists():
        back_cfg.write_text(
            '{"dry_run": true, "backstage": true}',
            encoding="utf-8",
        )
    # Create shim
    shim = bots_root / "strategies" / "MainStrategy.py"
    if not shim.exists():
        shim.write_text(
            (
                "import sys, pathlib\n"
                "# Ascend to locate project root containing backend/app\n"
                "_p = pathlib.Path(__file__).resolve().parent\n"
                "_root = None\n"
                "for _ in range(12):\n"
                "    if (_p / 'backend' / 'app').is_dir():\n"
                "        _root = _p\n"
                "        break\n"
                "    if _p.parent == _p: break\n"
                "    _p = _p.parent\n"
                "if not _root: raise RuntimeError('Cannot locate project root (backend/app) for MainStrategy shim')\n"
                "if str(_root) not in sys.path: sys.path.insert(0, str(_root))\n"
                "from backend.app.trading_core.main_strategy import MainStrategy as _CoreMainStrategy\n"
                "class MainStrategy(_CoreMainStrategy):\n"
                "    pass\n"
                "__all__ = ['MainStrategy']\n"
            ),
            encoding="utf-8",
        )
    return str(bots_root)


def validate_workspace(path: str) -> str:
    """Validate and normalize a user workspace path.
    Accept either the user_data folder itself, or a parent containing 'user_data'.
    Ensures strategies dir exists.
    Returns normalized absolute path to user_data.
    """
    p = Path(path).expanduser().resolve()
    if (p / 'user_data').is_dir():
        p = p / 'user_data'
    if not p.is_dir():
        raise ValueError("Workspace path not found")
    if p.name != 'user_data':
        raise ValueError("Workspace must be 'user_data' or contain a 'user_data' folder")
    # Ensure strategies folder exists
    (p / 'strategies' / '_strategies').mkdir(parents=True, exist_ok=True)
    init_path = p / 'strategies' / '_strategies' / '__init__.py'
    if not init_path.exists():
        init_path.write_text("", encoding='utf-8')
    return str(p)
