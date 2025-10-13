from __future__ import annotations

import os
import subprocess
import json
import time
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import BotProcess, User, Bot
from fastapi import HTTPException
from .config_service import compose_bot_config, compose_runtime_config, validate_user_and_bot  # legacy kept
from ..schemas import BacktestStartRequest


def _which_freqtrade() -> str:
    env_path = os.environ.get("FREQTRADE_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    return "freqtrade"


def _log_command(out_log: Path, cmd: list[str], env_additions: dict[str, str]) -> None:
    line = f"\n==== BOT START {time.strftime('%Y-%m-%d %H:%M:%S')} ===\nCMD: {' '.join(cmd)}\nENV_ADD: {json.dumps(env_additions)}\n"
    out_log.parent.mkdir(parents=True, exist_ok=True)
    with out_log.open("ab") as f:
        f.write(line.encode("utf-8", errors="ignore"))


def start_bot(db: Session, user: User, bot: Bot, config_path: Optional[str] = None) -> BotProcess:
    """Start a bot process using per-bot workspace and layered config.

    Args:
        user: owning user (for user root path)
        bot: bot DB record (bot.userdir points to bot user_data root)
        config_path: optional explicit config (normally ignored; we compose fresh)
    """
    user_root = Path(user.workspace_root).resolve()
    # Enforce single-instance per bot: don't start if an instance is already running
    existing = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    if existing and existing.pid:
        try:
            import psutil  # type: ignore
            p = psutil.Process(existing.pid)
            if p.is_running() and (getattr(psutil, 'STATUS_ZOMBIE', None) is None or p.status() != psutil.STATUS_ZOMBIE):
                raise HTTPException(status_code=409, detail={"message": "Bot is already running", "pid": existing.pid})
        except Exception:
            # If psutil fails or process not alive, allow start to proceed
            pass
    bot_userdir = Path(bot.userdir).resolve()
    # Auto-sync dry_run flag to mode before validation (in-memory adjustment only; not persisted here)
    mode = getattr(bot, "mode", None)
    if mode:
        mode_l = mode.lower()
        # Load bot config raw to adjust dry_run if inconsistent
        bot_cfg_path = Path(bot_userdir) / "configs" / "bot.json"
        try:
            if bot_cfg_path.exists():
                raw = json.loads(bot_cfg_path.read_text(encoding="utf-8")) or {}
                desired = (mode_l in {"dryrun", "backstage"})
                if mode_l == "live":
                    desired = False
                if raw.get("dry_run") != desired:
                    raw["dry_run"] = desired
                    bot_cfg_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except Exception:
            pass
    # Pre-validation (mode-aware, with relaxed credentials for non-live)
    validation = validate_user_and_bot(str(user_root), str(bot_userdir), mode=mode)
    if not validation.get("ok"):
        detail = {
            "message": "Configuration validation failed",
            "mode": validation.get("mode"),
            "user_errors": validation.get("user_errors", []),
            "bot_errors": validation.get("bot_errors", []),
        }
        raise HTTPException(status_code=422, detail=detail)

    # Compose layered config inside bot workspace
    # Decode active strategy spec if stored
    active_strategy_spec = None
    if getattr(bot, "active_strategy", None):
        try:
            active_strategy_spec = json.loads(bot.active_strategy)
        except Exception:
            active_strategy_spec = None
    try:
        cfg_path = compose_bot_config(
            str(user_root),
            str(bot_userdir),
            mode=getattr(bot, "mode", None),
            active_strategy=active_strategy_spec,
        )
    except Exception:
        # Fallback to deprecated runtime config (legacy path) if something unexpected happens
        cfg_path = compose_runtime_config(str(bot_userdir))

    logs_dir = bot_userdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / "bot.out.log"
    err_log = logs_dir / "bot.err.log"

    cmd = [
        _which_freqtrade(),
        "trade",
        "--config",
        str(cfg_path),
        "--userdir",
        str(bot_userdir),
    ]

    # Ensure strategy presence: prefer config; do not auto-force a default strategy name
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg_json = json.load(f)
        if not cfg_json.get("strategy"):
            raise HTTPException(status_code=422, detail="Strategy not set in composed config. Please specify a concrete strategy class name.")
    except HTTPException:
        raise
    except Exception:
        # If we cannot read the config to confirm, proceed and let freqtrade error explicitly
        pass

    # Environment adjustments (PYTHONPATH for shared strategies in user workspace)
    env = os.environ.copy()
    # Ensure Python can import shared backend modules (e.g., backend.app.*) and user workspace
    file_path = Path(__file__).resolve()
    # repo_root is 3 levels up from backend/app/services -> <repo>/
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    py_path_parts = [str(user_root), str(repo_root)] + ([env.get("PYTHONPATH")] if env.get("PYTHONPATH") else [])
    env["PYTHONPATH"] = os.pathsep.join(py_path_parts)
    additions = {"PYTHONPATH": env["PYTHONPATH"]}
    _log_command(out_log, cmd, additions)

    # Spawn
    with out_log.open("ab") as out, err_log.open("ab") as err:
        proc = subprocess.Popen(
            cmd,
            stdout=out,
            stderr=err,
            cwd=str(bot_userdir),
            shell=False,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0,
        )

    # Persist / replace existing BotProcess for this bot
    rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    if not rec:
        rec = BotProcess(bot_id=bot.id)
        db.add(rec)
    rec.pid = proc.pid
    rec.status = "running"
    rec.config_path = str(cfg_path)
    rec.exit_code = None
    rec.last_error = None
    db.commit()
    db.refresh(rec)

    # Early-exit detection (process crashed immediately)
    time.sleep(float(os.environ.get("FT_BOT_EARLY_EXIT_WAIT", "0.5")))
    if proc.poll() is not None:  # exited
        rec.exit_code = proc.returncode
        rec.status = "error" if proc.returncode else "stopped"
        # Capture tail of stderr
        try:
            with err_log.open("rb") as ef:
                data = ef.read()[-2048:]
            snippet = data.decode("utf-8", errors="ignore")
            rec.last_error = snippet.strip().splitlines()[-10:][-1] if snippet else "Exited immediately"
        except Exception:
            rec.last_error = "Exited immediately (log unreadable)"
        db.commit()
        db.refresh(rec)
    return rec


def stop_bot(db: Session, bot: Bot) -> BotProcess:
    rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    if not rec or not rec.pid:
        if not rec:
            rec = BotProcess(bot_id=bot.id, status="stopped")
            db.add(rec)
            db.commit()
            db.refresh(rec)
        return rec
    try:
        import psutil  # type: ignore

        p = psutil.Process(rec.pid)
        p.terminate()
        p.wait(timeout=10)
        rec.status = "stopped"
        rec.pid = None
        db.commit()
        db.refresh(rec)
        return rec
    except Exception as e:
        rec.status = "unknown"
        db.commit()
        db.refresh(rec)
        raise e


def bot_status(db: Session, bot: Bot):
    rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    if not rec or not rec.pid:
        return {"status": rec.status if rec else "stopped"}
    try:
        import psutil  # type: ignore
        p = psutil.Process(rec.pid)
        alive = p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        return {
            "status": "running" if alive else rec.status,
            "pid": rec.pid,
            "config": rec.config_path,
            "exit_code": rec.exit_code,
            "last_error": rec.last_error,
        }
    except Exception:
        return {"status": "unknown", "pid": rec.pid, "config": rec.config_path}


def start_backtest(db: Session, user: User, bot: Bot, params: BacktestStartRequest) -> BotProcess:
    """Start a backtest process for the given bot using its composed config.

    This uses freqtrade backtesting mode and writes outputs to the bot's user_data.
    """
    user_root = Path(user.workspace_root).resolve()
    bot_userdir = Path(bot.userdir).resolve()
    # Validate config environment (mode does not matter for backtest, but we'll keep relaxed creds)
    validation = validate_user_and_bot(str(user_root), str(bot_userdir), mode=getattr(bot, "mode", None))
    if not validation.get("ok"):
        detail = {
            "message": "Configuration validation failed",
            "mode": validation.get("mode"),
            "user_errors": validation.get("user_errors", []),
            "bot_errors": validation.get("bot_errors", []),
        }
        raise HTTPException(status_code=422, detail=detail)

    # Compose config (honors active_strategy)
    try:
        active_strategy_spec = None
        if getattr(bot, "active_strategy", None):
            active_strategy_spec = json.loads(bot.active_strategy)
    except Exception:
        active_strategy_spec = None
    try:
        cfg_path = compose_bot_config(
            str(user_root),
            str(bot_userdir),
            mode=getattr(bot, "mode", None),
            active_strategy=active_strategy_spec,
        )
    except Exception:
        cfg_path = compose_runtime_config(str(bot_userdir))

    logs_dir = bot_userdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / "backtest.out.log"
    err_log = logs_dir / "backtest.err.log"

    cmd = [
        _which_freqtrade(),
        "backtesting",
        "--config",
        str(cfg_path),
        "--userdir",
        str(bot_userdir),
    ]
    if params.strategy:
        cmd += ["--strategy", params.strategy]
    if params.timerange:
        cmd += ["--timerange", params.timerange]
    if params.export != "none":
        cmd += ["--export", params.export]
        if params.export_filename:
            cmd += ["--export-filename", params.export_filename]

    # Env setup similar to start_bot
    env = os.environ.copy()
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    py_path_parts = [str(user_root), str(repo_root)] + ([env.get("PYTHONPATH")] if env.get("PYTHONPATH") else [])
    env["PYTHONPATH"] = os.pathsep.join(py_path_parts)
    _log_command(out_log, cmd, {"PYTHONPATH": env["PYTHONPATH"]})

    with out_log.open("ab") as out, err_log.open("ab") as err:
        proc = subprocess.Popen(
            cmd,
            stdout=out,
            stderr=err,
            cwd=str(bot_userdir),
            shell=False,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0,
        )

    # Track as a BotProcess record tagged via status 'backtesting'
    rec = db.query(BotProcess).filter(BotProcess.bot_id == bot.id).first()
    if not rec:
        rec = BotProcess(bot_id=bot.id)
        db.add(rec)
    rec.pid = proc.pid
    rec.status = "backtesting"
    rec.config_path = str(cfg_path)
    rec.exit_code = None
    rec.last_error = None
    db.commit()
    db.refresh(rec)

    time.sleep(float(os.environ.get("FT_BOT_EARLY_EXIT_WAIT", "0.5")))
    if proc.poll() is not None:
        rec.exit_code = proc.returncode
        rec.status = "error" if proc.returncode else "stopped"
        try:
            with err_log.open("rb") as ef:
                data = ef.read()[-2048:]
            snippet = data.decode("utf-8", errors="ignore")
            rec.last_error = snippet.strip().splitlines()[-10:][-1] if snippet else "Exited immediately"
        except Exception:
            rec.last_error = "Exited immediately (log unreadable)"
        db.commit()
        db.refresh(rec)
    return rec


def _load_api_server_from_config(cfg_path: str) -> dict | None:
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("api_server")
    except Exception:
        return None


def _bot_freqtrade_api_base(bot: Bot) -> str | None:
    """Return base URL (http://host:port/api/v1) for the bot's Freqtrade API if enabled in config.
    Assumes listen_ip_address is reachable from this backend (ideally 127.0.0.1) and uses http.
    """
    if not bot.config_path:
        return None
    api = _load_api_server_from_config(bot.config_path) or {}
    if not api or not api.get("enabled"):
        return None
    host = api.get("listen_ip_address", "127.0.0.1")
    port = api.get("listen_port", 8080)
    return f"http://{host}:{port}/api/v1"


def proxy_freqtrade_api(bot: Bot, method: str, path: str, params: dict | None = None, body: dict | None = None) -> tuple[int, dict | str]:
    """Forward a request to the bot's Freqtrade REST API.

    Returns (status_code, json_or_text).
    """
    base = _bot_freqtrade_api_base(bot)
    if not base:
        return 409, {"error": "Bot API server not enabled in config"}
    url = base.rstrip("/") + "/" + path.lstrip("/")
    # Read credentials for Basic Auth if provided
    api = _load_api_server_from_config(bot.config_path) or {}
    auth = None
    try:
        user = api.get("username")
        pwd = api.get("password")
        if user and pwd:
            auth = (user, pwd)
    except Exception:
        auth = None
    try:
        import importlib
        requests = importlib.import_module("requests")
    except Exception:
        return 500, {"error": "Python package 'requests' is not installed. Please install backend requirements."}
    try:
        resp = requests.request(method.upper(), url, params=params, json=body, timeout=10, auth=auth)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text
    except Exception as e:
        return 502, {"error": str(e)}


def _import_strategy_timeframes(cfg_path: str) -> list[str]:
    """Best-effort import of strategy class to read timeframe and optional informative_timeframe.

    Returns a list of unique timeframes. Falls back to ["5m"] if not discoverable.
    """
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        strat = cfg.get("strategy")
        spath = cfg.get("strategy_path")
        if not strat or not spath:
            return ["5m"]
        strat_file = Path(spath) / f"{strat}.py"
        if not strat_file.exists():
            return ["5m"]
        import importlib.util
        spec = importlib.util.spec_from_file_location(strat, str(strat_file))
        if spec is None or spec.loader is None:
            return ["5m"]
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        cls = getattr(mod, strat, None)
        if cls is None:
            return ["5m"]
        tfs: list[str] = []
        if hasattr(cls, "timeframe") and isinstance(getattr(cls, "timeframe"), str):
            tfs.append(getattr(cls, "timeframe"))
        # Optional additional informative timeframe commonly used by strategies
        if hasattr(cls, "informative_timeframe") and isinstance(getattr(cls, "informative_timeframe"), str):
            tfs.append(getattr(cls, "informative_timeframe"))
        # Dedup and fallback
        uniq: list[str] = []
        for tf in tfs:
            if tf and tf not in uniq:
                uniq.append(tf)
        return uniq or ["5m"]
    except Exception:
        return ["5m"]


def download_data(db: Session, user: User, bot: Bot, timerange: str) -> dict:
    """Download market data for backstaging using bot's config and strategy.

    - Always uses Binance as the data source.
    - Derives pairs from composed config (pairs or pair_whitelist).
    - Derives timeframes from the strategy class (timeframe and optional informative_timeframe).
    """
    user_root = Path(user.workspace_root).resolve()
    bot_userdir = Path(bot.userdir).resolve()
    # Compose config (to read pairs/strategy)
    try:
        active_strategy_spec = None
        if getattr(bot, "active_strategy", None):
            active_strategy_spec = json.loads(bot.active_strategy)
    except Exception:
        active_strategy_spec = None
    try:
        cfg_path = compose_bot_config(
            str(user_root),
            str(bot_userdir),
            mode=getattr(bot, "mode", None),
            active_strategy=active_strategy_spec,
        )
    except Exception:
        cfg_path = compose_runtime_config(str(bot_userdir))

    # Read pairs from config
    pairs: list[str] = []
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg.get("pairs"), list):
            pairs = cfg.get("pairs") or []
        elif isinstance(cfg.get("pair_whitelist"), list):
            pairs = cfg.get("pair_whitelist") or []
    except Exception:
        pairs = []
    if not pairs:
        raise HTTPException(status_code=422, detail="No pairs configured in bot config. Set pair_whitelist or pairs.")

    # Discover timeframes from strategy
    timeframes = _import_strategy_timeframes(str(cfg_path))

    logs_dir = bot_userdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / "download-data.out.log"
    err_log = logs_dir / "download-data.err.log"

    cmd = [
        _which_freqtrade(),
        "download-data",
        "--exchange",
        "binance",
        "--timerange",
        timerange,
        "--userdir",
        str(bot_userdir),
        "--config",
        str(cfg_path),
    ]
    for tf in timeframes:
        cmd += ["-t", tf]
    for p in pairs:
        cmd += ["-p", p]

    # Env setup similar to start_bot
    env = os.environ.copy()
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    py_path_parts = [str(user_root), str(repo_root)] + ([env.get("PYTHONPATH")] if env.get("PYTHONPATH") else [])
    env["PYTHONPATH"] = os.pathsep.join(py_path_parts)
    _log_command(out_log, cmd, {"PYTHONPATH": env["PYTHONPATH"]})

    with out_log.open("ab") as out, err_log.open("ab") as err:
        proc = subprocess.Popen(
            cmd,
            stdout=out,
            stderr=err,
            cwd=str(bot_userdir),
            shell=False,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0,
        )

    return {
        "status": "started",
        "pid": proc.pid,
        "pairs": pairs,
        "timeframes": timeframes,
        "timerange": timerange,
        "logs": {
            "stdout": str(out_log),
            "stderr": str(err_log),
        },
        "args": cmd,
    }


# Backward compatibility wrapper (deprecated)
def start_user_level_bot(db: Session, user: User, config_path: Optional[str] = None):  # pragma: no cover
    raise RuntimeError("User-level bot start deprecated. Use per-bot /users/{id}/bots/{bot_id}/start endpoint.")
