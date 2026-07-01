"""Pydantic schemas for Freqtrade pairlist configuration."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class RemotePairListConfig(BaseModel):
    """RemotePairList configuration schema."""
    method: Literal["RemotePairList"] = "RemotePairList"
    mode: Literal["whitelist", "blacklist"] = "whitelist"
    processing_mode: Literal["filter", "append"] = "filter"
    pairlist_url: str = Field(..., description="URL or file:// path to pairlist")
    number_assets: int | None = Field(None, description="Max pairs (whitelist mode only)")
    refresh_period: int = Field(1800, description="Refresh interval in seconds")
    keep_pairlist_on_failure: bool = True
    read_timeout: int = 60
    bearer_token: str | None = Field(None, description="Optional bearer token for authentication")
    save_to_file: str | None = None


class StaticPairListConfig(BaseModel):
    """StaticPairList configuration schema."""
    method: Literal["StaticPairList"] = "StaticPairList"
    allow_inactive: bool = False


class VolumePairListConfig(BaseModel):
    """VolumePairList configuration schema."""
    method: Literal["VolumePairList"] = "VolumePairList"
    number_assets: int = Field(20, description="Number of top volume pairs")
    sort_key: Literal["quoteVolume"] = "quoteVolume"
    min_value: float = Field(0, description="Minimum volume threshold")
    max_value: float | None = Field(None, description="Maximum volume threshold")
    refresh_period: int = Field(1800, description="Refresh interval in seconds")
    # Advanced mode options
    lookback_days: int | None = Field(None, description="Lookback period in days (uses 1d candles)")
    lookback_timeframe: str | None = Field(None, description="Candle timeframe for lookback (e.g., '1h')")
    lookback_period: int | None = Field(None, description="Number of candles to look back")


class PercentChangePairListConfig(BaseModel):
    """PercentChangePairList configuration schema."""
    method: Literal["PercentChangePairList"] = "PercentChangePairList"
    number_assets: int = Field(15, description="Number of pairs to select")
    sort_key: Literal["percentage"] = "percentage"
    sort_direction: Literal["asc", "desc"] = Field("desc", description="Sort order")
    min_value: float | None = Field(None, description="Minimum percent change threshold")
    max_value: float | None = Field(None, description="Maximum percent change threshold")
    refresh_period: int = Field(1800, description="Refresh interval in seconds")
    # Advanced lookback options
    lookback_days: int | None = Field(None, description="Lookback period in days")
    lookback_timeframe: str | None = Field(None, description="Candle timeframe for lookback")
    lookback_period: int | None = Field(None, description="Number of candles to look back")


class MarketCapPairListConfig(BaseModel):
    """MarketCapPairList configuration schema."""
    method: Literal["MarketCapPairList"] = "MarketCapPairList"
    number_assets: int = Field(20, description="Max pairs in whitelist")
    max_rank: int = Field(50, description="Maximum market cap rank (recommended <= 250)")
    refresh_period: int = Field(86400, description="Refresh interval in seconds (default 1 day)")
    mode: Literal["whitelist", "blacklist"] = "whitelist"
    categories: list[str] = Field(default_factory=list, description="CoinGecko categories (e.g., ['layer-1'])")


# Union of all supported pairlist configs
PairlistHandlerConfig = (
    RemotePairListConfig |
    StaticPairListConfig |
    VolumePairListConfig |
    PercentChangePairListConfig |
    MarketCapPairListConfig
)


class FreqtradePairlistConfig(BaseModel):
    """Complete Freqtrade pairlist configuration."""
    enabled: bool = Field(True, description="Enable/disable pairlist handlers")
    pair_whitelist: list[str] = Field(
        default_factory=list,
        description="Static pair whitelist (used by StaticPairList)"
    )
    pair_blacklist: list[str] = Field(
        default_factory=list,
        description="Pairs to exclude from all pairlists"
    )
    pairlists: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Chain of pairlist handlers"
    )


class PairlistConfigResponse(BaseModel):
    """Response schema for pairlist configuration."""
    user_id: int
    bot_id: str | None
    config: FreqtradePairlistConfig
    updated_at: str | None


class PairlistConfigUpdate(BaseModel):
    """Schema for updating pairlist configuration."""
    bot_id: str | None = Field(None, description="Bot ID (None for user-level config)")
    config: FreqtradePairlistConfig
