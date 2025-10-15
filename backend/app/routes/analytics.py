from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db
from ..db.models import User, Bot
from ..services import analytics_service as svc
from ..services import analytics_runtime as rt

router = APIRouter()


def _get_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/{user_id}/bots/{bot_id}/analytics/snapshot")
def analytics_snapshot(user_id: int, bot_id: int, limit: int = 200, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    # Prefer runtime cache if collector running
    cached = None
    try:
        cached = rt.snapshot_from_runtime(user, bot)
        import asyncio
        if asyncio.iscoroutine(cached):
            cached = asyncio.get_event_loop().run_until_complete(cached)  # type: ignore
    except Exception:
        cached = None
    if cached:
        return cached
    return svc.snapshot(db, user, bot, limit=limit)


@router.get("/{user_id}/bots/{bot_id}/analytics/candles")
def analytics_candles(user_id: int, bot_id: int, pair: str, timeframe: str, limit: int = 200, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return svc.fetch_candles(bot, pair=pair, timeframe=timeframe, limit=limit)


@router.websocket("/{user_id}/bots/{bot_id}/analytics/ws")
async def analytics_ws(websocket: WebSocket, user_id: int, bot_id: int, db: Session = Depends(get_db)):
    # Note: WebSocket auth can be added via token query param or cookie; skipped for internal tooling.
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        await websocket.close(code=4404)
        return
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        await websocket.close(code=4404)
        return
    # Start collector if not running
    try:
        rt.start_collector(user, bot)
    except Exception:
        pass
    await rt.register_ws(bot.id, websocket)
    try:
        # Keep connection open; we only push server-to-client updates
        while True:
            # Drain any pings from client to keepalive
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await rt.unregister_ws(bot.id, websocket)
