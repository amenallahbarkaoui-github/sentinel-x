"""
Sentinel-X — Sentiment Engine

Two backends for headline sentiment:
  1. LLM-based (default) — uses the configured LLM API (lightweight, no model download)
  2. FinBERT local (optional) — ProsusAI/finbert for offline CPU inference

Active only in dry-run / live modes.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

from .contracts import NewsContext, NewsEvent, NewsWindow, NewsWindow24h, RSSEntry

logger = logging.getLogger(__name__)

_LABEL_MAP = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}

# ── FinBERT lazy-load (fallback) ─────────────────────────────────────────
_pipeline = None


def _get_pipeline():
    """Lazy-load the FinBERT pipeline (heavy; only on first call)."""
    global _pipeline
    if _pipeline is None:
        logger.info("Loading FinBERT sentiment model (first call)...")
        from transformers import pipeline as hf_pipeline

        _pipeline = hf_pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            device=-1,
            top_k=None,
        )
        logger.info("FinBERT loaded.")
    return _pipeline


class SentimentEngine:
    """
    Analyse headlines via FinBERT (default, local) or LLM API (fallback).
    """

    def __init__(self, decay_halflife_hours: float = 2.0, backend: str = "finbert"):
        """
        Parameters
        ----------
        backend : str
            "finbert" (default) — uses local ProsusAI/finbert model (fast, free).
            "llm" — uses configured LLM API with thinking disabled.
        """
        self._decay_halflife = decay_halflife_hours
        self._backend = backend
        self._llm_client = None

    def _get_llm_client(self):
        """Lazy-init OpenAI client for LLM sentiment."""
        if self._llm_client is None:
            from openai import OpenAI
            self._llm_client = OpenAI(
                api_key=os.environ.get("LLM_API_KEY", ""),
                base_url=os.environ.get("LLM_BASE_URL", ""),
                timeout=30,
            )
        return self._llm_client

    # ── Single headline ────────────────────────────────────────────────

    def analyze_headline(self, text: str) -> dict:
        """
        Returns
        -------
        dict with keys: sentiment_score (-1..1), confidence (0..1), label (str)
        """
        if self._backend == "llm":
            return self._analyze_llm(text)
        return self._analyze_finbert(text)

    def _analyze_llm(self, text: str) -> dict:
        """Sentiment via LLM API — thinking disabled for speed."""
        try:
            client = self._get_llm_client()
            model = os.environ.get("LLM_MODEL", "glm-5.1")

            response = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Classify this financial headline sentiment. "
                        f"Output ONLY valid JSON, nothing else: "
                        f'{{"label": "positive" or "negative" or "neutral", "confidence": 0.0 to 1.0}}\n\n'
                        f"Headline: {text[:300]}"
                    ),
                }],
                temperature=0.0,
                max_tokens=256,
                extra_body={"thinking": {"type": "disabled"}},
            )

            raw = response.choices[0].message.content or ""
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()

            data = json.loads(raw)
            label = data.get("label", "neutral").lower()
            confidence = float(data.get("confidence", 0.5))

            return {
                "sentiment_score": _LABEL_MAP.get(label, 0.0),
                "confidence": min(max(confidence, 0.0), 1.0),
                "label": label,
            }
        except Exception as exc:
            logger.warning("LLM sentiment failed for '%s': %s", text[:60], exc)
            return {"sentiment_score": 0.0, "confidence": 0.0, "label": "neutral"}

    def _analyze_finbert(self, text: str) -> dict:
        """Sentiment via local FinBERT model."""
        pipe = _get_pipeline()
        results = pipe(text[:512])

        # results is list[list[dict]] when top_k=None
        if isinstance(results[0], list):
            results = results[0]

        # Find the top label
        best = max(results, key=lambda r: r["score"])
        label = best["label"].lower()

        return {
            "sentiment_score": _LABEL_MAP.get(label, 0.0),
            "confidence": best["score"],
            "label": label,
        }

    # ── Enrich RSS entries ─────────────────────────────────────────────

    def enrich_entries(self, entries: list[RSSEntry]) -> list[RSSEntry]:
        """Add sentiment_score and confidence to each entry in-place."""
        for entry in entries:
            try:
                result = self.analyze_headline(entry.title)
                entry.sentiment_score = result["sentiment_score"]
                entry.confidence = result["confidence"]
            except Exception as exc:
                logger.warning("Sentiment failed for '%s': %s", entry.title[:60], exc)
                entry.sentiment_score = 0.0
                entry.confidence = 0.0
        return entries

    # ── Weighted sentiment windows ─────────────────────────────────────

    def _recency_weight(self, published_at: Optional[datetime], now: datetime) -> float:
        """Exponential decay weight based on age."""
        if published_at is None:
            return 0.5  # unknown age → half weight
        age_hours = (now - published_at).total_seconds() / 3600.0
        if age_hours < 0:
            age_hours = 0.0
        # Half-life decay: w = 2^(-age / halflife)
        return math.pow(2.0, -age_hours / self._decay_halflife)

    def compute_news_context(
        self,
        entries: list[RSSEntry],
        now: Optional[datetime] = None,
    ) -> NewsContext:
        """
        Build NewsContext with 4h and 24h windows from enriched entries.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        window_4h: list[RSSEntry] = []
        window_24h: list[RSSEntry] = []

        for e in entries:
            if e.published_at is None:
                window_24h.append(e)
                continue
            age_hours = (now - e.published_at).total_seconds() / 3600.0
            if age_hours <= 4.0:
                window_4h.append(e)
            if age_hours <= 24.0:
                window_24h.append(e)

        def _weighted_avg(subset: list[RSSEntry], use_trust: bool) -> float:
            total_w = 0.0
            weighted_sum = 0.0
            for e in subset:
                w = self._recency_weight(e.published_at, now) * e.confidence
                if use_trust:
                    w *= e.trust_score
                total_w += w
                weighted_sum += w * e.sentiment_score
            return weighted_sum / total_w if total_w > 0 else 0.0

        top_events_4h = [
            NewsEvent(
                title=e.title,
                source=e.source,
                sentiment_score=e.sentiment_score,
                published_at=e.published_at,
            )
            for e in window_4h[:5]
        ]

        return NewsContext(
            window_4h=NewsWindow(
                headline_count=len(window_4h),
                weighted_sentiment=_weighted_avg(window_4h, use_trust=False),
                trust_weighted_sentiment=_weighted_avg(window_4h, use_trust=True),
                top_events=top_events_4h,
            ),
            window_24h=NewsWindow(
                headline_count=len(window_24h),
                weighted_sentiment=_weighted_avg(window_24h, use_trust=False),
                trust_weighted_sentiment=_weighted_avg(window_24h, use_trust=True),
            ),
        )
