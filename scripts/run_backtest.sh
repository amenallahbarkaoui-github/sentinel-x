#!/usr/bin/env bash
# Sentinel-X — Backtest Suite
# Run from project root: bash scripts/run_backtest.sh

set -euo pipefail

CONFIG="user_data/config.json"
STRATEGY="SentinelX"

echo "============================================================"
echo " Sentinel-X Backtesting Suite"
echo "============================================================"

# ── 1. Lookahead analysis ─────────────────────────────────────
echo ""
echo ">>> [1/4] Lookahead bias analysis..."
freqtrade lookahead-analysis \
    --strategy "$STRATEGY" \
    --config "$CONFIG" \
    --timerange 20250401-20260401 \
    || echo "WARNING: lookahead-analysis failed or not available in this version."

# ── 2. Primary backtest (in-sample) ──────────────────────────
echo ""
echo ">>> [2/4] Primary backtest (Apr 2025 – Apr 2026)..."
freqtrade backtesting \
    --strategy "$STRATEGY" \
    --config "$CONFIG" \
    --timerange 20250401-20260401 \
    --export trades \
    --breakdown month

# ── 3. Out-of-sample backtest ────────────────────────────────
echo ""
echo ">>> [3/4] Out-of-sample backtest (Jan 2025 – Apr 2025)..."
freqtrade backtesting \
    --strategy "$STRATEGY" \
    --config "$CONFIG" \
    --timerange 20250101-20250401 \
    --export trades \
    --breakdown month

# ── 4. Timeframe-detail backtest (intra-candle) ─────────────
echo ""
echo ">>> [4/4] Timeframe-detail backtest (5m detail)..."
freqtrade backtesting \
    --strategy "$STRATEGY" \
    --config "$CONFIG" \
    --timerange 20250401-20260401 \
    --timeframe-detail 5m \
    --export trades

echo ""
echo "============================================================"
echo " Backtest suite complete. Check user_data/backtest_results/"
echo "============================================================"
echo ""
echo "Acceptance criteria to verify:"
echo "  - Profit Factor > 1.3"
echo "  - Expectancy > 0"
echo "  - Max Drawdown < 12%"
echo "  - Total trades > 150"
echo "  - No lookahead bias detected"
