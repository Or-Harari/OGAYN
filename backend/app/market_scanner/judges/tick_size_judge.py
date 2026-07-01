from __future__ import annotations

from ..models import JudgeResult, MarketContext
from .base import IMarketJudge


class TickSizeJudge(IMarketJudge):
    def __init__(self, max_score: int = 10):
        self.max_score = max_score

    def evaluate(self, context: MarketContext) -> JudgeResult:
        price = max(context.price, 0.0)
        tick = max(context.tick_size, 0.0)
        ratio = (tick / price) if price > 0 else 1.0

        if ratio <= 0.00001:
            score = self.max_score
        elif ratio <= 0.00003:
            score = 8
        elif ratio <= 0.0001:
            score = 5
        elif ratio <= 0.0003:
            score = 2
        else:
            score = 0

        reason = f"Tick={tick:.12f}, tick/price={ratio:.8f}"
        return JudgeResult(name="tick_size", score=score, max_score=self.max_score, reason=reason)
