from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db
from ..services.config_service import (
    load_meta_config,
    save_meta_config,
    get_user_account_config,
    update_user_account_config,
    reset_user_account_config,
    get_bot_config,
    update_bot_config,
    reset_bot_config,
    validate_user_and_bot,
)
from ..db.models import Bot
from ..schemas import UserConfigPatch, BotConfigPatch

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/meta")
def get_meta(current=Depends(get_current_user), db: Session = Depends(get_db)):
    return load_meta_config(current.workspace_root)

@router.put("/meta")
def put_meta(req: dict, current=Depends(get_current_user), db: Session = Depends(get_db)):
    meta = req.get("meta", {})
    return save_meta_config(meta, current.workspace_root)


# ---- User account config ----
@router.get("/user")
def get_user_config(current=Depends(get_current_user)):
    return get_user_account_config(current.workspace_root)


@router.patch("/user")
def patch_user_config(patch: UserConfigPatch, current=Depends(get_current_user)):
    return update_user_account_config(current.workspace_root, patch.model_dump(exclude_unset=True))


@router.post("/user/reset")
def reset_user_config(current=Depends(get_current_user)):
    return reset_user_account_config(current.workspace_root)


# ---- Bot config CRUD ----
def _get_bot(db: Session, current, bot_id: int) -> Bot:
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == current.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.get("/bot/{bot_id}")
def get_bot_cfg(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot(db, current, bot_id)
    return get_bot_config(bot.userdir)


@router.patch("/bot/{bot_id}")
def patch_bot_cfg(bot_id: int, patch: BotConfigPatch, current=Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot(db, current, bot_id)
    return update_bot_config(bot.userdir, patch.model_dump(exclude_unset=True))


@router.post("/bot/{bot_id}/reset")
def reset_bot_cfg(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot(db, current, bot_id)
    return reset_bot_config(bot.userdir)


@router.get("/validate/{bot_id}")
def validate_configs(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot(db, current, bot_id)
    return validate_user_and_bot(current.workspace_root, bot.userdir)
