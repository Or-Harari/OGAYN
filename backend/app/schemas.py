from __future__ import annotations

from typing import Any, Dict, Optional, Union, Literal
from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str
    # Either provide an explicit workspace_root (path) or a workspace_name for auto-creation
    workspace_root: Optional[str] = None
    workspace_name: Optional[str] = None


class UserRead(UserBase):
    id: int
    workspace_root: str

    class Config:
        from_attributes = True


class MetaUpdateRequest(BaseModel):
    meta: Dict[str, Any]


class ActiveStrategySpec(BaseModel):
    name: str | None = None  # registry key
    clazz: str | None = None  # fully qualified class path

    def is_empty(self) -> bool:
        return not (self.name or self.clazz)


class BotCreate(BaseModel):
    name: str
    mode: str | None = None  # 'live' | 'dryrun' | 'backstage'
    active_strategy: ActiveStrategySpec | None = None


class BotRead(BaseModel):
    id: int
    name: str
    userdir: str
    status: str
    pid: int | None = None
    config_path: str | None = None
    mode: str | None = None
    active_strategy: dict | None = None

    class Config:
        from_attributes = True


class UserConfigPatch(BaseModel):
    exchange: dict | None = None
    # Additional top-level future keys can be added here


class BotConfigPatch(BaseModel):
    pair_whitelist: list[str] | None = None
    stake_currency: str | None = None
    timeframe: str | None = None
    minimal_roi: dict | None = None
    stoploss: float | None = None
    dry_run: bool | None = None
    mode: str | None = None  # allow patching mode via bot config if desired
    meta: dict | None = None  # merged into meta at compose time


class BotModeUpdate(BaseModel):
    mode: str


class BotStrategyUpdate(BaseModel):
    active_strategy: ActiveStrategySpec


# ---- Structured config models ----
class ExchangeConfig(BaseModel):
    name: str
    key: str | None = None
    secret: str | None = None
    password: str | None = None
    uid: str | None = None
    sandbox: bool | None = None
    ccxt_config: Dict[str, Any] | None = None
    ccxt_sync_config: Dict[str, Any] | None = None
    ccxt_async_config: Dict[str, Any] | None = None
    enable_ws: bool | None = None
    markets_refresh_interval: int | None = None
    skip_open_order_update: bool | None = None
    unknown_fee_rate: float | None = None
    log_responses: bool | None = None
    only_from_ccxt: bool | None = None
    pair_blacklist: list[str] | None = None


class PricingDepthConfig(BaseModel):
    enabled: bool | None = None
    bids_to_ask_delta: float | None = None


class PricingConfig(BaseModel):
    price_side: Literal['ask', 'bid', 'same', 'other'] = 'same'
    price_last_balance: float = 0.0
    use_order_book: bool = False
    order_book_top: int = 1
    check_depth_of_market: PricingDepthConfig | None = None


class BotTradingControls(BaseModel):
    stake_currency: str
    stake_amount: Union[float, str]
    max_open_trades: int
    tradable_balance_ratio: float | None = None
    available_capital: float | None = None
    amend_last_stake_amount: bool | None = None
    last_stake_amount_min_ratio: float | None = None
    amount_reserve_percent: float | None = None
    fiat_display_currency: str | None = None
    dry_run_wallet: Union[float, Dict[str, float], None] = None
    fee: float | None = None
    futures_funding_rate: float | None = None
    trading_mode: Literal['spot', 'futures'] = 'spot'
    margin_mode: str | None = None
    liquidation_buffer: float | None = None
    cancel_open_orders_on_exit: bool | None = None
    custom_price_max_distance_ratio: float | None = None


class BotPricingUpdate(BaseModel):
    entry_pricing: PricingConfig
    exit_pricing: PricingConfig


class BotTradingModeUpdate(BaseModel):
    trading_mode: Literal['spot', 'futures']
