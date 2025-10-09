# Trading Core Migration

This document describes the refactor that moved the orchestration / meta strategy logic out of the legacy `user_data/strategies` tree into a versioned, testable backend package: `backend.app.trading_core`.

## Summary

| Before | After |
|--------|-------|
| `user_data/strategies/meta_strategy.py` contained a large orchestrator class mixing discovery, indicators, regime logic and DCA | Canonical `MainStrategy` lives in `backend/app/trading_core/main_strategy.py` |
| Ad‑hoc indicator helpers scattered / imported via implicit `sys.path` | Indicators consolidated under `backend/app/trading_core/indicators` |
| Direct imports from `user_data/strategies` in shared strategies | Shared strategies import indicators from `backend.app.trading_core.indicators` |
| Dynamic discovery sometimes relied on ambient PYTHONPATH including repo roots | Discovery now performs a controlled, temporary `sys.path` insertion of workspace + shared strategy roots |
| Silent fallbacks if a workspace path was invalid | Hard failure with explicit RuntimeError – no implicit fallback |
| `meta_strategy.py` loaded by config | A thin per‑workspace shim `user_data/strategies/MainStrategy.py` imports the core package |

## Goals

1. Decouple strategy orchestration from mutable per‑user `user_data` trees.
2. Provide a stable import path for backtests, live runs and API initiated bot sessions.
3. Eliminate hidden import side effects and fragile relative path hacks.
4. Enable incremental evolution (adding regime types, substrategies, indicators) without rewriting every workspace.
5. Make deprecation explicit – old entry points raise immediately so misconfiguration surfaces early.

## New Layout

```
backend/app/trading_core/
  __init__.py            # exports MainStrategy
  main_strategy.py       # Orchestrator (regimes, discovery, logging, DCA hooks)
  base.py                # BaseStrategy abstraction for light plug‑ins
  indicators/            # ema, rsi, bbands, adx utilities
  substrategies/
    dca.py               # DCA scaling logic
```

Each user (and bot) workspace now receives, on creation:

```
workspaces/<name>/user_data/strategies/MainStrategy.py  # shim
```

Shim content (simplified):

```python
import sys, os
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)
from backend.app.trading_core.main_strategy import MainStrategy
```

Freqtrade config continues to reference `"strategy": "MainStrategy"` – the shim resolves to the core class.

## Discovery Changes

`MainStrategy._discover_strategies()` now:

1. Validates `user_data_dir` exists and is literally a `user_data` folder (no fallback).
2. Builds a list of search roots:
   - Workspace `_strategies` directory.
   - All entries in `meta.strategy_paths` (resolved relative to workspace if not absolute).
   - Repo shared path `shared/strategies/_strategies` (auto-added if it exists and not duplicated).
3. Temporarily injects these paths at the front of `sys.path` while importing / scanning.
4. Restores the original `sys.path` afterward (no global pollution).

Strategy classes are accepted if they:
- Subclass `BaseStrategy` (excluding the base itself), OR
- Are duck-typed: expose callable `entry_mask(df)` and `exit_mask(df)`.

First occurrence of a name wins to keep precedence predictable.

## Deprecation of `meta_strategy.py`

The legacy file now contains only:

```python
raise RuntimeError("meta_strategy.py is deprecated ...")
```

Any lingering config pointing to it will fail fast, prompting an update.

## Configuration Impact

Meta configuration (`meta.json` or embedded under `custom_info.meta`) remains structurally the same:

```json
{
  "strategy_paths": ["./strategies/_strategies", "C:/path/to/extra/strategies"],
  "regime": {"enable": true, "tf": "1h", "ema_len": 200, "adx_thresh": 20},
  "decision_log": {"enable": true, "path": null},
  "strategies": {},
  "dca": {"enable": true, "total_budget": 2000.0, "mode": "martingale", "thresholds": [3.0, 6.0, 10.0], "max_adds": 3},
  "active_strategy": {"name": "TrendStrategy"}
}
```

`active_strategy` may reference a discovered strategy by its class `name` (preferred) or fully-qualified import path via `class`.

## Logging & DCA

Unchanged conceptually; decision log now writes under the workspace `logs/decision_log.csv` (path override still supported). DCA logic isolated in `substrategies/dca.py` and injected only if enabled.

## Migration Steps (Manual Workspaces)

If you have an older workspace that predates the automated shim creation:

1. Delete (or ignore) `user_data/strategies/meta_strategy.py` if present.
2. Create `user_data/strategies/MainStrategy.py` with the shim content above.
3. Ensure your config points to `"strategy": "MainStrategy"`.
4. (Optional) Add shared strategy path to `meta.strategy_paths`:
   `"C:/.../ft-bot/shared/strategies/_strategies"`.
5. Remove any direct imports of indicators from legacy locations; import from `backend.app.trading_core.indicators`.

## Failure Modes & Diagnostics

| Symptom | Likely Cause | Resolution |
|---------|--------------|-----------|
| RuntimeError: user_data_dir does not exist | Misconfigured `--userdir` or API-provided path | Point Freqtrade to a valid workspace created via backend API | 
| RuntimeError from meta_strategy.py | Config still references deprecated file | Change strategy to `MainStrategy` (shim) |
| Strategy list empty | No valid `_strategies` packages or missing paths; class signatures invalid | Add path to `meta.strategy_paths` or fix strategy class/duck-typed methods |
| Indicators missing columns | Strategy declared required indicator not implemented in `required_indicators()` | Implement or adjust strategy requirements |

## Future Extensions

- Additional regime classifiers (volatility, volume regime).
- Plug-in registry for custom indicator bundles.
- Test harness for strategy discovery (pytest fixtures around temporary dirs).
- Optional signature-based caching of discovery results.

---
Last updated: 2025-10-04
