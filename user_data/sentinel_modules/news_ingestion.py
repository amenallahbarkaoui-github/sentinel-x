"""
Sentinel-X — RSS News Ingestion

Polls crypto news RSS feeds, deduplicates, and extracts asset tags.
Active only in dry-run / live modes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser

from .contracts import RSSEntry

logger = logging.getLogger(__name__)

# ── Default RSS sources ────────────────────────────────────────────────────

TIER1_FEEDS: dict[str, str] = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "CoinTelegraph": "https://cointelegraph.com/rss",
}

TIER2_FEEDS: dict[str, str] = {
    "TheBlock": "https://www.theblock.co/rss.xml",
    "Decrypt": "https://decrypt.co/feed",
}

TRUST_SCORES: dict[str, float] = {
    **{k: 1.0 for k in TIER1_FEEDS},
    **{k: 0.7 for k in TIER2_FEEDS},
}

# Common crypto symbols for asset tagging
_ASSET_PATTERN = re.compile(
    r"\b(BTC|ETH|SOL|BNB|XRP|ADA|DOGE|AVAX|DOT|MATIC|LINK|UNI|SHIB|"
    r"Bitcoin|Ethereum|Solana|Binance|Ripple|Cardano|Dogecoin)\b",
    re.IGNORECASE,
)

# Map full names to ticker symbols
_NAME_TO_SYMBOL: dict[str, str] = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binance": "BNB",
    "ripple": "XRP",
    "cardano": "ADA",
    "dogecoin": "DOGE",
}


def _extract_asset_tags(text: str) -> list[str]:
    """Extract unique crypto asset tickers from text."""
    matches = _ASSET_PATTERN.findall(text)
    tags: set[str] = set()
    for m in matches:
        upper = m.upper()
        if upper in _NAME_TO_SYMBOL.values():
            tags.add(upper)
        else:
            mapped = _NAME_TO_SYMBOL.get(m.lower())
            if mapped:
                tags.add(mapped)
    return sorted(tags)


def _content_hash(title: str, published: str) -> str:
    """MD5 of title + published for deduplication."""
    raw = f"{title.strip().lower()}|{published}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def _parse_published(entry: dict) -> Optional[datetime]:
    """Parse feedparser's published_parsed into datetime."""
    pp = entry.get("published_parsed")
    if pp:
        return datetime(*pp[:6], tzinfo=timezone.utc)
    # Fallback: try 'updated_parsed'
    up = entry.get("updated_parsed")
    if up:
        return datetime(*up[:6], tzinfo=timezone.utc)
    return None


class RSSPoller:
    """
    Polls RSS feeds, deduplicates, and returns new entries as RSSEntry objects.

    Parameters
    ----------
    seen_hashes_path : Path or str
        JSON file to persist seen hashes across restarts.
    extra_feeds : dict
        Additional {name: url} feeds to include.
    """

    def __init__(
        self,
        seen_hashes_path: str | Path = "user_data/rss_seen.json",
        extra_feeds: dict[str, str] | None = None,
    ):
        self.feeds: dict[str, str] = {**TIER1_FEEDS, **TIER2_FEEDS}
        if extra_feeds:
            self.feeds.update(extra_feeds)

        self._seen_path = Path(seen_hashes_path)
        self._seen_hashes: set[str] = self._load_seen()
        self._last_poll: float = 0.0

    # ── Persistence ────────────────────────────────────────────────────

    def _load_seen(self) -> set[str]:
        if self._seen_path.exists():
            try:
                data = json.loads(self._seen_path.read_text(encoding="utf-8"))
                return set(data)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Corrupt seen-hashes file, starting fresh.")
        return set()

    def _save_seen(self) -> None:
        self._seen_path.parent.mkdir(parents=True, exist_ok=True)
        # Keep only the last 10 000 hashes to avoid unbounded growth
        trimmed = list(self._seen_hashes)[-10_000:]
        self._seen_path.write_text(
            json.dumps(trimmed, ensure_ascii=False), encoding="utf-8"
        )

    # ── Polling ────────────────────────────────────────────────────────

    def poll(self, max_per_feed: int = 15) -> list[RSSEntry]:
        """
        Fetch all feeds and return **new** entries only.

        Returns
        -------
        list[RSSEntry]
            New entries not seen before, sorted newest-first.
        """
        new_entries: list[RSSEntry] = []

        for source_name, url in self.feeds.items():
            try:
                feed = feedparser.parse(url)
            except Exception as exc:
                logger.warning("RSS fetch failed for %s: %s", source_name, exc)
                continue

            for entry in feed.entries[:max_per_feed]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                published = entry.get("published", "")
                h = _content_hash(title, published)

                if h in self._seen_hashes:
                    continue

                self._seen_hashes.add(h)

                pub_dt = _parse_published(entry)
                tags = _extract_asset_tags(title)

                new_entries.append(
                    RSSEntry(
                        source=source_name,
                        title=title,
                        published_at=pub_dt,
                        asset_tags=tags,
                        trust_score=TRUST_SCORES.get(source_name, 0.5),
                        content_hash=h,
                    )
                )

        self._save_seen()
        self._last_poll = time.time()

        # Sort newest first
        new_entries.sort(
            key=lambda e: e.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return new_entries
