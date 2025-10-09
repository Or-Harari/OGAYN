from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
import pkgutil
import sys
try:
    # Debug instrumentation: write a one-line marker when module loads
    from pathlib import Path as _P
    _dbg_file = _P(os.environ.get('FT_TRADING_CORE_DEBUG_FILE', 'trading_core_debug.log')).resolve()
    if not _dbg_file.parent.exists():
        _dbg_file.parent.mkdir(parents=True, exist_ok=True)
    with _dbg_file.open('a', encoding='utf-8') as _f:
        _f.write('loaded main_strategy module\n')
except Exception:  # pragma: no cover - silent if filesystem locked
    pass
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
from pandas import DataFrame

from .indicators import ema, rsi, bbands  # adx removed with regime
from .base_strategy import CoreBaseStrategy
# DCA removed from core orchestrator; specific strategies may implement.


class MainStrategy(CoreBaseStrategy):
    """Minimal baseline strategy.

    Responsibilities retained:
        - Optional discovery of additional strategies (if user supplies strategy_paths)
        - Optional single active_strategy delegation
        - Decision log (if enabled in meta)

    Removed responsibilities (now strategy-specific if desired):
        - Regime detection / regime switching
        - DCA / position adjustment logic
        - Automatic multi-regime registry fan-out
        - Mass indicator orchestration (only delegates to active strategy now)
    """
        # Removed ATR/regime helpers (strategies can implement if needed)

    timeframe = "1m"
    informative_timeframe = "1h"  # still used for informative_pairs if consumers rely on it
    startup_candle_count = 200  # conservative default; strategies may override
    can_short = False

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    minimal_roi = {"0": 1.0}
    stoploss = -0.50
    trailing_stop = False
    use_custom_stoploss = False

    protections = [{"method": "CooldownPeriod", "stop_duration_candles": 2}]

    def __init__(self, config: dict) -> None:  # type: ignore[override]
        super().__init__(config)  # type: ignore
        self.logger = logging.getLogger(f"freqtrade.strategy.{self.__class__.__name__}")
        # Instrumentation: log pairlist-related config early to debug StaticPairList errors
        try:
            pw = self.config.get("pair_whitelist")  # type: ignore[attr-defined]
            pls = self.config.get("pairlists")  # type: ignore[attr-defined]
            self.logger.info(f"DEBUG Pairlist config: pair_whitelist={pw} pairlists={pls}")
            if (pls and isinstance(pls, list) and any(isinstance(x, dict) and x.get("method") == "StaticPairList" for x in pls)) and not pw:
                self.logger.error("DEBUG Detected StaticPairList without pair_whitelist at strategy init")
        except Exception:  # pragma: no cover
            pass
        self.meta = self._load_meta_config(config)
        # Minimal strategy registry (no regimes) just for optional active strategy
        self._strategy_registry = self._discover_strategies()
        self.active_strategy = None
        active_cfg = (self.meta.get("active_strategy") or {})
        active_class = active_cfg.get("class")
        active_name = active_cfg.get("name")
        if active_name and active_name in self._strategy_registry:
            try:
                self.active_strategy = self._strategy_registry[active_name]()
                self.logger.info(f"Active strategy set to '{active_name}' via registry")
            except Exception as e:  # pragma: no cover
                self.logger.warning(f"Failed to instantiate active strategy by name '{active_name}': {e}")
        elif active_class:
            try:
                self.active_strategy = self._build_strategy_instance(active_class)
                self.logger.info(f"Active strategy set to {active_class}")
            except Exception as e:  # pragma: no cover
                self.logger.warning(f"Failed to load active strategy '{active_class}': {e}")

        log_cfg = self.meta.get("decision_log", {})
        self.decision_log_enable = bool(log_cfg.get("enable", True))
        # user_data_dir provided by freqtrade config (in newer versions) or fallback to '.'
        user_data_dir = Path(self.config.get("user_data_dir", "."))  # type: ignore[attr-defined]
        default_log_path = user_data_dir / "logs" / "decision_log.csv"
        self.decision_log_path = str(log_cfg.get("path", default_log_path))
        try:
            os.makedirs(os.path.dirname(self.decision_log_path), exist_ok=True)
        except Exception:  # pragma: no cover
            pass
        self._last_logged_ts = {}  # type: Dict[str, Any]

    # ----------------- Meta -----------------
    def _load_meta_config(self, config: dict) -> dict:
        defaults = {
            "decision_log": {"enable": True, "path": None},
            "strategy_paths": [],
            "strategies": {},  # kept for potential active strategy selection
            # active_strategy: { name|class } may live at top-level meta
        }
        ci = (config or {}).get("custom_info", {})
        sp = (config or {}).get("strategy_parameters", {})
        user_meta = ci.get("meta") or sp.get("meta") or {}

        def deep_merge(a: dict, b: dict):
            for k, v in b.items():
                if isinstance(v, dict) and isinstance(a.get(k), dict):
                    deep_merge(a[k], v)
                else:
                    a[k] = v
            return a

        return deep_merge(defaults, user_meta)

    # --------------- Discovery ---------------
    def _build_strategy_instance(self, class_path: str):
        module_path, class_name = class_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls()

    def _is_strategy_class(self, obj) -> bool:
        try:
            from .base_strategy import CoreBaseStrategy as _CBS  # local import to avoid circulars
            if issubclass(obj, _CBS) and obj is not _CBS:
                return True
        except Exception:
            pass
        required = ["entry_mask", "exit_mask"]
        return all(callable(getattr(obj, m, None)) for m in required)

    def _scan_dir_for_strategies(self, root: str, registry: dict) -> None:
        p = Path(root)
        if not p.exists():
            return
        for py in p.rglob("*.py"):
            if py.name.startswith("_"):
                continue
            try:
                modname = f"ext_strat_{abs(hash(str(py)))}"
                spec = importlib.util.spec_from_file_location(modname, str(py))
                if not spec or not spec.loader:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[attr-defined]
                for _, obj in inspect.getmembers(mod, inspect.isclass):
                    if self._is_strategy_class(obj):
                        key = getattr(obj, "name", None) or obj.__name__
                        if key not in registry:
                            registry[str(key)] = obj
            except Exception:
                continue

    def _discover_strategies(self) -> dict:
        registry: Dict[str, Any] = {}
        # Validate user_data_dir explicitly (no silent fallbacks)
        base_root = Path(self.config.get("user_data_dir", "")).expanduser().resolve()  # type: ignore[attr-defined]
        if not base_root.exists():
            raise RuntimeError(
                "Configured user_data_dir does not exist. Workspace must be created explicitly; no implicit fallback."
            )
        if base_root.name != "user_data":  # freqtrade should pass the user_data folder
            raise RuntimeError(
                f"user_data_dir must point to a 'user_data' folder (got '{base_root}')."
            )

        # Candidate paths: local strategies/_strategies plus any meta.strategy_paths and shared strategies path if specified
        extra_paths = list(self.meta.get("strategy_paths") or [])

        # Ensure shared strategies path if not already present and exists (repo-level shared package)
        repo_shared = (base_root.parent.parent / "shared" / "strategies" / "_strategies")
        if repo_shared.exists():
            shared_str = str(repo_shared.resolve())
            if shared_str not in extra_paths:
                extra_paths.append(shared_str)

        # Always include local workspace _strategies relative path
        local_pkg_path = base_root / "strategies" / "_strategies"
        search_roots: list[str] = []
        if local_pkg_path.exists():
            search_roots.append(str(local_pkg_path.resolve()))
        # Add extra configured paths (resolve relative to workspace root)
        for p in extra_paths:
            abs_p = p if os.path.isabs(p) else str((base_root / p).resolve())
            if abs_p not in search_roots:
                search_roots.append(abs_p)

        # Temporarily extend sys.path for discovery (isolated, no permanent mutation order issues)
        original_sys_path = list(sys.path)
        try:
            for root in search_roots:
                if root not in sys.path:
                    sys.path.insert(0, root)
            # Attempt to import local _strategies package if present
            try:
                import _strategies as strat_pkg  # type: ignore
                for _, modname, ispkg in pkgutil.iter_modules(strat_pkg.__path__, prefix="_strategies."):
                    if ispkg:
                        continue
                    try:
                        mod = importlib.import_module(modname)
                    except Exception:
                        continue
                    for _, obj in inspect.getmembers(mod, inspect.isclass):
                        if self._is_strategy_class(obj):
                            key = getattr(obj, "name", None) or obj.__name__
                            if key not in registry:
                                registry[str(key)] = obj
            except Exception:
                pass
            # Scan every root (covers shared + extras)
            for root in search_roots:
                self._scan_dir_for_strategies(root, registry)
        finally:
            sys.path = original_sys_path
        return registry

    # --------------- Logging ---------------
    def _log_decision(self, df: DataFrame, metadata: dict) -> None:
        if not getattr(self, "decision_log_enable", False) or df is None or df.empty:
            return
        try:
            pair = metadata.get("pair", "?")
            last_logged = self._last_logged_ts.get(pair)
            if last_logged is not None:
                to_log = df.loc[df.index > last_logged]
            else:
                to_log = df
            if to_log.empty:
                return
            if self.active_strategy is not None:
                active_label = getattr(self.active_strategy, "name", None) or self.active_strategy.__class__.__name__
                strategy_series = pd.Series(active_label, index=to_log.index)
            else:
                regime_series = to_log.get("regime", pd.Series(index=to_log.index, dtype=str)).fillna("")
                label_map = {k: (getattr(v, "name", None) or v.__class__.__name__) for k, v in self._regime_strategies.items()}
                strategy_series = regime_series.map(label_map).fillna("none")
            rows = []
            for ts, row in to_log.iterrows():
                rows.append({
                    "time": str(ts),
                    "pair": pair,
                    "regime": str(row.get("regime", "")),
                    "strategy": str(strategy_series.loc[ts]) if ts in strategy_series.index else "none",
                    "close": float(row.get("close", np.nan)),
                    "ema_fast": float(row.get("ema_fast", np.nan)),
                    "ema_slow": float(row.get("ema_slow", np.nan)),
                    "rsi": float(row.get("rsi", np.nan)),
                    "bb_u": float(row.get("bb_u", np.nan)),
                    "bb_m": float(row.get("bb_m", np.nan)),
                    "bb_l": float(row.get("bb_l", np.nan)),
                    "macd": float(row.get("macd", np.nan)),
                    "macd_hist": float(row.get("macd_hist", np.nan)),
                    "volume": float(row.get("volume", np.nan)),
                    "vol_ma": float(row.get("vol_ma", np.nan)),
                    "vol_ok": bool(row.get("vol_ok", False)),
                    "enter_long": int(row.get("enter_long", 0)),
                    "enter_tag": str(row.get("enter_tag", "")),
                    "exit_long": int(row.get("exit_long", 0)),
                })
            file_exists = os.path.isfile(self.decision_log_path)
            import csv
            fieldnames = list(rows[0].keys())
            with open(self.decision_log_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(rows)
            self._last_logged_ts[pair] = to_log.index[-1]
        except Exception:  # pragma: no cover
            self.logger.debug("Decision log error", exc_info=True)

    # --------------- Informative ---------------
    def informative_pairs(self):  # type: ignore[override]
        pairs = self.dp.current_whitelist()  # type: ignore[attr-defined]
        return [(p, self.informative_timeframe) for p in pairs]

    # --------------- Indicators ---------------
    # Removed ATR/regime helpers (strategies can implement if needed)

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:  # type: ignore[override]
        if df.empty:
            return df

        def compute_indicator(spec_key: str, spec: dict):
            t = spec.get("type")
            if t == "ema":
                length = int(spec.get("length", 9))
                src = spec.get("source", "close")
                return ema(df[src], length)
            if t == "rsi":
                length = int(spec.get("length", 14))
                return rsi(df["close"], length)
            if t == "bbands":
                length = int(spec.get("length", 20))
                stdev = float(spec.get("stdev", 2.0))
                bu, bm, bl = bbands(df["close"], length, stdev)
                cols = spec.get("columns", ["bb_u", "bb_m", "bb_l"])
                return {cols[0]: bu, cols[1]: bm, cols[2]: bl}
            if t == "macd":
                f = int(spec.get("fast", 12))
                s = int(spec.get("slow", 26))
                sg = int(spec.get("signal", 9))
                mf = ema(df["close"], f)
                ms = ema(df["close"], s)
                macd_line = mf - ms
                macd_sig = ema(macd_line, sg)
                macd_hist = macd_line - macd_sig
                cols = spec.get("columns", ["macd", "macd_signal", "macd_hist"])
                return {cols[0]: macd_line, cols[1]: macd_sig, cols[2]: macd_hist}
            if t == "sma":
                length = int(spec.get("length", 20))
                on = spec.get("on", "volume")
                return df[on].rolling(length).mean()
            return None

        reqs: Dict[str, Any] = {}
        if self.active_strategy is not None and hasattr(self.active_strategy, "required_indicators"):
            reqs.update(self.active_strategy.required_indicators() or {})
        for key, spec in reqs.items():
            res = compute_indicator(key, spec)
            if isinstance(res, pd.Series):
                df[key] = res
            elif isinstance(res, dict):
                for k, v in res.items():
                    df[k] = v

        # No regime column enforced; strategies can add their own metadata.

        if self.active_strategy is not None and hasattr(self.active_strategy, "populate_indicators"):
            self.active_strategy.populate_indicators(df)
        return df

    # --------------- Entries / Exits ---------------
    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:  # type: ignore[override]
        if df.empty:
            df["enter_long"] = 0
            return df
        df["enter_long"] = 0
        if self.active_strategy is not None:
            mask = self.active_strategy.entry_mask(df)
            df.loc[mask, "enter_long"] = 1
            tag = getattr(self.active_strategy, "name", None) or self.active_strategy.__class__.__name__
            df.loc[mask, "enter_tag"] = tag
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:  # type: ignore[override]
        if df.empty:
            df["exit_long"] = 0
            return df
        df["exit_long"] = 0
        if self.active_strategy is not None:
            mask = self.active_strategy.exit_mask(df)
            df.loc[mask, "exit_long"] = 1
        self._log_decision(df, metadata)
        return df

    # DCA and position adjustment removed; specific strategies can subclass and implement.

# Additional post-definition diagnostics (only once at module import)
try:  # pragma: no cover
    from pathlib import Path as _P2
    _dbg_file2 = _P2(os.environ.get('FT_TRADING_CORE_DEBUG_FILE', 'trading_core_debug.log')).resolve()
    import inspect as _inspect
    import importlib as _importlib
    # Record module, file, and MRO info to ensure resolver sees a proper subclass
    with _dbg_file2.open('a', encoding='utf-8') as _f:
        _f.write(f'MainStrategy qualname={MainStrategy.__qualname__} module={MainStrategy.__module__}\n')
        _f.write(f'MainStrategy file={_inspect.getsourcefile(MainStrategy)}\n')
        _f.write('MainStrategy MRO=' + ' > '.join(c.__name__ for c in MainStrategy.mro()) + '\n')
        try:  # dynamic import guard
            import importlib as _il
            _mod = _il.import_module('freqtrade.strategy')
            _IS = getattr(_mod, 'IStrategy', None)
            if _IS is not None:
                _f.write(f'ISubclass(MainStrategy, IStrategy)={issubclass(MainStrategy, _IS)}\n')
                try:
                    _f.write(f'IStrategy module path={_inspect.getsourcefile(_IS)}\n')
                except Exception:
                    pass
            else:
                _f.write('IStrategy symbol not found in freqtrade.strategy\n')
        except Exception as _e:
            _f.write(f'Could not import freqtrade.strategy: {_e}\n')
        _f.write('--- end diagnostics ---\n')
except Exception:
    pass
