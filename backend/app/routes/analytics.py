from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db
from ..db.models import User, Bot
from ..services import analytics_service as svc

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
