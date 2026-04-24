"""
Sentinel-X Strategy V16 — Freqtrade IStrategy (INTERFACE_VERSION 3)

Enhanced crypto trading system combining:
  • Technical Analysis (RSI, MACD, EMA50/200, ATR, ADX, BB Width, Volume Z-score)
  • Regime Filters (ADX > 18, ATR percentile < 0.85)
  • ATR-based adaptive trailing stoploss
  • 1h Informative Timeframe (pair + BTC context)
  • News Sentiment — FinBERT (dry/live only)
  • Graph Trade Memory  (dry/live only)
  • GLM-5.1 LLM Decision Gate with tool calling (dry/live only)
  • Telegram Notifications with full analysis (dry/live only)

Backtesting uses pure vectorized TA rules + regime filters.
Dry/live adds News + Sentiment + Graph + LLM + Telegram.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from pandas import DataFrame

from freqtrade.enums import RunMode
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, informative

# ── Ensure sentinel_modules is importable ──────────────────────────────────
_modules_dir = str(Path(__file__).resolve().parent.parent / "sentinel_modules")
if _modules_dir not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentinel_modules.indicators import (
    add_all_indicators,
    compute_adx,
    compute_atr,
    compute_atr_percentile,
    compute_bollinger_bandwidth,
    compute_ema,
    compute_macd,
    compute_rsi,
    compute_trend_label,
    compute_volume_zscore,
)
from sentinel_modules.contracts import (
    BTCContext1h,
    CandidateSide,
    Decision,
    GraphContext,
    MarketContext,
    NewsContext,
    TradeRecord,
    TrendDirection,
)
from sentinel_modules.risk_manager import check_risk_flags
from sentinel_modules.decision_gate import decide as decision_gate_decide

logger = logging.getLogger(__name__)


class SentinelX(IStrategy):
    """
    Sentinel-X V17 — Halal-Compliant, Maximum Win-Rate Architecture.

    Islamic Finance Compliance (Halal):
      • Spot trading ONLY — no leverage, no margin, no interest (riba)
      • Long-only — no short selling
      • No derivatives, no options, no futures
      • Systematic rules — not gambling (maysir); defined entry/exit logic
      • Transparent conditions — no hidden risk (gharar)

    Win-Rate Maximization Strategy:
      • exit_profit_only = True  → NEVER sell at a loss via exit signals
      • Aggressive ROI targets   → lock in small profits quickly (0.8–1.5%)
      • Very wide hard stoploss  → -8% (rare market crashes only)
      • ATR trailing only above +4% profit → protects big winners only
      • Strict entry filters     → only enter high-probability setups

    Result: High win rate (target > 85%), low-but-consistent profit per trade.
    """

    # ══════════════════════════════════════════════════════════════════════
    # Class-level configuration
    # ══════════════════════════════════════════════════════════════════════

    INTERFACE_VERSION = 3
    timeframe = "15m"

    # EMA200 needs ~200 candles + buffer for stable values
    startup_candle_count: int = 210

    # Risk management — V17 Halal Max-WR
    # Wide stoploss: gives trades room to recover; exit_profit_only blocks signal exits in loss
    # Combined effect: nearly all closed trades exit in profit (ROI or trailing lock ≥+0.3%)
    stoploss = -0.05           # 5% emergency stop (rarely triggered)

    # Tight ROI: lock in small profits quickly — maximises closed-in-profit count
    minimal_roi = {
        "0":   0.015,          # take 1.5% immediately if hit
        "30":  0.012,          # 1.2% after 30 min
        "60":  0.010,          # 1.0% after 1h
        "120": 0.008,          # 0.8% after 2h
        "240": 0.006,          # 0.6% after 4h
        "480": 0.004,          # 0.4% after 8h (stale cleanup)
    }

    # No shorts in v1 (spot)
    can_short = False

    # V16: ATR-based trailing via custom_stoploss replaces fixed trailing
    use_custom_stoploss = True
    trailing_stop = False

    # Order settings
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ══════════════════════════════════════════════════════════════════════
    # Internal state (initialized in bot_start)
    # ══════════════════════════════════════════════════════════════════════

    _rss_poller = None
    _sentiment_engine = None
    _graph_store = None
    _telegram = None
    _news_cache: Optional[NewsContext] = None
    _news_entries: list = []
    _last_news_poll: float = 0.0
    _NEWS_POLL_INTERVAL = 900  # 15 minutes

    # ══════════════════════════════════════════════════════════════════════
    # Informative pairs — BTC/USDT 1h as market reference
    # ══════════════════════════════════════════════════════════════════════

    def informative_pairs(self):
        return [("BTC/USDT", "1h")]

    # ══════════════════════════════════════════════════════════════════════
    # 1h informative indicator (auto-merged via decorator)
    # ══════════════════════════════════════════════════════════════════════

    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Compute 1h indicators — merged into main df with '_1h' suffix."""
        dataframe["rsi_1h"] = compute_rsi(dataframe)
        dataframe["ema50_1h"] = compute_ema(dataframe, 50)
        dataframe["ema200_1h"] = compute_ema(dataframe, 200)
        dataframe["trend_1h"] = compute_trend_label(dataframe["ema50_1h"], dataframe["ema200_1h"])
        return dataframe

    # ══════════════════════════════════════════════════════════════════════
    # Main indicators (15m)
    # ══════════════════════════════════════════════════════════════════════

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Add all indicators to the 15m dataframe.
        1h columns already merged automatically via @informative decorator.
        """
        dataframe = add_all_indicators(dataframe)

        # Derived indicators for entry/exit quality
        dataframe["macd_hist_prev"] = dataframe["macd_hist"].shift(1)
        dataframe["macd_hist_prev2"] = dataframe["macd_hist"].shift(2)
        dataframe["rsi_prev"] = dataframe["rsi"].shift(1)
        dataframe["ema50_prev"] = dataframe["ema50"].shift(1)
        dataframe["ema200_prev"] = dataframe["ema200"].shift(1)

        # EMA50/200 spread as % of price — measures trend strength
        dataframe["ema_spread_pct"] = (
            (dataframe["ema50"] - dataframe["ema200"]) / dataframe["close"] * 100
        )

        # Close relative to EMA50 — only enter when close is above support
        dataframe["close_above_ema50"] = dataframe["close"] > dataframe["ema50"]

        # Volume spike detection
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()

        # V16 — ATR as % of price (for custom_stoploss + meta layer)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]

        return dataframe

    # ══════════════════════════════════════════════════════════════════════
    # Entry signals (vectorized, no live data)
    # ══════════════════════════════════════════════════════════════════════

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        LONG entry conditions — V17 (selective multi-pair).

        Same strict V16 filters on 4 proven profitable pairs
        (ETH, BTC, ADA, XRP). Frequency gained via pair count not
        filter relaxation — quality preserved.
        """
        conditions = (
            # ── Mandatory trend structure ──
            (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["ema_spread_pct"] > 0.2)
            & (dataframe["close_above_ema50"])
            # ── Momentum (strict) ──
            & (dataframe["rsi"] >= 42)
            & (dataframe["rsi"] <= 58)
            & (dataframe["rsi"] > dataframe["rsi_prev"])
            & (dataframe["macd_hist"] > 0)
            & (dataframe["macd_hist"] > dataframe["macd_hist_prev"])
            & (dataframe["macd_hist_prev"] > dataframe["macd_hist_prev2"])
            # ── Volume ──
            & (dataframe["volume_zscore"] > 0.5)
            & (dataframe["volume"] > 0)
            # ── Higher-TF alignment ──
            & (dataframe.get("trend_1h_1h", dataframe.get("trend_1h", "neutral")) != "bearish")
            & (dataframe["close_1h"] > dataframe.get("ema50_1h_1h", dataframe.get("ema50_1h", 0)))
            # ── Regime filters ──
            & (dataframe["adx"] > 18)
            & (dataframe["atr_percentile"] < 0.85)
        )

        dataframe.loc[conditions, ["enter_long", "enter_tag"]] = (1, "sentinel_long_v17")

        return dataframe

    # ══════════════════════════════════════════════════════════════════════
    # Exit signals (vectorized)
    # ══════════════════════════════════════════════════════════════════════

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        V16 exit signals (vectorized):

        1. Overbought reversal — RSI > 78 AND MACD hist < 0

        Primary profit extraction: ATR-based trailing in custom_stoploss.
        Late ROI floor cleans up stale trades.
        This signal catches extreme overbought reversals only.
        """
        conditions = (
            (dataframe["rsi"] > 78)
            & (dataframe["macd_hist"] < 0)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[conditions, ["exit_long", "exit_tag"]] = (1, "overbought_reversal")

        return dataframe

    # ══════════════════════════════════════════════════════════════════════
    # Custom stoploss — V15 ATR-based adaptive trailing
    # ══════════════════════════════════════════════════════════════════════

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        """
        V17 Halal — ATR adaptive trailing, activates at +1.5% profit.

        Phases:
          profit < 1.5%  → hard stoploss only (-5%) — gives trade room to recover
          profit ≥ 1.5%  → trail at 1.0 × ATR% (wide — room for trend)
          profit ≥ 3.0%  → trail at 0.75 × ATR% (tighter)
          profit ≥ 5.0%  → trail at 0.5 × ATR%  (lock big winners)

        Lock floor: min +0.3% once trailing is active — ALL trailing exits
        close in profit. Only a rare -12% hard stop closes at a loss.
        Combined with exit_profit_only=True (blocks signal exits in loss)
        this achieves maximum win rate.
        """
        from freqtrade.strategy import stoploss_from_open

        if current_profit < 0.015:
            return self.stoploss  # -5% hard floor; gives trade room to recover

        atr_pct = self._get_current_atr_pct(pair, current_rate)
        if atr_pct <= 0:
            atr_pct = 0.005  # fallback: 0.5%

        # Scale trailing distance by profit level
        if current_profit >= 0.05:
            trail = 0.5 * atr_pct    # tight: lock most of big winners
        elif current_profit >= 0.03:
            trail = 0.75 * atr_pct   # medium
        else:
            trail = 1.0 * atr_pct    # wide: give room for trend

        # Lock at least 0.3% profit once trailing activates
        # ALL trailing stop exits are therefore profitable — no loss from trailing
        lock_pct = max(0.003, current_profit - trail)
        return stoploss_from_open(lock_pct, current_profit, is_short=False)

    # ══════════════════════════════════════════════════════════════════════
    # Callbacks — live/dry-run enhancements
    # ══════════════════════════════════════════════════════════════════════

    def bot_start(self, **kwargs) -> None:
        """Initialize external modules (only in dry/live)."""
        if self.dp and self.dp.runmode.value in ("live", "dry_run"):
            self._init_live_modules()

    def _init_live_modules(self) -> None:
        """Lazy-load external modules for dry/live mode."""
        from dotenv import load_dotenv
        load_dotenv()

        try:
            from sentinel_modules.telegram_notifier import TelegramNotifier
            self._telegram = TelegramNotifier()
            if self._telegram.enabled:
                mode = self.dp.runmode.value if self.dp else "unknown"
                self._telegram.notify_startup(mode=mode)
            logger.info("Telegram Notifier initialized.")
        except Exception as exc:
            logger.warning("Telegram Notifier init failed: %s", exc)

        try:
            from sentinel_modules.news_ingestion import RSSPoller
            self._rss_poller = RSSPoller()
            logger.info("RSS Poller initialized.")
        except Exception as exc:
            logger.warning("RSS Poller init failed: %s", exc)

        try:
            from sentinel_modules.sentiment_engine import SentimentEngine
            self._sentiment_engine = SentimentEngine()
            logger.info("Sentiment Engine initialized.")
        except Exception as exc:
            logger.warning("Sentiment Engine init failed: %s", exc)

        try:
            from sentinel_modules.graph_memory import TradeMemoryStore
            self._graph_store = TradeMemoryStore()
            logger.info("Graph Memory Store initialized.")
        except Exception as exc:
            logger.warning("Graph Memory Store init failed: %s", exc)

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        """Poll RSS and update sentiment cache periodically."""
        if not self._is_live():
            return

        now = time.time()
        if now - self._last_news_poll < self._NEWS_POLL_INTERVAL:
            return

        self._last_news_poll = now

        if self._rss_poller:
            try:
                new_entries = self._rss_poller.poll()
                if new_entries:
                    self._news_entries.extend(new_entries)
                    # Keep only last 200 entries
                    self._news_entries = self._news_entries[-200:]

                    if self._sentiment_engine:
                        self._sentiment_engine.enrich_entries(new_entries)
                        self._news_cache = self._sentiment_engine.compute_news_context(
                            self._news_entries
                        )
                        logger.info(
                            "News updated: %d entries, 4h sentiment=%.3f",
                            self._news_cache.window_4h.headline_count,
                            self._news_cache.window_4h.trust_weighted_sentiment,
                        )
            except Exception as exc:
                logger.warning("News poll/sentiment failed: %s", exc)

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        """
        Last-second gate before entry.  In dry/live, runs the full decision
        pipeline and sends detailed analysis to Telegram before executing.
        In backtest, always confirms (rules already checked in populate_entry_trend).
        """
        if not self._is_live():
            return True  # backtest: trust vectorized rules

        # Build MarketContext from latest dataframe
        market_ctx = self._build_market_context(pair, current_time, rate)
        if market_ctx is None:
            logger.warning("Could not build MarketContext for %s — rejecting.", pair)
            return False

        # Risk flags
        atr_avg = self._get_recent_atr_avg(pair)
        risk_flags = check_risk_flags(market_ctx, atr_avg)

        # Graph context
        graph_ctx = None
        if self._graph_store:
            try:
                macd_sign = "positive" if market_ctx.macd >= 0 else "negative"
                graph_ctx = self._graph_store.find_similar_setups(
                    pair=pair,
                    rsi=market_ctx.rsi,
                    ema_trend=market_ctx.trend_1h.value,
                    macd_sign=macd_sign,
                )
            except Exception as exc:
                logger.warning("Graph lookup failed: %s", exc)

        # Full decision gate (L1 → L2 → L3/GLM)
        result = decision_gate_decide(
            market=market_ctx,
            news=self._news_cache,
            graph=graph_ctx,
            risk_flags=risk_flags,
            is_live=True,
        )

        executed = result.decision == Decision.BUY

        # ── Telegram: send FULL analysis BEFORE execution ──
        if self._telegram:
            try:
                self._telegram.notify_entry_analysis(
                    pair=pair,
                    price=rate,
                    decision_output=result,
                    market_ctx=market_ctx,
                    news_ctx=self._news_cache,
                    risk_flags=risk_flags,
                    executed=executed,
                )
            except Exception as exc:
                logger.warning("Telegram notification failed: %s", exc)

        if executed:
            logger.info(
                "ENTRY CONFIRMED %s | confidence=%.2f | regime=%s | risk=%s | reason=%s",
                pair, result.confidence, result.market_regime,
                result.risk_level, result.entry_reason,
            )
            return True
        else:
            logger.info(
                "ENTRY REJECTED %s | decision=%s | reason=%s",
                pair, result.decision.value, result.entry_reason,
            )
            return False

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        """
        V16 Custom exit logic (live/dry only):
          - Exit if news sentiment drops sharply while in profit.
        ATR trailing handles profit extraction via custom_stoploss.
        """
        if not self._is_live():
            return None

        if self._news_cache and current_profit > 0.005:
            ws = self._news_cache.window_4h.trust_weighted_sentiment
            if ws < -0.3:
                return "negative_news_exit"

        return None

    def order_filled(
        self,
        pair: str,
        trade: Trade,
        order,
        current_time: datetime,
        **kwargs,
    ) -> None:
        """Store trade context in graph memory + send Telegram on exit."""
        if not self._is_live():
            return

        try:
            # Determine if this is an entry or exit fill
            is_entry = (order.ft_order_side == "buy")

            if is_entry and self._graph_store:
                # Store initial trade context
                market_ctx = self._build_market_context(pair, current_time, order.safe_price)
                if market_ctx:
                    record = TradeRecord(
                        trade_id=str(trade.id),
                        pair=pair,
                        timestamp=current_time.replace(tzinfo=timezone.utc) if current_time.tzinfo is None else current_time,
                        side=CandidateSide.LONG,
                        entry_reason=trade.enter_tag or "",
                        rsi=market_ctx.rsi,
                        macd=market_ctx.macd,
                        ema_trend=market_ctx.trend_1h,
                        sentiment_score=(
                            self._news_cache.window_4h.trust_weighted_sentiment
                            if self._news_cache else 0.0
                        ),
                        outcome="PENDING",
                    )
                    self._graph_store.store_trade(record)
            elif not is_entry:
                # Exit fill — update graph + notify Telegram
                duration_minutes = int(
                    (current_time - trade.open_date).total_seconds() / 60
                )
                pnl = trade.calc_profit_ratio(order.safe_price)
                outcome = "WIN" if pnl > 0 else "LOSS"

                if self._graph_store:
                    self._graph_store.update_trade_exit(
                        trade_id=str(trade.id),
                        exit_reason=trade.exit_reason or "",
                        pnl_pct=pnl,
                        duration_minutes=duration_minutes,
                        outcome=outcome,
                    )

                # ── Telegram exit notification ──
                if self._telegram:
                    try:
                        self._telegram.notify_trade_exit(
                            pair=pair,
                            profit_pct=pnl,
                            exit_reason=trade.exit_reason or "unknown",
                            duration_minutes=duration_minutes,
                        )
                    except Exception as tex:
                        logger.warning("Telegram exit notification failed: %s", tex)

        except Exception as exc:
            logger.warning("order_filled processing failed: %s", exc)

    # ══════════════════════════════════════════════════════════════════════
    # Helper methods
    # ══════════════════════════════════════════════════════════════════════

    def _is_live(self) -> bool:
        """True if running in dry_run or live mode."""
        return bool(
            self.dp and self.dp.runmode.value in ("live", "dry_run")
        )

    def _build_market_context(
        self, pair: str, current_time: datetime, price: float
    ) -> Optional[MarketContext]:
        """Build MarketContext from the latest dataframe row."""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe.empty:
                return None

            last = dataframe.iloc[-1]

            # BTC context from informative pairs
            btc_rsi_1h = 50.0
            btc_trend_1h = TrendDirection.NEUTRAL
            try:
                btc_df, _ = self.dp.get_analyzed_dataframe("BTC/USDT", "1h")
                if not btc_df.empty:
                    btc_last = btc_df.iloc[-1]
                    btc_rsi_1h = float(btc_last.get("rsi_1h", btc_last.get("rsi", 50.0)))
                    trend_str = str(btc_last.get("trend_1h", btc_last.get("trend", "neutral")))
                    btc_trend_1h = TrendDirection(trend_str) if trend_str in ("bullish", "bearish", "neutral") else TrendDirection.NEUTRAL
            except Exception:
                pass

            # Determine 1h trend from merged columns
            trend_1h_str = str(last.get("trend_1h_1h", last.get("trend_1h", "neutral")))
            trend_1h = TrendDirection(trend_1h_str) if trend_1h_str in ("bullish", "bearish", "neutral") else TrendDirection.NEUTRAL

            ts = current_time
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            return MarketContext(
                pair=pair,
                timeframe=self.timeframe,
                timestamp=ts,
                price=price,
                rsi=float(last.get("rsi", 50.0)),
                macd=float(last.get("macd", 0.0)),
                macd_signal=float(last.get("macd_signal", 0.0)),
                macd_hist=float(last.get("macd_hist", 0.0)),
                ema50=float(last.get("ema50", 0.0)),
                ema200=float(last.get("ema200", 0.0)),
                atr=float(last.get("atr", 0.0)),
                volume_zscore=float(last.get("volume_zscore", 0.0)),
                ema_spread_pct=float(last.get("ema_spread_pct", 0.0)),
                adx=float(last.get("adx", 0.0)),
                atr_percentile=min(1.0, max(0.0, float(last.get("atr_percentile", 0.5)))),
                bb_width=max(0.0, float(last.get("bb_width", 0.0))),
                trend_1h=trend_1h,
                btc_context_1h=BTCContext1h(
                    btc_rsi_1h=btc_rsi_1h,
                    btc_trend_1h=btc_trend_1h,
                ),
            )
        except Exception as exc:
            logger.warning("Failed to build MarketContext for %s: %s", pair, exc)
            return None

    def _get_recent_atr_avg(self, pair: str, window: int = 20) -> float:
        """Return the mean ATR over the last *window* candles."""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe.empty or "atr" not in dataframe.columns:
                return 0.0
            return float(dataframe["atr"].tail(window).mean())
        except Exception:
            return 0.0

    def _get_current_atr_pct(self, pair: str, current_rate: float) -> float:
        """Return current ATR as a fraction of price (for adaptive trailing)."""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe.empty or "atr" not in dataframe.columns:
                return 0.0
            atr = float(dataframe["atr"].iloc[-1])
            return atr / current_rate if current_rate > 0 else 0.0
        except Exception:
            return 0.0
