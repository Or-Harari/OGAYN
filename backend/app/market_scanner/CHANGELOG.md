# Multi-Scanner Refactor - Changelog

## Version 2.0.0 - Multi-Scanner Architecture (2026-06-29)

### 🚀 Major Changes

#### Database Schema
- **Added** `scanner_configs` table for managing scanner configurations
- **Added** `scanner_id` and `user_id` columns to `market_snapshots` table
- **Added** Migration script: `backend/app/db/migrations/add_scanner_configs.sql`
- **Added** Migration helper: `backend/app/db/apply_migration.py`

#### Models & Schemas
- **Added** `ScannerConfig` database model in `db/models.py`
- **Added** Comprehensive Pydantic schemas in `market_scanner/schemas.py`:
  - `ScannerConfigBase`
  - `ScannerConfigCreate`
  - `ScannerConfigUpdate`
  - `ScannerConfigResponse`
  - `ScannerConfigInternal`
  - `ScoringWeights`
  - `ScoringThresholds`
  - `ScannerResultSummary`

#### Services
- **Added** `ScannerConfigRepository` for scanner CRUD operations
- **Modified** `MarketScannerService` to accept `scanner_config` parameter
- **Modified** `PairlistService` to support scanner-specific output paths
- **Modified** `JudgeEngine` to create configurable judges from scanner config
- **Modified** Judges to accept threshold parameters:
  - `LiquidityJudge`: min_volume, excellent_volume
  - `ATRJudge`: min_atr, ideal_low, ideal_high, max_atr
  - `SpreadJudge`: max_spread
- **Modified** `MarketRepository.latest_markets()` to filter by scanner_id/user_id
- **Modified** `ScannerRuntime` to support multi-scanner execution

#### API Routes
- **Added** New router: `routes/scanners.py` with endpoints:
  - `GET /api/scanners/users/{userId}/scanners` - List user scanners
  - `POST /api/scanners/users/{userId}/scanners` - Create scanner
  - `GET /api/scanners/users/{userId}/scanners/{scannerId}` - Get scanner
  - `PUT /api/scanners/users/{userId}/scanners/{scannerId}` - Update scanner
  - `DELETE /api/scanners/users/{userId}/scanners/{scannerId}` - Delete scanner
  - `GET /api/scanners/users/{userId}/scanners/{scannerId}/results/latest` - Latest scan results
  - `GET /api/scanners/users/{userId}/scanners/{scannerId}/pairlist` - Get pairlist (Freqtrade compatible)
  - `POST /api/scanners/users/{userId}/scanners/{scannerId}/run` - Run scanner now
- **Added** Legacy endpoints for backward compatibility:
  - `GET /api/scanners/status` - Scanner runtime status
  - `POST /api/scanners/run` - Run default scanner
  - `POST /api/scanners/run-multi` - Run all enabled scanners
- **Modified** `main.py` to register scanners router

#### File Structure
- **Changed** Output paths from global `backend/data/pairlists/` to user/scanner-specific:
  - `user_data/users/{userId}/scanners/{scannerName}/pairlists/`
  - `user_data/users/{userId}/scanners/{scannerName}/snapshots/`
  - `user_data/users/{userId}/scanners/{scannerName}/logs/`
- **Added** New pairlist files per scanner:
  - `top_pairs.json` - Top N pairs based on scanner config
  - `top_pairs.txt` - Plain text list
  - `remote_pairlist.json` - Freqtrade RemotePairList compatible
  - `pairlist{10-90}.json` - Legacy threshold-based pairlists

#### Configuration
- **Added** Environment variable: `MULTI_SCANNER_ENABLED` (default: true)
- **Modified** Scanner runtime behavior:
  - If `MULTI_SCANNER_ENABLED=true`: runs all enabled scanner configs
  - If `MULTI_SCANNER_ENABLED=false`: uses legacy single-scanner mode

#### Documentation
- **Added** `MULTI_SCANNER_ARCHITECTURE.md` - Comprehensive architecture guide
- **Added** `QUICKSTART.md` - Quick start guide for users
- **Added** `test_multi_scanner.py` - Automated test script

### 🔧 Breaking Changes

⚠️ **Database Migration Required**
- Must run migration to add `scanner_configs` table
- Existing `market_snapshots` will be assigned to default scanner

⚠️ **Output Path Changes**
- New scanners output to `user_data/users/{userId}/scanners/{name}/pairlists/`
- Legacy path `backend/data/pairlists/` still works for default scanner

### ✅ Backward Compatibility

- **Default Scanner**: Automatically created for user_id=1 with previous hardcoded values
- **Legacy Mode**: Set `MULTI_SCANNER_ENABLED=false` to use old behavior
- **Legacy Endpoints**: Old `/api/markets/*` endpoints still work
- **Existing Data**: Migration assigns existing snapshots to default scanner

### 🐛 Bug Fixes

- Fixed hardcoded scoring values (now configurable)
- Fixed global pairlist path (now user/scanner-specific)

### 📊 Performance Improvements

- Parallel execution of multiple scanners
- Scanner-specific database queries (indexed by scanner_id)
- Atomic file writes (temp file → rename)

### 🔒 Security Enhancements

- User isolation enforced at API level
- Filesystem-safe scanner names (alphanumeric, hyphens, underscores only)
- Server-side path computation (no user input in paths)
- JWT-based authentication for all scanner endpoints

### 📝 Code Quality

- No errors reported by static analyzer
- Type hints added throughout
- Comprehensive docstrings
- Clean separation of concerns

### 🧪 Testing

- **Added** Automated test script: `test_multi_scanner.py`
- **Tests** CRUD operations on scanner configs
- **Tests** Multi-scanner execution
- **Tests** Pairlist generation
- **Tests** Database record verification

### 📖 API Documentation

All endpoints documented with OpenAPI/Swagger:
- Visit http://localhost:8000/docs for interactive API documentation

### 🎯 Use Cases Enabled

1. **Strategy-Specific Scanners**: Different scanners optimized for different strategies
2. **Multi-Exchange Support**: Separate scanners per exchange
3. **Risk Profiles**: Conservative, balanced, and aggressive scanner configurations
4. **A/B Testing**: Run multiple scanner variants simultaneously
5. **User Isolation**: Each user manages their own scanners

### 🔮 Future Roadmap

- [ ] Per-scanner interval configuration
- [ ] Scanner scheduling (cron-like syntax)
- [ ] Scanner performance metrics and analytics
- [ ] Scanner alerts/notifications
- [ ] Scanner templates/presets
- [ ] Scanner sharing between users
- [ ] Scanner versioning/history
- [ ] Frontend UI for scanner management

### 📦 Files Modified

#### Created Files (15)
- `backend/app/db/migrations/add_scanner_configs.sql`
- `backend/app/db/apply_migration.py`
- `backend/app/market_scanner/schemas.py`
- `backend/app/market_scanner/services/scanner_config_repository.py`
- `backend/app/routes/scanners.py`
- `backend/app/market_scanner/MULTI_SCANNER_ARCHITECTURE.md`
- `backend/app/market_scanner/QUICKSTART.md`
- `backend/app/market_scanner/test_multi_scanner.py`

#### Modified Files (11)
- `backend/app/db/models.py` - Added ScannerConfig model, updated MarketSnapshot
- `backend/app/market_scanner/services/market_scanner_service.py` - Scanner config support
- `backend/app/market_scanner/services/pairlist_service.py` - Scanner-specific paths
- `backend/app/market_scanner/services/scanner_runtime.py` - Multi-scanner execution
- `backend/app/market_scanner/services/judge_engine.py` - Configurable judges
- `backend/app/market_scanner/services/market_repository.py` - Scanner filtering
- `backend/app/market_scanner/judges/liquidity_judge.py` - Configurable thresholds
- `backend/app/market_scanner/judges/atr_judge.py` - Configurable thresholds
- `backend/app/market_scanner/judges/spread_judge.py` - Configurable thresholds
- `backend/app/market_scanner/services/__init__.py` - Export new repository
- `backend/app/main.py` - Register scanners router

### 🙏 Migration Instructions

1. **Backup Database**
   ```bash
   cp backend/data/app.db backend/data/app.db.backup
   ```

2. **Apply Migration**
   ```bash
   cd backend
   python -m app.db.apply_migration
   ```

3. **Verify Migration**
   ```bash
   sqlite3 backend/data/app.db "SELECT * FROM scanner_configs;"
   ```

4. **Restart Backend**
   ```bash
   python -m uvicorn app.main:app --reload
   ```

5. **Run Tests**
   ```bash
   python -m app.market_scanner.test_multi_scanner
   ```

### 📞 Support

For issues or questions:
- Check documentation: `MULTI_SCANNER_ARCHITECTURE.md`
- Run test script: `python -m app.market_scanner.test_multi_scanner`
- Review API docs: http://localhost:8000/docs

---

**Note**: This refactor maintains full backward compatibility. Existing deployments will continue to work with default scanner configuration.
