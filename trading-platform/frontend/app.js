// ── State ───────────────────────────────────────────────────────────────────
const API = '';
let portfolioChart = null;
let refreshInterval = null;

// ── Navigation ──────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const page = link.dataset.page;
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    link.classList.add('active');
    document.getElementById(`page-${page}`).classList.add('active');
    onPageLoad(page);
  });
});

function onPageLoad(page) {
  if (page === 'dashboard') { loadDashboard(); }
  if (page === 'portfolio') { loadPortfolio(); }
  if (page === 'research') { loadAnalyses(); }
  if (page === 'watchlist') { loadWatchlist(); }
  if (page === 'history') { loadTrades(); }
  if (page === 'settings') { loadSettings(); }
  if (page === 'trade') { loadOpenOrders(); }
}

// ── Helpers ─────────────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  const r = await fetch(API + path, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r.json();
}

function fmt(n, dec = 2) {
  if (n == null || isNaN(n)) return '--';
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtMoney(n) {
  if (n == null || isNaN(n)) return '--';
  return '$' + fmt(n);
}

function fmtPct(n) {
  if (n == null || isNaN(n)) return '--';
  const sign = n >= 0 ? '+' : '';
  return `${sign}${fmt(n)}%`;
}

function colorClass(n) {
  if (n == null || isNaN(n)) return '';
  return n >= 0 ? 'green' : 'red';
}

function actionBadge(action) {
  const a = (action || '').toLowerCase();
  return `<span class="action-badge ${a}">${action}</span>`;
}

function confBar(c) {
  const cls = c >= 70 ? 'high' : c >= 50 ? 'med' : 'low';
  return `<div class="confidence-bar">
    <span>${c}%</span>
    <div class="conf-bar-track"><div class="conf-bar-fill ${cls}" style="width:${c}%"></div></div>
  </div>`;
}

function toast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type}`;
  setTimeout(() => t.classList.add('hidden'), 3500);
}

function timeAgo(isoStr) {
  if (!isoStr) return '--';
  const d = new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z'));
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return d.toLocaleDateString();
}

// ── Dashboard ────────────────────────────────────────────────────────────────
async function loadDashboard() {
  await Promise.all([loadAccount(), loadStatus(), loadPortfolioChart(), loadSentiment()]);
}

async function loadAccount() {
  try {
    const data = await api('/api/account');
    document.getElementById('total-value').textContent = fmtMoney(data.total_value);
    const pnl = data.total_pnl;
    const pnlPct = data.total_pnl_pct;
    const pnlEl = document.getElementById('total-pnl');
    pnlEl.textContent = `${fmtMoney(pnl)} (${fmtPct(pnlPct)})`;
    pnlEl.className = `stat-sub ${colorClass(pnl)}`;

    document.getElementById('cash-value').textContent = fmtMoney(data.cash);
    const cashPct = data.total_value > 0 ? (data.cash / data.total_value * 100) : 0;
    document.getElementById('cash-pct').textContent = `${fmt(cashPct)}% of portfolio`;

    document.getElementById('invested-value').textContent = fmtMoney(data.invested);
    document.getElementById('position-count').textContent = `${data.position_count} positions`;

    // Mode badge
    const mode = await api('/api/settings');
    const badge = document.getElementById('mode-badge');
    badge.textContent = mode.t212_mode.toUpperCase();
    badge.className = `badge ${mode.t212_mode}`;
  } catch (e) {
    document.getElementById('total-value').textContent = 'API Error';
    document.getElementById('total-pnl').textContent = e.message;
  }
}

async function loadSentiment() {
  try {
    const s = await api('/api/sentiment');
    const sentEl = document.getElementById('sentiment-value');
    const scoreEl = document.getElementById('sentiment-score');
    const label = s.sentiment?.replace(/_/g, ' ') || '--';
    sentEl.textContent = label.charAt(0).toUpperCase() + label.slice(1);
    const score = s.score || 0;
    sentEl.className = `stat-value ${score > 0 ? 'green' : score < 0 ? 'red' : ''}`;
    scoreEl.textContent = `Score: ${score > 0 ? '+' : ''}${score}`;
  } catch(e) {
    document.getElementById('sentiment-value').textContent = 'Unavailable';
  }
}

async function loadPortfolioChart() {
  try {
    const history = await api('/api/portfolio/history?limit=288');
    const canvas = document.getElementById('portfolio-chart');
    const ctx = canvas.getContext('2d');

    if (portfolioChart) portfolioChart.destroy();

    if (!history || history.length === 0) {
      ctx.fillStyle = '#6b7280';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('No history yet. Run analysis to start tracking.', canvas.width / 2, 100);
      return;
    }

    portfolioChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: history.map(h => {
          const d = new Date(h.snapshot_at);
          return `${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`;
        }),
        datasets: [{
          label: 'Portfolio Value',
          data: history.map(h => h.total_value),
          borderColor: '#6366f1',
          backgroundColor: 'rgba(99,102,241,0.08)',
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          tension: 0.4,
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: { label: ctx => `$${fmt(ctx.raw)}` }
          }
        },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#6b7280', maxTicksLimit: 8 } },
          y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#6b7280', callback: v => `$${fmt(v, 0)}` } }
        }
      }
    });
  } catch(e) {
    console.error('Chart error', e);
  }
}

async function loadStatus() {
  try {
    const s = await api('/api/status');
    const dot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    if (s.is_running) {
      dot.className = 'status-dot running';
      statusText.textContent = 'Bot Running';
    } else {
      dot.className = 'status-dot idle';
      statusText.textContent = s.last_run ? `Last: ${timeAgo(s.last_run)}` : 'Bot Idle';
    }

    const log = document.getElementById('activity-log');
    if (s.log && s.log.length > 0) {
      log.innerHTML = s.log.slice().reverse().map(l =>
        `<div class="log-entry">${escHtml(l)}</div>`
      ).join('');
    }
  } catch(e) { /* ignore */ }
}

async function triggerAnalysis() {
  const btn = document.getElementById('run-analysis-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Running...';
  try {
    await api('/api/analyze/run', { method: 'POST' });
    toast('Analysis started in background', 'success');
    setTimeout(loadStatus, 2000);
    setTimeout(loadStatus, 8000);
    setTimeout(loadStatus, 20000);
  } catch(e) {
    toast(`Error: ${e.message}`, 'error');
  } finally {
    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = '▶ Run AI Analysis';
    }, 3000);
  }
}

async function loadPortfolioReview() {
  const el = document.getElementById('portfolio-review-content');
  el.innerHTML = '<span style="color:#6b7280">Loading AI review...</span>';
  try {
    const r = await api('/api/portfolio/review');
    const score = r.health_score || 50;
    const scoreColor = score >= 70 ? '#22c55e' : score >= 45 ? '#eab308' : '#ef4444';
    el.innerHTML = `
      <div class="health-score" style="color:${scoreColor}">${score}</div>
      <div class="health-label" style="color:${scoreColor}">${(r.overall_health || '').replace(/_/g,' ')}</div>
      <p style="font-size:13px;color:#9ca3af;margin-bottom:14px">${escHtml(r.summary || '')}</p>
      ${r.top_risks?.length ? `<div class="review-section"><h4>Risks</h4><ul class="review-list">${r.top_risks.map(x=>`<li>${escHtml(x)}</li>`).join('')}</ul></div>` : ''}
      ${r.opportunities?.length ? `<div class="review-section"><h4>Opportunities</h4><ul class="review-list">${r.opportunities.map(x=>`<li>${escHtml(x)}</li>`).join('')}</ul></div>` : ''}
      ${r.cash_deployment_advice ? `<div class="review-section"><h4>Cash Advice</h4><p style="font-size:13px;color:#9ca3af">${escHtml(r.cash_deployment_advice)}</p></div>` : ''}
    `;
  } catch(e) {
    el.innerHTML = `<span style="color:#ef4444">Error: ${escHtml(e.message)}</span>`;
  }
}

// ── Portfolio ────────────────────────────────────────────────────────────────
async function loadPortfolio() {
  const tbody = document.getElementById('portfolio-tbody');
  tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">Loading...</td></tr>';
  try {
    const positions = await api('/api/portfolio');
    if (!positions || positions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">No positions</td></tr>';
      return;
    }
    tbody.innerHTML = positions.map(p => {
      const pnl = p.ppl || 0;
      const pnlPct = p.investedValue > 0 ? pnl / p.investedValue * 100 : 0;
      return `<tr>
        <td><strong>${p.ticker}</strong></td>
        <td>${fmt(p.quantity, 4)}</td>
        <td>${fmtMoney(p.averagePrice)}</td>
        <td>${fmtMoney(p.currentPrice)}</td>
        <td>${fmtMoney(p.currentValue)}</td>
        <td class="${colorClass(pnl)}">${fmtMoney(pnl)}</td>
        <td class="${colorClass(pnlPct)}">${fmtPct(pnlPct)}</td>
        <td>
          <button class="btn btn-danger" onclick="quickSell('${p.ticker}', ${p.quantity})">Sell</button>
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 8px;margin-left:4px" onclick="analyzeFromPortfolio('${p.ticker}')">Analyze</button>
        </td>
      </tr>`;
    }).join('');
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-cell" style="color:#ef4444">${escHtml(e.message)}</td></tr>`;
  }
}

async function quickSell(ticker, qty) {
  if (!confirm(`Sell all ${qty} shares of ${ticker}?`)) return;
  try {
    await api('/api/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, action: 'SELL', quantity: qty })
    });
    toast(`Sell order placed for ${ticker}`, 'success');
    setTimeout(loadPortfolio, 1500);
  } catch(e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

function analyzeFromPortfolio(ticker) {
  document.querySelector('[data-page="research"]').click();
  setTimeout(() => {
    document.getElementById('research-ticker').value = ticker;
    runSingleAnalysis();
  }, 200);
}

// ── AI Research ──────────────────────────────────────────────────────────────
async function runSingleAnalysis() {
  const ticker = document.getElementById('research-ticker').value.trim().toUpperCase();
  if (!ticker) { toast('Enter a ticker', 'error'); return; }

  const resultEl = document.getElementById('analysis-result');
  resultEl.classList.add('hidden');
  document.getElementById('analysis-decision').innerHTML = '<span style="color:#6b7280">Analyzing...</span>';
  resultEl.classList.remove('hidden');

  try {
    const data = await api(`/api/analyze/${ticker}`, { method: 'POST' });
    renderAnalysis(data);
  } catch(e) {
    document.getElementById('analysis-decision').innerHTML = `<span style="color:#ef4444">Error: ${escHtml(e.message)}</span>`;
  }
}

function renderAnalysis({ ticker, market_data: md, analysis: a }) {
  const action = a.action || 'SKIP';
  const colors = { BUY: '#22c55e', SELL: '#ef4444', HOLD: '#3b82f6', SKIP: '#6b7280' };
  const color = colors[action] || '#6b7280';

  document.getElementById('analysis-decision').innerHTML = `
    <div class="analysis-decision">
      <div>
        <div class="decision-action" style="color:${color}">${action}</div>
        <div style="color:#9ca3af;margin-top:4px">Confidence: ${confBar(a.confidence || 0)}</div>
      </div>
      <p style="font-size:13px;color:#d1d5db">${escHtml(a.reasoning || '')}</p>
      ${a.price_target ? `<div style="font-size:13px">🎯 Target: <strong>${fmtMoney(a.price_target)}</strong></div>` : ''}
      ${a.stop_loss_price ? `<div style="font-size:13px">🛡 Stop-Loss: <strong>${fmtMoney(a.stop_loss_price)}</strong></div>` : ''}
      ${a.time_horizon ? `<div style="font-size:13px">⏱ Horizon: <strong>${a.time_horizon}</strong></div>` : ''}
      ${a.key_signals?.length ? `
        <div>
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Key Signals</div>
          <div class="signal-list">${a.key_signals.map(s=>`<span class="signal-tag">${escHtml(s)}</span>`).join('')}</div>
        </div>` : ''}
      ${a.risk_factors?.length ? `
        <div>
          <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Risk Factors</div>
          <div class="signal-list">${a.risk_factors.map(r=>`<span class="risk-tag">${escHtml(r)}</span>`).join('')}</div>
        </div>` : ''}
    </div>`;

  if (md) {
    document.getElementById('analysis-market-data').innerHTML = `
      <div class="market-grid">
        ${mRow('Price', fmtMoney(md.price))}
        ${mRow('1D Change', `<span class="${colorClass(md.change_1d_pct)}">${fmtPct(md.change_1d_pct)}</span>`)}
        ${mRow('1W Change', `<span class="${colorClass(md.change_1w_pct)}">${fmtPct(md.change_1w_pct)}</span>`)}
        ${mRow('1M Change', `<span class="${colorClass(md.change_1m_pct)}">${fmtPct(md.change_1m_pct)}</span>`)}
        ${mRow('RSI (14)', md.rsi != null ? `<span class="${md.rsi > 70 ? 'red' : md.rsi < 30 ? 'green' : ''}">${fmt(md.rsi)}</span>` : '--')}
        ${mRow('Volume Ratio', `${fmt(md.volume_ratio)}x`)}
        ${mRow('MACD', md.macd_crossover || '--')}
        ${mRow('Bollinger %', md.bb_pct != null ? fmt(md.bb_pct) : '--')}
        ${mRow('Above EMA 50', md.above_ema_50 != null ? (md.above_ema_50 ? '<span class="green">Yes</span>' : '<span class="red">No</span>') : '--')}
        ${mRow('Above SMA 200', md.above_sma_200 != null ? (md.above_sma_200 ? '<span class="green">Yes</span>' : '<span class="red">No</span>') : '--')}
        ${mRow('P/E Ratio', md.pe_ratio != null ? fmt(md.pe_ratio) : '--')}
        ${mRow('Analyst Target', md.analyst_target ? fmtMoney(md.analyst_target) : '--')}
        ${mRow('52W High', fmtMoney(md['52w_high']))}
        ${mRow('52W Low', fmtMoney(md['52w_low']))}
        ${mRow('Sector', md.sector || '--')}
        ${mRow('Beta', md.beta != null ? fmt(md.beta) : '--')}
      </div>`;
  }
}

function mRow(label, value) {
  return `<div class="market-row"><label>${label}</label><span>${value}</span></div>`;
}

async function loadAnalyses() {
  const tbody = document.getElementById('analyses-tbody');
  try {
    const analyses = await api('/api/analyses?limit=20');
    if (!analyses || analyses.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">No analyses yet</td></tr>';
      return;
    }
    tbody.innerHTML = analyses.map(a => `<tr>
      <td style="color:#6b7280;white-space:nowrap">${timeAgo(a.created_at)}</td>
      <td><strong>${a.ticker}</strong></td>
      <td>${actionBadge(a.action)}</td>
      <td>${confBar(a.confidence)}</td>
      <td style="color:#9ca3af;font-size:12px;max-width:300px">${escHtml(a.reasoning || '')}</td>
    </tr>`).join('');
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-cell" style="color:#ef4444">${escHtml(e.message)}</td></tr>`;
  }
}

// ── Manual Trade ─────────────────────────────────────────────────────────────
function toggleLimitPrice() {
  const type = document.getElementById('trade-order-type').value;
  const group = document.getElementById('limit-price-group');
  group.classList.toggle('hidden', type !== 'limit');
}

async function placeTrade() {
  const ticker = document.getElementById('trade-ticker').value.trim().toUpperCase();
  const action = document.getElementById('trade-action').value;
  const quantity = parseFloat(document.getElementById('trade-quantity').value);
  const orderType = document.getElementById('trade-order-type').value;
  const limitPrice = parseFloat(document.getElementById('trade-limit-price').value) || null;

  if (!ticker || isNaN(quantity) || quantity <= 0) {
    toast('Fill in all fields', 'error'); return;
  }
  if (orderType === 'limit' && !limitPrice) {
    toast('Enter a limit price', 'error'); return;
  }

  const resultEl = document.getElementById('trade-result');
  resultEl.innerHTML = 'Placing order...';
  resultEl.className = '';
  resultEl.classList.remove('hidden');

  try {
    const order = await api('/api/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, action, quantity, order_type: orderType, limit_price: limitPrice }),
    });
    resultEl.innerHTML = `✓ Order placed: ID ${order.id || 'N/A'}`;
    resultEl.style.color = '#22c55e';
    toast(`${action} order placed for ${ticker}`, 'success');
    loadOpenOrders();
  } catch(e) {
    resultEl.innerHTML = `✗ Error: ${escHtml(e.message)}`;
    resultEl.style.color = '#ef4444';
    toast(e.message, 'error');
  }
}

async function loadOpenOrders() {
  const tbody = document.getElementById('open-orders-tbody');
  try {
    const orders = await api('/api/orders');
    if (!orders || orders.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No open orders</td></tr>';
      return;
    }
    tbody.innerHTML = orders.map(o => `<tr>
      <td style="color:#6b7280">${o.id}</td>
      <td><strong>${o.ticker}</strong></td>
      <td>${o.type || '--'}</td>
      <td>${fmt(Math.abs(o.quantity || o.filledQuantity || 0), 4)}</td>
      <td>${o.limitPrice ? fmtMoney(o.limitPrice) : 'Market'}</td>
      <td>${o.status || '--'}</td>
      <td><button class="btn btn-danger" onclick="cancelOrder(${o.id})">Cancel</button></td>
    </tr>`).join('');
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-cell" style="color:#ef4444">${escHtml(e.message)}</td></tr>`;
  }
}

async function cancelOrder(id) {
  if (!confirm('Cancel this order?')) return;
  try {
    await api(`/api/order/${id}`, { method: 'DELETE' });
    toast('Order cancelled', 'success');
    loadOpenOrders();
  } catch(e) {
    toast(`Error: ${e.message}`, 'error');
  }
}

// ── Watchlist ────────────────────────────────────────────────────────────────
async function loadWatchlist() {
  const tbody = document.getElementById('watchlist-tbody');
  tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">Loading market data...</td></tr>';

  try {
    const tickers = await api('/api/watchlist');
    if (!tickers || tickers.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">Watchlist empty</td></tr>';
      return;
    }

    // Load market data for each ticker in parallel
    const dataArr = await Promise.allSettled(tickers.map(t => api(`/api/market/${t}`)));
    const rows = tickers.map((ticker, i) => {
      const result = dataArr[i];
      const md = result.status === 'fulfilled' ? result.value : null;
      if (!md) return `<tr>
        <td><strong>${ticker}</strong></td>
        <td colspan="4" style="color:#ef4444">Data unavailable</td>
        <td><button class="btn btn-danger" onclick="removeFromWatchlist('${ticker}')">Remove</button></td>
      </tr>`;

      const macdStyle = md.macd_crossover?.includes('bullish') ? 'green' : md.macd_crossover?.includes('bearish') ? 'red' : '';
      return `<tr>
        <td>
          <strong>${ticker}</strong>
          <div style="font-size:11px;color:#6b7280">${md.sector || ''}</div>
        </td>
        <td>${fmtMoney(md.price)}</td>
        <td class="${colorClass(md.change_1d_pct)}">${fmtPct(md.change_1d_pct)}</td>
        <td class="${md.rsi > 70 ? 'red' : md.rsi < 30 ? 'green' : ''}">${fmt(md.rsi)}</td>
        <td class="${macdStyle}">${md.macd_crossover?.replace(/_/g,' ') || '--'}</td>
        <td>
          <button class="btn btn-secondary" style="font-size:11px;padding:3px 8px" onclick="analyzeWatchlist('${ticker}')">Analyze</button>
          <button class="btn btn-danger" style="margin-left:4px" onclick="removeFromWatchlist('${ticker}')">✕</button>
        </td>
      </tr>`;
    });
    tbody.innerHTML = rows.join('');
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-cell" style="color:#ef4444">${escHtml(e.message)}</td></tr>`;
  }
}

function analyzeWatchlist(ticker) {
  document.querySelector('[data-page="research"]').click();
  setTimeout(() => {
    document.getElementById('research-ticker').value = ticker;
    runSingleAnalysis();
  }, 200);
}

async function addToWatchlist() {
  const ticker = document.getElementById('add-ticker-input').value.trim().toUpperCase();
  if (!ticker) return;
  try {
    await api('/api/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker }),
    });
    document.getElementById('add-ticker-input').value = '';
    toast(`${ticker} added to watchlist`, 'success');
    loadWatchlist();
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function removeFromWatchlist(ticker) {
  try {
    await api(`/api/watchlist/${ticker}`, { method: 'DELETE' });
    toast(`${ticker} removed`, 'success');
    loadWatchlist();
  } catch(e) {
    toast(e.message, 'error');
  }
}

// ── Trade History ────────────────────────────────────────────────────────────
async function loadTrades() {
  const tbody = document.getElementById('trades-tbody');
  try {
    const trades = await api('/api/trades?limit=50');
    if (!trades || trades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No trades yet</td></tr>';
      return;
    }
    tbody.innerHTML = trades.map(t => `<tr>
      <td style="color:#6b7280;white-space:nowrap">${timeAgo(t.created_at)}</td>
      <td><strong>${t.ticker}</strong></td>
      <td>${actionBadge(t.action)}</td>
      <td>${fmt(t.quantity, 4)}</td>
      <td>${t.price ? fmtMoney(t.price) : 'Market'}</td>
      <td>${confBar(t.confidence || 0)}</td>
      <td style="color:#9ca3af;font-size:12px;max-width:280px">${escHtml(t.ai_reasoning || '')}</td>
    </tr>`).join('');
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-cell" style="color:#ef4444">${escHtml(e.message)}</td></tr>`;
  }
}

// ── Settings ─────────────────────────────────────────────────────────────────
async function loadSettings() {
  const tbody = document.getElementById('settings-tbody');
  try {
    const s = await api('/api/settings');
    const rows = [
      ['Mode', `<span class="badge ${s.t212_mode}">${s.t212_mode.toUpperCase()}</span>`],
      ['Max Position Size', `${s.max_position_pct}% of portfolio`],
      ['Analysis Interval', `${s.analysis_interval_minutes} minutes`],
      ['Max Open Positions', s.max_open_positions],
      ['Stop-Loss', `${s.stop_loss_pct}%`],
      ['Take-Profit', `${s.take_profit_pct}%`],
      ['Min AI Confidence', `${s.min_confidence}%`],
    ];
    tbody.innerHTML = rows.map(([k, v]) =>
      `<tr><td>${k}</td><td>${v}</td></tr>`
    ).join('');
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="2" style="color:#ef4444">${escHtml(e.message)}</td></tr>`;
  }
}

// ── Utils ────────────────────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Init ─────────────────────────────────────────────────────────────────────
loadDashboard();
// Auto-refresh status every 15s
setInterval(loadStatus, 15000);
