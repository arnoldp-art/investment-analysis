#!/usr/bin/env python3
"""
Fetch market data and technical analysis for all holdings.
Writes docs/data.json — consumed by the static GitHub Pages frontend.
"""

import json
import sys
from datetime import datetime, timezone

import numpy as np
import yfinance as yf

sys.path.insert(0, ".")
from analysis import analyse
from tracker import HOLDINGS, _fund_manager_commentary


def fetch_and_analyse():
    output = []
    errors = []

    for holding in HOLDINGS:
        ticker = holding["ticker"]
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")
            if hist is None or len(hist) < 30:
                errors.append(f"{ticker}: insufficient data")
                continue

            result = analyse(hist)
            info = {}
            try:
                info = t.info or {}
            except Exception:
                pass

            commentary = _fund_manager_commentary(holding, result, info)

            # Sanitise NaN/Inf
            clean = {}
            for k, v in result.items():
                if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    clean[k] = None
                else:
                    clean[k] = v

            output.append({
                "ticker": holding["ticker"],
                "name": holding["name"],
                "type": holding["type"],
                "sector": holding["sector"],
                **clean,
                "commentary": commentary,
            })
            print(f"  ✓ {ticker}")
        except Exception as e:
            errors.append(f"{ticker}: {e}")
            print(f"  ✗ {ticker}: {e}")

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "holdings": output,
        "errors": errors,
    }

    with open("docs/data.json", "w") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"\nWrote docs/data.json — {len(output)} holdings, {len(errors)} errors")
    return len(output) > 0


if __name__ == "__main__":
    ok = fetch_and_analyse()
    sys.exit(0 if ok else 1)
