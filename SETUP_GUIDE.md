# Sentinel-X V16 — Setup & Run Guide

## Architecture Overview

```
Signal Detected (15m candle)
        │
        ▼
┌─── L1: Rule Engine ───┐       vectorized / fast
│  EMA, RSI, MACD, Vol   │
│  ADX > 18 (regime)     │
│  ATR pctile < 0.85     │
└────────┬───────────────┘
         │ PASS
         ▼
┌─── L2: Heuristic ─────┐       graph + sentiment
│  Graph winrate check   │
│  BTC 1h context        │
│  FinBERT sentiment     │
└────────┬───────────────┘
         │ confidence > 0.50
         ▼
┌─── L3: GLM-5.1 LLM ───┐       tool calling
│  Multi-factor analysis │
│  Market regime class.  │
│  Risk level assessment │
│  Structured JSON out   │
└────────┬───────────────┘
         │ BUY + confidence ≥ 0.60
         ▼
┌─── Telegram ───────────┐
│  Full analysis sent    │
│  BEFORE execution      │
└────────┬───────────────┘
         │
         ▼
     Execute Trade
         │
         ▼
┌─── Exit Architecture ──┐
│  ATR-based trailing    │
│  Late ROI floor (6h/12h)│
│  Overbought reversal   │
│  Negative news exit    │
└────────────────────────┘
```

## Prerequisites

- Python 3.11+ (tested on 3.14.2)
- Freqtrade 2026.3
- TA-Lib C library installed
- Binance account (API keys for live trading)

## Quick Start

### 1. Activate Environment

```powershell
cd C:\path\to\sentinel-x
.\.venv\Scripts\Activate.ps1
```

### 2. Verify Configuration

The `.env` file contains all sensitive credentials:

```
# LLM Decision Gate (GLM-5.1 via z.ai)
LLM_API_KEY=<your-key>
LLM_BASE_URL=https://api.z.ai/api/coding/paas/v4
LLM_MODEL=glm-5.1

# Telegram Notifications
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
```

### 3. Run Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: **83 tests passed**

### 4. Run Backtest

```powershell
# In-sample (12 months)
.\.venv\Scripts\freqtrade.exe backtesting --strategy SentinelX -c user_data/config.json --timerange 20250401-20260401

# Out-of-sample (3 months)
.\.venv\Scripts\freqtrade.exe backtesting --strategy SentinelX -c user_data/config.json --timerange 20250101-20250401

# Full period (15 months)
.\.venv\Scripts\freqtrade.exe backtesting --strategy SentinelX -c user_data/config.json --timerange 20250101-20260401
```

### 5. Launch Dry-Run

```powershell
.\.venv\Scripts\freqtrade.exe trade --strategy SentinelX -c user_data/config.json
```

This will:
- Initialize FinBERT sentiment engine
- Connect to Binance (dry-run mode)
- Start Telegram notifications
- Send startup message to your Telegram

### 6. Telegram Bot Commands

Freqtrade's built-in Telegram commands:

| Command | Description |
|---------|-------------|
| `/status` | Show open trades |
| `/profit` | Show profit summary |
| `/balance` | Show account balance |
| `/daily` | Daily profit |
| `/performance` | Pair performance |
| `/forcesell <id>` | Force-close a trade |
| `/start` / `/stop` | Start/stop trading |
| `/reload_config` | Reload configuration |
| `/help` | List all commands |

### 7. Switch to Live Trading

When ready for real money:

1. Edit `user_data/config.json`:
   ```json
   "dry_run": false,
   "exchange": {
       "key": "<your-binance-api-key>",
       "secret": "<your-binance-secret>"
   }
   ```

2. Start with minimal stake:
   ```json
   "stake_amount": 10,
   "max_open_trades": 1
   ```

3. Monitor via Telegram for at least 1 week before increasing stake.

---

## Backtest Benchmark Results (V16)

| Period | Trades | WR | PF | Profit | Max DD |
|--------|--------|-----|------|---------|--------|
| In-sample (Apr 25 – Apr 26) | 30 | 83.3% | **2.66** | +16.26 USDT | 0.39% |
| Out-of-sample (Jan 25 – Apr 25) | 10 | 70.0% | 1.08 | +0.54 USDT | 0.56% |
| Full (Jan 25 – Apr 26) | 40 | 80.0% | **2.02** | +16.80 USDT | 0.67% |

### Exit Breakdown (Full Period)

| Exit Method | Trades | Win Rate | Net Profit |
|-------------|--------|----------|------------|
| ROI floor (6h/12h) | 24 | **100%** | +21.04 USDT |
| ATR trailing stop | 16 | 50% | -4.24 USDT |

### Key Metrics
- **Max consecutive wins**: 16
- **Max consecutive losses**: 2
- **Worst single trade**: -2.69%
- **Best single trade**: +1.93%
- **Avg trade duration**: 11h 12m

---

## Module Reference

| Module | Purpose |
|--------|---------|
| `sentinel_x.py` | Main strategy (V16) |
| `decision_gate.py` | 3-layer decision pipeline (L1→L2→L3/GLM) |
| `telegram_notifier.py` | Rich Telegram notifications |
| `indicators.py` | TA indicators (RSI, MACD, EMA, ATR, ADX, BB) |
| `contracts.py` | Pydantic data models |
| `sentiment_engine.py` | FinBERT sentiment analysis |
| `news_ingestion.py` | RSS feed polling |
| `graph_memory.py` | Trade history pattern matching |
| `risk_manager.py` | Risk flag detection |

---

## What Happens on Each Trade

### Entry Flow (dry-run / live)
1. 15m candle closes → L1 rules check (vectorized)
2. Signal detected → `confirm_trade_entry` callback
3. MarketContext built from latest indicators
4. Risk flags checked (BTC bearish, extreme RSI, low volume, ATR spike)
5. L2 heuristic: graph winrate + BTC context + sentiment
6. L3 GLM-5.1: tool calling → structured JSON decision
7. **Full analysis sent to Telegram** (BEFORE execution)
8. If BUY + confidence ≥ 0.60 → trade executes
9. If HOLD → trade rejected (logged + Telegram notified)

### Exit Flow
1. ATR-based trailing activates at +1.5% profit
2. Trail tightens: 1.0×ATR → 0.75×ATR → 0.5×ATR
3. Late ROI floor: 1.5% after 6h, 0.5% after 12h
4. Emergency: hard stop at -2.5%
5. Live: negative news exit if sentiment < -0.3
6. **Exit notification sent to Telegram** with P&L

### Telegram Message Example

```
✅ TRADE EXECUTED — BTC/USDT
━━━━━━━━━━━━━━━━━━━━

📊 Market Analysis
├ Price: $67,450.00
├ RSI: 52.3 ↑
├ MACD Hist: +0.0050 ✅
├ EMA Trend: ✅ (spread +1.54%)
├ ADX: 24.5
├ ATR Pctile: 45%
├ Vol Z: 1.20
└ BB Width: 0.0320

🧠 Decision Gate
├ L1 Rules: ✅ PASS
├ L2 Heuristic: 82%
├ L3 LLM: ✅ Called
├ Decision: BUY
├ Confidence: 85%
├ Risk: low
├ Regime: trending_bullish
└ Reason: Strong trend continuation with volume

📰 Sentiment (FinBERT)
├ 4h Score: +0.250
└ Headlines: 8

📝 All indicators aligned, uptrend confirmed
```

---

## Security Notes

- `.env` contains API keys — **never commit to git**
- `config.json` contains Telegram token — add to `.gitignore` if using git
- Binance API keys should have **spot trade only** permissions (no withdraw)
- Start with dry-run, monitor for 1+ week before live
