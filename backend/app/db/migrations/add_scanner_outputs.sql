-- Migration: Add scanner_outputs table
-- Date: 2026-06-30
-- Description: Add scanner_outputs table to store current scanner output symbols
--              This table replaces the multiple JSON threshold files with a single DB table
--              that's used by the frontend, while bots use remote_pairlist.json

-- Create scanner_outputs table
CREATE TABLE IF NOT EXISTS scanner_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanner_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    generated_at INTEGER NOT NULL,
    symbol VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL DEFAULT 'binance',
    rank INTEGER NOT NULL,
    price FLOAT NOT NULL,
    volume FLOAT NOT NULL,
    atr FLOAT NOT NULL,
    spread FLOAT NOT NULL,
    funding FLOAT,
    total_score INTEGER NOT NULL,
    liquidity_score INTEGER NOT NULL DEFAULT 0,
    volatility_score INTEGER NOT NULL DEFAULT 0,
    spread_score INTEGER NOT NULL DEFAULT 0,
    funding_score INTEGER NOT NULL DEFAULT 0,
    tick_score INTEGER NOT NULL DEFAULT 0,
    reasons_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (scanner_id) REFERENCES scanner_configs(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_scanner_outputs_scanner_id ON scanner_outputs(scanner_id);
CREATE INDEX IF NOT EXISTS idx_scanner_outputs_user_id ON scanner_outputs(user_id);
CREATE INDEX IF NOT EXISTS idx_scanner_outputs_generated_at ON scanner_outputs(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_scanner_outputs_symbol ON scanner_outputs(symbol);
CREATE INDEX IF NOT EXISTS idx_scanner_outputs_total_score ON scanner_outputs(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_scanner_outputs_rank ON scanner_outputs(rank);

-- Create composite index for main query pattern (scanner + rank order)
CREATE INDEX IF NOT EXISTS idx_scanner_outputs_scanner_rank ON scanner_outputs(scanner_id, rank);
