#!/usr/bin/env python3
"""
Investment Tracker — daily performance, technicals and fund-manager commentary.

Usage:
    python tracker.py                  # full report, all holdings
    python tracker.py --ticker NVDA    # single ticker
    python tracker.py --save           # save HTML report to ./reports/
    python tracker.py --json           # output JSON for programmatic use
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from analysis import analyse

console = Console()

# ── Portfolio definition ──────────────────────────────────────────────────────
HOLDINGS = [
    {"ticker": "NVDA",   "name": "Nvidia",               "type": "equity",  "sector": "Technology"},
    {"ticker": "AAPL",   "name": "Apple",                "type": "equity",  "sector": "Technology"},
    {"ticker": "GOOGL",  "name": "Alphabet (Google)",    "type": "equity",  "sector": "Technology"},
    {"ticker": "AMZN",   "name": "Amazon",               "type": "equity",  "sector": "Consumer/Cloud"},
    {"ticker": "RBLX",   "name": "Roblox",               "type": "equity",  "sector": "Gaming/Metaverse"},
    {"ticker": "ILMN",   "name": "Illumina",             "type": "equity",  "sector": "Genomics"},
    {"ticker": "NKTR",   "name": "Nektar Therapeutics",  "type": "equity",  "sector": "Biotech"},
    {"ticker": "HMI",    "name": "Harte-Hanks",          "type": "equity",  "sector": "Marketing Services"},
    {"ticker": "VWRL.L", "name": "Vanguard FTSE All-World ETF", "type": "etf", "sector": "Global Equity"},
    {"ticker": "XDWH.L", "name": "Xtrackers MSCI World Hedged ETF", "type": "etf", "sector": "Developed Markets"},
    {"ticker": "IIND.L", "name": "iShares MSCI India ETF",  "type": "etf", "sector": "Emerging Markets"},
    {"ticker": "SGLN.L", "name": "iShares Physical Gold ETC", "type": "etc", "sector": "Commodities"},
]

RECOMMENDATION_COLOURS = {
    "BUY": "bold green",
    "HOLD": "bold yellow",
    "SELL": "bold red",
}


def _colour_pct(val: float) -> Text:
    formatted = f"{val:+.2f}%"
    if val > 0:
        return Text(formatted, style="green")
    elif val < 0:
        return Text(formatted, style="red")
    return Text(formatted)


def _fetch_history(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist.empty:
            return None
        return hist
    except Exception as e:
        console.print(f"[red]Failed to fetch {ticker}: {e}[/red]")
        return None


def _fetch_info(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        return info
    except Exception:
        return {}


def _fund_manager_commentary(holding: dict, result: dict, info: dict) -> str:
    """Generate concise fund-manager style narrative."""
    lines = []
    name = holding["name"]
    rec = result["recommendation"]
    score = result["score"]
    rsi = result.get("rsi")
    pct_52 = result.get("pct_from_52w_high", 0)
    month_chg = result.get("month_change_pct", 0)

    # Sector/macro context
    sector = holding.get("sector", "")
    asset_type = holding.get("type", "equity")

    if asset_type == "etf":
        lines.append(f"{name} provides diversified exposure. ")
    elif asset_type == "etc":
        lines.append(f"{name} is a physical commodity instrument. ")

    # Trend context
    if score >= 0.5:
        lines.append(f"Technical picture is constructive — multiple indicators aligned to the upside. ")
    elif score <= -0.5:
        lines.append(f"Technical picture is cautious — indicators skew negative. ")
    else:
        lines.append(f"Mixed signals present — no clear directional conviction. ")

    # RSI narrative
    if rsi is not None and not np.isnan(rsi):
        if rsi < 30:
            lines.append(f"RSI deeply oversold ({rsi:.0f}) — price may be exhausting sellers; watch for a bounce catalyst. ")
        elif rsi > 70:
            lines.append(f"RSI elevated ({rsi:.0f}) — momentum is stretched; disciplined investors may trim on further strength. ")

    # 52w context
    if pct_52 < -0.40:
        lines.append(f"Down {abs(pct_52)*100:.0f}% from peak — high-risk, high-reward territory; position sizing is key. ")
    elif pct_52 > -0.05:
        lines.append(f"Near all-time/52-week highs — momentum is strong but entry risk is elevated. ")

    # Monthly drift
    if month_chg > 15:
        lines.append(f"The {month_chg:.0f}% monthly surge warrants trailing stop discipline. ")
    elif month_chg < -15:
        lines.append(f"The {month_chg:.0f}% monthly drawdown raises questions about near-term support levels. ")

    # Fundamental snippets from info
    mkt_cap = info.get("marketCap")
    pe = info.get("trailingPE") or info.get("forwardPE")
    analyst_target = info.get("targetMeanPrice")
    current_price = result.get("price")

    if mkt_cap and mkt_cap > 0:
        if mkt_cap >= 1e12:
            lines.append(f"Market cap ${mkt_cap/1e12:.1f}T — mega-cap liquidity supports institutional ownership. ")
        elif mkt_cap >= 1e9:
            lines.append(f"Market cap ${mkt_cap/1e9:.1f}B. ")

    if pe and not np.isnan(pe):
        if pe > 50:
            lines.append(f"P/E of {pe:.0f}x reflects growth premium — execution must match expectations. ")
        elif pe < 15:
            lines.append(f"P/E of {pe:.0f}x looks undemanding — value opportunity if fundamentals hold. ")

    if analyst_target and current_price:
        upside = (analyst_target - current_price) / current_price * 100
        if abs(upside) > 5:
            direction = "upside" if upside > 0 else "downside"
            lines.append(f"Consensus price target implies {abs(upside):.0f}% {direction} from current levels. ")

    # Closing recommendation rationale
    if rec == "BUY":
        lines.append("Overall, the balance of evidence supports accumulation on weakness.")
    elif rec == "SELL":
        lines.append("Risk/reward is unfavourable at current levels; consider reducing exposure.")
    else:
        lines.append("Hold current position; re-assess on a decisive technical break either way.")

    return "".join(lines)


def run_analysis(tickers: list[dict]) -> list[dict]:
    results = []
    with console.status("[bold cyan]Fetching market data…[/bold cyan]"):
        for holding in tickers:
            ticker = holding["ticker"]
            hist = _fetch_history(ticker)
            if hist is None or len(hist) < 30:
                console.print(f"[yellow]Insufficient data for {ticker}, skipping.[/yellow]")
                continue
            result = analyse(hist)
            info = _fetch_info(ticker)
            commentary = _fund_manager_commentary(holding, result, info)
            results.append({
                "holding": holding,
                "result": result,
                "commentary": commentary,
                "info": info,
            })
    return results


def print_summary_table(results: list[dict]):
    table = Table(
        title=f"Portfolio Summary — {datetime.now().strftime('%A, %d %B %Y')}",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("Ticker", style="bold", width=8)
    table.add_column("Name", width=26)
    table.add_column("Price", justify="right", width=10)
    table.add_column("Day", justify="right", width=8)
    table.add_column("Week", justify="right", width=8)
    table.add_column("Month", justify="right", width=8)
    table.add_column("RSI", justify="right", width=6)
    table.add_column("Signal", justify="center", width=8)

    for item in results:
        h = item["holding"]
        r = item["result"]
        rec = r["recommendation"]
        rsi_val = r.get("rsi")
        rsi_str = f"{rsi_val:.0f}" if rsi_val and not np.isnan(rsi_val) else "—"

        table.add_row(
            h["ticker"],
            h["name"],
            f"${r['price']:.2f}" if h["ticker"] not in ("VWRL.L", "XDWH.L", "IIND.L", "SGLN.L") else f"{r['price']:.2f}",
            _colour_pct(r["day_change_pct"]),
            _colour_pct(r["week_change_pct"]),
            _colour_pct(r["month_change_pct"]),
            rsi_str,
            Text(rec, style=RECOMMENDATION_COLOURS[rec]),
        )

    console.print(table)


def print_detail_cards(results: list[dict]):
    console.print("\n[bold cyan]── Detailed Analysis ──────────────────────────────────────────────[/bold cyan]\n")
    for item in results:
        h = item["holding"]
        r = item["result"]
        commentary = item["commentary"]
        rec = r["recommendation"]

        # Build reasons list
        reasons_text = "\n".join(f"  • {reason}" for reason in r["reasons"])

        # Key stats
        sma50 = r.get("sma_50")
        sma200 = r.get("sma_200")
        atr_pct = r.get("atr_pct")

        stats_lines = []
        if sma50 and not np.isnan(sma50):
            stats_lines.append(f"SMA50: {sma50:.2f}")
        if sma200 and not np.isnan(sma200):
            stats_lines.append(f"SMA200: {sma200:.2f}")
        if atr_pct and not np.isnan(atr_pct):
            stats_lines.append(f"ATR%: {atr_pct:.1f}%")
        stats_line = "  |  ".join(stats_lines)

        content = (
            f"[bold]{h['name']}[/bold]  [{RECOMMENDATION_COLOURS[rec]}]{rec}[/{RECOMMENDATION_COLOURS[rec]}]  "
            f"[dim]{h['sector']}  ·  {h['type'].upper()}[/dim]\n\n"
            f"[bold]Price:[/bold] {r['price']:.2f}   "
            f"Day: {_colour_pct(r['day_change_pct'])}   "
            f"Month: {_colour_pct(r['month_change_pct'])}   "
            f"52w High: {_colour_pct(r['pct_from_52w_high'] * 100)}\n"
            f"[dim]{stats_line}[/dim]\n\n"
            f"[bold]Technical signals:[/bold]\n{reasons_text}\n\n"
            f"[bold]Fund manager view:[/bold]\n  {commentary}"
        )

        panel = Panel(
            content,
            title=f"[bold]{h['ticker']}[/bold]",
            border_style=RECOMMENDATION_COLOURS[rec].replace("bold ", ""),
            expand=False,
            width=90,
        )
        console.print(panel)
        console.print()


def save_html_report(results: list[dict], output_dir: str = "reports"):
    Path(output_dir).mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = Path(output_dir) / f"report_{date_str}.html"

    rec_colours = {"BUY": "#4ade80", "HOLD": "#facc15", "SELL": "#f87171"}

    rows = []
    for item in results:
        h = item["holding"]
        r = item["result"]
        rec = r["recommendation"]
        colour = rec_colours[rec]
        rsi_val = r.get("rsi")
        rsi_str = f"{rsi_val:.0f}" if rsi_val and not np.isnan(rsi_val) else "—"

        def pct_cell(v):
            c = "#4ade80" if v > 0 else "#f87171" if v < 0 else "#e5e7eb"
            return f'<td style="color:{c};text-align:right">{v:+.2f}%</td>'

        reasons_html = "".join(f"<li>{r2}</li>" for r2 in r["reasons"])

        rows.append(f"""
        <tr>
          <td><strong>{h['ticker']}</strong></td>
          <td>{h['name']}</td>
          <td style="text-align:right">{r['price']:.2f}</td>
          {pct_cell(r['day_change_pct'])}
          {pct_cell(r['week_change_pct'])}
          {pct_cell(r['month_change_pct'])}
          <td style="text-align:right">{rsi_str}</td>
          <td style="text-align:center;color:{colour};font-weight:bold">{rec}</td>
        </tr>
        <tr class="detail-row">
          <td colspan="8" style="padding:12px 16px;background:#1e293b;font-size:0.85em">
            <strong>Technical signals:</strong><ul style="margin:4px 0 8px 0">{reasons_html}</ul>
            <strong>Fund manager view:</strong> {item['commentary']}
          </td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Investment Report — {date_str}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background:#0f172a; color:#e2e8f0; margin:0; padding:24px; }}
  h1 {{ color:#38bdf8; margin-bottom:4px; }}
  .subtitle {{ color:#94a3b8; margin-bottom:24px; font-size:0.9em; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.9em; }}
  th {{ background:#1e293b; color:#94a3b8; padding:10px 12px; text-align:left;
        border-bottom:1px solid #334155; }}
  td {{ padding:10px 12px; border-bottom:1px solid #1e293b; vertical-align:top; }}
  tr:hover td {{ background:#1e293b; }}
  .detail-row td {{ color:#94a3b8; }}
  ul {{ padding-left:18px; }}
  li {{ margin-bottom:2px; }}
</style>
</head>
<body>
<h1>Portfolio Daily Report</h1>
<p class="subtitle">Generated {datetime.now().strftime('%A, %d %B %Y at %H:%M')}</p>
<table>
  <thead>
    <tr>
      <th>Ticker</th><th>Name</th><th>Price</th>
      <th>Day</th><th>Week</th><th>Month</th>
      <th>RSI</th><th>Signal</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
</body>
</html>"""

    filepath.write_text(html)
    console.print(f"\n[green]HTML report saved to:[/green] {filepath}")
    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="Investment Tracker — daily report")
    parser.add_argument("--ticker", help="Analyse a single ticker only")
    parser.add_argument("--save", action="store_true", help="Save HTML report to reports/")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    args = parser.parse_args()

    if args.ticker:
        tickers = [h for h in HOLDINGS if h["ticker"].upper() == args.ticker.upper()]
        if not tickers:
            # Ad-hoc ticker not in portfolio
            tickers = [{"ticker": args.ticker.upper(), "name": args.ticker.upper(),
                        "type": "equity", "sector": "Unknown"}]
    else:
        tickers = HOLDINGS

    console.print(Panel.fit(
        "[bold cyan]Investment Tracker[/bold cyan]  [dim]powered by yfinance + technical analysis[/dim]",
        border_style="cyan",
    ))

    results = run_analysis(tickers)

    if not results:
        console.print("[red]No data retrieved. Check your internet connection.[/red]")
        sys.exit(1)

    if args.json:
        output = []
        for item in results:
            r = item["result"]
            output.append({
                "ticker": item["holding"]["ticker"],
                "name": item["holding"]["name"],
                "price": round(r["price"], 4),
                "day_change_pct": round(r["day_change_pct"], 2),
                "week_change_pct": round(r["week_change_pct"], 2),
                "month_change_pct": round(r["month_change_pct"], 2),
                "recommendation": r["recommendation"],
                "rsi": round(r["rsi"], 1) if r.get("rsi") and not np.isnan(r["rsi"]) else None,
                "commentary": item["commentary"],
                "reasons": r["reasons"],
            })
        print(json.dumps(output, indent=2))
        return

    print_summary_table(results)
    print_detail_cards(results)

    if args.save:
        save_html_report(results)


if __name__ == "__main__":
    main()
