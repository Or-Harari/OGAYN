# Multi-Scanner Architecture

## Overview

The market scanner system has been refactored from a single global scanner to a **user-based multi-scanner architecture**. Each user can now create and manage multiple scanner configurations with custom parameters, scoring weights, and output paths.

## Key Features

- ✅ **User-owned scanners**: Each user can have multiple scanners
- ✅ **Configurable scoring**: Custom weights and thresholds per scanner
- ✅ **Independent outputs**: Scanner-specific pairlist files and directories
- ✅ **Backward compatible**: Existing single-scanner setup still works
- ✅ **Multi-scanner runtime**: Run all enabled scanners in parallel
- ✅ **API endpoints**: Full CRUD for scanner management

## Architecture Changes

### Database

#### New Table: `scanner_configs`
```sql
scanner_configs (
    id, user_id, name, exchange, market_type, enabled,
    interval_minutes, config_json, output_base_path,
    created_at, updated_at
)
```

#### Updated Table: `market_snapshots`
Added fields for multi-user/scanner support:
- `scanner_id` (FK to scanner_configs)
- `user_id` (FK to users)

### Directory Structure

**Legacy (still supported):**
```
backend/data/pairlists/
  pairlist10.json
  pairlist20.json
  ...
```

**New multi-scanner structure:**
```
user_data/
  users/
    {userId}/
      scanners/
        {scannerName}/
          pairlists/
            top_pairs.json
            top_pairs.txt
            remote_pairlist.json
            pairlist10.json
            pairlist20.json
            ...
          snapshots/
          logs/
```

## Configuration

### Scanner Config Schema

```json
{
  "name": "binance-futures-main",
  "exchange": "binance",
  "market_type": "futures",
  "enabled": true,
  "interval_minutes": 5,
  "quote_asset": "USDT",
  "max_pairs": 30,
  "min_market_score": 70,
  "include_symbols": [],
  "exclude_symbols": ["BTCSTUSDT"],
  "scoring_weights": {
    "liquidity": 25,
    "volatility": 20,
    "spread": 30,
    "funding": 5,
    "tradeCount": 0,
    "recentActivity": 20
  },
  "scoring_thresholds": {
    "minQuoteVolume24h": 30000000,
    "excellentQuoteVolume24h": 500000000,
    "minAtrPct": 0.5,
    "idealAtrPctLow": 1.0,
    "idealAtrPctHigh": 3.0,
    "maxAtrPct": 6.0,
    "maxSpreadPct": 0.1
  },
  "recent_activity": {
    "enabled": true,
    "primaryWindow": "1h",
    "secondaryWindow": "4h",
    "use1d": true,
    "staleAfterSeconds": 180
  },
  "recent_activity_thresholds": {
    "minQuoteVolume1h": 1000000,
    "excellentQuoteVolume1h": 25000000,
    "minQuoteVolume4h": 5000000,
    "excellentQuoteVolume4h": 100000000,
    "minQuoteVolume1d": 20000000,
    "excellentQuoteVolume1d": 500000000,
    "minTrades1h": 500,
    "excellentTrades1h": 10000,
    "minTrades4h": 1500,
    "excellentTrades4h": 30000
  }
}
```

### Environment Variables

```bash
# Enable multi-scanner mode (default: true)
MULTI_SCANNER_ENABLED=true

# Scanner interval (applies to all scanners)
MARKET_SCANNER_INTERVAL_SECONDS=300

# Run scanner at startup
MARKET_SCANNER_RUN_AT_STARTUP=true

# Enable scanner
MARKET_SCANNER_ENABLED=true

# Pairlist format
PAIRLIST_FORMAT=slash  # "slash" (BTC/USDT) or "plain" (BTCUSDT)
```

## API Endpoints

### Scanner Management

#### List User Scanners
```http
GET /api/scanners/users/{userId}/scanners
Response: ScannerConfigResponse[]
```

#### Create Scanner
```http
POST /api/scanners/users/{userId}/scanners
Body: ScannerConfigCreate
Response: ScannerConfigResponse (201)
```

#### Get Scanner
```http
GET /api/scanners/users/{userId}/scanners/{scannerId}
Response: ScannerConfigResponse
```

#### Update Scanner
```http
PUT /api/scanners/users/{userId}/scanners/{scannerId}
Body: ScannerConfigUpdate
Response: ScannerConfigResponse
```

#### Delete Scanner
```http
DELETE /api/scanners/users/{userId}/scanners/{scannerId}
Response: 204 No Content
```

### Scanner Operations

#### Get Latest Results
```http
GET /api/scanners/users/{userId}/scanners/{scannerId}/results/latest
Query: ?limit=50&min_score=70
Response: { scanner_id, scanner_name, markets[] }
```

#### Get Pairlist
```http
GET /api/scanners/users/{userId}/scanners/{scannerId}/pairlist
Response: { pairs: string[], refresh_period: number }
```

#### Run Scanner Now
```http
POST /api/scanners/users/{userId}/scanners/{scannerId}/run
Response: { ok, scanner_id, scanner_name, symbols_processed, timestamp }
```

### Legacy Endpoints (Backward Compatibility)

```http
GET /api/scanners/status          # Get scanner runtime status
POST /api/scanners/run             # Run default scanner
POST /api/scanners/run-multi       # Run all enabled scanners
```

## Usage Examples

### 1. Create Scanner via API

```bash
curl -X POST http://localhost:8000/api/scanners/users/1/scanners \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "aggressive-scalper",
    "exchange": "binance",
    "market_type": "futures",
    "enabled": true,
    "interval_minutes": 5,
    "quote_asset": "USDT",
    "max_pairs": 20,
    "min_market_score": 80,
    "scoring_weights": {
      "liquidity": 40,
      "volatility": 30,
      "spread": 20,
      "openInterest": 5,
      "funding": 0,
      "tradeCount": 5
    }
  }'
```

### 2. Configure Freqtrade RemotePairList

```json
{
  "pairlists": [
    {
      "method": "RemotePairList",
      "pairlist_url": "http://localhost:8000/api/scanners/users/1/scanners/2/pairlist",
      "number_assets": 20,
      "refresh_period": 300
    }
  ]
}
```

### 3. Run Scanner Programmatically

```python
from backend.app.market_scanner.services import (
    MarketScannerService,
    PairlistService,
    ScannerConfigRepository
)
from backend.app.db.database import SessionLocal

# Load scanner config
db = SessionLocal()
repo = ScannerConfigRepository()
config_internal = repo.get_internal_config(db, scanner_id=2)

# Create scanner service
scanner = MarketScannerService(scanner_config=config_internal)

# Run scan
result = await scanner.run_cycle()

# Generate pairlists
pairlist_service = PairlistService(scanner_config=config_internal)
pairlist_summary = pairlist_service.generate_pairlists(db)

db.close()
```

## Migration

### Apply Migration

```bash
cd backend
python -m app.db.apply_migration
```

Or manually run:
```bash
sqlite3 backend/data/app.db < backend/app/db/migrations/add_scanner_configs.sql
```

### Default Scanner

The migration automatically creates a "default" scanner for user_id=1 with the previous hardcoded values:
- Exchange: binance
- Market type: futures
- Interval: 5 minutes
- Max pairs: 100
- Min score: 50
- Default scoring weights

All existing `market_snapshots` rows are assigned to this default scanner for continuity.

## Backward Compatibility

### Legacy Mode

Set `MULTI_SCANNER_ENABLED=false` to use single-scanner mode:
- Uses legacy `MarketScannerService()` without config
- Outputs to `backend/data/pairlists/`
- No scanner_id/user_id assignment

### Automatic Default Scanner

On first multi-scanner run, if no scanner configs exist, a default scanner is automatically created for user 1.

### Legacy API Endpoints

Old endpoints continue to work:
- `GET /api/markets/latest`
- `GET /api/markets/pairlists`
- `GET /api/markets/pairlists/{threshold}`
- `POST /api/markets/scan`

## Scoring Customization

### Configurable Judges

Each scanner can have custom scoring weights:

```json
{
  "scoring_weights": {
    "liquidity": 30,      // 0-100, weight for volume/depth
    "volatility": 20,     // 0-100, weight for ATR
    "spread": 20,         // 0-100, weight for bid-ask spread
    "openInterest": 10,   // 0-100, weight for OI (futures)
    "funding": 10,        // 0-100, weight for funding rate
    "tradeCount": 10      // 0-100, weight for tick size/activity
  }
}
```

### Configurable Thresholds

```json
{
  "scoring_thresholds": {
    "minQuoteVolume24h": 30000000,          // Minimum volume to consider
    "excellentQuoteVolume24h": 500000000,   // Volume for max liquidity score
    "minAtrPct": 0.5,                       // Minimum ATR %
    "idealAtrPctLow": 1.0,                  // Ideal ATR % (low bound)
    "idealAtrPctHigh": 3.0,                 // Ideal ATR % (high bound)
    "maxAtrPct": 6.0,                       // Maximum ATR %
    "maxSpreadPct": 0.1                     // Maximum acceptable spread %
  }
}
```

## Use Cases

### 1. Strategy-Specific Scanners

Create scanners optimized for different strategies:

- **Scalper Scanner**: High liquidity weight, tight spread, low volatility
- **Swing Trader Scanner**: Medium volatility, lower liquidity requirement
- **Breakout Scanner**: High volatility weight, high ATR thresholds

### 2. Multi-Exchange Scanners

Different scanners for different exchanges:

- `binance-futures-main`
- `binance-spot-stable`
- `bybit-futures-aggressive`

### 3. Risk-Profiled Scanners

Different risk profiles:

- **Conservative**: min_score=80, max_pairs=10, tight thresholds
- **Balanced**: min_score=70, max_pairs=30, moderate thresholds
- **Aggressive**: min_score=60, max_pairs=50, loose thresholds

## Testing

### Verify Multi-Scanner Setup

```bash
# 1. Create test user A scanner
curl -X POST http://localhost:8000/api/scanners/users/1/scanners \
  -d '{"name": "test-a", "max_pairs": 10, "min_market_score": 80}'

# 2. Create test user B scanner
curl -X POST http://localhost:8000/api/scanners/users/2/scanners \
  -d '{"name": "test-b", "max_pairs": 30, "min_market_score": 60}'

# 3. Run multi-scanner
curl -X POST http://localhost:8000/api/scanners/run-multi

# 4. Verify outputs
ls -la user_data/users/1/scanners/test-a/pairlists/
ls -la user_data/users/2/scanners/test-b/pairlists/

# 5. Check pairlist counts
curl http://localhost:8000/api/scanners/users/1/scanners/1/pairlist | jq '.pairs | length'
curl http://localhost:8000/api/scanners/users/2/scanners/2/pairlist | jq '.pairs | length'
```

## Troubleshooting

### Scanner Not Running

1. Check if enabled: `GET /api/scanners/users/{userId}/scanners/{scannerId}`
2. Check logs for errors
3. Verify `MARKET_SCANNER_ENABLED=true`
4. Verify `MULTI_SCANNER_ENABLED=true`

### No Pairlist Output

1. Run scanner manually: `POST /api/scanners/users/{userId}/scanners/{scannerId}/run`
2. Check output directory exists: `user_data/users/{userId}/scanners/{name}/pairlists/`
3. Check min_market_score isn't too high
4. Check if any markets meet criteria: `GET /api/scanners/users/{userId}/scanners/{scannerId}/results/latest`

### Permission Errors

- Ensure user_id in request matches current_user_id from JWT
- Scanner ownership is enforced (users can only access their own scanners)

## Performance Considerations

- Each scanner runs independently (parallel execution)
- Scanner interval is shared across all scanners
- Database queries are optimized with scanner_id index
- Pairlist generation happens after scan completes
- File I/O is atomic (temp file → rename)

## Security

- Scanner names must be filesystem-safe (alphanumeric, hyphens, underscores only)
- Output paths are computed server-side (no user input in paths)
- User isolation enforced at API level
- Scanner configs stored as JSON in database (no code injection)

## Future Enhancements

- [ ] Per-scanner interval configuration
- [ ] Scanner scheduling (cron-like syntax)
- [ ] Scanner performance metrics
- [ ] Scanner alerts/notifications
- [ ] Scanner templates/presets
- [ ] Scanner sharing between users
- [ ] Scanner versioning/history
