from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Request
import os
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db
from ..db.models import User, Bot
from ..schemas import (
    BotCreate,
    BotRead,
    BotModeUpdate,
    BotStrategyUpdate,
    BotConfigPatch,
)
from ..services.workspace_service import create_bot_workspace
from ..services.bot_service import (
    start_bot,
    stop_bot,
    bot_status as bot_status_service,
    start_backtest,
    proxy_freqtrade_api,
    download_data,
    get_runtime_info,
    get_trades_history,
    get_backtest_status,
    tail_backtest_logs,
    tail_runtime_logs,
    get_backtest_results,
    list_backtest_results,
    load_backtest_result,
)
from ..services import analytics_runtime as rt
from ..schemas import BacktestStartRequest, RuntimeInfo

import logging
router = APIRouter()
logger = logging.getLogger(__name__)


def _get_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/{user_id}/bots", response_model=list[BotRead])
def list_bots(user_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return db.query(Bot).filter(Bot.user_id == user.id).all()


@router.post("/{user_id}/bots", response_model=BotRead)
def create_bot(user_id: int, req: BotCreate, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    # Create per-bot user_data (user.workspace_root now points to user root, not user_data)
    userdir = create_bot_workspace(user.workspace_root, req.name)
    bot = Bot(user_id=user.id, name=req.name, userdir=userdir, status="stopped")
    # Persist mode & active strategy spec if provided
    if req.mode:
        bot.mode = req.mode.lower()
    if req.active_strategy and not req.active_strategy.is_empty():
        import json as _json
        bot.active_strategy = _json.dumps(req.active_strategy.dict(exclude_none=True))
    db.add(bot)
    db.commit()
    db.refresh(bot)
    # Persist initial leverage into bot config if provided
    try:
        if req.leverage is not None:
            from pathlib import Path as _Path
            import json as _json
            cfg_dir = _Path(bot.userdir) / "configs"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            bot_cfg_path = cfg_dir / "bot.json"
            current_cfg = {}
            if bot_cfg_path.exists():
                try:
                    with bot_cfg_path.open("r", encoding="utf-8") as f:
                        current_cfg = _json.load(f) or {}
                except Exception:
                    current_cfg = {}
            current_cfg["leverage"] = int(req.leverage)
            with bot_cfg_path.open("w", encoding="utf-8") as f:
                _json.dump(current_cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        # Non-fatal: leverage can be patched later via /config
        pass
    return bot


@router.delete("/{user_id}/bots/{bot_id}")
def delete_bot(user_id: int, bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    # Do not delete files yet; only the DB record (safe default)
    db.delete(bot)
    db.commit()
    return {"status": "deleted"}


@router.patch("/{user_id}/bots/{bot_id}/config")
def update_bot_config(user_id: int, bot_id: int, req: BotConfigPatch, current=Depends(get_current_user), db: Session = Depends(get_db)):
    """Patch non-strategy bot configuration into bot.json.

    Allowed keys: pair_whitelist, stake_currency, stake_amount, dry_run, meta
    Strategy-owned keys (roi, timeframe, stoploss, etc.) are ignored here and must be set in the strategy.
    """
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    from pathlib import Path as _Path
    import json as _json
    bot_userdir = _Path(bot.userdir)
    cfg_dir = bot_userdir / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    bot_cfg_path = cfg_dir / "bot.json"
    try:
        current_cfg = {}
        if bot_cfg_path.exists():
            with bot_cfg_path.open("r", encoding="utf-8") as f:
                current_cfg = _json.load(f) or {}
    except Exception:
        current_cfg = {}

    # Apply only allowed fields
    payload = req.dict(exclude_none=True)
    allowed = {"pair_whitelist", "stake_currency", "stake_amount", "dry_run", "dry_run_wallet", "meta", "trading_mode", "margin_mode", "liquidation_buffer", "leverage", "strategy", "timeframe"}
    for k in list(payload.keys()):
        if k not in allowed:
            payload.pop(k, None)
    # Normalize pair_whitelist from input
    if "pair_whitelist" in payload and payload["pair_whitelist"] is not None:
        if not isinstance(payload["pair_whitelist"], list):
            raise HTTPException(status_code=422, detail="pair_whitelist must be a list of symbols")
        payload["pair_whitelist"] = [str(x).upper() for x in payload["pair_whitelist"] if str(x).strip()]

    # Merge and write
    new_cfg = {**current_cfg, **payload}
    # Atomic write via save_bot_config to avoid JSON corruption under concurrent calls
    try:
        from ..services.config_service import save_bot_config as _atomic_save
        _atomic_save(new_cfg, str(bot_userdir))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write bot config: {e}")

    return new_cfg


@router.post("/{user_id}/bots/{bot_id}/start")
def start_bot_route(user_id: int, bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    rec = start_bot(db, user, bot)
    bot.status = rec.status
    bot.pid = rec.pid
    bot.config_path = rec.config_path
    db.commit()
    db.refresh(bot)
    try:
        rt.start_collector(user, bot)
    except Exception:
        pass
    return {"status": bot.status, "pid": bot.pid, "config": bot.config_path}


@router.post("/{user_id}/bots/{bot_id}/stop")
def stop_bot_route(user_id: int, bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    rec = stop_bot(db, bot)
    bot.status = rec.status
    bot.pid = None
    db.commit()
    db.refresh(bot)
    try:
        import asyncio
        asyncio.create_task(rt.stop_collector(bot.id))
    except Exception:
        pass
    return {"status": bot.status}


## start-api-only endpoint removed per revised design


@router.get("/{user_id}/bots/{bot_id}/balance")
def get_bot_balance(user_id: int, bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    """Convenience endpoint that proxies to the bot's Freqtrade /balance REST endpoint.

    Requires that the bot's api_server.enabled is true in its composed config.
    """
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    status_code, payload = proxy_freqtrade_api(bot, "GET", "/balance")
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=payload)
    return payload


@router.post("/{user_id}/bots/{bot_id}/data/download")
def download_bot_data(user_id: int, bot_id: int, body: dict, current=Depends(get_current_user), db: Session = Depends(get_db)):
    """Trigger market data download for backstaging.

    The endpoint derives pairs and timeframes from the bot's composed config and strategy, and downloads from Binance.

    Params:
      - timerange: Freqtrade timerange syntax, e.g., "20240101-20241231" or "-365d".
    """
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    timerange = None
    pairs = None
    timeframes = None
    try:
        timerange = body.get("timerange") if isinstance(body, dict) else None
        pairs = body.get("pairs") if isinstance(body, dict) else None
        timeframes = body.get("timeframes") if isinstance(body, dict) else None
        sync = bool(body.get("sync")) if isinstance(body, dict) else False
    except Exception:
        timerange = None
        sync = False
    if not timerange or not isinstance(timerange, str):
        raise HTTPException(status_code=422, detail="timerange is required (string)")
    if pairs is not None and not isinstance(pairs, list):
        raise HTTPException(status_code=422, detail="pairs must be a list of strings when provided")
    if timeframes is not None and not isinstance(timeframes, list):
        raise HTTPException(status_code=422, detail="timeframes must be a list of strings when provided")
    result = download_data(db, user, bot, timerange, pairs_override=pairs, timeframes_override=timeframes, sync=sync)
    return result


@router.get("/{user_id}/bots/{bot_id}/backtest/results")
def backtest_results_route(user_id: int, bot_id: int, limit_trades: int = 200, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    res = get_backtest_results(bot, limit_trades=limit_trades)
    return res


@router.get("/{user_id}/bots/{bot_id}/backtest/list")
def backtest_list_route(user_id: int, bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    items = list_backtest_results(bot)
    return {"items": items}


@router.get("/{user_id}/bots/{bot_id}/backtest/result")
def backtest_result_route(user_id: int, bot_id: int, file: str, limit_trades: int = 200, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    res = load_backtest_result(bot, file=file, limit_trades=limit_trades)
    return res


@router.api_route("/{user_id}/bots/{bot_id}/proxy/freqtrade/{full_path:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH", "HEAD", "OPTIONS"])
async def proxy_freqtrade(user_id: int, bot_id: int, full_path: str, request: Request, current=Depends(get_current_user), db: Session = Depends(get_db)):
    """Generic proxy: forward to the bot's Freqtrade REST API at /api/v1/<full_path>.

    Auth is handled by our backend; Freqtrade API should be bound to localhost with strong creds.
    """
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    # Extract method, query and JSON body if present
    method = request.method
    params = dict(request.query_params)
    body = None
    raw_body = None
    try:
        # Try JSON first
        if request.headers.get("content-type", "").lower().startswith("application/json"):
            body = await request.json()
        else:
            raw_body = await request.body()
    except Exception:
        raw_body = None
    status_code, payload = proxy_freqtrade_api(
        bot,
        method,
        "/" + full_path,
        params=params or None,
        body=body,
        raw_body=raw_body,
        headers=dict(request.headers),
    )
    if status_code >= 400:
        raise HTTPException(status_code=status_code, detail=payload)
    return payload


@router.post("/{user_id}/bots/{bot_id}/backtest")
def start_backtest_route(user_id: int, bot_id: int, req: BacktestStartRequest, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    rec = start_backtest(db, user, bot, req)
    # Behavior toggle: allow legacy behavior that mutates bot fields during backtest
    # Controlled via env FT_BACKTEST_MUTATE_BOT (default 'false' to keep isolation by default)
    mutate = os.environ.get("FT_BACKTEST_MUTATE_BOT", "false").lower() == "true"
    if mutate:
        bot.status = rec.status
        bot.pid = rec.pid
        # Only mutate config_path if it points to the bot's own userdir (never the isolated bt-userdir)
        try:
            from pathlib import Path
            bot_ud = Path(bot.userdir).resolve()
            rec_cfg = Path(rec.config_path).resolve() if rec.config_path else None
            if rec_cfg and str(bot_ud) in str(rec_cfg):
                bot.config_path = rec.config_path
        except Exception:
            pass
        db.commit()
        db.refresh(bot)
        return {"status": bot.status, "pid": bot.pid, "config": bot.config_path}
    else:
        return {"status": rec.status, "pid": rec.pid, "config": rec.config_path}


@router.get("/{user_id}/bots/{bot_id}/backtest/status")
def backtest_status_route(user_id: int, bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    st = get_backtest_status(bot)
    return st


@router.get("/{user_id}/bots/{bot_id}/backtest/logs")
def backtest_logs_route(user_id: int, bot_id: int, tail: int = 1000, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    res = tail_backtest_logs(bot, tail=tail)
    return res


@router.get("/{user_id}/bots/{bot_id}/logs")
def bot_logs_route(user_id: int, bot_id: int, tail: int = 1000, current=Depends(get_current_user), db: Session = Depends(get_db)):
    """Tail the running bot container logs (dryrun/live)."""
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    res = tail_runtime_logs(bot, tail=tail)
    return res


@router.get("/{user_id}/bots/{bot_id}/status")
def bot_status_route(user_id: int, bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    st = bot_status_service(db, bot)
    return st


@router.get("/{user_id}/bots/{bot_id}/runtime", response_model=RuntimeInfo)
def bot_runtime_route(user_id: int, bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    info = get_runtime_info(db, user, bot)
    return info


@router.get("/{user_id}/bots/{bot_id}/trades-history")
def bot_trades_history_route(user_id: int, bot_id: int, mode: str | None = None, limit: int | None = None, current=Depends(get_current_user), db: Session = Depends(get_db)):
        """Return historical trades for a bot from its local SQLite DBs.

        Params:
            - mode: 'live' | 'dryrun' | 'all' (default 'all')
            - limit: optional max rows per DB (applied per selected DB)

        Notes:
            - Does not require the bot to be running.
            - Reads tradesv3.sqlite and/or tradesv3.dryrun.sqlite inside the bot's user_data.
        """
        user = _get_user(db, user_id)
        if current.id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
        rows = get_trades_history(user, bot, mode=mode, limit=limit)
        logger.info(f"Fetched {len(rows)} trade history rows for bot {bot.id} (mode={mode}, limit={limit})")
        return rows


@router.post("/{user_id}/bots/{bot_id}/dryrun/reset")
def bot_dryrun_reset_route(user_id: int, bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    """Reset (delete) the bot's dryrun trades database files.

    Removes tradesv3.dryrun.sqlite / tradesv4.dryrun.sqlite from the bot's userdir if present.
    Bot must be stopped before calling this to avoid file locks.
    """
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    # Ensure bot is not running to avoid file lock issues
    try:
        info = get_runtime_info(db, user, bot)
        if info and info.get("running"):
            raise HTTPException(status_code=409, detail="Stop the bot before resetting dryrun trades")
    except HTTPException:
        raise
    except Exception:
        pass
    from pathlib import Path as _Path
    bot_userdir = _Path(bot.userdir).resolve()
    candidates = [
        bot_userdir / "tradesv3.dryrun.sqlite",
        bot_userdir / "tradesv4.dryrun.sqlite",
    ]
    removed: list[str] = []
    for p in candidates:
        try:
            if p.exists():
                p.unlink()
                removed.append(p.name)
        except Exception as e:
            # If deletion fails, attempt to truncate file
            try:
                with p.open("w", encoding="utf-8") as f:
                    f.write("")
                removed.append(p.name)
            except Exception:
                logger.warning(f"Failed to remove/truncate {p}: {e}")
    return {"status": "ok", "removed": removed}


@router.patch("/{user_id}/bots/{bot_id}/mode", response_model=BotRead)
def update_bot_mode(user_id: int, bot_id: int, req: BotModeUpdate, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    bot.mode = req.mode.lower()
    db.commit()
    db.refresh(bot)
    return bot


@router.patch("/{user_id}/bots/{bot_id}/strategy", response_model=BotRead)
def update_bot_strategy(user_id: int, bot_id: int, req: BotStrategyUpdate, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    # New behavior: write 'strategy' directly into bot.json and clear active_strategy for single source of truth.
    from pathlib import Path as _Path
    import json as _json
    strategy_val: str | None = None
    if isinstance(req.strategy, str) and req.strategy.strip():
        strategy_val = req.strategy.strip()
    elif req.active_strategy:
        try:
            data = req.active_strategy.dict(exclude_none=True)
            strategy_val = str(data.get("name") or data.get("clazz") or "").strip()
        except Exception:
            strategy_val = None
    if not strategy_val:
        raise HTTPException(status_code=422, detail="strategy is required")
    cfg_dir = _Path(bot.userdir) / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    bot_cfg_path = cfg_dir / "bot.json"
    current_cfg = {}
    try:
        if bot_cfg_path.exists():
            with bot_cfg_path.open("r", encoding="utf-8") as f:
                current_cfg = _json.load(f) or {}
    except Exception:
        current_cfg = {}
    current_cfg["strategy"] = strategy_val
    try:
        from ..services.config_service import save_bot_config as _atomic_save
        _atomic_save(current_cfg, bot.userdir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write bot config: {e}")
    # Clear legacy DB field
    try:
        bot.active_strategy = None
        db.commit()
        db.refresh(bot)
    except Exception:
        pass
    return bot
