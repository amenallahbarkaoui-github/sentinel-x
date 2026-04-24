"""
Sentinel-X — Risk Manager

Computes risk flags from market context.
Used by the Decision Gate to veto entries.
"""

from __future__ import annotations

from .contracts import MarketContext, TrendDirection


# ── Thresholds (tuneable) ──────────────────────────────────────────────────

RSI_EXTREME_LOW = 20.0
RSI_EXTREME_HIGH = 80.0
VOLUME_ZSCORE_LOW = -1.0
ATR_HIGH_MULTIPLIER = 2.5  # flag if ATR > 2.5× its recent average


def check_risk_flags(ctx: MarketContext, atr_avg: float = 0.0) -> list[str]:
    """
    Return a list of risk-flag strings.  Empty list = no risks detected.

    Parameters
    ----------
    ctx : MarketContext
        Current market snapshot.
    atr_avg : float
        Recent average ATR (e.g. 20-candle mean).  Pass 0 to skip ATR check.
    """
    flags: list[str] = []

    # BTC bearish on 1h
    if ctx.btc_context_1h.btc_trend_1h == TrendDirection.BEARISH:
        flags.append("btc_bearish_1h")

    # Extreme RSI
    if ctx.rsi <= RSI_EXTREME_LOW or ctx.rsi >= RSI_EXTREME_HIGH:
        flags.append("extreme_rsi")

    # Low volume
    if ctx.volume_zscore < VOLUME_ZSCORE_LOW:
        flags.append("low_volume")

    # High volatility (ATR spike)
    if atr_avg > 0 and ctx.atr > atr_avg * ATR_HIGH_MULTIPLIER:
        flags.append("high_atr_volatility")

    return flags
