"""
WebSocket Market Data Fetcher Service
Connects to Binance WebSocket streams for real-time market data.
Uses REST only for historical klines (ATR calculation).
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
import os
from typing import Any

import aiohttp
import certifi
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from .binance_client import BinanceFuturesClient
from .market_cache_repository import MarketCacheRepository

logger = logging.getLogger(__name__)


class WebSocketFetcherService:
    """
    WebSocket-based market data fetcher.
    Subscribes to Binance futures WebSocket streams for real-time updates.
    """
    
    def __init__(self, repository: MarketCacheRepository, binance_client: BinanceFuturesClient):
        self.repository = repository
        self.binance_client = binance_client

        # WebSocket endpoints - split by Binance routing (public vs market)
        self.futures_public_endpoint = "wss://fstream.binance.com/public/stream"
        self.futures_market_endpoint = "wss://fstream.binance.com/market/stream"
        self.spot_stream_endpoint = "wss://stream.binance.com:9443/stream"

        # Market-specific stream sets split by endpoint routing
        self.futures_public_streams = ["!bookTicker"]
        self.futures_market_streams = ["!ticker@arr", "!miniTicker@arr", "!markPrice@arr"]
        self.spot_base_streams = [
            "!bookTicker",
            "!ticker@arr",
            "!ticker_1h@arr",
            "!ticker_4h@arr",
            "!ticker_1d@arr",
        ]

        # Recent activity config (WebSocket-first, conservative futures subscription defaults)
        self.recent_activity_cfg = {
            "enabled": True,
            "windows": ["1h", "4h", "1d"],
            "sourcePreference": "websocket",
            "allowRestFallback": False,
            "futuresKlineTopN": int(os.getenv("RECENT_ACTIVITY_FUTURES_KLINE_TOP_N", "100")),
            "staleAfterSeconds": int(os.getenv("RECENT_ACTIVITY_STALE_AFTER_SECONDS", "180")),
            "futuresUniverseRefreshSeconds": int(os.getenv("RECENT_ACTIVITY_FUTURES_UNIVERSE_REFRESH_SECONDS", "600")),
            "futuresKlineChunkSize": int(os.getenv("RECENT_ACTIVITY_FUTURES_KLINE_CHUNK_SIZE", "120")),
        }

        # In-memory data aggregation by market_type
        self._book_data_futures: dict[str, dict] = {}
        self._ticker_data_futures: dict[str, dict] = {}
        self._funding_data_futures: dict[str, dict] = {}

        self._book_data_spot: dict[str, dict] = {}
        self._ticker_data_spot: dict[str, dict] = {}

        # symbol -> recent activity payload
        self._recent_activity_futures: dict[str, dict[str, Any]] = {}
        self._recent_activity_spot: dict[str, dict[str, Any]] = {}

        self._exchange_info: dict[str, Any] = {}
        
        # Control flags
        self._running = False
        self._futures_public_ws_task = None
        self._futures_market_ws_task = None
        self._spot_ws_task = None
        self._futures_kline_manager_task = None
        self._futures_kline_tasks: list[asyncio.Task] = []
        self._futures_kline_symbols: set[str] = set()
        self._futures_public_connected = 0
        self._futures_market_connected = 0
        self._spot_ws_connections = 0
        self._save_task = None
        self._last_save_time = 0
        self._save_interval = 60  # Save to database every 60 seconds
        
        # Status tracking
        self.status = {
            'connected': False,
            'last_message_time': 0,
            'message_count': 0,
            'reconnect_count': 0,
            'last_save_time': 0,
            'cached_symbols': 0,
        }
    
    async def start(self, save_interval_seconds: int = 60):
        """Start the WebSocket fetcher service"""
        if self._running:
            logger.warning("WebSocket fetcher already running")
            return
        
        self._running = True
        self._save_interval = save_interval_seconds
        
        print(f"[WebSocketFetcherService] Starting... (save interval: {save_interval_seconds}s)")
        logger.info(f"Starting WebSocket fetcher (save interval: {save_interval_seconds}s)")
        
        # Fetch exchange info once at startup (for tick sizes, lot sizes, etc.)
        print("[WebSocketFetcherService] Fetching exchange info...")
        await self._fetch_exchange_info()
        
        # Start market-specific WebSocket tasks
        print("[WebSocketFetcherService] Starting futures/spot WebSocket tasks...")
        self._futures_public_ws_task = asyncio.create_task(self._ws_loop_futures_public())
        self._futures_market_ws_task = asyncio.create_task(self._ws_loop_futures_market())
        self._spot_ws_task = asyncio.create_task(self._ws_loop_spot())
        self._futures_kline_manager_task = asyncio.create_task(self._futures_kline_manager_loop())
        
        # Start periodic save task
        print("[WebSocketFetcherService] Starting periodic save task...")
        self._save_task = asyncio.create_task(self._save_loop())
        
        print("[WebSocketFetcherService] Started successfully")
        logger.info("WebSocket fetcher started successfully")
    
    async def stop(self):
        """Stop the WebSocket fetcher service"""
        logger.info("Stopping WebSocket fetcher...")
        self._running = False
        
        if self._futures_public_ws_task:
            self._futures_public_ws_task.cancel()
            try:
                await self._futures_public_ws_task
            except asyncio.CancelledError:
                pass
        
        if self._futures_market_ws_task:
            self._futures_market_ws_task.cancel()
            try:
                await self._futures_market_ws_task
            except asyncio.CancelledError:
                pass

        if self._spot_ws_task:
            self._spot_ws_task.cancel()
            try:
                await self._spot_ws_task
            except asyncio.CancelledError:
                pass

        if self._futures_kline_manager_task:
            self._futures_kline_manager_task.cancel()
            try:
                await self._futures_kline_manager_task
            except asyncio.CancelledError:
                pass

        for task in self._futures_kline_tasks:
            task.cancel()
        self._futures_kline_tasks.clear()
        
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass
        
        self.status['connected'] = False
        logger.info("WebSocket fetcher stopped")
    
    async def _fetch_exchange_info(self):
        """Fetch exchange info once for tick sizes, lot sizes, etc."""
        try:
            exchange_info = await self.binance_client.get_exchange_info()
            
            # Index by symbol
            for symbol_info in exchange_info.get('symbols', []):
                symbol = symbol_info['symbol']
                self._exchange_info[symbol] = symbol_info
            
            logger.info(f"Fetched exchange info for {len(self._exchange_info)} symbols")
        except Exception as e:
            logger.error(f"Failed to fetch exchange info: {e}")
    
    async def _ws_loop_futures_public(self):
        """Futures public websocket loop (bookTicker) with reconnect backoff."""
        reconnect_delay = 1
        max_reconnect_delay = 60
        
        while self._running:
            try:
                await self._connect_and_listen_public()
                reconnect_delay = 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Futures public WebSocket error: {e}")
                self.status['reconnect_count'] += 1
                if self._running:
                    logger.info(f"Reconnecting public stream in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
    
    async def _ws_loop_futures_market(self):
        """Futures market websocket loop (ticker, markPrice) with reconnect backoff."""
        reconnect_delay = 1
        max_reconnect_delay = 60
        
        while self._running:
            try:
                await self._connect_and_listen_market()
                reconnect_delay = 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Futures market WebSocket error: {e}")
                self.status['reconnect_count'] += 1
                if self._running:
                    logger.info(f"Reconnecting market stream in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    async def _ws_loop_spot(self):
        """Spot base websocket loop with reconnect backoff."""
        reconnect_delay = 1
        max_reconnect_delay = 60

        while self._running:
            try:
                await self._connect_and_listen_spot()
                reconnect_delay = 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Spot websocket error: {e}")
                self.status['connected'] = False
                self.status['reconnect_count'] += 1
                if self._running:
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
    
    async def _connect_and_listen_public(self):
        """Connect to futures public websocket (bookTicker) and listen for messages."""
        stream_names = "/".join(self.futures_public_streams)
        url = f"{self.futures_public_endpoint}?streams={stream_names}"
        
        # DEBUG: Write subscription URL to file
        with open(r"c:\Users\user\dev\backend\ws_debug.txt", "w") as f:
            f.write(f"[PUBLIC_SUB] URL: {url}\n")
            f.write(f"[PUBLIC_SUB] streams: {stream_names}\n\n")
        
        logger.info(f"Connecting to Public WebSocket: {url}")
        
        try:
            # Create SSL context
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            
            # Use ThreadedResolver instead of AsyncResolver to work around DNS issues
            # This uses the system's DNS resolver instead of aiodns
            from aiohttp import ThreadedResolver
            resolver = ThreadedResolver()
            
            # Create connector with explicit SSL context and system DNS resolver
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                resolver=resolver,
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                use_dns_cache=True
            )
            
            print(f"[WebSocketFetcherService] Connecting to {url}...")
            
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.ws_connect(
                    url,
                    heartbeat=30,
                    timeout=aiohttp.ClientTimeout(total=None, connect=30, sock_read=None)
                ) as ws:
                    print(f"[WebSocketFetcherService] ✓ Public WebSocket connected!")
                    self._futures_public_connected = 1
                    self.status['connected'] = True
                    logger.info("Public WebSocket connected successfully")
                    
                    async for msg in ws:
                        if not self._running:
                            break
                        
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._process_message(msg.data, market_type="futures")
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"WebSocket error: {ws.exception()}")
                            break
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                            logger.warning("WebSocket closed")
                            break
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection error: {e}. Check firewall/network settings. Retrying...")
            raise
        except asyncio.TimeoutError as e:
            logger.error(f"Connection timeout: {e}. Retrying...")
            raise
        except Exception as e:
            logger.error(f"Public WebSocket connection failed: {e}. Type: {type(e).__name__}")
            raise
    
    async def _connect_and_listen_market(self):
        """Connect to futures market websocket (ticker, markPrice) and listen for messages."""
        stream_names = "/".join(self.futures_market_streams)
        url = f"{self.futures_market_endpoint}?streams={stream_names}"
        
        # DEBUG: Append market subscription URL to file
        with open(r"c:\Users\user\dev\backend\ws_debug.txt", "a") as f:
            f.write(f"[MARKET_SUB] URL: {url}\n")
            f.write(f"[MARKET_SUB] streams: {stream_names}\n\n")
        
        logger.info(f"Connecting to Market WebSocket: {url}")
        
        try:
            # Create SSL context
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            
            from aiohttp import ThreadedResolver
            resolver = ThreadedResolver()
            
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                resolver=resolver,
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                use_dns_cache=True
            )
            
            print(f"[WebSocketFetcherService] Connecting to Market stream {url}...")
            
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.ws_connect(
                    url,
                    heartbeat=30,
                    timeout=aiohttp.ClientTimeout(total=None, connect=30, sock_read=None)
                ) as ws:
                    print(f"[WebSocketFetcherService] ✓ Market WebSocket connected!")
                    self._futures_market_connected = 1
                    self.status['connected'] = True
                    logger.info("Market WebSocket connected successfully")
                    
                    async for msg in ws:
                        if not self._running:
                            break
                        
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._process_message(msg.data, market_type="futures")
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"Market WebSocket error: {ws.exception()}")
                            break
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                            logger.warning("Market WebSocket closed")
                            break
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Market connection error: {e}. Check firewall/network settings. Retrying...")
            raise
        except asyncio.TimeoutError as e:
            logger.error(f"Market connection timeout: {e}. Retrying...")
            raise
        except Exception as e:
            logger.error(f"Market WebSocket connection failed: {e}. Type: {type(e).__name__}")
            raise

    async def _connect_and_listen_spot(self):
        """Connect to spot base websocket and listen for messages."""
        stream_names = "/".join(self.spot_base_streams)
        url = f"{self.spot_stream_endpoint}?streams={stream_names}"

        logger.info(f"Connecting to Spot WebSocket: {url}")
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            from aiohttp import ThreadedResolver
            resolver = ThreadedResolver()
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                resolver=resolver,
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.ws_connect(
                    url,
                    heartbeat=30,
                    timeout=aiohttp.ClientTimeout(total=None, connect=30, sock_read=None),
                ) as ws:
                    self._spot_ws_connections = 1
                    async for msg in ws:
                        if not self._running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._process_message(msg.data, market_type="spot")
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"Spot WebSocket error: {ws.exception()}")
                            break
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                            logger.warning("Spot WebSocket closed")
                            break
        except Exception as e:
            logger.error(f"Spot WebSocket connection failed: {e}. Type: {type(e).__name__}")
            raise

    async def _futures_kline_manager_loop(self):
        """Manage futures kline subscriptions for a conservative top-N universe."""
        refresh_seconds = self.recent_activity_cfg["futuresUniverseRefreshSeconds"]
        while self._running:
            try:
                await self._refresh_futures_kline_subscriptions()
                await asyncio.sleep(refresh_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Futures kline manager error: {e}")
                await asyncio.sleep(30)

    async def _refresh_futures_kline_subscriptions(self):
        if not self.recent_activity_cfg.get("enabled", True):
            return

        top_symbols = self._select_futures_recent_activity_universe()
        desired = set(top_symbols)
        if desired == self._futures_kline_symbols:
            return

        # Recreate kline websocket tasks only when the universe changes.
        for task in self._futures_kline_tasks:
            task.cancel()
        self._futures_kline_tasks.clear()
        self._futures_kline_symbols = desired

        if not desired:
            return

        windows = self.recent_activity_cfg["windows"]
        stream_names = []
        for symbol in sorted(desired):
            symbol_l = symbol.lower()
            for w in windows:
                stream_names.append(f"{symbol_l}@kline_{w}")

        chunk_size = max(1, int(self.recent_activity_cfg["futuresKlineChunkSize"]))
        for i in range(0, len(stream_names), chunk_size):
            chunk = stream_names[i:i + chunk_size]
            task = asyncio.create_task(self._run_futures_kline_ws(chunk))
            self._futures_kline_tasks.append(task)

    async def _run_futures_kline_ws(self, stream_names: list[str]):
        url = f"{self.futures_market_endpoint}?streams={'/'.join(stream_names)}"
        reconnect_delay = 1
        max_reconnect_delay = 60

        while self._running:
            try:
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                from aiohttp import ThreadedResolver
                resolver = ThreadedResolver()
                connector = aiohttp.TCPConnector(
                    ssl=ssl_context,
                    resolver=resolver,
                    limit=100,
                    limit_per_host=30,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                )
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.ws_connect(
                        url,
                        heartbeat=30,
                        timeout=aiohttp.ClientTimeout(total=None, connect=30, sock_read=None),
                    ) as ws:
                        reconnect_delay = 1
                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._process_message(msg.data, market_type="futures")
                            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Futures kline websocket error: {e}")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    def _select_futures_recent_activity_universe(self) -> list[str]:
        """Choose futures symbols for kline windows using existing ws data only."""
        top_n = max(1, int(self.recent_activity_cfg["futuresKlineTopN"]))
        scored: list[tuple[float, str]] = []

        for symbol, ticker in self._ticker_data_futures.items():
            book = self._book_data_futures.get(symbol)
            if not book:
                continue
            bid = float(book.get("bid_price", 0) or 0)
            ask = float(book.get("ask_price", 0) or 0)
            if bid <= 0 or ask <= 0:
                continue
            mid = (bid + ask) / 2.0
            if mid <= 0:
                continue
            spread_pct = ((ask - bid) / mid) * 100.0
            if spread_pct > 1.0:
                continue
            qv = float(ticker.get("quote_volume", 0) or 0)
            if qv <= 0:
                continue
            scored.append((qv, symbol))

        scored.sort(reverse=True)
        return [symbol for _, symbol in scored[:top_n]]
    
    async def _process_message(self, data: str, market_type: str):
        """Process incoming WebSocket message"""
        try:
            msg = json.loads(data)
            stream = msg.get('stream', '')
            stream_lower = str(stream).lower()
            event_data = msg.get('data')
            
            if not event_data:
                return
            
            self.status['last_message_time'] = int(time.time())
            self.status['message_count'] += 1
            
            # Debug: Log first 50 stream names to file
            if self.status['message_count'] <= 50:
                data_type = type(event_data).__name__
                data_preview = ""
                if isinstance(event_data, list):
                    data_preview = f", len={len(event_data)}"
                    if len(event_data) > 0:
                        first_item_keys = list(event_data[0].keys())[:8] if isinstance(event_data[0], dict) else []
                        data_preview += f", first_item_keys={first_item_keys}"
                elif isinstance(event_data, dict):
                    data_preview = f", keys={list(event_data.keys())[:8]}"
                
                with open(r"c:\Users\user\dev\backend\ws_debug.txt", "a") as f:
                    f.write(f"[MSG #{self.status['message_count']}] stream='{stream}', type={data_type}{data_preview}\n")
                
                print(f"[DEBUG #{self.status['message_count']}] stream='{stream}', type={data_type}{data_preview}")
            
            # Route message to appropriate handler
            if stream_lower == '!bookticker' or stream_lower.startswith('!bookticker@'):
                await self._handle_book_ticker(event_data, market_type=market_type)
            elif stream_lower.startswith('!ticker@arr') or stream_lower.startswith('!miniticker@arr'):
                await self._handle_ticker_array(event_data, market_type=market_type)
            elif stream_lower.startswith('!markprice@arr') and market_type == 'futures':
                await self._handle_mark_price_array(event_data)
            elif market_type == 'spot' and stream_lower in ('!ticker_1h@arr', '!ticker_4h@arr', '!ticker_1d@arr'):
                window = stream_lower.split('_')[1].split('@')[0]
                await self._handle_recent_activity_array(event_data, market_type='spot', window=window, mode='rolling')
            elif '@kline_' in stream_lower and market_type == 'futures':
                await self._handle_futures_kline_event(event_data)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
    
    async def _handle_book_ticker(self, data: dict, market_type: str):
        """Handle best bid/ask updates (also used for price calculation)"""
        symbol = data.get('s')
        if not symbol:
            return

        target = self._book_data_futures if market_type == 'futures' else self._book_data_spot
        target[symbol] = {
            'symbol': symbol,
            'bid_price': float(data.get('b', 0)),
            'bid_qty': float(data.get('B', 0)),
            'ask_price': float(data.get('a', 0)),
            'ask_qty': float(data.get('A', 0)),
            'timestamp': data.get('T', int(time.time() * 1000))
        }

    async def _handle_ticker_array(self, data: Any, market_type: str):
        """Handle 24h ticker array updates (quote volume + last price)."""
        if isinstance(data, dict) and isinstance(data.get('data'), list):
            data = data.get('data')
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return

        target = self._ticker_data_futures if market_type == 'futures' else self._ticker_data_spot
        for item in data:
            if not isinstance(item, dict):
                continue
            symbol = item.get('s') or item.get('symbol')
            if not symbol:
                continue

            # After CM migration payloads may include merged UM/CM events with st discriminator.
            # Keep only UM rows in futures cache when the field is present.
            st = item.get('st')
            if market_type == 'futures' and st is not None:
                try:
                    if int(st) != 1:
                        continue
                except Exception:
                    pass

            last_price = item.get('c')
            if last_price is None:
                last_price = item.get('lastPrice')

            quote_volume = item.get('q')
            if quote_volume is None:
                quote_volume = item.get('quoteVolume')

            target[symbol] = {
                'symbol': symbol,
                'last_price': float(last_price or 0),
                'quote_volume': float(quote_volume or 0),
                'timestamp': int(item.get('E', int(time.time() * 1000))),
            }
            
            # DEBUG: Log first few ticker saves
            if len(target) <= 5:
                with open(r"c:\Users\user\dev\backend\ws_debug.txt", "a") as f:
                    f.write(f"[TICKER_SAVE] {symbol} -> price={last_price}, vol={quote_volume}, count={len(target)}\n")

    async def _handle_mark_price_array(self, data: Any):
        """Handle futures mark price stream for websocket funding updates."""
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return
        for item in data:
            if not isinstance(item, dict):
                continue
            symbol = item.get('s')
            if not symbol:
                continue
            self._funding_data_futures[symbol] = {
                'symbol': symbol,
                'funding_rate': float(item.get('r', 0) or 0),
                'timestamp': int(item.get('E', int(time.time() * 1000))),
            }

    def _ensure_recent_activity_payload(self, market_type: str, symbol: str, mode: str) -> dict[str, Any]:
        store = self._recent_activity_futures if market_type == 'futures' else self._recent_activity_spot
        if symbol not in store:
            store[symbol] = {
                'source': 'websocket',
                'mode': mode,
                'updated_at': int(time.time()),
                'stale_after_seconds': int(self.recent_activity_cfg['staleAfterSeconds']),
                'windows': {},
            }
        payload = store[symbol]
        payload['mode'] = mode
        payload['source'] = 'websocket'
        payload['stale_after_seconds'] = int(self.recent_activity_cfg['staleAfterSeconds'])
        return payload

    async def _handle_recent_activity_array(self, data: Any, market_type: str, window: str, mode: str):
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return
        now_ts = int(time.time())
        for item in data:
            if not isinstance(item, dict):
                continue
            symbol = item.get('s')
            if not symbol:
                continue
            payload = self._ensure_recent_activity_payload(market_type, symbol, mode)
            payload['updated_at'] = now_ts
            payload['windows'][window] = {
                'quote_volume': float(item.get('q', 0) or 0),
                'trade_count': int(item.get('n', 0) or 0),
                'updated_at': int(item.get('E', now_ts)),
                'stale': False,
            }

    async def _handle_futures_kline_event(self, data: Any):
        if not isinstance(data, dict):
            return
        kline = data.get('k') or {}
        symbol = kline.get('s') or data.get('s')
        interval = kline.get('i')
        if not symbol or not interval:
            return
        if interval not in self.recent_activity_cfg['windows']:
            return

        payload = self._ensure_recent_activity_payload('futures', symbol, 'candle')
        now_ts = int(time.time())
        payload['updated_at'] = now_ts
        payload['windows'][interval] = {
            'quote_volume': float(kline.get('q', 0) or 0),
            'trade_count': int(kline.get('n', 0) or 0),
            'updated_at': int(data.get('E', now_ts)),
            'stale': False,
            'closed': bool(kline.get('x', False)),
        }
    
    async def _save_loop(self):
        """Periodically save aggregated data to cache"""
        while self._running:
            try:
                await asyncio.sleep(self._save_interval)
                await self._save_to_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in save loop: {e}")
    
    async def _save_to_cache(self):
        """Save aggregated WebSocket data to cache"""
        if not self._book_data_futures and not self._book_data_spot:
            print(
                f"[WebSocketFetcherService] No book data to save "
                f"(futures={len(self._book_data_futures)}, spot={len(self._book_data_spot)})"
            )
            logger.warning("No book data to save")
            return
        
        try:
            # Fetch klines for ATR calculation (REST endpoint)
            # We need the last 14 candles for ATR
            klines_map = await self._fetch_klines_for_atr()
            
            # Build cache data
            cache_data = await self._build_cache_data(klines_map)
            
            if not cache_data:
                logger.warning("No cache data to save")
                return
            
            # Save to database
            def _save():
                db = SessionLocal()
                try:
                    self.repository.save_cache(db, cache_data)
                finally:
                    db.close()
            
            await asyncio.to_thread(_save)
            
            self.status['last_save_time'] = int(time.time())
            self.status['cached_symbols'] = len(cache_data)
            self._last_save_time = time.time()

            futures_rows = 0
            spot_rows = 0
            recent_1h = 0
            recent_4h = 0
            recent_1d = 0
            recent_stale = 0
            for row in cache_data:
                try:
                    raw = json.loads(row.get('raw_data_json', '{}'))
                except Exception:
                    raw = {}
                mt = raw.get('market_type')
                if mt == 'futures':
                    futures_rows += 1
                elif mt == 'spot':
                    spot_rows += 1
                ra = raw.get('recent_activity', {})
                windows = ra.get('windows', {}) if isinstance(ra, dict) else {}
                for w in ('1h', '4h', '1d'):
                    wv = windows.get(w, {}) if isinstance(windows, dict) else {}
                    if wv.get('quote_volume') is not None or wv.get('trade_count') is not None:
                        if w == '1h':
                            recent_1h += 1
                        elif w == '4h':
                            recent_4h += 1
                        elif w == '1d':
                            recent_1d += 1
                    if wv.get('stale') is True:
                        recent_stale += 1

            logger.info(f"Saved {len(cache_data)} symbols to cache")
            logger.info(
                "recent_activity_summary market_type=futures/spot futures_rows=%s spot_rows=%s "
                "recent_activity_symbols_1h=%s recent_activity_symbols_4h=%s recent_activity_symbols_1d=%s "
                "recent_activity_stale=%s kline_stream_symbols=%s ws_connections=%s rest_fallback_used=%s",
                futures_rows,
                spot_rows,
                recent_1h,
                recent_4h,
                recent_1d,
                recent_stale,
                len(self._futures_kline_symbols),
                self._futures_public_connected + self._futures_market_connected + self._spot_ws_connections + len(self._futures_kline_tasks),
                bool(self.recent_activity_cfg.get('allowRestFallback', False)),
            )
            
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    async def _fetch_klines_for_atr(self) -> dict[str, list]:
        """Fetch klines via REST for ATR calculation"""
        try:
            symbols = list(self._book_data_futures.keys())
            klines_map = await self.binance_client.get_klines_bulk(
                symbols=symbols,
                interval='1h',
                limit=14
            )
            return klines_map
        except Exception as e:
            logger.error(f"Failed to fetch klines: {e}")
            return {}
    
    async def _fetch_funding_rates(self) -> dict[str, float]:
        """Optional fallback funding fetch (disabled by default)."""
        if not self.recent_activity_cfg.get('allowRestFallback', False):
            return {}
        try:
            response = await self.binance_client._get_json_async('/fapi/v1/premiumIndex')
            funding_rates = {}
            if isinstance(response, list):
                for item in response:
                    symbol = item.get('symbol')
                    if symbol:
                        funding_rates[symbol] = float(item.get('lastFundingRate', 0))
            return funding_rates
        except Exception as e:
            logger.error(f"Failed to fetch funding rates fallback: {e}")
            return {}
    
    async def _build_cache_data(self, klines_map: dict[str, list]) -> list[dict[str, Any]]:
        """Build cache data from aggregated WebSocket data"""
        cache_data: list[dict[str, Any]] = []
        funding_fallback = await self._fetch_funding_rates()
        now_ts = int(time.time())
        stale_after = int(self.recent_activity_cfg['staleAfterSeconds'])
        
        # DEBUG: Log in-memory data counts
        with open(r"c:\Users\user\dev\backend\ws_debug.txt", "a") as f:
            f.write(f"\n[BUILD_CACHE_START] book_count={len(self._book_data_futures)}, ticker_count={len(self._ticker_data_futures)}\n")

        def _materialize_recent_activity(store: dict[str, dict[str, Any]], symbol: str, mode: str) -> dict[str, Any]:
            payload = store.get(symbol) or {
                'source': 'websocket',
                'mode': mode,
                'updated_at': None,
                'stale_after_seconds': stale_after,
                'windows': {},
            }
            windows: dict[str, Any] = {}
            for w in self.recent_activity_cfg['windows']:
                w_payload = payload.get('windows', {}).get(w) or {}
                updated = w_payload.get('updated_at')
                stale = True
                if isinstance(updated, (int, float)):
                    stale = (now_ts - int(updated)) > stale_after
                windows[w] = {
                    'quote_volume': w_payload.get('quote_volume'),
                    'trade_count': w_payload.get('trade_count'),
                    'updated_at': updated,
                    'stale': stale,
                }
            return {
                'source': payload.get('source', 'websocket'),
                'mode': mode,
                'updated_at': payload.get('updated_at'),
                'stale_after_seconds': stale_after,
                'windows': windows,
            }

        # Futures rows
        for symbol, book in self._book_data_futures.items():
            ticker = self._ticker_data_futures.get(symbol, {})
            exchange = self._exchange_info.get(symbol, {})
            klines = klines_map.get(symbol, [])
            atr = self._calculate_atr(klines)

            bid = float(book.get('bid_price', 0) or 0)
            ask = float(book.get('ask_price', 0) or 0)
            mid_price = (bid + ask) / 2 if (bid > 0 and ask > 0) else 0
            ticker_price = float(ticker.get('last_price', 0.0) or 0.0)
            price = mid_price if mid_price > 0 else ticker_price

            spread = 0.0
            if bid > 0 and ask > 0 and price > 0:
                spread = ((ask - bid) / price) * 100.0

            quote_volume = float(ticker.get('quote_volume', 0.0) or 0.0)
            
            # DEBUG: Log ticker state for first few symbols during cache build
            if len(cache_data) < 3:
                with open(r"c:\Users\user\dev\backend\ws_debug.txt", "a") as f:
                    f.write(f"[CACHE_BUILD] {symbol} -> ticker_keys={list(ticker.keys())}, quote_vol={quote_volume}\n")
            
            funding_ws = self._funding_data_futures.get(symbol, {})
            funding_rate = float(funding_ws.get('funding_rate', funding_fallback.get(symbol, 0.0)) or 0.0)

            tick_size = 0.0
            step_size = 0.0
            if exchange:
                for filter_info in exchange.get('filters', []):
                    if filter_info['filterType'] == 'PRICE_FILTER':
                        tick_size = float(filter_info.get('tickSize', 0) or 0)
                    elif filter_info['filterType'] == 'LOT_SIZE':
                        step_size = float(filter_info.get('stepSize', 0) or 0)

            recent_activity = _materialize_recent_activity(self._recent_activity_futures, symbol, mode='candle')

            cache_data.append({
                'symbol': symbol,
                'exchange': 'binance',
                'price': price,
                'volume': quote_volume,
                'atr': atr,
                'spread': spread,
                'funding_rate': funding_rate,
                'bid_price': bid,
                'ask_price': ask,
                'bid_qty': float(book.get('bid_qty', 0) or 0),
                'ask_qty': float(book.get('ask_qty', 0) or 0),
                'tick_size': tick_size,
                'step_size': step_size,
                'raw_data_json': json.dumps({
                    'market_type': 'futures',
                    'book': book,
                    'ticker': ticker,
                    'funding_ws': funding_ws,
                    'recent_activity': recent_activity,
                })
            })

        # Spot rows
        for symbol, book in self._book_data_spot.items():
            ticker = self._ticker_data_spot.get(symbol, {})
            bid = float(book.get('bid_price', 0) or 0)
            ask = float(book.get('ask_price', 0) or 0)
            mid_price = (bid + ask) / 2 if (bid > 0 and ask > 0) else 0
            ticker_price = float(ticker.get('last_price', 0.0) or 0.0)
            price = mid_price if mid_price > 0 else ticker_price

            spread = 0.0
            if bid > 0 and ask > 0 and price > 0:
                spread = ((ask - bid) / price) * 100.0

            quote_volume = float(ticker.get('quote_volume', 0.0) or 0.0)
            recent_activity = _materialize_recent_activity(self._recent_activity_spot, symbol, mode='rolling')

            cache_data.append({
                'symbol': symbol,
                'exchange': 'binance',
                'price': price,
                'volume': quote_volume,
                'atr': 0.0,
                'spread': spread,
                'funding_rate': 0.0,
                'bid_price': bid,
                'ask_price': ask,
                'bid_qty': float(book.get('bid_qty', 0) or 0),
                'ask_qty': float(book.get('ask_qty', 0) or 0),
                'tick_size': 0.0,
                'step_size': 0.0,
                'raw_data_json': json.dumps({
                    'market_type': 'spot',
                    'book': book,
                    'ticker': ticker,
                    'recent_activity': recent_activity,
                })
            })

        return cache_data
    
    def _calculate_atr(self, klines: list) -> float:
        """Calculate ATR from klines (Average True Range)"""
        if len(klines) < 2:
            return 0.0
        
        try:
            true_ranges = []
            for i in range(1, len(klines)):
                high = float(klines[i][2])
                low = float(klines[i][3])
                prev_close = float(klines[i-1][4])
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
            
            if not true_ranges:
                return 0.0
            
            atr = sum(true_ranges) / len(true_ranges)
            
            # Convert to percentage of current price
            current_price = float(klines[-1][4])
            if current_price > 0:
                return (atr / current_price) * 100
            
            return 0.0
        except (IndexError, ValueError, ZeroDivisionError) as e:
            logger.error(f"ATR calculation error: {e}")
            return 0.0
    
    def get_status(self) -> dict[str, Any]:
        """Get current service status"""
        return {
            'running': self._running,
            'connected': self.status['connected'],
            'last_message_time': self.status['last_message_time'],
            'message_count': self.status['message_count'],
            'reconnect_count': self.status['reconnect_count'],
            'last_save_time': self.status['last_save_time'],
            'cached_symbols': self.status['cached_symbols'],
            'save_interval': self._save_interval,
            'in_memory_symbols': len(self._book_data_futures) + len(self._book_data_spot),
            'in_memory_tickers': len(self._ticker_data_futures) + len(self._ticker_data_spot),
            'futures_symbols': len(self._book_data_futures),
            'spot_symbols': len(self._book_data_spot),
            'kline_stream_symbols': len(self._futures_kline_symbols),
            'ws_connections': self._futures_public_connected + self._futures_market_connected + self._spot_ws_connections + len(self._futures_kline_tasks),
            'recent_activity': self.recent_activity_cfg,
        }
