# Scanner Workflow Documentation

## Current Scan Process (Step-by-Step)

### When User Clicks "Run Now" on Scanner:

1. **Frontend → Backend API**
   - POST `/api/scanners/users/{userId}/scanners/{scannerId}/run`

2. **Authorization Check**
   - Verify user owns the scanner
   - Fetch scanner configuration from database
   - **Close database session immediately** (to prevent locking during scan)

3. **Market Data Fetching** (~10-20 seconds)
   - `BinanceFuturesClient.fetch_cycle_payload()`
   - Fetches:
     - Exchange symbols metadata (~600+ futures pairs)
     - 24h ticker data for all symbols
     - Book ticker (bid/ask) for all symbols
     - Funding rates
     - Open interest data
     - 1h klines (for ATR calculation)

4. **Scoring Phase** (~5-10 seconds)
   - For each symbol (600+ pairs):
     - Calculate indicators (ATR, spread, liquidity, etc.)
     - Run through judge engine with scanner's custom weights
     - Produce market score (0-100)

5. **Database Persistence** (~5-10 seconds)
   - **Opens NEW database session**
   - Bulk insert all scored markets to `market_snapshots` table
   - Tagged with `scanner_id` and `user_id`
   - **Closes session after commit**

6. **Pairlist Generation** (~10-30 seconds)
   - **Opens ANOTHER database session**
   - For each threshold (50, 60, 70, 80, 90):
     - Query: `SELECT * FROM market_snapshots WHERE scanner_id={id} AND market_quality >= {threshold}`
     - This query can be SLOW with many snapshots (6000+ rows per scanner)
     - Generate `pairlist{threshold}.json` file
   - Generate `top_pairs.json` (top N pairs based on scanner config)
   - Generate `remote_pairlist.json` (Freqtrade format)
   - **Closes session after all files written**

7. **Return Response**
   - Returns scan summary with symbols processed count

---

## Issues Identified

### 1. **Different Results for Same Config**

**Root Cause**: Each scanner creates its own snapshots in the database, tagged with different `scanner_id`. When you run multiple scans with the same config:

- They fetch the SAME market data at DIFFERENT times
- Market data changes every second (prices, volumes, spreads change)
- Each scan captures a snapshot of the market at that specific moment
- Therefore, different timestamps = different market conditions = different scores

**Example**:
```
Scanner "default" runs at 15:30:00 → BTC price: $60,075.30
Scanner "ass" runs at 15:30:45 → BTC price: $60,100.50
```
The scores will be different because the market moved in those 45 seconds.

**This is EXPECTED behavior** - scanners capture point-in-time market snapshots.

### 2. **Slow Pairlist Fetching**

**Root Cause**: The pairlist endpoint reads from disk, but the files are generated during scan. The slowness comes from:

**Problem A**: Database queries during pairlist generation
- `latest_markets()` does a complex query with subqueries
- With 16,000+ total snapshots, this query is slow
- The query finds latest snapshot for each symbol per scanner
- This happens for EACH threshold (5 queries per scanner)

**Problem B**: File I/O
- Multiple JSON files being written (8-10 files per scanner)
- Synchronous file operations

**Problem C**: No caching
- Every scan regenerates ALL pairlist files
- No incremental updates

### 3. **Can 2 Scans Run Simultaneously?**

**Current State**: YES, they CAN run simultaneously, but with issues:

**What Works**:
- Different scanners fetch market data independently
- Each uses its own database session
- SQLite WAL mode allows concurrent writes

**What Doesn't Work Well**:
- Database contention when both try to save snapshots simultaneously
- Pairlist generation can lock database for reads
- No queuing system - unlimited concurrent scans possible
- Resource exhaustion if many scans run at once

**Observed Behavior**:
- First scan starts, fetches data, scores, saves
- Second scan starts while first is in pairlist generation
- Second scan may timeout or experience database lock errors
- Both try to commit snapshots around the same time → contention

---

## Recommendations

### Fix 1: Add Scan Results Endpoint
Instead of reading pairlist files, query database directly:
```
GET /api/scanners/users/{userId}/scanners/{scannerId}/results/latest
```
This already exists but needs to be used by frontend for display.

### Fix 2: Optimize Database Queries
- Add indexes on `(scanner_id, timestamp)` 
- Limit snapshots to last 7 days per scanner
- Delete old snapshots periodically

### Fix 3: Queue Scan Execution
- Only allow 1 scan per user at a time
- Queue additional scans
- Show "Scanner busy" state in UI

### Fix 4: Cache Pairlist Files
- Only regenerate when scan completes
- Serve cached files for GET requests
- Add `last_updated` timestamp to response

### Fix 5: Background Scan Task
- Move scan execution to background task
- Return immediately with "scan queued" response
- Use WebSocket or polling for status updates

---

## Current Performance Metrics

| Phase | Duration | Bottleneck |
|-------|----------|------------|
| Market Data Fetch | 10-20s | Binance API rate limits |
| Scoring | 5-10s | CPU (600+ symbols × 6 judges) |
| Database Save | 5-10s | SQLite write locks |
| Pairlist Generation | 10-30s | Database query + file I/O |
| **Total** | **30-70s** | |

---

## Scanner Isolation

Each scanner is isolated by:
- Separate `scanner_id` in database
- Separate output directories: `workspaces/user{id}/user/scanners/{scannerName}/`
- Separate pairlist files
- Independent configurations (weights, thresholds, max_pairs)

**BUT**: All scanners share:
- Same Binance API client (rate limited)
- Same database connection pool
- Same scoring logic (only weights differ)
- Same market data source (Binance)

---

## Why Results Differ

Even with identical configs, results will differ because:

1. **Time-based data**: Market prices, volumes, spreads change constantly
2. **Different timestamps**: Each scan captures market at different moment
3. **ATR calculation**: Uses recent 1h klines - these change every minute
4. **Funding rates**: Update every 8 hours but fetched at scan time
5. **Open interest**: Changes continuously

**To get identical results**: Run scans at EXACT same timestamp (impossible) or use cached market data (not implemented).

---

## Database Schema Impact

```sql
-- market_snapshots table structure
CREATE TABLE market_snapshots (
    id INTEGER PRIMARY KEY,
    scanner_id INTEGER,  -- ISOLATES scanners
    user_id INTEGER,
    timestamp INTEGER,   -- When scan ran
    symbol VARCHAR,
    market_quality INTEGER,
    -- ... other fields
);

-- Current snapshot counts:
-- Scanner "default" (ID=1): 6,348 snapshots
-- Scanner "ass" (ID=2): 7,935 snapshots  
-- Scanner "asd" (ID=3): 2,116 snapshots
-- TOTAL: 16,399 snapshots (growing with each scan)
```

**Issue**: No cleanup strategy - table grows indefinitely.
