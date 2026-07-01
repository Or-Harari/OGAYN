# Market Scanner Quick Start Commands

# ============================================
# STEP 1: INSTALL PYTHON (if not installed)
# ============================================

# Option A: Download Python 3.11+ from official website
# https://www.python.org/downloads/
# ⚠️ IMPORTANT: Check "Add Python to PATH" during installation

# Option B: Install via winget (Windows Package Manager)
winget install Python.Python.3.11

# Option C: Install via Chocolatey
# choco install python --version=3.11.0

# Verify Python installation
python --version
# Should show: Python 3.11.x or 3.12.x or 3.13.x

# Verify pip is installed
pip --version


# ============================================
# STEP 2: INSTALL PROJECT DEPENDENCIES
# ============================================

# Navigate to backend directory
cd backend

# Install all Python dependencies
pip install -r requirements.txt

# Verify installation
pip list | Select-String "fastapi|uvicorn|sqlalchemy|requests"


# ============================================
# RUNNING THE BACKEND
# ============================================

# Development mode (with auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode (multiple workers)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2


# ============================================
# OPTIONAL: CONFIGURE SCANNER
# ============================================

# Change scan interval to 10 minutes
$env:MARKET_SCANNER_INTERVAL_SECONDS = "600"

# Disable auto-start (manual trigger only)
$env:MARKET_SCANNER_RUN_AT_STARTUP = "false"

# Disable scanner completely
$env:MARKET_SCANNER_ENABLED = "false"


# ============================================
# TESTING THE SCANNER
# ============================================

# First, create a user (if you don't have one)
Invoke-RestMethod -Uri "http://localhost:8000/users" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"email":"test@example.com","password":"password123","workspace_name":"test_workspace"}'

# Login to get auth token
$loginResponse = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" `
  -Method POST `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "username=test@example.com&password=password123"

$token = $loginResponse.access_token

# Manually trigger a scan cycle
Invoke-RestMethod -Uri "http://localhost:8000/markets/scan/run-once" `
  -Method POST `
  -Headers @{ "Authorization" = "Bearer $token" }

# Check scanner status
Invoke-RestMethod -Uri "http://localhost:8000/markets/scan/status" `
  -Method GET `
  -Headers @{ "Authorization" = "Bearer $token" }

# Get top 10 markets (min score 70)
Invoke-RestMethod -Uri "http://localhost:8000/markets/top?limit=10&minScore=70" `
  -Method GET `
  -Headers @{ "Authorization" = "Bearer $token" }

# Get specific market
Invoke-RestMethod -Uri "http://localhost:8000/markets/BTCUSDT" `
  -Method GET `
  -Headers @{ "Authorization" = "Bearer $token" }

# Get market history
Invoke-RestMethod -Uri "http://localhost:8000/markets/history/BTCUSDT?limit=50" `
  -Method GET `
  -Headers @{ "Authorization" = "Bearer $token" }


# ============================================
# USING curl (Alternative)
# ============================================

# Get auth token
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=your@email.com&password=yourpassword"

# Trigger scan (replace YOUR_TOKEN)
curl -X POST http://localhost:8000/markets/scan/run-once `
  -H "Authorization: Bearer YOUR_TOKEN"

# Get top markets
curl "http://localhost:8000/markets/top?limit=10&minScore=70" `
  -H "Authorization: Bearer YOUR_TOKEN"


# ============================================
# DATABASE INSPECTION
# ============================================

# View database file location
Get-Item backend/data/backend.db

# Query with SQLite CLI (if installed)
sqlite3 backend/data/backend.db "SELECT symbol, market_quality, timestamp FROM market_snapshots ORDER BY market_quality DESC LIMIT 10;"

# Or use Python to inspect
python backend/data/inspect-db.py


# ============================================
# LOGS AND DEBUGGING
# ============================================

# Enable debug logging
$env:LOG_LEVEL = "DEBUG"
uvicorn app.main:app --reload --log-level debug

# Test Binance connectivity
python -c "import requests; print(requests.get('https://fapi.binance.com/fapi/v1/ping').json())"


# ============================================
# PRODUCTION DEPLOYMENT
# ============================================

# Set production environment
$env:ENVIRONMENT = "production"
$env:FT_JWT_SECRET = "your-strong-secret-key-here"

# Run with systemd or PM2 (Linux) or NSSM (Windows)
# See deployment/ folder for systemd service examples


# ============================================
# RUNNING THE FRONTEND
# ============================================

# Navigate to frontend directory (in a new terminal)
cd frontend/tradingg_bot_front

# Install dependencies (first time only)
npm install

# Start development server
npm run dev

# Frontend will be available at: http://localhost:5173
# Navigate to "Markets" tab in the UI to view scanner results

