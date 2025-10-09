from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
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
from ..services.bot_service import start_bot, stop_bot, bot_status as bot_status_service

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
    return {"status": bot.status}


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
