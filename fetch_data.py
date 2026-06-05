#!/usr/bin/env python3
"""
Multi-source market data fetch.

Sources:
  1. Yahoo Finance  — price history (OHLCV 1y), fundamentals, analyst targets, news headlines
  2. Stooq          — independent price cross-validation
  3. Yahoo Finance  — macro context: VIX, S&P 500, FTSE 100, Gold, GBP/USD, US 10Y Treasury

Writes docs/data.json consumed by the static GitHub Pages frontend.
"""

import io
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf

sys.path.insert(0, ".")
from analysis import analyse
from tracker import HOLDINGS, _fund_manager_commentary

# ── Macro indicator symbols (Yahoo Finance) ───────────────────────────────────
MACRO_SYMBOLS = {
    "vix":         ("^VIX",     "VIX"),
    "sp500":       ("^GSPC",    "S&P 500"),
    "ftse100":     ("^FTSE",    "FTSE 100"),
    "gold":        ("GC=F",     "Gold"),
    "treasury10y": ("^TNX",     "US 10Y"),
    "gbpusd":      ("GBPUSD=X", "GBP/USD"),
}

# ── Stooq symbols for independent price cross-validation ─────────────────────
STOOQ_MAP = {
    "NVDA":   "nvda.us",
    "AAPL":   "aapl.us",
    "GOOGL":  "googl.us",
    "AMZN":   "amzn.us",
    "RBLX":   "rblx.us",
    "ILMN":   "ilmn.us",
    "NKTR":   "nktr.us",
    "HMI":    "hmi.us",
    "VWRL.L": "vwrl.uk",
    "XDWH.L": "xdwh.uk",
    "IIND.L": "iind.uk",
    "SGLN.L": "sgln.uk",
}


def _clean(v):
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return v


# ── Source 1/3: Yahoo Finance macro context ───────────────────────────────────
def fetch_macro() -> dict:
    macro = {}
    for key, (sym, label) in MACRO_SYMBOLS.items():
        try:
            hist = yf.Ticker(sym).history(period="5d")
            if hist is not None and len(hist) >= 2:
                price = float(hist["Close"].iloc[-1])
                prev  = float(hist["Close"].iloc[-2])
                macro[key] = {
                    "label":      label,
                    "value":      round(price, 4),
                    "change_pct": round((price - prev) / prev * 100, 2),
                }
            elif hist is not None and len(hist) == 1:
                macro[key] = {
                    "label":      label,
                    "value":      round(float(hist["Close"].iloc[-1]), 4),
                    "change_pct": None,
                }
        except Exception as exc:
            print(f"  macro {key}: {exc}")
    return macro


# ── Source 2: Stooq independent price cross-validation ───────────────────────
def fetch_stooq_price(ticker: str) -> float | None:
    sym = STOOQ_MAP.get(ticker)
    if not sym:
        return None
    try:
        r = requests.get(f"https://stooq.com/q/d/l/?s={sym}&i=d", timeout=15)
        if r.status_code != 200:
            return None
        df = pd.read_csv(io.StringIO(r.text))
        if df.empty or "Close" not in df.columns:
            return None
        val = float(df["Close"].iloc[-1])
        return val if np.isfinite(val) else None
    except Exception:
        return None


# ── Source 1: Yahoo Finance enhanced — analyst data, news, fundamentals ───────
def fetch_extras(ticker: str) -> dict:
    out: dict = {}
    try:
        t    = yf.Ticker(ticker)
        info = t.info or {}

        # Analyst price targets
        out["analyst_target_mean"] = _clean(info.get("targetMeanPrice"))
        out["analyst_target_high"] = _clean(info.get("targetHighPrice"))
        out["analyst_target_low"]  = _clean(info.get("targetLowPrice"))
        out["analyst_count"]       = info.get("numberOfAnalystOpinions")
        out["recommendation_key"]  = info.get("recommendationKey")

        # Valuation & growth
        out["beta"]            = _clean(info.get("beta"))
        out["forward_pe"]      = _clean(info.get("forwardPE"))
        out["trailing_pe"]     = _clean(info.get("trailingPE"))
        out["price_to_book"]   = _clean(info.get("priceToBook"))
        out["dividend_yield"]  = _clean(info.get("dividendYield"))
        out["revenue_growth"]  = _clean(info.get("revenueGrowth"))
        out["earnings_growth"] = _clean(info.get("earningsGrowth"))
        out["roe"]             = _clean(info.get("returnOnEquity"))
        out["debt_to_equity"]  = _clean(info.get("debtToEquity"))
        out["short_ratio"]     = _clean(info.get("shortRatio"))

        # Analyst buy/hold/sell breakdown (most recent period)
        try:
            rec_df = t.recommendations_summary
            if rec_df is not None and not rec_df.empty:
                row = rec_df.iloc[0]
                out["analyst_breakdown"] = {
                    "strong_buy":  int(row.get("strongBuy",  0)),
                    "buy":         int(row.get("buy",        0)),
                    "hold":        int(row.get("hold",       0)),
                    "sell":        int(row.get("sell",       0)),
                    "strong_sell": int(row.get("strongSell", 0)),
                }
        except Exception:
            pass

        # News headlines — top 5, from Yahoo Finance news API
        try:
            raw = t.news or []
            headlines = []
            for n in raw[:5]:
                # yfinance ≥0.2.38 wraps headlines under content{}
                content = n.get("content", {}) or {}
                title  = content.get("title")   or n.get("title",     "")
                pub    = (content.get("provider", {}) or {}).get("displayName", "") or n.get("publisher", "")
                link   = (content.get("canonicalUrl", {}) or {}).get("url", "")     or n.get("link",      "")
                ts     = content.get("pubDate",   "") or str(n.get("providerPublishTime", ""))
                if title:
                    headlines.append({"title": title, "publisher": pub, "link": link, "time": ts})
            out["news"] = headlines
        except Exception:
            out["news"] = []

        # Earnings date
        try:
            cal = t.calendar
            if cal is not None:
                ed = None
                if isinstance(cal, dict):
                    dates = cal.get("Earnings Date")
                    if isinstance(dates, list) and dates:
                        ed = dates[0]
                    elif dates:
                        ed = dates
                elif hasattr(cal, "columns") and "Earnings Date" in cal.columns:
                    ed = cal["Earnings Date"].iloc[0]
                elif hasattr(cal, "index") and "Earnings Date" in cal.index:
                    ed = cal.loc["Earnings Date"].iloc[0]
                if ed is not None:
                    out["earnings_date"] = str(ed)[:10]
        except Exception:
            pass

        # Dividend details
        try:
            out["annual_dividend"] = _clean(info.get("dividendRate"))
            ex_div = info.get("exDividendDate")
            if ex_div:
                from datetime import datetime as _dt, timezone as _tz
                out["ex_dividend_date"] = _dt.fromtimestamp(int(ex_div), tz=_tz.utc).strftime("%Y-%m-%d")
        except Exception:
            pass

    except Exception as exc:
        print(f"  extras {ticker}: {exc}")
    return out


# ── Main fetch loop ───────────────────────────────────────────────────────────
def load_previous_recommendations() -> dict:
    """Read existing data.json and return {ticker: {recommendation, generated}}."""
    try:
        with open("docs/data.json") as f:
            prev = json.load(f)
        return {
            h["ticker"]: {
                "recommendation": h.get("recommendation"),
                "generated": prev.get("generated"),
            }
            for h in prev.get("holdings", [])
            if h.get("recommendation")
        }
    except Exception:
        return {}


def fetch_and_analyse():
    output = []
    errors = []

    prev_recs = load_previous_recommendations()
    if prev_recs:
        print(f"Loaded previous recommendations for {len(prev_recs)} holdings.")

    print("Fetching macro indicators (Yahoo Finance)...")
    macro = fetch_macro()
    for k, v in macro.items():
        chg = v.get("change_pct")
        sign = "+" if (chg or 0) >= 0 else ""
        print(f"  {k}: {v.get('value')}  ({sign}{chg}%)")

    print("\nFetching holdings...")
    for holding in HOLDINGS:
        ticker = holding["ticker"]
        try:
            # Primary: Yahoo Finance price history
            hist = yf.Ticker(ticker).history(period="1y")
            if hist is None or len(hist) < 30:
                errors.append(f"{ticker}: insufficient data")
                continue

            result = analyse(hist)
            info = {}
            try:
                info = yf.Ticker(ticker).info or {}
            except Exception:
                pass

            commentary = _fund_manager_commentary(holding, result, info)

            # 30-day closing price history for portfolio chart
            price_history = []
            for idx, row in hist.tail(30).iterrows():
                c = float(row["Close"])
                if not np.isfinite(c):
                    continue
                d_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                price_history.append({"d": d_str, "c": round(c, 4)})

            # Enhanced: Yahoo Finance analyst + news + fundamentals
            extras = fetch_extras(ticker)

            # Cross-check: Stooq independent price
            stooq_price    = fetch_stooq_price(ticker)
            stooq_verified = None
            if stooq_price and result.get("price"):
                diff_pct = abs(stooq_price - result["price"]) / result["price"] * 100
                stooq_verified = diff_pct < 2.0

            clean = {k: _clean(v) for k, v in result.items()}

            prev = prev_recs.get(ticker, {})
            prev_rec = prev.get("recommendation")
            prev_generated = prev.get("generated")

            output.append({
                "ticker":                  holding["ticker"],
                "name":                    holding["name"],
                "type":                    holding["type"],
                "sector":                  holding["sector"],
                **clean,
                "commentary":              commentary,
                "price_history":           price_history,
                **extras,
                "stooq_price":             stooq_price,
                "stooq_verified":          stooq_verified,
                "previous_recommendation": prev_rec,
                "previous_generated":      prev_generated,
            })

            sv = "ok" if stooq_verified else ("diff" if stooq_price else "n/a")
            print(f"  OK {ticker}  stooq={sv}  news={len(extras.get('news', []))}")

        except Exception as exc:
            errors.append(f"{ticker}: {exc}")
            print(f"  FAIL {ticker}: {exc}")

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "sources": [
            "Yahoo Finance — OHLCV price history (1 year)",
            "Yahoo Finance — fundamentals: P/E, beta, P/B, dividend yield, ROE, D/E, short ratio",
            "Yahoo Finance — analyst consensus: price targets + buy/hold/sell breakdown",
            "Yahoo Finance — news headlines (top 5 per holding)",
            "Yahoo Finance — macro: VIX, S&P 500, FTSE 100, Gold, GBP/USD, US 10Y",
            "Stooq.com — independent price cross-validation",
        ],
        "holdings": output,
        "macro":    macro,
        "errors":   errors,
    }

    # Serialize with NaN/Infinity replaced by null (standard JSON does not allow them)
    import re as _re
    raw = json.dumps(payload, indent=2, default=str, allow_nan=True)
    raw = _re.sub(r'\bNaN\b', 'null', raw)
    raw = _re.sub(r'\bInfinity\b', 'null', raw)
    raw = _re.sub(r'\b-Infinity\b', 'null', raw)
    with open("docs/data.json", "w") as f:
        f.write(raw)

    print(f"\nWrote docs/data.json — {len(output)} holdings, {len(errors)} errors")
    return len(output) > 0


if __name__ == "__main__":
    sys.exit(0 if fetch_and_analyse() else 1)
