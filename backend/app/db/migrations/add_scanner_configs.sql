-- Migration: Add multi-scanner support
-- Date: 2026-06-29
-- Description: Add scanner_configs table and update market_snapshots for multi-user scanner support

-- Create scanner_configs table
CREATE TABLE IF NOT EXISTS scanner_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL DEFAULT 'binance',
    market_type VARCHAR NOT NULL DEFAULT 'futures',
    enabled BOOLEAN NOT NULL DEFAULT 1,
    interval_minutes INTEGER NOT NULL DEFAULT 5,
    config_json TEXT NOT NULL DEFAULT '{}',
    output_base_path VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_scanner_configs_user_id ON scanner_configs(user_id);
CREATE INDEX IF NOT EXISTS idx_scanner_configs_name ON scanner_configs(name);
CREATE INDEX IF NOT EXISTS idx_scanner_configs_enabled ON scanner_configs(enabled);

-- Add scanner_id and user_id to market_snapshots (nullable for backward compatibility)
ALTER TABLE market_snapshots ADD COLUMN scanner_id INTEGER;
ALTER TABLE market_snapshots ADD COLUMN user_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_market_snapshots_scanner_id ON market_snapshots(scanner_id);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_user_id ON market_snapshots(user_id);

-- Insert default scanner config for existing data (assumes user_id=1 exists)
-- This provides backward compatibility
INSERT INTO scanner_configs (user_id, name, exchange, market_type, enabled, interval_minutes, config_json, output_base_path)
SELECT 1, 'default', 'binance', 'futures', 1, 5, 
    json_object(
        'quoteAsset', 'USDT',
        'maxPairs', 100,
        'minMarketScore', 50,
        'includeSymbols', json('[]'),
        'excludeSymbols', json('[]'),
        'scoringWeights', json_object(
            'liquidity', 30,
            'volatility', 20,
            'spread', 20,
            'openInterest', 10,
            'funding', 10,
            'tradeCount', 10
        ),
        'scoringThresholds', json_object(
            'minQuoteVolume24h', 30000000,
            'excellentQuoteVolume24h', 500000000,
            'minAtrPct', 0.5,
            'idealAtrPctLow', 1.0,
            'idealAtrPctHigh', 3.0,
            'maxAtrPct', 6.0,
            'maxSpreadPct', 0.1
        )
    ),
    'user_data/users/1/scanners/default'
WHERE EXISTS (SELECT 1 FROM users WHERE id = 1)
AND NOT EXISTS (SELECT 1 FROM scanner_configs WHERE user_id = 1 AND name = 'default');

-- Update existing market_snapshots to reference default scanner
UPDATE market_snapshots 
SET scanner_id = (SELECT id FROM scanner_configs WHERE user_id = 1 AND name = 'default' LIMIT 1),
    user_id = 1
WHERE scanner_id IS NULL 
AND EXISTS (SELECT 1 FROM scanner_configs WHERE user_id = 1 AND name = 'default');
