from __future__ import annotations

from typing import Any


class IndicatorService:
    @staticmethod
    def compute_atr_percent(klines: list[list[Any]], period: int = 14) -> float:
        if not klines or len(klines) < period + 1:
            return 0.0

        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []

        for row in klines:
            try:
                highs.append(float(row[2]))
                lows.append(float(row[3]))
                closes.append(float(row[4]))
            except Exception:
                return 0.0

        true_ranges: list[float] = []
        for i in range(1, len(closes)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(max(tr, 0.0))

        if len(true_ranges) < period:
            return 0.0

        atr = sum(true_ranges[-period:]) / period
        last_close = closes[-1]
        if last_close <= 0:
            return 0.0
        return (atr / last_close) * 100.0
