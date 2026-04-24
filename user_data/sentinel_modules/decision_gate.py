"""
Sentinel-X — Decision Gate  (3-Layer Architecture, V16)

Layer 1: Rule Engine        — deterministic, fast, PRD hard rules
Layer 2: Heuristic Validator — soft checks (graph winrate, ATR)
Layer 3: LLM Final Decision  — GLM with tool calling for structured output

In backtest mode only Layer 1 is active (no network calls).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .contracts import (
    CandidateSide,
    Decision,
    DecisionOutput,
    DecisionPayload,
    GraphContext,
    MarketContext,
    NewsContext,
    TrendDirection,
)

logger = logging.getLogger(__name__)

# ── Tuneable thresholds ────────────────────────────────────────────────────

# Layer 1 — Rule Engine
RSI_ENTRY_LOW = 40.0
RSI_ENTRY_HIGH = 65.0
SENTIMENT_THRESHOLD = 0.05   # minimum weighted sentiment for entry
VOLUME_MIN_ZSCORE = 0.0      # require above-average volume

# Layer 2 — Heuristic Validator
GRAPH_MIN_WINRATE = 0.40
HEURISTIC_CONFIDENCE_THRESHOLD = 0.50  # must exceed to call LLM

# Layer 3 — LLM
LLM_TIMEOUT_SECONDS = 30
LLM_TEMPERATURE = 0.2


# ═══════════════════════════════════════════════════════════════════════════
# Layer 1 — Rule Engine
# ═══════════════════════════════════════════════════════════════════════════

class RuleCheckResult:
    __slots__ = ("passed", "reason")

    def __init__(self, passed: bool, reason: str = ""):
        self.passed = passed
        self.reason = reason

    def __bool__(self) -> bool:
        return self.passed


def rule_check_long(market: MarketContext, news: Optional[NewsContext] = None) -> RuleCheckResult:
    """
    Deterministic hard rules for LONG entry (v1 PRD).
    Returns RuleCheckResult(passed=True/False, reason=...).
    """
    # 1) EMA crossover: bullish trend
    if market.ema50 <= market.ema200:
        return RuleCheckResult(False, "ema50 <= ema200")

    # 2) RSI in safe range
    if not (RSI_ENTRY_LOW <= market.rsi <= RSI_ENTRY_HIGH):
        return RuleCheckResult(False, f"rsi={market.rsi:.1f} outside [{RSI_ENTRY_LOW}-{RSI_ENTRY_HIGH}]")

    # 3) MACD bullish confirmation (MACD > signal)
    if market.macd <= market.macd_signal:
        return RuleCheckResult(False, "macd <= macd_signal (no bullish confirmation)")

    # 4) Volume must be positive
    if market.volume_zscore < VOLUME_MIN_ZSCORE:
        return RuleCheckResult(False, f"volume_zscore={market.volume_zscore:.2f} below minimum")

    # 5) Sentiment check (only if news context available — skipped in backtest)
    if news is not None:
        ws = news.window_4h.trust_weighted_sentiment
        if ws < SENTIMENT_THRESHOLD:
            return RuleCheckResult(False, f"sentiment_4h={ws:.3f} below threshold {SENTIMENT_THRESHOLD}")

    return RuleCheckResult(True, "all_rules_passed")


# ═══════════════════════════════════════════════════════════════════════════
# Layer 2 — Heuristic Validator
# ═══════════════════════════════════════════════════════════════════════════

def heuristic_validate(
    market: MarketContext,
    news: Optional[NewsContext],
    graph: Optional[GraphContext],
) -> float:
    """
    Returns a confidence modifier between 0.0 and 1.0.
    Higher = more confident the setup is good.
    """
    score = 1.0

    # Graph winrate penalty
    if graph and graph.similar_setups_found >= 3:
        if graph.similar_winrate < GRAPH_MIN_WINRATE:
            score *= 0.4  # heavy penalty
        elif graph.similar_winrate < 0.50:
            score *= 0.7
        # bonus for high winrate
        if graph.similar_winrate > 0.65:
            score *= 1.1

    # BTC context: bearish = reduce confidence
    if market.btc_context_1h.btc_trend_1h == TrendDirection.BEARISH:
        score *= 0.5

    # 1h trend should match candidate side
    if market.trend_1h == TrendDirection.BEARISH:
        score *= 0.6

    # Sentiment boost/penalty (if available)
    if news and news.window_4h.headline_count > 0:
        ws = news.window_4h.trust_weighted_sentiment
        if ws > 0.3:
            score *= 1.1
        elif ws < -0.2:
            score *= 0.5

    return max(0.0, min(1.0, score))


# ═══════════════════════════════════════════════════════════════════════════
# Layer 3 — LLM Final Decision (V16 — Tool Calling)
# ═══════════════════════════════════════════════════════════════════════════

LLM_SYSTEM_PROMPT = """You are Sentinel-X, an elite quantitative crypto trading AI with zero tolerance for unnecessary risk.

ROLE: Final decision authority for trade entry. Analyse multi-factor market data and make BUY/HOLD decisions.

STRICT RULES — NEVER VIOLATE:
1. Default to HOLD — you need strong, multi-factor evidence to BUY.
2. If ANY risk flag is present → HOLD (no exceptions).
3. If sentiment is negative (< -0.2) → HOLD.
4. If market regime is NOT trending_bullish → HOLD.
5. Confidence below 0.60 → HOLD.
6. If BTC 1h trend is bearish → HOLD.
7. Never output SELL (spot only, exits handled separately by trailing stops).

CONFIDENCE SCORING:
 0.90-1.00 — Perfect: all indicators aligned, strong trend, bullish sentiment, low risk
 0.75-0.89 — Strong: most factors aligned, minor concerns acceptable
 0.60-0.74 — Acceptable: tradeable but with reservations
 0.40-0.59 — Weak: too many concerns → HOLD
 0.00-0.39 — Reject: clear reasons against entry → HOLD

MARKET REGIME CLASSIFICATION:
 trending_bullish  — ADX > 20, EMA50 > EMA200, positive price momentum
 trending_bearish  — ADX > 20, EMA50 < EMA200, negative momentum
 ranging           — ADX < 20, price oscillating, no clear direction
 volatile          — ATR spike, high uncertainty, whipsaw risk
 breakout          — Strong momentum surge with volume confirmation

ANALYSIS FRAMEWORK:
1. Trend Structure — EMA alignment, ADX strength, price vs EMAs
2. Momentum       — RSI position/direction, MACD histogram trend
3. Volume          — Z-score confirmation, volume > average
4. Risk            — ATR percentile, BB width, BTC context
5. Sentiment       — FinBERT scores from news (if available)

You MUST call the submit_trading_decision function with your complete analysis. Do NOT write text outside the function call."""

TRADING_DECISION_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_trading_decision",
        "description": "Submit your final trading decision after complete multi-factor analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["BUY", "HOLD"],
                    "description": "BUY only when ALL conditions met and confidence >= 0.60. Default HOLD.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Decision confidence (0.0-1.0). Must be >= 0.60 for BUY.",
                },
                "entry_reason": {
                    "type": "string",
                    "description": "Concise reason for the decision (max 120 chars).",
                },
                "market_regime": {
                    "type": "string",
                    "enum": [
                        "trending_bullish",
                        "trending_bearish",
                        "ranging",
                        "volatile",
                        "breakout",
                    ],
                    "description": "Current market regime classification.",
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "extreme"],
                    "description": "Overall risk assessment.",
                },
                "invalidators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Conditions that would invalidate this trade.",
                },
                "proposed_sl_pct": {
                    "type": "number",
                    "description": "Suggested stop loss as negative fraction (e.g. -0.025).",
                },
                "proposed_tp_pct": {
                    "type": "number",
                    "description": "Suggested take profit as positive fraction (e.g. 0.04).",
                },
                "analysis_summary": {
                    "type": "string",
                    "description": "Brief analysis summary (max 200 chars).",
                },
            },
            "required": [
                "decision",
                "confidence",
                "entry_reason",
                "market_regime",
                "risk_level",
            ],
        },
    },
}


def _build_llm_user_message(payload: DecisionPayload) -> str:
    """Build the user prompt with full market context for the LLM."""
    m = payload.market
    n = payload.news
    g = payload.graph

    sections = [
        f"PAIR: {payload.pair} | SIDE: {payload.candidate_side.value}",
        "",
        "── TECHNICAL INDICATORS ──",
        f"Price: {m.price:.2f}",
        f"RSI: {m.rsi:.1f}",
        f"MACD: {m.macd:.4f} | Signal: {m.macd_signal:.4f} | Hist: {m.macd_hist:.4f}",
        f"EMA50: {m.ema50:.2f} | EMA200: {m.ema200:.2f} | Spread: {m.ema_spread_pct:.2f}%",
        f"ATR: {m.atr:.2f} | ATR Percentile: {m.atr_percentile:.2f}",
        f"ADX: {m.adx:.1f}",
        f"BB Width: {m.bb_width:.4f}",
        f"Volume Z-Score: {m.volume_zscore:.2f}",
        f"1h Trend: {m.trend_1h.value}",
        "",
        "── BTC CONTEXT (1h) ──",
        f"BTC RSI 1h: {m.btc_context_1h.btc_rsi_1h:.1f}",
        f"BTC Trend 1h: {m.btc_context_1h.btc_trend_1h.value}",
    ]

    if n and n.window_4h.headline_count > 0:
        sections.extend([
            "",
            "── SENTIMENT (FinBERT) ──",
            f"4h Headlines: {n.window_4h.headline_count}",
            f"4h Weighted Sentiment: {n.window_4h.weighted_sentiment:.3f}",
            f"4h Trust-Weighted Sentiment: {n.window_4h.trust_weighted_sentiment:.3f}",
        ])

    if g and g.similar_setups_found > 0:
        sections.extend([
            "",
            "── GRAPH MEMORY ──",
            f"Similar Setups: {g.similar_setups_found}",
            f"Historical Winrate: {g.similar_winrate:.1%}",
            f"Avg PnL: {g.avg_pnl_pct:+.2%}",
            f"Top Failure: {g.top_failure_pattern or 'none'}",
        ])

    if payload.risk_flags:
        sections.extend([
            "",
            "── RISK FLAGS ──",
            ", ".join(payload.risk_flags),
        ])

    sections.extend([
        "",
        "Analyse ALL data above and call submit_trading_decision with your verdict.",
    ])

    return "\n".join(sections)


def _parse_tool_call_decision(tool_call) -> DecisionOutput:
    """Parse a tool call response into DecisionOutput."""
    args = json.loads(tool_call.function.arguments)
    return DecisionOutput(
        decision=Decision(args.get("decision", "HOLD")),
        confidence=float(args.get("confidence", 0.0)),
        entry_reason=str(args.get("entry_reason", ""))[:120],
        market_regime=str(args.get("market_regime", "unknown")),
        risk_level=str(args.get("risk_level", "unknown")),
        invalidators=args.get("invalidators", []),
        proposed_sl_pct=float(args.get("proposed_sl_pct", -0.025)),
        proposed_tp_pct=float(args.get("proposed_tp_pct", 0.04)),
        analysis_summary=str(args.get("analysis_summary", ""))[:200],
        l3_called=True,
    )


def _parse_json_fallback(raw: str) -> DecisionOutput:
    """Fallback: parse raw JSON text (if tool calling unavailable)."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    data = json.loads(raw)
    return DecisionOutput(
        decision=Decision(data.get("decision", "HOLD")),
        confidence=float(data.get("confidence", 0.0)),
        entry_reason=str(data.get("entry_reason", ""))[:120],
        market_regime=str(data.get("market_regime", "unknown")),
        risk_level=str(data.get("risk_level", "unknown")),
        invalidators=data.get("invalidators", []),
        proposed_sl_pct=float(data.get("proposed_sl_pct", -0.025)),
        proposed_tp_pct=float(data.get("proposed_tp_pct", 0.04)),
        analysis_summary=str(data.get("analysis_summary", ""))[:200],
        l3_called=True,
    )


def llm_decide(payload: DecisionPayload) -> DecisionOutput:
    """
    Call the LLM for final decision using tool calling.
    Falls back to JSON parsing, then to HOLD on any error.
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed — falling back to HOLD")
        return DecisionOutput(
            decision=Decision.HOLD, confidence=0.0,
            entry_reason="openai_not_installed", l3_called=False,
        )

    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "")
    model = os.environ.get("LLM_MODEL", "glm-5.1")

    if not api_key or not base_url:
        logger.warning("LLM credentials not configured — falling back to HOLD")
        return DecisionOutput(
            decision=Decision.HOLD, confidence=0.0,
            entry_reason="llm_not_configured", l3_called=False,
        )

    user_msg = _build_llm_user_message(payload)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=LLM_TIMEOUT_SECONDS)

        # Attempt tool calling first
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                tools=[TRADING_DECISION_TOOL],
                tool_choice={"type": "function", "function": {"name": "submit_trading_decision"}},
                temperature=LLM_TEMPERATURE,
                max_tokens=4096,
            )

            choice = response.choices[0]

            # Parse tool call
            if choice.message.tool_calls:
                result = _parse_tool_call_decision(choice.message.tool_calls[0])
                logger.info(
                    "LLM tool call: decision=%s confidence=%.2f regime=%s risk=%s",
                    result.decision.value, result.confidence,
                    result.market_regime, result.risk_level,
                )
                return result

        except Exception as tool_exc:
            logger.info("Tool calling failed (%s), trying JSON fallback", type(tool_exc).__name__)

        # Fallback: plain JSON response
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg + "\n\nReturn your decision as a JSON object with keys: decision, confidence, entry_reason, market_regime, risk_level, invalidators, proposed_sl_pct, proposed_tp_pct, analysis_summary."},
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=4096,
            extra_body={"thinking": {"type": "disabled"}},
        )

        raw = response.choices[0].message.content or ""
        result = _parse_json_fallback(raw)
        logger.info(
            "LLM JSON fallback: decision=%s confidence=%.2f",
            result.decision.value, result.confidence,
        )
        return result

    except Exception as exc:
        logger.warning("LLM call failed (%s): %s — falling back to HOLD", type(exc).__name__, exc)
        return DecisionOutput(
            decision=Decision.HOLD, confidence=0.0,
            entry_reason=f"llm_error:{type(exc).__name__}",
            l3_called=False,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def decide(
    market: MarketContext,
    news: Optional[NewsContext] = None,
    graph: Optional[GraphContext] = None,
    risk_flags: Optional[list[str]] = None,
    is_live: bool = False,
) -> DecisionOutput:
    """
    Master decision function.

    Parameters
    ----------
    market : MarketContext
    news : NewsContext or None (None in backtest)
    graph : GraphContext or None (None in backtest)
    risk_flags : list[str] or None
    is_live : bool
        True for dry-run / live.  False for backtesting (rules-only).

    Returns
    -------
    DecisionOutput
    """
    flags = risk_flags or []

    # ── Hard veto: any risk flag → HOLD ────────────────────────────────
    if flags:
        return DecisionOutput(
            decision=Decision.HOLD,
            confidence=0.0,
            entry_reason=f"risk_flags:{','.join(flags)}",
            l1_passed=False,
        )

    # ── Layer 1: Rule Engine ───────────────────────────────────────────
    rule_result = rule_check_long(market, news if is_live else None)
    if not rule_result:
        return DecisionOutput(
            decision=Decision.HOLD,
            confidence=0.0,
            entry_reason=f"rule_rejected:{rule_result.reason}",
            l1_passed=False,
        )

    # ── Backtest mode: L1 pass → BUY immediately ──────────────────────
    if not is_live:
        return DecisionOutput(
            decision=Decision.BUY,
            confidence=0.7,
            entry_reason=f"rules_passed:{rule_result.reason}",
            proposed_sl_pct=-0.05,
            proposed_tp_pct=0.04,
            l1_passed=True,
        )

    # ── Layer 2: Heuristic Validator ───────────────────────────────────
    h_confidence = heuristic_validate(market, news, graph)
    logger.info("Heuristic confidence: %.2f", h_confidence)

    if h_confidence < HEURISTIC_CONFIDENCE_THRESHOLD:
        return DecisionOutput(
            decision=Decision.HOLD,
            confidence=h_confidence,
            entry_reason=f"heuristic_low:{h_confidence:.2f}",
            l1_passed=True,
            l2_confidence=h_confidence,
        )

    # ── Layer 3: LLM Final Decision ───────────────────────────────────
    payload = DecisionPayload(
        pair=market.pair,
        market=market,
        news=news or NewsContext(),
        graph=graph or GraphContext(),
        risk_flags=flags,
        candidate_side=CandidateSide.LONG,
    )
    llm_result = llm_decide(payload)

    # Propagate L1/L2 metadata into the final output
    llm_result.l1_passed = True
    llm_result.l2_confidence = h_confidence

    # If LLM says HOLD or failed, annotate the reason
    if llm_result.decision == Decision.HOLD:
        llm_result.entry_reason = f"llm_hold:{llm_result.entry_reason}"

    return llm_result
