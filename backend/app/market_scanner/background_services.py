"""
Background Services Singleton
Global instances of background services for the application
"""
from .services.binance_client import BinanceFuturesClient
from .services.market_cache_repository import MarketCacheRepository
from .services.market_data_fetcher_service import MarketDataFetcherService
from .services.websocket_fetcher_service import WebSocketFetcherService
from .services.scanner_scheduler_service import ScannerSchedulerService

# Initialize clients and repositories
binance_client = BinanceFuturesClient()
cache_repository = MarketCacheRepository()

# Global singleton instances
# REST-based fetcher (legacy, can be used as fallback)
market_data_fetcher = MarketDataFetcherService(cache_repository, binance_client)

# WebSocket-based fetcher (primary, real-time updates)
websocket_fetcher = WebSocketFetcherService(cache_repository, binance_client)

# Scanner scheduler
scanner_scheduler = ScannerSchedulerService()
