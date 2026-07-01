from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..judges import (
    ATRJudge,
    FundingJudge,
    IMarketJudge,
    LiquidityJudge,
    RecentActivityJudge,
    SpreadJudge,
    TickSizeJudge,
)
from ..models import JudgeResult, MarketContext

if TYPE_CHECKING:
    from ..schemas import ScannerConfigInternal


logger = logging.getLogger(__name__)


class JudgeEngine:
    def __init__(self, judges: list[IMarketJudge] | None = None, scanner_config: 'ScannerConfigInternal | None' = None):
        if judges:
            self.judges = judges
        elif scanner_config:
            # Create judges from scanner config with custom weights and thresholds
            weights = scanner_config.scoring_weights
            thresholds = scanner_config.scoring_thresholds
            recent_activity_cfg = scanner_config.recent_activity
            recent_activity_thresholds = scanner_config.recent_activity_thresholds

            total_weight = (
                int(weights.liquidity)
                + int(weights.volatility)
                + int(weights.spread)
                + int(weights.funding)
                + int(weights.tradeCount)
                + int(getattr(weights, "recentActivity", 0))
            )
            if total_weight > 100:
                logger.warning(
                    "Scanner '%s' weight total exceeds 100 (total=%s). "
                    "Scores are not auto-normalized.",
                    scanner_config.name,
                    total_weight,
                )
            
            self.judges = [
                LiquidityJudge(
                    max_score=weights.liquidity,
                    min_volume=thresholds.minQuoteVolume24h,
                    excellent_volume=thresholds.excellentQuoteVolume24h
                ),
                SpreadJudge(
                    max_score=weights.spread,
                    max_spread=thresholds.maxSpreadPct,
                    max_spread_to_atr_ratio=getattr(thresholds, "maxSpreadToAtrRatio", 0.10)
                ),
                ATRJudge(
                    max_score=weights.volatility,
                    min_atr=thresholds.minAtrPct,
                    ideal_low=thresholds.idealAtrPctLow,
                    ideal_high=thresholds.idealAtrPctHigh,
                    max_atr=thresholds.maxAtrPct
                ),
                FundingJudge(
                    max_score=weights.funding,
                    normal_funding_abs=getattr(thresholds, "normalFundingAbs", 0.0001),
                    max_funding_abs=getattr(thresholds, "maxFundingAbs", 0.001),
                ),
                RecentActivityJudge(
                    max_score=getattr(weights, "recentActivity", 0),
                    enabled=bool(getattr(recent_activity_cfg, "enabled", True)),
                    primary_window=getattr(recent_activity_cfg, "primaryWindow", "1h"),
                    secondary_window=getattr(recent_activity_cfg, "secondaryWindow", "4h"),
                    use_1d=bool(getattr(recent_activity_cfg, "use1d", True)),
                    stale_after_seconds=int(getattr(recent_activity_cfg, "staleAfterSeconds", 180)),
                    min_quote_volume_1h=float(getattr(recent_activity_thresholds, "minQuoteVolume1h", 1_000_000)),
                    excellent_quote_volume_1h=float(getattr(recent_activity_thresholds, "excellentQuoteVolume1h", 25_000_000)),
                    min_quote_volume_4h=float(getattr(recent_activity_thresholds, "minQuoteVolume4h", 5_000_000)),
                    excellent_quote_volume_4h=float(getattr(recent_activity_thresholds, "excellentQuoteVolume4h", 100_000_000)),
                    min_quote_volume_1d=float(getattr(recent_activity_thresholds, "minQuoteVolume1d", 20_000_000)),
                    excellent_quote_volume_1d=float(getattr(recent_activity_thresholds, "excellentQuoteVolume1d", 500_000_000)),
                    min_trades_1h=int(getattr(recent_activity_thresholds, "minTrades1h", 500)),
                    excellent_trades_1h=int(getattr(recent_activity_thresholds, "excellentTrades1h", 10_000)),
                    min_trades_4h=int(getattr(recent_activity_thresholds, "minTrades4h", 1_500)),
                    excellent_trades_4h=int(getattr(recent_activity_thresholds, "excellentTrades4h", 30_000)),
                ),
                # Backward compatibility: tradeCount weight currently powers precision quality
                # via TickSizeJudge. Recent activity uses real trade counts separately.
                TickSizeJudge(max_score=weights.tradeCount),
            ]
        else:
            # Default judges with hardcoded values (backward compatibility)
            self.judges = [
                LiquidityJudge(),
                SpreadJudge(),
                ATRJudge(),
                FundingJudge(),
                TickSizeJudge(),
            ]

    async def evaluate(self, context: MarketContext) -> list[JudgeResult]:
        async def _eval(judge: IMarketJudge) -> JudgeResult:
            return await asyncio.to_thread(judge.evaluate, context)

        return await asyncio.gather(*[_eval(j) for j in self.judges])
