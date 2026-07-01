from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from ...db.database import SessionLocal
from ..models import MarketContext, MarketScore
from .binance_client import BinanceFuturesClient
from .indicator_service import IndicatorService
from .judge_engine import JudgeEngine
from .market_repository import MarketRepository
from .market_cache_repository import MarketCacheRepository
from .scanner_output_repository import ScannerOutputRepository
from .pairlist_service import PairlistService

if TYPE_CHECKING:
    from ..schemas import ScannerConfigInternal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HardFilterResult:
    passed: bool
    failed_reasons: list[str]
    spread_to_atr_ratio: float | None
    soft_warnings: list[str]


class MarketScannerService:
    def __init__(
        self,
        scanner_config: 'ScannerConfigInternal | None' = None,
        binance_client: BinanceFuturesClient | None = None,
        indicator_service: IndicatorService | None = None,
        judge_engine: JudgeEngine | None = None,
        repository: MarketRepository | None = None,
        cache_repository: MarketCacheRepository | None = None,
        output_repository: ScannerOutputRepository | None = None,
    ):
        self.scanner_config = scanner_config
        self.binance_client = binance_client or BinanceFuturesClient()
        self.indicator_service = indicator_service or IndicatorService()
        
        # Create judge engine from scanner config if provided
        if judge_engine:
            self.judge_engine = judge_engine
        elif scanner_config:
            self.judge_engine = JudgeEngine(scanner_config=scanner_config)
        else:
            self.judge_engine = JudgeEngine()
        
        self.repository = repository or MarketRepository()
        self.cache_repository = cache_repository or MarketCacheRepository()
        self.output_repository = output_repository or ScannerOutputRepository()
        self._running = False
        self._last_run_started_at: int | None = None
        self._last_run_finished_at: int | None = None
        self._last_run_error: str | None = None
        self._cache_timestamp: int | None = None  # Track which cache was used

    @staticmethod
    def _default_recent_activity_payload() -> dict[str, Any]:
        return {
            'source': None,
            'mode': None,
            'updated_at': None,
            'stale_after_seconds': None,
            'windows': {
                '1h': {'quote_volume': None, 'trade_count': None, 'updated_at': None, 'stale': True},
                '4h': {'quote_volume': None, 'trade_count': None, 'updated_at': None, 'stale': True},
                '1d': {'quote_volume': None, 'trade_count': None, 'updated_at': None, 'stale': True},
            },
        }

    def _normalize_recent_activity(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        base = self._default_recent_activity_payload()
        incoming = raw_data.get('recent_activity')
        if not isinstance(incoming, dict):
            raw_data['recent_activity'] = base
            return base

        normalized = {
            'source': incoming.get('source'),
            'mode': incoming.get('mode'),
            'updated_at': incoming.get('updated_at'),
            'stale_after_seconds': incoming.get('stale_after_seconds'),
            'windows': {},
        }
        windows = incoming.get('windows') if isinstance(incoming.get('windows'), dict) else {}
        for window in ('1h', '4h', '1d'):
            w_in = windows.get(window) if isinstance(windows.get(window), dict) else {}
            normalized['windows'][window] = {
                'quote_volume': w_in.get('quote_volume'),
                'trade_count': w_in.get('trade_count'),
                'updated_at': w_in.get('updated_at'),
                'stale': bool(w_in.get('stale', True)),
            }

        raw_data['recent_activity'] = normalized
        return normalized

    def _recent_activity_summary(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        recent_activity = self._normalize_recent_activity(raw_data)
        windows = recent_activity.get('windows', {}) if isinstance(recent_activity.get('windows'), dict) else {}
        w1h = windows.get('1h', {}) if isinstance(windows.get('1h'), dict) else {}
        w4h = windows.get('4h', {}) if isinstance(windows.get('4h'), dict) else {}
        w1d = windows.get('1d', {}) if isinstance(windows.get('1d'), dict) else {}

        return {
            'mode': recent_activity.get('mode'),
            'source': recent_activity.get('source'),
            'quote_volume_1h': w1h.get('quote_volume'),
            'trade_count_1h': w1h.get('trade_count'),
            'quote_volume_4h': w4h.get('quote_volume'),
            'trade_count_4h': w4h.get('trade_count'),
            'quote_volume_1d': w1d.get('quote_volume'),
            'stale': bool(w1h.get('stale', False) or w4h.get('stale', False) or w1d.get('stale', False)),
        }

    @property
    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "lastRunStartedAt": self._last_run_started_at,
            "lastRunFinishedAt": self._last_run_finished_at,
            "lastRunError": self._last_run_error,
        }

    async def run_cycle(self) -> dict[str, Any]:
        self._running = True
        self._last_run_started_at = int(time.time())
        self._last_run_error = None
        try:
            # NEW: Read from cache instead of fetching from Binance
            cache_timestamp, cached_data = await self._read_from_cache()
            
            if not cached_data:
                raise ValueError("No cached market data available. Fetcher service may not be running.")
            
            self._cache_timestamp = cache_timestamp
            
            # Convert cache to scoring format
            market_scores = await self._score_from_cache(cached_data)

            # Annotate hard-filter results before persisting snapshots.
            if self.scanner_config:
                market_scores = self._annotate_hard_filters(market_scores)
            
            # Persist scores to MarketSnapshot (for historical tracking)
            await self._persist_scores(market_scores, cache_timestamp)
            
            # NEW: Write scanner outputs (fresh data to both DB and JSON)
            output_count = 0
            if self.scanner_config:
                output_count = await self._write_scanner_outputs(market_scores)
            
            return {
                "ok": True,
                "symbolsProcessed": len(market_scores),
                "outputSymbols": output_count,
                "timestamp": int(time.time()),
                "cacheTimestamp": cache_timestamp,
                "cacheAge": int(time.time() - cache_timestamp)
            }
        except Exception as exc:
            self._last_run_error = str(exc)
            logger.exception("Market scanner cycle failed")
            return {"ok": False, "error": str(exc), "timestamp": int(time.time())}
        finally:
            self._running = False
            self._last_run_finished_at = int(time.time())
    
    async def _read_from_cache(self) -> tuple[int, list[dict[str, Any]]]:
        """Read latest market data from cache"""
        def _read():
            db = SessionLocal()
            try:
                return self.cache_repository.get_latest_cache(db)
            finally:
                db.close()
        
        return await asyncio.to_thread(_read)
    
    async def _score_from_cache(self, cached_data: list[dict[str, Any]]) -> list[MarketScore]:
        """Score markets from cached data"""
        contexts: list[MarketContext] = []
        now_ts = int(time.time())
        
        for data in cached_data:
            raw_data = data.get('raw_data')
            if not isinstance(raw_data, dict):
                raw_data_json = data.get('raw_data_json')
                if isinstance(raw_data_json, str) and raw_data_json:
                    try:
                        raw_data = json.loads(raw_data_json)
                    except Exception:
                        raw_data = {}
                else:
                    raw_data = {}

            row_market_type = str(raw_data.get('market_type', 'futures')).lower()
            if self.scanner_config:
                desired_market_type = str(self.scanner_config.market_type).lower()
                if row_market_type != desired_market_type:
                    continue

            self._normalize_recent_activity(raw_data)

            # Build MarketContext from cached data
            contexts.append(
                MarketContext(
                    symbol=data['symbol'],
                    exchange=data['exchange'],
                    timestamp=now_ts,
                    price=data['price'],
                    quote_volume=data['volume'],
                    bid_price=data['bid_price'],
                    ask_price=data['ask_price'],
                    bid_qty=data['bid_qty'],
                    ask_qty=data['ask_qty'],
                    spread_pct=data['spread'],
                    atr_pct=data['atr'],
                    funding_rate=data['funding_rate'],
                    tick_size=data['tick_size'],
                    step_size=data['step_size'],
                    raw_data=raw_data
                )
            )
        
        # Score all contexts
        async def _score_one(context: MarketContext) -> MarketScore:
            results = await self.judge_engine.evaluate(context)
            total_score = sum(r.score for r in results)
            reasons = {r.name: r.reason for r in results}
            activity_summary = self._recent_activity_summary(context.raw_data)
            reasons['recent_activity_summary'] = activity_summary
            context.raw_data['recent_activity_summary'] = activity_summary
            return MarketScore(
                symbol=context.symbol,
                exchange=context.exchange,
                timestamp=context.timestamp,
                total_score=max(0, min(100, total_score)),
                price=context.price,
                volume=context.quote_volume,
                atr=context.atr_pct,
                spread=context.spread_pct,
                funding=context.funding_rate,
                judge_results=results,
                reasons=reasons,
                raw_data=context.raw_data,
            )
        
        return await asyncio.gather(*[_score_one(c) for c in contexts])

    async def _build_scores(self, payload: dict[str, Any]) -> list[MarketScore]:
        symbols_meta = payload.get("symbols_meta") or []
        tickers = payload.get("tickers") or []
        book_tickers = payload.get("book_tickers") or []
        funding = payload.get("funding") or []

        klines_map = payload.get("klines_map") or {}

        ticker_by_symbol = {str(x.get("symbol")): x for x in tickers if isinstance(x, dict)}
        book_by_symbol = {str(x.get("symbol")): x for x in book_tickers if isinstance(x, dict)}
        funding_by_symbol = {str(x.get("symbol")): x for x in funding if isinstance(x, dict)}

        contexts: list[MarketContext] = []
        now_ts = int(time.time())

        for meta in symbols_meta:
            symbol = str(meta.get("symbol") or "").upper()
            if not symbol:
                continue

            ticker = ticker_by_symbol.get(symbol) or {}
            book = book_by_symbol.get(symbol) or {}
            fund = funding_by_symbol.get(symbol) or {}

            price = float(ticker.get("lastPrice") or 0.0)
            quote_volume = float(ticker.get("quoteVolume") or 0.0)
            bid_price = float(book.get("bidPrice") or 0.0)
            ask_price = float(book.get("askPrice") or 0.0)
            bid_qty = float(book.get("bidQty") or 0.0)
            ask_qty = float(book.get("askQty") or 0.0)

            if bid_price > 0 and ask_price > 0:
                spread_pct = ((ask_price - bid_price) / ((ask_price + bid_price) / 2.0)) * 100.0
            else:
                spread_pct = 100.0

            atr_pct = self.indicator_service.compute_atr_percent(klines_map.get(symbol) or [])
            funding_rate = float(fund.get("lastFundingRate") or 0.0)

            tick_size = 0.0
            step_size = 0.0
            for filt in meta.get("filters") or []:
                if not isinstance(filt, dict):
                    continue
                f_type = filt.get("filterType")
                if f_type == "PRICE_FILTER":
                    tick_size = float(filt.get("tickSize") or 0.0)
                elif f_type == "LOT_SIZE":
                    step_size = float(filt.get("stepSize") or 0.0)

            contexts.append(
                MarketContext(
                    symbol=symbol,
                    exchange="binance",
                    timestamp=now_ts,
                    price=price,
                    quote_volume=quote_volume,
                    bid_price=bid_price,
                    ask_price=ask_price,
                    bid_qty=bid_qty,
                    ask_qty=ask_qty,
                    spread_pct=max(spread_pct, 0.0),
                    atr_pct=max(atr_pct, 0.0),
                    funding_rate=funding_rate,
                    tick_size=max(tick_size, 0.0),
                    step_size=max(step_size, 0.0),
                    raw_data={
                        "ticker": ticker,
                        "bookTicker": book,
                        "funding": fund,
                        "exchangeMeta": {
                            "pricePrecision": meta.get("pricePrecision"),
                            "quantityPrecision": meta.get("quantityPrecision"),
                            "contractType": meta.get("contractType"),
                        },
                    },
                )
            )

        async def _score_one(context: MarketContext) -> MarketScore:
            results = await self.judge_engine.evaluate(context)
            total_score = sum(r.score for r in results)
            reasons = {r.name: r.reason for r in results}
            return MarketScore(
                symbol=context.symbol,
                exchange=context.exchange,
                timestamp=context.timestamp,
                total_score=max(0, min(100, total_score)),
                price=context.price,
                volume=context.quote_volume,
                atr=context.atr_pct,
                spread=context.spread_pct,
                funding=context.funding_rate,
                judge_results=results,
                reasons=reasons,
                raw_data=context.raw_data,
            )

        return await asyncio.gather(*[_score_one(c) for c in contexts])

    async def _persist_scores(self, market_scores: list[MarketScore], cache_timestamp: int | None = None) -> None:
        def _to_row(score: MarketScore) -> dict[str, Any]:
            by_name = {r.name: r for r in score.judge_results}
            row = {
                "timestamp": score.timestamp,
                "exchange": score.exchange,
                "symbol": score.symbol,
                "price": score.price,
                "volume": score.volume,
                "atr": score.atr,
                "spread": score.spread,
                "funding": score.funding,
                "liquidity_score": int((by_name.get("liquidity").score if by_name.get("liquidity") else 0)),
                "spread_score": int((by_name.get("spread").score if by_name.get("spread") else 0)),
                "atr_score": int((by_name.get("atr").score if by_name.get("atr") else 0)),
                "funding_score": int((by_name.get("funding").score if by_name.get("funding") else 0)),
                "tick_score": int((by_name.get("tick_size").score if by_name.get("tick_size") else 0)),
                "market_quality": int(score.total_score),
                "reasons_json": json.dumps(score.reasons, ensure_ascii=False),
                "raw_data_json": json.dumps(score.raw_data, ensure_ascii=False),
            }
            
            # Add scanner_id and user_id if available
            if self.scanner_config:
                row["scanner_id"] = self.scanner_config.id
                row["user_id"] = self.scanner_config.user_id
            
            return row

        rows = [_to_row(s) for s in market_scores]

        def _save():
            db = SessionLocal()
            try:
                self.repository.save_snapshots(db, rows)
            finally:
                db.close()

        await asyncio.to_thread(_save)

    def _evaluate_hard_filters(self, score: MarketScore) -> HardFilterResult:
        thresholds = self.scanner_config.scoring_thresholds
        weights = self.scanner_config.scoring_weights
        failed_reasons: list[str] = []
        soft_warnings: list[str] = []

        spread_to_atr_ratio = (score.spread / score.atr) if score.atr > 0 else None

        # Hard safety filters: only exclude clearly unsafe/unusable pairs.
        if score.price <= 0:
            failed_reasons.append("invalid price")
        if score.volume < thresholds.minQuoteVolume24h:
            failed_reasons.append("volume below minimum")
        if score.spread > thresholds.maxSpreadPct:
            failed_reasons.append("spread above maximum")

        # ATR is a scoring signal; only hard-fail invalid ATR when volatility scoring is used.
        if score.atr <= 0 and weights.volatility > 0:
            failed_reasons.append("invalid ATR")

        # Soft warnings for transparency (do not block output).
        if score.atr < thresholds.minAtrPct:
            soft_warnings.append("ATR below preferred range")
        if score.atr > thresholds.maxAtrPct:
            soft_warnings.append("ATR above preferred range")

        max_ratio = getattr(thresholds, "maxSpreadToAtrRatio", 0.10)
        if spread_to_atr_ratio is not None and max_ratio > 0 and spread_to_atr_ratio > max_ratio:
            soft_warnings.append("spread/ATR ratio above preferred maximum")

        funding_abs = abs(score.funding)
        normal_funding_abs = getattr(thresholds, "normalFundingAbs", 0.0001)
        max_funding_abs = getattr(thresholds, "maxFundingAbs", 0.001)
        if funding_abs >= max_funding_abs:
            soft_warnings.append("funding extreme")
        elif funding_abs > normal_funding_abs:
            soft_warnings.append("funding elevated")

        return HardFilterResult(
            passed=len(failed_reasons) == 0,
            failed_reasons=failed_reasons,
            spread_to_atr_ratio=spread_to_atr_ratio,
            soft_warnings=soft_warnings,
        )

    def _annotate_hard_filters(self, market_scores: list[MarketScore]) -> list[MarketScore]:
        """Attach hard-filter metadata to score raw/reason payloads for transparency."""
        annotated: list[MarketScore] = []

        for score in market_scores:
            result = self._evaluate_hard_filters(score)

            hard_filter_payload = {
                "passed": result.passed,
                "failed_reasons": result.failed_reasons,
                "spread_to_atr_ratio": result.spread_to_atr_ratio,
                "soft_warnings": result.soft_warnings,
            }

            score.raw_data = score.raw_data or {}
            score.raw_data["hard_filters"] = hard_filter_payload

            score.reasons["hard_filters"] = (
                "passed"
                if result.passed
                else "failed: " + ", ".join(result.failed_reasons)
            )
            if result.soft_warnings:
                score.reasons["soft_warnings"] = ", ".join(result.soft_warnings)

            annotated.append(score)

        return annotated

    def _select_output_scores(self, market_scores: list[MarketScore]) -> list[MarketScore]:
        """Select final output symbols using hard filters + min score, sorted and limited."""
        selected = []
        for score in market_scores:
            hard_filters = (score.raw_data or {}).get("hard_filters") or {}
            hard_passed = hard_filters.get("passed", True)
            if hard_passed and score.total_score >= self.scanner_config.min_market_score:
                selected.append(score)

        selected.sort(key=lambda s: s.total_score, reverse=True)
        return selected[:self.scanner_config.max_pairs]

    async def _write_scanner_outputs(self, market_scores: list[MarketScore]) -> int:
        """
        Write scanner outputs to both DB and JSON file.
        Filters based on min_score and max_pairs from scanner config.
        Returns the number of symbols written.
        """
        if not self.scanner_config:
            return 0

        top_scores = self._select_output_scores(market_scores)
        
        if not top_scores:
            logger.warning(
                f"No symbols meet minimum score {self.scanner_config.min_market_score} "
                f"for scanner '{self.scanner_config.name}'"
            )
            # Still clear old outputs even if no new ones
            def _clear():
                db = SessionLocal()
                try:
                    self.output_repository.clear_scanner_outputs(db, self.scanner_config.id)
                finally:
                    db.close()
            await asyncio.to_thread(_clear)
            return 0
        
        # Convert to output format
        generated_at = int(time.time())
        outputs = []
        
        for rank, score in enumerate(top_scores, start=1):
            # Get individual judge scores
            by_name = {r.name: r for r in score.judge_results}
            
            output = {
                "scanner_id": self.scanner_config.id,
                "user_id": self.scanner_config.user_id,
                "generated_at": generated_at,
                "symbol": score.symbol,
                "exchange": score.exchange,
                "rank": rank,
                "price": score.price,
                "volume": score.volume,
                "atr": score.atr,
                "spread": score.spread,
                "funding": score.funding,
                "total_score": int(score.total_score),
                "liquidity_score": int(by_name.get("liquidity").score if by_name.get("liquidity") else 0),
                "volatility_score": int(by_name.get("atr").score if by_name.get("atr") else 0),
                "spread_score": int(by_name.get("spread").score if by_name.get("spread") else 0),
                "funding_score": int(by_name.get("funding").score if by_name.get("funding") else 0),
                "tick_score": int(by_name.get("tick_size").score if by_name.get("tick_size") else 0),
                "reasons_json": json.dumps(score.reasons, ensure_ascii=False),
            }
            outputs.append(output)
        
        # Write to database (atomically replace old outputs)
        def _write_db():
            db = SessionLocal()
            try:
                self.output_repository.replace_scanner_outputs(
                    db,
                    scanner_id=self.scanner_config.id,
                    outputs=outputs
                )
            finally:
                db.close()
        
        await asyncio.to_thread(_write_db)
        
        # Write to JSON file
        pairlist_service = PairlistService(
            scanner_config=self.scanner_config,
            refresh_period=self.scanner_config.interval_minutes * 60,
            pair_format="slash"
        )
        
        pairlist_result = pairlist_service.generate_pairlist_from_outputs(outputs)
        
        if pairlist_result.get("success"):
            logger.info(
                f"Scanner '{self.scanner_config.name}' output: "
                f"{len(outputs)} symbols written to DB and JSON"
            )
        else:
            logger.error(
                f"Scanner '{self.scanner_config.name}' DB write succeeded but JSON failed: "
                f"{pairlist_result.get('error')}"
            )
        
        return len(outputs)
