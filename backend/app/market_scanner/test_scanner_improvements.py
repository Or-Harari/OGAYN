import asyncio
import unittest

from app.market_scanner.judges import SpreadJudge, FundingJudge, TickSizeJudge, RecentActivityJudge
from app.market_scanner.models import MarketContext, MarketScore
from app.market_scanner.schemas import (
    RecentActivityConfig,
    RecentActivityThresholds,
    ScannerConfigInternal,
    ScoringThresholds,
    ScoringWeights,
)
from app.market_scanner.services.judge_engine import JudgeEngine
from app.market_scanner.services.market_scanner_service import MarketScannerService


class ScannerImprovementsTests(unittest.TestCase):
    def _make_config(self, min_score: int = 70) -> ScannerConfigInternal:
        return ScannerConfigInternal(
            id=1,
            user_id=1,
            name="test",
            exchange="binance",
            market_type="futures",
            enabled=True,
            interval_minutes=5,
            quote_asset="USDT",
            max_pairs=30,
            min_market_score=min_score,
            include_symbols=[],
            exclude_symbols=[],
            scoring_weights=ScoringWeights(
                liquidity=30,
                volatility=25,
                spread=25,
                funding=10,
                tradeCount=17,
                recentActivity=0,
            ),
            scoring_thresholds=ScoringThresholds(
                minQuoteVolume24h=30_000_000,
                excellentQuoteVolume24h=500_000_000,
                minAtrPct=0.5,
                idealAtrPctLow=1.0,
                idealAtrPctHigh=3.0,
                maxAtrPct=6.0,
                maxSpreadPct=0.1,
                maxSpreadToAtrRatio=0.10,
                normalFundingAbs=0.0001,
                maxFundingAbs=0.001,
            ),
            recent_activity=RecentActivityConfig(
                enabled=True,
                primaryWindow="1h",
                secondaryWindow="4h",
                use1d=True,
                staleAfterSeconds=180,
            ),
            recent_activity_thresholds=RecentActivityThresholds(
                minQuoteVolume1h=1_000_000,
                excellentQuoteVolume1h=25_000_000,
                minQuoteVolume4h=5_000_000,
                excellentQuoteVolume4h=100_000_000,
                minQuoteVolume1d=20_000_000,
                excellentQuoteVolume1d=500_000_000,
                minTrades1h=500,
                excellentTrades1h=10_000,
                minTrades4h=1_500,
                excellentTrades4h=30_000,
            ),
            output_base_path="tmp/scanner",
            last_run_at=None,
        )

    def _make_score(self, symbol: str, score: int, volume: float, spread: float, atr: float) -> MarketScore:
        return MarketScore(
            symbol=symbol,
            exchange="binance",
            timestamp=1,
            total_score=score,
            price=100.0,
            volume=volume,
            atr=atr,
            spread=spread,
            funding=0.0,
            judge_results=[],
            reasons={},
            raw_data={},
        )

    def test_hard_filter_pass_fail_annotation(self):
        service = MarketScannerService(scanner_config=self._make_config())

        passing = self._make_score("BTCUSDT", 90, 50_000_000, 0.05, 1.2)
        failing = self._make_score("LOWVOLUSDT", 90, 1_000_000, 0.2, 0.2)

        annotated = service._annotate_hard_filters([passing, failing])

        self.assertTrue(annotated[0].raw_data["hard_filters"]["passed"])
        self.assertEqual(annotated[0].raw_data["hard_filters"]["failed_reasons"], [])

        self.assertFalse(annotated[1].raw_data["hard_filters"]["passed"])
        reasons = annotated[1].raw_data["hard_filters"]["failed_reasons"]
        self.assertIn("volume below minimum", reasons)
        self.assertIn("spread above maximum", reasons)
        self.assertNotIn("ATR below minimum", reasons)
        soft = annotated[1].raw_data["hard_filters"]["soft_warnings"]
        self.assertIn("ATR below preferred range", soft)

    def test_pairlist_selection_excludes_hard_filter_failures(self):
        service = MarketScannerService(scanner_config=self._make_config(min_score=70))

        good = self._make_score("GOODUSDT", 85, 100_000_000, 0.05, 1.0)
        bad_hard_filter = self._make_score("BADFILTERUSDT", 95, 500_000, 0.05, 1.0)

        annotated = service._annotate_hard_filters([good, bad_hard_filter])
        selected = service._select_output_scores(annotated)

        symbols = [s.symbol for s in selected]
        self.assertIn("GOODUSDT", symbols)
        self.assertNotIn("BADFILTERUSDT", symbols)

    def test_spread_to_atr_ratio_penalty(self):
        judge = SpreadJudge(max_score=20, max_spread=0.1, max_spread_to_atr_ratio=0.10)

        good = MarketContext(
            symbol="GOODUSDT",
            exchange="binance",
            timestamp=1,
            price=100.0,
            quote_volume=100_000_000,
            bid_price=99.95,
            ask_price=100.05,
            bid_qty=1.0,
            ask_qty=1.0,
            spread_pct=0.05,
            atr_pct=1.0,
            funding_rate=0.0,
            tick_size=0.01,
            step_size=0.001,
            raw_data={},
        )
        bad = MarketContext(
            symbol="BADUSDT",
            exchange="binance",
            timestamp=1,
            price=100.0,
            quote_volume=100_000_000,
            bid_price=99.9,
            ask_price=100.1,
            bid_qty=1.0,
            ask_qty=1.0,
            spread_pct=0.10,
            atr_pct=0.5,
            funding_rate=0.0,
            tick_size=0.01,
            step_size=0.001,
            raw_data={},
        )

        good_result = judge.evaluate(good)
        bad_result = judge.evaluate(bad)

        self.assertGreater(good_result.score, bad_result.score)
        self.assertIn("spread/ATR", bad_result.reason)

    def test_funding_extremeness_scoring(self):
        judge = FundingJudge(max_score=10, normal_funding_abs=0.0001, max_funding_abs=0.001)

        neutral = MarketContext(
            symbol="NEUTRALUSDT",
            exchange="binance",
            timestamp=1,
            price=100.0,
            quote_volume=100_000_000,
            bid_price=99.95,
            ask_price=100.05,
            bid_qty=1.0,
            ask_qty=1.0,
            spread_pct=0.05,
            atr_pct=1.0,
            funding_rate=0.00005,
            tick_size=0.01,
            step_size=0.001,
            raw_data={},
        )
        extreme = MarketContext(
            symbol="EXTREMEUSDT",
            exchange="binance",
            timestamp=1,
            price=100.0,
            quote_volume=100_000_000,
            bid_price=99.95,
            ask_price=100.05,
            bid_qty=1.0,
            ask_qty=1.0,
            spread_pct=0.05,
            atr_pct=1.0,
            funding_rate=0.002,
            tick_size=0.01,
            step_size=0.001,
            raw_data={},
        )

        neutral_result = judge.evaluate(neutral)
        extreme_result = judge.evaluate(extreme)

        self.assertGreater(neutral_result.score, extreme_result.score)
        self.assertEqual(extreme_result.score, 0)

    def test_tradecount_weight_maps_to_ticksize_judge(self):
        config = self._make_config()
        engine = JudgeEngine(scanner_config=config)

        tick_judges = [j for j in engine.judges if isinstance(j, TickSizeJudge)]
        self.assertEqual(len(tick_judges), 1)
        self.assertEqual(tick_judges[0].max_score, 17)

    def _make_recent_activity_context(self, windows: dict | None = None, mode: str = "rolling") -> MarketContext:
        payload = {
            "source": "websocket",
            "mode": mode,
            "updated_at": 123,
            "stale_after_seconds": 180,
            "windows": windows or {},
        }
        return MarketContext(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=1,
            price=100.0,
            quote_volume=100_000_000,
            bid_price=99.95,
            ask_price=100.05,
            bid_qty=10.0,
            ask_qty=10.0,
            spread_pct=0.05,
            atr_pct=1.0,
            funding_rate=0.0,
            tick_size=0.01,
            step_size=0.001,
            raw_data={"recent_activity": payload},
        )

    def test_recent_activity_missing_does_not_crash_and_scores_zero(self):
        judge = RecentActivityJudge(max_score=20, enabled=True)
        context = MarketContext(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp=1,
            price=100.0,
            quote_volume=100_000_000,
            bid_price=99.95,
            ask_price=100.05,
            bid_qty=10.0,
            ask_qty=10.0,
            spread_pct=0.05,
            atr_pct=1.0,
            funding_rate=0.0,
            tick_size=0.01,
            step_size=0.001,
            raw_data={},
        )

        result = judge.evaluate(context)
        self.assertEqual(result.score, 0)
        self.assertIn("missing", result.reason)

    def test_recent_activity_stale_penalizes_score(self):
        judge = RecentActivityJudge(max_score=20, enabled=True)
        fresh = self._make_recent_activity_context(
            windows={
                "1h": {"quote_volume": 20_000_000, "trade_count": 8_000, "updated_at": 1, "stale": False},
                "4h": {"quote_volume": 80_000_000, "trade_count": 22_000, "updated_at": 1, "stale": False},
                "1d": {"quote_volume": 400_000_000, "trade_count": 100_000, "updated_at": 1, "stale": False},
            }
        )
        stale = self._make_recent_activity_context(
            windows={
                "1h": {"quote_volume": 20_000_000, "trade_count": 8_000, "updated_at": 1, "stale": True},
                "4h": {"quote_volume": 80_000_000, "trade_count": 22_000, "updated_at": 1, "stale": False},
                "1d": {"quote_volume": 400_000_000, "trade_count": 100_000, "updated_at": 1, "stale": False},
            }
        )

        fresh_result = judge.evaluate(fresh)
        stale_result = judge.evaluate(stale)
        self.assertGreater(fresh_result.score, stale_result.score)
        self.assertIn("stale", stale_result.reason)

    def test_recent_activity_strong_1h_4h_volume_scores_high(self):
        judge = RecentActivityJudge(max_score=20, enabled=True)
        context = self._make_recent_activity_context(
            windows={
                "1h": {"quote_volume": 25_000_000, "trade_count": 10_000, "updated_at": 1, "stale": False},
                "4h": {"quote_volume": 100_000_000, "trade_count": 30_000, "updated_at": 1, "stale": False},
                "1d": {"quote_volume": 50_000_000, "trade_count": 50_000, "updated_at": 1, "stale": False},
            }
        )

        result = judge.evaluate(context)
        self.assertGreaterEqual(result.score, 15)

    def test_total_score_changes_with_recent_activity(self):
        config = self._make_config()
        config.scoring_weights.recentActivity = 20
        config.scoring_weights.tradeCount = 0

        service = MarketScannerService(scanner_config=config)

        base_row = {
            "symbol": "BTCUSDT",
            "exchange": "binance",
            "price": 100.0,
            "volume": 100_000_000,
            "bid_price": 99.95,
            "ask_price": 100.05,
            "bid_qty": 100.0,
            "ask_qty": 100.0,
            "spread": 0.05,
            "atr": 1.2,
            "funding_rate": 0.00005,
            "tick_size": 0.01,
            "step_size": 0.001,
            "raw_data": {
                "market_type": "futures",
            },
        }

        strong = dict(base_row)
        strong["raw_data"] = {
            "market_type": "futures",
            "recent_activity": {
                "source": "websocket",
                "mode": "rolling",
                "updated_at": 1,
                "stale_after_seconds": 180,
                "windows": {
                    "1h": {"quote_volume": 25_000_000, "trade_count": 10_000, "updated_at": 1, "stale": False},
                    "4h": {"quote_volume": 100_000_000, "trade_count": 30_000, "updated_at": 1, "stale": False},
                    "1d": {"quote_volume": 500_000_000, "trade_count": 100_000, "updated_at": 1, "stale": False},
                },
            },
        }

        weak = dict(base_row)
        weak["raw_data"] = {
            "market_type": "futures",
            "recent_activity": {
                "source": "websocket",
                "mode": "rolling",
                "updated_at": 1,
                "stale_after_seconds": 180,
                "windows": {
                    "1h": {"quote_volume": 10_000, "trade_count": 5, "updated_at": 1, "stale": False},
                    "4h": {"quote_volume": 20_000, "trade_count": 20, "updated_at": 1, "stale": False},
                    "1d": {"quote_volume": 30_000, "trade_count": 50, "updated_at": 1, "stale": False},
                },
            },
        }

        strong_score = asyncio.run(service._score_from_cache([strong]))[0]
        weak_score = asyncio.run(service._score_from_cache([weak]))[0]

        self.assertGreater(strong_score.total_score, weak_score.total_score)
        self.assertIn("recent_activity_summary", strong_score.reasons)


if __name__ == "__main__":
    unittest.main()
