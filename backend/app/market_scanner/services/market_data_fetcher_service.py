"""
Market Data Fetcher Service
Background service that fetches market data periodically and caches it
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ...db.database import SessionLocal
from .binance_client import BinanceFuturesClient
from .indicator_service import IndicatorService
from .market_cache_repository import MarketCacheRepository

logger = logging.getLogger(__name__)


class MarketDataFetcherService:
    """
    Background service that fetches market data from Binance periodically.
    All scanners read from this shared cache instead of fetching individually.
    """
    
    def __init__(
        self,
        binance_client: BinanceFuturesClient | None = None,
        indicator_service: IndicatorService | None = None,
        cache_repository: MarketCacheRepository | None = None,
    ):
        self.binance_client = binance_client or BinanceFuturesClient()
        self.indicator_service = indicator_service or IndicatorService()
        self.cache_repository = cache_repository or MarketCacheRepository()
        self._running = False
        self._task = None
        self._fetch_interval = 5  # minutes
        self._last_fetch_at = None
        self._last_error = None
    
    async def fetch_and_cache(self) -> dict[str, Any]:
        """
        Fetch market data from Binance and store in cache.
        Returns summary of operation.
        """
        start_time = time.time()
        
        try:
            logger.info("Fetching market data from Binance...")
            
            # Fetch all market data (same as before)
            payload = await self.binance_client.fetch_cycle_payload()
            
            # Process into cache format
            cache_data = await self._process_payload_to_cache(payload)
            
            # Save to database cache
            def _save():
                db = SessionLocal()
                try:
                    fetch_timestamp = self.cache_repository.save_cache(db, cache_data)
                    self._update_fetcher_status(db, fetch_timestamp, None)
                    return fetch_timestamp
                finally:
                    db.close()
            
            fetch_timestamp = await asyncio.to_thread(_save)
            
            duration = time.time() - start_time
            self._last_fetch_at = fetch_timestamp
            self._last_error = None
            
            logger.info(
                f"Market data cached successfully: {len(cache_data)} symbols "
                f"in {duration:.1f}s (timestamp: {fetch_timestamp})"
            )
            
            return {
                "ok": True,
                "timestamp": fetch_timestamp,
                "symbols_count": len(cache_data),
                "duration_seconds": duration
            }
            
        except Exception as e:
            error_msg = str(e)
            self._last_error = error_msg
            logger.exception("Failed to fetch and cache market data")
            
            # Update error status in DB
            def _save_error():
                db = SessionLocal()
                try:
                    self._update_fetcher_status(db, None, error_msg)
                finally:
                    db.close()
            
            await asyncio.to_thread(_save_error)
            
            return {
                "ok": False,
                "error": error_msg,
                "timestamp": int(time.time())
            }
    
    async def _process_payload_to_cache(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Process Binance payload into cache format"""
        symbols_meta = payload.get("symbols_meta") or []
        tickers = payload.get("tickers") or []
        book_tickers = payload.get("book_tickers") or []
        funding = payload.get("funding") or []
        oi_map = payload.get("oi_map") or {}
        klines_map = payload.get("klines_map") or {}
        
        ticker_by_symbol = {str(x.get("symbol")): x for x in tickers if isinstance(x, dict)}
        book_by_symbol = {str(x.get("symbol")): x for x in book_tickers if isinstance(x, dict)}
        funding_by_symbol = {str(x.get("symbol")): x for x in funding if isinstance(x, dict)}
        
        cache_data = []
        
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
            
            # Calculate spread
            if bid_price > 0 and ask_price > 0:
                spread_pct = ((ask_price - bid_price) / ((ask_price + bid_price) / 2.0)) * 100.0
            else:
                spread_pct = 100.0
            
            # Calculate ATR
            atr_pct = self.indicator_service.compute_atr_percent(klines_map.get(symbol) or [])
            
            funding_rate = float(fund.get("lastFundingRate") or 0.0)

            
            # Extract tick/step size
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
            
            # Store in cache format
            cache_data.append({
                'symbol': symbol,
                'exchange': 'binance',
                'price': price,
                'volume': quote_volume,
                'atr': atr_pct,
                'spread': max(spread_pct, 0.0),
                'funding_rate': funding_rate,
                'bid_price': bid_price,
                'ask_price': ask_price,
                'bid_qty': bid_qty,
                'ask_qty': ask_qty,
                'tick_size': tick_size,
                'step_size': step_size,
                'raw_data_json': '{}'  # Can store full data if needed
            })
        
        return cache_data
    
    def _update_fetcher_status(self, db, fetch_timestamp: int | None, error: str | None):
        """Update fetcher status in database"""
        from sqlalchemy import text
        try:
            if fetch_timestamp:
                db.execute(
                    text("UPDATE market_data_fetcher_status SET last_fetch_at=:ts, is_running=0, last_error=NULL WHERE id=1"),
                    {"ts": fetch_timestamp}
                )
            elif error:
                db.execute(
                    text("UPDATE market_data_fetcher_status SET is_running=0, last_error=:err WHERE id=1"),
                    {"err": error}
                )
            db.commit()
        except Exception as e:
            logger.error(f"Failed to update fetcher status: {e}")
    
    def set_fetch_interval(self, minutes: int):
        """Set fetch interval in minutes"""
        self._fetch_interval = max(1, minutes)
        logger.info(f"Fetch interval set to {self._fetch_interval} minutes")
    
    async def _schedule_loop(self):
        """Main scheduler loop"""
        logger.info(f"Market data fetcher started (interval: {self._fetch_interval} minutes)")
        
        while self._running:
            try:
                # Run fetch and cache
                await self.fetch_and_cache()
                
                # Cleanup old cache (keep last 1 hour)
                def _cleanup():
                    db = SessionLocal()
                    try:
                        self.cache_repository.cleanup_old_cache(db, hours_to_keep=1)
                    finally:
                        db.close()
                
                await asyncio.to_thread(_cleanup)
                
                # Sleep until next interval
                await asyncio.sleep(self._fetch_interval * 60)
                
            except asyncio.CancelledError:
                logger.info("Fetcher loop cancelled")
                break
            except Exception as e:
                logger.exception(f"Error in fetcher loop: {e}")
                # Sleep a bit before retrying
                await asyncio.sleep(60)
    
    def start(self, fetch_interval_minutes: int = 5):
        """Start the fetcher service"""
        if self._running:
            logger.warning("Fetcher already running")
            return
        
        self._running = True
        self._fetch_interval = fetch_interval_minutes
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info(f"Market data fetcher service started")
    
    def stop(self):
        """Stop the fetcher service"""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Market data fetcher service stopped")
    
    def status(self) -> dict[str, Any]:
        """Get fetcher status"""
        return {
            "running": self._running,
            "fetch_interval_minutes": self._fetch_interval,
            "last_fetch_at": self._last_fetch_at,
            "last_error": self._last_error
        }
