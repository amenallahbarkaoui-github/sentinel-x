"""Tests for Sentinel-X Telegram Notifier."""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from sentinel_modules.contracts import (
    BTCContext1h,
    Decision,
    DecisionOutput,
    MarketContext,
    NewsContext,
    NewsWindow,
    TrendDirection,
)
from sentinel_modules.telegram_notifier import TelegramNotifier


def _sample_market() -> MarketContext:
    return MarketContext(
        pair="BTC/USDT",
        timestamp=datetime.now(timezone.utc),
        price=67450.0,
        rsi=52.3,
        macd=1.5,
        macd_signal=1.0,
        macd_hist=0.5,
        ema50=66000.0,
        ema200=65000.0,
        atr=350.0,
        volume_zscore=1.2,
        ema_spread_pct=1.54,
        adx=24.5,
        atr_percentile=0.45,
        bb_width=0.032,
        trend_1h=TrendDirection.BULLISH,
        btc_context_1h=BTCContext1h(btc_rsi_1h=55.0, btc_trend_1h=TrendDirection.BULLISH),
    )


def _sample_decision(decision=Decision.BUY, confidence=0.85) -> DecisionOutput:
    return DecisionOutput(
        decision=decision,
        confidence=confidence,
        entry_reason="Strong bullish trend continuation",
        market_regime="trending_bullish",
        risk_level="low",
        analysis_summary="All indicators aligned, strong uptrend with volume confirmation",
        invalidators=["EMA50 crosses below EMA200", "RSI drops below 30"],
        proposed_sl_pct=-0.025,
        proposed_tp_pct=0.04,
        l1_passed=True,
        l2_confidence=0.82,
        l3_called=True,
    )


class TestTelegramNotifierInit:
    def test_disabled_without_env(self):
        with patch.dict("os.environ", {}, clear=True):
            notifier = TelegramNotifier()
            assert notifier.enabled is False

    def test_enabled_with_env(self):
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            assert notifier.enabled is True

    def test_disabled_partial_env(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test"}, clear=True):
            notifier = TelegramNotifier()
            assert notifier.enabled is False


class TestTelegramSend:
    def test_send_disabled_returns_false(self):
        with patch.dict("os.environ", {}, clear=True):
            notifier = TelegramNotifier()
            assert notifier._send("test") is False

    @patch("httpx.post")
    def test_send_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            result = notifier._send("Hello")
            assert result is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "123456" in str(call_args)

    @patch("httpx.post")
    def test_send_api_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400, text="Bad Request")
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            result = notifier._send("Hello")
            assert result is False

    @patch("httpx.post", side_effect=Exception("Network error"))
    def test_send_exception(self, mock_post):
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            result = notifier._send("Hello")
            assert result is False


class TestNotifyEntryAnalysis:
    @patch("httpx.post")
    def test_entry_executed_message(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            result = notifier.notify_entry_analysis(
                pair="BTC/USDT",
                price=67450.0,
                decision_output=_sample_decision(),
                market_ctx=_sample_market(),
                executed=True,
            )
            assert result is True
            # Check the message contains key elements
            sent_text = mock_post.call_args.kwargs.get("json", mock_post.call_args[1].get("json", {}))
            msg = sent_text.get("text", "")
            assert "BTC/USDT" in msg
            assert "EXECUTED" in msg
            assert "85%" in msg  # confidence

    @patch("httpx.post")
    def test_entry_rejected_message(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            result = notifier.notify_entry_analysis(
                pair="ETH/USDT",
                price=3500.0,
                decision_output=_sample_decision(Decision.HOLD, 0.3),
                risk_flags=["btc_bearish_1h"],
                executed=False,
            )
            assert result is True
            sent_text = mock_post.call_args.kwargs.get("json", mock_post.call_args[1].get("json", {}))
            msg = sent_text.get("text", "")
            assert "REJECTED" in msg
            assert "btc_bearish_1h" in msg

    @patch("httpx.post")
    def test_entry_with_sentiment(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        news = NewsContext(
            window_4h=NewsWindow(headline_count=8, trust_weighted_sentiment=0.25)
        )
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            result = notifier.notify_entry_analysis(
                pair="BTC/USDT",
                price=67450.0,
                decision_output=_sample_decision(),
                market_ctx=_sample_market(),
                news_ctx=news,
                executed=True,
            )
            assert result is True
            sent_text = mock_post.call_args.kwargs.get("json", mock_post.call_args[1].get("json", {}))
            msg = sent_text.get("text", "")
            assert "FinBERT" in msg
            assert "+0.250" in msg


class TestNotifyTradeExit:
    @patch("httpx.post")
    def test_profitable_exit(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            result = notifier.notify_trade_exit(
                pair="BTC/USDT",
                profit_pct=0.025,
                exit_reason="trailing_stop_loss",
                duration_minutes=180,
            )
            assert result is True
            sent_text = mock_post.call_args.kwargs.get("json", mock_post.call_args[1].get("json", {}))
            msg = sent_text.get("text", "")
            assert "+2.50%" in msg
            assert "3h 0m" in msg

    @patch("httpx.post")
    def test_loss_exit(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            result = notifier.notify_trade_exit(
                pair="ETH/USDT",
                profit_pct=-0.015,
                exit_reason="stop_loss",
                duration_minutes=45,
            )
            assert result is True
            sent_text = mock_post.call_args.kwargs.get("json", mock_post.call_args[1].get("json", {}))
            msg = sent_text.get("text", "")
            assert "-1.50%" in msg


class TestNotifyStartup:
    @patch("httpx.post")
    def test_startup_message(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456",
        }):
            notifier = TelegramNotifier()
            result = notifier.notify_startup(mode="dry_run")
            assert result is True
            sent_text = mock_post.call_args.kwargs.get("json", mock_post.call_args[1].get("json", {}))
            msg = sent_text.get("text", "")
            assert "V16" in msg
            assert "GLM" in msg
