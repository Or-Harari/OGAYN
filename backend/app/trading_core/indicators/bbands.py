from pandas import Series

def bbands(close: Series, window: int = 20, dev: float = 2.0):
    mid = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    upper = mid + dev * std
    lower = mid - dev * std
    return upper, mid, lower
