-- Migration: Add market data cache for shared market data
-- Date: 2026-06-29
-- Description: Decouple market data fetching from scanner execution

-- Create market_data_cache table for shared market snapshots
CREATE TABLE IF NOT EXISTS market_data_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetch_timestamp INTEGER NOT NULL,
    symbol VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL DEFAULT 'binance',
    price FLOAT,
    volume FLOAT,
    atr FLOAT,
    spread FLOAT,
    open_interest FLOAT,
    funding_rate FLOAT,
    bid_price FLOAT,
    ask_price FLOAT,
    bid_qty FLOAT,
    ask_qty FLOAT,
    tick_size FLOAT,
    step_size FLOAT,
    raw_data_json TEXT
);

-- Indexes for fast lookups (create after table)
CREATE INDEX IF NOT EXISTS idx_cache_timestamp ON market_data_cache(fetch_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_cache_symbol_timestamp ON market_data_cache(symbol, fetch_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_cache_exchange ON market_data_cache(exchange, fetch_timestamp DESC);

-- Add last_run_at to scanner_configs
-- Note: SQLite doesn't support ADD COLUMN IF NOT EXISTS, so check first
-- Using a dummy update to check if column exists
-- If error: column does not exist, we add it


-- Create fetcher status table
CREATE TABLE IF NOT EXISTS market_data_fetcher_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_fetch_at INTEGER,
    fetch_interval INTEGER DEFAULT 5,
    is_running BOOLEAN DEFAULT 0,
    last_error TEXT
);

-- Insert default fetcher status
INSERT OR IGNORE INTO market_data_fetcher_status (id, fetch_interval) VALUES (1, 5);
