"""Smoke test: RSS polling + Sentiment Engine."""
import sys, time
sys.path.insert(0, "user_data")

print("=== RSS Poller Test ===")
from sentinel_modules.news_ingestion import RSSPoller

poller = RSSPoller(seen_hashes_path="user_data/rss_seen_test.json")
t0 = time.time()
entries = poller.poll()
elapsed = time.time() - t0
print(f"  Polled {len(entries)} new entries in {elapsed:.1f}s")

if entries:
    for e in entries[:3]:
        print(f"  - [{e.source}] {e.title[:80]}")
        print(f"    Tags: {e.asset_tags}, Published: {e.published_at}")

    print("\n=== Sentiment Engine Test ===")
    from sentinel_modules.sentiment_engine import SentimentEngine
    engine = SentimentEngine()
    t0 = time.time()
    enriched = engine.enrich_entries(entries[:5])  # only first 5 to keep fast
    elapsed = time.time() - t0
    print(f"  Analyzed {len(enriched)} headlines in {elapsed:.1f}s")
    for e in enriched:
        print(f"  - score={e.sentiment_score:+.2f} conf={e.confidence:.2f} | {e.title[:70]}")

    ctx = engine.compute_news_context(entries[:5])
    print(f"\n  NewsContext 4h: count={ctx.window_4h.headline_count}, "
          f"sentiment={ctx.window_4h.trust_weighted_sentiment:.3f}")
    print(f"  NewsContext 24h: count={ctx.window_24h.headline_count}")
else:
    print("  WARNING: No entries returned (possible network issue)")

# Cleanup test file
import os
try:
    os.remove("user_data/rss_seen_test.json")
except OSError:
    pass

print("\nSTATUS: PASS")
