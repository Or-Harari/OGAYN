from __future__ import annotations

from ..models import JudgeResult, MarketContext
from .base import IMarketJudge


class FundingJudge(IMarketJudge):
    def __init__(
        self,
        max_score: int = 10,
        normal_funding_abs: float = 0.0001,
        max_funding_abs: float = 0.001,
    ):
        self.max_score = max_score
        self.normal_funding_abs = normal_funding_abs
        self.max_funding_abs = max_funding_abs

    def evaluate(self, context: MarketContext) -> JudgeResult:
        funding_abs = abs(context.funding_rate)

        if funding_abs <= self.normal_funding_abs:
            score = self.max_score
        elif funding_abs >= self.max_funding_abs:
            score = 0
        else:
            span = self.max_funding_abs - self.normal_funding_abs
            if span <= 0:
                score = 0
            else:
                progress = (funding_abs - self.normal_funding_abs) / span
                score = int(self.max_score * (1.0 - progress))

        reason = (
            f"Funding={context.funding_rate:.6f} "
            f"(abs={funding_abs:.6f}, normal<={self.normal_funding_abs:.6f}, max={self.max_funding_abs:.6f})"
        )
        return JudgeResult(name="funding", score=score, max_score=self.max_score, reason=reason)
