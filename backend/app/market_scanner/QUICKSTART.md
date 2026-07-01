# Multi-Scanner Refactor - Quick Start Guide

## What Changed

The market scanner system has been refactored from a **single global scanner** to a **user-based multi-scanner architecture**. Each user can now create multiple scanners with custom configurations.

## Quick Setup

### 1. Apply Migration

```bash
cd backend
python -m app.db.apply_migration
```

This creates:
- `scanner_configs` table
- Adds `scanner_id` and `user_id` to `market_snapshots`
- Creates a default scanner for backward compatibility

### 2. Configure Environment

```bash
# Enable multi-scanner mode
MULTI_SCANNER_ENABLED=true

# Scanner runs every 5 minutes
MARKET_SCANNER_INTERVAL_SECONDS=300

# Enable scanner
MARKET_SCANNER_ENABLED=true
```

### 3. Start Backend

```bash
cd backend
python -m uvicorn app.main:app --reload
```

The scanner runtime will:
- Automatically create a default scanner if none exists
- Run all enabled scanners every interval
- Generate pairlists for each scanner

## Usage Examples

### Create Scanner via API

```bash
curl -X POST http://localhost:8000/api/scanners/users/1/scanners \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-scanner",
    "exchange": "binance",
    "market_type": "futures",
    "enabled": true,
    "quote_asset": "USDT",
    "max_pairs": 30,
    "min_market_score": 70
  }'
```

### List User Scanners

```bash
curl http://localhost:8000/api/scanners/users/1/scanners \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Get Scanner Pairlist (for Freqtrade)

```bash
curl http://localhost:8000/api/scanners/users/1/scanners/1/pairlist
```

### Configure Freqtrade

```json
{
  "pairlists": [
    {
      "method": "RemotePairList",
      "pairlist_url": "http://localhost:8000/api/scanners/users/1/scanners/1/pairlist",
      "number_assets": 30,
      "refresh_period": 300
    }
  ]
}
```

## Testing

Run the test script to verify functionality:

```bash
cd backend
python -m app.market_scanner.test_multi_scanner
```

This will:
1. Create two test scanners (aggressive and conservative)
2. Run scans for both
3. Generate pairlists
4. Verify outputs and database records
5. Compare results

## File Structure

Scanner outputs are now user/scanner-specific:

```
user_data/
  users/
    1/
      scanners/
        my-scanner/
          pairlists/
            top_pairs.json         # Top N pairs
            top_pairs.txt          # Plain text list
            remote_pairlist.json   # Freqtrade compatible
            pairlist10.json        # Score >= 10
            pairlist20.json        # Score >= 20
            ...
```

## Key Features

✅ **Multiple Scanners**: Each user can have unlimited scanners  
✅ **Custom Scoring**: Configure weights and thresholds per scanner  
✅ **Independent Outputs**: Each scanner has its own output directory  
✅ **Backward Compatible**: Default scanner preserves existing behavior  
✅ **User Isolation**: Users can only access their own scanners  
✅ **API-Driven**: Full CRUD operations via REST API  

## Customization

### Scoring Weights

```json
{
  "scoring_weights": {
    "liquidity": 30,
    "volatility": 20,
    "spread": 20,
    "openInterest": 10,
    "funding": 10,
    "tradeCount": 10
  }
}
```

### Thresholds

```json
{
  "scoring_thresholds": {
    "minQuoteVolume24h": 30000000,
    "excellentQuoteVolume24h": 500000000,
    "minAtrPct": 0.5,
    "idealAtrPctLow": 1.0,
    "idealAtrPctHigh": 3.0,
    "maxAtrPct": 6.0,
    "maxSpreadPct": 0.1
  }
}
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scanners/users/{userId}/scanners` | List scanners |
| POST | `/api/scanners/users/{userId}/scanners` | Create scanner |
| GET | `/api/scanners/users/{userId}/scanners/{id}` | Get scanner |
| PUT | `/api/scanners/users/{userId}/scanners/{id}` | Update scanner |
| DELETE | `/api/scanners/users/{userId}/scanners/{id}` | Delete scanner |
| GET | `/api/scanners/users/{userId}/scanners/{id}/results/latest` | Latest results |
| GET | `/api/scanners/users/{userId}/scanners/{id}/pairlist` | Get pairlist |
| POST | `/api/scanners/users/{userId}/scanners/{id}/run` | Run scanner now |

## Troubleshooting

### Scanner Not Running
- Check `MARKET_SCANNER_ENABLED=true`
- Check `MULTI_SCANNER_ENABLED=true`
- Verify scanner is enabled: `enabled: true`

### No Output Files
- Run scanner manually: `POST /api/scanners/users/{userId}/scanners/{id}/run`
- Check min_market_score isn't too high
- Check output directory permissions

### Empty Pairlists
- Lower `min_market_score` threshold
- Increase `max_pairs` limit
- Check market conditions (might not have enough qualified pairs)

## Documentation

- **Architecture**: [MULTI_SCANNER_ARCHITECTURE.md](./MULTI_SCANNER_ARCHITECTURE.md)
- **API Docs**: http://localhost:8000/docs
- **Test Script**: [test_multi_scanner.py](./test_multi_scanner.py)
- **Migration**: [migrations/add_scanner_configs.sql](../db/migrations/add_scanner_configs.sql)

## Next Steps

1. Apply migration
2. Create your first custom scanner
3. Configure Freqtrade to use scanner pairlist
4. Monitor scanner performance
5. Tune scoring weights for your strategy

For detailed information, see [MULTI_SCANNER_ARCHITECTURE.md](./MULTI_SCANNER_ARCHITECTURE.md).
