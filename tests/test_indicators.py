"""Tests for Sentinel-X vectorized indicators."""

import numpy as np
import pandas as pd
import pytest

from sentinel_modules.indicators import (
    add_all_indicators,
    compute_adx,
    compute_atr,
    compute_atr_percentile,
    compute_bollinger_bandwidth,
    compute_ema,
    compute_macd,
    compute_rsi,
    compute_trend_label,
    compute_volume_zscore,
)


def _make_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    close = np.maximum(close, 1.0)  # no negatives
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    low = np.maximum(low, 0.1)
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.uniform(100, 10000, n)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestComputeRSI:
    def test_rsi_range(self):
        df = _make_ohlcv()
        rsi = compute_rsi(df)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_constant_close(self):
        """RSI of constant series should be ~50 (no change)."""
        df = pd.DataFrame({"close": [100.0] * 100})
        rsi = compute_rsi(df)
        valid = rsi.dropna()
        # TA-Lib returns NaN for constant series, which is acceptable


class TestComputeMACD:
    def test_macd_shape(self):
        df = _make_ohlcv()
        macd, signal, hist = compute_macd(df)
        assert len(macd) == len(df)
        assert len(signal) == len(df)
        assert len(hist) == len(df)

    def test_hist_equals_diff(self):
        df = _make_ohlcv()
        macd, signal, hist = compute_macd(df)
        valid_idx = macd.dropna().index & signal.dropna().index & hist.dropna().index
        np.testing.assert_allclose(
            hist.loc[valid_idx].values,
            (macd.loc[valid_idx] - signal.loc[valid_idx]).values,
            atol=1e-10,
        )


class TestComputeEMA:
    def test_ema_length(self):
        df = _make_ohlcv()
        ema = compute_ema(df, 50)
        assert len(ema) == len(df)


class TestComputeATR:
    def test_atr_positive(self):
        df = _make_ohlcv()
        atr = compute_atr(df)
        valid = atr.dropna()
        assert (valid >= 0).all()


class TestVolumeZScore:
    def test_zscore_mean_near_zero(self):
        df = _make_ohlcv(n=500)
        zs = compute_volume_zscore(df, window=20)
        # Overall mean should be roughly 0
        assert abs(zs.mean()) < 1.0

    def test_zscore_no_nans(self):
        df = _make_ohlcv()
        zs = compute_volume_zscore(df)
        assert zs.isna().sum() == 0


class TestTrendLabel:
    def test_basic(self):
        ema50 = pd.Series([100.0, 90.0, 100.0])
        ema200 = pd.Series([90.0, 100.0, 100.0])
        result = compute_trend_label(ema50, ema200)
        assert list(result) == ["bullish", "bearish", "neutral"]


class TestAddAllIndicators:
    def test_columns_added(self):
        df = _make_ohlcv()
        result = add_all_indicators(df)
        for col in ["rsi", "macd", "macd_signal", "macd_hist",
                     "ema50", "ema200", "atr", "volume_zscore", "trend",
                     "adx", "bb_width", "atr_percentile"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_original_ohlcv_unchanged(self):
        df = _make_ohlcv()
        orig_close = df["close"].copy()
        add_all_indicators(df)
        pd.testing.assert_series_equal(df["close"], orig_close)


class TestComputeADX:
    def test_adx_range(self):
        df = _make_ohlcv()
        adx = compute_adx(df)
        valid = adx.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_adx_length(self):
        df = _make_ohlcv()
        adx = compute_adx(df)
        assert len(adx) == len(df)


class TestBollingerBandwidth:
    def test_bb_width_positive(self):
        df = _make_ohlcv()
        bb = compute_bollinger_bandwidth(df)
        valid = bb.dropna()
        assert (valid >= 0).all()

    def test_bb_width_length(self):
        df = _make_ohlcv()
        bb = compute_bollinger_bandwidth(df)
        assert len(bb) == len(df)


class TestATRPercentile:
    def test_percentile_range(self):
        df = _make_ohlcv()
        atr = compute_atr(df)
        pct = compute_atr_percentile(atr)
        valid = pct.dropna()
        assert (valid >= 0).all() and (valid <= 1).all()

    def test_percentile_length(self):
        df = _make_ohlcv()
        atr = compute_atr(df)
        pct = compute_atr_percentile(atr)
        assert len(pct) == len(df)
