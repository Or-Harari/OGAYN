from __future__ import annotations

from pandas import DataFrame
import numpy as np

from backend.app.trading_core.base_strategy import CoreBaseStrategy
from backend.app.trading_core.indicators import macd as macd_ind, ema


def _swing_points(series, strength: int = 5):
    """Return boolean arrays for swing highs/lows using a simple pivot definition.
    A pivot at i is a high if it's >= `strength` neighbors on both sides, and similarly for lows.
    """
    n = strength
    vals = series.values
    highs = np.zeros_like(vals, dtype=bool)
    lows = np.zeros_like(vals, dtype=bool)
    for i in range(n, len(vals) - n):
        window = vals[i - n:i + n + 1]
        c = vals[i]
        if np.all(c >= window[:n]) and np.all(c >= window[n+1:]):
            highs[i] = True
        if np.all(c <= window[:n]) and np.all(c <= window[n+1:]):
            lows[i] = True
    return highs, lows


def _find_divergence(price_close, hist, bullish: bool, strength: int = 5, min_sep: int = 5):
    """Detect a single recent divergence using histogram vs price closes.
    Returns boolean mask where divergence is confirmed at the second pivot.
    """
    highs, lows = _swing_points(price_close, strength)
    h_highs, h_lows = _swing_points(hist, strength)

    sig = np.zeros(len(price_close), dtype=bool)
    if bullish:
        piv_idx = np.where(lows)[0]
        hp_idx = np.where(h_lows)[0]
        if len(piv_idx) >= 2 and len(hp_idx) >= 2:
            a, b = piv_idx[-2], piv_idx[-1]
            ha, hb = hp_idx[-2], hp_idx[-1]
            if b - a >= min_sep and hb - ha >= min_sep:
                if price_close.iloc[b] < price_close.iloc[a] and hist.iloc[hb] > hist.iloc[ha]:
                    sig[b] = True
    else:
        piv_idx = np.where(highs)[0]
        hp_idx = np.where(h_highs)[0]
        if len(piv_idx) >= 2 and len(hp_idx) >= 2:
            a, b = piv_idx[-2], piv_idx[-1]
            ha, hb = hp_idx[-2], hp_idx[-1]
            if b - a >= min_sep and hb - ha >= min_sep:
                if price_close.iloc[b] > price_close.iloc[a] and hist.iloc[hb] < hist.iloc[ha]:
                    sig[b] = True
    return sig


def _atr(df: DataFrame, window: int = 14) -> DataFrame:
    """Compute ATR using classic True Range with EMA smoothing (pandas-safe)."""
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    h_l = (high - low).abs()
    h_pc = (high - prev_close).abs()
    l_pc = (low - prev_close).abs()
    tr = (h_l.to_frame('hl')
          .join(h_pc.to_frame('hpc'))
          .join(l_pc.to_frame('lpc'))).max(axis=1)
    atr = ema(tr, window)
    return atr


class MacdSRDivergenceStrategy(CoreBaseStrategy):
    INTERFACE_VERSION = 3
    """Strategy 1: MACD Histogram Divergence + Support/Resistance reaction (informative-style within single TF).

    Simplified single-timeframe implementation:
      - Timeframe: 1h (acts as LTF)
      - S/R approximation from recent pivot highs/lows with tolerance based on ATR
      - Entry long when: recent bullish divergence AND price is near support zone AND momentum turns up
      - Exits via ROI / Stoploss
    """

    strategy_name = "MACD_SR_Divergence"

    timeframe = "1h"
    minimal_roi = {
        "120": 0.10,  # after 2 hours
        "60": 0.15,   # after 1 hour
        "0": 0.20,    # anytime
    }
    stoploss = -0.10

    process_only_new_candles = True
    startup_candle_count = 400

    # Tunables (could be exposed via hyperparams later)
    pivot_strength = 3       # S/R detection sensitivity
    divergence_window = 15       # bars after divergence to allow entry
    sr_lookback = 60             # bars to search for most recent S/R
    sr_atr_mult = 1.25         # proximity tolerance in ATRs (slightly wider)

    def populate_indicators(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        # MACD
        macd_line, signal_line, hist = macd_ind(df['close'])
        df['macd'] = macd_line
        df['macd_signal'] = signal_line
        df['macd_hist'] = hist
        # ATR for zone tolerance
        df['atr14'] = _atr(df, 14)
        # Pivots for S/R
        ph, pl = _swing_points(df['close'], strength=self.pivot_strength)
        df['pivot_high'] = ph
        df['pivot_low'] = pl

        # Most recent support/resistance levels within lookback
        # For each row, find last pivot low/high price within sr_lookback
        recent_support = []
        recent_resist = []
        close = df['close']
        for i in range(len(df)):
            a = max(0, i - self.sr_lookback)
            lows_idx = np.where(pl[a:i+1])[0]
            highs_idx = np.where(ph[a:i+1])[0]
            sup = np.nan
            res = np.nan
            if len(lows_idx) > 0:
                sup = float(close.iloc[a + lows_idx[-1]])
            if len(highs_idx) > 0:
                res = float(close.iloc[a + highs_idx[-1]])
            recent_support.append(sup)
            recent_resist.append(res)
        df['sr_support'] = recent_support
        df['sr_resist'] = recent_resist

        # Divergence detection (bullish)
        bull_div = _find_divergence(df['close'], df['macd_hist'], bullish=True, strength=self.pivot_strength, min_sep=5)
        df['macd_bull_div'] = bull_div
        df['macd_bull_div_recent'] = (df['macd_bull_div'].astype(int).rolling(window=self.divergence_window, min_periods=1).max() > 0)
        # Momentum confirmation: MACD above signal (hist >= 0)
        df['macd_above_signal'] = (df['macd'] > df['macd_signal']).fillna(False)

        # Proximity to support zone using ATR tolerance
        # Avoid deprecated fillna(method=..); use ffill/bfill
        tol = (df['atr14'] * self.sr_atr_mult).ffill().bfill()
        # use low to detect intrabar touches near support
        df['near_support'] = (df['sr_support'].notna()) & ((df['low'] - df['sr_support']).abs() <= tol)

        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        try:
            df = self.populate_indicators(df, metadata) or df
        except Exception:
            pass
        df['enter_long'] = 0
        cond = (
            (df['macd_bull_div_recent']) &
            (df['near_support']) &
            (df['macd_above_signal'])
        )
        df.loc[cond, 'enter_long'] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        if 'exit_long' not in df.columns:
            df['exit_long'] = 0
        return df
