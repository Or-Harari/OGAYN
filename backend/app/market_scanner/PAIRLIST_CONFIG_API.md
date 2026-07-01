# Pairlist Configuration API Reference

## Overview

The Pairlist Configuration API allows you to configure Freqtrade pairlist handlers directly from the backend, supporting both user-level and bot-specific configurations.

## Supported Pairlist Handlers

### 1. RemotePairList

Fetches pairlist from a remote URL or local file.

```json
{
  "method": "RemotePairList",
  "mode": "whitelist",              // or "blacklist"
  "processing_mode": "filter",       // or "append"
  "pairlist_url": "http://example.com/pairlist",
  "number_assets": 50,               // optional, whitelist mode only
  "refresh_period": 1800,
  "keep_pairlist_on_failure": true,
  "read_timeout": 60,
  "bearer_token": "optional-token",  // OPTIONAL
  "save_to_file": "path/to/file.json" // optional
}
```

**Key Parameters:**
- `bearer_token`: **OPTIONAL** - Only needed if your endpoint requires authentication
- `mode`: whitelist (include pairs) or blacklist (exclude pairs)
- `processing_mode`: filter (intersect with existing) or append (add to existing)

### 2. StaticPairList

Uses a static predefined list of pairs.

```json
{
  "method": "StaticPairList",
  "allow_inactive": false  // Allow inactive markets (for backtesting)
}
```

Uses `pair_whitelist` from the exchange config.

### 3. VolumePairList

Filters and sorts pairs by trading volume.

```json
{
  "method": "VolumePairList",
  "number_assets": 20,
  "sort_key": "quoteVolume",
  "min_value": 0,              // Minimum volume threshold
  "max_value": null,           // Maximum volume threshold (optional)
  "refresh_period": 1800,
  
  // Advanced mode (optional)
  "lookback_days": 7,          // Use 7 days of 1d candles
  // OR
  "lookback_timeframe": "1h",
  "lookback_period": 72        // 72 hours of 1h candles
}
```

### 4. PercentChangePairList

Filters pairs by percentage price change.

```json
{
  "method": "PercentChangePairList",
  "number_assets": 15,
  "sort_key": "percentage",
  "sort_direction": "desc",    // "asc" or "desc"
  "min_value": -10,            // Minimum % change
  "max_value": 50,             // Maximum % change
  "refresh_period": 1800,
  
  // Advanced mode (optional)
  "lookback_days": 1,          // Last 24 hours
  // OR
  "lookback_timeframe": "1h",
  "lookback_period": 24
}
```

### 5. MarketCapPairList

Filters pairs by CoinGecko market cap ranking.

```json
{
  "method": "MarketCapPairList",
  "number_assets": 20,
  "max_rank": 50,              // Max market cap rank (recommended <= 250)
  "refresh_period": 86400,     // Default 1 day
  "mode": "whitelist",         // or "blacklist"
  "categories": ["layer-1", "defi"]  // CoinGecko categories
}
```

## API Endpoints

### Authentication

All endpoints require JWT authentication:

```http
Authorization: Bearer YOUR_JWT_TOKEN
```

Get token:
```bash
curl -X POST http://127.0.0.1:8000/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_user&password=your_pass"
```

### 1. Get User-Level Configuration

**GET** `/api/config/pairlist/user`

Returns the user's default pairlist configuration.

**Response:**
```json
{
  "user_id": 1,
  "bot_id": null,
  "config": {
    "enabled": true,
    "pair_whitelist": ["BTC/USDT", "ETH/USDT"],
    "pair_blacklist": ["BNB/USDT"],
    "pairlists": [...]
  },
  "updated_at": "2026-06-29T12:00:00"
}
```

### 2. Update User-Level Configuration

**PUT** `/api/config/pairlist/user`

**Request Body:**
```json
{
  "config": {
    "enabled": true,
    "pair_whitelist": [],
    "pair_blacklist": ["BNB/USDT"],
    "pairlists": [
      {
        "method": "RemotePairList",
        "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/50",
        "number_assets": 50,
        "refresh_period": 300
      }
    ]
  }
}
```

**Response:**
```json
{
  "ok": true,
  "message": "User pairlist configuration updated"
}
```

### 3. Get Bot-Specific Configuration

**GET** `/api/config/pairlist/bot/{bot_id}`

Returns pairlist configuration for a specific bot.

### 4. Update Bot-Specific Configuration

**PUT** `/api/config/pairlist/bot/{bot_id}`

Same request body as user-level update.

### 5. Export for Freqtrade

**POST** `/api/config/pairlist/export-freqtrade?bot_id={bot_id}`

Query parameter `bot_id` is optional (defaults to user-level config).

**Response:**
```json
{
  "exchange": {
    "pair_whitelist": [],
    "pair_blacklist": ["BNB/USDT"]
  },
  "pairlists": [
    {
      "method": "RemotePairList",
      "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/50",
      "number_assets": 50,
      "refresh_period": 300
    }
  ]
}
```

This can be directly merged into your Freqtrade `config.json`.

## Example Configurations

### Scanner Integration (RemotePairList)

Best for dynamic pair selection based on market quality scores.

```powershell
$config = @{
    config = @{
        enabled = $true
        pair_whitelist = @()
        pair_blacklist = @("BNB/USDT")
        pairlists = @(
            @{
                method = "RemotePairList"
                pairlist_url = "http://127.0.0.1:8000/api/markets/pairlists/50"
                number_assets = 50
                refresh_period = 300
            }
        )
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/user" `
  -Method PUT `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body $config
```

### High Volume Markets (VolumePairList)

Best for liquid, high-volume trading.

```json
{
  "config": {
    "enabled": true,
    "pair_whitelist": [],
    "pair_blacklist": [],
    "pairlists": [
      {
        "method": "VolumePairList",
        "number_assets": 30,
        "sort_key": "quoteVolume",
        "min_value": 1000000,
        "refresh_period": 1800
      }
    ]
  }
}
```

### Momentum Trading (PercentChangePairList)

Best for catching trending markets.

```json
{
  "config": {
    "enabled": true,
    "pair_whitelist": [],
    "pair_blacklist": [],
    "pairlists": [
      {
        "method": "PercentChangePairList",
        "number_assets": 20,
        "sort_direction": "desc",
        "min_value": 2,
        "max_value": 50,
        "refresh_period": 1800
      }
    ]
  }
}
```

### Top Market Cap (MarketCapPairList)

Best for established, lower-risk assets.

```json
{
  "config": {
    "enabled": true,
    "pair_whitelist": [],
    "pair_blacklist": [],
    "pairlists": [
      {
        "method": "MarketCapPairList",
        "number_assets": 20,
        "max_rank": 50,
        "refresh_period": 86400,
        "categories": ["layer-1"]
      }
    ]
  }
}
```

### Chained Pairlists (Advanced)

Combine multiple handlers for sophisticated filtering.

```json
{
  "config": {
    "enabled": true,
    "pair_whitelist": [],
    "pair_blacklist": ["BNB/USDT"],
    "pairlists": [
      {
        "method": "VolumePairList",
        "number_assets": 50,
        "sort_key": "quoteVolume",
        "min_value": 500000,
        "refresh_period": 1800
      },
      {
        "method": "RemotePairList",
        "mode": "whitelist",
        "processing_mode": "filter",
        "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/40",
        "refresh_period": 300
      },
      {
        "method": "PercentChangePairList",
        "number_assets": 25,
        "sort_direction": "desc",
        "min_value": 1,
        "refresh_period": 1800
      }
    ]
  }
}
```

**How it works:**
1. Start with top 50 volume pairs (min 500k volume)
2. Filter by scanner quality score ≥ 40
3. Further narrow to top 25 by percent change (min +1%)

## Testing

Run the comprehensive test script:

```powershell
cd backend
.\TEST_PAIRLIST_CONFIG.ps1
```

This will:
- Test all 5 pairlist handlers
- Create example configurations
- Export Freqtrade-compatible config
- Save to `pairlist_config_freqtrade.json`

## Integration with Freqtrade

### Step 1: Export Configuration

```bash
curl -X POST "http://127.0.0.1:8000/api/config/pairlist/export-freqtrade" \
  -H "Authorization: Bearer YOUR_TOKEN" > pairlist.json
```

### Step 2: Merge into Freqtrade Config

Copy the `exchange` and `pairlists` sections from `pairlist.json` into your Freqtrade `config.json`.

### Step 3: Start Freqtrade

```bash
freqtrade trade --config config.json --strategy YourStrategy
```

## Best Practices

1. **Start Simple**: Begin with a single handler (RemotePairList or VolumePairList)
2. **Test First**: Use Freqtrade's `test-pairlist` command to verify configuration
3. **Monitor**: Check Freqtrade logs to ensure pairlist updates correctly
4. **Adjust Refresh**: Match `refresh_period` to your scanner interval (default 300s)
5. **Blacklist Tokens**: Always blacklist problematic pairs (leverage tokens, stablecoins)

## Troubleshooting

### Configuration Not Saving

Ensure the request body is valid JSON and includes the `config` wrapper:
```json
{
  "config": {
    "enabled": true,
    ...
  }
}
```

### Pairlist Empty in Freqtrade

- Check scanner is running: `GET /api/markets/scan/status`
- Verify pairlist files exist: `GET /api/markets/pairlists`
- Lower threshold if needed (try 30 instead of 50)

### Authentication Errors

- Ensure JWT token is not expired (tokens typically expire after 24 hours)
- Include `Authorization: Bearer TOKEN` header in all requests
- For RemotePairList, `bearer_token` is optional unless your endpoint requires it

## Reference

- **Freqtrade Pairlist Docs**: https://www.freqtrade.io/en/stable/plugins/#pairlists-and-pairlist-handlers
- **Scanner Integration**: See `PAIRLIST_INTEGRATION.md`
- **Test Scripts**: `TEST_PAIRLIST.ps1` and `TEST_PAIRLIST_CONFIG.ps1`
