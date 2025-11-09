from pandas import Series
from .ema import ema

def macd(close: Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Compute MACD line, Signal line and Histogram.

    MACD = EMA(fast) - EMA(slow)
    Signal = EMA(MACD, signal)
    Hist = MACD - Signal
    Returns tuple (macd, signal, hist)
    """
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist
