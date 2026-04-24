"""Tests for Sentinel-X Decision Gate."""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from sentinel_modules.contracts import (
    BTCContext1h,
    Decision,
    DecisionOutput,
    GraphContext,
    MarketContext,
    NewsContext,
    NewsWindow,
    TrendDirection,
)
from sentinel_modules.decision_gate import (
    decide,
    heuristic_validate,
    rule_check_long,
)


def _bullish_market(**overrides) -> MarketContext:
    """A market context that passes all rule-engine checks."""
    defaults = dict(
        pair="BTC/USDT",
        timestamp=datetime.now(timezone.utc),
        price=50000.0,
        rsi=55.0,
        macd=1.5,
        macd_signal=1.0,
        ema50=49000.0,
        ema200=48000.0,
        atr=200.0,
        volume_zscore=1.0,
        trend_1h=TrendDirection.BULLISH,
        btc_context_1h=BTCContext1h(btc_rsi_1h=55.0, btc_trend_1h=TrendDirection.BULLISH),
    )
    defaults.update(overrides)
    return MarketContext(**defaults)


def _positive_news() -> NewsContext:
    return NewsContext(
        window_4h=NewsWindow(
            headline_count=5,
            weighted_sentiment=0.4,
            trust_weighted_sentiment=0.3,
        ),
    )


class TestRuleCheckLong:
    def test_all_pass(self):
        result = rule_check_long(_bullish_market())
        assert result.passed is True

    def test_ema_cross_fail(self):
        result = rule_check_long(_bullish_market(ema50=47000.0, ema200=48000.0))
        assert result.passed is False
        assert "ema50" in result.reason

    def test_rsi_too_low(self):
        result = rule_check_long(_bullish_market(rsi=30.0))
        assert result.passed is False
        assert "rsi" in result.reason

    def test_rsi_too_high(self):
        result = rule_check_long(_bullish_market(rsi=75.0))
        assert result.passed is False

    def test_macd_no_confirmation(self):
        result = rule_check_long(_bullish_market(macd=0.5, macd_signal=1.0))
        assert result.passed is False
        assert "macd" in result.reason

    def test_low_volume(self):
        result = rule_check_long(_bullish_market(volume_zscore=-1.0))
        assert result.passed is False
        assert "volume" in result.reason

    def test_sentiment_check_live(self):
        bad_news = NewsContext(
            window_4h=NewsWindow(
                headline_count=3,
                weighted_sentiment=-0.5,
                trust_weighted_sentiment=-0.3,
            ),
        )
        result = rule_check_long(_bullish_market(), news=bad_news)
        assert result.passed is False
        assert "sentiment" in result.reason

    def test_no_news_skips_sentiment(self):
        result = rule_check_long(_bullish_market(), news=None)
        assert result.passed is True


class TestHeuristicValidate:
    def test_high_winrate_high_confidence(self):
        graph = GraphContext(similar_setups_found=10, similar_winrate=0.7, avg_pnl_pct=0.02)
        score = heuristic_validate(_bullish_market(), _positive_news(), graph)
        assert score > 0.8

    def test_low_winrate_low_confidence(self):
        graph = GraphContext(similar_setups_found=10, similar_winrate=0.25, avg_pnl_pct=-0.01)
        score = heuristic_validate(_bullish_market(), _positive_news(), graph)
        assert score < 0.6

    def test_btc_bearish_penalizes(self):
        market = _bullish_market(
            btc_context_1h=BTCContext1h(btc_rsi_1h=35.0, btc_trend_1h=TrendDirection.BEARISH),
        )
        score = heuristic_validate(market, _positive_news(), None)
        assert score < 0.7


class TestOrchestratorDecide:
    def test_backtest_rules_pass_returns_buy(self):
        result = decide(_bullish_market(), is_live=False)
        assert result.decision == Decision.BUY
        assert result.l1_passed is True

    def test_backtest_rules_fail_returns_hold(self):
        result = decide(_bullish_market(rsi=30.0), is_live=False)
        assert result.decision == Decision.HOLD
        assert result.l1_passed is False

    def test_risk_flags_force_hold(self):
        result = decide(_bullish_market(), risk_flags=["btc_bearish_1h"], is_live=True)
        assert result.decision == Decision.HOLD
        assert "risk_flags" in result.entry_reason
        assert result.l1_passed is False

    def test_live_full_pipeline_with_llm_mock(self):
        mock_output = DecisionOutput(
            decision=Decision.BUY,
            confidence=0.8,
            entry_reason="strong bullish setup",
            proposed_sl_pct=-0.03,
            proposed_tp_pct=0.05,
            market_regime="trending_bullish",
            risk_level="low",
            l3_called=True,
        )
        with patch("sentinel_modules.decision_gate.llm_decide", return_value=mock_output):
            result = decide(
                _bullish_market(),
                news=_positive_news(),
                graph=GraphContext(similar_setups_found=5, similar_winrate=0.6, avg_pnl_pct=0.015),
                is_live=True,
            )
        assert result.decision == Decision.BUY
        assert result.confidence == 0.8
        assert result.l1_passed is True
        assert result.l2_confidence > 0.0
        assert result.l3_called is True
        assert result.market_regime == "trending_bullish"

    def test_heuristic_low_returns_hold_with_metadata(self):
        """When L2 confidence is too low, result includes l1_passed=True and l2 score."""
        market = _bullish_market(
            btc_context_1h=BTCContext1h(btc_rsi_1h=35.0, btc_trend_1h=TrendDirection.BEARISH),
            trend_1h=TrendDirection.BEARISH,
        )
        result = decide(market, news=_positive_news(), is_live=True)
        assert result.decision == Decision.HOLD
        assert result.l1_passed is True
        assert result.l2_confidence < 0.5
        assert "heuristic_low" in result.entry_reason


class TestRiskManager:
    def test_btc_bearish_flag(self):
        from sentinel_modules.risk_manager import check_risk_flags

        ctx = _bullish_market(
            btc_context_1h=BTCContext1h(btc_rsi_1h=35.0, btc_trend_1h=TrendDirection.BEARISH),
        )
        flags = check_risk_flags(ctx)
        assert "btc_bearish_1h" in flags

    def test_extreme_rsi_flag(self):
        from sentinel_modules.risk_manager import check_risk_flags

        ctx = _bullish_market(rsi=85.0)
        flags = check_risk_flags(ctx)
        assert "extreme_rsi" in flags

    def test_no_flags_on_clean_market(self):
        from sentinel_modules.risk_manager import check_risk_flags

        ctx = _bullish_market()
        flags = check_risk_flags(ctx)
        assert flags == []
