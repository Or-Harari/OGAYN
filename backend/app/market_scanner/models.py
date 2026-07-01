from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class MarketContext:
    symbol: str
    exchange: str
    timestamp: int
    price: float
    quote_volume: float
    bid_price: float
    ask_price: float
    bid_qty: float
    ask_qty: float
    spread_pct: float
    atr_pct: float
    funding_rate: float
    tick_size: float
    step_size: float
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JudgeResult:
    name: str
    score: int
    max_score: int
    reason: str


@dataclass(slots=True)
class MarketScore:
    symbol: str
    exchange: str
    timestamp: int
    total_score: int
    price: float
    volume: float
    atr: float
    spread: float
    funding: float
    judge_results: List[JudgeResult]
    reasons: Dict[str, Any]
    raw_data: Dict[str, Any]
