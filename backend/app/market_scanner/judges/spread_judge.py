from __future__ import annotations

from ..models import JudgeResult, MarketContext
from .base import IMarketJudge


class SpreadJudge(IMarketJudge):
    def __init__(
        self,
        max_score: int = 20,
        max_spread: float = 0.1,
        max_spread_to_atr_ratio: float = 0.10,
    ):
        self.max_score = max_score
        self.max_spread = max_spread
        self.max_spread_to_atr_ratio = max_spread_to_atr_ratio

    def evaluate(self, context: MarketContext) -> JudgeResult:
        spread = max(context.spread_pct, 0.0)
        atr_pct = max(context.atr_pct, 0.0)
        ratio = (spread / atr_pct) if atr_pct > 0 else None

        # Score inversely proportional to spread, with configurable max
        if spread <= 0.01:
            score = self.max_score
        elif spread <= self.max_spread / 10:
            score = int(self.max_score * 0.8)
        elif spread <= self.max_spread / 5:
            score = int(self.max_score * 0.6)
        elif spread <= self.max_spread / 2:
            score = int(self.max_score * 0.4)
        elif spread <= self.max_spread:
            score = int(self.max_score * 0.2)
        else:
            score = 0

        # Penalize spread that is too large relative to ATR.
        if ratio is None:
            score = int(score * 0.2)
        elif self.max_spread_to_atr_ratio > 0 and ratio > self.max_spread_to_atr_ratio:
            penalty_factor = min(1.0, self.max_spread_to_atr_ratio / ratio)
            score = int(score * penalty_factor)

        ratio_text = "n/a" if ratio is None else f"{ratio:.4f}"
        reason = (
            f"Spread={spread:.4f}% (max: {self.max_spread}%), "
            f"spread/ATR={ratio_text} (max: {self.max_spread_to_atr_ratio})"
        )
        return JudgeResult(name="spread", score=score, max_score=self.max_score, reason=reason)
