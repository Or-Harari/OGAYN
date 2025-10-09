from __future__ import annotations
from pandas import DataFrame

class DcaSubStrategy:
    """Simple DCA scaling logic with configurable thresholds and budget."""
    def __init__(self, total_budget: float = 2000.0, mode: str = "martingale", thresholds=None, max_adds: int = 3):
        self.total_budget = total_budget
        self.mode = mode
        self.thresholds = thresholds or [3.0, 6.0, 10.0]
        self.max_adds = max_adds

    def _weights(self):
        raw = [1, 1, 1, 1] if self.mode == "equal" else [1, 2, 4, 8]
        s = sum(raw)
        return [x / s for x in raw]

    def custom_stake_amount(self, proposed_stake: float) -> float:
        first = self._weights()[0] * self.total_budget
        return float(min(first, proposed_stake or first))

    def adjust_trade_position(self, trade, current_rate: float) -> float:
        ud = dict(getattr(trade, "user_data", {}) or {})
        adds_used = ud.get("adds_used", 0)
        if adds_used >= self.max_adds:
            return 0.0
        waep = trade.open_rate
        dd_pct = (waep - current_rate) / waep * 100.0
        if adds_used < len(self.thresholds) and dd_pct < self.thresholds[adds_used]:
            return 0.0
        weights = self._weights()
        tranche_idx = adds_used + 1
        if tranche_idx >= len(weights):
            return 0.0
        committed = ud.get("budget_used", weights[0] * self.total_budget)
        remaining = max(0.0, self.total_budget - committed)
        add_size = min(weights[tranche_idx] * self.total_budget, remaining)
        if add_size <= 0.0:
            return 0.0
        ud["adds_used"] = adds_used + 1
        ud["budget_used"] = committed + add_size
        trade.user_data = ud
        return float(add_size)
