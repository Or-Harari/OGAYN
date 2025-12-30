from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db
from ..services.config_service import (
    load_meta_config,
    save_meta_config,
    get_user_account_config,
    update_user_account_config,
    reset_user_account_config,
    get_bot_config,
    update_bot_config,
    reset_bot_config,
    validate_user_and_bot,
)
from ..db.models import Bot
from ..schemas import (
    UserConfigPatch,
    BotConfigPatch,
    ExchangeConfig,
    BotTradingControls,
    BotPricingUpdate,
    BotTradingModeUpdate,
)
from ..services.config_validation import BOT_PLACEHOLDER
from ..services.config_service import SYSTEM_DEFAULTS, save_bot_config
import re
from pathlib import Path
import os

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/meta")
def get_meta(current=Depends(get_current_user), db: Session = Depends(get_db)):
    return load_meta_config(current.workspace_root)

@router.put("/meta")
def put_meta(req: dict, current=Depends(get_current_user), db: Session = Depends(get_db)):
    meta = req.get("meta", {})
    return save_meta_config(meta, current.workspace_root)


# ---- User account config ----
@router.get("/user")
def get_user_config(current=Depends(get_current_user)):
    return get_user_account_config(current.workspace_root)


@router.patch("/user")
def patch_user_config(patch: UserConfigPatch, current=Depends(get_current_user)):
    return update_user_account_config(current.workspace_root, patch.model_dump(exclude_unset=True))


@router.post("/user/reset")
def reset_user_config(current=Depends(get_current_user)):
    return reset_user_account_config(current.workspace_root)


# ---- Focused: User Exchange config ----
@router.get("/user/exchange")
def get_user_exchange(current=Depends(get_current_user)) -> dict:
    acc = get_user_account_config(current.workspace_root)
    return acc.get("exchange", {}) or {}


@router.put("/user/exchange")
def put_user_exchange(cfg: ExchangeConfig, current=Depends(get_current_user)) -> dict:
    payload = {"exchange": cfg.model_dump(exclude_none=True)}
    return update_user_account_config(current.workspace_root, payload)


@router.get("/user/exchange/view")
def get_user_exchange_view(current=Depends(get_current_user)) -> dict:
    """Masked view of user exchange config for safe UI display."""
    ex = get_user_account_config(current.workspace_root).get("exchange", {}) or {}
    return {
        "name": ex.get("name"),
        "sandbox": bool(ex.get("sandbox", False)),
        "has_key": bool(ex.get("key")),
        "has_secret": bool(ex.get("secret")),
        "has_password": bool(ex.get("password")),
    }


# ---- Bot config CRUD ----
def _get_bot(db: Session, current, bot_id: int) -> Bot:
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == current.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.get("/bot/{bot_id}")
def get_bot_cfg(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot(db, current, bot_id)
    return get_bot_config(bot.userdir)


@router.patch("/bot/{bot_id}")
def patch_bot_cfg(bot_id: int, patch: BotConfigPatch, current=Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot(db, current, bot_id)
    return update_bot_config(bot.userdir, patch.model_dump(exclude_unset=True))


@router.post("/bot/{bot_id}/reset")
def reset_bot_cfg(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot(db, current, bot_id)
    return reset_bot_config(bot.userdir)


@router.get("/validate/{bot_id}")
def validate_configs(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _get_bot(db, current, bot_id)
    return validate_user_and_bot(current.workspace_root, bot.userdir)

# ---- Isolated Backtest config CRUD ----
def _paths_repo_root() -> tuple[str, str]:
    from pathlib import Path
    file_path = Path(__file__).resolve()
    try:
        repo_root = file_path.parents[3]
    except Exception:
        repo_root = file_path.parent
    return str(repo_root), str(file_path)


def _backtest_config_path() -> str:
    """Return canonical isolated backtest config path.

    Preference order:
      1. FT_ISO_BT_CONFIG env var
      2. repo_root/bt-userdir/configs/backtest.json
      3. repo_root/config/backtest.json
    """
    import os
    from pathlib import Path
    repo_root, _ = _paths_repo_root()
    env_override = os.environ.get("FT_ISO_BT_CONFIG")
    if env_override:
        return env_override
    candidates = [
        Path(repo_root) / "bt-userdir" / "configs" / "backtest.json",
        Path(repo_root) / "config" / "backtest.json",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # Default to bt-userdir canonical location
    return str(Path(repo_root) / "bt-userdir" / "configs" / "backtest.json")


def _backtest_strategies_dir() -> Path:
    repo_root_str, _ = _paths_repo_root()
    repo_root = Path(repo_root_str)
    return repo_root / "bt-userdir" / "strategies"

def _backtest_userdir() -> Path:
    repo_root_str, _ = _paths_repo_root()
    repo_root = Path(repo_root_str)
    return repo_root / "bt-userdir"


@router.get("/backtest/strategies")
def list_backtest_strategies(current=Depends(get_current_user)) -> dict:
    """List available strategy class names from bt-userdir/strategies.

    Parses Python files for classes inheriting IStrategy. Falls back to filenames.
    """
    strategies_dir = _backtest_strategies_dir()
    if not strategies_dir.exists():
        return {"strategies": []}
    names: list[str] = []
    try:
        for p in strategies_dir.glob("*.py"):
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            # Find classes like: class MyStrategy(IStrategy):
            matches = re.findall(r"class\s+(\w+)\s*\(\s*IStrategy\s*\)", text)
            if matches:
                names.extend(matches)
            else:
                # Fallback to filename without extension
                names.append(p.stem)
    except Exception:
        pass
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for n in names:
        if n not in seen:
            uniq.append(n)
            seen.add(n)
    return {"strategies": uniq}


@router.get("/backtest")
def get_backtest_config(current=Depends(get_current_user)):
    import json
    p = _backtest_config_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backtest config not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read backtest config: {e}")


@router.put("/backtest")
def put_backtest_config(cfg: dict, current=Depends(get_current_user)):
    import json
    p = _backtest_config_path()
    # Minimal validation: ensure pairlists/pair_whitelist presence
    try:
        if not isinstance(cfg, dict):
            raise ValueError("Invalid payload")
        # Write atomically
        from pathlib import Path
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return cfg
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save backtest config: {e}")


@router.post("/backtest/run")
def run_backtest(req: dict | None = None, current=Depends(get_current_user)):
    """Run an isolated backtest using the isolated config and script.

    Request payload may include:
      - strategy: strategy class name
      - strategy_path: absolute path to strategies folder
      - timerange: freqtrade timerange string
      - export_trades: bool
      - timeframe: override timeframe (else read from config)
    """
    import json
    import subprocess
    from pathlib import Path
    req = req or {}
    repo_root_str, _ = _paths_repo_root()
    repo_root = Path(repo_root_str)
    cfg_path = Path(_backtest_config_path())
    if not cfg_path.exists():
        raise HTTPException(status_code=404, detail="Backtest config not found")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read backtest config: {e}")

    strategy = req.get("strategy") or "SupplyDemandStructureStrategyHTF_TrendV3"
    strategy_path = Path(req.get("strategy_path") or (repo_root / "workspaces" / "user3" / "user" / "strategies"))
    userdir = repo_root / "bt-userdir"
    db_url = req.get("db_url") or f"sqlite:///{str(userdir / 'backtest.sqlite').replace('\\', '/')}"
    timeframe = req.get("timeframe") or cfg.get("timeframe") or "15m"
    timerange = req.get("timerange")
    export_trades = bool(req.get("export_trades"))

    script = repo_root / "scripts" / "run-backtest-isolated.ps1"
    if not script.exists():
        raise HTTPException(status_code=404, detail="Isolated backtest script not found")

    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
        "-Strategy", str(strategy),
        "-StrategyPath", str(strategy_path),
        "-Config", str(cfg_path),
        "-UserDir", str(userdir),
        "-DbUrl", str(db_url),
        "-Timeframe", str(timeframe),
    ]
    if timerange:
        cmd.extend(["-Timerange", str(timerange)])
    if export_trades:
        cmd.append("-ExportTrades")

    # Ensure pycache isolation
    env = dict(**os.environ)
    env["PYTHONPYCACHEPREFIX"] = str(userdir / "pycache")

    def _tail_file_lines(path: Path, tail: int) -> list[str]:
        try:
            if not path.exists():
                return []
            with path.open("rb") as f:
                data = f.read()
            txt = data.decode("utf-8", errors="ignore")
            lines = txt.splitlines()
            return lines[-tail:]
        except Exception:
            return []

    def _list_artifacts(res_dir: Path) -> list[dict]:
        items: list[dict] = []
        try:
            for z in res_dir.glob("*.zip"):
                try:
                    stat = z.stat()
                    items.append({"file": z.name, "mtime": stat.st_mtime, "size": stat.st_size})
                except Exception:
                    continue
            items.sort(key=lambda d: d.get("mtime", 0), reverse=True)
        except Exception:
            items = []
        return items

    def _extract_trades(payload: dict | list) -> list:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        if isinstance(payload.get("trades"), list):
            return payload["trades"]
        strat = payload.get("strategy")
        if isinstance(strat, dict):
            for v in strat.values():
                if isinstance(v, dict) and isinstance(v.get("trades"), list):
                    return v["trades"]
        return []

    def _load_latest_summary(res_dir: Path) -> tuple[dict | None, str | None, list]:
        import json as _json, zipfile
        try:
            latest_desc = res_dir / ".last_result.json"
            latest_backtest = None
            if latest_desc.exists():
                try:
                    latest_backtest = (_json.loads(latest_desc.read_text(encoding="utf-8")) or {}).get("latest_backtest")
                except Exception:
                    latest_backtest = None
            # fallback: newest zip
            if not latest_backtest:
                zips = sorted([p for p in res_dir.glob("*.zip")], key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
                latest_backtest = zips[0].name if zips else None
            if not latest_backtest:
                return None, None
            zip_path = (res_dir / latest_backtest).resolve()
            if not zip_path.exists():
                return None, None
            inner_json_name = Path(latest_backtest).stem + ".json"
            with zipfile.ZipFile(zip_path, "r") as z:
                target_name = inner_json_name
                namelist = z.namelist()
                if target_name not in namelist:
                    candidates = [n for n in namelist if n.endswith("/" + inner_json_name) or n.endswith(inner_json_name)]
                    if candidates:
                        target_name = candidates[0]
                    else:
                        json_candidates = [n for n in namelist if n.lower().endswith(".json")]
                        if not json_candidates:
                            return None, latest_backtest
                        target_name = json_candidates[0]
                with z.open(target_name) as jf:
                    data = _json.load(jf)
            trades = _extract_trades(data)
            timeframe_val = None
            try:
                if isinstance(data, dict):
                    strat_block = data.get("strategy")
                    if isinstance(strat_block, dict):
                        for _name, strat_obj in strat_block.items():
                            if isinstance(strat_obj, dict):
                                tf = strat_obj.get("timeframe") or strat_obj.get("ticker_interval")
                                if isinstance(tf, str) and tf:
                                    timeframe_val = tf
                                    break
                    if timeframe_val is None:
                        cfg = data.get("config")
                        if isinstance(cfg, dict):
                            tf = cfg.get("timeframe")
                            if isinstance(tf, str) and tf:
                                timeframe_val = tf
            except Exception:
                timeframe_val = None
            timerange = data.get("timerange") or None
            total = len(trades)
            wins = 0
            profit_sum = 0.0
            profit_ratio_sum = 0.0
            by_pair: dict = {}
            for t in trades:
                pr = float((t.get("profit_ratio") or 0.0) or 0.0)
                profit_ratio_sum += pr
                profit_sum += float((t.get("profit_abs") or 0.0) or 0.0)
                if pr > 0:
                    wins += 1
                pair = t.get("pair") or "?"
                agg = by_pair.setdefault(pair, {"count": 0, "profit_ratio_sum": 0.0, "profit_abs_sum": 0.0})
                agg["count"] += 1
                agg["profit_ratio_sum"] += pr
                agg["profit_abs_sum"] += float((t.get("profit_abs") or 0.0) or 0.0)
            summary = {
                "total_trades": total,
                "winrate": (wins / total) if total else 0.0,
                "profit_abs_sum": profit_sum,
                "profit_ratio_avg": (profit_ratio_sum / total) if total else 0.0,
                "by_pair": by_pair,
                "file": latest_backtest,
                "timeframe": timeframe_val,
                "timerange": timerange,
            }
            return summary, latest_backtest, trades
        except Exception:
            return None, None, []

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        # Build additional payload for isolated flow
        results_dir = userdir / "backtest_results"
        logs_dir = userdir / "logs"
        artifacts = _list_artifacts(results_dir)
        latest_summary, latest_file, latest_trades_all = _load_latest_summary(results_dir)
        latest_trades = latest_trades_all[:200] if isinstance(latest_trades_all, list) else []
        logs_lines = []
        try:
            logs_lines = (_tail_file_lines(logs_dir / "backtest.out.log", 500) + _tail_file_lines(logs_dir / "backtest.err.log", 200))[-700:]
        except Exception:
            logs_lines = []
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": cmd,
            "artifacts": artifacts,
            "latest_file": latest_file,
            "latest_summary": latest_summary,
            "latest_trades": latest_trades,
            "logs": {"lines": logs_lines},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start backtest: {e}")




# ---- Focused: Bot trading controls ----
_TRADING_CONTROL_KEYS = [
    "stake_currency",
    "stake_amount",
    "max_open_trades",
    "tradable_balance_ratio",
    "available_capital",
    "amend_last_stake_amount",
    "last_stake_amount_min_ratio",
    "amount_reserve_percent",
    "fiat_display_currency",
    "dry_run_wallet",
    "fee",
    "futures_funding_rate",
    "trading_mode",
    "margin_mode",
    "liquidation_buffer",
    "cancel_open_orders_on_exit",
    "custom_price_max_distance_ratio",
]


def _extract_trading_controls(cfg: dict) -> dict:
    base = {k: cfg.get(k) for k in _TRADING_CONTROL_KEYS if k in cfg}
    # Ensure required keys have sensible defaults
    base.setdefault("stake_currency", cfg.get("stake_currency") or BOT_PLACEHOLDER.get("stake_currency"))
    base.setdefault("stake_amount", cfg.get("stake_amount") or BOT_PLACEHOLDER.get("stake_amount"))
    base.setdefault("max_open_trades", cfg.get("max_open_trades") or BOT_PLACEHOLDER.get("max_open_trades"))
    base.setdefault("trading_mode", cfg.get("trading_mode") or BOT_PLACEHOLDER.get("trading_mode") or "spot")
    return base


@router.get("/bot/{bot_id}/trading-controls")
def get_bot_trading_controls(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)) -> BotTradingControls:
    bot = _get_bot(db, current, bot_id)
    cfg = get_bot_config(bot.userdir) or {}
    data = _extract_trading_controls(cfg)
    return BotTradingControls(**data)


@router.put("/bot/{bot_id}/trading-controls")
def put_bot_trading_controls(
    bot_id: int,
    controls: BotTradingControls,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_bot(db, current, bot_id)
    patch = controls.model_dump(exclude_none=True)
    updated = update_bot_config(bot.userdir, patch)
    return _extract_trading_controls(updated)


# ---- Focused: Bot pricing ----
@router.get("/bot/{bot_id}/pricing")
def get_bot_pricing(bot_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)) -> BotPricingUpdate:
    bot = _get_bot(db, current, bot_id)
    cfg = get_bot_config(bot.userdir) or {}
    entry = cfg.get("entry_pricing") or SYSTEM_DEFAULTS.get("entry_pricing")
    exitp = cfg.get("exit_pricing") or SYSTEM_DEFAULTS.get("exit_pricing")
    return BotPricingUpdate(entry_pricing=entry, exit_pricing=exitp)


@router.put("/bot/{bot_id}/pricing")
def put_bot_pricing(
    bot_id: int,
    pricing: BotPricingUpdate,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_bot(db, current, bot_id)
    patch = pricing.model_dump(exclude_none=True)
    updated = update_bot_config(bot.userdir, patch)
    return {
        "entry_pricing": updated.get("entry_pricing"),
        "exit_pricing": updated.get("exit_pricing"),
    }


# ---- Focused: Bot trading mode ----
@router.patch("/bot/{bot_id}/trading-mode")
def patch_bot_trading_mode(
    bot_id: int,
    update: BotTradingModeUpdate,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_bot(db, current, bot_id)
    mode = (update.trading_mode or "spot").lower()
    # Load, mutate explicitly to allow removal of futures-only keys when switching to spot
    cur = get_bot_config(bot.userdir) or {}
    cur["trading_mode"] = mode
    if mode == "spot":
        cur.pop("liquidation_buffer", None)
        cur.pop("margin_mode", None)
    # Persist full object to reflect removals
    saved = save_bot_config(cur, bot.userdir)
    return {"trading_mode": saved.get("trading_mode", mode)}
