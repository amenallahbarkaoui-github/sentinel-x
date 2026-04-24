"""
Sentinel-X — Vectorized Technical Indicators

All functions operate on DataFrame columns. No loops, no iloc[-1].
Only indicators used in entry/exit logic are computed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas import DataFrame

import talib.abstract as ta


def compute_rsi(dataframe: DataFrame, period: int = 14, col: str = "close") -> pd.Series:
    """RSI — Relative Strength Index."""
    return pd.Series(ta.RSI(dataframe[col], timeperiod=period), index=dataframe.index)


def compute_macd(
    dataframe: DataFrame,
    fastperiod: int = 12,
    slowperiod: int = 26,
    signalperiod: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram."""
    result = ta.MACD(
        dataframe["close"],
        fastperiod=fastperiod,
        slowperiod=slowperiod,
        signalperiod=signalperiod,
    )
    # ta.MACD returns a list of 3 numpy arrays: [macd, signal, hist]
    return (
        pd.Series(result[0], index=dataframe.index),
        pd.Series(result[1], index=dataframe.index),
        pd.Series(result[2], index=dataframe.index),
    )


def compute_ema(dataframe: DataFrame, period: int, col: str = "close") -> pd.Series:
    """Exponential Moving Average."""
    return pd.Series(ta.EMA(dataframe[col], timeperiod=period), index=dataframe.index)


def compute_atr(dataframe: DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    return pd.Series(
        ta.ATR(dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=period),
        index=dataframe.index,
    )


def compute_volume_zscore(dataframe: DataFrame, window: int = 20) -> pd.Series:
    """Rolling z-score of volume over *window* candles."""
    vol = dataframe["volume"].astype(float)
    mean = vol.rolling(window=window, min_periods=1).mean()
    std = vol.rolling(window=window, min_periods=1).std().replace(0, np.nan)
    return ((vol - mean) / std).fillna(0.0)


def compute_trend_label(ema50: pd.Series, ema200: pd.Series) -> pd.Series:
    """
    Return vectorized trend label:
      'bullish'  if ema50 > ema200
      'bearish'  if ema50 < ema200
      'neutral'  otherwise (equal / NaN)
    """
    conditions = [ema50 > ema200, ema50 < ema200]
    choices = ["bullish", "bearish"]
    return pd.Series(
        np.select(conditions, choices, default="neutral"),
        index=ema50.index,
    )


def compute_adx(dataframe: DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength (0–100)."""
    return pd.Series(
        ta.ADX(dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=period),
        index=dataframe.index,
    )


def compute_bollinger_bandwidth(
    dataframe: DataFrame, period: int = 20, nbdev: float = 2.0
) -> pd.Series:
    """Bollinger Bandwidth = (upper − lower) / middle.  Measures vol expansion."""
    result = ta.BBANDS(dataframe["close"], timeperiod=period, nbdevup=nbdev, nbdevdn=nbdev)
    upper = pd.Series(result[0], index=dataframe.index)
    middle = pd.Series(result[1], index=dataframe.index)
    lower = pd.Series(result[2], index=dataframe.index)
    return ((upper - lower) / middle.replace(0, np.nan)).fillna(0.0)


def compute_atr_percentile(atr: pd.Series, lookback: int = 100) -> pd.Series:
    """Rolling percentile rank of ATR over *lookback* candles (0–1)."""
    return atr.rolling(lookback, min_periods=1).rank(pct=True).fillna(0.5)


def add_all_indicators(dataframe: DataFrame) -> DataFrame:
    """Add every v1 indicator to *dataframe* in-place and return it."""
    dataframe["rsi"] = compute_rsi(dataframe)
    dataframe["macd"], dataframe["macd_signal"], dataframe["macd_hist"] = compute_macd(dataframe)
    dataframe["ema50"] = compute_ema(dataframe, 50)
    dataframe["ema200"] = compute_ema(dataframe, 200)
    dataframe["atr"] = compute_atr(dataframe)
    dataframe["volume_zscore"] = compute_volume_zscore(dataframe)
    dataframe["trend"] = compute_trend_label(dataframe["ema50"], dataframe["ema200"])
    # V15 regime indicators
    dataframe["adx"] = compute_adx(dataframe)
    dataframe["bb_width"] = compute_bollinger_bandwidth(dataframe)
    dataframe["atr_percentile"] = compute_atr_percentile(dataframe["atr"])
    return dataframe
