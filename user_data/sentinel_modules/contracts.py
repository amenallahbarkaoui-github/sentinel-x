"""
Sentinel-X Data Contracts

Pydantic models matching the PRD JSON specifications.
Used across all modules for type safety and validation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────

class TrendDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class CandidateSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class Decision(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


# ── Market Context ─────────────────────────────────────────────────────────

class BTCContext1h(BaseModel):
    btc_rsi_1h: float = Field(0.0, ge=0, le=100)
    btc_trend_1h: TrendDirection = TrendDirection.NEUTRAL


class MarketContext(BaseModel):
    pair: str
    timeframe: str = "15m"
    timestamp: datetime
    price: float = Field(0.0, ge=0)
    rsi: float = Field(0.0, ge=0, le=100)
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    ema50: float = Field(0.0, ge=0)
    ema200: float = Field(0.0, ge=0)
    atr: float = Field(0.0, ge=0)
    volume_zscore: float = 0.0
    ema_spread_pct: float = 0.0
    adx: float = Field(0.0, ge=0)
    atr_percentile: float = Field(0.5, ge=0.0, le=1.0)
    bb_width: float = Field(0.0, ge=0)
    trend_1h: TrendDirection = TrendDirection.NEUTRAL
    btc_context_1h: BTCContext1h = Field(default_factory=BTCContext1h)


# ── News Context ───────────────────────────────────────────────────────────

class NewsEvent(BaseModel):
    title: str
    source: str
    sentiment_score: float = Field(0.0, ge=-1.0, le=1.0)
    published_at: Optional[datetime] = None


class NewsWindow(BaseModel):
    headline_count: int = Field(0, ge=0)
    weighted_sentiment: float = 0.0
    trust_weighted_sentiment: float = 0.0
    top_events: list[NewsEvent] = Field(default_factory=list)


class NewsContext(BaseModel):
    window_4h: NewsWindow = Field(default_factory=NewsWindow)
    window_24h: NewsWindow = Field(default_factory=NewsWindow)


class NewsWindow24h(BaseModel):
    """Simplified 24h window per PRD (no trust_weighted_sentiment)."""
    headline_count: int = Field(0, ge=0)
    weighted_sentiment: float = 0.0


class NewsContextStrict(BaseModel):
    """Strict version matching PRD exactly."""
    window_4h: NewsWindow = Field(default_factory=NewsWindow)
    window_24h: NewsWindow24h = Field(default_factory=NewsWindow24h)


# ── Graph Context ──────────────────────────────────────────────────────────

class GraphContext(BaseModel):
    similar_setups_found: int = Field(0, ge=0)
    similar_winrate: float = Field(0.0, ge=0.0, le=1.0)
    avg_pnl_pct: float = 0.0
    median_duration_min: int = Field(0, ge=0)
    top_failure_pattern: str = ""


# ── Decision Payload & Output ──────────────────────────────────────────────

class DecisionPayload(BaseModel):
    pair: str
    market: MarketContext
    news: NewsContext = Field(default_factory=NewsContext)
    graph: GraphContext = Field(default_factory=GraphContext)
    risk_flags: list[str] = Field(default_factory=list)
    candidate_side: CandidateSide = CandidateSide.NONE


class DecisionOutput(BaseModel):
    decision: Decision = Decision.HOLD
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    entry_reason: str = ""
    invalidators: list[str] = Field(default_factory=list)
    proposed_sl_pct: float = Field(0.0, le=0.0)  # negative or zero
    proposed_tp_pct: float = Field(0.0, ge=0.0)
    # V16 — enhanced decision metadata
    market_regime: str = "unknown"
    risk_level: str = "unknown"
    analysis_summary: str = ""
    l1_passed: bool = False
    l2_confidence: float = 0.0
    l3_called: bool = False


# ── News Entry (raw from RSS) ─────────────────────────────────────────────

class RSSEntry(BaseModel):
    source: str
    title: str
    published_at: Optional[datetime] = None
    asset_tags: list[str] = Field(default_factory=list)
    sentiment_score: float = Field(0.0, ge=-1.0, le=1.0)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    trust_score: float = Field(1.0, ge=0.0, le=1.0)
    content_hash: str = ""


# ── Trade Record (for Graph Memory) ───────────────────────────────────────

class TradeRecord(BaseModel):
    trade_id: Optional[str] = None
    pair: str
    timestamp: datetime
    side: CandidateSide
    entry_reason: str = ""
    exit_reason: str = ""
    rsi: float = 0.0
    macd: float = 0.0
    ema_trend: TrendDirection = TrendDirection.NEUTRAL
    sentiment_score: float = 0.0
    pnl_pct: float = 0.0
    duration_minutes: int = 0
    outcome: str = ""  # "WIN" | "LOSS" | "PENDING"
    market_state: str = ""
