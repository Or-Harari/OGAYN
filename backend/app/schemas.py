from __future__ import annotations

from typing import Any, Dict, Optional
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
