# Investment Tracker

Daily performance tracker and fund-manager-style analysis for a custom portfolio of equities and funds.

## Holdings tracked

| Ticker | Name | Type |
|--------|------|------|
| NVDA | Nvidia | Equity |
| AAPL | Apple | Equity |
| GOOGL | Alphabet (Google) | Equity |
| AMZN | Amazon | Equity |
| RBLX | Roblox | Equity |
| ILMN | Illumina | Equity |
| NKTR | Nektar Therapeutics | Equity |
| HMI | Harte-Hanks | Equity |
| VWRL.L | Vanguard FTSE All-World ETF | ETF |
| XDWH.L | Xtrackers MSCI World Hedged ETF | ETF |
| IIND.L | iShares MSCI India ETF | ETF |
| SGLN.L | iShares Physical Gold ETC | ETC |

## Features

- **Live market data** via Yahoo Finance (yfinance)
- **Technical analysis**: RSI, MACD, Bollinger Bands, SMA50/200, EMA20, ATR, volume trend, 52-week range, momentum
- **Buy / Sell / Hold signals** scored from multiple independent indicators
- **Fund manager commentary** synthesising technicals and fundamentals
- **HTML reports** saved to `reports/` directory
- **Daily scheduler** to auto-run at a configured time
- **Demo mode** with synthetic data (no internet required)

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Full live report — all holdings
python tracker.py

# Single ticker
python tracker.py --ticker NVDA

# Save HTML report to reports/
python tracker.py --save

# JSON output (for piping / further processing)
python tracker.py --json

# Demo mode (no internet needed)
python demo.py

# Auto-schedule: runs every day at 07:30
python schedule_daily.py

# Auto-schedule at custom time
python schedule_daily.py --time 08:00
```

## Report anatomy

Each holding shows:
- **Price** with day / week / month % change
- **RSI** (14-period)
- **Signal**: BUY / HOLD / SELL
- **Technical signals** — itemised reasons driving the recommendation
- **Fund manager view** — narrative commentary combining technicals, fundamentals, sector context and analyst consensus

## Signals methodology

The recommendation is derived from a weighted score across these indicators:

| Indicator | Weight |
|-----------|--------|
| SMA50 vs SMA200 (Golden/Death Cross) | 1 |
| Price vs EMA20 | 1 |
| RSI (oversold/overbought) | 2 |
| MACD vs signal line | 1 |
| Bollinger Band position | 1–2 |
| Volume trend confirmation | 1 |
| 52-week range position | 1 |
| 20-day rate of change | 1 |

A normalised score ≥ 0.5 → **BUY**, ≤ -0.5 → **SELL**, otherwise **HOLD**.

> **Disclaimer**: This tool is for informational purposes only. Nothing here constitutes financial advice. Always do your own research and consult a qualified financial adviser before investing.
