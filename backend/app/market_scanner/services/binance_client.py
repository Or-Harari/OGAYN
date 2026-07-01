from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Tuple

import requests

logger = logging.getLogger(__name__)


class BinanceFuturesClient:
    BASE_URL = "https://fapi.binance.com"

    def __init__(self, timeout_seconds: int = 12):
        self.timeout_seconds = timeout_seconds
        self._exchange_info_cache: dict[str, Any] | None = None
        self._exchange_info_ts = 0.0
        self._exchange_info_ttl = 60 * 60

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.BASE_URL}{path}"
        response = requests.get(url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    async def _get_json_async(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await asyncio.to_thread(self._get_json, path, params)

    async def get_exchange_info(self) -> dict[str, Any]:
        now = time.time()
        if self._exchange_info_cache and (now - self._exchange_info_ts) < self._exchange_info_ttl:
            return self._exchange_info_cache

        data = await self._get_json_async("/fapi/v1/exchangeInfo")
        self._exchange_info_cache = data
        self._exchange_info_ts = now
        return data

    async def get_markets_snapshot(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        tickers_task = self._get_json_async("/fapi/v1/ticker/24hr")
        book_ticker_task = self._get_json_async("/fapi/v1/ticker/bookTicker")
        funding_task = self._get_json_async("/fapi/v1/premiumIndex")
        tickers, book_tickers, funding = await asyncio.gather(tickers_task, book_ticker_task, funding_task)
        return tickers, book_tickers, funding

    async def get_klines_for_symbols(
        self,
        symbols: list[str],
        timeframe: str = "5m",
        limit: int = 80,
        concurrency: int = 12,
    ) -> dict[str, list[list[Any]]]:
        semaphore = asyncio.Semaphore(max(1, concurrency))
        out: dict[str, list[list[Any]]] = {}

        async def _fetch_one(symbol: str):
            async with semaphore:
                try:
                    payload = await self._get_json_async(
                        "/fapi/v1/klines",
                        {"symbol": symbol, "interval": timeframe, "limit": limit},
                    )
                    out[symbol] = payload if isinstance(payload, list) else []
                except Exception as exc:
                    logger.debug("Klines fetch failed for %s: %s", symbol, exc)
                    out[symbol] = []

        await asyncio.gather(*[_fetch_one(s) for s in symbols])
        return out

    async def get_klines_bulk(
        self,
        symbols: list[str],
        interval: str = "1h",
        limit: int = 14,
        concurrency: int = 20,
    ) -> dict[str, list[list[Any]]]:
        """Fetch klines for multiple symbols (alias for get_klines_for_symbols)"""
        return await self.get_klines_for_symbols(
            symbols=symbols,
            timeframe=interval,
            limit=limit,
            concurrency=concurrency
        )

    async def fetch_cycle_payload(self) -> Dict[str, Any]:
        exchange_info_task = self.get_exchange_info()
        tickers_task = self.get_markets_snapshot()

        exchange_info, (tickers, book_tickers, funding) = await asyncio.gather(exchange_info_task, tickers_task)

        symbols_meta = []
        for entry in exchange_info.get("symbols") or []:
            if entry.get("contractType") != "PERPETUAL":
                continue
            if entry.get("quoteAsset") != "USDT":
                continue
            if entry.get("status") != "TRADING":
                continue
            symbols_meta.append(entry)

        symbols = [s.get("symbol") for s in symbols_meta if isinstance(s.get("symbol"), str)]

        klines_task = self.get_klines_for_symbols(symbols)
        klines_map = await klines_task

        return {
            "exchange": "binance",
            "fetched_at": int(time.time()),
            "symbols_meta": symbols_meta,
            "tickers": tickers,
            "book_tickers": book_tickers,
            "funding": funding,
            "klines_map": klines_map,
        }
