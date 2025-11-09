from __future__ import annotations

from pandas import DataFrame
import numpy as np

from backend.app.trading_core.base_strategy import CoreBaseStrategy
from backend.app.trading_core.indicators import macd as macd_ind, bbands


def _swing_points(series, strength: int = 3):
    """Return boolean Series marking swing highs (+1) and swing lows (-1).
    Simple pivot definition: value greater than/less than `strength` neighbors on both sides.
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


def _find_divergence(price: DataFrame, hist: DataFrame, bullish: bool, strength: int = 3, min_sep: int = 5):
    """Detect a single recent divergence using histogram vs price closes.
    Returns boolean mask where divergence is confirmed at the second pivot.
    """
    close = price['close']
    highs, lows = _swing_points(close, strength)
    # Use histogram pivots based on same swing logic
    h_highs, h_lows = _swing_points(hist, strength)

    sig = np.zeros(len(close), dtype=bool)
    if bullish:
        # price LL and hist HL
        piv_idx = np.where(lows)[0]
        hp_idx = np.where(h_lows)[0]
        if len(piv_idx) >= 2 and len(hp_idx) >= 2:
            a, b = piv_idx[-2], piv_idx[-1]
            ha, hb = hp_idx[-2], hp_idx[-1]
            if b - a >= min_sep and hb - ha >= min_sep:
                if close.iloc[b] < close.iloc[a] and hist.iloc[hb] > hist.iloc[ha]:
                    sig[b] = True
    else:
        # price HH and hist LH
        piv_idx = np.where(highs)[0]
        hp_idx = np.where(h_highs)[0]
        if len(piv_idx) >= 2 and len(hp_idx) >= 2:
            a, b = piv_idx[-2], piv_idx[-1]
            ha, hb = hp_idx[-2], hp_idx[-1]
            if b - a >= min_sep and hb - ha >= min_sep:
                if close.iloc[b] > close.iloc[a] and hist.iloc[hb] < hist.iloc[ha]:
                    sig[b] = True
    return sig


class MacdBBDivergenceStrategy(CoreBaseStrategy):
    """MACD Histogram Divergence + Bollinger(200,2) re-entry.

    Long-only implementation:
      - Bullish divergence via MACD histogram vs price
      - Price closes back inside lower band after being below it
      - ROI/SL as provided
    """

    strategy_name = "MACD_BB_Divergence"

    timeframe = "4h"
    minimal_roi = {
        # minutes: ROI target
        "120": 0.10,  # after 2 hours
        "60": 0.15,   # after 1 hour
        "0": 0.20,    # anytime
    }
    stoploss = -0.10

    process_only_new_candles = True
    startup_candle_count = 300  # enough for EMA200 + MACD warmup

    def populate_indicators(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        # MACD
        macd_line, signal_line, hist = macd_ind(df['close'])
        df['macd'] = macd_line
        df['macd_signal'] = signal_line
        df['macd_hist'] = hist
        # Bollinger(200,2)
        upper, mid, lower = bbands(df['close'], window=200, dev=2.0)
        df['bb_upper_200_2'] = upper
        df['bb_mid_200_2'] = mid
        df['bb_lower_200_2'] = lower
        # Divergence (bullish) detection mask at pivot b
        bull_div = _find_divergence(df[['close']], df['macd_hist'], bullish=True, strength=3, min_sep=5)
        # mark exact pivot divergence
        df['macd_bull_div'] = bull_div
        # be less strict: allow entries on re-entry that occurs within a short window after a detected divergence
        # recent divergence within last 10 candles
        df['macd_bull_div_recent'] = (
            df['macd_bull_div'].astype(int).rolling(window=10, min_periods=1).max() > 0
        )
        # Track "outside lower band then close back inside" with a small lookback (allow up to 5 candles between outside and re-entry)
        below_lower = (df['close'] < lower)
        prev_below_any = (
            below_lower.shift(1).rolling(window=5, min_periods=1).max().fillna(0) > 0
        )
        back_inside = (df['close'] >= lower)
        df['bb_reentry_long'] = (prev_below_any & back_inside).fillna(False)
        # Optional momentum confirmation: histogram turning up
        df['macd_hist_turn_up'] = (df['macd_hist'] > df['macd_hist'].shift(1)).fillna(False)
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        try:
            df = self.populate_indicators(df, metadata) or df
        except Exception:
            pass
        df['enter_long'] = 0
        # Conditions for long (less strict):
        # - A recent bullish divergence occurred within the last 10 candles
        # - Price has re-entered the bands after being below the lower band within the last 5 candles
        # - Optional: MACD histogram is turning up
        cond = (
            (df['macd_bull_div_recent']) &
            (df['bb_reentry_long']) &
            (df['macd_hist_turn_up'])
        )
        df.loc[cond, 'enter_long'] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        # We lean on ROI/SL for exits; keep explicit exit empty
        if 'exit_long' not in df.columns:
            df['exit_long'] = 0
        return df
