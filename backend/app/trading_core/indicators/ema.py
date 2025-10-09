from pandas import Series

def ema(series: Series, span: int):
    return series.ewm(span=span, adjust=False).mean()
