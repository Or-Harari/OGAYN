from __future__ import annotations

from pandas import DataFrame
import numpy as np

from backend.app.trading_core.base_strategy import CoreBaseStrategy
from backend.app.trading_core.indicators import macd as macd_ind, ema
from backend.app.trading_core.indicators.rsi import rsi as rsi_ind
from backend.app.trading_core.indicators.adx import adx as adx_ind


class MacdMomentumStrategy(CoreBaseStrategy):
    """Strategy 3: Momentum (MACD + Trend + Strength)

    Concept (single timeframe):
      - Trade with trend (price above EMA trend filter)
      - Require momentum up (MACD > signal and histogram rising)
      - Require market strength (ADX above threshold) and RSI regime (> 50)
      - Exits via ROI / Stoploss
    """

    INTERFACE_VERSION = 3
    strategy_name = "MACD_Momentum"

    timeframe = "1h"
    minimal_roi = {
        "40": 0.02,  # after 2 hours
        "20": 0.03,   # after 1 hour
        "0": 0.05,    # anytime
    }
    stoploss = -0.02
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 300

    # Tunables (could be exposed via hyperparams later)
    trend_ema_period = 200    # trend filter period
    adx_period = 14           # ADX period
    adx_threshold = 20.0      # minimal market strength
    rsi_period = 14           # RSI period
    rsi_threshold = 50.0      # bullish RSI regime
    hist_rising_bars = 1      # require N bars of hist rising (1 = just last bar rising)

    def populate_indicators(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        # Trend filter
        df['ema_trend'] = ema(df['close'], self.trend_ema_period)
        # Momentum (MACD)
        macd_line, signal_line, hist = macd_ind(df['close'])
        df['macd'] = macd_line
        df['macd_signal'] = signal_line
        df['macd_hist'] = hist
        df['macd_above_signal'] = (df['macd'] > df['macd_signal']).fillna(False)
        # Rising histogram
        df['hist_rising'] = (df['macd_hist'] > df['macd_hist'].shift(1)).fillna(False)
        if self.hist_rising_bars > 1:
            roll = df['hist_rising'].astype(int).rolling(self.hist_rising_bars, min_periods=1).sum()
            df['hist_rising_n'] = (roll >= self.hist_rising_bars)
        else:
            df['hist_rising_n'] = df['hist_rising']
        # RSI regime
        df['rsi'] = rsi_ind(df['close'], self.rsi_period)
        # Market strength
        df['adx'] = adx_ind(df['high'], df['low'], df['close'], self.adx_period)
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        try:
            df = self.populate_indicators(df, metadata) or df
        except Exception:
            pass
        df['enter_short'] = 0
        cond = (
            (df['close'] > df['ema_trend']) &
            (df['macd_above_signal']) &
            (df['macd_hist'] > 0) &
            (df['hist_rising_n']) &
            (df['adx'] >= self.adx_threshold) &
            (df['rsi'] >= self.rsi_threshold)
        )
        df.loc[cond, 'enter_short'] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict | None = None) -> DataFrame:
        if 'exit_short' not in df.columns:
            df['exit_short'] = 0
        return df

    # Notes on defaults / missing information
    # ---------------------------------------
    # The transcript did not specify exact momentum filters and thresholds.
    # Defaults assumed here:
    # - Timeframe: 1h (kept consistent with Strategy 1)
    # - Trend filter: EMA(200) as standard bullish regime filter
    # - Momentum: MACD > Signal and MACD histogram > 0 with last bar rising
    # - Strength filters: ADX(14) >= 20 and RSI(14) >= 50
    # - Exits: ROI/SL only (no explicit trailing/exit signals)
    # If you want different momentum/strength definitions (e.g., EMA length, ADX/RSI thresholds,
    # or histogram rising streak), we can expose them as hyperparams or adjust constants above.
