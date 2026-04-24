<div align="center">

<h1>🛡️ Sentinel-X</h1>

<p><strong>AI-powered crypto trading bot — built on Freqtrade</strong></p>

<p>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Freqtrade-2026.3-00BFFF?style=for-the-badge&logo=bitcoin&logoColor=white"/>
  <img src="https://img.shields.io/badge/Tests-83%20passed-brightgreen?style=for-the-badge&logo=pytest&logoColor=white"/>
  <img src="https://img.shields.io/badge/Mode-Dry%20Run%20%7C%20Live-orange?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Exchange-Binance%20Spot-F0B90B?style=for-the-badge&logo=binance&logoColor=black"/>
</p>

<p>
  <img src="https://img.shields.io/badge/LLM-GLM--5.1%20(Tool%20Calling)-7B52AB?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Sentiment-FinBERT%20(Local)-4CAF50?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Notifications-Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white"/>
</p>

> A **production-grade**, multi-layer AI trading strategy that combines classical technical analysis with a 3-layer decision pipeline: deterministic rule engine → heuristic validator → GLM LLM with tool calling. Includes FinBERT news sentiment, SQLite graph trade memory, and rich Telegram notifications.

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Modules](#-modules)
- [Performance](#-performance)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Running the Bot](#-running-the-bot)
- [Backtesting](#-backtesting)
- [Testing](#-testing)
- [Telegram Commands](#-telegram-commands)
- [Project Structure](#-project-structure)
- [Disclaimer](#-disclaimer)

---

## 🔍 Overview

Sentinel-X is a **selective long-only trend-following** strategy for Binance Spot markets. It is designed around one principle: **only trade when multiple independent systems agree**.

In **backtesting**, the bot uses pure vectorized technical analysis with regime filters. In **dry-run / live** mode, it activates all AI layers:

| Layer | System | Technology |
|-------|--------|------------|
| Signal | Technical Analysis | RSI, MACD, EMA50/200, ATR, ADX, BB Width, Volume Z-score |
| Filter | Regime Detection | ADX > 18, ATR Percentile < 0.85 |
| Sentiment | News Analysis | FinBERT (ProsusAI) + RSS ingestion |
| Memory | Graph Trade Store | SQLite with similarity retrieval |
| Decision | AI Gate (3-Layer) | Rule Engine → Heuristic → GLM-5.1 (tool calling) |
| Exit | Adaptive Trailing | ATR-based custom stoploss |
| Alerts | Notifications | Rich HTML Telegram messages |

**Traded pairs:** `BTC/USDT` · `ETH/USDT` · `ADA/USDT` · `XRP/USDT`  
**Timeframes:** 15m primary · 1h informative

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SENTINEL-X BOT                             │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              MARKET DATA PIPELINE                            │  │
│  │  Binance 15m candles ──► Indicators ──► Regime Filter        │  │
│  │  Binance 1h  candles ──► BTC Context ──► Trend Alignment     │  │
│  └─────────────────────────────┬────────────────────────────────┘  │
│                                │  Entry Signal                      │
│  ┌─────────────────────────────▼────────────────────────────────┐  │
│  │              3-LAYER DECISION GATE                           │  │
│  │                                                              │  │
│  │  Layer 1 ─ Rule Engine        ─ hard rules, deterministic   │  │
│  │      │       (RSI, EMA, MACD, volume, sentiment)            │  │
│  │      │ PASS                                                  │  │
│  │  Layer 2 ─ Heuristic Validator ─ soft checks, confidence    │  │
│  │      │       (Graph win-rate, ATR regime, L1 quality)       │  │
│  │      │ PASS                                                  │  │
│  │  Layer 3 ─ GLM-5.1 LLM        ─ structured tool calling     │  │
│  │              (submit_trading_decision function schema)       │  │
│  └─────────────────────────────┬────────────────────────────────┘  │
│                                │  APPROVE / REJECT                  │
│  ┌─────────────────────────────▼────────────────────────────────┐  │
│  │              EXECUTION & MANAGEMENT                          │  │
│  │  Entry ──► ATR Trailing Stop ──► ROI/Exit Signal ──► Close  │  │
│  │                    │                                         │  │
│  │              Graph Memory ◄──── Store Trade Context         │  │
│  │              Telegram ◄──────── Rich HTML Notifications     │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Modules

| Module | File | Description |
|--------|------|-------------|
| **Strategy** | `strategies/sentinel_x.py` | Main Freqtrade IStrategy — entry/exit logic, callbacks |
| **Indicators** | `sentinel_modules/indicators.py` | All TA indicators (RSI, MACD, EMA, ATR, ADX, BB, Volume Z) |
| **Contracts** | `sentinel_modules/contracts.py` | Pydantic data models (MarketContext, DecisionOutput, …) |
| **Decision Gate** | `sentinel_modules/decision_gate.py` | 3-layer AI pipeline (Rule → Heuristic → GLM) |
| **Sentiment Engine** | `sentinel_modules/sentiment_engine.py` | FinBERT headline sentiment + LLM fallback |
| **News Ingestion** | `sentinel_modules/news_ingestion.py` | RSS feed ingestion with dedup & decay |
| **Graph Memory** | `sentinel_modules/graph_memory.py` | SQLite trade context store for similarity lookups |
| **Risk Manager** | `sentinel_modules/risk_manager.py` | Position sizing & exposure guards |
| **Telegram Notifier** | `sentinel_modules/telegram_notifier.py` | Rich HTML Telegram notifications |

---

## 📊 Performance

> Backtested on Binance Spot historical data (Jan 2025 – Apr 2026, 15 months)  
> Starting balance: 1,000 USDT | Stake: 100 USDT/trade | Fee: 0.10% (worst case)

### V17 — Final (BTC, ETH, ADA, XRP | 4 pairs)

| Metric | Value |
|--------|-------|
| **Total Trades** | 78 |
| **Win Rate** | 73.1% |
| **Total Profit** | +25.12 USDT (+2.51%) |
| **Profit Factor** | **1.60** |
| **Max Drawdown** | **0.69%** |
| **Drawdown Duration** | 62 days |
| **Avg Daily Profit** | +0.056 USDT |
| **Best Pair** | ETH/USDT +1.23% |

### Per-Pair Breakdown

| Pair | Trades | Win Rate | Total Profit |
|------|--------|----------|--------------|
| ETH/USDT | 22 | 81.8% | +12.28 USDT |
| ADA/USDT | 20 | 65.0% | +5.49 USDT |
| BTC/USDT | 18 | 77.8% | +4.52 USDT |
| XRP/USDT | 18 | 66.7% | +2.84 USDT |

### Capital Required for $30/Month

| Capital | Stake/Trade | Est. Monthly |
|---------|-------------|--------------|
| $500 | ~$125 | ~$8.40 |
| $1,000 | ~$250 | ~$16.70 |
| $1,500 | ~$375 | ~$25.05 |
| **$1,800** | **~$450** | **~$30** ✅ |

---

## 🔧 Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Tested on 3.14.2 |
| Freqtrade | 2026.3 | `pip install freqtrade` |
| TA-Lib | 0.6.8+ | [System lib required](https://ta-lib.github.io/ta-lib-python/) |
| GLM API key | — | [z.ai](https://z.ai/) (free tier available) |
| Binance account | — | API key + secret for live trading |
| Telegram Bot | — | `@BotFather` to create one (optional) |

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/amenallahbarkaoui-github/sentinel-x.git
cd sentinel-x
```

### 2. Install TA-Lib (system dependency)

**Windows:**
```bash
# Download pre-built wheel from: https://github.com/cgohlke/talib-build
pip install TA_Lib‑0.4.xx‑cpXX‑cpXX‑win_amd64.whl
```

**Linux / macOS:**
```bash
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz && cd ta-lib && ./configure && make && sudo make install
```

### 3. Create virtual environment & install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
pip install freqtrade
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your credentials
```

---

## ⚙️ Configuration

### `.env` file

```env
# LLM Decision Gate (GLM-5.1 via z.ai)
LLM_API_KEY=your_glm_api_key
LLM_BASE_URL=https://api.z.ai/api/coding/paas/v4
LLM_MODEL=glm-5.1

# Telegram Notifications (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### `user_data/config.json` key settings

```json
{
  "max_open_trades": 4,
  "stake_amount": 100,
  "dry_run": true,
  "dry_run_wallet": 1000,
  "exchange": {
    "name": "binance",
    "key": "",
    "secret": "",
    "pair_whitelist": ["BTC/USDT", "ETH/USDT", "ADA/USDT", "XRP/USDT"]
  }
}
```

> Set `"dry_run": false` and fill in your Binance API key/secret when ready for live trading.

---

## ▶️ Running the Bot

### Dry Run (paper trading — recommended first)

```bash
freqtrade trade \
  --strategy SentinelX \
  --config user_data/config.json
```

### Download historical data

```bash
freqtrade download-data \
  --config user_data/config.json \
  --timerange 20250101-20260401 \
  --timeframes 15m 1h
```

### Live Trading

1. Add your Binance API key and secret to `user_data/config.json`
2. Set `"dry_run": false`
3. Run the same `freqtrade trade` command above

---

## 📈 Backtesting

```bash
# Full backtest with monthly breakdown
freqtrade backtesting \
  --strategy SentinelX \
  --config user_data/config.json \
  --timerange 20250101-20260401 \
  --breakdown month

# In-sample only (last 12 months)
freqtrade backtesting \
  --strategy SentinelX \
  --config user_data/config.json \
  --timerange 20250401-20260401
```

---

## 🧪 Testing

```bash
# Run full test suite (83 tests)
pytest tests/ -v

# Run specific module tests
pytest tests/test_decision_gate.py -v
pytest tests/test_sentiment_engine.py -v
pytest tests/test_indicators.py -v
pytest tests/test_telegram_notifier.py -v
```

---

## 📱 Telegram Commands

Once running, control the bot from Telegram:

| Command | Description |
|---------|-------------|
| `/status` | Show all open trades |
| `/profit` | Cumulative profit summary |
| `/balance` | Wallet balance |
| `/trades` | Last 10 closed trades |
| `/forcebuy ETH/USDT` | Force a buy (dry-run safe) |
| `/forceexit all` | Close all open trades |
| `/stop` | Stop the bot |
| `/start` | Start the bot |

In addition to native commands, Sentinel-X sends:
- 🟢 **Entry alert** — full market analysis, LLM reasoning, sentiment score
- 🔴 **Exit alert** — P&L, duration, exit reason
- 🚀 **Startup alert** — mode, pairs, configuration summary

---

## 📁 Project Structure

```
sentinel-x/
├── user_data/
│   ├── strategies/
│   │   └── sentinel_x.py          # Main Freqtrade strategy (V17)
│   ├── sentinel_modules/
│   │   ├── __init__.py
│   │   ├── contracts.py            # Pydantic data models
│   │   ├── indicators.py           # TA indicator library
│   │   ├── decision_gate.py        # 3-layer AI decision pipeline
│   │   ├── sentiment_engine.py     # FinBERT / LLM news sentiment
│   │   ├── news_ingestion.py       # RSS feed ingestion
│   │   ├── graph_memory.py         # SQLite trade memory store
│   │   ├── risk_manager.py         # Position & exposure management
│   │   └── telegram_notifier.py    # Telegram rich notifications
│   └── config.json                 # Freqtrade configuration
├── tests/
│   ├── conftest.py
│   ├── test_contracts.py
│   ├── test_indicators.py
│   ├── test_decision_gate.py
│   ├── test_sentiment_engine.py
│   ├── test_news_ingestion.py
│   ├── test_graph_memory.py
│   └── test_telegram_notifier.py
├── .env.example                    # Environment variable template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🛡️ Security Notes

- **Never** commit `.env` or any file containing API keys
- `.env` is already in `.gitignore`
- Use Binance **read + trade** permissions only — never withdrawal permissions
- Run in dry-run mode first to validate behavior
- The bot uses `limit` orders only (no market orders on entry/exit)

---

## ⚠️ Disclaimer

> **This software is for educational and research purposes only.**  
> Cryptocurrency trading involves substantial risk of loss. Past backtest performance does not guarantee future results. The authors are not responsible for any financial losses incurred from using this software. Always start with dry-run mode and never invest more than you can afford to lose.

---

<div align="center">

Built with ❤️ using [Freqtrade](https://www.freqtrade.io/) · [FinBERT](https://huggingface.co/ProsusAI/finbert) · [GLM-5.1](https://z.ai/)

</div>
