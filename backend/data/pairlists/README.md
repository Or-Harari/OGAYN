# Pairlist Directory

This directory contains auto-generated Freqtrade RemotePairList JSON files.

## Generated Files

After each scanner cycle, the following files are created:

- `pairlist10.json` - Markets with score ≥ 10
- `pairlist20.json` - Markets with score ≥ 20
- `pairlist30.json` - Markets with score ≥ 30
- `pairlist40.json` - Markets with score ≥ 40
- `pairlist50.json` - Markets with score ≥ 50
- `pairlist60.json` - Markets with score ≥ 60
- `pairlist70.json` - Markets with score ≥ 70
- `pairlist80.json` - Markets with score ≥ 80
- `pairlist90.json` - Markets with score ≥ 90

## File Format

Each file follows Freqtrade's RemotePairList format:

```json
{
  "pairs": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
  "refresh_period": 300
}
```

## Usage

Configure Freqtrade to consume these files:

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

See [PAIRLIST_INTEGRATION.md](../../app/market_scanner/PAIRLIST_INTEGRATION.md) for full documentation.
