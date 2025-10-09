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

    # Ensure strategy flag if missing in config
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg_json = json.load(f)
        if not cfg_json.get("strategy"):
            cmd += ["--strategy", "MainStrategy"]
    except Exception:
        pass

    # Environment adjustments (PYTHONPATH for shared strategies in user workspace)
    env = os.environ.copy()
    py_path_parts = [str(user_root)] + ([env.get("PYTHONPATH")] if env.get("PYTHONPATH") else [])
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


# Backward compatibility wrapper (deprecated)
def start_user_level_bot(db: Session, user: User, config_path: Optional[str] = None):  # pragma: no cover
    raise RuntimeError("User-level bot start deprecated. Use per-bot /users/{id}/bots/{bot_id}/start endpoint.")
