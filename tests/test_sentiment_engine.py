"""Tests for Sentinel-X Sentiment Engine (mocked — no model download in CI)."""

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from sentinel_modules.contracts import RSSEntry
from sentinel_modules.sentiment_engine import SentimentEngine


@pytest.fixture
def engine():
    return SentimentEngine(decay_halflife_hours=2.0)


@pytest.fixture
def mock_pipeline():
    """Mock the HuggingFace pipeline to avoid downloading the model."""
    mock_pipe = MagicMock()
    # Simulate finbert output: list[list[dict]] when top_k=None
    mock_pipe.return_value = [[
        {"label": "positive", "score": 0.85},
        {"label": "neutral", "score": 0.10},
        {"label": "negative", "score": 0.05},
    ]]
    return mock_pipe


class TestAnalyzeHeadline:
    def test_positive_sentiment(self, engine, mock_pipeline):
        with patch("sentinel_modules.sentiment_engine._pipeline", mock_pipeline):
            with patch("sentinel_modules.sentiment_engine._get_pipeline", return_value=mock_pipeline):
                result = engine.analyze_headline("Bitcoin surges to new all-time high")
                assert result["sentiment_score"] == 1.0
                assert result["confidence"] == 0.85
                assert result["label"] == "positive"

    def test_negative_sentiment(self, engine):
        mock_pipe = MagicMock()
        mock_pipe.return_value = [[
            {"label": "negative", "score": 0.90},
            {"label": "neutral", "score": 0.07},
            {"label": "positive", "score": 0.03},
        ]]
        with patch("sentinel_modules.sentiment_engine._get_pipeline", return_value=mock_pipe):
            result = engine.analyze_headline("Crypto market crashes")
            assert result["sentiment_score"] == -1.0
            assert result["confidence"] == 0.90


class TestRecencyWeight:
    def test_current_time_weight_1(self, engine):
        now = datetime.now(timezone.utc)
        w = engine._recency_weight(now, now)
        assert abs(w - 1.0) < 0.01

    def test_halflife_weight(self, engine):
        now = datetime.now(timezone.utc)
        published = now - timedelta(hours=2.0)  # exactly one halflife
        w = engine._recency_weight(published, now)
        assert abs(w - 0.5) < 0.01

    def test_none_published(self, engine):
        now = datetime.now(timezone.utc)
        w = engine._recency_weight(None, now)
        assert w == 0.5


class TestComputeNewsContext:
    def test_empty_entries(self, engine):
        ctx = engine.compute_news_context([])
        assert ctx.window_4h.headline_count == 0
        assert ctx.window_4h.weighted_sentiment == 0.0

    def test_windowing(self, engine):
        now = datetime.now(timezone.utc)
        entries = [
            RSSEntry(
                source="CoinDesk", title="A",
                published_at=now - timedelta(hours=1),
                sentiment_score=1.0, confidence=0.9, trust_score=1.0,
            ),
            RSSEntry(
                source="TheBlock", title="B",
                published_at=now - timedelta(hours=10),
                sentiment_score=-0.5, confidence=0.8, trust_score=0.7,
            ),
        ]
        ctx = engine.compute_news_context(entries, now=now)
        # Entry A is in both windows, entry B is only in 24h
        assert ctx.window_4h.headline_count == 1
        assert ctx.window_24h.headline_count == 2
        assert ctx.window_4h.weighted_sentiment > 0  # positive from entry A
