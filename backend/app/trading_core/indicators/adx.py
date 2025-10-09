from __future__ import annotations
import numpy as np
from pandas import DataFrame, Series

def _true_range(h: Series, l: Series, c: Series):
    prev_close = c.shift(1)
    tr1 = h - l
    tr2 = (h - prev_close).abs()
    tr3 = (l - prev_close).abs()
    return np.nanmax(np.vstack([tr1.values, tr2.values, tr3.values]), axis=0)

def adx(high: Series, low: Series, close: Series, period: int = 14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = DataFrame(_true_range(high, low, close), index=high.index)
    atr = tr.rolling(period).mean().iloc[:, 0]
    plus_di = 100 * (DataFrame(plus_dm, index=high.index).rolling(period).mean().iloc[:, 0] / atr)
    minus_di = 100 * (DataFrame(minus_dm, index=high.index).rolling(period).mean().iloc[:, 0] / atr)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.rolling(period).mean().fillna(0)
