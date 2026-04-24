"""Quick smoke test for all live components."""
import sys, os, time
sys.path.insert(0, "user_data")
from dotenv import load_dotenv
load_dotenv()

print("=" * 50)
print("SENTINEL-X LIVE COMPONENT SMOKE TEST")
print("=" * 50)

# 1. FinBERT
print("\n[1/4] FinBERT Sentiment...")
t0 = time.time()
from sentinel_modules.sentiment_engine import SentimentEngine
se = SentimentEngine()
r1 = se.analyze_headline("Bitcoin surges past 100000")
r2 = se.analyze_headline("Crypto exchange hacked millions stolen")
print(f"  Positive: {r1['label']} ({r1['confidence']:.3f})")
print(f"  Negative: {r2['label']} ({r2['confidence']:.3f})")
print(f"  Time: {time.time()-t0:.1f}s")

# 2. RSS
print("\n[2/4] RSS Polling...")
t0 = time.time()
import tempfile
from sentinel_modules.news_ingestion import RSSPoller
p = RSSPoller(seen_hashes_path=tempfile.mktemp(suffix=".json"))
entries = p.poll()
print(f"  Fetched {len(entries)} entries from {len(p.feeds)} feeds")
print(f"  Time: {time.time()-t0:.1f}s")

# 3. Sentiment on real headlines
print("\n[3/4] Sentiment on real headlines...")
t0 = time.time()
se.enrich_entries(entries[:5])
ctx = se.compute_news_context(entries[:5])
print(f"  4h sentiment: {ctx.window_4h.trust_weighted_sentiment:.3f}")
print(f"  24h sentiment: {ctx.window_24h.trust_weighted_sentiment:.3f}")
print(f"  Time: {time.time()-t0:.1f}s")

# 4. LLM Decision Gate
print("\n[4/4] LLM Decision Gate...")
t0 = time.time()
from sentinel_modules.contracts import (
    MarketContext, NewsContext, DecisionPayload, TrendDirection, CandidateSide, GraphContext
)
from sentinel_modules.decision_gate import llm_decide
import datetime

market = MarketContext(
    pair="BTC/USDT", timeframe="15m",
    timestamp=datetime.datetime.now(datetime.timezone.utc),
    close=95000.0, rsi=50.0, macd=100.0, macd_signal=80.0, macd_hist=20.0,
    ema50=94000.0, ema200=92000.0, atr=500.0, volume_zscore=1.2,
    trend_15m=TrendDirection.BULLISH, trend_1h=TrendDirection.BULLISH,
    ema_spread_pct=0.5
)

payload = DecisionPayload(
    pair="BTC/USDT",
    market=market,
    news=NewsContext(),
    graph=GraphContext(),
    risk_flags=[],
    candidate_side=CandidateSide.LONG,
)

result = llm_decide(payload)
print(f"  Decision: {result.decision.value}")
print(f"  Confidence: {result.confidence:.2f}")
print(f"  Reason: {result.entry_reason}")
print(f"  Time: {time.time()-t0:.1f}s")

print("\n" + "=" * 50)
print("ALL SMOKE TESTS COMPLETE")
print("=" * 50)
