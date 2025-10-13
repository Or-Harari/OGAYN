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

    # --- Common Freqtrade strategy parameters (strategy-owned) ---
    # Required / commonly used
    timeframe: str = "1m"
    minimal_roi: dict = {"0": 0.10}
    stoploss: float = -0.10

    # Trade slots
    max_open_trades: int = 3

    # Trailing stop settings
    trailing_stop: bool = False
    trailing_stop_positive: float | None = None
    trailing_stop_positive_offset: float | None = None
    trailing_only_offset_is_reached: bool = False

    # Optional custom stoploss hook usage (method to be implemented by subclass if used)
    use_custom_stoploss: bool = False

    # Engine behavior
    process_only_new_candles: bool = True
    disable_dataframe_checks: bool = False

    # Orders
    order_types: dict | None = {
        "entry": "limit",
        "exit": "limit",
        "emergency_exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "stoploss": "market",
        # Required by recent Freqtrade versions to complete the mapping
        "stoploss_on_exchange": False,
        "stoploss_on_exchange_interval": 60,
    }
    order_time_in_force: dict | None = {
        "entry": "GTC",
        "exit": "GTC",
    }
    unfilledtimeout: dict | None = {
        "entry": 10,
        "exit": 10,
        "exit_timeout_count": 0,
        "unit": "minutes",
    }

    # Exit logic controls
    use_exit_signal: bool = True
    exit_profit_only: bool = False
    exit_profit_offset: float = 0.0
    ignore_roi_if_entry_signal: bool = False
    ignore_buying_expired_candle_after: int | float | None = None  # disabled by default

    # Position adjustment (DCA / scaling)
    position_adjustment_enable: bool = False
    max_entry_position_adjustment: int = 0

    # Other common flags
    can_short: bool = False
    startup_candle_count: int = 600

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

    def populate_indicators(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        """Default no-op indicator hook.

        Freqtrade expects populate_indicators to return a DataFrame. Even if subclasses
        mutate in-place, they must still return df to avoid NoneType propagation in the
        framework's advise flow.
        """
        return df

    # Freqtrade standard methods expected to return a DataFrame -------------
    # Subclasses should override these and set 'enter_long' / 'exit_long' columns.
    def populate_entry_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:  # type: ignore[override]
        # Let subclasses add indicators first (no-op by default)
        try:
            df = self.populate_indicators(df, metadata) or df
        except Exception:
            # Keep df as-is if indicator step fails to ensure framework stability
            df = df
        if 'enter_long' not in df.columns:
            df['enter_long'] = 0
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:  # type: ignore[override]
        if 'exit_long' not in df.columns:
            df['exit_long'] = 0
        return df

__all__ = ["CoreBaseStrategy"]