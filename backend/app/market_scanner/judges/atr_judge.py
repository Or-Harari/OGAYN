from __future__ import annotations

from ..models import JudgeResult, MarketContext
from .base import IMarketJudge


class ATRJudge(IMarketJudge):
    def __init__(
        self, 
        max_score: int = 20,
        min_atr: float = 0.5,
        ideal_low: float = 1.0,
        ideal_high: float = 3.0,
        max_atr: float = 6.0
    ):
        self.max_score = max_score
        self.min_atr = min_atr
        self.ideal_low = ideal_low
        self.ideal_high = ideal_high
        self.max_atr = max_atr

    def evaluate(self, context: MarketContext) -> JudgeResult:
        atr_pct = max(context.atr_pct, 0.0)

        # Score based on configurable ideal range
        if self.ideal_low <= atr_pct <= self.ideal_high:
            score = self.max_score
        elif self.min_atr <= atr_pct < self.ideal_low:
            # Linear scale from min_atr to ideal_low
            ratio = (atr_pct - self.min_atr) / (self.ideal_low - self.min_atr) if self.ideal_low > self.min_atr else 0
            score = int(self.max_score * 0.7 * ratio)
        elif self.ideal_high < atr_pct <= self.max_atr:
            # Linear scale from ideal_high to max_atr
            ratio = 1.0 - ((atr_pct - self.ideal_high) / (self.max_atr - self.ideal_high)) if self.max_atr > self.ideal_high else 0
            score = int(self.max_score * 0.7 * ratio)
        else:
            score = 0

        reason = f"ATR%={atr_pct:.4f} (ideal: {self.ideal_low}-{self.ideal_high}%)"
        return JudgeResult(name="atr", score=score, max_score=self.max_score, reason=reason)
