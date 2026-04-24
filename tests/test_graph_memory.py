"""Tests for Sentinel-X Graph Memory Store."""

from datetime import datetime, timezone

import pytest

from sentinel_modules.contracts import CandidateSide, TrendDirection, TradeRecord
from sentinel_modules.graph_memory import TradeMemoryStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test_memory.db"
    s = TradeMemoryStore(db_path=db_path)
    yield s
    s.close()


def _make_record(**overrides) -> TradeRecord:
    defaults = dict(
        trade_id="t1",
        pair="BTC/USDT",
        timestamp=datetime.now(timezone.utc),
        side=CandidateSide.LONG,
        entry_reason="test",
        rsi=55.0,
        macd=1.0,
        ema_trend=TrendDirection.BULLISH,
        sentiment_score=0.5,
        pnl_pct=0.02,
        duration_minutes=60,
        outcome="WIN",
    )
    defaults.update(overrides)
    return TradeRecord(**defaults)


class TestStoreAndRetrieve:
    def test_store_returns_id(self, store):
        row_id = store.store_trade(_make_record())
        assert row_id >= 1

    def test_update_exit(self, store):
        store.store_trade(_make_record(trade_id="tx1", outcome="PENDING"))
        store.update_trade_exit(
            trade_id="tx1",
            exit_reason="stoploss",
            pnl_pct=-0.03,
            duration_minutes=30,
            outcome="LOSS",
        )
        row = store.conn.execute(
            "SELECT outcome, pnl_pct FROM trades WHERE trade_id='tx1'"
        ).fetchone()
        assert row["outcome"] == "LOSS"
        assert row["pnl_pct"] == pytest.approx(-0.03)


class TestSimilarSetups:
    def test_no_history_returns_empty(self, store):
        ctx = store.find_similar_setups("BTC/USDT", rsi=55, ema_trend="bullish", macd_sign="positive")
        assert ctx.similar_setups_found == 0

    def test_finds_matching_trades(self, store):
        for i in range(5):
            store.store_trade(_make_record(
                trade_id=f"w{i}", rsi=56.0, outcome="WIN", pnl_pct=0.02,
            ))
        for i in range(3):
            store.store_trade(_make_record(
                trade_id=f"l{i}", rsi=54.0, outcome="LOSS", pnl_pct=-0.01,
                exit_reason="stoploss",
            ))

        ctx = store.find_similar_setups("BTC/USDT", rsi=55, ema_trend="bullish", macd_sign="positive")
        assert ctx.similar_setups_found == 8
        assert ctx.similar_winrate == pytest.approx(5 / 8)
        assert ctx.avg_pnl_pct > 0  # net positive
        assert ctx.top_failure_pattern == "stoploss"

    def test_different_pair_excluded(self, store):
        store.store_trade(_make_record(trade_id="e1", pair="ETH/USDT"))
        ctx = store.find_similar_setups("BTC/USDT", rsi=55, ema_trend="bullish", macd_sign="positive")
        assert ctx.similar_setups_found == 0

    def test_different_trend_excluded(self, store):
        store.store_trade(_make_record(trade_id="b1", ema_trend=TrendDirection.BEARISH))
        ctx = store.find_similar_setups("BTC/USDT", rsi=55, ema_trend="bullish", macd_sign="positive")
        assert ctx.similar_setups_found == 0
