"""
Sentinel-X — Telegram Notifier

Sends rich trade analysis and execution notifications to Telegram.
Active in dry-run and live modes only.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends structured trading notifications via the Telegram Bot API."""

    def __init__(self) -> None:
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self._enabled = bool(self.token and self.chat_id)
        if self._enabled:
            logger.info("Telegram Notifier enabled (chat_id=%s)", self.chat_id)
        else:
            logger.warning(
                "Telegram Notifier disabled — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Low-level send ─────────────────────────────────────────────────

    def _send(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message via Telegram Bot API.  Returns True on success."""
        if not self._enabled:
            return False
        try:
            import httpx

            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            resp = httpx.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("Telegram API %d: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)
            return False

    # ── Notification types ─────────────────────────────────────────────

    def notify_startup(self, mode: str = "dry_run") -> bool:
        """Notify that Sentinel-X has started."""
        msg = (
            "\U0001f916 <b>Sentinel-X V16 Started</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Mode: {mode}\n"
            "Strategy: SentinelX V16\n"
            "Pairs: BTC/USDT, ETH/USDT\n"
            "AI: GLM-5.1 (tool calling)\n"
            "Sentiment: FinBERT\n\n"
            "\u2705 All trade decisions will be sent here with full analysis."
        )
        return self._send(msg)

    def notify_entry_analysis(
        self,
        pair: str,
        price: float,
        decision_output,  # DecisionOutput
        market_ctx=None,   # MarketContext
        news_ctx=None,     # NewsContext
        risk_flags: Optional[list[str]] = None,
        executed: bool = False,
    ) -> bool:
        """Send a detailed trade analysis notification BEFORE execution."""
        d = decision_output
        flags = risk_flags or []

        # Header
        if executed:
            header = "\u2705 <b>TRADE EXECUTED \u2014 {}</b>".format(pair)
        else:
            header = "\u274c <b>TRADE REJECTED \u2014 {}</b>".format(pair)

        lines = [
            header,
            "\u2501" * 20,
            "",
        ]

        # Market analysis
        if market_ctx:
            m = market_ctx
            rsi_arrow = "\u2191" if m.rsi > 50 else "\u2193"
            ema_ok = "\u2705" if m.ema50 > m.ema200 else "\u274c"
            macd_ok = "\u2705" if m.macd_hist > 0 else "\u274c"

            lines.extend([
                "\U0001f4ca <b>Market Analysis</b>",
                f"\u251c Price: ${price:,.2f}",
                f"\u251c RSI: {m.rsi:.1f} {rsi_arrow}",
                f"\u251c MACD Hist: {m.macd_hist:+.4f} {macd_ok}",
                f"\u251c EMA Trend: {ema_ok} (spread {m.ema_spread_pct:+.2f}%)",
                f"\u251c ADX: {m.adx:.1f}",
                f"\u251c ATR Pctile: {m.atr_percentile:.0%}",
                f"\u251c Vol Z: {m.volume_zscore:.2f}",
                f"\u2514 BB Width: {m.bb_width:.4f}",
                "",
            ])

        # Decision gate layers
        lines.extend([
            "\U0001f9e0 <b>Decision Gate</b>",
            f"\u251c L1 Rules: {'\u2705 PASS' if d.l1_passed else '\u274c FAIL'}",
            f"\u251c L2 Heuristic: {d.l2_confidence:.0%}",
            f"\u251c L3 LLM: {'\u2705 Called' if d.l3_called else '\u23ed Skipped'}",
            f"\u251c Decision: <b>{d.decision.value}</b>",
            f"\u251c Confidence: <b>{d.confidence:.0%}</b>",
            f"\u251c Risk: {d.risk_level}",
            f"\u251c Regime: {d.market_regime}",
            f"\u2514 Reason: {d.entry_reason}",
            "",
        ])

        # Risk flags
        if flags:
            flag_lines = [f"\u251c {f}" for f in flags]
            flag_lines[-1] = flag_lines[-1].replace("\u251c", "\u2514", 1)
            lines.extend([
                "\u26a0\ufe0f <b>Risk Flags</b>",
                *flag_lines,
                "",
            ])

        # Sentiment
        if news_ctx and news_ctx.window_4h.headline_count > 0:
            ws = news_ctx.window_4h.trust_weighted_sentiment
            lines.extend([
                "\U0001f4f0 <b>Sentiment (FinBERT)</b>",
                f"\u251c 4h Score: {ws:+.3f}",
                f"\u2514 Headlines: {news_ctx.window_4h.headline_count}",
                "",
            ])

        # Analysis summary from LLM
        if d.analysis_summary:
            lines.extend([
                f"\U0001f4dd {d.analysis_summary}",
                "",
            ])

        # Invalidators
        if d.invalidators:
            inv_lines = [f"\u251c {inv}" for inv in d.invalidators[:4]]
            inv_lines[-1] = inv_lines[-1].replace("\u251c", "\u2514", 1)
            lines.extend([
                "\U0001f6ab <b>Invalidators</b>",
                *inv_lines,
                "",
            ])

        msg = "\n".join(lines)
        return self._send(msg)

    def notify_trade_exit(
        self,
        pair: str,
        profit_pct: float,
        exit_reason: str,
        duration_minutes: int = 0,
    ) -> bool:
        """Notify about a closed trade."""
        emoji = "\U0001f4b0" if profit_pct > 0 else "\U0001f4c9"
        hours = duration_minutes // 60
        mins = duration_minutes % 60
        dur = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

        msg = (
            f"{emoji} <b>TRADE CLOSED \u2014 {pair}</b>\n"
            f"{'\u2501' * 20}\n\n"
            f"\u251c P&L: <b>{profit_pct:+.2%}</b>\n"
            f"\u251c Exit: {exit_reason}\n"
            f"\u2514 Duration: {dur}"
        )
        return self._send(msg)

    def notify_custom(self, message: str) -> bool:
        """Send a custom free-form message."""
        return self._send(message)
