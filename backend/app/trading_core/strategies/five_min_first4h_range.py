from __future__ import annotations

from typing import Optional, Any, Tuple
from datetime import datetime

import pandas as pd
from pandas import DataFrame
import numpy as np
try:
    # Preferred import when backend package is on sys.path
    from backend.app.trading_core.base_strategy import CoreBaseStrategy
except Exception:
    try:
        # Fallback: add repo backend path to sys.path and retry
        import sys
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[4]  # .../ft-bot
        backend_path = repo_root / "backend"
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))
        from app.trading_core.base_strategy import CoreBaseStrategy  # type: ignore
    except Exception:
        # Last-resort stub so discovery doesn't fail on import
        class CoreBaseStrategy:  # type: ignore
            INTERFACE_VERSION = 3
            def __init__(self, *args, **kwargs):
                pass
            def populate_indicators(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
                return df
            def populate_entry_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
                if 'enter_long' not in df.columns:
                    df['enter_long'] = 0
                if 'enter_short' not in df.columns:
                    df['enter_short'] = 0
                return df
            def populate_exit_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
                if 'exit_long' not in df.columns:
                    df['exit_long'] = 0
                if 'exit_short' not in df.columns:
                    df['exit_short'] = 0
                return df


class _DayState:
    def __init__(self) -> None:
        # 0 = none, +1 = broke above high, -1 = broke below low
        self.last_breakout: int = 0
        # high if +1, low if -1 (from breakout candle)
        self.breakout_extreme: Optional[float] = None


class FiveMinFirst4HRangeStrategy(CoreBaseStrategy):
    """5-Minute Scalping using first New York 4H range of the day.

    Rules (from transcript):
      - Timeframe: 5m
      - Determine the first 4-hour candle of the day using New York time (America/New_York):
        that's the range from 00:00 to 04:00 NY for that calendar day.
      - After that first 4h has CLOSED, trade only during the same NY day.
      - Setup: wait for a 5m candle CLOSE outside the 4h range (wicks don't count). That's the
        breakout in a direction. Then wait for price to CLOSE back inside the range; enter in
        the opposite direction of the breakout at that re-entry close.
          * Broke above, then re-entered inside -> enter SHORT
          * Broke below, then re-entered inside -> enter LONG
      - Stop loss: at the extreme of the breakout candle (high for short, low for long).
      - Take profit: 2R (twice the stop distance). This draft implements clean entries and leaves
        exits to ROI/SL for now. If desired, we can add custom_stoploss/custom_exit to exactly
        enforce 2R using trade metadata.

    Assumptions / Notes:
      - DataFrame 'date' column is UTC (Freqtrade default). We'll convert to America/New_York to
        compute day boundaries and the 00:00-04:00 window. If tz-naive, we assume UTC.
      - We only generate signals after 04:00 NY (when the 4h range has fully closed), and only
        until 23:59:59 of the same NY day.
      - If the 00:00-04:00 window has missing data, that day is skipped (no entries).
    """

    INTERFACE_VERSION = 3
    strategy_name = "5m_First4H_Range_Reentry"

    timeframe = "5m"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 600  # ensure enough history for early-day windows

    # Placeholders: exits can be controlled via config for now; we can add custom hooks on request
    # To enforce 2R take-profit via custom_exit, we disable ROI interference by setting a high ROI.
    minimal_roi = {"0": 1.0}  # effectively disabled for typical intraday moves
    # Base stop is overridden by custom_stoploss to use breakout extreme per trade.
    stoploss = -0.10  # fallback only (won't be used if we can compute the breakout extreme)

    # Enable per-trade dynamic stoploss based on breakout candle extreme
    use_custom_stoploss: bool = True

    def _ensure_ny_columns(self, df: DataFrame) -> DataFrame:
        # Convert 'date' to tz-aware NY time for boundary logic
        dts = df["date"]
        if pd.api.types.is_datetime64_any_dtype(dts):
            if dts.dt.tz is None:
                # Assume UTC if tz-naive
                dts = dts.dt.tz_localize("UTC")
        else:
            dts = pd.to_datetime(dts, utc=True, errors="coerce")
        ny = dts.dt.tz_convert("America/New_York")
        df = df.copy()
        df["_ny_dt"] = ny
        df["_ny_day"] = ny.dt.date
        df["_ny_hour"] = ny.dt.hour
        return df

    def _compute_daily_first4h_range(self, df: DataFrame) -> DataFrame:
        # For each NY day, compute high/low of [00:00, 04:00) NY window using 5m candles
        is_first4h = df["_ny_hour"].between(0, 3, inclusive="both")
        # Mark highs/lows in that window; others NaN
        df = df.copy()
        df["_win_high"] = df["high"].where(is_first4h)
        df["_win_low"] = df["low"].where(is_first4h)
        # Aggregate per day
        daily_high = df.groupby("_ny_day")["_win_high"].transform("max")
        daily_low = df.groupby("_ny_day")["_win_low"].transform("min")
        df["range_high"] = daily_high
        df["range_low"] = daily_low
        # Only valid after 04:00 (range closed)
        df["after_first4h"] = df["_ny_hour"] >= 4
        return df

    def populate_indicators(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        try:
            df = self._ensure_ny_columns(df)
            df = self._compute_daily_first4h_range(df)
            # Precompute position of close relative to range (only after 04:00)
            df["closed_above"] = (df["close"] > df["range_high"]) & df["after_first4h"]
            df["closed_below"] = (df["close"] < df["range_low"]) & df["after_first4h"]
            df["inside_range"] = (~df["closed_above"] & ~df["closed_below"]) & df["after_first4h"]
        except Exception:
            # If anything fails, ensure required columns exist to avoid crashes
            df = df.copy()
            for col in ("range_high", "range_low", "after_first4h", "closed_above", "closed_below", "inside_range"):
                if col not in df:
                    df[col] = pd.NA
        return df

    def _generate_entries(self, df: DataFrame) -> DataFrame:
        # Stateful per-day scan: breakout close outside, then re-entry close inside -> entry
        enter_long = pd.Series(0, index=df.index)
        enter_short = pd.Series(0, index=df.index)
        # We'll also record breakout extremes at re-entry for potential custom SL/TP extensions later
        # Use np.nan for float dtype compatibility (pd.NA is not valid for float64 in some pandas versions)
        breakout_extreme_at_entry = pd.Series(np.nan, index=df.index, dtype="float64")

        for day, gidx in df.groupby("_ny_day").groups.items():
            sub = df.loc[gidx]
            st = _DayState()
            for i, row in sub.iterrows():
                # Skip before range is closed or if the day's range is undefined
                if not bool(row.get("after_first4h", False)):
                    continue
                if pd.isna(row.get("range_high")) or pd.isna(row.get("range_low")):
                    continue

                if bool(row.get("closed_above", False)):
                    st.last_breakout = +1
                    st.breakout_extreme = float(row.get("high", float("nan")))
                    continue
                if bool(row.get("closed_below", False)):
                    st.last_breakout = -1
                    st.breakout_extreme = float(row.get("low", float("nan")))
                    continue

                # Inside the range -> potential entry if we have a pending breakout
                if bool(row.get("inside_range", False)) and st.last_breakout != 0:
                    if st.last_breakout == +1:
                        # Broke above then re-entered -> SHORT
                        enter_short.loc[i] = 1
                        breakout_extreme_at_entry.loc[i] = st.breakout_extreme if st.breakout_extreme is not None else np.nan
                    elif st.last_breakout == -1:
                        # Broke below then re-entered -> LONG
                        enter_long.loc[i] = 1
                        breakout_extreme_at_entry.loc[i] = st.breakout_extreme if st.breakout_extreme is not None else np.nan
                    # Reset to wait for next setup
                    st = _DayState()

        out = df.copy()
        out["enter_long"] = enter_long
        out["enter_short"] = enter_short
        out["breakout_extreme_at_entry"] = breakout_extreme_at_entry
        return out

    def populate_entry_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:  # type: ignore[override]
        try:
            ind = self.populate_indicators(df, metadata) or df
        except Exception:
            ind = df
        out = self._generate_entries(ind)
        return out

    def populate_exit_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:  # type: ignore[override]
        # No explicit exit signals here; rely on ROI/SL unless we add custom TP/SL hooks
        if 'exit_long' not in df.columns:
            df['exit_long'] = 0
        if 'exit_short' not in df.columns:
            df['exit_short'] = 0
        return df

    # ---- Custom SL/TP logic (exact breakout extreme stop, TP at 2R) ----
    def _get_entry_row_and_extreme(self, pair: str, open_time: datetime) -> Tuple[Optional[pd.Series], Optional[float]]:
        """Locate the row at or before trade open_time and read breakout_extreme_at_entry.

        We rely on analyzed dataframe so the column exists.
        """
        try:
            dp = getattr(self, "dp", None)
            if dp is None:
                return None, None
            df, _ = dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            # Older dp versions return only df
            try:
                df = self.dp.get_analyzed_dataframe(pair, self.timeframe)  # type: ignore
            except Exception:
                return None, None
        if df is None or df.empty:
            return None, None
        # Ensure datetime alignment
        dts = df.get("date")
        if dts is None:
            return None, None
        # Find the last candle at or before open_time
        try:
            mask = dts <= pd.Timestamp(open_time, tz="UTC")
        except Exception:
            # Attempt without forcing tz
            mask = dts <= pd.Timestamp(open_time)
        sub = df.loc[mask]
        if sub.empty:
            return None, None
        row = sub.iloc[-1]
        extreme = row.get("breakout_extreme_at_entry")
        try:
            extreme_f = float(extreme) if pd.notna(extreme) else None
        except Exception:
            extreme_f = None
        return row, extreme_f

    def _compute_risk_and_targets(self, entry: float, extreme: float, is_long: bool) -> Tuple[Optional[float], Optional[float]]:
        if any(x is None or not (x > 0) for x in [entry, extreme]):
            return None, None
        if is_long:
            risk = entry - extreme
            if risk <= 0:
                return None, None
            tp = entry + 2.0 * risk
        else:
            risk = extreme - entry
            if risk <= 0:
                return None, None
            tp = entry - 2.0 * risk
        return risk, tp

    def custom_exit(self, pair: str, trade: Any, current_time: datetime, current_rate: float,
                     current_profit: float, **kwargs: Any) -> Optional[str]:
        """Exit at 2R relative to breakout extreme.

        Returns an exit tag string to trigger exit when target is reached; otherwise None.
        """
        try:
            row, extreme = self._get_entry_row_and_extreme(pair, trade.open_date_utc)
            if extreme is None:
                return None
            entry = float(trade.open_rate)
            is_long = not bool(getattr(trade, "is_short", False))
            risk, tp = self._compute_risk_and_targets(entry, extreme, is_long)
            if risk is None or tp is None:
                return None
            # Trigger exit once price crosses target in the favorable direction
            if is_long and current_rate >= tp:
                return "TP_2R"
            if (not is_long) and current_rate <= tp:
                return "TP_2R"
            return None
        except Exception:
            return None
