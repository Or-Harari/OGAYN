import numpy as np
from pandas import Series

def rsi(close: Series, length: int = 14):
    diff = close.diff()
    up = diff.clip(lower=0)
    down = -diff.clip(upper=0)
    roll_up = up.ewm(alpha=1 / length, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / length, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))
