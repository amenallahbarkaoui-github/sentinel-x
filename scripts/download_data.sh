#!/usr/bin/env bash
# Sentinel-X — Download Historical Data
# Run from project root: bash scripts/download_data.sh

set -euo pipefail

CONFIG="user_data/config.json"
PAIRS="BTC/USDT ETH/USDT"
TIMEFRAMES="15m 1h"
TIMERANGE="20250101-20260401"

echo "=== Downloading OHLCV data ==="
echo "Pairs: $PAIRS"
echo "Timeframes: $TIMEFRAMES"
echo "Range: $TIMERANGE"
echo ""

freqtrade download-data \
    --config "$CONFIG" \
    --pairs $PAIRS \
    --timeframes $TIMEFRAMES \
    --timerange "$TIMERANGE" \
    --exchange binance

echo ""
echo "=== Download complete ==="
echo "Data stored in: user_data/data/"
