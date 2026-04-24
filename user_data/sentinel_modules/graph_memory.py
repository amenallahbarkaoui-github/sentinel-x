"""
Sentinel-X — Graph Memory (SQLite Trade Store)

Stores closed trades with full context for similarity retrieval.
Active only in dry-run / live modes.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .contracts import GraphContext, TradeRecord, TrendDirection

logger = logging.getLogger(__name__)


class TradeMemoryStore:
    """
    SQLite-backed store for trade contexts.

    Parameters
    ----------
    db_path : str or Path
        Path to the SQLite database file.
    """

    def __init__(self, db_path: str | Path = "user_data/trade_memory.db"):
        self._db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    # ── Connection ─────────────────────────────────────────────────────

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id        TEXT,
                pair            TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                side            TEXT NOT NULL,
                entry_reason    TEXT DEFAULT '',
                exit_reason     TEXT DEFAULT '',
                rsi             REAL DEFAULT 0,
                macd            REAL DEFAULT 0,
                ema_trend       TEXT DEFAULT 'neutral',
                sentiment_score REAL DEFAULT 0,
                pnl_pct         REAL DEFAULT 0,
                duration_minutes INTEGER DEFAULT 0,
                outcome         TEXT DEFAULT 'PENDING',
                market_state    TEXT DEFAULT ''
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(pair)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_outcome ON trades(outcome)
        """)
        self.conn.commit()

    # ── Write ──────────────────────────────────────────────────────────

    def store_trade(self, record: TradeRecord) -> int:
        """Insert a trade record. Returns the row id."""
        cur = self.conn.execute(
            """
            INSERT INTO trades
                (trade_id, pair, timestamp, side, entry_reason, exit_reason,
                 rsi, macd, ema_trend, sentiment_score,
                 pnl_pct, duration_minutes, outcome, market_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.trade_id,
                record.pair,
                record.timestamp.isoformat(),
                record.side.value,
                record.entry_reason,
                record.exit_reason,
                record.rsi,
                record.macd,
                record.ema_trend.value,
                record.sentiment_score,
                record.pnl_pct,
                record.duration_minutes,
                record.outcome,
                record.market_state,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def update_trade_exit(
        self,
        trade_id: str,
        exit_reason: str,
        pnl_pct: float,
        duration_minutes: int,
        outcome: str,
    ) -> None:
        """Update a previously stored trade with exit info."""
        self.conn.execute(
            """
            UPDATE trades
            SET exit_reason = ?, pnl_pct = ?, duration_minutes = ?, outcome = ?
            WHERE trade_id = ?
            """,
            (exit_reason, pnl_pct, duration_minutes, outcome, trade_id),
        )
        self.conn.commit()

    # ── Read / Similarity ──────────────────────────────────────────────

    def find_similar_setups(
        self,
        pair: str,
        rsi: float,
        ema_trend: str,
        macd_sign: str,  # "positive" | "negative"
        n: int = 10,
    ) -> GraphContext:
        """
        Find past trades with similar setup profile and build a GraphContext.

        Similarity criteria:
          - Same pair
          - RSI within ±10
          - Same EMA trend state
          - Same MACD sign
        """
        rows = self.conn.execute(
            """
            SELECT pnl_pct, duration_minutes, outcome, exit_reason
            FROM trades
            WHERE pair = ?
              AND outcome IN ('WIN', 'LOSS')
              AND ABS(rsi - ?) <= 10
              AND ema_trend = ?
              AND (
                    (? = 'positive' AND macd >= 0)
                    OR (? = 'negative' AND macd < 0)
                  )
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (pair, rsi, ema_trend, macd_sign, macd_sign, n),
        ).fetchall()

        if not rows:
            return GraphContext()

        wins = sum(1 for r in rows if r["outcome"] == "WIN")
        pnls = [r["pnl_pct"] for r in rows]
        durations = sorted(r["duration_minutes"] for r in rows)

        # Top failure pattern: most common exit_reason among losses
        loss_reasons: dict[str, int] = {}
        for r in rows:
            if r["outcome"] == "LOSS" and r["exit_reason"]:
                loss_reasons[r["exit_reason"]] = loss_reasons.get(r["exit_reason"], 0) + 1
        top_fail = max(loss_reasons, key=loss_reasons.get, default="") if loss_reasons else ""

        median_dur = durations[len(durations) // 2] if durations else 0

        return GraphContext(
            similar_setups_found=len(rows),
            similar_winrate=wins / len(rows),
            avg_pnl_pct=sum(pnls) / len(pnls),
            median_duration_min=median_dur,
            top_failure_pattern=top_fail,
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
