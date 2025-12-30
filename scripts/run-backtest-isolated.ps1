param(
    [string]$Strategy = "SupplyDemandStructureStrategyHTF_TrendV3",
    [string]$StrategyPath = "C:\Users\orhar\ft-bot\workspaces\user3\user\strategies",
    [string]$Config = "C:\Users\orhar\ft-bot\bt-userdir\configs\backtest.json",
    [string]$UserDir = "C:\Users\orhar\ft-bot\bt-userdir",
    [string]$DbUrl = "sqlite:///C:/Users/orhar/ft-bot/bt-userdir/backtest.sqlite",
    [string]$Timeframe = "15m",
    [string]$Timerange = "",
    [string[]]$Pairs = @("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"),
    [switch]$ExportTrades,
    [string]$PythonExe = "python"
)

# Isolate Python bytecode cache so backtests don't touch live strategy caches
$env:PYTHONPYCACHEPREFIX = Join-Path $UserDir "pycache"

<#
 Determine how to invoke freqtrade:
 - Prefer the freqtrade CLI if available in PATH
 - Otherwise fallback to `python -m freqtrade`
#>
$freqtradeCmd = Get-Command freqtrade -ErrorAction SilentlyContinue
if ($null -ne $freqtradeCmd) {
    $exe = "freqtrade"
    $args = @(
        "backtesting",
        "--strategy", $Strategy,
        "--strategy-path", $StrategyPath,
        "--config", $Config,
        "--userdir", $UserDir,
        "--timeframe", $Timeframe
    )
} else {
    # Fallback to python -m freqtrade
    $pythonCmd = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if ($null -eq $pythonCmd) {
        # Try Windows py launcher
        $PythonExe = "py"
        $pythonCmd = Get-Command $PythonExe -ErrorAction SilentlyContinue
    }
    if ($null -eq $pythonCmd) {
        Write-Error "Neither 'freqtrade' CLI nor a Python executable ('$PythonExe') was found in PATH. Please install Freqtrade or provide Python via -PythonExe."
        exit 127
    }
    $exe = $PythonExe
    $args = @(
        "-m", "freqtrade",
        "backtesting",
        "--strategy", $Strategy,
        "--strategy-path", $StrategyPath,
        "--config", $Config,
        "--userdir", $UserDir,
        "--timeframe", $Timeframe
    )
}

if ($Timerange -and $Timerange.Trim().Length -gt 0) {
    $args += @("--timerange", $Timerange)
}

    if ($Pairs -and $Pairs.Count -gt 0) {
        $args += @("-p")
        $args += $Pairs
    }

if ($ExportTrades) {
    $args += @("--export", "trades")
}

# Run
Write-Host "Running isolated backtest:" -ForegroundColor Cyan
Write-Host "$exe $($args -join ' ')"
& $exe @args

if ($LASTEXITCODE -ne 0) {
    Write-Error "Backtesting failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "Backtest completed successfully." -ForegroundColor Green
