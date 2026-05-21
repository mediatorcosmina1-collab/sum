# AI Trading Platform — Setup Guide

## Quick Start

### 1. Install dependencies
```bash
cd trading-platform
pip install -r requirements.txt
```

### 2. Configure your keys
```bash
cp .env.example .env
```

Edit `.env`:
- **T212_API_KEY** — Get from: Trading 212 app → Settings → API (scroll to bottom)
- **ANTHROPIC_API_KEY** — Get from: console.anthropic.com
- **T212_MODE** — Start with `demo` to test without real money

### 3. Run it
```bash
python run.py
```

Open **http://localhost:8000** in your browser.

---

## How It Works

### AI Analysis Cycle (every 30 min by default)
1. Fetches your T212 account cash + current positions
2. Downloads market data + 20+ technical indicators for every ticker on your watchlist
3. Claude AI analyzes each ticker with full context (RSI, MACD, Bollinger, fundamentals, etc.)
4. For each **BUY** signal with confidence ≥ 70%: places a market order
5. For each **SELL** signal with confidence ≥ 70% (on held positions): places a sell order
6. All decisions + reasoning are logged to the database

### Stop-Loss / Take-Profit (every 5 min)
- Automatically sells any position that hits your configured stop-loss or take-profit %

### Dashboard
- **Dashboard**: Portfolio overview, value chart, bot activity log
- **Portfolio**: All open positions with P&L, quick sell
- **AI Research**: Deep-analyze any ticker on demand
- **Trade**: Manual buy/sell orders
- **Watchlist**: Monitored tickers with live market data
- **History**: Full trade log with AI reasoning

---

## Risk Settings (in .env)

| Setting | Default | Description |
|---------|---------|-------------|
| MAX_POSITION_PCT | 5% | Max % of portfolio per trade |
| STOP_LOSS_PCT | 3% | Auto-sell if position drops this much |
| TAKE_PROFIT_PCT | 8% | Auto-sell if position gains this much |
| MIN_CONFIDENCE | 70% | AI must be this confident to execute |
| MAX_OPEN_POSITIONS | 10 | Never hold more than this many stocks |
| ANALYSIS_INTERVAL_MINUTES | 30 | How often the AI runs |

---

## IMPORTANT DISCLAIMER

This is an automated trading system using AI. Trading involves risk of loss.
- **Always start in DEMO mode** (T212_MODE=demo)
- Test thoroughly before switching to live
- Never risk money you cannot afford to lose
- Past AI performance does not guarantee future results
