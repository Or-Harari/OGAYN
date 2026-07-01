from __future__ import annotations

from ..models import JudgeResult, MarketContext
from .base import IMarketJudge


class LiquidityJudge(IMarketJudge):
    def __init__(
        self, 
        max_score: int = 30,
        min_volume: float = 30_000_000.0,
        excellent_volume: float = 500_000_000.0
    ):
        self.max_score = max_score
        self.min_volume = min_volume
        self.excellent_volume = excellent_volume

    def evaluate(self, context: MarketContext) -> JudgeResult:
        quote_volume = max(context.quote_volume, 0.0)
        book_depth_quote = max((context.bid_qty * context.bid_price) + (context.ask_qty * context.ask_price), 0.0)

        # Scale volume score based on configurable thresholds
        volume_ratio = min(1.0, quote_volume / self.excellent_volume)
        volume_score = int(volume_ratio * 20)
        
        depth_score = min(10, int((book_depth_quote / 2_000_000.0) * 10))

        score = min(self.max_score, max(0, volume_score + depth_score))
        reason = (
            f"Quote volume={quote_volume:.2f}, depth={book_depth_quote:.2f}, "
            f"volume_score={volume_score}/20, depth_score={depth_score}/10"
        )
        return JudgeResult(name="liquidity", score=score, max_score=self.max_score, reason=reason)
