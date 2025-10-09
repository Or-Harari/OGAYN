from __future__ import annotations

import importlib.util
import inspect
import os
from pathlib import Path
import sys
from typing import Dict

from .config_service import load_meta_config
from pathlib import Path as _PathAlias  # for template clarity


def _default_strategies_dir(workspace_root: str) -> Path:
    # user_data/strategies/_strategies
    return Path(workspace_root) / "strategies" / "_strategies"


def _strategy_paths(workspace_root: str) -> list[str]:
    base = Path(workspace_root)
    paths = [str(_default_strategies_dir(workspace_root))]
    try:
        meta = load_meta_config(workspace_root)
        extras = meta.get("strategy_paths") or []
        user_base = base  # user_data
        for p in extras:
            abs_p = p if os.path.isabs(p) else str((user_base / p).resolve())
            paths.append(abs_p)
    except Exception:
        pass
    # Deduplicate preserving order
    seen = set()
    uniq = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _is_candidate_strategy(obj) -> bool:
    """Detect a strategy-like class by duck-typing.
    Accept either our orchestrator's contract (entry_mask/exit_mask)
    or Freqtrade-style contracts (populate_entry_trend/populate_exit_trend)
    and older populate_buy_trend/populate_sell_trend.
    Exclude the base class itself by name.
    """
    name = getattr(obj, "__name__", "")
    if name in ("BaseStrategy", "IStrategy"):
        return False

    # Our orchestrator contract
    ours = all(callable(getattr(obj, m, None)) for m in ("entry_mask", "exit_mask"))
    if ours:
        return True

    # Freqtrade modern methods
    ft_new = all(callable(getattr(obj, m, None)) for m in ("populate_entry_trend", "populate_exit_trend"))
    if ft_new:
        return True

    # Freqtrade legacy methods
    ft_old = all(callable(getattr(obj, m, None)) for m in ("populate_buy_trend", "populate_sell_trend"))
    if ft_old:
        return True

    return False


def _scan_dir_for_strategies(path: str, registry: Dict[str, str]) -> None:
    p = Path(path)
    if not p.exists():
        return
    # Prepare temporary import paths to help resolve local helper packages (e.g., _indicators)
    # Try both the strategies dir root and the repo-level user_data/strategies for shared helpers
    extra_paths = set()
    try:
        # path: .../strategies/_strategies or any directory inside
        strategies_root = p.parent if p.name == "_strategies" else p
        extra_paths.add(str(strategies_root))
        # project root heuristic: backend/app/services/.. -> project root at parents[3]
        project_root = Path(__file__).resolve().parents[3]
        extra_paths.add(str(project_root / "user_data" / "strategies"))
    except Exception:
        pass

    cleanup = []
    for ep in extra_paths:
        if ep and ep not in sys.path:
            sys.path.insert(0, ep)
            cleanup.append(ep)

    for py in p.rglob("*.py"):
        if py.name.startswith("_"):
            continue
        try:
            modname = f"user_strat_{abs(hash(str(py)))}"
            spec = importlib.util.spec_from_file_location(modname, str(py))
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[attr-defined]
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                if _is_candidate_strategy(obj) and name not in registry:
                    registry[name] = str(py)
        except Exception:
            continue
    # Cleanup temporary sys.path entries
    for ep in cleanup:
        try:
            if ep in sys.path:
                sys.path.remove(ep)
        except Exception:
            pass


def discover_strategies(workspace_root: str) -> Dict[str, str]:
    """Discover strategy classes under user_data/strategies/_strategies and any extra meta.strategy_paths.
    Returns mapping of class name -> source file path. Earlier paths win on duplicates.
    """
    registry: Dict[str, str] = {}
    for path in _strategy_paths(workspace_root):
        _scan_dir_for_strategies(path, registry)
    return registry


_TEMPLATE = '''from __future__ import annotations

"""Variant strategy subclassing project MainStrategy.

Edit only what you need: indicators, entry/exit logic, risk hooks.
"""

from pandas import DataFrame
from backend.app.trading_core.main_strategy import MainStrategy as CoreMainStrategy


class {class_name}(CoreMainStrategy):
    name = "{class_name}"

    def populate_indicators(self, dataframe: DataFrame, metadata: dict | None = None):
        dataframe = super().populate_indicators(dataframe, metadata)
        # TODO: add custom indicators here
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict | None = None):
        dataframe = super().populate_entry_trend(dataframe, metadata)
        # Example tweak: tag when close above EMA200 (if present)
        if 'ema200' in dataframe.columns:
            dataframe.loc[dataframe['close'] > dataframe['ema200'], 'enter_long'] = 1
            dataframe.loc[dataframe['close'] > dataframe['ema200'], 'enter_tag'] = '{class_name}:ema200'
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict | None = None):
        dataframe = super().populate_exit_trend(dataframe, metadata)
        # Example exit: clear longs if close below ema200
        if 'ema200' in dataframe.columns:
            dataframe.loc[dataframe['close'] < dataframe['ema200'], 'exit_long'] = 1
            dataframe.loc[dataframe['close'] < dataframe['ema200'], 'exit_tag'] = '{class_name}:ema200-cross'
        return dataframe
'''


def create_strategy_file(class_name: str, filename: str | None, workspace_root: str) -> str:
    """Create a new variant strategy subclassing MainStrategy.

    Writes file under strategies/variants/ to distinguish from auto-discovered _strategies legacy dir.
    """
    base_dir = Path(workspace_root) / "strategies" / "variants"
    base_dir.mkdir(parents=True, exist_ok=True)
    init_path = base_dir / "__init__.py"
    if not init_path.exists():
        init_path.write_text("", encoding="utf-8")
    fname = (filename or f"{class_name}.py").replace(".py", ".py")
    path = base_dir / fname
    if path.exists():
        raise FileExistsError(f"Strategy file already exists: {path}")
    content = _TEMPLATE.format(class_name=class_name)
    path.write_text(content, encoding="utf-8")
    return str(path)
