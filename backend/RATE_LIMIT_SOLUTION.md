# Binance Rate Limiting - Solutions & Analysis

## Date: 2026-06-29

## Current Problem

**Error:** `binance 418 I'm a teapot - Way too many requests; IP banned until...`

**Root Cause:** Our MarketDataFetcherService makes ~400-500 API calls every 5 minutes:
- 1x `/fapi/v1/ticker/24hr` (weight: 40)
- 1x `/fapi/v1/ticker/bookTicker` (weight: 40)
- 1x `/fapi/v1/premiumIndex` (weight: 10)
- ~200x `/fapi/v1/openInterest` per symbol (weight: 200)
- ~200x `/fapi/v1/klines` per symbol (weight: 200)

**Total Weight:** ~490 every 5 minutes = **~98 weight/minute + 100 requests/minute**

When combined with FreqTrade bot trading operations, this exceeds Binance's burst limits.

---

## Why FreqTrade Doesn't Get Rate Limited

1. **Minimal pairs:** Only fetches 5-10 active pairs, not 200+
2. **WebSockets:** Uses real-time streams (zero weight)
3. **CCXT throttling:** Built-in request rate limiting
4. **Spread requests:** Distributes calls over time
5. **Selective fetching:** Only gets what it needs

---

## Solutions Ranked

### 1. WebSocket Streams ⭐ **BEST LONG-TERM**

**Implementation:**
Replace REST API polling with WebSocket connections:

```python
# Binance Futures WebSocket Streams
wss://fstream.binance.com/stream?streams=
  !ticker@arr           # All 24hr tickers (real-time)
  !bookTicker          # All order books (real-time)
  !markPrice@arr       # Mark prices & funding rates (real-time)
```

**Pros:**
- ✅ Zero API weight (no rate limits)
- ✅ Real-time data (sub-second updates)
- ✅ Single persistent connection
- ✅ Recommended by Binance
- ✅ Production-grade solution

**Cons:**
- ❌ Requires new implementation (~4 hours)
- ❌ Need WebSocket library (websockets, aiohttp)
- ❌ Connection management complexity

**Libraries:**
- `websockets` - Simple WebSocket client
- `python-binance` - Official Binance library with WS support
- Custom implementation with `aiohttp`

**Code Structure:**
```
backend/app/market_scanner/services/
  ├── websocket_fetcher_service.py  (new)
  ├── websocket_handlers.py         (new)
  └── market_cache_repository.py    (existing)
```

---

### 2. Batch & Throttle (with delays) ⚡ **QUICK FIX**

**Implementation:**
Add delays between batches of symbols:

```python
async def fetch_cycle_payload_throttled(self):
    all_symbols = self._get_perpetual_usdt_symbols()
    batch_size = 30
    batch_delay = 45  # seconds
    
    all_data = []
    for i in range(0, len(all_symbols), batch_size):
        batch = all_symbols[i:i+batch_size]
        
        # Fetch batch
        batch_data = await self._fetch_batch(batch)
        all_data.extend(batch_data)
        
        # Wait before next batch
        if i + batch_size < len(all_symbols):
            await asyncio.sleep(batch_delay)
    
    return all_data
```

**Pros:**
- ✅ Quick implementation (~1 hour)
- ✅ Stays under rate limits
- ✅ Uses existing code
- ✅ Configurable batch sizes

**Cons:**
- ❌ Slower full refresh (10-15 minutes for all symbols)
- ❌ Still REST-based (less efficient)
- ❌ Complex scheduling logic

---

### 3. Increase Fetch Interval ⏱️ **IMMEDIATE FIX**

**Implementation:** (ALREADY APPLIED)
Changed from 5 minutes to 30 minutes in main.py:

```python
market_data_fetcher.start(fetch_interval_minutes=30)
```

**Pros:**
- ✅ Immediate (no code changes)
- ✅ Reduces rate limit pressure by 6x
- ✅ Already configurable

**Cons:**
- ❌ Stale data (30 minutes old)
- ❌ Still bursts when it does fetch
- ❌ Not suitable for high-frequency trading

**Status:** ✅ APPLIED (see main.py)

---

### 4. Reduce Symbol Count 📊

**Implementation:**
Pre-filter to top volume symbols only:

```python
async def fetch_cycle_payload(self):
    # Get all symbols
    all_symbols = await self._get_perpetual_usdt_symbols()
    
    # Get 24hr tickers to sort by volume
    tickers = await self._get_json_async("/fapi/v1/ticker/24hr")
    
    # Sort by quote volume and take top 100
    sorted_symbols = sorted(
        tickers, 
        key=lambda x: float(x.get('quoteVolume', 0)), 
        reverse=True
    )[:100]
    
    symbols = [s['symbol'] for s in sorted_symbols]
    
    # Continue with filtered list...
```

**Pros:**
- ✅ Reduces calls by 50-75%
- ✅ Focuses on liquid pairs
- ✅ Better scanner results

**Cons:**
- ❌ Misses low-volume opportunities
- ❌ Fixed limit might not fit all strategies

---

### 5. Optimize Endpoints 🔧

**Implementation:**
Use multi-symbol batch endpoints where available:

```python
# Binance supports batch OI requests (undocumented)
# Instead of 200 individual calls, use symbol list parameter
response = requests.get(
    "/fapi/v1/openInterest",
    params={"symbols": ["BTCUSDT", "ETHUSDT", ...]}  # Multiple symbols
)
```

**Pros:**
- ✅ Fewer API calls
- ✅ Same data quality

**Cons:**
- ❌ Not officially documented
- ❌ May not work for all endpoints
- ❌ Binance might remove this

---

### 6. Cache Longer ⏳

**Implementation:**
Increase cache TTL from 1 hour to 6-12 hours:

```python
# In market_cache_repository.py
def cleanup_old_cache(self, db: Session, hours_to_keep: int = 6):
    ...
```

**Pros:**
- ✅ Less frequent fetching
- ✅ Reduces pressure

**Cons:**
- ❌ Very stale data
- ❌ Not suitable for market scanning
- ❌ Defeats purpose of system

---

## Recommended Implementation Plan

### Phase 1: Immediate (DONE ✅)
- [x] Increase fetch interval to 30 minutes
- [x] Document the issue
- [x] Wait for IP ban to expire

### Phase 2: Short-term (This Week)
- [ ] Implement batch/throttle mechanism (Option 2)
  - Split 200 symbols into 7 batches of ~30
  - Add 4-minute delays between batches
  - Total fetch time: ~28 minutes (fits in 30-minute interval)
- [ ] Reduce to top 100 symbols (Option 4)
- [ ] Test with FreqTrade running simultaneously

### Phase 3: Long-term (Next Week)
- [ ] Implement WebSocket fetcher (Option 1)
- [ ] Real-time streaming updates
- [ ] Remove REST API polling entirely
- [ ] Production deployment

---

## WebSocket Implementation Guide

### Required Changes:

**1. New Service: `websocket_fetcher_service.py`**
```python
import asyncio
import json
import websockets
from typing import Dict, Any

class WebSocketFetcherService:
    WS_URL = "wss://fstream.binance.com/stream"
    
    async def connect(self):
        # Subscribe to combined streams
        streams = [
            "!ticker@arr",        # All 24hr tickers
            "!bookTicker",        # All order book tickers
            "!markPrice@arr@1s"   # All mark prices (1s updates)
        ]
        
        uri = f"{self.WS_URL}?streams={'/'.join(streams)}"
        
        async with websockets.connect(uri) as ws:
            while self._running:
                msg = await ws.recv()
                await self._handle_message(json.loads(msg))
    
    async def _handle_message(self, data: Dict[str, Any]):
        stream = data.get('stream')
        payload = data.get('data')
        
        if stream == '!ticker@arr':
            await self._update_tickers(payload)
        elif stream == '!bookTicker':
            await self._update_book_ticker(payload)
        elif stream == '!markPrice@arr@1s':
            await self._update_funding(payload)
```

**2. Handler Methods:**
- `_update_tickers()` - Process 24hr ticker data
- `_update_book_ticker()` - Process bid/ask prices
- `_update_funding()` - Process funding rates
- Background task to compute indicators (ATR) from cached klines

**3. Integration:**
Replace `market_data_fetcher.start()` with `websocket_fetcher.start()`

**4. Fallback:**
Keep REST API for:
- Historical klines (one-time on startup)
- Open Interest (fetch less frequently, 1-2 hours)
- Exchange info (daily refresh)

---

## Configuration Recommendations

### Development:
```python
fetch_interval_minutes=30  # REST API polling
cache_ttl_hours=2
top_symbols=100
```

### Production (REST):
```python
fetch_interval_minutes=15
cache_ttl_hours=1
top_symbols=150
batch_size=25
batch_delay=30
```

### Production (WebSocket):
```python
websocket_enabled=True
rest_fallback_interval=60  # Only for OI and klines
cache_ttl_hours=1
real_time_updates=True
```

---

## Testing Plan

1. **Monitor API Weight:**
   ```python
   # Log weight usage from response headers
   weight_used = response.headers.get('X-MBX-USED-WEIGHT-1M')
   logger.info(f"API weight used: {weight_used}/1200")
   ```

2. **FreqTrade Compatibility:**
   - Run both systems simultaneously
   - Monitor for 418 errors
   - Check FreqTrade order execution

3. **Data Quality:**
   - Compare REST vs WebSocket data
   - Verify indicator calculations
   - Check cache freshness

---

## Resources

- [Binance Futures WebSocket Docs](https://binance-docs.github.io/apidocs/futures/en/#websocket-market-streams)
- [CCXT Rate Limiting](https://docs.ccxt.com/#/README?id=rate-limit)
- [Python WebSocket Library](https://websockets.readthedocs.io/)
- [python-binance (Unofficial SDK)](https://python-binance.readthedocs.io/)

---

## IP Ban Recovery

**Current Ban Status:** Until Unix timestamp 1782752159012 (check your error)

**Time to Wait:** Usually 10-60 minutes after last violation

**Check Ban Status:**
```bash
curl -v https://fapi.binance.com/fapi/v1/ping
```

**Verify Lifted:**
- Response: `{}` = OK
- Error 418 = Still banned

**After Ban Lifts:**
- Backend will auto-retry on next 30-minute interval
- Cache will populate automatically
- Scanners will start working again

---

## Conclusion

The 30-minute interval (Phase 1) will prevent future bans. 

For production with real-time requirements, implementing WebSocket streams (Phase 3) is essential - it's how professional trading systems operate and exactly what Binance recommends.
