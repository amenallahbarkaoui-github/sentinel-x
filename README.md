<div align="center">

<br/>

# 🛡️ Sentinel-X

### Production-Grade AI Crypto Trading Bot

<p>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Freqtrade-2026.3-00BFFF?style=flat-square&logo=bitcoin&logoColor=white"/>
  <img src="https://img.shields.io/badge/Tests-83%20passed-22c55e?style=flat-square&logo=pytest&logoColor=white"/>
  <img src="https://img.shields.io/badge/Win%20Rate-92.3%25-22c55e?style=flat-square"/>
  <img src="https://img.shields.io/badge/License-MIT-6366f1?style=flat-square"/>
</p>

<p>
  <img src="https://img.shields.io/badge/LLM-GLM--5.1%20Tool%20Calling-7c3aed?style=flat-square"/>
  <img src="https://img.shields.io/badge/NLP-FinBERT%20Local%20Inference-059669?style=flat-square"/>
  <img src="https://img.shields.io/badge/Exchange-Binance%20Spot-F0B90B?style=flat-square&logo=binance&logoColor=black"/>
  <img src="https://img.shields.io/badge/Sharia%20Mode-Spot%20Only%20%7C%20Scholar%20Review-009900?style=flat-square"/>
</p>

<br/>

> Sentinel-X is a **multi-layer AI trading system** that fuses classical quantitative analysis with a real-time 3-stage decision pipeline — deterministic rule engine, heuristic confidence scoring, and an LLM (GLM-5.1) with structured tool calling. Built on Freqtrade with a **conservative spot-only, sharia-oriented architecture**: `exit_profit_only`, tight ROI targets, ATR-adaptive trailing, runtime guards for `spot` and `long-only`, and FinBERT-powered news sentiment.

<br/>

</div>

---

## Key Metrics

<div align="center">

| 📊 Backtest Period | 🏆 Win Rate | 💰 Profit Factor | 📉 Max Drawdown | 🧪 Test Suite |
|:------------------:|:-----------:|:----------------:|:---------------:|:-------------:|
| Jan 2025 – Apr 2026 (15 months) | **92.3%** | **1.65** | **0.86%** | **83 tests** |

</div>

---

## Table of Contents

- [Why Sentinel-X](#-why-sentinel-x)
- [Halal Review](#-halal-review)
- [Architecture](#-architecture)
- [Technology Stack](#-technology-stack)
- [Decision Pipeline](#-decision-pipeline)
- [Performance](#-performance)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Testing](#-testing)
- [Telegram Interface](#-telegram-interface)
- [Security](#-security)
- [Disclaimer](#-disclaimer)

---

## Why Sentinel-X

Most trading bots are either a bundle of indicators or a raw LLM prompt. Sentinel-X is neither — it is a **structured, layered system** where each component gates the next:

```
Raw Market Data
      │
      ▼
  Indicators (15m primary + 1h informative)   ← quantitative signal generation
      │
      ▼
  L1 Rule Engine                               ← deterministic hard filters
      │  PASS only ↓
  L2 Heuristic Validator                       ← confidence score from graph memory
      │  PASS only ↓
  L3 GLM-5.1 LLM (structured tool calling)    ← final reasoning over MarketContext
      │  APPROVE ↓
  Trade Entry + ATR Adaptive Trailing Stop
```

No signal reaches execution without passing **all three gates**. This multi-layer rejection model is what drives the 92.3% win rate in conservative mode — the bot simply does not trade unless everything aligns.

---

## ☪️ Halal Review

Sentinel-X is designed to enforce **conservative, commonly requested sharia-oriented constraints**, but the repository does **not** self-issue a fatwa or claim universal scholarly certification:

Runtime guardrails in `SentinelX` now refuse to start if any of the following drift from the conservative profile: `trading_mode != spot`, `margin_mode` is set, `can_short = True`, or the whitelist contains anything other than `BTC/USDT` and `ETH/USDT`.

**Important:** whether crypto itself, stablecoin quotes, or exchange custody are halal is still a matter for your scholar, jurisdiction, and risk policy. The code can enforce conservative constraints; it cannot issue a binding religious ruling.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            SENTINEL-X                                   │
│                                                                         │
│  ╔═══════════════════════════════════════════════════════════════════╗  │
│  ║                    DATA INGESTION LAYER                          ║  │
│  ║                                                                   ║  │
│  ║   Binance REST  ──►  15m OHLCV  ──►  Indicator Engine            ║  │
│  ║   Binance REST  ──►  1h  OHLCV  ──►  Trend Alignment Filter      ║  │
│  ║   RSS Feeds     ──►  News Items  ──►  FinBERT Sentiment          ║  │
│  ╚═══════════════════════════════╤═══════════════════════════════════╝  │
│                                  │  MarketContext (Pydantic v2)         │
│  ╔═══════════════════════════════▼═══════════════════════════════════╗  │
│  ║                   3-LAYER DECISION GATE                          ║  │
│  ║                                                                   ║  │
│  ║  ┌────────────────────────────────────────────────────────────┐  ║  │
│  ║  │  L1  Rule Engine          hard filters, zero tolerance     │  ║  │
│  ║  │      EMA trend · RSI range · MACD acceleration             │  ║  │
│  ║  │      volume z-score · ADX · ATR percentile · 1h align      │  ║  │
│  ║  └─────────────────────────────┬──────────────────────────────┘  ║  │
│  ║                             PASS │ REJECT → stop                 ║  │
│  ║  ┌──────────────────────────────▼──────────────────────────────┐ ║  │
│  ║  │  L2  Heuristic Validator   confidence scoring               │ ║  │
│  ║  │      graph win-rate · ATR regime · L1 quality score         │ ║  │
│  ║  └─────────────────────────────┬───────────────────────────────┘ ║  │
│  ║                             PASS │ REJECT → stop                 ║  │
│  ║  ┌──────────────────────────────▼──────────────────────────────┐ ║  │
│  ║  │  L3  GLM-5.1 LLM           structured tool calling          │ ║  │
│  ║  │      submit_trading_decision(pair, action, confidence,      │ ║  │
│  ║  │        reasoning, risk_level, market_regime)                │ ║  │
│  ║  └─────────────────────────────┬───────────────────────────────┘ ║  │
│  ╚═════════════════════════════════│══════════════════════════════════╝  │
│                               APPROVE │ REJECT                          │
│  ╔════════════════════════════════▼════════════════════════════════╗   │
│  ║                  EXECUTION & LIFECYCLE                         ║   │
│  ║                                                                 ║   │
│  ║   Entry (limit order)                                          ║   │
│  ║   → ATR Trailing Stop  (activates at +1.5% · locks ≥ +0.3%)   ║   │
│  ║   → ROI exit  OR  trailing lock  OR  emergency stop (-5%)      ║   │
│  ║   → Graph Memory  (store context + outcome for L2 learning)    ║   │
│  ║   → Telegram       (rich HTML P&L notification)                ║   │
│  ╚═════════════════════════════════════════════════════════════════╝   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Role |
|-------|-----------|------|
| **Framework** | [Freqtrade 2026.3](https://www.freqtrade.io/) | Trading engine, backtesting, order management |
| **Language** | Python 3.12+ | Async-compatible, full type annotations |
| **Technical Analysis** | TA-Lib 0.6.8 | C-compiled: RSI, MACD, EMA, ATR, ADX, Bollinger |
| **LLM** | GLM-5.1 via z.ai | OpenAI-compatible API with native tool/function calling |
| **NLP / Sentiment** | [FinBERT](https://huggingface.co/ProsusAI/finbert) | Finance-domain BERT — runs locally, zero API cost |
| **Data Contracts** | Pydantic v2 | Strict typed models: `MarketContext`, `DecisionOutput` |
| **Trade Memory** | SQLite + graph layer | Similarity-based historical context retrieval |
| **News Feed** | RSS ingestion | Deduplicated with time-decay relevance scoring |
| **Notifications** | Telegram Bot API | Rich HTML: entry analysis, exit P&L, startup |
| **Testing** | pytest | 83 tests — unit + integration across all modules |

---

## Decision Pipeline

### L1 — Rule Engine (Deterministic)

Every condition must pass simultaneously:

```python
# Trend structure
ema50 > ema200              # confirmed uptrend
ema_spread_pct > 0.2%       # meaningful separation
close > ema50               # price above momentum line

# Momentum
42 < RSI < 58               # neither overbought nor oversold
RSI rising (2 candles)      # building momentum
MACD histogram > 0          # bullish
2-candle MACD acceleration  # momentum increasing

# Volume & Market Regime
volume_zscore > 0.5         # above-average participation
ADX > 18                    # trending, not ranging
ATR_percentile < 0.85       # not in extreme volatility spike

# Higher-Timeframe Alignment (1h informative)
trend_1h != "bearish"
close_1h > ema50_1h
```

### L2 — Heuristic Validator

Soft confidence scoring from:
- **Graph win-rate** — historical win-rate for structurally similar setups
- **ATR regime** — volatility quality relative to historical baseline
- **L1 quality score** — how comfortably the signal cleared Layer 1

### L3 — LLM with Tool Calling

GLM-5.1 receives a serialized `MarketContext` and must respond by calling `submit_trading_decision` — free-text responses are not accepted. This enforces structured, auditable decisions:

```json
{
  "function": "submit_trading_decision",
  "parameters": {
    "pair": "ETH/USDT",
    "action": "ENTER_LONG",
    "confidence": 0.84,
    "reasoning": "Strong EMA alignment with confirmed MACD acceleration on above-average volume. 1h trend supportive.",
    "risk_level": "LOW",
    "market_regime": "TRENDING_BULL"
  }
}
```

### ATR Adaptive Trailing Stoploss

```
profit < 1.5%  →  hold — 5% hard floor only (room to recover)
profit ≥ 1.5%  →  trail at 1.0 × ATR%
profit ≥ 3.0%  →  trail at 0.75 × ATR%  (tighter)
profit ≥ 5.0%  →  trail at 0.5 × ATR%   (lock big winners)

lock floor: max(current_profit − trail, +0.3%)
```

Once trailing activates the **minimum exit is +0.3%**. In Freqtrade reports, `trailing_stop_loss` may still include hard-floor exits emitted by `custom_stoploss`, so the backtest table should be read with that implementation detail in mind.

---

## Performance

> Binance Spot conservative mode (`BTC/USDT`, `ETH/USDT`) · Jan 2025 – Apr 2026 (15 months) · 1,000 USDT start · 100 USDT/trade · 0.10% fee

### Summary

| Metric | Value |
|--------|-------|
| Total Trades | 39 |
| **Win Rate** | **92.3%** |
| ROI Exit Win Rate | **100%** (36 / 36) |
| Total Profit | +9.163 USDT |
| **Profit Factor** | **1.65** |
| **Max Drawdown** | **0.86%** |
| Min Balance Ever | 996.436 USDT |
| Avg Winning Trade | +0.65% |
| Avg Losing Trade | -4.69% *(hard stop only)* |
| Avg Trade Duration | 12h 50m |

### Exit Breakdown

| Exit Reason | Count | Avg P&L | Win Rate |
|-------------|:-----:|:-------:|:--------:|
| `roi` | 36 | +0.65% | **100%** |
| `trailing_stop_loss` *(custom-stop hard floor in practice)* | 3 | -4.69% | 0% |

### Per-Pair Breakdown

| Pair | Trades | Win Rate | Net Profit |
|------|:------:|:--------:|:----------:|
| ETH/USDT | 21 | **100%** | +12.79 USDT |
| BTC/USDT | 18 | 83.3% | -3.624 USDT |

---

## Project Structure

```
sentinel-x/
│
├── user_data/
│   ├── strategies/
│   │   └── sentinel_x.py              # IStrategy — entry/exit logic, custom_stoploss
│   │
│   └── sentinel_modules/
│       ├── contracts.py               # Pydantic v2: MarketContext, DecisionOutput
│       ├── indicators.py              # TA indicator library (12 indicators)
│       ├── decision_gate.py           # 3-layer AI decision pipeline
│       ├── sentiment_engine.py        # FinBERT local inference + LLM fallback
│       ├── news_ingestion.py          # RSS ingestion with dedup + time-decay
│       ├── graph_memory.py            # SQLite trade context store
│       ├── risk_manager.py            # Position sizing & exposure guards
│       └── telegram_notifier.py       # Rich HTML Telegram notifications
│
├── tests/
│   ├── conftest.py
│   ├── test_contracts.py
│   ├── test_indicators.py
│   ├── test_decision_gate.py
│   ├── test_sentiment_engine.py
│   ├── test_news_ingestion.py
│   ├── test_graph_memory.py
│   └── test_telegram_notifier.py      # 83 tests total, all passing
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Installation

### 1. Clone

```bash
git clone https://github.com/amenallahbarkaoui-github/sentinel-x.git
cd sentinel-x
```

### 2. Install TA-Lib (system dependency)

**Windows** — pre-built wheel from [ta-lib-build](https://github.com/cgohlke/talib-build):
```bash
pip install TA_Lib-0.4.xx-cpXX-cpXX-win_amd64.whl
```

**Linux / macOS:**
```bash
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib && ./configure && make && sudo make install
```

### 3. Environment & dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Credentials

```bash
cp .env.example .env
# Edit .env with your keys
```

---

## Configuration

### `.env`

```env
# LLM — GLM-5.1 via z.ai (free tier available)
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.z.ai/api/coding/paas/v4
LLM_MODEL=glm-5.1

# Telegram (optional but recommended)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Key `config.json` fields

```json
{
  "max_open_trades": 2,
  "stake_amount": 100,
  "dry_run": true,
  "exit_profit_only": true,
  "exchange": {
    "name": "binance",
    "key": "",
    "secret": "",
    "pair_whitelist": ["BTC/USDT", "ETH/USDT"]
  }
}
```

Set `"dry_run": false` and add API credentials when ready for live trading.

---

## Usage

```bash
# Download historical data
freqtrade download-data \
  --config user_data/config.json \
  --timerange 20250101-20260401 \
  --timeframes 15m 1h

# Backtest with monthly breakdown
freqtrade backtesting \
  --strategy SentinelX \
  --config user_data/config.json \
  --timerange 20250101-20260401 \
  --breakdown month

# Paper trading (dry run)
freqtrade trade \
  --strategy SentinelX \
  --config user_data/config.json
```

---

## Testing

```bash
# Full suite (83 tests)
pytest tests/ -v

# Individual modules
pytest tests/test_decision_gate.py -v
pytest tests/test_sentiment_engine.py -v
pytest tests/test_indicators.py -v
```

Tests cover: indicator computation, Pydantic contract validation, all 3 decision gate layers, FinBERT inference, news deduplication, graph memory CRUD, and Telegram message formatting.

---

## Telegram Interface

| Command | Action |
|---------|--------|
| `/status` | Open trades + unrealized P&L |
| `/profit` | Cumulative profit summary |
| `/balance` | Wallet balance |
| `/trades` | Last 10 closed trades |
| `/forcebuy ETH/USDT` | Manual entry (dry-run safe) |
| `/forceexit all` | Close all positions |
| `/stop` / `/start` | Stop / start the bot |

Automatic alerts:
- **Entry** — indicators snapshot, LLM reasoning, sentiment score, confidence level
- **Exit** — P&L, duration, exit reason
- **Startup** — mode, pairs, wallet, config summary

---

## Security

- Never commit `.env` — already excluded via `.gitignore`
- Use Binance **read + trade** permissions only — **never withdrawal**
- Validate behavior in dry-run before live deployment
- All entry/exit orders use `limit` type — no market order slippage
- LLM is activated only in live/dry-run mode — backtesting is pure TA

---

## Disclaimer

> **For educational and research purposes only.**  
> Cryptocurrency trading carries substantial risk of loss. Past backtest performance does not guarantee future returns. Never invest more than you can afford to lose. Always validate in dry-run mode before going live.

---

<div align="center">

<br/>

Built with precision · [Freqtrade](https://www.freqtrade.io/) · [FinBERT](https://huggingface.co/ProsusAI/finbert) · [GLM-5.1](https://z.ai/) · [Pydantic](https://docs.pydantic.dev/)

<br/>

</div>
