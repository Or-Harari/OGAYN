"""
Pydantic schemas for Market Scanner configurations
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ScoringWeights(BaseModel):
    """Scoring weights for market quality evaluation."""
    liquidity: int = Field(default=30, ge=0, le=100, description="Weight for liquidity score")
    volatility: int = Field(default=25, ge=0, le=100, description="Weight for volatility score (ATR)")
    spread: int = Field(default=25, ge=0, le=100, description="Weight for spread score")
    funding: int = Field(default=10, ge=0, le=100, description="Weight for funding rate score")
    tradeCount: int = Field(default=10, ge=0, le=100, description="Weight for trade/tick score")
    recentActivity: int = Field(default=0, ge=0, le=100, description="Weight for recent activity score")

    @field_validator('liquidity', 'volatility', 'spread', 'funding', 'tradeCount', 'recentActivity')
    @classmethod
    def validate_weight(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError("Weight must be between 0 and 100")
        return v


class RecentActivityConfig(BaseModel):
    """Recent activity scoring behavior."""
    enabled: bool = Field(default=True, description="Enable recent activity judge")
    primaryWindow: str = Field(default="1h", description="Primary recent activity window")
    secondaryWindow: str = Field(default="4h", description="Secondary recent activity window")
    use1d: bool = Field(default=True, description="Include 1d window in scoring")
    staleAfterSeconds: int = Field(default=180, ge=1, description="Stale timeout for recent activity")

    @field_validator('primaryWindow', 'secondaryWindow')
    @classmethod
    def validate_window(cls, v: str) -> str:
        if v not in {'1h', '4h', '1d'}:
            raise ValueError("Window must be one of: 1h, 4h, 1d")
        return v


class RecentActivityThresholds(BaseModel):
    """Thresholds used by recent activity judge."""
    minQuoteVolume1h: float = Field(default=1_000_000, ge=0)
    excellentQuoteVolume1h: float = Field(default=25_000_000, ge=0)
    minQuoteVolume4h: float = Field(default=5_000_000, ge=0)
    excellentQuoteVolume4h: float = Field(default=100_000_000, ge=0)
    minQuoteVolume1d: float = Field(default=20_000_000, ge=0)
    excellentQuoteVolume1d: float = Field(default=500_000_000, ge=0)
    minTrades1h: int = Field(default=500, ge=0)
    excellentTrades1h: int = Field(default=10_000, ge=0)
    minTrades4h: int = Field(default=1_500, ge=0)
    excellentTrades4h: int = Field(default=30_000, ge=0)


class ScoringThresholds(BaseModel):
    """Thresholds for market quality evaluation."""
    minQuoteVolume24h: float = Field(default=30_000_000, ge=0, description="Minimum 24h quote volume")
    excellentQuoteVolume24h: float = Field(default=500_000_000, ge=0, description="Excellent 24h quote volume")
    minAtrPct: float = Field(default=0.5, ge=0, description="Minimum ATR percentage")
    idealAtrPctLow: float = Field(default=1.0, ge=0, description="Ideal ATR percentage (low bound)")
    idealAtrPctHigh: float = Field(default=3.0, ge=0, description="Ideal ATR percentage (high bound)")
    maxAtrPct: float = Field(default=6.0, ge=0, description="Maximum ATR percentage")
    maxSpreadPct: float = Field(default=0.1, ge=0, description="Maximum spread percentage")
    maxSpreadToAtrRatio: float = Field(
        default=0.10,
        ge=0,
        description="Maximum spread/ATR ratio where spread quality remains unpenalized"
    )
    normalFundingAbs: float = Field(
        default=0.0001,
        ge=0,
        description="Funding abs value considered normal (decimal units, e.g. 0.0001 = 0.01%)"
    )
    maxFundingAbs: float = Field(
        default=0.001,
        ge=0,
        description="Funding abs value considered extreme (decimal units, e.g. 0.001 = 0.1%)"
    )


class ScannerConfigBase(BaseModel):
    """Base scanner configuration."""
    name: str = Field(..., min_length=1, max_length=100, description="Scanner name (filesystem-safe)")
    exchange: str = Field(default="binance", description="Exchange name")
    market_type: str = Field(default="futures", description="Market type (futures/spot)")
    enabled: bool = Field(default=True, description="Whether scanner is enabled")
    interval_minutes: int = Field(default=5, ge=1, le=1440, description="Scan interval in minutes")
    
    # Market filtering
    quote_asset: str = Field(default="USDT", description="Quote asset filter")
    max_pairs: int = Field(default=30, ge=1, le=500, description="Maximum pairs to output")
    min_market_score: int = Field(default=70, ge=0, le=100, description="Minimum market quality score")
    include_symbols: list[str] = Field(default_factory=list, description="Symbols to always include")
    exclude_symbols: list[str] = Field(default_factory=list, description="Symbols to always exclude")
    
    # Scoring configuration
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    scoring_thresholds: ScoringThresholds = Field(default_factory=ScoringThresholds)
    recent_activity: RecentActivityConfig = Field(default_factory=RecentActivityConfig)
    recent_activity_thresholds: RecentActivityThresholds = Field(default_factory=RecentActivityThresholds)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure scanner name is filesystem-safe."""
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Scanner name must only contain letters, numbers, hyphens, and underscores")
        return v

    @field_validator('market_type')
    @classmethod
    def validate_market_type(cls, v: str) -> str:
        if v.lower() not in ['futures', 'spot']:
            raise ValueError("Market type must be 'futures' or 'spot'")
        return v.lower()


class ScannerConfigCreate(ScannerConfigBase):
    """Schema for creating a new scanner configuration."""
    pass


class ScannerConfigUpdate(BaseModel):
    """Schema for updating scanner configuration (all fields optional)."""
    name: str | None = Field(None, min_length=1, max_length=100)
    exchange: str | None = None
    market_type: str | None = None
    enabled: bool | None = None
    interval_minutes: int | None = Field(None, ge=1, le=1440)
    quote_asset: str | None = None
    max_pairs: int | None = Field(None, ge=1, le=500)
    min_market_score: int | None = Field(None, ge=0, le=100)
    include_symbols: list[str] | None = None
    exclude_symbols: list[str] | None = None
    scoring_weights: ScoringWeights | None = None
    scoring_thresholds: ScoringThresholds | None = None
    recent_activity: RecentActivityConfig | None = None
    recent_activity_thresholds: RecentActivityThresholds | None = None


class ScannerConfigResponse(ScannerConfigBase):
    """Schema for scanner configuration response."""
    id: int
    user_id: int
    output_base_path: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScannerConfigInternal(BaseModel):
    """Internal scanner configuration with all computed fields."""
    id: int
    user_id: int
    name: str
    exchange: str
    market_type: str
    enabled: bool
    interval_minutes: int
    quote_asset: str
    max_pairs: int
    min_market_score: int
    include_symbols: list[str]
    exclude_symbols: list[str]
    scoring_weights: ScoringWeights
    scoring_thresholds: ScoringThresholds
    recent_activity: RecentActivityConfig
    recent_activity_thresholds: RecentActivityThresholds
    output_base_path: str
    last_run_at: int | None = None  # Timestamp of last run

    @staticmethod
    def from_db_model(db_config: Any) -> ScannerConfigInternal:
        """Convert database model to internal config."""
        import json
        
        config_json = json.loads(db_config.config_json) if isinstance(db_config.config_json, str) else db_config.config_json
        
        return ScannerConfigInternal(
            id=db_config.id,
            user_id=db_config.user_id,
            name=db_config.name,
            exchange=db_config.exchange,
            market_type=db_config.market_type,
            enabled=db_config.enabled,
            interval_minutes=db_config.interval_minutes,
            quote_asset=config_json.get('quoteAsset', 'USDT'),
            max_pairs=config_json.get('maxPairs', 30),
            min_market_score=config_json.get('minMarketScore', 70),
            include_symbols=config_json.get('includeSymbols', []),
            exclude_symbols=config_json.get('excludeSymbols', []),
            scoring_weights=ScoringWeights(**config_json.get('scoringWeights', {})),
            scoring_thresholds=ScoringThresholds(**config_json.get('scoringThresholds', {})),
            recent_activity=RecentActivityConfig(**config_json.get('recentActivity', {})),
            recent_activity_thresholds=RecentActivityThresholds(**config_json.get('recentActivityThresholds', {})),
            output_base_path=db_config.output_base_path or f"user_data/users/{db_config.user_id}/scanners/{db_config.name}",
            last_run_at=getattr(db_config, "last_run_at", None)
        )


class ScannerResultSummary(BaseModel):
    """Summary of scanner run results."""
    scanner_id: int
    scanner_name: str
    timestamp: int
    symbols_scanned: int
    symbols_qualified: int
    output_path: str
    pairlist_files: list[str]
