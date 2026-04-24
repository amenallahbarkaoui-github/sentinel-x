"""Tests for Sentinel-X RSS News Ingestion."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sentinel_modules.news_ingestion import (
    RSSPoller,
    _content_hash,
    _extract_asset_tags,
)


class TestAssetTagExtraction:
    def test_ticker_symbols(self):
        tags = _extract_asset_tags("BTC and ETH prices surge today")
        assert "BTC" in tags
        assert "ETH" in tags

    def test_full_names(self):
        tags = _extract_asset_tags("Bitcoin reaches new highs, Ethereum follows")
        assert "BTC" in tags
        assert "ETH" in tags

    def test_no_match(self):
        tags = _extract_asset_tags("Stock market falls on trade fears")
        assert tags == []

    def test_dedup(self):
        tags = _extract_asset_tags("BTC BTC Bitcoin bitcoin")
        assert tags == ["BTC"]


class TestContentHash:
    def test_deterministic(self):
        h1 = _content_hash("Title", "2026-01-01")
        h2 = _content_hash("Title", "2026-01-01")
        assert h1 == h2

    def test_different_input(self):
        h1 = _content_hash("Title A", "2026-01-01")
        h2 = _content_hash("Title B", "2026-01-01")
        assert h1 != h2

    def test_case_insensitive_title(self):
        h1 = _content_hash("Bitcoin Surges", "")
        h2 = _content_hash("bitcoin surges", "")
        assert h1 == h2


class TestRSSPoller:
    def test_dedup_prevents_duplicates(self, tmp_path):
        """Same entry polled twice should appear only once."""
        mock_entry = MagicMock()
        mock_entry.get = lambda k, d="": {
            "title": "BTC hits 100k",
            "published": "Wed, 01 Jan 2026 00:00:00 GMT",
            "published_parsed": time.strptime("2026-01-01", "%Y-%m-%d"),
            "link": "https://example.com/1",
        }.get(k, d)
        mock_entry.title = "BTC hits 100k"

        mock_feed = MagicMock()
        mock_feed.entries = [mock_entry]
        mock_feed.feed.get = lambda k, d="": "TestSource"

        seen_path = tmp_path / "seen.json"
        poller = RSSPoller(seen_hashes_path=seen_path)
        poller.feeds = {"TestSource": "https://fake.url/rss"}

        with patch("sentinel_modules.news_ingestion.feedparser.parse", return_value=mock_feed):
            first = poller.poll()
            second = poller.poll()

        assert len(first) == 1
        assert len(second) == 0  # dedup

    def test_seen_hashes_persisted(self, tmp_path):
        seen_path = tmp_path / "seen.json"
        poller = RSSPoller(seen_hashes_path=seen_path)
        poller._seen_hashes = {"abc123", "def456"}
        poller._save_seen()

        assert seen_path.exists()
        data = json.loads(seen_path.read_text())
        assert set(data) == {"abc123", "def456"}

    def test_load_corrupt_seen_file(self, tmp_path):
        seen_path = tmp_path / "seen.json"
        seen_path.write_text("not valid json!!!")
        poller = RSSPoller(seen_hashes_path=seen_path)
        assert poller._seen_hashes == set()
