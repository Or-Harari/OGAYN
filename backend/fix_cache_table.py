"""Recreate market_data_cache table with correct schema"""
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "data" / "backend.db"
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("Dropping old market_data_cache table...")
cursor.execute("DROP TABLE IF EXISTS market_data_cache;")

print("Creating new market_data_cache table...")
cursor.execute("""
CREATE TABLE market_data_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetch_timestamp INTEGER NOT NULL,
    symbol VARCHAR NOT NULL,
    exchange VARCHAR DEFAULT 'binance',
    price FLOAT,
    volume FLOAT,
    atr FLOAT,
    spread FLOAT,
    funding_rate FLOAT,
    bid_price FLOAT,
    ask_price FLOAT,
    bid_qty FLOAT,
    ask_qty FLOAT,
    tick_size FLOAT,
    step_size FLOAT,
    raw_data_json TEXT
);
""")

conn.commit()
conn.close()

print("✓ Successfully recreated market_data_cache table")
print("  Columns: id, fetch_timestamp, symbol, exchange, price, volume, atr, spread,")
print("           funding_rate, bid_price, ask_price, bid_qty, ask_qty, tick_size,")
print("           step_size, raw_data_json")
print("  No open_interest column!")
