"""Flask web app for the investment tracker."""

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, render_template_string

from analysis import analyse
from tracker import HOLDINGS, _fetch_history, _fetch_info, _fund_manager_commentary

app = Flask(__name__)

# ── In-memory cache ───────────────────────────────────────────────────────────
_cache: dict = {"data": [], "last_updated": None, "status": "idle"}
_lock = threading.Lock()

REFRESH_INTERVAL = 900  # seconds (15 min)


def _run_analysis_background():
    """Fetch and analyse all holdings; update cache."""
    with _lock:
        _cache["status"] = "refreshing"

    results = []
    for holding in HOLDINGS:
        ticker = holding["ticker"]
        try:
            hist = _fetch_history(ticker)
            if hist is None or len(hist) < 30:
                continue
            result = analyse(hist)
            info = _fetch_info(ticker)
            commentary = _fund_manager_commentary(holding, result, info)
            # Sanitise for JSON
            for k, v in result.items():
                if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    result[k] = None
            results.append({
                "ticker": holding["ticker"],
                "name": holding["name"],
                "type": holding["type"],
                "sector": holding["sector"],
                **result,
                "commentary": commentary,
            })
        except Exception as e:
            app.logger.warning(f"Error processing {ticker}: {e}")

    with _lock:
        _cache["data"] = results
        _cache["last_updated"] = datetime.now().isoformat()
        _cache["status"] = "ready"


def _auto_refresh():
    """Background thread: refresh data every REFRESH_INTERVAL seconds."""
    while True:
        _run_analysis_background()
        time.sleep(REFRESH_INTERVAL)


# Start background refresh thread
_thread = threading.Thread(target=_auto_refresh, daemon=True)
_thread.start()

# ── HTML template ─────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Portfolio Tracker</title>
<style>
  :root {
    --bg: #0a0f1e;
    --surface: #111827;
    --surface2: #1a2235;
    --border: #1f2d45;
    --text: #e2e8f0;
    --muted: #64748b;
    --green: #22c55e;
    --red: #ef4444;
    --yellow: #f59e0b;
    --blue: #38bdf8;
    --accent: #6366f1;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { font-size: 16px; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    min-height: 100vh;
    padding-bottom: 40px;
  }

  /* ── Header ── */
  header {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
    border-bottom: 1px solid var(--border);
    padding: 16px 20px 12px;
    position: sticky; top: 0; z-index: 100;
  }
  .header-top { display: flex; align-items: center; justify-content: space-between; }
  .logo { font-size: 1.1rem; font-weight: 700; color: var(--blue); letter-spacing: -0.3px; }
  .logo span { color: var(--accent); }
  .refresh-btn {
    background: var(--accent); color: #fff; border: none; border-radius: 8px;
    padding: 7px 14px; font-size: 0.8rem; font-weight: 600; cursor: pointer;
    display: flex; align-items: center; gap: 6px; transition: opacity 0.2s;
  }
  .refresh-btn:disabled { opacity: 0.5; cursor: default; }
  .status-bar {
    margin-top: 8px; font-size: 0.72rem; color: var(--muted);
    display: flex; align-items: center; gap: 8px;
  }
  .status-dot {
    width: 7px; height: 7px; border-radius: 50%; background: var(--muted);
    flex-shrink: 0;
  }
  .status-dot.ready { background: var(--green); }
  .status-dot.refreshing { background: var(--yellow); animation: pulse 1s infinite; }

  /* ── Summary strip ── */
  .summary-strip {
    display: flex; gap: 10px; overflow-x: auto; padding: 14px 16px 4px;
    scrollbar-width: none;
  }
  .summary-strip::-webkit-scrollbar { display: none; }
  .strip-card {
    flex-shrink: 0; background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 10px 14px; min-width: 90px; text-align: center;
  }
  .strip-card .s-label { font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
  .strip-card .s-val { font-size: 1.15rem; font-weight: 700; margin-top: 2px; }

  /* ── Filter tabs ── */
  .filter-tabs {
    display: flex; gap: 8px; padding: 12px 16px 0;
    overflow-x: auto; scrollbar-width: none;
  }
  .filter-tabs::-webkit-scrollbar { display: none; }
  .tab {
    flex-shrink: 0; background: var(--surface); border: 1px solid var(--border);
    border-radius: 20px; padding: 5px 14px; font-size: 0.78rem; font-weight: 500;
    color: var(--muted); cursor: pointer; transition: all 0.15s;
  }
  .tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }

  /* ── Cards grid ── */
  .cards { padding: 14px 12px; display: flex; flex-direction: column; gap: 12px; }

  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; overflow: hidden; cursor: pointer;
    transition: transform 0.15s, border-color 0.15s;
  }
  .card:active { transform: scale(0.985); }
  .card.buy  { border-left: 3px solid var(--green); }
  .card.hold { border-left: 3px solid var(--yellow); }
  .card.sell { border-left: 3px solid var(--red); }

  .card-top { padding: 14px 16px 10px; display: flex; align-items: flex-start; justify-content: space-between; }
  .card-left {}
  .card-ticker { font-size: 0.8rem; font-weight: 700; color: var(--muted); letter-spacing: 0.5px; }
  .card-name { font-size: 1rem; font-weight: 700; color: var(--text); margin-top: 1px; }
  .card-sector { font-size: 0.72rem; color: var(--muted); margin-top: 2px; }

  .card-right { text-align: right; }
  .card-price { font-size: 1.1rem; font-weight: 700; }
  .card-day { font-size: 0.85rem; font-weight: 600; margin-top: 2px; }

  .signal-badge {
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.5px; margin-top: 6px;
  }
  .signal-badge.buy  { background: rgba(34,197,94,0.15); color: var(--green); }
  .signal-badge.hold { background: rgba(245,158,11,0.15); color: var(--yellow); }
  .signal-badge.sell { background: rgba(239,68,68,0.15); color: var(--red); }

  /* ── Metrics row ── */
  .metrics {
    display: flex; border-top: 1px solid var(--border);
    padding: 10px 16px;
  }
  .metric { flex: 1; text-align: center; }
  .metric:not(:last-child) { border-right: 1px solid var(--border); }
  .metric-label { font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .metric-val { font-size: 0.9rem; font-weight: 600; margin-top: 2px; }

  /* ── Expanded detail ── */
  .card-detail {
    display: none; border-top: 1px solid var(--border);
    padding: 14px 16px;
    background: var(--surface2);
  }
  .card-detail.open { display: block; }

  .detail-section { margin-bottom: 14px; }
  .detail-section:last-child { margin-bottom: 0; }
  .detail-title {
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.8px; color: var(--muted); margin-bottom: 8px;
  }

  .signals-list { list-style: none; display: flex; flex-direction: column; gap: 5px; }
  .signals-list li {
    font-size: 0.82rem; color: #94a3b8; padding-left: 14px; position: relative;
  }
  .signals-list li::before { content: "•"; position: absolute; left: 0; color: var(--accent); }

  .commentary {
    font-size: 0.85rem; line-height: 1.6; color: #94a3b8;
  }

  .stat-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
  }
  .stat-item {
    background: var(--surface); border-radius: 8px; padding: 8px 10px;
    border: 1px solid var(--border);
  }
  .stat-item .s-key { font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .stat-item .s-v { font-size: 0.92rem; font-weight: 600; margin-top: 2px; }

  .chevron {
    display: inline-block; transition: transform 0.2s; margin-left: 6px;
    color: var(--muted); font-size: 0.7rem;
  }
  .card.expanded .chevron { transform: rotate(180deg); }

  /* ── Loading overlay ── */
  .loading-overlay {
    position: fixed; inset: 0; background: var(--bg);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    z-index: 999;
  }
  .spinner {
    width: 44px; height: 44px; border: 3px solid var(--border);
    border-top-color: var(--accent); border-radius: 50%;
    animation: spin 0.8s linear infinite; margin-bottom: 16px;
  }
  .loading-text { color: var(--muted); font-size: 0.9rem; }

  /* ── Empty / error states ── */
  .empty { text-align: center; padding: 48px 24px; color: var(--muted); font-size: 0.9rem; }

  /* ── Utilities ── */
  .green { color: var(--green); }
  .red   { color: var(--red); }
  .yellow{ color: var(--yellow); }

  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

  @media (min-width: 600px) {
    .cards { max-width: 680px; margin: 0 auto; }
    .summary-strip { justify-content: center; }
  }
</style>
</head>
<body>

<div id="loading-overlay" class="loading-overlay">
  <div class="spinner"></div>
  <div class="loading-text" id="loading-text">Loading market data…</div>
</div>

<header>
  <div class="header-top">
    <div class="logo">Portfolio<span>Tracker</span></div>
    <button class="refresh-btn" id="refresh-btn" onclick="refresh()">
      <span>↻</span> Refresh
    </button>
  </div>
  <div class="status-bar">
    <div class="status-dot" id="status-dot"></div>
    <span id="status-text">Loading…</span>
  </div>
</header>

<div id="summary-strip" class="summary-strip"></div>

<div class="filter-tabs" id="filter-tabs">
  <div class="tab active" onclick="setFilter('all', this)">All</div>
  <div class="tab" onclick="setFilter('buy', this)">🟢 Buy</div>
  <div class="tab" onclick="setFilter('hold', this)">🟡 Hold</div>
  <div class="tab" onclick="setFilter('sell', this)">🔴 Sell</div>
  <div class="tab" onclick="setFilter('equity', this)">Equities</div>
  <div class="tab" onclick="setFilter('etf', this)">ETFs</div>
</div>

<div class="cards" id="cards"></div>

<script>
let allData = [];
let currentFilter = 'all';

function pct(v) {
  if (v == null) return '—';
  const sign = v >= 0 ? '+' : '';
  return sign + v.toFixed(2) + '%';
}
function pctClass(v) {
  if (v == null) return '';
  return v > 0 ? 'green' : v < 0 ? 'red' : '';
}
function fmt(v, decimals=2) {
  if (v == null) return '—';
  return v.toFixed(decimals);
}

async function fetchData() {
  const res = await fetch('/api/data');
  const json = await res.json();
  return json;
}

async function load() {
  const overlay = document.getElementById('loading-overlay');
  const loadingText = document.getElementById('loading-text');

  try {
    let state = await fetch('/api/status').then(r=>r.json());

    if (state.status === 'refreshing' || state.status === 'idle') {
      loadingText.textContent = 'Fetching live market data… (this takes ~30s)';
      // Poll until ready
      while (true) {
        await new Promise(r => setTimeout(r, 2000));
        state = await fetch('/api/status').then(r=>r.json());
        if (state.status === 'ready') break;
      }
    }

    const payload = await fetchData();
    allData = payload.data;
    renderSummary();
    renderCards();
    updateStatus(payload.last_updated);
    overlay.style.display = 'none';
  } catch(e) {
    loadingText.textContent = 'Error loading data. Retrying…';
    setTimeout(load, 3000);
  }
}

async function refresh() {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true;
  btn.textContent = '↻ Refreshing…';
  setStatusRefreshing();

  await fetch('/api/refresh', { method: 'POST' });

  // Poll until done
  while (true) {
    await new Promise(r => setTimeout(r, 2000));
    const s = await fetch('/api/status').then(r=>r.json());
    if (s.status === 'ready') break;
  }

  const payload = await fetchData();
  allData = payload.data;
  renderSummary();
  renderCards();
  updateStatus(payload.last_updated);
  btn.disabled = false;
  btn.innerHTML = '<span>↻</span> Refresh';
}

function updateStatus(ts) {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  dot.className = 'status-dot ready';
  if (ts) {
    const d = new Date(ts);
    text.textContent = 'Updated ' + d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
  }
}

function setStatusRefreshing() {
  document.getElementById('status-dot').className = 'status-dot refreshing';
  document.getElementById('status-text').textContent = 'Refreshing…';
}

function renderSummary() {
  const buys  = allData.filter(d => d.recommendation === 'BUY').length;
  const holds = allData.filter(d => d.recommendation === 'HOLD').length;
  const sells = allData.filter(d => d.recommendation === 'SELL').length;
  const winners = allData.filter(d => d.day_change_pct > 0).length;

  const strip = document.getElementById('summary-strip');
  strip.innerHTML = `
    <div class="strip-card">
      <div class="s-label">Holdings</div>
      <div class="s-val">${allData.length}</div>
    </div>
    <div class="strip-card">
      <div class="s-label">Buy</div>
      <div class="s-val green">${buys}</div>
    </div>
    <div class="strip-card">
      <div class="s-label">Hold</div>
      <div class="s-val yellow">${holds}</div>
    </div>
    <div class="strip-card">
      <div class="s-label">Sell</div>
      <div class="s-val red">${sells}</div>
    </div>
    <div class="strip-card">
      <div class="s-label">Up today</div>
      <div class="s-val green">${winners}</div>
    </div>
  `;
}

function setFilter(f, el) {
  currentFilter = f;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  renderCards();
}

function filtered() {
  if (currentFilter === 'all') return allData;
  if (currentFilter === 'buy')  return allData.filter(d => d.recommendation === 'BUY');
  if (currentFilter === 'hold') return allData.filter(d => d.recommendation === 'HOLD');
  if (currentFilter === 'sell') return allData.filter(d => d.recommendation === 'SELL');
  if (currentFilter === 'equity') return allData.filter(d => d.type === 'equity');
  if (currentFilter === 'etf')  return allData.filter(d => d.type === 'etf' || d.type === 'etc');
  return allData;
}

function renderCards() {
  const container = document.getElementById('cards');
  const items = filtered();
  if (!items.length) {
    container.innerHTML = '<div class="empty">No holdings match this filter.</div>';
    return;
  }

  container.innerHTML = items.map((d, i) => {
    const rec = d.recommendation.toLowerCase();
    const dayClass = pctClass(d.day_change_pct);
    const signals = (d.reasons || []).map(r => `<li>${r}</li>`).join('');
    const stats = `
      <div class="stat-grid">
        <div class="stat-item"><div class="s-key">RSI</div><div class="s-v">${d.rsi ? d.rsi.toFixed(0) : '—'}</div></div>
        <div class="stat-item"><div class="s-key">ATR %</div><div class="s-v">${d.atr_pct ? d.atr_pct.toFixed(1)+'%' : '—'}</div></div>
        <div class="stat-item"><div class="s-key">SMA 50</div><div class="s-v">${fmt(d.sma_50)}</div></div>
        <div class="stat-item"><div class="s-key">SMA 200</div><div class="s-v">${fmt(d.sma_200)}</div></div>
        <div class="stat-item"><div class="s-key">52W High</div><div class="s-v">${fmt(d.high_52w)}</div></div>
        <div class="stat-item"><div class="s-key">52W Low</div><div class="s-v">${fmt(d.low_52w)}</div></div>
      </div>`;

    return `
    <div class="card ${rec}" id="card-${i}" onclick="toggleCard(${i})">
      <div class="card-top">
        <div class="card-left">
          <div class="card-ticker">${d.ticker} <span class="chevron">▼</span></div>
          <div class="card-name">${d.name}</div>
          <div class="card-sector">${d.sector} · ${d.type.toUpperCase()}</div>
          <div class="signal-badge ${rec}">${d.recommendation}</div>
        </div>
        <div class="card-right">
          <div class="card-price">${d.price < 100 ? d.price.toFixed(2) : d.price.toFixed(1)}</div>
          <div class="card-day ${dayClass}">${pct(d.day_change_pct)}</div>
        </div>
      </div>
      <div class="metrics">
        <div class="metric">
          <div class="metric-label">Week</div>
          <div class="metric-val ${pctClass(d.week_change_pct)}">${pct(d.week_change_pct)}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Month</div>
          <div class="metric-val ${pctClass(d.month_change_pct)}">${pct(d.month_change_pct)}</div>
        </div>
        <div class="metric">
          <div class="metric-label">52W Δ</div>
          <div class="metric-val ${pctClass(d.pct_from_52w_high * 100)}">${pct(d.pct_from_52w_high ? d.pct_from_52w_high * 100 : null)}</div>
        </div>
        <div class="metric">
          <div class="metric-label">RSI</div>
          <div class="metric-val">${d.rsi ? d.rsi.toFixed(0) : '—'}</div>
        </div>
      </div>
      <div class="card-detail" id="detail-${i}">
        <div class="detail-section">
          <div class="detail-title">Technical Signals</div>
          <ul class="signals-list">${signals}</ul>
        </div>
        <div class="detail-section">
          <div class="detail-title">Key Levels</div>
          ${stats}
        </div>
        <div class="detail-section">
          <div class="detail-title">Fund Manager View</div>
          <div class="commentary">${d.commentary}</div>
        </div>
      </div>
    </div>`;
  }).join('');
}

function toggleCard(i) {
  const card = document.getElementById('card-' + i);
  const detail = document.getElementById('detail-' + i);
  card.classList.toggle('expanded');
  detail.classList.toggle('open');
}

load();

// Auto-refresh every 15 minutes
setInterval(async () => {
  try {
    const payload = await fetchData();
    if (payload.data && payload.data.length) {
      allData = payload.data;
      renderSummary();
      renderCards();
      updateStatus(payload.last_updated);
    }
  } catch(e) {}
}, 15 * 60 * 1000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/status")
def api_status():
    with _lock:
        return jsonify({"status": _cache["status"], "last_updated": _cache["last_updated"]})


@app.route("/api/data")
def api_data():
    with _lock:
        return jsonify({
            "data": _cache["data"],
            "last_updated": _cache["last_updated"],
            "status": _cache["status"],
        })


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    t = threading.Thread(target=_run_analysis_background, daemon=True)
    t.start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
