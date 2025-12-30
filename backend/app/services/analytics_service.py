from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import importlib.util
import sys

from fastapi import HTTPException
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session

from ..db.models import User, Bot
from .bot_service import proxy_freqtrade_api, _get_freqtrade_image, _docker_image_ensure
import subprocess
import os


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
    from pathlib import Path as _P

    user_root = _P(user.workspace_root).resolve()
    bot_userdir = _P(bot.userdir).resolve()

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

    # Timeframes: prefer strategy timeframe, else config timeframe; if none, leave empty (no synthetic default)
    tfs: list[str] = []
    if primary_timeframe:
        tfs.append(primary_timeframe)
    try:
        tf_cfg = cfg.get("timeframe")
        if isinstance(tf_cfg, str) and tf_cfg and tf_cfg not in tfs:
            tfs.append(tf_cfg)
    except Exception:
        pass
    # if not tfs: remain empty; snapshot will return empty series

    series: list[dict] = []  # <-- always define
    # Cache parity results per timeframe to avoid spawning multiple containers
    parity_cache_by_tf: dict[str, dict[str, dict]] = {}

    # Iterate pairs/timeframes safely
    for pair in (pairs or []):
        for tf in tfs:
            indicators: dict[str, list] = {}
            signals: dict[str, list] = {}
            candles_out: list = []

            # Fetch candles with best-effort error handling
            candles = None
            try:
                candles = fetch_candles(bot, pair, tf, limit=limit)
            except Exception:
                candles = None

            # Try to build a DataFrame for indicators/signals
            df, _err = _df_from_candles(candles) if candles is not None else (None, "no candle data")

            if df is not None:
                # compute signals/indicators best-effort
                sdf = _apply_strategy(strategy_cls, tf, df)
                # serialize candles from df (processed) if possible
                try:
                    import pandas as _pd  # type: ignore
                    d = sdf if sdf is not None else df
                    # Ensure we have the columns we need; else fallback to raw
                    base_cols = {"date", "open", "high", "low", "close"}
                    cols = getattr(d, "columns", [])
                    if all(k in cols for k in base_cols):
                        tmp_out = []
                        for i in range(len(d)):
                            try:
                                row = d.iloc[i]
                                # epoch seconds if possible
                                ts = None
                                try:
                                    dv = row["date"]
                                    if hasattr(dv, "value"):
                                        ts = int(int(dv.value) // 1_000_000_000)
                                    else:
                                        ts = int(_pd.to_datetime(dv, utc=True).value // 1_000_000_000)
                                except Exception:
                                    ts = None
                                vol = float(row["volume"]) if "volume" in cols else 0.0
                                tmp_out.append(
                                    {
                                        "date": str(row["date"]),
                                        "date_ts": ts,
                                        "open": float(row["open"]),
                                        "high": float(row["high"]),
                                        "low": float(row["low"]),
                                        "close": float(row["close"]),
                                        "volume": vol,
                                    }
                                )
                            except Exception:
                                continue
                        candles_out = tmp_out
                    # Extract indicators & signals from sdf (if available)
                    src = sdf if sdf is not None else df
                    base_cols = {"date", "open", "high", "low", "close", "volume"}
                    for col in getattr(src, "columns", []):
                        if col in base_cols:
                            continue
                        if col in ("buy", "sell", "enter_long", "exit_long"):
                            try:
                                signals[col] = [
                                    bool(v) if v in (0, 1, True, False) else False for v in src[col].tolist()
                                ]
                            except Exception:
                                pass
                        else:
                            vals = []
                            for v in src[col].tolist():
                                try:
                                    vals.append(None if v is None else float(v))
                                except Exception:
                                    vals.append(None)
                            indicators[col] = vals
                except Exception:
                    # ignore; we'll fallback to raw candles below
                    pass

            # Fallback to raw candles if we couldn't serialize from df
            if not candles_out:
                try:
                    if isinstance(candles, dict) and isinstance(candles.get("data"), list):
                        candles_out = candles["data"]
                    elif isinstance(candles, list):
                        candles_out = candles
                    else:
                        candles_out = []
                except Exception:
                    candles_out = []

            # Final fallback: when API is unreachable or provided no candles, try parity snapshot once per timeframe
            if not candles_out:
                try:
                    # Prepare cache for this timeframe if missing
                    if tf not in parity_cache_by_tf:
                        # Call parity snapshot for all configured pairs at this timeframe to minimize container runs
                        # Returns a dict with 'series': [{pair, timeframe, candles, indicators, signals}, ...]
                        p_res = parity_snapshot(db, user, bot, timeframe=tf, limit=limit, pairs=pairs or None)
                        tf_map: dict[str, dict] = {}
                        try:
                            if isinstance(p_res, dict) and isinstance(p_res.get('series'), list):
                                for ent in p_res['series']:
                                    if isinstance(ent, dict) and ent.get('pair') and ent.get('timeframe') == tf:
                                        tf_map[str(ent['pair'])] = ent
                        except Exception:
                            tf_map = {}
                        parity_cache_by_tf[tf] = tf_map
                    # Use cached parity result for this pair if present
                    cand_ent = parity_cache_by_tf.get(tf, {}).get(pair)
                    if isinstance(cand_ent, dict):
                        try:
                            c = cand_ent.get('candles')
                            if isinstance(c, list):
                                candles_out = c
                            elif isinstance(c, dict) and isinstance(c.get('data'), list):
                                candles_out = c['data']
                            # pick indicators/signals if parity provided them
                            indicators = cand_ent.get('indicators') or indicators
                            signals = cand_ent.get('signals') or signals
                        except Exception:
                            pass
                except Exception:
                    # parity fallback is best-effort
                    pass

            series.append(
                {
                    "pair": pair,
                    "timeframe": tf,
                    "candles": candles_out,
                    "indicators": indicators,
                    "signals": signals,
                }
            )

    # Trades / Orders / Performance via proxy
    def _get(path: str):
        s, p = proxy_freqtrade_api(bot, "GET", path)
        if s >= 400:
            return None
        return p

    open_trades = _get("/status")
    balance = _get("/balance")
    profit = _get("/profit")
    performance = _get("/performance")
    show_config = _get("/show_config")
    effective_timeframe = None
    try:
        if isinstance(show_config, dict):
            effective_timeframe = show_config.get("timeframe")
    except Exception:
        effective_timeframe = None
    
    trades = _get("/trades?limit=200")

    return {
        "pairs": pairs,
        "timeframes": tfs,
        "series": series,
        "open_trades": open_trades,
        "balance": balance,
        "profit": profit,
        "performance": performance,
        "trades": trades,
        "effective_timeframe": effective_timeframe,
    }



def parity_snapshot(
    db: Session,
    user: User,
    bot: Bot,
    timeframe: Optional[str] = None,
    limit: int = 200,
    pairs: Optional[list[str]] = None,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
):
    """Build an analytics snapshot using Freqtrade internals inside the Docker image for full parity.

    Runs a short-lived container that:
      - Loads config.generated.json
      - Resolves strategy via StrategyResolver
      - Uses DataProvider and analyze_ticker() to compute indicators/signals
      - Loads candles from datadir for the requested timeframe and pairs
    Returns JSON similar to snapshot().
    """
    user_root = Path(user.workspace_root).resolve()
    bot_userdir = Path(bot.userdir).resolve()

    # Ensure analytics script exists under user_data
    analytics_dir = bot_userdir / "analytics"
    analytics_dir.mkdir(parents=True, exist_ok=True)
    script_path = analytics_dir / "collect_snapshot.py"
    # Detect trading mode from composed config to select CandleType
    tmode = "spot"
    try:
        cfg_path = _read_bot_config_path(bot_userdir)
        if cfg_path:
            cfg = _load_config(cfg_path)
            tmode = str((cfg.get("trading_mode") or "spot")).lower()
    except Exception:
        tmode = "spot"

    script = r'''
import json
import sys
import argparse
from pathlib import Path
import traceback
import math

from freqtrade.configuration import Configuration
from freqtrade.data.history import load_pair_history
from freqtrade.enums import CandleType
from freqtrade.resolvers import StrategyResolver
from freqtrade.data.dataprovider import DataProvider

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--timeframe', required=False)
    ap.add_argument('--limit', type=int, default=200)
    ap.add_argument('--pairs', nargs='*')
    ap.add_argument('--candle-type', choices=['spot','futures'], default='spot')
    ap.add_argument('--from-ts', type=int, default=None)
    ap.add_argument('--to-ts', type=int, default=None)
    args = ap.parse_args()

    # Pre-normalize config to avoid errors inside Configuration.from_files
    tmp_cfg_path = '/freqtrade/user_data/analytics/config.parity.json'
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    try:
        # Force absolute user_data_dir and datadir
        raw['user_data_dir'] = '/freqtrade/user_data'
        ex = raw.get('exchange') or {}
        exname = ex.get('name') if isinstance(ex, dict) else 'binance'
        if not exname:
            exname = 'binance'
        dd = str(raw.get('datadir') or '')
        if not dd.startswith('/freqtrade/user_data'):
            raw['datadir'] = f"/freqtrade/user_data/data/{exname}"
        # Normalize strategy_path if it's a host (Windows) path not valid inside the container
        # Prefer extra_strategies if present; else fallback to user_data/strategies
        try:
            if Path('/freqtrade/extra_strategies').exists():
                raw['strategy_path'] = '/freqtrade/extra_strategies'
            elif Path('/freqtrade/user_data/strategies').exists():
                raw['strategy_path'] = '/freqtrade/user_data/strategies'
        except Exception:
            pass
        # Write normalized file
        with open(tmp_cfg_path, 'w', encoding='utf-8') as f:
            json.dump(raw, f)
        cfg = Configuration.from_files([tmp_cfg_path])
    except Exception:
        cfg = Configuration.from_files([args.config])
    # Force absolute user_data_dir/datadir paths inside the container to avoid double-prefix issues
    try:
        from pathlib import Path as _P
        cfg['user_data_dir'] = _P('/freqtrade/user_data')
        exname = None
        try:
            ex = cfg.get('exchange') or {}
            if isinstance(ex, dict):
                exname = ex.get('name')
        except Exception:
            exname = None
        if not exname:
            exname = 'binance'
        dd_val = cfg.get('datadir')
        dd_str = str(dd_val) if dd_val is not None else ''
        if not dd_str.startswith('/freqtrade/user_data'):
            cfg['datadir'] = _P(f"/freqtrade/user_data/data/{exname}")
    except Exception:
        pass
    # Normalize strategy_path if it's a host (Windows) path not valid inside the container
    try:
        sp = cfg.get('strategy_path')
        if sp:
            sps = str(sp)
            if (':' in sps) or ('\\' in sps):
                # Prefer mounted extra strategies, fallback to user_data strategies
                if Path('/freqtrade/extra_strategies').exists():
                    cfg['strategy_path'] = '/freqtrade/extra_strategies'
                elif Path('/freqtrade/user_data/strategies').exists():
                    cfg['strategy_path'] = '/freqtrade/user_data/strategies'
                else:
                    # Drop invalid path to allow PYTHONPATH-based resolution
                    cfg.pop('strategy_path', None)
    except Exception:
        pass
    # Apply timeframe override if provided
    if args.timeframe:
        cfg['timeframe'] = args.timeframe
    tf = cfg.get('timeframe') or '5m'

    # Derive pairs
    pairs = []
    if args.pairs:
        pairs = args.pairs
    elif isinstance(cfg.get('pairs'), list):
        pairs = cfg.get('pairs') or []
    elif isinstance(cfg.get('pair_whitelist'), list):
        pairs = cfg.get('pair_whitelist') or []

    # Ensure sys.path contains common mounts
    for p in ['/freqtrade/extra_strategies', '/freqtrade/user_data', '/repo']:
        if p not in sys.path and Path(p).exists():
            sys.path.insert(0, p)

    # Prefer manual import first to avoid resolver issues with config paths
    strategy = None
    try:
        sname = cfg.get('strategy')
        spath = cfg.get('strategy_path')
        sys.stderr.write(f"Manual import attempt for strategy={sname} strategy_path={spath}\n")
        search_roots = []
        if spath:
            search_roots.append(Path(spath))
        for base in ['/freqtrade/extra_strategies', '/freqtrade/user_data/strategies', '/repo/workspaces']:
            if Path(base).exists():
                search_roots.append(Path(base))
        # Build candidate list recursively
        candidates = []
        try:
            import os as _os
            for root in search_roots:
                if not root.exists():
                    continue
                for dirpath, _, filenames in _os.walk(root):
                    for fn in filenames:
                        if fn.lower() == f"{sname.lower()}.py":
                            candidates.append(Path(dirpath) / fn)
        except Exception:
            pass
        if not candidates:
            # Also try non-recursive direct files
            candidates = [root / f"{sname}.py" for root in search_roots]
        sys.stderr.write("Candidates:\n" + "\n".join([f" - {str(c)} (exists={c.exists()})" for c in candidates]) + "\n")
        # Directory listings for debug (ensure appears near tail)
        try:
            import os as _os
            for root in search_roots:
                try:
                    listing = []
                    for dp, dn, fn in _os.walk(root):
                        listing.append(dp + ' -> files:' + ','.join(fn[:10]))
                        if len(listing) > 10:
                            break
                    sys.stderr.write("Walk " + str(root) + "\n" + "\n".join(listing) + "\n")
                except Exception as _e:
                    sys.stderr.write(f"walk {root} failed: {_e}\n")
        except Exception:
            pass
        for f in candidates:
            if f.exists():
                try:
                    import importlib.util
                    # Ensure the candidate's directory is on sys.path so sibling imports work
                    try:
                        import sys as _sys
                        pdir = str(f.parent)
                        if pdir not in _sys.path:
                            _sys.path.insert(0, pdir)
                            sys.stderr.write(f"Added to sys.path: {pdir}\n")
                    except Exception:
                        pass
                    spec = importlib.util.spec_from_file_location(sname, str(f))
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)  # type: ignore
                        cls = getattr(mod, sname, None)
                        if cls:
                            strategy = cls(cfg)
                            sys.stderr.write(f"Manual import succeeded from {f}\n")
                            break
                        else:
                            sys.stderr.write(f"Class {sname} not found in {f}\n")
                except Exception:
                    sys.stderr.write('Error importing candidate:\n')
                    sys.stderr.write(traceback.format_exc())
                    sys.stderr.flush()
                    continue
    except Exception:
        sys.stderr.write('Manual import pre-step failed with:\n')
        sys.stderr.write(traceback.format_exc())
        sys.stderr.flush()
    # If manual import failed, fall back to StrategyResolver
    if strategy is None:
        try:
            strategy = StrategyResolver.load_strategy(cfg)
        except Exception:
            sys.stderr.write('StrategyResolver.load_strategy failed with:\n')
            sys.stderr.write(traceback.format_exc())
            sys.stderr.flush()
            raise RuntimeError(f"Manual import fallback failed for strategy {cfg.get('strategy')}")
    strategy.dp = DataProvider(cfg, None, None)
    try:
        strategy.ft_bot_start()
    except Exception:
        pass

    datadir = cfg.get('datadir')
    ctype = CandleType.FUTURES if args.candle_type == 'futures' else CandleType.SPOT
    out_series = []
    base_cols = {'date','open','high','low','close','volume'}

    def _serialize_candles(df):
        try:
            import pandas as _pd  # type: ignore
            d = df
            # If date is index, copy to column
            if isinstance(getattr(d, 'index', None), _pd.Index) and 'date' not in getattr(d, 'columns', []):
                try:
                    d = d.copy()
                    d['date'] = d.index
                except Exception:
                    pass
            cols = getattr(d, 'columns', [])
            if not all(k in cols for k in ['date','open','high','low','close']):
                raise ValueError('missing base columns')
            if 'volume' not in cols:
                try:
                    d = d.copy()
                    d['volume'] = 0.0
                except Exception:
                    pass
            out = []
            # Use iloc to avoid issues with non-range indices
            def _sf(x):
                try:
                    f = float(x)
                    return f if math.isfinite(f) else None
                except Exception:
                    return None
            for i in range(len(d)):
                try:
                    row = d.iloc[i]
                    # Compute epoch seconds for fast client-side rendering
                    ts = None
                    try:
                        dv = row['date']
                        if hasattr(dv, 'value'):
                            ts = int(int(dv.value) // 1_000_000_000)
                        else:
                            ts = int(_pd.to_datetime(dv, utc=True).value // 1_000_000_000)
                    except Exception:
                        ts = None
                    out.append({
                        'date': str(row['date']),
                        'date_ts': ts,
                        'open': _sf(row['open']),
                        'high': _sf(row['high']),
                        'low': _sf(row['low']),
                        'close': _sf(row['close']),
                        'volume': _sf(row['volume']) if 'volume' in row else 0.0,
                    })
                except Exception:
                    continue
            return out
        except Exception:
            return []
    for pair in pairs:
        candles = None
        # Try configured dataformat first, then parquet/feather/json fallback
        try_formats = []
        try:
            cfg_fmt = cfg.get('dataformat_ohlcv')
        except Exception:
            cfg_fmt = None
        if cfg_fmt:
            try_formats.append(str(cfg_fmt))
        try_formats += ['parquet', 'feather', 'json']
        # de-duplicate preserving order
        seen = set()
        fmts = []
        for f in try_formats:
            if f not in seen:
                seen.add(f)
                fmts.append(f)
        for fmt in fmts:
            try:
                tmp = load_pair_history(
                    datadir=datadir,
                    timeframe=tf,
                    pair=pair,
                    data_format=fmt,
                    candle_type=ctype,
                )
                if tmp is not None and len(tmp) > 0:
                    candles = tmp
                    break
            except Exception:
                continue
        if candles is None or len(candles) == 0:
            # No data available; return empty series entry and continue
            out_series.append({'pair': pair, 'timeframe': tf, 'candles': [], 'indicators': {}, 'signals': {}})
            continue
        # Optional slice by from/to unix seconds (inclusive)
        try:
            if args.from_ts or args.to_ts:
                import pandas as _pd  # type: ignore
                start = _pd.to_datetime(args.from_ts, unit='s', utc=True) if args.from_ts else None
                end = _pd.to_datetime(args.to_ts, unit='s', utc=True) if args.to_ts else None
                if start is not None and end is not None:
                    candles = candles.loc[(candles.index >= start) & (candles.index <= end)]
                elif start is not None:
                    candles = candles.loc[candles.index >= start]
                elif end is not None:
                    candles = candles.loc[candles.index <= end]
        except Exception:
            # best-effort; continue without slicing on error
            pass

        if args.limit and args.limit > 0:
            candles = candles.tail(args.limit)
        df = strategy.analyze_ticker(candles, {'pair': pair})
        # Serialize candles preferring strategy output if it still contains base OHLCV columns; otherwise fallback to raw candles
        cd_processed = _serialize_candles(df)
        cd_raw = _serialize_candles(candles)
        cd = cd_processed if cd_processed else cd_raw
        # Indicators and signals
        indicators = {}
        signals = {}
        for col in df.columns:
            if col in base_cols:
                continue
            if col in ('buy','sell','enter_long','exit_long'):
                try:
                    signals[col] = [bool(v) if v in (0,1,True,False) else False for v in df[col].tolist()]
                except Exception:
                    pass
            else:
                vals = []
                for v in df[col].tolist():
                    try:
                        if v is None:
                            vals.append(None)
                        else:
                            f = float(v)
                            vals.append(f if math.isfinite(f) else None)
                    except Exception:
                        vals.append(None)
                indicators[col] = vals
        out_series.append({'pair': pair, 'timeframe': tf, 'candles': cd, 'indicators': indicators, 'signals': signals})
    res = {'pairs': pairs, 'timeframes': [tf], 'series': out_series}
    print(json.dumps(res))

if __name__ == '__main__':
    main()
'''
    try:
        script_path.write_text(script, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write analytics script: {e}")

    # Build docker run command
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    # Extra strategies mount (if available)
    extra_strategy_dir = user_root / "user" / "strategies" / "variants"
    if not extra_strategy_dir.exists():
        extra_strategy_dir = user_root / "user" / "strategies"

    image = _get_freqtrade_image()
    # Best-effort ensure image is present
    _docker_image_ensure(image, bot_userdir / "logs" / "analytics.out.log")

    volumes = [
        f"{str(bot_userdir)}:/freqtrade/user_data",
        f"{str(repo_root)}:/repo",
    ]
    docker_py_path = "/freqtrade/user_data:/repo"
    if extra_strategy_dir and extra_strategy_dir.exists():
        # Mount strategies into both standard locations to maximize resolver compatibility
        volumes.append(f"{str(extra_strategy_dir)}:/freqtrade/extra_strategies")
        volumes.append(f"{str(extra_strategy_dir)}:/freqtrade/user_data/strategies")
        docker_py_path += ":/freqtrade/extra_strategies:/freqtrade/user_data/strategies"

    cmd = [
        "docker", "run", "--rm",
    ]
    for v in volumes:
        cmd += ["-v", v]
    cmd += ["-e", f"PYTHONPATH={docker_py_path}"]
    # Set container timezone for consistent logs
    try:
        tz = os.environ.get("FT_CONTAINER_TZ", os.environ.get("TZ", "Etc/UTC"))
    except Exception:
        tz = "Etc/UTC"
    cmd += ["-e", f"TZ={tz}"]
    # Set working directory inside container for predictability
    cmd += ["-w", "/freqtrade/user_data"]
    # Override entrypoint so we can run python directly (freqtrade image entrypoint is `freqtrade`)
    cmd += ["--entrypoint", "python"]
    cmd += [
        image,
        "/freqtrade/user_data/analytics/collect_snapshot.py",
        "--config", "/freqtrade/user_data/configs/config.generated.json",
    ]
    if timeframe:
        cmd += ["--timeframe", timeframe]
    if limit:
        cmd += ["--limit", str(limit)]
    if pairs:
        cmd += ["--pairs", *pairs]
    # Optional time slicing in container
    if from_ts is not None:
        cmd += ["--from-ts", str(int(from_ts))]
    if to_ts is not None:
        cmd += ["--to-ts", str(int(to_ts))]
    # Pass candle type based on trading mode
    cmd += ["--candle-type", ("futures" if tmode == "futures" else "spot")]

    # Execute and capture output
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(bot_userdir), encoding="utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run analytics container: {e}")
    if proc.returncode != 0:
        # Include full stderr to aid debugging (may be long, but far more helpful)
        raise HTTPException(status_code=502, detail={"error": "container failed", "stderr": proc.stderr})
    # Parse stdout into JSON on the server to guarantee a clean JSON response for clients
    raw = proc.stdout or ""

    def _extract_loose_json(text: str):
        # Try direct parse first
        try:
            s = text.lstrip("\ufeff").strip()
            return json.loads(s)
        except Exception:
            pass
        # Try to find an object {...}
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                slice_txt = text[start : end + 1]
                return json.loads(slice_txt)
        except Exception:
            pass
        # Try to find an array [...]
        try:
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                slice_txt = text[start : end + 1]
                return json.loads(slice_txt)
        except Exception:
            pass
        return None

    parsed = _extract_loose_json(raw)
    # Recursively sanitize to remove NaN/Inf which are not JSON-compliant
    def _sanitize(obj):
        try:
            import math as _m
        except Exception:
            _m = None
        if obj is None:
            return None
        if isinstance(obj, float):
            if _m and not _m.isfinite(obj):
                return None
            return obj
        if isinstance(obj, (int, str, bool)):
            return obj
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                out[k] = _sanitize(v)
            return out
        if isinstance(obj, (list, tuple)):
            return [_sanitize(v) for v in obj]
        # Fallback: attempt float conversion if possible
        try:
            f = float(obj)  # type: ignore[arg-type]
            if _m and not _m.isfinite(f):
                return None
            return f
        except Exception:
            return None

    parsed = _sanitize(parsed)
    if parsed is None:
        # If backend cannot extract valid JSON, surface stderr and a small snippet of stdout for diagnosis
        snippet = raw[:512]
        raise HTTPException(status_code=502, detail={
            "error": "invalid json from analytics container",
            "stdout_snippet": snippet,
            "stderr": proc.stderr,
        })
    # Return dict to allow callers to easily reuse the result without dealing with Response objects
    return parsed
