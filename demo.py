#!/usr/bin/env python3
"""
Demo mode — generates a synthetic report using realistic price data.
Run this to verify the app works before connecting to live market data.
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel

console = Console()

DEMO_DATA = {
    "NVDA":   {"price": 1208.88, "day": 2.31,  "week": 5.12,  "month": 18.4,  "rsi": 68, "rec": "BUY",  "sector": "Technology"},
    "AAPL":   {"price": 189.30,  "day": -0.42, "week": -1.20, "month": 3.1,   "rsi": 52, "rec": "HOLD", "sector": "Technology"},
    "GOOGL":  {"price": 176.55,  "day": 1.05,  "week": 2.80,  "month": 8.9,   "rsi": 59, "rec": "BUY",  "sector": "Technology"},
    "AMZN":   {"price": 193.61,  "day": 0.88,  "week": 3.40,  "month": 11.2,  "rsi": 61, "rec": "BUY",  "sector": "Consumer/Cloud"},
    "RBLX":   {"price": 44.21,   "day": -1.92, "week": -5.30, "month": -12.8, "rsi": 34, "rec": "HOLD", "sector": "Gaming"},
    "ILMN":   {"price": 134.78,  "day": -0.55, "week": -2.10, "month": -6.4,  "rsi": 41, "rec": "HOLD", "sector": "Genomics"},
    "NKTR":   {"price": 3.91,    "day": -3.20, "week": -8.50, "month": -22.1, "rsi": 27, "rec": "SELL", "sector": "Biotech"},
    "HMI":    {"price": 7.65,    "day": 0.39,  "week": 1.20,  "month": 4.5,   "rsi": 55, "rec": "HOLD", "sector": "Marketing"},
    "VWRL.L": {"price": 112.46,  "day": 0.22,  "week": 0.80,  "month": 2.3,   "rsi": 54, "rec": "BUY",  "sector": "Global Equity ETF"},
    "XDWH.L": {"price": 34.18,   "day": 0.18,  "week": 0.65,  "month": 1.8,   "rsi": 53, "rec": "BUY",  "sector": "Developed Markets ETF"},
    "IIND.L": {"price": 27.92,   "day": -0.71, "week": -1.40, "month": 3.6,   "rsi": 49, "rec": "HOLD", "sector": "India ETF"},
    "SGLN.L": {"price": 28.54,   "day": 0.95,  "week": 2.30,  "month": 7.2,   "rsi": 63, "rec": "BUY",  "sector": "Gold ETC"},
}

COMMENTARIES = {
    "NVDA":   "Nvidia continues to dominate the AI accelerator market with unrivalled pricing power. RSI is elevated at 68 — healthy momentum without extreme overbought conditions. The AI infrastructure supercycle shows no signs of abating; TSMC capacity constraints are the primary near-term risk. We favour accumulation on any 5-8% pullbacks.",
    "AAPL":   "Apple is in a digestion phase after a modest re-rating. Services revenue remains the key growth driver. Mixed signals on China demand and Vision Pro adoption create a balanced picture. At current multiples, risk/reward favours holding rather than adding aggressively.",
    "GOOGL":  "Alphabet's AI-integrated search and growing cloud business provide dual growth vectors. The market is underestimating YouTube's monetisation potential. P/E of ~24x is reasonable for a business compounding free cash flow at this rate. Constructive — bias to add on dips.",
    "AMZN":   "AWS margin expansion is the compelling investment case here. Advertising is an underappreciated high-margin business scaling rapidly. MACD and momentum are both positive. Strong conviction long, with a 12-month price target suggesting meaningful upside.",
    "RBLX":   "Roblox remains a controversial name — strong user engagement metrics but a challenging path to profitability. The RSI at 34 hints at oversold conditions, but fundamental deterioration must stabilise first. Avoid adding until cost discipline evidence emerges in the next earnings.",
    "ILMN":   "Illumina is navigating post-Grail divestiture repositioning. Sequencing volumes are recovering but slowly. RSI and momentum indicators suggest the stock is finding a floor. Wait for clearer earnings inflection before adding — current positioning reflects a show-me story.",
    "NKTR":   "Nektar's pipeline setbacks have eroded the investment thesis materially. With RSI at 27, the stock is technically oversold but fundamentals remain impaired. Avoid new positions; existing holders should reassess their stop-loss discipline. High-risk speculation only.",
    "HMI":    "Harte-Hanks is a small-cap turnaround story with limited liquidity. Technicals are broadly neutral. The business is restructuring but macro headwinds in marketing services persist. Hold a modest position, but size appropriately given the illiquidity premium.",
    "VWRL.L": "VWRL is a core portfolio holding providing global diversification at minimal cost. Dollar-cost averaging remains the optimal strategy. Current momentum is mildly positive; this is a long-term compounder, not a trading instrument.",
    "XDWH.L": "The currency-hedged MSCI World ETF is well-positioned if GBP strengthens. Developed market valuations are stretched in the US but more reasonable in Europe and Japan. A prudent core allocation for risk-managed portfolios.",
    "IIND.L": "India's structural growth story — demographics, digitalisation, and domestic consumption — remains intact. Near-term RSI is neutral. Valuations are no longer cheap, but the secular tailwind justifies a strategic allocation. Stay invested; tactical additions on corrections.",
    "SGLN.L": "Physical gold is benefiting from central bank accumulation and geopolitical risk premia. RSI at 63 is constructive without being extreme. Gold serves as portfolio insurance in the current macro environment — maintain a 5-10% strategic allocation.",
}

COLOURS = {"BUY": "bold green", "HOLD": "bold yellow", "SELL": "bold red"}


def run_demo():
    from rich.table import Table
    from rich.text import Text

    console.print(Panel.fit(
        "[bold cyan]Investment Tracker[/bold cyan]  [dim]DEMO MODE — synthetic data[/dim]",
        border_style="cyan",
    ))
    console.print(f"[dim]Report date: {datetime.now().strftime('%A, %d %B %Y')}[/dim]\n")

    table = Table(
        title="Portfolio Summary",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("Ticker", style="bold", width=9)
    table.add_column("Name/Sector", width=28)
    table.add_column("Price", justify="right", width=10)
    table.add_column("Day", justify="right", width=8)
    table.add_column("Week", justify="right", width=8)
    table.add_column("Month", justify="right", width=8)
    table.add_column("RSI", justify="right", width=6)
    table.add_column("Signal", justify="center", width=8)

    names = {
        "NVDA": "Nvidia", "AAPL": "Apple", "GOOGL": "Alphabet",
        "AMZN": "Amazon", "RBLX": "Roblox", "ILMN": "Illumina",
        "NKTR": "Nektar", "HMI": "Harte-Hanks", "VWRL.L": "Vanguard FTSE All-World",
        "XDWH.L": "Xtrackers MSCI World Hdg", "IIND.L": "iShares MSCI India",
        "SGLN.L": "iShares Physical Gold",
    }

    def cpct(v):
        t = Text(f"{v:+.2f}%")
        t.stylize("green" if v > 0 else "red" if v < 0 else "dim")
        return t

    for ticker, d in DEMO_DATA.items():
        table.add_row(
            ticker,
            f"{names.get(ticker, ticker)}\n[dim]{d['sector']}[/dim]",
            f"{d['price']:.2f}",
            cpct(d["day"]),
            cpct(d["week"]),
            cpct(d["month"]),
            str(d["rsi"]),
            Text(d["rec"], style=COLOURS[d["rec"]]),
        )

    console.print(table)

    console.print("\n[bold cyan]── Detailed Analysis ──────────────────────────────────────────────[/bold cyan]\n")

    for ticker, d in DEMO_DATA.items():
        rec = d["rec"]
        commentary = COMMENTARIES.get(ticker, "")
        panel = Panel(
            f"[bold]{names.get(ticker, ticker)}[/bold]  [{COLOURS[rec]}]{rec}[/{COLOURS[rec]}]  [dim]{d['sector']}[/dim]\n\n"
            f"Price: {d['price']:.2f}  Day: [{'green' if d['day']>0 else 'red'}]{d['day']:+.2f}%[/{'green' if d['day']>0 else 'red'}]  "
            f"Month: [{'green' if d['month']>0 else 'red'}]{d['month']:+.2f}%[/{'green' if d['month']>0 else 'red'}]  "
            f"RSI: {d['rsi']}\n\n"
            f"[bold]Fund manager view:[/bold]\n  {commentary}",
            title=f"[bold]{ticker}[/bold]",
            border_style=COLOURS[rec].replace("bold ", ""),
            expand=False,
            width=90,
        )
        console.print(panel)
        console.print()

    console.print(
        Panel(
            "[yellow]This is DEMO mode with synthetic data.\n"
            "Run [bold]python tracker.py[/bold] for live market data (requires internet access).[/yellow]",
            border_style="yellow",
        )
    )


if __name__ == "__main__":
    run_demo()
