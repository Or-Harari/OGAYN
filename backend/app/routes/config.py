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
from ..schemas import (
    UserConfigPatch,
    BotConfigPatch,
    ExchangeConfig,
    BotTradingControls,
    BotPricingUpdate,
    BotTradingModeUpdate,
)
from ..services.config_validation import BOT_PLACEHOLDER
from ..services.config_service import SYSTEM_DEFAULTS, save_bot_config

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


# ---- Focused: User Exchange config ----
@router.get("/user/exchange")
def get_user_exchange(current=Depends(get_current_user)) -> dict:
    acc = get_user_account_config(current.workspace_root)
    return acc.get("exchange", {}) or {}


@router.put("/user/exchange")
def put_user_exchange(cfg: ExchangeConfig, current=Depends(get_current_user)) -> dict:
    payload = {"exchange": cfg.model_dump(exclude_none=True)}
    return update_user_account_config(current.workspace_root, payload)


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


# ---- Focused: Bot trading controls ----
_TRADING_CONTROL_KEYS = [
    "stake_currency",
    "stake_amount",
    "max_open_trades",
    "tradable_balance_ratio",
    "available_capital",
    "amend_last_stake_amount",
    "last_stake_amount_min_ratio",
    "amount_reserve_percent",
    "fiat_display_currency",
    "dry_run_wallet",
    "fee",
    "futures_funding_rate",
    "trading_mode",
    "margin_mode",
    "liquidation_buffer",
    "cancel_open_orders_on_exit",
    "custom_price_max_distance_ratio",
]


def _extract_trading_controls(cfg: dict) -> dict:
    base = {k: cfg.get(k) for k in _TRADING_CONTROL_KEYS if k in cfg}
    # Ensure required keys have sensible defaults
    base.setdefault("stake_currency", cfg.get("stake_currency") or BOT_PLACEHOLDER.get("stake_currency"))
    base.setdefault("stake_amount", cfg.get("stake_amount") or BOT_PLACEHOLDER.get("stake_amount"))
    base.setdefault("max_open_trades", cfg.get("max_open_trades") or BOT_PLACEHOLDER.get("max_open_trades"))
    base.setdefault("trading_mode", cfg.get("trading_mode") or BOT_PLACEHOLDER.get("trading_mode") or "spot")
    return base


@router.get("/bot/{bot_id}/trading-controls")
def get_bot_trading_controls(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)) -> BotTradingControls:
    bot = _get_bot(db, current, bot_id)
    cfg = get_bot_config(bot.userdir) or {}
    data = _extract_trading_controls(cfg)
    return BotTradingControls(**data)


@router.put("/bot/{bot_id}/trading-controls")
def put_bot_trading_controls(
    bot_id: int,
    controls: BotTradingControls,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_bot(db, current, bot_id)
    patch = controls.model_dump(exclude_none=True)
    updated = update_bot_config(bot.userdir, patch)
    return _extract_trading_controls(updated)


# ---- Focused: Bot pricing ----
@router.get("/bot/{bot_id}/pricing")
def get_bot_pricing(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)) -> BotPricingUpdate:
    bot = _get_bot(db, current, bot_id)
    cfg = get_bot_config(bot.userdir) or {}
    entry = cfg.get("entry_pricing") or SYSTEM_DEFAULTS.get("entry_pricing")
    exitp = cfg.get("exit_pricing") or SYSTEM_DEFAULTS.get("exit_pricing")
    return BotPricingUpdate(entry_pricing=entry, exit_pricing=exitp)


@router.put("/bot/{bot_id}/pricing")
def put_bot_pricing(
    bot_id: int,
    pricing: BotPricingUpdate,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_bot(db, current, bot_id)
    patch = pricing.model_dump(exclude_none=True)
    updated = update_bot_config(bot.userdir, patch)
    return {
        "entry_pricing": updated.get("entry_pricing"),
        "exit_pricing": updated.get("exit_pricing"),
    }


# ---- Focused: Bot trading mode ----
@router.patch("/bot/{bot_id}/trading-mode")
def patch_bot_trading_mode(
    bot_id: int,
    update: BotTradingModeUpdate,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_bot(db, current, bot_id)
    mode = (update.trading_mode or "spot").lower()
    # Load, mutate explicitly to allow removal of futures-only keys when switching to spot
    cur = get_bot_config(bot.userdir) or {}
    cur["trading_mode"] = mode
    if mode == "spot":
        cur.pop("liquidation_buffer", None)
        cur.pop("margin_mode", None)
    # Persist full object to reflect removals
    saved = save_bot_config(cur, bot.userdir)
    return {"trading_mode": saved.get("trading_mode", mode)}
