# Pairlist Configuration Manager - Testing Script (PowerShell)

# =============================================================================
# AUTHENTICATION
# =============================================================================

Write-Host "=== Pairlist Configuration Manager ===" -ForegroundColor Cyan
Write-Host "Authenticating..." -ForegroundColor Yellow

$loginResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8000/auth/token" `
  -Method POST `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "username=user2@example.com&password=1234"

$token = $loginResponse.access_token
$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

Write-Host "✓ Authenticated" -ForegroundColor Green

# =============================================================================
# 1. CREATE REMOTEPAIRLIST CONFIG (Scanner Integration)
# =============================================================================

Write-Host "`n=== 1. Create RemotePairList Configuration ===" -ForegroundColor Cyan

$remotePairlistConfig = @{
    config = @{
        enabled = $true
        pair_whitelist = @()
        pair_blacklist = @("BNB/USDT")
        pairlists = @(
            @{
                method = "RemotePairList"
                pairlist_url = "http://127.0.0.1:8000/api/markets/pairlists/50"
                mode = "whitelist"
                processing_mode = "filter"
                number_assets = 50
                refresh_period = 300
                keep_pairlist_on_failure = $true
            }
        )
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/user" `
  -Method PUT `
  -Headers $headers `
  -Body $remotePairlistConfig

Write-Host "✓ RemotePairList configuration saved" -ForegroundColor Green

# =============================================================================
# 2. CREATE VOLUMEPAIRLIST CONFIG
# =============================================================================

Write-Host "`n=== 2. Create VolumePairList Configuration ===" -ForegroundColor Cyan

$volumePairlistConfig = @{
    config = @{
        enabled = $true
        pair_whitelist = @()
        pair_blacklist = @("BNB/USDT", "BUSD/USDT")
        pairlists = @(
            @{
                method = "VolumePairList"
                number_assets = 30
                sort_key = "quoteVolume"
                min_value = 1000000
                max_value = $null
                refresh_period = 1800
            }
        )
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/user" `
  -Method PUT `
  -Headers $headers `
  -Body $volumePairlistConfig

Write-Host "✓ VolumePairList configuration saved" -ForegroundColor Green

# =============================================================================
# 3. CREATE STATICPAIRLIST CONFIG
# =============================================================================

Write-Host "`n=== 3. Create StaticPairList Configuration ===" -ForegroundColor Cyan

$staticPairlistConfig = @{
    config = @{
        enabled = $true
        pair_whitelist = @("BTC/USDT", "ETH/USDT", "SOL/USDT", "MATIC/USDT")
        pair_blacklist = @()
        pairlists = @(
            @{
                method = "StaticPairList"
                allow_inactive = $false
            }
        )
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/user" `
  -Method PUT `
  -Headers $headers `
  -Body $staticPairlistConfig

Write-Host "✓ StaticPairList configuration saved" -ForegroundColor Green

# =============================================================================
# 4. CREATE PERCENTCHANGEPAIRLIST CONFIG
# =============================================================================

Write-Host "`n=== 4. Create PercentChangePairList Configuration ===" -ForegroundColor Cyan

$percentChangePairlistConfig = @{
    config = @{
        enabled = $true
        pair_whitelist = @()
        pair_blacklist = @()
        pairlists = @(
            @{
                method = "PercentChangePairList"
                number_assets = 20
                sort_key = "percentage"
                sort_direction = "desc"
                min_value = 2
                max_value = 50
                refresh_period = 1800
            }
        )
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/user" `
  -Method PUT `
  -Headers $headers `
  -Body $percentChangePairlistConfig

Write-Host "✓ PercentChangePairList configuration saved" -ForegroundColor Green

# =============================================================================
# 5. CREATE MARKETCAPPAIRLIST CONFIG
# =============================================================================

Write-Host "`n=== 5. Create MarketCapPairList Configuration ===" -ForegroundColor Cyan

$marketCapPairlistConfig = @{
    config = @{
        enabled = $true
        pair_whitelist = @()
        pair_blacklist = @()
        pairlists = @(
            @{
                method = "MarketCapPairList"
                number_assets = 25
                max_rank = 50
                refresh_period = 86400
                mode = "whitelist"
                categories = @("layer-1")
            }
        )
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/user" `
  -Method PUT `
  -Headers $headers `
  -Body $marketCapPairlistConfig

Write-Host "✓ MarketCapPairList configuration saved" -ForegroundColor Green

# =============================================================================
# 6. CREATE CHAINED PAIRLIST CONFIG (Advanced)
# =============================================================================

Write-Host "`n=== 6. Create Chained Pairlist Configuration ===" -ForegroundColor Cyan

$chainedPairlistConfig = @{
    config = @{
        enabled = $true
        pair_whitelist = @()
        pair_blacklist = @("BNB/USDT")
        pairlists = @(
            @{
                method = "VolumePairList"
                number_assets = 50
                sort_key = "quoteVolume"
                min_value = 500000
                refresh_period = 1800
            },
            @{
                method = "RemotePairList"
                mode = "whitelist"
                processing_mode = "filter"
                pairlist_url = "http://127.0.0.1:8000/api/markets/pairlists/40"
                refresh_period = 300
            },
            @{
                method = "PercentChangePairList"
                number_assets = 25
                sort_direction = "desc"
                min_value = 1
                refresh_period = 1800
            }
        )
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/user" `
  -Method PUT `
  -Headers $headers `
  -Body $chainedPairlistConfig

Write-Host "✓ Chained pairlist configuration saved" -ForegroundColor Green

# =============================================================================
# 7. GET CURRENT CONFIGURATION
# =============================================================================

Write-Host "`n=== 7. Get Current Configuration ===" -ForegroundColor Cyan

$currentConfig = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/user" `
  -Method GET `
  -Headers $headers

Write-Host "Current configuration:" -ForegroundColor Yellow
$currentConfig | ConvertTo-Json -Depth 10

# =============================================================================
# 8. EXPORT FOR FREQTRADE
# =============================================================================

Write-Host "`n=== 8. Export Freqtrade Configuration ===" -ForegroundColor Cyan

$freqtradeConfig = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/export-freqtrade" `
  -Method POST `
  -Headers $headers

Write-Host "Freqtrade-compatible configuration:" -ForegroundColor Yellow
$freqtradeConfig | ConvertTo-Json -Depth 10

# Save to file
$freqtradeConfig | ConvertTo-Json -Depth 10 | Out-File "pairlist_config_freqtrade.json" -Encoding UTF8
Write-Host "`n✓ Saved to pairlist_config_freqtrade.json" -ForegroundColor Green

# =============================================================================
# 9. EXAMPLE: BOT-SPECIFIC CONFIGURATION
# =============================================================================

Write-Host "`n=== 9. Create Bot-Specific Configuration (Example) ===" -ForegroundColor Cyan

# First, get list of bots
try {
    $bots = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/bots" `
      -Method GET `
      -Headers $headers

    if ($bots -and $bots.Count -gt 0) {
        $firstBot = $bots[0]
        Write-Host "Creating configuration for bot: $($firstBot.name) (ID: $($firstBot.id))" -ForegroundColor Yellow

        $botPairlistConfig = @{
            config = @{
                enabled = $true
                pair_whitelist = @()
                pair_blacklist = @()
                pairlists = @(
                    @{
                        method = "RemotePairList"
                        pairlist_url = "http://127.0.0.1:8000/api/markets/pairlists/70"
                        number_assets = 20
                        refresh_period = 300
                    }
                )
            }
        } | ConvertTo-Json -Depth 10

        Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/config/pairlist/bot/$($firstBot.id)" `
          -Method PUT `
          -Headers $headers `
          -Body $botPairlistConfig

        Write-Host "✓ Bot-specific configuration saved" -ForegroundColor Green
    } else {
        Write-Host "No bots available for configuration" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Could not configure bot: $_" -ForegroundColor Yellow
}

# =============================================================================
# SUMMARY
# =============================================================================

Write-Host "`n=== Summary ===" -ForegroundColor Cyan
Write-Host @"
✓ Tested all 5 supported pairlist handlers:
  1. RemotePairList - Scanner integration
  2. StaticPairList - Static pair list
  3. VolumePairList - Volume-based filtering
  4. PercentChangePairList - Momentum-based filtering
  5. MarketCapPairList - Market cap ranking

✓ Demonstrated chained pairlist configuration
✓ Exported Freqtrade-compatible config to pairlist_config_freqtrade.json

Next Steps:
1. Copy configuration from pairlist_config_freqtrade.json to your Freqtrade config.json
2. Adjust parameters based on your strategy
3. Start Freqtrade with the new configuration
"@ -ForegroundColor Green

Write-Host "`n=== Testing Complete ===" -ForegroundColor Cyan
