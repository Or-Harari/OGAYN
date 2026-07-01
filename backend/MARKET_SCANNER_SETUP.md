# Market Scanner Setup Guide

## Installation

### 1. Install Python Dependencies

All required dependencies are already listed in `requirements.txt`. Run:

```powershell
cd backend
pip install -r requirements.txt
```

The market scanner uses only standard libraries and packages already in your requirements:
- `requests` (HTTP client for Binance API)
- `fastapi` + `uvicorn` (web server)
- `sqlalchemy` (database)
- Python standard library: `asyncio`, `json`, `logging`, `time`, `dataclasses`

**No additional dependencies are needed.**

---

## Configuration

The scanner is controlled via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MARKET_SCANNER_ENABLED` | `true` | Set to `false` to disable scanner at startup |
| `MARKET_SCANNER_INTERVAL_SECONDS` | `300` | Scan cycle interval (5 minutes) |
| `MARKET_SCANNER_RUN_AT_STARTUP` | `true` | Run scan immediately when server starts |

Example:
```powershell
$env:MARKET_SCANNER_INTERVAL_SECONDS = "600"  # 10 minutes
$env:MARKET_SCANNER_RUN_AT_STARTUP = "false"
```

---

## Running the Backend

### Development
```powershell
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production
```powershell
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

The scanner will automatically start and run every 5 minutes.

---

## API Endpoints

All endpoints require authentication (Bearer token in `Authorization` header).

### Get All Markets (Latest Snapshot per Symbol)
```http
GET /markets?limit=200&minScore=80
```

**Query Parameters:**
- `limit` (optional, default 200, max 1000): Max results
- `minScore` (optional, 0-100): Filter by minimum market quality score

**Response:**
```json
[
  {
    "id": 1234,
    "timestamp": 1719619200,
    "exchange": "binance",
    "symbol": "BTCUSDT",
    "price": 61234.5,
    "volume": 1234567890.0,
    "atr": 1.25,
    "spread": 0.01,
    "openInterest": 987654321.0,
    "funding": 0.0001,
    "scores": {
      "liquidity": 30,
      "spread": 20,
      "atr": 20,
      "openInterest": 10,
      "funding": 10,
      "tickSize": 10
    },
    "marketQuality": 100,
    "reasons": {
      "liquidity": "Quote volume=1234567890.00, depth=5000000.00, volume_score=20/20, depth_score=10/10",
      "spread": "Spread=0.0100%",
      "atr": "ATR%=1.2500 (prefer medium volatility)",
      "open_interest": "Open interest (quote)=987654321.00",
      "funding": "Funding=0.000100 (neutral preferred)",
      "tick_size": "Tick=0.100000000000, tick/price=0.00000163"
    },
    "rawData": { ... }
  }
]
```

---

### Get Top Markets
```http
GET /markets/top?limit=50&minScore=70
```

Same as `/markets` but explicitly for top-N use cases.

---

### Get Specific Market (Latest)
```http
GET /markets/BTCUSDT
```

**Response:**
```json
{
  "id": 1234,
  "symbol": "BTCUSDT",
  "found": true,
  ...
}
```

If not found:
```json
{
  "symbol": "NOTFOUND",
  "found": false
}
```

---

### Get Market History
```http
GET /markets/history/BTCUSDT?limit=200
```

Returns time series of snapshots for a symbol (newest first).

---

### Manually Trigger Scan (Admin)
```http
POST /markets/scan/run-once
```

Forces an immediate scan cycle. Useful for testing.

**Response:**
```json
{
  "ok": true,
  "symbolsProcessed": 245,
  "timestamp": 1719619456
}
```

---

### Get Scanner Status
```http
GET /markets/scan/status
```

**Response:**
```json
{
  "running": false,
  "lastRunStartedAt": 1719619200,
  "lastRunFinishedAt": 1719619245,
  "lastRunError": null
}
```

---

## Database

The scanner creates a `market_snapshots` table automatically on first run.

### SQLite Location
`backend/data/backend.db`

### Schema
- `timestamp` (indexed): Unix timestamp
- `exchange` (indexed): "binance"
- `symbol` (indexed): "BTCUSDT", etc.
- `price`, `volume`, `atr`, `spread`, `open_interest`, `funding`
- Judge scores: `liquidity_score`, `spread_score`, `atr_score`, `oi_score`, `funding_score`, `tick_score`
- `market_quality` (indexed): Total score 0-100
- `reasons_json`: Explainability per judge
- `raw_data_json`: Full Binance API payload

---

## Architecture

```
Scanner Pipeline (every 5 minutes):

1. BinanceFuturesClient.fetch_cycle_payload()
   ├── exchangeInfo (cached 1h)
   ├── 24hr tickers
   ├── book tickers
   ├── funding rates
   ├── open interest (parallel per symbol)
   └── klines (parallel per symbol)

2. IndicatorService.compute_atr_percent()
   └── ATR% from 5m candles

3. MarketContext (per symbol)
   └── All data prepared once

4. JudgeEngine.evaluate() (parallel)
   ├── LiquidityJudge (30 pts)
   ├── SpreadJudge (20 pts)
   ├── ATRJudge (20 pts)
   ├── OpenInterestJudge (10 pts)
   ├── FundingJudge (10 pts)
   └── TickSizeJudge (10 pts)

5. MarketRepository.save_snapshots()
   └── Bulk insert to SQLite
```

---

## Judge Scoring Logic

### Liquidity Judge (max 30)
- **20 pts** from quote volume (normalized to $150M)
- **10 pts** from order book depth (normalized to $2M)

### Spread Judge (max 20)
- ≤0.01%: 20
- ≤0.03%: 16
- ≤0.06%: 12
- ≤0.10%: 8
- ≤0.20%: 4
- >0.20%: 0

### ATR Judge (max 20)
- 0.20%-2.00%: 20 (optimal)
- 0.10%-0.20% or 2.00%-3.50%: 14
- 0.05%-0.10% or 3.50%-5.00%: 8
- 0.02%-0.05% or 5.00%-8.00%: 4
- Outside range: 0

### Open Interest Judge (max 10)
- ≥$500M: 10
- ≥$200M: 8
- ≥$75M: 6
- ≥$20M: 3
- <$20M: 0

### Funding Judge (max 10)
- ≤0.01%: 10 (neutral)
- ≤0.03%: 8
- ≤0.06%: 5
- ≤0.10%: 2
- >0.10%: 0

### Tick Size Judge (max 10)
- tick/price ≤0.001%: 10
- ≤0.003%: 8
- ≤0.01%: 5
- ≤0.03%: 2
- >0.03%: 0

---

## Adding New Judges

### 1. Create Judge Class
```python
# backend/app/market_scanner/judges/sentiment_judge.py
from ..models import JudgeResult, MarketContext
from .base import IMarketJudge

class SentimentJudge(IMarketJudge):
    def __init__(self, max_score: int = 15):
        self.max_score = max_score

    def evaluate(self, context: MarketContext) -> JudgeResult:
        # Your logic here
        score = 10
        reason = "Sentiment is bullish"
        return JudgeResult(
            name="sentiment",
            score=score,
            max_score=self.max_score,
            reason=reason
        )
```

### 2. Register in JudgeEngine
```python
# backend/app/market_scanner/services/judge_engine.py
from ..judges import SentimentJudge  # Add import

class JudgeEngine:
    def __init__(self, judges: list[IMarketJudge] | None = None):
        self.judges: list[IMarketJudge] = judges or [
            LiquidityJudge(),
            SpreadJudge(),
            ATRJudge(),
            OpenInterestJudge(),
            FundingJudge(),
            TickSizeJudge(),
            SentimentJudge(),  # Add here
        ]
```

### 3. Add DB Column (Optional)
```python
# backend/app/db/models.py
class MarketSnapshot(Base):
    # ...
    sentiment_score = Column(Integer, nullable=False, default=0)
```

### 4. Update Persistence
```python
# backend/app/market_scanner/services/market_scanner_service.py
def _to_row(score: MarketScore) -> dict[str, Any]:
    by_name = {r.name: r for r in score.judge_results}
    return {
        # ...
        "sentiment_score": int(by_name.get("sentiment").score if by_name.get("sentiment") else 0),
    }
```

**That's it.** The judge will automatically run in parallel with others. The total score will update, and reasons will be stored.

---

## Testing

### Manual Trigger
```powershell
# With authentication
curl -X POST http://localhost:8000/markets/scan/run-once `
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Check Status
```powershell
curl http://localhost:8000/markets/scan/status `
  -H "Authorization: Bearer YOUR_TOKEN"
```

### View Results
```powershell
curl "http://localhost:8000/markets/top?limit=10&minScore=80" `
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Performance Notes

- **Single Binance fetch per cycle**: All endpoints called once, data reused
- **Parallel OI/klines fetch**: ~200+ symbols in ~3-5 seconds
- **Parallel judge evaluation**: All judges run concurrently via asyncio
- **Cached exchangeInfo**: 1-hour TTL
- **Async DB writes**: Non-blocking bulk insert
- **Typical cycle time**: 8-15 seconds for 240+ symbols

---

## Future Extensibility

The architecture is designed for:

### AI Analyst Integration
```python
class AIAnalystJudge(IMarketJudge):
    def evaluate(self, context: MarketContext) -> JudgeResult:
        # Call your AI service
        sentiment = call_ai_analyst(context.symbol, context.raw_data)
        return JudgeResult(name="ai_analyst", score=sentiment.score, ...)
```

### Multi-Exchange Support
```python
# backend/app/market_scanner/services/bybit_client.py
class BybitFuturesClient:
    async def fetch_cycle_payload(self) -> Dict[str, Any]:
        # Same interface, different exchange
        ...
```

### Strategy Engine Consumption
```python
# In your Freqtrade strategy:
from backend.app.market_scanner.services.market_repository import MarketRepository

class MyStrategy(IStrategy):
    def populate_indicators(self, dataframe, metadata):
        # Inject market quality score
        symbol = metadata['pair']
        repo = MarketRepository()
        snapshot = repo.latest_for_symbol(db, symbol)
        dataframe['market_quality'] = snapshot.market_quality if snapshot else 0
        return dataframe
```

---

## Troubleshooting

### Scanner not running
Check logs for startup errors:
```powershell
# Set log level
$env:LOG_LEVEL = "DEBUG"
uvicorn app.main:app --reload
```

### Binance API errors
- Verify internet connectivity
- Check Binance rate limits (weight limits apply)
- Use VPN if Binance is restricted in your region

### Empty results
- Scanner needs 1 cycle to populate DB (5 minutes default)
- Manually trigger: `POST /markets/scan/run-once`
- Check status: `GET /markets/scan/status`

### Database locked
SQLite doesn't handle concurrent writes well. If you see `database is locked`:
- Reduce concurrency (already handled in scanner)
- Consider PostgreSQL for production (easy SQLAlchemy switch)

---

## Environment Variables Summary

```powershell
# Scanner control
$env:MARKET_SCANNER_ENABLED = "true"
$env:MARKET_SCANNER_INTERVAL_SECONDS = "300"
$env:MARKET_SCANNER_RUN_AT_STARTUP = "true"

# Pairlist format
$env:PAIRLIST_FORMAT = "slash"  # "slash" (BTC/USDT) or "plain" (BTCUSDT)

# Database (optional override)
$env:FT_BACKEND_DB = "C:\path\to\custom.db"

# FastAPI/Auth
$env:FT_JWT_SECRET = "your-secret-key-here"
$env:ENVIRONMENT = "development"  # or "production"
```

---

## Freqtrade RemotePairList Integration

The scanner automatically generates Freqtrade-compatible pairlist files after each scan. These can be used with Freqtrade's `RemotePairList` handler for dynamic pair selection.

**Full documentation:** [PAIRLIST_INTEGRATION.md](app/market_scanner/PAIRLIST_INTEGRATION.md)

### Quick Start

1. **Files generated:** `backend/data/pairlists/pairlist{10,20,30,40,50,60,70,80,90}.json`
2. **Format:** `{"pairs": ["BTC/USDT", ...], "refresh_period": 300}`
3. **Endpoints:**
   - `GET /api/markets/pairlists` - List all pairlists
   - `GET /api/markets/pairlists/{threshold}` - Get specific pairlist
   - `POST /api/markets/pairlists/generate` - Manual generation

### Freqtrade Configuration

```json
{
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

---

## Next Steps

1. **Start the backend**: `uvicorn app.main:app --reload --port 8000`
2. **Wait 5 minutes** (or trigger manually)
3. **Query results**: `GET /markets/top?limit=10`
4. **Test pairlists**: Run `.\TEST_PAIRLIST.ps1` to verify pairlist generation
5. **Build UI**: Dashboard showing top markets by quality score
6. **Integrate with Freqtrade**: Use RemotePairList with generated pairlists
7. **Add custom judges**: Implement domain-specific scoring logic

---

**The scanner is production-ready and designed to scale with your trading brain architecture.**
