from __future__ import annotations

from typing import Any

from ..models import JudgeResult, MarketContext
from .base import IMarketJudge


class RecentActivityJudge(IMarketJudge):
    def __init__(
        self,
        max_score: int = 0,
        enabled: bool = True,
        primary_window: str = "1h",
        secondary_window: str = "4h",
        use_1d: bool = True,
        stale_after_seconds: int = 180,
        min_quote_volume_1h: float = 1_000_000,
        excellent_quote_volume_1h: float = 25_000_000,
        min_quote_volume_4h: float = 5_000_000,
        excellent_quote_volume_4h: float = 100_000_000,
        min_quote_volume_1d: float = 20_000_000,
        excellent_quote_volume_1d: float = 500_000_000,
        min_trades_1h: int = 500,
        excellent_trades_1h: int = 10_000,
        min_trades_4h: int = 1_500,
        excellent_trades_4h: int = 30_000,
    ):
        self.max_score = max(0, int(max_score))
        self.enabled = bool(enabled)
        self.primary_window = primary_window if primary_window in {"1h", "4h", "1d"} else "1h"
        self.secondary_window = secondary_window if secondary_window in {"1h", "4h", "1d"} else "4h"
        self.use_1d = bool(use_1d)
        self.stale_after_seconds = max(1, int(stale_after_seconds))

        self.min_quote_volume_1h = float(min_quote_volume_1h)
        self.excellent_quote_volume_1h = float(excellent_quote_volume_1h)
        self.min_quote_volume_4h = float(min_quote_volume_4h)
        self.excellent_quote_volume_4h = float(excellent_quote_volume_4h)
        self.min_quote_volume_1d = float(min_quote_volume_1d)
        self.excellent_quote_volume_1d = float(excellent_quote_volume_1d)
        self.min_trades_1h = int(min_trades_1h)
        self.excellent_trades_1h = int(excellent_trades_1h)
        self.min_trades_4h = int(min_trades_4h)
        self.excellent_trades_4h = int(excellent_trades_4h)

    @staticmethod
    def _extract_window(recent_activity: dict[str, Any], window: str) -> dict[str, Any]:
        windows = recent_activity.get("windows")
        if not isinstance(windows, dict):
            return {}
        value = windows.get(window)
        if not isinstance(value, dict):
            return {}
        return value

    @staticmethod
    def _normalize(value: Any, minimum: float, excellent: float) -> float:
        try:
            val = float(value)
        except Exception:
            return 0.0
        if val <= minimum:
            return 0.0
        span = max(excellent - minimum, 1e-9)
        return max(0.0, min(1.0, (val - minimum) / span))

    def evaluate(self, context: MarketContext) -> JudgeResult:
        if not self.enabled or self.max_score <= 0:
            return JudgeResult(
                name="recent_activity",
                score=0,
                max_score=self.max_score,
                reason="recent activity disabled",
            )

        raw_data = context.raw_data if isinstance(context.raw_data, dict) else {}
        recent_activity = raw_data.get("recent_activity")
        if not isinstance(recent_activity, dict):
            return JudgeResult(
                name="recent_activity",
                score=0,
                max_score=self.max_score,
                reason="recent activity missing",
            )

        mode = str(recent_activity.get("mode") or "unknown")
        source = str(recent_activity.get("source") or "unknown")

        w1h = self._extract_window(recent_activity, "1h")
        w4h = self._extract_window(recent_activity, "4h")
        w1d = self._extract_window(recent_activity, "1d")

        ratio_1h = self._normalize(
            w1h.get("quote_volume"),
            self.min_quote_volume_1h,
            self.excellent_quote_volume_1h,
        )
        ratio_4h = self._normalize(
            w4h.get("quote_volume"),
            self.min_quote_volume_4h,
            self.excellent_quote_volume_4h,
        )
        ratio_1d = self._normalize(
            w1d.get("quote_volume"),
            self.min_quote_volume_1d,
            self.excellent_quote_volume_1d,
        ) if self.use_1d else 0.0

        trades_1h = self._normalize(
            w1h.get("trade_count"),
            float(self.min_trades_1h),
            float(self.excellent_trades_1h),
        )
        trades_4h = self._normalize(
            w4h.get("trade_count"),
            float(self.min_trades_4h),
            float(self.excellent_trades_4h),
        )
        trades_ratio = (trades_1h + trades_4h) / 2.0

        vol_weights = {
            "1h": 0.45,
            "4h": 0.30,
            "1d": 0.10 if self.use_1d else 0.0,
            "trades": 0.15,
        }

        # Candle-mode windows (futures klines) can be early in the candle,
        # so de-emphasize 1d to avoid over-penalizing scalping scanners.
        if mode == "candle":
            vol_weights["1d"] = min(vol_weights["1d"], 0.03)

        total_weight = max(vol_weights["1h"] + vol_weights["4h"] + vol_weights["1d"] + vol_weights["trades"], 1e-9)
        raw_ratio = (
            ratio_1h * vol_weights["1h"]
            + ratio_4h * vol_weights["4h"]
            + ratio_1d * vol_weights["1d"]
            + trades_ratio * vol_weights["trades"]
        ) / total_weight

        stale_windows = []
        for window_name, window_data in (("1h", w1h), ("4h", w4h), ("1d", w1d)):
            if isinstance(window_data, dict) and bool(window_data.get("stale", False)):
                stale_windows.append(window_name)

        stale_penalty = 1.0
        if stale_windows:
            stale_penalty = 0.6

        score = int(round(max(0.0, min(1.0, raw_ratio * stale_penalty)) * self.max_score))

        status_bits = []
        if stale_windows:
            status_bits.append(f"recent activity stale ({','.join(stale_windows)})")
        reason = (
            f"mode={mode}, source={source}, vol1h={w1h.get('quote_volume')}, trades1h={w1h.get('trade_count')}, "
            f"vol4h={w4h.get('quote_volume')}, trades4h={w4h.get('trade_count')}, vol1d={w1d.get('quote_volume')}, "
            f"ratio={raw_ratio:.3f}, stale_penalty={stale_penalty:.2f}"
        )
        if status_bits:
            reason += f", status={'; '.join(status_bits)}"

        return JudgeResult(
            name="recent_activity",
            score=score,
            max_score=self.max_score,
            reason=reason,
        )
