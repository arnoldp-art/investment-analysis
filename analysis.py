"""Technical analysis engine for investment tracking."""

import numpy as np
import pandas as pd


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(series: pd.Series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def analyse(hist: pd.DataFrame) -> dict:
    """Run all technical indicators and produce a scored signal."""
    # Drop any trailing rows where Close is NaN (e.g. partial pre-market bar)
    hist = hist[hist["Close"].notna()]
    close = hist["Close"].squeeze()
    high = hist["High"].squeeze()
    low = hist["Low"].squeeze()
    volume = hist["Volume"].squeeze()

    signals = []
    reasons = []

    # ── Moving Averages ──────────────────────────────────────────────────────
    sma_50 = close.rolling(50).mean()
    sma_200 = close.rolling(200).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()

    price = close.iloc[-1]
    s50 = sma_50.iloc[-1]
    s200 = sma_200.iloc[-1]
    e20 = ema_20.iloc[-1]

    if not (np.isnan(s50) or np.isnan(s200)):
        if s50 > s200:
            signals.append(1)
            reasons.append("Golden Cross (SMA50 > SMA200) — bullish trend structure")
        else:
            signals.append(-1)
            reasons.append("Death Cross (SMA50 < SMA200) — bearish trend structure")

    if not np.isnan(e20):
        if price > e20:
            signals.append(1)
            reasons.append(f"Price above EMA20 ({e20:.2f}) — short-term momentum positive")
        else:
            signals.append(-1)
            reasons.append(f"Price below EMA20 ({e20:.2f}) — short-term momentum negative")

    # ── RSI ──────────────────────────────────────────────────────────────────
    rsi = compute_rsi(close)
    rsi_val = rsi.iloc[-1]
    if not np.isnan(rsi_val):
        if rsi_val < 30:
            signals.append(2)
            reasons.append(f"RSI oversold at {rsi_val:.1f} — potential reversal opportunity")
        elif rsi_val > 70:
            signals.append(-2)
            reasons.append(f"RSI overbought at {rsi_val:.1f} — risk of near-term pullback")
        elif rsi_val < 45:
            signals.append(-1)
            reasons.append(f"RSI weakening at {rsi_val:.1f}")
        elif rsi_val > 55:
            signals.append(1)
            reasons.append(f"RSI strengthening at {rsi_val:.1f}")
        else:
            signals.append(0)
            reasons.append(f"RSI neutral at {rsi_val:.1f}")

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_line, signal_line, histogram = compute_macd(close)
    macd_val = macd_line.iloc[-1]
    sig_val = signal_line.iloc[-1]
    hist_val = histogram.iloc[-1]
    prev_hist = histogram.iloc[-2] if len(histogram) > 1 else hist_val

    if not (np.isnan(macd_val) or np.isnan(sig_val)):
        if macd_val > sig_val:
            signals.append(1)
            reasons.append("MACD above signal line — bullish momentum")
        else:
            signals.append(-1)
            reasons.append("MACD below signal line — bearish momentum")

        if not np.isnan(hist_val) and not np.isnan(prev_hist):
            if hist_val > prev_hist and hist_val > 0:
                reasons.append("MACD histogram expanding positively")
            elif hist_val < prev_hist and hist_val < 0:
                reasons.append("MACD histogram expanding negatively")

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_upper, bb_mid, bb_lower = compute_bollinger_bands(close)
    bb_u = bb_upper.iloc[-1]
    bb_l = bb_lower.iloc[-1]
    bb_m = bb_mid.iloc[-1]

    if not (np.isnan(bb_u) or np.isnan(bb_l)):
        bb_pct = (price - bb_l) / (bb_u - bb_l) if bb_u != bb_l else 0.5
        if price <= bb_l:
            signals.append(2)
            reasons.append("Price at/below lower Bollinger Band — mean reversion candidate")
        elif price >= bb_u:
            signals.append(-1)
            reasons.append("Price at/above upper Bollinger Band — stretched, watch for reversal")
        else:
            bb_width = (bb_u - bb_l) / bb_m if bb_m else 0
            if bb_width < 0.05:
                reasons.append("Bollinger Band squeeze — volatility breakout likely imminent")

    # ── Volume Trend ─────────────────────────────────────────────────────────
    if len(volume) >= 20:
        avg_vol_20 = volume.iloc[-20:].mean()
        recent_vol = volume.iloc[-5:].mean()
        price_change = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]

        if recent_vol > avg_vol_20 * 1.3:
            if price_change > 0:
                signals.append(1)
                reasons.append("Above-average volume confirming upward price move")
            else:
                signals.append(-1)
                reasons.append("Above-average volume on price decline — distribution signal")

    # ── 52-Week Relative Position ────────────────────────────────────────────
    if len(close) >= 252:
        high_52 = close.iloc[-252:].max()
        low_52 = close.iloc[-252:].min()
        pct_from_high = (price - high_52) / high_52
        pct_of_range = (price - low_52) / (high_52 - low_52) if high_52 != low_52 else 0.5

        if pct_from_high < -0.30:
            signals.append(1)
            reasons.append(f"Down {abs(pct_from_high)*100:.0f}% from 52-week high — deep value zone")
        elif pct_from_high > -0.05:
            reasons.append("Near 52-week high — strong momentum but limited upside buffer")
    else:
        high_52 = close.max()
        low_52 = close.min()
        pct_from_high = (price - high_52) / high_52
        pct_of_range = 0.5

    # ── Momentum (rate of change) ─────────────────────────────────────────────
    if len(close) >= 20:
        roc_20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]
        if roc_20 > 0.10:
            signals.append(1)
            reasons.append(f"Strong 20-day momentum: +{roc_20*100:.1f}%")
        elif roc_20 < -0.10:
            signals.append(-1)
            reasons.append(f"Weak 20-day momentum: {roc_20*100:.1f}%")

    # ── Score → Recommendation ────────────────────────────────────────────────
    score = sum(signals) if signals else 0
    n = len([s for s in signals if s != 0]) or 1
    norm = score / n

    if norm >= 0.5:
        recommendation = "BUY"
    elif norm <= -0.5:
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    # ── Price metrics ─────────────────────────────────────────────────────────
    prev_close = close.iloc[-2] if len(close) > 1 else price
    day_change_pct = (price - prev_close) / prev_close * 100

    week_close = close.iloc[-5] if len(close) >= 5 else close.iloc[0]
    week_change_pct = (price - week_close) / week_close * 100

    month_close = close.iloc[-21] if len(close) >= 21 else close.iloc[0]
    month_change_pct = (price - month_close) / month_close * 100

    atr = compute_atr(high, low, close)
    atr_val = atr.iloc[-1]
    atr_pct = atr_val / price * 100 if not np.isnan(atr_val) else None

    return {
        "price": price,
        "day_change_pct": day_change_pct,
        "week_change_pct": week_change_pct,
        "month_change_pct": month_change_pct,
        "recommendation": recommendation,
        "score": norm,
        "reasons": reasons,
        "rsi": rsi_val,
        "macd": macd_val,
        "signal_line": sig_val,
        "sma_50": s50,
        "sma_200": s200,
        "high_52w": high_52,
        "low_52w": low_52,
        "pct_from_52w_high": pct_from_high,
        "atr_pct": atr_pct,
    }
