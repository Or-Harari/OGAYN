from __future__ import annotations

from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    workspace_root = Column(String, nullable=False)


class BotProcess(Base):
    __tablename__ = "bot_processes"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, index=True, nullable=False)
    pid = Column(Integer, nullable=True)
    status = Column(String, default="stopped")
    config_path = Column(String, nullable=True)
    exit_code = Column(Integer, nullable=True)
    last_error = Column(String, nullable=True)


class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    name = Column(String, nullable=False)
    userdir = Column(String, nullable=False)  # absolute path to this bot's user_data
    status = Column(String, default="stopped")
    pid = Column(Integer, nullable=True)
    config_path = Column(String, nullable=True)
    mode = Column(String, nullable=True)  # live | dryrun | backstage
    active_strategy = Column(String, nullable=True)  # JSON string storing active strategy spec

    # Dynamic property: derive currently selected strategy from bot.json config.
    # This is the authoritative strategy used when composing runtime config.
    @property
    def strategy(self) -> str | None:  # type: ignore[override]
        try:
            from pathlib import Path
            import json
            cfg_path = Path(self.userdir) / "configs" / "bot.json"
            if not cfg_path.exists():
                return None
            with cfg_path.open("r", encoding="utf-8") as f:
                data = json.load(f) or {}
            val = data.get("strategy")
            if isinstance(val, str) and val.strip():
                return val.strip()
            return None
        except Exception:
            return None


class ScannerConfig(Base):
    __tablename__ = "scanner_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String, index=True, nullable=False)  # scanner name (user-friendly, filesystem-safe)
    exchange = Column(String, default="binance", nullable=False)
    market_type = Column(String, default="futures", nullable=False)  # futures | spot
    enabled = Column(Boolean, default=True, nullable=False)
    interval_minutes = Column(Integer, default=5, nullable=False)
    
    # Configuration stored as JSON
    config_json = Column(Text, nullable=False, default="{}")
    # Contains: quoteAsset, maxPairs, minMarketScore, includeSymbols, excludeSymbols,
    # scoringWeights, scoringThresholds
    
    output_base_path = Column(String, nullable=True)  # Computed path: user_data/users/{userId}/scanners/{name}
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(Integer, index=True, nullable=False)
    exchange = Column(String, index=True, nullable=False, default="binance")
    symbol = Column(String, index=True, nullable=False)
    
    # Multi-scanner support
    scanner_id = Column(Integer, ForeignKey("scanner_configs.id"), index=True, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)

    price = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    atr = Column(Float, nullable=True)
    spread = Column(Float, nullable=True)

    funding = Column(Float, nullable=True)

    liquidity_score = Column(Integer, nullable=False, default=0)
    spread_score = Column(Integer, nullable=False, default=0)
    atr_score = Column(Integer, nullable=False, default=0)

    funding_score = Column(Integer, nullable=False, default=0)
    tick_score = Column(Integer, nullable=False, default=0)

    market_quality = Column(Integer, index=True, nullable=False, default=0)

    reasons_json = Column(Text, nullable=False, default="{}")
    raw_data_json = Column(Text, nullable=False, default="{}")


class ScannerOutput(Base):
    """
    Current scanner output - represents the latest symbols that meet scanner criteria.
    This table is cleared and refreshed on each scanner run (fresh data).
    Used by frontend for viewing scanner results.
    """
    __tablename__ = "scanner_outputs"

    id = Column(Integer, primary_key=True, index=True)
    scanner_id = Column(Integer, ForeignKey("scanner_configs.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    
    # When this output was generated
    generated_at = Column(Integer, index=True, nullable=False)
    
    # Symbol information
    symbol = Column(String, index=True, nullable=False)
    exchange = Column(String, nullable=False, default="binance")
    rank = Column(Integer, nullable=False)  # Position in sorted list (1 = best)
    
    # Market data
    price = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    atr = Column(Float, nullable=False)
    spread = Column(Float, nullable=False)
    funding = Column(Float, nullable=True)
    
    # Scores
    total_score = Column(Integer, index=True, nullable=False)
    liquidity_score = Column(Integer, nullable=False, default=0)
    volatility_score = Column(Integer, nullable=False, default=0)
    spread_score = Column(Integer, nullable=False, default=0)
    funding_score = Column(Integer, nullable=False, default=0)
    tick_score = Column(Integer, nullable=False, default=0)
    
    # Additional metadata
    reasons_json = Column(Text, nullable=False, default="{}")  # Detailed scoring reasons
