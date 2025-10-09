from __future__ import annotations

import logging
from pandas import DataFrame
from typing import Any

try:
    from freqtrade.strategy import IStrategy  # type: ignore
except Exception:  # pragma: no cover - fallback during tooling without freqtrade
    class IStrategy:  # type: ignore
        pass


class CoreBaseStrategy(IStrategy):
    """Minimal shared base for all project strategies.

    Provides:
      - Standard logger namespace
      - Hook structure for indicators and entry/exit mask style strategies
      - Compatibility shim so variant strategies can choose override depth.
    """

    strategy_name: str | None = None  # optional human label

    def __init__(self, config: dict | None = None, *args: Any, **kwargs: Any) -> None:  # freqtrade passes config as positional kw
        # Freqtrade's IStrategy expects the config dict as first arg OR via kwargs
        # Support both while remaining tolerant if framework changes
        if config is None and args:
            # if caller passed config positionally, shift it
            config = args[0]
            args = args[1:]
        try:
            super().__init__(config)  # type: ignore[arg-type]
        except TypeError:
            # Fallback: older/newer signature may require kwargs
            try:
                super().__init__(config=config)  # type: ignore
            except Exception:
                # Last resort: call without config (not ideal, but prevents hard crash during development)
                super().__init__()  # type: ignore
        self.config = config or {}
        name = self.__class__.__name__
        self.logger = logging.getLogger(f"freqtrade.strategy.{name}")

    # --- Indicator & signal hook style (optional for subclass) ---
    def required_indicators(self) -> dict:
        return {}

    def populate_indicators(self, df: DataFrame) -> None:  # mutate df
        pass

    # Mask-based optional API (used by orchestrator layer) -----------------
    def entry_mask(self, df: DataFrame):  # return boolean Series or array-like
        return None

    def exit_mask(self, df: DataFrame):
        return None

    # Freqtrade standard methods expected to return a DataFrame -------------
    # Subclasses (like MainStrategy) will implement populate_entry_trend / populate_exit_trend.

__all__ = ["CoreBaseStrategy"]