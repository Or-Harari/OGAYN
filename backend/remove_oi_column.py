"""
Script to remove oi_score and open_interest columns from database tables.
"""
import sqlite3
import sys
from pathlib import Path

# Database path
db_path = Path(__file__).parent / "data" / "backend.db"

if not db_path.exists():
    print(f"ERROR: Database not found at {db_path}")
    sys.exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("=== Current market_snapshots schema ===")
cursor.execute("PRAGMA table_info(market_snapshots);")
for row in cursor.fetchall():
    print(row)

print("\n=== Current market_data_cache schema ===")
cursor.execute("PRAGMA table_info(market_data_cache);")
for row in cursor.fetchall():
    print(row)

print("\n=== Removing oi_score and open_interest columns ===")

# SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
# For market_snapshots - remove oi_score
cursor.execute("""
CREATE TABLE IF NOT EXISTS market_snapshots_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    scanner_id INTEGER,
    user_id INTEGER,
    price REAL,
    volume REAL,
    atr REAL,
    spread REAL,
    funding REAL,
    liquidity_score INTEGER,
    spread_score INTEGER,
    atr_score INTEGER,
    funding_score INTEGER,
    tick_score INTEGER,
    market_quality INTEGER,
    reasons_json TEXT,
    raw_data_json TEXT
);
""")

print("Created market_snapshots_new table")

# Copy data from old table to new
cursor.execute("""
INSERT INTO market_snapshots_new 
SELECT id, timestamp, exchange, symbol, COALESCE(scanner_id, -1), COALESCE(user_id, -1), price, volume, 
       atr, spread, funding, COALESCE(liquidity_score, 0), COALESCE(spread_score, 0), COALESCE(atr_score, 0), 
       COALESCE(funding_score, 0), COALESCE(tick_score, 0), COALESCE(market_quality, 0), 
       COALESCE(reasons_json, '{}'), COALESCE(raw_data_json, '{}')
FROM market_snapshots;
""")

print(f"Copied {cursor.rowcount} rows")

# Drop old table and rename new one
cursor.execute("DROP TABLE market_snapshots;")
cursor.execute("ALTER TABLE market_snapshots_new RENAME TO market_snapshots;")

# Recreate indexes
cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_scanner ON market_snapshots(scanner_id);")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_user ON market_snapshots(user_id);")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_symbol ON market_snapshots(symbol);")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_timestamp ON market_snapshots(timestamp);")

print("Recreated indexes")

# For market_data_cache - remove open_interest
cursor.execute("""
CREATE TABLE IF NOT EXISTS market_data_cache_new (
    symbol TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    price REAL,
    volume REAL,
    quote_volume REAL,
    bid_price REAL,
    bid_qty REAL,
    ask_price REAL,
    ask_qty REAL,
    atr REAL,
    spread REAL,
    funding_rate REAL,
    last_updated INTEGER NOT NULL
);
""")

print("Created market_data_cache_new table")

# Copy data
cursor.execute("""
INSERT INTO market_data_cache_new
SELECT symbol, COALESCE(fetch_timestamp, 0), price, volume, 0 as quote_volume, 
       bid_price, bid_qty, ask_price, ask_qty, atr, spread, 
       funding_rate, COALESCE(fetch_timestamp, 0) as last_updated
FROM market_data_cache;
""")

print(f"Copied {cursor.rowcount} rows from cache")

cursor.execute("DROP TABLE market_data_cache;")
cursor.execute("ALTER TABLE market_data_cache_new RENAME TO market_data_cache;")

print("Renamed table")

conn.commit()
conn.close()

print("\n=== COMPLETE ===")
print("Successfully removed oi_score and open_interest columns from both tables")
