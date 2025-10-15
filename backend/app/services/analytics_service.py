from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import importlib.util
import sys

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..db.models import User, Bot
from .bot_service import proxy_freqtrade_api


def _host_strategy_path(user_root: Path, bot_userdir: Path, spath: Optional[str]) -> Optional[Path]:
    """Inverse-map strategy_path written for the container back to a host path.

    Maps:
    - /freqtrade/user_data/<rel> -> bot_userdir/<rel>
    - /freqtrade/extra_strategies/<rel> -> user_root/user/strategies[/variants]/<rel>
    If the path is already an absolute host path, returns it as Path if exists.
    Returns None if cannot resolve.
    """
    if not spath:
        return None
    try:
        p = Path(spath)
        if p.is_absolute() and p.drive:  # Windows absolute path
            return p if p.exists() else None
    except Exception:
        pass
    # Container mappings
    try:
        if spath.startswith("/freqtrade/user_data/"):
            rel = spath[len("/freqtrade/user_data/") :]
            host = bot_userdir / Path(rel)
            return host if host.exists() else None
        if spath.startswith("/freqtrade/extra_strategies/"):
            rel = spath[len("/freqtrade/extra_strategies/") :]
            pref = (user_root / "user" / "strategies" / "variants").resolve()
            base = pref if pref.exists() else (user_root / "user" / "strategies").resolve()
            host = base / Path(rel)
            return host if host.exists() else None
    except Exception:
        return None
    # Maybe it's a relative path to bot_userdir
    candidate = (bot_userdir / spath).resolve()
    return candidate if candidate.exists() else None


def _read_bot_config_path(bot_userdir: Path) -> Optional[Path]:
    cfg = bot_userdir / "configs" / "config.generated.json"
    return cfg if cfg.exists() else None


def _load_config(cfg_path: Path) -> dict:
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _import_strategy(user_root: Path, bot_userdir: Path, cfg: dict) -> tuple[Optional[type], Optional[str]]:
    """Import the strategy class referenced by config. Returns (class, timeframe or None).

    Adds strategy_path and repo root to sys.path temporarily to allow imports.
    """
    strat = cfg.get("strategy")
    spath = cfg.get("strategy_path")
    if not strat or not spath:
        return None, None
    host_spath = _host_strategy_path(user_root, bot_userdir, spath)
    if not host_spath:
        return None, None
    strat_file = host_spath / f"{strat}.py"
    if not strat_file.exists():
        return None, None
    # Extend sys.path with strategy path and repo root
    add_paths: list[str] = []
    try:
        add_paths.append(str(host_spath))
    except Exception:
        pass
    try:
        file_path = Path(__file__).resolve()
        repo_root = file_path.parents[3] if len(file_path.parents) >= 4 else file_path.parent
        add_paths.append(str(repo_root))
    except Exception:
        pass
    original_sys_path = list(sys.path)
    try:
        for p in add_paths:
            if p and p not in sys.path:
                sys.path.insert(0, p)
        spec = importlib.util.spec_from_file_location(strat, str(strat_file))
        if spec is None or spec.loader is None:
            return None, None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        cls = getattr(mod, strat, None)
        # Extract primary timeframe if present
        timeframe = None
        if cls is not None and hasattr(cls, "timeframe") and isinstance(getattr(cls, "timeframe"), str):
            timeframe = getattr(cls, "timeframe")
        return cls, timeframe
    except Exception:
        return None, None
    finally:
        sys.path = original_sys_path


def _df_from_candles(candles: Any):
    """Create a pandas DataFrame from /pair_candles response.

    Supports common shapes: list of dicts with keys [date, open, high, low, close, volume].
    Returns (df or None, error string or None).
    """
    try:
        import pandas as pd  # type: ignore
    except Exception as e:
        return None, f"pandas not available: {e}"
    try:
        if isinstance(candles, dict) and "data" in candles:
            data = candles["data"]
        else:
            data = candles
        if not isinstance(data, list) or not data:
            return None, "no candle data"
        # Normalize to dicts
        if isinstance(data[0], dict):
            rows = data
        elif isinstance(data[0], (list, tuple)) and len(data[0]) >= 6:
            # Try index order: [date, open, high, low, close, volume]
            keys = ["date", "open", "high", "low", "close", "volume"]
            rows = [dict(zip(keys, r[:6])) for r in data]
        else:
            return None, "unsupported candle format"
        df = pd.DataFrame(rows)
        # Standardize columns
        required = ["date", "open", "high", "low", "close", "volume"]
        for k in required:
            if k not in df.columns:
                return None, f"missing column: {k}"
        # Convert date to pandas datetime
        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.dropna(subset=["date"]).reset_index(drop=True)
        return df, None
    except Exception as e:
        return None, str(e)


def _apply_strategy(cls: Any, timeframe: Optional[str], df):
    """Apply strategy methods to compute indicators and signals. Returns dataframe or None.

    Gracefully degrades if methods are absent.
    """
    try:
        if cls is None or df is None:
            return None
        inst = cls()
        if timeframe and not getattr(inst, "timeframe", None):
            try:
                setattr(inst, "timeframe", timeframe)
            except Exception:
                pass
        # Freqtrade signature: (dataframe, metadata)
        meta = {"pair": None, "timeframe": timeframe}
        if hasattr(inst, "populate_indicators"):
            df = inst.populate_indicators(df.copy(), meta)
        if hasattr(inst, "populate_buy_trend"):
            df = inst.populate_buy_trend(df, meta)
        if hasattr(inst, "populate_sell_trend"):
            df = inst.populate_sell_trend(df, meta)
        return df
    except Exception:
        return None


def fetch_candles(bot: Bot, pair: str, timeframe: str, limit: int = 200) -> Any:
    # Use the generic proxy to call /pair_candles
    params = {"pair": pair, "timeframe": timeframe, "limit": str(limit)}
    status, payload = proxy_freqtrade_api(bot, "GET", "/pair_candles", params=params)
    if status >= 400:
        raise HTTPException(status_code=status, detail=payload)
    return payload


def snapshot(db: Session, user: User, bot: Bot, limit: int = 200) -> dict:
    """Build a one-shot analytics snapshot for a bot.

    - Reads config to identify strategy and pairs
    - Fetches candles via REST for each pair/timeframe
    - Computes indicators and signals using the strategy class (best-effort)
    - Reads open trades/orders/balance/performance via REST
    """
    user_root = Path(user.workspace_root).resolve()
    bot_userdir = Path(bot.userdir).resolve()

    cfg_path = _read_bot_config_path(bot_userdir)
    cfg: dict = {}
    if cfg_path:
        cfg = _load_config(cfg_path)
    strategy_cls, primary_timeframe = _import_strategy(user_root, bot_userdir, cfg)

    # Pairs
    pairs: list[str] = []
    try:
        if isinstance(cfg.get("pairs"), list):
            pairs = cfg.get("pairs") or []
        elif isinstance(cfg.get("pair_whitelist"), list):
            pairs = cfg.get("pair_whitelist") or []
    except Exception:
        pairs = []

    # Timeframes: prefer strategy timeframe, else fallback to config timeframe or default '5m'
    tfs: list[str] = []
    if primary_timeframe:
        tfs.append(primary_timeframe)
    try:
        if isinstance(cfg.get("timeframe"), str) and cfg.get("timeframe") not in tfs:
            tfs.append(cfg.get("timeframe"))
    except Exception:
        pass
    if not tfs:
        tfs = ["5m"]

    series: list[dict] = []
    # Iterate pairs/timeframes
    for pair in pairs:
        for tf in tfs:
            candles = fetch_candles(bot, pair, tf, limit=limit)
            df, err = _df_from_candles(candles)
            indicators: dict[str, list] = {}
            signals: dict[str, list] = {}
            if df is not None:
                # Apply strategy best-effort
                sdf = _apply_strategy(strategy_cls, tf, df)
                if sdf is not None:
                    # Extract indicators as columns not in basic OHLCV/date
                    base_cols = {"date", "open", "high", "low", "close", "volume"}
                    for col in sdf.columns:
                        if col not in base_cols:
                            try:
                                indicators[col] = [None if pd.isna(v) else float(v) for v in sdf[col].tolist()]  # type: ignore
                            except Exception:
                                pass
                    # Common signal columns
                    for col in ("buy", "sell", "enter_long", "exit_long"):
                        if col in sdf.columns:
                            try:
                                signals[col] = [bool(v) if v in (0, 1, True, False) else False for v in sdf[col].tolist()]
                            except Exception:
                                pass
                # Serialize candles compactly
                try:
                    candles_out = [
                        {
                            "date": str(df.loc[i, "date"]),
                            "open": float(df.loc[i, "open"]),
                            "high": float(df.loc[i, "high"]),
                            "low": float(df.loc[i, "low"]),
                            "close": float(df.loc[i, "close"]),
                            "volume": float(df.loc[i, "volume"]),
                        }
                        for i in range(len(df))
                    ]
                except Exception:
                    candles_out = candles
            else:
                candles_out = candles
            series.append({
                "pair": pair,
                "timeframe": tf,
                "candles": candles_out,
                "indicators": indicators,
                "signals": signals,
            })

    # Trades / Orders / Performance via proxy
    def _get(path: str):
        s, p = proxy_freqtrade_api(bot, "GET", path)
        if s >= 400:
            return None
        return p

    open_trades = _get("/open_trades")
    open_orders = _get("/open_orders")
    balance = _get("/balance")
    profit = _get("/profit")
    performance = _get("/performance")

    return {
        "pairs": pairs,
        "timeframes": tfs,
        "series": series,
        "open_trades": open_trades,
        "open_orders": open_orders,
        "balance": balance,
        "profit": profit,
        "performance": performance,
    }
