from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import JudgeResult, MarketContext


class IMarketJudge(ABC):
    @abstractmethod
    def evaluate(self, context: MarketContext) -> JudgeResult:
        raise NotImplementedError
