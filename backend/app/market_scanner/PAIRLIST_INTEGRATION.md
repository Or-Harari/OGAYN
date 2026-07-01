# Freqtrade RemotePairList Integration

## Overview

The Market Scanner automatically generates Freqtrade-compatible pairlist JSON files after each scan cycle. These files can be consumed by Freqtrade's `RemotePairList` handler to dynamically update trading pairs based on market quality scores.

## Generated Files

Location: `backend/data/pairlists/`

| File | Content |
|------|---------|
| `pairlist10.json` | Symbols with score ≥ 10 |
| `pairlist20.json` | Symbols with score ≥ 20 |
| `pairlist30.json` | Symbols with score ≥ 30 |
| `pairlist40.json` | Symbols with score ≥ 40 |
| `pairlist50.json` | Symbols with score ≥ 50 |
| `pairlist60.json` | Symbols with score ≥ 60 |
| `pairlist70.json` | Symbols with score ≥ 70 |
| `pairlist80.json` | Symbols with score ≥ 80 |
| `pairlist90.json` | Symbols with score ≥ 90 |

## File Format

Each file follows Freqtrade's RemotePairList format:

```json
{
  "pairs": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
  "refresh_period": 300
}
```

- **pairs**: Array of trading pairs in `BASE/QUOTE` format (e.g., `BTC/USDT`)
- **refresh_period**: How often (in seconds) Freqtrade should refetch the list (matches scanner interval)

## REST API Endpoints

All endpoints require authentication (JWT Bearer token).

### 1. List Available Pairlists

**GET** `/api/markets/pairlists`

Returns metadata for all generated pairlist files.

**Response:**
```json
[
  {
    "threshold": 50,
    "filename": "pairlist50.json",
    "count": 42,
    "refresh_period": 300,
    "path": "/path/to/pairlist50.json"
  }
]
```

### 2. Get Specific Pairlist

**GET** `/api/markets/pairlists/{threshold}`

Returns the pairlist JSON for a specific score threshold.

**Example:** `GET /api/markets/pairlists/50`

**Response:**
```json
{
  "pairs": ["BTC/USDT", "ETH/USDT", ...],
  "refresh_period": 300
}
```

**Error Response (404):**
```json
{
  "detail": "Pairlist for threshold 55 not found. Available: [10, 20, 30, 40, 50, 60, 70, 80, 90]"
}
```

### 3. Manual Pairlist Generation

**POST** `/api/markets/pairlists/generate`

Triggers immediate pairlist generation from current database snapshots (useful for testing or manual updates).

**Response:**
```json
{
  "files": {
    "pairlist10.json": {
      "threshold": 10,
      "count": 250,
      "path": "/path/to/pairlist10.json"
    },
    "pairlist20.json": {
      "threshold": 20,
      "count": 180,
      "path": "/path/to/pairlist20.json"
    }
  },
  "errors": []
}
```

## Freqtrade Configuration

### Option 1: Direct File Access

If Freqtrade runs on the same server:

```json
{
  "pairlists": [
    {
      "method": "RemotePairList",
      "pairlist_url": "file:///path/to/backend/data/pairlists/pairlist50.json",
      "number_assets": 50,
      "refresh_period": 300,
      "keep_pairlist_on_failure": true
    }
  ]
}
```

### Option 2: HTTP Endpoint (Recommended)

Using the REST API endpoint:

```json
{
  "pairlists": [
    {
      "method": "RemotePairList",
      "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/50",
      "bearer_token": "your-jwt-token-here",
      "number_assets": 50,
      "refresh_period": 300,
      "keep_pairlist_on_failure": true
    }
  ]
}
```

**Note:** `bearer_token` is **optional**. If your API requires authentication, include it. For public endpoints or local file access, you can omit it.

**Parameters:**
- `pairlist_url`: API endpoint or file path
- `bearer_token`: **Optional** authentication token (get from `/auth/token`)
- `number_assets`: Max pairs to use (Freqtrade will limit to this)
- `refresh_period`: How often to refetch (should match scanner interval)
- `keep_pairlist_on_failure`: Keep old list if fetch fails

### Getting a Bearer Token

```bash
# Login to get token
curl -X POST http://127.0.0.1:8000/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=youruser&password=yourpass"

# Response
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Use the `access_token` value as your `bearer_token` in Freqtrade config.

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PAIRLIST_FORMAT` | `slash` | Pair format: `slash` (BTC/USDT) or `plain` (BTCUSDT) |
| `MARKET_SCANNER_INTERVAL_SECONDS` | `300` | Scanner interval (also used as refresh_period) |

### Customizing Thresholds

Edit `backend/app/market_scanner/services/pairlist_service.py`:

```python
self.thresholds = [10, 20, 30, 40, 50, 60, 70, 80, 90]
```

You can add/remove thresholds as needed (e.g., `[25, 50, 75]` for fewer files).

### Customizing Output Directory

```python
pairlist_service = PairlistService(
    output_dir="/custom/path/to/pairlists",
    refresh_period=600,  # 10 minutes
    pair_format="plain"  # BTCUSDT instead of BTC/USDT
)
```

## Generation Timing

Pairlists are automatically generated:

1. **After each scanner cycle** (default: every 5 minutes)
2. **On startup** (if MARKET_SCANNER_RUN_AT_STARTUP=true)
3. **On manual trigger** (POST /api/markets/pairlists/generate)

This ensures pairlists are always based on the latest market data.

## Choosing the Right Threshold

| Threshold | Use Case | Typical Count |
|-----------|----------|---------------|
| **10-20** | Large pairlist, includes lower-quality markets | 200-300 |
| **30-40** | Balanced pairlist, decent liquidity | 100-200 |
| **50-60** | High-quality markets only | 50-100 |
| **70-80** | Premium markets, best conditions | 20-50 |
| **90+** | Top-tier markets, very strict | 5-20 |

Start with **threshold 40-50** for most strategies. Adjust based on:
- **Lower threshold**: More trading opportunities, lower quality
- **Higher threshold**: Fewer pairs, better conditions

## Example Workflow

### 1. Generate Initial Pairlists

```bash
# Trigger manual generation
curl -X POST http://127.0.0.1:8000/api/markets/pairlists/generate \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 2. View Available Pairlists

```bash
curl http://127.0.0.1:8000/api/markets/pairlists \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3. Test a Specific Pairlist

```bash
curl http://127.0.0.1:8000/api/markets/pairlists/50 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 4. Configure Freqtrade

Update your Freqtrade `config.json`:

```json
{
  "exchange": {
    "name": "binance",
    "pair_whitelist": [],
    "pair_blacklist": []
  },
  "pairlists": [
    {
      "method": "RemotePairList",
      "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/50",
      "bearer_token": "YOUR_JWT_TOKEN",
      "number_assets": 50,
      "refresh_period": 300
    }
  ]
}
```

### 5. Start Freqtrade

```bash
freqtrade trade --config config.json --strategy YourStrategy
```

Freqtrade will now:
- Fetch the pairlist every 5 minutes
- Use only markets with score ≥ 50
- Automatically update as market conditions change

## Troubleshooting

### Pairlist files not generated

Check logs for errors:
```bash
tail -f backend/logs/app.log | grep -i pairlist
```

Manually trigger generation:
```bash
curl -X POST http://127.0.0.1:8000/api/markets/pairlists/generate \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Empty pairlists

If a pairlist is empty or has very few pairs:
- Lower the threshold (try 30 or 40 instead of 50)
- Check if scanner is running: `GET /api/markets/scan/status`
- Verify database has data: `GET /api/markets/top?limit=10&minScore=0`

### Authentication errors

Ensure your JWT token is valid and not expired. Tokens typically expire after 24 hours.

### Wrong pair format

If Freqtrade expects `BTCUSDT` instead of `BTC/USDT`:
```bash
export PAIRLIST_FORMAT=plain
```

Then restart the backend and regenerate pairlists.

## Performance Notes

- Each pairlist file is typically **< 10 KB**
- Generation takes **< 1 second** (reads from DB, no API calls)
- No impact on scanner performance (runs after scan completes)
- Files are written atomically (safe for concurrent reads)

## Advanced: Multiple Bots

You can run multiple Freqtrade bots with different thresholds:

**Bot 1 (Conservative):**
```json
{
  "pairlists": [{
    "method": "RemotePairList",
    "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/70",
    "number_assets": 20
  }]
}
```

**Bot 2 (Aggressive):**
```json
{
  "pairlists": [{
    "method": "RemotePairList",
    "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/30",
    "number_assets": 100
  }]
}
```

Each bot will trade different markets based on quality thresholds.

---

## Pairlist Configuration Manager

The backend provides endpoints to manage Freqtrade pairlist configurations. This allows you to configure and export complete pairlist handler chains for your Freqtrade bots.

### Supported Pairlist Handlers

1. **RemotePairList** - Fetch pairlist from URL or scanner endpoint
2. **StaticPairList** - Use static pair whitelist
3. **VolumePairList** - Sort/filter by trading volume
4. **PercentChangePairList** - Filter by price percent change
5. **MarketCapPairList** - Sort by CoinGecko market cap

### Configuration API Endpoints

All endpoints require authentication (JWT Bearer token).

#### 1. Get User-Level Config

**GET** `/api/config/pairlist/user`

Returns user's default pairlist configuration.

**Response:**
```json
{
  "user_id": 1,
  "bot_id": null,
  "config": {
    "enabled": true,
    "pair_whitelist": ["BTC/USDT", "ETH/USDT"],
    "pair_blacklist": ["BNB/USDT"],
    "pairlists": [
      {
        "method": "RemotePairList",
        "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/50",
        "number_assets": 50,
        "refresh_period": 300
      }
    ]
  },
  "updated_at": "2026-06-29T12:34:56"
}
```

#### 2. Update User-Level Config

**PUT** `/api/config/pairlist/user`

**Body:**
```json
{
  "config": {
    "enabled": true,
    "pair_whitelist": [],
    "pair_blacklist": ["BNB/USDT"],
    "pairlists": [
      {
        "method": "VolumePairList",
        "number_assets": 30,
        "sort_key": "quoteVolume",
        "min_value": 100000,
        "refresh_period": 1800
      },
      {
        "method": "RemotePairList",
        "mode": "whitelist",
        "processing_mode": "filter",
        "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/40",
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

#### 3. Get Bot-Specific Config

**GET** `/api/config/pairlist/bot/{bot_id}`

Returns pairlist configuration for a specific bot.

#### 4. Update Bot-Specific Config

**PUT** `/api/config/pairlist/bot/{bot_id}`

Same body structure as user-level update.

#### 5. Export for Freqtrade

**POST** `/api/config/pairlist/export-freqtrade?bot_id={bot_id}`

Returns a Freqtrade-compatible config snippet that can be merged into `config.json`.

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

### Example Pairlist Configurations

#### RemotePairList (Scanner Integration)

```json
{
  "enabled": true,
  "pair_whitelist": [],
  "pair_blacklist": [],
  "pairlists": [
    {
      "method": "RemotePairList",
      "pairlist_url": "http://127.0.0.1:8000/api/markets/pairlists/50",
      "mode": "whitelist",
      "processing_mode": "filter",
      "number_assets": 50,
      "refresh_period": 300,
      "keep_pairlist_on_failure": true
    }
  ]
}
```

#### StaticPairList

```json
{
  "enabled": true,
  "pair_whitelist": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
  "pair_blacklist": ["BNB/USDT"],
  "pairlists": [
    {
      "method": "StaticPairList",
      "allow_inactive": false
    }
  ]
}
```

#### VolumePairList (High Volume Markets)

```json
{
  "enabled": true,
  "pair_whitelist": [],
  "pair_blacklist": [],
  "pairlists": [
    {
      "method": "VolumePairList",
      "number_assets": 20,
      "sort_key": "quoteVolume",
      "min_value": 1000000,
      "refresh_period": 1800
    }
  ]
}
```

#### PercentChangePairList (Momentum Markets)

```json
{
  "enabled": true,
  "pair_whitelist": [],
  "pair_blacklist": [],
  "pairlists": [
    {
      "method": "PercentChangePairList",
      "number_assets": 15,
      "sort_key": "percentage",
      "sort_direction": "desc",
      "min_value": 2,
      "max_value": 50,
      "refresh_period": 1800
    }
  ]
}
```

#### MarketCapPairList (Top Market Cap)

```json
{
  "enabled": true,
  "pair_whitelist": [],
  "pair_blacklist": [],
  "pairlists": [
    {
      "method": "MarketCapPairList",
      "number_assets": 20,
      "max_rank": 50,
      "refresh_period": 86400,
      "mode": "whitelist",
      "categories": ["layer-1"]
    }
  ]
}
```

#### Chained Pairlists (Advanced)

Combine multiple handlers for sophisticated filtering:

```json
{
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
```

This configuration:
1. Starts with top 50 volume pairs (min 500k volume)
2. Filters by scanner quality score ≥40
3. Further narrows to top 25 by percent change (min +1%)
