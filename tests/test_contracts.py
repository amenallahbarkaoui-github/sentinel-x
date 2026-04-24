"""Tests for Sentinel-X Pydantic data contracts."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from sentinel_modules.contracts import (
    BTCContext1h,
    CandidateSide,
    Decision,
    DecisionOutput,
    DecisionPayload,
    GraphContext,
    MarketContext,
    NewsContext,
    NewsEvent,
    NewsWindow,
    RSSEntry,
    TradeRecord,
    TrendDirection,
)


class TestMarketContext:
    def test_defaults(self):
        ctx = MarketContext(pair="BTC/USDT", timestamp=datetime.now(timezone.utc))
        assert ctx.timeframe == "15m"
        assert ctx.rsi == 0.0
        assert ctx.btc_context_1h.btc_trend_1h == TrendDirection.NEUTRAL

    def test_rsi_bounds(self):
        with pytest.raises(ValidationError):
            MarketContext(pair="X", timestamp=datetime.now(timezone.utc), rsi=101)
        with pytest.raises(ValidationError):
            MarketContext(pair="X", timestamp=datetime.now(timezone.utc), rsi=-1)

    def test_valid_full(self):
        ctx = MarketContext(
            pair="ETH/USDT",
            timestamp=datetime.now(timezone.utc),
            price=3000.0,
            rsi=55.0,
            macd=1.5,
            macd_signal=1.0,
            ema50=2900.0,
            ema200=2800.0,
            atr=50.0,
            volume_zscore=1.2,
            trend_1h=TrendDirection.BULLISH,
            btc_context_1h=BTCContext1h(btc_rsi_1h=60.0, btc_trend_1h=TrendDirection.BULLISH),
        )
        assert ctx.ema50 == 2900.0


class TestDecisionOutput:
    def test_defaults(self):
        out = DecisionOutput()
        assert out.decision == Decision.HOLD
        assert out.confidence == 0.0

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            DecisionOutput(confidence=1.5)
        with pytest.raises(ValidationError):
            DecisionOutput(confidence=-0.1)

    def test_sl_must_be_non_positive(self):
        with pytest.raises(ValidationError):
            DecisionOutput(proposed_sl_pct=0.05)  # positive SL invalid


class TestGraphContext:
    def test_defaults(self):
        g = GraphContext()
        assert g.similar_setups_found == 0
        assert g.top_failure_pattern == ""

    def test_winrate_bounds(self):
        with pytest.raises(ValidationError):
            GraphContext(similar_winrate=1.5)


class TestRSSEntry:
    def test_trust_score(self):
        e = RSSEntry(source="CoinDesk", title="BTC surges", trust_score=1.0)
        assert e.trust_score == 1.0

    def test_sentiment_bounds(self):
        with pytest.raises(ValidationError):
            RSSEntry(source="X", title="Y", sentiment_score=2.0)


class TestTradeRecord:
    def test_minimal(self):
        r = TradeRecord(
            pair="BTC/USDT",
            timestamp=datetime.now(timezone.utc),
            side=CandidateSide.LONG,
        )
        assert r.outcome == ""
        assert r.ema_trend == TrendDirection.NEUTRAL
