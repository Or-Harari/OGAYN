"""
Market Data Cache Repository
Handles reading/writing market data cache
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy import desc, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class MarketCacheRepository:
    """Repository for market data cache operations"""
    
    def save_cache(self, db: Session, cache_data: list[dict[str, Any]]) -> int:
        """Save market data to cache. Returns fetch_timestamp."""
        if not cache_data:
            return 0
        
        fetch_timestamp = int(time.time())
        
        try:
            # Bulk insert cache rows using text SQL
            insert_sql = text("""
                INSERT INTO market_data_cache 
                (fetch_timestamp, symbol, exchange, price, volume, atr, spread, 
                 funding_rate, bid_price, ask_price, bid_qty, ask_qty,
                 tick_size, step_size, raw_data_json)
                VALUES (:fetch_timestamp, :symbol, :exchange, :price, :volume, :atr, :spread, 
                        :funding_rate, :bid_price, :ask_price, :bid_qty, :ask_qty,
                        :tick_size, :step_size, :raw_data_json)
            """)
            
            rows = []
            for data in cache_data:
                rows.append({
                    'fetch_timestamp': fetch_timestamp,
                    'symbol': data['symbol'],
                    'exchange': data.get('exchange', 'binance'),
                    'price': data['price'],
                    'volume': data['volume'],
                    'atr': data['atr'],
                    'spread': data['spread'],
                    'funding_rate': data['funding_rate'],
                    'bid_price': data['bid_price'],
                    'ask_price': data['ask_price'],
                    'bid_qty': data['bid_qty'],
                    'ask_qty': data['ask_qty'],
                    'tick_size': data['tick_size'],
                    'step_size': data['step_size'],
                    'raw_data_json': data.get('raw_data_json', '{}')
                })
            
            # Execute bulk insert
            for row in rows:
                db.execute(insert_sql, row)
            
            db.commit()
            logger.info(f"Cached {len(rows)} market data entries at timestamp {fetch_timestamp}")
            return fetch_timestamp
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save cache: {e}")
            raise
    
    def get_latest_cache(self, db: Session) -> tuple[int, list[dict[str, Any]]]:
        """
        Get the most recent cache entry.
        Returns (fetch_timestamp, list of market data)
        """
        # Get latest timestamp
        result = db.execute(
            text("SELECT MAX(fetch_timestamp) FROM market_data_cache")
        ).fetchone()
        
        if not result or not result[0]:
            return 0, []
        
        latest_timestamp = result[0]
        
        # Get all data for that timestamp
        rows = db.execute(text("""
            SELECT symbol, exchange, price, volume, atr, spread,
                   funding_rate, bid_price, ask_price, bid_qty, ask_qty,
                   tick_size, step_size, raw_data_json
            FROM market_data_cache
            WHERE fetch_timestamp = :timestamp
        """), {"timestamp": latest_timestamp}).fetchall()
        
        cache_data = []
        for row in rows:
            raw_data_json = row[13]
            raw_data = {}
            if raw_data_json:
                try:
                    raw_data = json.loads(raw_data_json)
                except Exception:
                    raw_data = {}
            cache_data.append({
                'symbol': row[0],
                'exchange': row[1],
                'price': row[2],
                'volume': row[3],
                'atr': row[4],
                'spread': row[5],
                'funding_rate': row[6],
                'bid_price': row[7],
                'ask_price': row[8],
                'bid_qty': row[9],
                'ask_qty': row[10],
                'tick_size': row[11],
                'step_size': row[12],
                'raw_data_json': raw_data_json,
                'raw_data': raw_data,
            })
        
        return latest_timestamp, cache_data
    
    def cleanup_old_cache(self, db: Session, hours_to_keep: int = 1) -> int:
        """Delete cache entries older than specified hours. Returns count deleted."""
        cutoff = int(time.time()) - (hours_to_keep * 3600)
        
        try:
            result = db.execute(
                text("DELETE FROM market_data_cache WHERE fetch_timestamp < :cutoff"),
                {"cutoff": cutoff}
            )
            deleted = result.rowcount
            db.commit()
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old cache entries")
            
            return deleted
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to cleanup cache: {e}")
            return 0
    
    def get_cache_status(self, db: Session) -> dict[str, Any]:
        """Get cache statistics"""
        # Get total entries
        total = db.execute(text("SELECT COUNT(*) FROM market_data_cache")).fetchone()[0]
        
        # Get latest timestamp
        latest = db.execute(text("SELECT MAX(fetch_timestamp) FROM market_data_cache")).fetchone()[0]
        
        # Get unique timestamps (number of cache snapshots)
        snapshots = db.execute(
            text("SELECT COUNT(DISTINCT fetch_timestamp) FROM market_data_cache")
        ).fetchone()[0]
        
        return {
            'total_entries': total,
            'latest_timestamp': latest,
            'cache_snapshots': snapshots,
            'age_seconds': int(time.time() - latest) if latest else None
        }
