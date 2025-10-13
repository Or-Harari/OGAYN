from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from pandas import DataFrame

from ..base_strategy import CoreBaseStrategy


@dataclass
class Params:
    # Eligibility (1d informative)
    min_day_change: float = 0.10  # +10%
    min_rvol: float = 5.0         # RVOL >= 5, defined as cumulative intraday QV vs 20-day daily QV SMA

    # Pullback
    pullback_lookback: int = 20   # rolling swing-high lookback (bars), capped at 20
    max_drawdown: float = 0.30    # pullback <= 30%

    # MACD distance from signal (avoid imminent crossover)
    macd_gap_ratio_min: float = 0.0005  # |macd - signal| / close >= gap

    # Volume (pullback sell vol relatively low)
    vol_sma_window: int = 60
    red_vol_sma_window: int = 20
    red_vol_rel_ceiling: float = 0.8  # avg red volume must be <= 0.8 * vol_sma


class MomentumPullbackStrategy(CoreBaseStrategy):
    """
    Momentum-pullback strategy per user spec.

    - timeframe: 1m
    - Eligibility to watch: daily change >= +10% and RVOL >= 5
    - Entry: pullback drawdown <= 30% from recent swing-high, stays above EMA9 or VWAP,
             MACD not near cross, relatively low sell volume, confirmation green candle closes > prev open
    - Exit: on 3rd pullback completion or when price breaks below both EMA9 and VWAP (trailing)
    - SL: -10%, ROI: +10%

    Note on "today" metrics:
    Freqtrade does not expose incomplete 1d candles. We compute day-open and day-anchored VWAP from 1m candles
    by resetting at UTC day boundaries.
    """

    name = "MomentumPullbackStrategy"

    timeframe = "1m"
    startup_candle_count = 600  # ensure enough for rolling and day-anchored calcs

    minimal_roi = {"0": 0.10}
    stoploss = -0.10
    use_exit_signal = True
    can_short = False

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.p = Params()

    # Request orchestrator to precompute some basics
    def required_indicators(self) -> dict:
        return {
            "ema9": {"type": "ema", "length": 9, "source": "close"},
            "macd": {"type": "macd", "fast": 12, "slow": 26, "signal": 9,
                      "columns": ["macd", "macd_signal", "macd_hist"]},
            "vol_sma": {"type": "sma", "length": self.p.vol_sma_window, "on": "volume"},
        }

    def populate_indicators(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        if df.empty:
            # Ensure dataframe is returned, even if untouched
            return df
        # Ensure datetime and a UTC-day id
        dt = pd.to_datetime(df["date"], utc=True)
        day_id = dt.dt.floor("D")
        # Quote-volume
        df["quote_volume"] = df["volume"] * df["close"]
        # Build day-anchored cumulative PV and V once (used for RVOL and VWAP)
        pv = df["quote_volume"]
        cum_pv = pv.groupby(day_id).cumsum()
        cum_v = df["volume"].groupby(day_id).cumsum()

        # Daily context provided by orchestrator (merged from 1d informative):
        # - daily_prev_close: last completed daily close
        # - daily_qv_sma20: 20-day SMA of daily quote volume
        # Compute intraday day_change vs previous daily close
        if "daily_prev_close" in df:
            df["day_change"] = (df["close"] / df["daily_prev_close"]) - 1.0
        else:
            # Fallback to day-open method if informative missing
            day_first_open = df.groupby(day_id)["open"].transform("first")
            df["day_change"] = (df["close"] / day_first_open) - 1.0

        # RVOL versus daily baseline: cumulative intraday QV vs 20-day daily QV EMA (preferred) or SMA fallback
        if "daily_qv_ema20" in df:
            df["rvol"] = (cum_pv / df["daily_qv_ema20"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        elif "daily_qv_sma20" in df:
            df["rvol"] = (cum_pv / df["daily_qv_sma20"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        else:
            # Fallback to intraday SMA baseline if informative missing
            qv_sma = df["quote_volume"].rolling(60).mean()
            df["rvol"] = (df["quote_volume"] / qv_sma).replace([np.inf, -np.inf], np.nan).fillna(0.0)

        # Daily anchored VWAP (from intraday 1m data as proxy), reset per UTC day
        df["vwap_day"] = (cum_pv / cum_v).replace([np.inf, -np.inf], np.nan).fillna(df["close"])  # fallback

        # Day-anchored running high and drawdown from today's high (pullback definition)
        day_high = df["high"].groupby(day_id).cummax()
        df["day_high"] = day_high
        dd_day = (day_high - df["close"]) / day_high
        df["drawdown_day"] = dd_day.replace([np.inf, -np.inf], np.nan).clip(lower=0.0).fillna(0.0)

        # Identify pullback start when price falls from today's high within max drawdown
        pullback_active = (df["drawdown_day"] > 0.0) & (df["drawdown_day"] <= self.p.max_drawdown)
        pullback_started = pullback_active & (~pullback_active.shift(1).fillna(False))
        df["pullback_started"] = pullback_started.astype(int)

        # Capture the last high before pullback, then forward-fill within the day
        pre_pb_high = day_high.where(pullback_started)
        df["pre_pullback_high"] = pre_pb_high.groupby(day_id).ffill()

        # Eligibility state per day (after first eligibility moment)
        eligible = (df["day_change"] >= self.p.min_day_change) & (df["rvol"] >= self.p.min_rvol)
        df["eligible"] = eligible
        df["eligible_after_first"] = eligible.groupby(day_id).cummax()

        # A pullback completes when price reclaims (closes above) the pre-pullback day high with a green candle,
        # count only the first candle that achieves this (rising-edge) to avoid double counting across consecutive bars.
        pullback_completion_now = (
            df["eligible_after_first"]
            & df["pre_pullback_high"].notna()
            & (df["close"] > df["pre_pullback_high"]) 
            & (df["close"] > df["open"])  # green
            & pullback_active.shift(1).fillna(False)
        )
        df["pullback_completion_now"] = pullback_completion_now
        df["pbk_comp_count"] = pullback_completion_now.groupby(day_id).cumsum()

        # Red-volume measures (approximation for "pullback sell volume relatively low")
        red_mask = (df["close"] < df["open"]).astype(int)
        df["red_vol"] = df["volume"] * red_mask
        df["red_vol_sma"] = df["red_vol"].rolling(self.p.red_vol_sma_window).mean()
        return df

    # ---------- Freqtrade signal methods ----------
    def populate_entry_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:  # type: ignore[override]
        self.populate_indicators(df, metadata)
        if df.empty:
            df['enter_long'] = 0
            return df
        p = self.p
        above_ema_or_vwap = (df["low"] >= df["ema9"]) | (df["low"] >= df["vwap_day"]) 
        macd_gap = (df["macd"] - df["macd_signal"]).abs() / df["close"].replace(0, np.nan)
        macd_ok = (macd_gap >= p.macd_gap_ratio_min) & (df.get("macd_hist", 0) >= 0)
        vol_ceiling = (df.get("red_vol_sma", 0).fillna(0) <= (df.get("vol_sma", 0).fillna(0) * p.red_vol_rel_ceiling))
        first_completion = df.get("pbk_comp_count", 0) == 1
        completion_now = df.get("pullback_completion_now", False)
        mask = (completion_now & first_completion & above_ema_or_vwap & macd_ok & vol_ceiling).fillna(False)
        df['enter_long'] = 0
        df.loc[mask, 'enter_long'] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:  # type: ignore[override]
        if df.empty:
            df['exit_long'] = 0
            return df
        trailing_break = (df["close"] < df["ema9"]) & (df["close"] < df["vwap_day"]) & (df.get("pbk_comp_count", 0) >= 1)
        third_completion = df.get("pbk_comp_count", 0) >= 3
        mask = (trailing_break | third_completion).fillna(False)
        df['exit_long'] = 0
        df.loc[mask, 'exit_long'] = 1
        return df
