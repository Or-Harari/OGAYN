# Pairlist Testing Commands (PowerShell)

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================

# Set pairlist format (slash format for standard Freqtrade: BTC/USDT)
$env:PAIRLIST_FORMAT = "slash"

# Set scanner interval (also used as refresh_period in JSON files)
$env:MARKET_SCANNER_INTERVAL_SECONDS = "300"

# =============================================================================
# AUTHENTICATION
# =============================================================================

# Login to get JWT token (replace with your credentials)
$loginResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8000/auth/token" `
  -Method POST `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "username=user2@example.com&password=1234"

$token = $loginResponse.access_token
Write-Host "Token obtained: $($token.Substring(0,20))..." -ForegroundColor Green

# =============================================================================
# PAIRLIST ENDPOINTS
# =============================================================================

# 1. List all available pairlists
Write-Host "`n=== List Available Pairlists ===" -ForegroundColor Cyan
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/markets/pairlists" `
  -Method GET `
  -Headers @{ Authorization = "Bearer $token" } | ConvertTo-Json -Depth 3

# 2. Get a specific pairlist (threshold 50)
Write-Host "`n=== Get Pairlist 50 ===" -ForegroundColor Cyan
$pairlist50 = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/markets/pairlists/50" `
  -Method GET `
  -Headers @{ Authorization = "Bearer $token" }

Write-Host "Pairs count: $($pairlist50.pairs.Count)" -ForegroundColor Yellow
Write-Host "Refresh period: $($pairlist50.refresh_period)s" -ForegroundColor Yellow
Write-Host "First 10 pairs:" -ForegroundColor Yellow
$pairlist50.pairs | Select-Object -First 10

# 3. Manually trigger pairlist generation
Write-Host "`n=== Trigger Pairlist Generation ===" -ForegroundColor Cyan
$generateResult = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/markets/pairlists/generate" `
  -Method POST `
  -Headers @{ Authorization = "Bearer $token" }

Write-Host "Generation result:" -ForegroundColor Yellow
$generateResult | ConvertTo-Json -Depth 3

# =============================================================================
# FILE INSPECTION
# =============================================================================

# View generated files in data/pairlists/
Write-Host "`n=== Pairlist Files ===" -ForegroundColor Cyan
$pairlistDir = "data/pairlists"
if (Test-Path $pairlistDir) {
    Get-ChildItem $pairlistDir -Filter "pairlist*.json" | ForEach-Object {
        $content = Get-Content $_.FullName | ConvertFrom-Json
        Write-Host "$($_.Name) - $($content.pairs.Count) pairs" -ForegroundColor Yellow
    }
} else {
    Write-Host "Directory not found: $pairlistDir" -ForegroundColor Red
}

# =============================================================================
# TESTING DIFFERENT THRESHOLDS
# =============================================================================

Write-Host "`n=== Testing All Thresholds ===" -ForegroundColor Cyan
$thresholds = @(10, 20, 30, 40, 50, 60, 70, 80, 90)

foreach ($threshold in $thresholds) {
    try {
        $pairlist = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/markets/pairlists/$threshold" `
          -Method GET `
          -Headers @{ Authorization = "Bearer $token" }
        
        Write-Host "Threshold $threshold : $($pairlist.pairs.Count) pairs" -ForegroundColor Green
    } catch {
        Write-Host "Threshold $threshold : Not available" -ForegroundColor Red
    }
}

# =============================================================================
# FREQTRADE CONFIGURATION EXAMPLE
# =============================================================================

Write-Host "`n=== Freqtrade Configuration Example ===" -ForegroundColor Cyan
Write-Host @"
Note: bearer_token is OPTIONAL in RemotePairList. Include it only if your API requires authentication.

Option 1 - Without authentication (for public endpoints):
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
      "number_assets": 50,
      "refresh_period": 300,
      "keep_pairlist_on_failure": true
    }
  ]
}

Option 2 - With authentication (if required):
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
      "bearer_token": "$token",
      "number_assets": 50,
      "refresh_period": 300,
      "keep_pairlist_on_failure": true
    }
  ]
}
"@ -ForegroundColor Yellow

# =============================================================================
# PLAIN FORMAT TESTING (BTCUSDT instead of BTC/USDT)
# =============================================================================

Write-Host "`n=== Testing Plain Format ===" -ForegroundColor Cyan
Write-Host "To use plain format (BTCUSDT instead of BTC/USDT):" -ForegroundColor Yellow
Write-Host "1. Set: `$env:PAIRLIST_FORMAT = 'plain'" -ForegroundColor Yellow
Write-Host "2. Restart backend" -ForegroundColor Yellow
Write-Host "3. Regenerate pairlists: POST /api/markets/pairlists/generate" -ForegroundColor Yellow

# =============================================================================
# VERIFICATION
# =============================================================================

Write-Host "`n=== Verification ===" -ForegroundColor Cyan

# Check if scanner is running
$scanStatus = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/markets/scan/status" `
  -Method GET `
  -Headers @{ Authorization = "Bearer $token" }

Write-Host "Scanner status: $($scanStatus.status)" -ForegroundColor Yellow
Write-Host "Last scan: $($scanStatus.last_scan_time)" -ForegroundColor Yellow
Write-Host "Markets scanned: $($scanStatus.markets_count)" -ForegroundColor Yellow

# Check if pairlist directory exists and has files
$pairlistFiles = Get-ChildItem "data/pairlists" -Filter "pairlist*.json" -ErrorAction SilentlyContinue
if ($pairlistFiles) {
    Write-Host "`n✓ Pairlist generation working! Found $($pairlistFiles.Count) files" -ForegroundColor Green
} else {
    Write-Host "`n✗ No pairlist files found. Try triggering manual generation." -ForegroundColor Red
}

Write-Host "`n=== Testing Complete ===" -ForegroundColor Cyan
