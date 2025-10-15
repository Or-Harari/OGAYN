from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db
from ..db.models import User, Bot
from ..schemas import (
    BotCreate,
    BotRead,
    BotModeUpdate,
    BotStrategyUpdate,
)
from ..services.workspace_service import create_bot_workspace
from ..services.bot_service import start_bot, stop_bot, bot_status as bot_status_service, start_backtest, proxy_freqtrade_api, download_data, get_runtime_info
from ..services import analytics_runtime as rt
from ..schemas import BacktestStartRequest, RuntimeInfo

router = APIRouter()


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
def download_bot_data(user_id: int, bot_id: int, timerange: str, current=Depends(get_current_user), db: Session = Depends(get_db)):
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
    if not timerange or not isinstance(timerange, str):
        raise HTTPException(status_code=422, detail="timerange is required (string)")
    result = download_data(db, user, bot, timerange)
    return result


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
    bot.status = rec.status
    bot.pid = rec.pid
    bot.config_path = rec.config_path
    db.commit()
    db.refresh(bot)
    return {"status": bot.status, "pid": bot.pid, "config": bot.config_path}


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
    import json as _json
    bot.active_strategy = _json.dumps(req.active_strategy.dict(exclude_none=True))
    db.commit()
    db.refresh(bot)
    return bot
