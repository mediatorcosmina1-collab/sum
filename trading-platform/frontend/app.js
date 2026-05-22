// ── Globals ───────────────────────────────────────────────────────────────────
let portfolioChart = null;
let allocationChart = null;
let growthChart = null;
let autoRefreshInterval = null;
const PALETTE = ['#6366f1','#22c55e','#ef4444','#eab308','#3b82f6','#a855f7','#f97316','#06b6d4','#ec4899','#84cc16'];

// ── Page navigation ───────────────────────────────────────────────────────────
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', () => {
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    link.classList.add('active');
    const page = link.dataset.page;
    document.getElementById('page-' + page).classList.add('active');
    if (page === 'dashboard')   { loadDashboard(); }
    if (page === 'portfolio')   { loadPortfolio(); }
    if (page === 'watchlist')   { loadWatchlist(); }
    if (page === 'history')     { loadTrades(); }
    if (page === 'performance') { loadPerformance(); }
    if (page === 'alerts')      { loadAlerts(); }
    if (page === 'chat')        { loadChatHistory(); }
    if (page === 'settings')    { loadSettings(); }
    if (page === 'research')    { loadAnalyses(); }
  });
});

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type}`;
  setTimeout(() => t.classList.add('hidden'), 3500);
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function showModal(title, body, onConfirm) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').textContent = body;
  document.getElementById('confirm-modal').classList.remove('hidden');
  document.getElementById('modal-confirm-btn').onclick = () => { closeModal(); onConfirm(); };
}
function closeModal() { document.getElementById('confirm-modal').classList.add('hidden'); }

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (v, dec=2) => v == null ? '--' : Number(v).toFixed(dec);
const fmtMoney = v => v == null ? '--' : '$' + Number(v).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
const fmtPct = v => v == null ? '--' : (v >= 0 ? '+' : '') + fmt(v) + '%';
const colorClass = v => v > 0 ? 'green' : v < 0 ? 'red' : '';

function confClass(c) { return c >= 75 ? 'high' : c >= 55 ? 'med' : 'low'; }

function confBar(c) {
  return `<div class="confidence-bar">
    <div class="conf-bar-track"><div class="conf-bar-fill ${confClass(c)}" style="width:${c}%"></div></div>
    <strong>${c}%</strong>
  </div>`;
}

function actionBadge(a) {
  return `<span class="action-badge ${(a||'').toLowerCase()}">${a}</span>`;
}

function strategyTag(s) {
  const label = s === 'sl_tp' ? 'SL/TP' : s === 'trailing_stop' ? 'Trail' : s === 'dca' ? 'DCA' : (s||'AI');
  return `<span class="strategy-tag ${s||''}">${label}</span>`;
}

function timeAgo(ts) {
  if (!ts) return '--';
  const d = new Date(ts.includes('T') ? ts : ts + 'Z');
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return Math.round(diff) + 's ago';
  if (diff < 3600) return Math.round(diff/60) + 'm ago';
  if (diff < 86400) return Math.round(diff/3600) + 'h ago';
  return d.toLocaleDateString();
}

function escHtml(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── API ───────────────────────────────────────────────────────────────────────
async function api(path, method='GET', body=null) {
  const opts = { method, headers: {'Content-Type':'application/json'} };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) {
    const e = await r.json().catch(() => ({detail: r.statusText}));
    throw new Error(e.detail || r.statusText);
  }
  return r.json();
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
  await Promise.all([loadAccount(), loadStatus(), loadSentiment(), loadPortfolioHistoryChart()]);
  loadAllocChart();
}

async function loadAccount() {
  try {
    const d = await api('/api/account');
    document.getElementById('total-value').textContent = fmtMoney(d.total_value);
    const pnl = d.total_pnl || 0;
    document.getElementById('total-pnl').innerHTML = `<span class="${colorClass(pnl)}">${fmtMoney(pnl)} (${fmtPct(d.total_pnl_pct)})</span>`;
    document.getElementById('cash-value').textContent = fmtMoney(d.cash);
    const cashPct = d.total_value > 0 ? (d.cash / d.total_value * 100) : 0;
    document.getElementById('cash-pct').textContent = fmt(cashPct) + '% of portfolio';
    document.getElementById('invested-value').textContent = fmtMoney(d.invested);
    document.getElementById('position-count').textContent = d.position_count + ' positions';
  } catch(e) { console.error('Account:', e.message); }
}

async function loadSentiment() {
  try {
    const d = await api('/api/sentiment');
    const label = d.sentiment.replace('_', ' ');
    const cls = d.sentiment.includes('bullish') ? 'green' : d.sentiment.includes('bearish') ? 'red' : 'yellow';
    document.getElementById('sentiment-value').innerHTML = `<span class="${cls}" style="text-transform:capitalize">${label}</span>`;
    document.getElementById('sentiment-score').textContent = `Score: ${d.score} / 100`;
  } catch(e) {}
}

let _chartPeriodData = null;

async function loadPortfolioHistoryChart() {
  try {
    const history = await api('/api/portfolio/history?limit=1000');
    _chartPeriodData = history;
    renderPortfolioChart(history, '1d');
  } catch(e) {}
}

function setChartPeriod(period, btn) {
  document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (_chartPeriodData) renderPortfolioChart(_chartPeriodData, period);
}

function renderPortfolioChart(history, period) {
  const now = Date.now();
  const cutoffs = { '1d': 86400000, '1w': 604800000, '1m': 2592000000 };
  const filtered = history.filter(h => {
    const ts = new Date(h.snapshot_at.includes('T') ? h.snapshot_at : h.snapshot_at + 'Z').getTime();
    return (now - ts) <= (cutoffs[period] || cutoffs['1d']);
  });
  const data = filtered.length >= 2 ? filtered : history.slice(-48);

  const labels = data.map(h => {
    const d = new Date(h.snapshot_at.includes('T') ? h.snapshot_at : h.snapshot_at + 'Z');
    return period === '1d'
      ? d.toLocaleTimeString('en-US', {hour:'2-digit',minute:'2-digit'})
      : d.toLocaleDateString('en-US', {month:'short',day:'numeric'});
  });
  const values = data.map(h => h.total_value);

  if (portfolioChart) portfolioChart.destroy();
  const ctx = document.getElementById('portfolio-chart').getContext('2d');
  portfolioChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{ data: values, borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.08)', fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2 }] },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#1e2130' }, ticks: { color: '#6b7280', font: { size: 11 }, maxTicksLimit: 8 } },
        y: { grid: { color: '#1e2130' }, ticks: { color: '#6b7280', font: { size: 11 }, callback: v => '$' + Number(v).toLocaleString() } }
      }
    }
  });
}

async function loadAllocChart() {
  try {
    const portfolio = await api('/api/portfolio');
    if (!portfolio.length) return;
    const labels = portfolio.map(p => p.ticker);
    const values = portfolio.map(p => p.currentValue || 0);

    if (allocationChart) allocationChart.destroy();
    const ctx = document.getElementById('allocation-chart').getContext('2d');
    allocationChart = new Chart(ctx, {
      type: 'doughnut',
      data: { labels, datasets: [{ data: values, backgroundColor: PALETTE.slice(0, labels.length), borderWidth: 0 }] },
      options: { responsive: true, cutout: '65%', plugins: { legend: { display: false } } }
    });

    const legend = document.getElementById('allocation-legend');
    const total = values.reduce((a,b)=>a+b,0);
    legend.innerHTML = portfolio.map((p, i) =>
      `<div class="alloc-item"><div class="alloc-dot" style="background:${PALETTE[i % PALETTE.length]}"></div>${p.ticker} ${fmt(values[i]/total*100,1)}%</div>`
    ).join('');
  } catch(e) {}
}

async function loadStatus() {
  try {
    const d = await api('/api/status');
    const dot = document.getElementById('status-dot');
    const txt = document.getElementById('status-text');
    if (d.is_paused) {
      dot.className = 'status-dot paused';
      txt.textContent = 'Bot Paused';
    } else if (d.is_running) {
      dot.className = 'status-dot running';
      txt.textContent = 'Bot Running';
    } else {
      dot.className = 'status-dot idle';
      txt.textContent = d.last_run ? 'Last: ' + timeAgo(d.last_run) : 'Bot Idle';
    }

    const log = document.getElementById('activity-log');
    if (d.log && d.log.length) {
      log.innerHTML = d.log.slice().reverse().map(l => {
        let cls = '';
        if (l.includes('BUYING') || (l.includes('✓') && l.includes('BUY'))) cls = 'buy';
        else if (l.includes('SELLING') || l.includes('SELL')) cls = 'sell';
        else if (l.includes('ERROR') || l.includes('✗')) cls = 'err';
        else if (l.includes('⚠️') || l.includes('ALERT') || l.includes('limit') || l.includes('🔔')) cls = 'warn';
        return `<div class="log-entry ${cls}">${escHtml(l)}</div>`;
      }).join('');
    }
  } catch(e) {}
}

function toggleAutoRefresh(enabled) {
  clearInterval(autoRefreshInterval);
  if (enabled) autoRefreshInterval = setInterval(() => loadStatus(), 5000);
}

toggleAutoRefresh(true);

async function triggerAnalysis() {
  try {
    await api('/api/analyze/run', 'POST');
    showToast('Analysis cycle started', 'info');
    setTimeout(loadStatus, 2000);
  } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function loadPortfolioReview() {
  const el = document.getElementById('portfolio-review-content');
  el.innerHTML = '<div style="color:var(--text-muted);font-size:13px">Analyzing portfolio...</div>';
  try {
    const d = await api('/api/portfolio/review');
    const color = d.health_score >= 70 ? 'green' : d.health_score >= 40 ? 'yellow' : 'red';
    el.innerHTML = `
      <div class="health-score ${color}">${d.health_score}</div>
      <div class="health-label ${color}">${d.overall_health}</div>
      <div class="review-section"><h4>Summary</h4><p style="font-size:13px;color:var(--text-muted)">${d.summary}</p></div>
      ${d.top_risks?.length ? `<div class="review-section"><h4>Risks</h4><ul class="review-list">${d.top_risks.map(r=>`<li>${r}</li>`).join('')}</ul></div>` : ''}
      ${d.opportunities?.length ? `<div class="review-section"><h4>Opportunities</h4><ul class="review-list">${d.opportunities.map(r=>`<li>${r}</li>`).join('')}</ul></div>` : ''}
      <p style="font-size:12px;color:var(--accent);margin-top:8px">${d.cash_deployment_advice}</p>
    `;
  } catch(e) { el.innerHTML = `<p style="color:var(--red)">${e.message}</p>`; }
}

async function loadBrief() {
  const el = document.getElementById('brief-content');
  el.innerHTML = '<div style="color:var(--text-muted);font-size:13px">Generating brief...</div>';
  try {
    const d = await api('/api/brief');
    const biasColor = d.market_bias === 'bullish' ? 'green' : d.market_bias === 'bearish' ? 'red' : 'yellow';
    el.innerHTML = `
      <div class="brief-headline">${escHtml(d.headline)}</div>
      <div class="brief-row"><strong>Bias</strong><span class="${biasColor}" style="text-transform:capitalize">${d.market_bias}</span></div>
      ${d.tickers_to_watch?.length ? `<div class="brief-row"><strong>Watch</strong>${d.tickers_to_watch.join(', ')}</div>` : ''}
      ${d.key_opportunities?.length ? `<div class="review-section" style="margin-top:10px"><h4>Opportunities</h4><ul class="review-list">${d.key_opportunities.map(r=>`<li>${r}</li>`).join('')}</ul></div>` : ''}
      ${d.key_risks?.length ? `<div class="review-section"><h4>Risks</h4><ul class="review-list">${d.key_risks.map(r=>`<li>${r}</li>`).join('')}</ul></div>` : ''}
      <p style="font-size:12px;color:var(--text-muted);margin-top:8px">${escHtml(d.suggested_focus)}</p>
    `;
  } catch(e) { el.innerHTML = `<p style="color:var(--red)">${e.message}</p>`; }
}

// ── Portfolio ─────────────────────────────────────────────────────────────────
async function loadPortfolio() {
  try {
    const positions = await api('/api/portfolio');
    const tbody = document.getElementById('portfolio-tbody');
    if (!positions.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">No open positions</td></tr>';
      document.getElementById('portfolio-stats').innerHTML = '';
      return;
    }
    const totalVal = positions.reduce((s, p) => s + (p.currentValue||0), 0);
    const totalPnl = positions.reduce((s, p) => s + (p.ppl||0), 0);
    document.getElementById('portfolio-stats').innerHTML = [
      ['Positions', positions.length],
      ['Total Value', fmtMoney(totalVal)],
      ['Total P&L', `<span class="${colorClass(totalPnl)}">${fmtMoney(totalPnl)}</span>`],
      ['Avg P&L %', `<span class="${colorClass(totalPnl)}">${fmtPct(positions.reduce((s,p)=>s+(p.ppl||0)/Math.max(p.investedValue||1,1)*100,0)/positions.length)}</span>`],
    ].map(([l,v]) => `<div class="stat-card"><div class="stat-label">${l}</div><div class="stat-value">${v}</div></div>`).join('');

    tbody.innerHTML = positions.map(p => {
      const pnl = p.ppl || 0;
      const pnlPct = pnl / Math.max(p.investedValue||1, 1) * 100;
      return `<tr>
        <td><strong>${p.ticker}</strong></td>
        <td>${fmt(p.quantity, 4)}</td>
        <td>${fmtMoney(p.averagePrice)}</td>
        <td>${fmtMoney(p.currentPrice)}</td>
        <td>${fmtMoney(p.currentValue)}</td>
        <td class="${colorClass(pnl)}">${fmtMoney(pnl)}</td>
        <td class="${colorClass(pnlPct)}">${fmtPct(pnlPct)}</td>
        <td><button class="btn btn-danger" onclick="sellPosition('${p.ticker}',${p.quantity})">Sell</button></td>
      </tr>`;
    }).join('');
  } catch(e) { showToast('Portfolio error: ' + e.message, 'error'); }
}

async function sellPosition(ticker, qty) {
  showModal('Confirm Sell', `Sell all ${qty} shares of ${ticker} at market price?`, async () => {
    try {
      await api('/api/order', 'POST', { ticker, action: 'SELL', quantity: qty, order_type: 'market' });
      showToast(`Sell order placed for ${ticker}`, 'success');
      loadPortfolio();
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
  });
}

// ── AI Research ───────────────────────────────────────────────────────────────
async function runSingleAnalysis() {
  const ticker = document.getElementById('research-ticker').value.trim().toUpperCase();
  if (!ticker) return;
  document.getElementById('analysis-result').classList.add('hidden');
  showToast(`Analyzing ${ticker}...`, 'info');
  try {
    const d = await api(`/api/analyze/${ticker}`, 'POST');
    const a = d.analysis;
    const md = d.market_data;
    const color = a.action === 'BUY' ? 'green' : a.action === 'SELL' ? 'red' : a.action === 'HOLD' ? 'blue' : 'text-muted';

    document.getElementById('analysis-decision').innerHTML = `
      <div class="analysis-decision">
        <div class="decision-action ${color}">${a.action}</div>
        ${confBar(a.confidence)}
        <p style="font-size:13px;color:var(--text-muted)">${escHtml(a.reasoning)}</p>
        ${a.price_target ? `<div style="font-size:13px">Target: <strong>${fmtMoney(a.price_target)}</strong>&nbsp;&nbsp;SL: <strong>${fmtMoney(a.stop_loss_price)}</strong></div>` : ''}
        ${a.pattern_assessment ? `<p style="font-size:12px;color:var(--yellow)">${escHtml(a.pattern_assessment)}</p>` : ''}
        <div>
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);margin-bottom:6px">Signals</div>
          <div class="signal-list">${(a.key_signals||[]).map(s=>`<span class="signal-tag">${escHtml(s)}</span>`).join('')}</div>
        </div>
        <div>
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);margin-bottom:6px">Risk Factors</div>
          <div class="signal-list">${(a.risk_factors||[]).map(r=>`<span class="risk-tag">${escHtml(r)}</span>`).join('')}</div>
        </div>
        ${md.patterns?.length ? `<div><div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);margin-bottom:6px">Patterns</div><div class="signal-list">${md.patterns.map(p=>`<span class="pattern-tag">${p.replace(/_/g,' ')}</span>`).join('')}</div></div>` : ''}
      </div>`;

    document.getElementById('analysis-market-data').innerHTML = `
      <div class="market-grid">
        ${[
          ['Price', fmtMoney(md.price)],
          ['1D Change', `<span class="${colorClass(md.change_1d_pct)}">${fmtPct(md.change_1d_pct)}</span>`],
          ['RSI (daily)', fmt(md.rsi,1)],
          ['RSI (1h)', md.rsi_1h != null ? fmt(md.rsi_1h,1) : '--'],
          ['Williams %R', fmt(md.williams_r,1)],
          ['CCI', fmt(md.cci,1)],
          ['ADX', fmt(md.adx,1)],
          ['MACD Status', md.macd_crossover||'--'],
          ['Bollinger %B', fmt(md.bb_pct,3)],
          ['ATR', fmt(md.atr)],
          ['OBV Trend', md.obv_trend||'--'],
          ['VWAP', fmtMoney(md.vwap)],
          ['52W High', fmtMoney(md['52w_high'])],
          ['52W Low', fmtMoney(md['52w_low'])],
          ['P/E', fmt(md.pe_ratio,1)],
          ['Fwd P/E', fmt(md.forward_pe,1)],
          ['Rev Growth', md.revenue_growth ? fmtPct(md.revenue_growth*100) : '--'],
          ['Analyst Target', fmtMoney(md.analyst_target)],
          ['Short Float', md.short_float ? fmt(md.short_float*100,1)+'%' : '--'],
          ['Next Earnings', md.earnings_date||'--'],
        ].map(([l,v])=>`<div class="market-row"><label>${l}</label><span>${v}</span></div>`).join('')}
      </div>`;

    document.getElementById('analysis-signals').innerHTML = `
      <div class="market-grid">
        ${[
          ['Above EMA9', md.above_ema_9==null?'--':md.above_ema_9?'✓ Yes':'✗ No'],
          ['Above EMA50', md.above_ema_50==null?'--':md.above_ema_50?'✓ Yes':'✗ No'],
          ['Above SMA200', md.above_sma_200==null?'--':md.above_sma_200?'✓ Yes':'✗ No'],
          ['EMA9', fmtMoney(md.ema_9)],
          ['EMA21', fmtMoney(md.ema_21)],
          ['EMA50', fmtMoney(md.ema_50)],
          ['SMA200', fmtMoney(md.sma_200)],
          ['BB Upper', fmtMoney(md.bb_upper)],
          ['BB Lower', fmtMoney(md.bb_lower)],
          ['Support', fmtMoney(md.support)],
          ['Resistance', fmtMoney(md.resistance)],
          ['Beta', fmt(md.beta,2)],
          ['Volume Ratio', fmt(md.volume_ratio)+'x'],
          ['Stoch K/D', `${fmt(md.stoch_k,1)} / ${fmt(md.stoch_d,1)}`],
        ].map(([l,v])=>`<div class="market-row"><label>${l}</label><span>${v}</span></div>`).join('')}
      </div>`;

    const news = md.news || [];
    document.getElementById('analysis-news').innerHTML = news.length
      ? news.map(n=>`<div class="news-item"><div class="news-title">${escHtml(n.title||'')}</div><div class="news-meta">${escHtml(n.source||'')}${n.summary?' · '+escHtml(n.summary):''}</div></div>`).join('')
      : '<p style="color:var(--text-muted);font-size:13px">No recent news found</p>';

    document.getElementById('analysis-result').classList.remove('hidden');
  } catch(e) { showToast('Analysis error: ' + e.message, 'error'); }
}

async function loadAnalyses() {
  try {
    const rows = await api('/api/analyses?limit=30');
    const tbody = document.getElementById('analyses-tbody');
    if (!rows.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">No analyses yet</td></tr>'; return; }
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td style="color:var(--text-muted);font-size:12px;white-space:nowrap">${timeAgo(r.created_at)}</td>
        <td><strong>${r.ticker}</strong></td>
        <td>${actionBadge(r.action)}</td>
        <td>${confBar(r.confidence)}</td>
        <td style="font-size:12px">${r.news_sentiment?`<span class="${r.news_sentiment==='positive'?'green':r.news_sentiment==='negative'?'red':'yellow'}">${r.news_sentiment}</span>`:'--'}</td>
        <td style="color:var(--text-muted);font-size:12px;max-width:280px">${escHtml(r.reasoning||'')}</td>
      </tr>`).join('');
  } catch(e) {}
}

// ── Manual Trade ──────────────────────────────────────────────────────────────
function toggleLimitPrice() {
  document.getElementById('limit-price-group').classList.toggle('hidden', document.getElementById('trade-order-type').value !== 'limit');
}

async function placeTrade() {
  const ticker = document.getElementById('trade-ticker').value.trim().toUpperCase();
  const action = document.getElementById('trade-action').value;
  const quantity = parseFloat(document.getElementById('trade-quantity').value);
  const orderType = document.getElementById('trade-order-type').value;
  const limitPrice = parseFloat(document.getElementById('trade-limit-price').value) || null;
  if (!ticker || !quantity || quantity <= 0) { showToast('Fill in ticker and quantity', 'warning'); return; }
  showModal('Confirm Order', `${action} ${quantity} shares of ${ticker} (${orderType} order)?`, async () => {
    try {
      await api('/api/order', 'POST', { ticker, action, quantity, order_type: orderType, limit_price: limitPrice });
      showToast(`${action} order placed for ${ticker}`, 'success');
      loadOpenOrders();
    } catch(e) { showToast('Order error: ' + e.message, 'error'); }
  });
}

async function loadOpenOrders() {
  try {
    const orders = await api('/api/orders');
    const tbody = document.getElementById('open-orders-tbody');
    if (!orders.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No open orders</td></tr>'; return; }
    tbody.innerHTML = orders.map(o => `
      <tr>
        <td style="color:var(--text-muted);font-size:12px">#${o.id}</td>
        <td><strong>${o.ticker}</strong></td>
        <td>${o.limitPrice ? 'LIMIT' : 'MARKET'}</td>
        <td>${fmt(o.quantity,4)}</td>
        <td>${o.limitPrice ? fmtMoney(o.limitPrice) : 'Market'}</td>
        <td><span style="color:var(--yellow)">${o.status||'PENDING'}</span></td>
        <td><button class="btn btn-danger" onclick="cancelOrder(${o.id})">Cancel</button></td>
      </tr>`).join('');
  } catch(e) {}
}

async function cancelOrder(id) {
  try {
    await api(`/api/order/${id}`, 'DELETE');
    showToast('Order cancelled', 'info');
    loadOpenOrders();
  } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

// ── Watchlist ─────────────────────────────────────────────────────────────────
async function loadWatchlist() {
  try {
    const tickers = await api('/api/watchlist');
    const tbody = document.getElementById('watchlist-tbody');
    tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">Loading market data...</td></tr>';
    const dataArr = await Promise.all(tickers.map(t => api(`/api/market/${t}`).catch(() => ({ ticker: t, error: true }))));
    tbody.innerHTML = dataArr.map(d => {
      if (d.error) return `<tr><td><strong>${d.ticker}</strong></td><td colspan="7" style="color:var(--red)">Data unavailable</td></tr>`;
      const rsiStr = d.rsi != null ? fmt(d.rsi,1) : '--';
      const rsi1hStr = d.rsi_1h != null ? `/${fmt(d.rsi_1h,1)}` : '';
      const rsiColor = d.rsi > 70 ? 'red' : d.rsi < 30 ? 'green' : '';
      const macdColor = d.macd_crossover?.includes('bullish') ? 'green' : d.macd_crossover?.includes('bearish') ? 'red' : '';
      const patterns = d.patterns?.length ? d.patterns.slice(0,2).map(p=>`<span class="pattern-tag" style="font-size:10px">${p.replace(/_/g,' ')}</span>`).join(' ') : '--';
      return `<tr>
        <td><strong>${d.ticker}</strong><br><span style="font-size:11px;color:var(--text-muted)">${d.sector||''}</span></td>
        <td>${fmtMoney(d.price)}</td>
        <td class="${colorClass(d.change_1d_pct)}">${fmtPct(d.change_1d_pct)}</td>
        <td class="${rsiColor}" title="Daily / 1h">${rsiStr}${rsi1hStr}</td>
        <td class="${macdColor}">${(d.macd_crossover||'').replace(/_/g,' ')}</td>
        <td>${d.adx != null ? fmt(d.adx,1) : '--'}</td>
        <td>${patterns}</td>
        <td style="display:flex;gap:4px;flex-wrap:wrap">
          <button class="btn btn-secondary" style="font-size:11px;padding:3px 8px" onclick="quickAnalyze('${d.ticker}')">Analyze</button>
          <button class="btn btn-danger" style="font-size:11px" onclick="removeFromWatchlist('${d.ticker}')">✕</button>
        </td>
      </tr>`;
    }).join('');
  } catch(e) { showToast('Watchlist error: ' + e.message, 'error'); }
}

function quickAnalyze(ticker) {
  document.getElementById('research-ticker').value = ticker;
  document.querySelector('[data-page=research]').click();
}

async function addToWatchlist() {
  const ticker = document.getElementById('add-ticker-input').value.trim().toUpperCase();
  if (!ticker) return;
  try {
    await api('/api/watchlist', 'POST', { ticker });
    document.getElementById('add-ticker-input').value = '';
    showToast(`${ticker} added`, 'success');
    loadWatchlist();
  } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function removeFromWatchlist(ticker) {
  try {
    await api(`/api/watchlist/${ticker}`, 'DELETE');
    showToast(`${ticker} removed`, 'info');
    loadWatchlist();
  } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

// ── History ───────────────────────────────────────────────────────────────────
async function loadTrades() {
  try {
    const rows = await api('/api/trades?limit=100');
    const tbody = document.getElementById('trades-tbody');
    if (!rows.length) { tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">No trades yet</td></tr>'; return; }
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td style="color:var(--text-muted);font-size:12px;white-space:nowrap">${timeAgo(r.created_at)}</td>
        <td><strong>${r.ticker}</strong></td>
        <td>${actionBadge(r.action)}</td>
        <td>${fmt(r.quantity,4)}</td>
        <td>${fmtMoney(r.price)}</td>
        <td>${strategyTag(r.strategy_tag)}</td>
        <td>${confBar(r.confidence)}</td>
        <td style="color:var(--text-muted);font-size:12px;max-width:260px">${escHtml(r.ai_reasoning||'')}</td>
      </tr>`).join('');
  } catch(e) {}
}

// ── Performance ───────────────────────────────────────────────────────────────
async function loadPerformance() {
  try {
    const d = await api('/api/performance');
    document.getElementById('perf-stats-grid').innerHTML = [
      ['Total Trades', d.total_trades],
      ['Total P&L', `<span class="${colorClass(d.total_pnl)}">${fmtMoney(d.total_pnl)}</span>`],
      ['Profit Factor', d.profit_factor != null ? fmt(d.profit_factor,2)+'x' : '--'],
      ['Portfolio Growth', d.portfolio_growth_pct != null ? `<span class="${colorClass(d.portfolio_growth_pct)}">${fmtPct(d.portfolio_growth_pct)}</span>` : '--'],
    ].map(([l,v]) => `<div class="stat-card"><div class="stat-label">${l}</div><div class="stat-value">${v}</div></div>`).join('');

    const winPct = d.win_rate || 0;
    document.getElementById('win-rate-display').innerHTML = `
      <div style="text-align:center;padding:12px 0">
        <div style="font-size:56px;font-weight:800;color:${winPct>=50?'var(--green)':'var(--red)'}">${fmt(winPct,1)}%</div>
        <div style="color:var(--text-muted);font-size:13px;margin-top:4px">${d.total_sells} closed trades · ${d.total_buys} buys total</div>
        <div style="color:var(--text-muted);font-size:12px;margin-top:2px">Avg AI confidence: ${fmt(d.avg_confidence,1)}%</div>
      </div>`;

    document.getElementById('pnl-breakdown').innerHTML = `
      <div class="pnl-row"><label>Avg Win</label><strong class="green">${fmtMoney(d.avg_win)}</strong></div>
      <div class="pnl-row"><label>Avg Loss</label><strong class="red">${fmtMoney(d.avg_loss)}</strong></div>
      <div class="pnl-row"><label>Best Trade</label><strong class="green">${fmtMoney(d.best_trade)}</strong></div>
      <div class="pnl-row"><label>Worst Trade</label><strong class="red">${fmtMoney(d.worst_trade)}</strong></div>
      <div class="pnl-row"><label>Wins / Trades</label><strong>${Math.round(d.total_sells * d.win_rate / 100)} / ${d.total_sells}</strong></div>
    `;

    const history = await api('/api/portfolio/history?limit=500');
    if (history.length >= 2) {
      if (growthChart) growthChart.destroy();
      const ctx = document.getElementById('growth-chart').getContext('2d');
      growthChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: history.map(h => { const d = new Date(h.snapshot_at.includes('T') ? h.snapshot_at : h.snapshot_at+'Z'); return d.toLocaleDateString('en-US',{month:'short',day:'numeric'}); }),
          datasets: [{ data: history.map(h=>h.total_value), borderColor:'#6366f1', backgroundColor:'rgba(99,102,241,0.08)', fill:true, tension:0.4, pointRadius:0, borderWidth:2 }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid:{color:'#1e2130'}, ticks:{color:'#6b7280',font:{size:11},maxTicksLimit:8} },
            y: { grid:{color:'#1e2130'}, ticks:{color:'#6b7280',font:{size:11},callback:v=>'$'+Number(v).toLocaleString()} }
          }
        }
      });
    }
  } catch(e) { console.error('Performance:', e); }
}

// ── Alerts ────────────────────────────────────────────────────────────────────
async function createAlert() {
  const ticker = document.getElementById('alert-ticker').value.trim().toUpperCase();
  const direction = document.getElementById('alert-direction').value;
  const price = parseFloat(document.getElementById('alert-price').value);
  const note = document.getElementById('alert-note').value.trim();
  if (!ticker || !price) { showToast('Enter ticker and price', 'warning'); return; }
  try {
    await api('/api/alerts', 'POST', { ticker, direction, target_price: price, note });
    showToast(`Alert set: ${ticker} ${direction} $${price}`, 'success');
    ['alert-ticker','alert-price','alert-note'].forEach(id => document.getElementById(id).value = '');
    loadAlerts();
  } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function loadAlerts() {
  const showTriggered = document.getElementById('show-triggered')?.checked;
  try {
    const alerts = await api(`/api/alerts?include_triggered=${!!showTriggered}`);
    const active = alerts.filter(a => !a.triggered);
    const badge = document.getElementById('alerts-badge');
    if (active.length > 0) { badge.textContent = active.length; badge.classList.remove('hidden'); }
    else badge.classList.add('hidden');

    const tbody = document.getElementById('alerts-tbody');
    if (!alerts.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No alerts set</td></tr>'; return; }
    tbody.innerHTML = alerts.map(a => `
      <tr style="${a.triggered?'opacity:0.5':''}">
        <td><strong>${a.ticker}</strong></td>
        <td>${a.direction}</td>
        <td>${fmtMoney(a.target_price)}</td>
        <td style="color:var(--text-muted);font-size:12px">${escHtml(a.note||'')}</td>
        <td>${a.triggered?'<span class="green">Triggered</span>':'<span class="yellow">Active</span>'}</td>
        <td style="color:var(--text-muted);font-size:12px">${timeAgo(a.created_at)}</td>
        <td><button class="btn btn-danger" onclick="deleteAlert(${a.id})">✕</button></td>
      </tr>`).join('');
  } catch(e) {}
}

async function deleteAlert(id) {
  try {
    await api(`/api/alerts/${id}`, 'DELETE');
    showToast('Alert deleted', 'info');
    loadAlerts();
  } catch(e) { showToast('Error: ' + e.message, 'error'); }
}

// ── Chat ──────────────────────────────────────────────────────────────────────
async function loadChatHistory() {
  try {
    const msgs = await api('/api/chat/history');
    const box = document.getElementById('chat-messages');
    box.innerHTML = '<div class="chat-bubble assistant">Hello! I\'m your AI trading assistant with full context of your portfolio. Ask me anything about stocks, your positions, strategy, or the market.</div>';
    msgs.forEach(m => appendChatBubble(m.role, m.content));
  } catch(e) {}
}

function appendChatBubble(role, content) {
  const box = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `chat-bubble ${role}`;
  div.textContent = content;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  appendChatBubble('user', msg);

  const thinking = document.createElement('div');
  thinking.className = 'chat-bubble assistant thinking';
  thinking.textContent = 'Thinking...';
  document.getElementById('chat-messages').appendChild(thinking);
  document.getElementById('chat-messages').scrollTop = 999999;

  try {
    const d = await api('/api/chat', 'POST', { message: msg });
    thinking.remove();
    appendChatBubble('assistant', d.reply);
  } catch(e) {
    thinking.remove();
    appendChatBubble('assistant', 'Error: ' + e.message);
  }
}

async function clearChat() {
  showModal('Clear Chat', 'Delete all chat history?', async () => {
    try { await api('/api/chat/history', 'DELETE'); loadChatHistory(); } catch(e) {}
  });
}

// ── Bot controls ──────────────────────────────────────────────────────────────
async function pauseBot() {
  try { await api('/api/bot/pause', 'POST'); showToast('Bot paused', 'warning'); loadStatus(); }
  catch(e) { showToast('Error: ' + e.message, 'error'); }
}

async function resumeBot() {
  try { await api('/api/bot/resume', 'POST'); showToast('Bot resumed', 'success'); loadStatus(); }
  catch(e) { showToast('Error: ' + e.message, 'error'); }
}

function confirmEmergencyExit() {
  showModal(
    '🚨 Emergency Exit',
    'This will IMMEDIATELY sell ALL open positions at market price and pause the bot. Are you sure?',
    async () => {
      try {
        await api('/api/bot/emergency-exit', 'POST');
        showToast('Emergency exit initiated — selling all positions', 'error');
        setTimeout(() => { loadStatus(); loadPortfolio(); }, 3000);
      } catch(e) { showToast('Error: ' + e.message, 'error'); }
    }
  );
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function loadSettings() {
  try {
    const d = await api('/api/settings');
    const badge = document.getElementById('mode-badge');
    badge.textContent = d.t212_mode.toUpperCase();
    badge.className = 'badge ' + d.t212_mode;
    const labels = {
      t212_mode:'Mode', max_position_pct:'Max Position Size %',
      max_sector_pct:'Max Sector Concentration %', analysis_interval_minutes:'Analysis Interval (min)',
      max_open_positions:'Max Open Positions', stop_loss_pct:'Stop Loss %',
      take_profit_pct:'Take Profit %', trailing_stop_pct:'Trailing Stop %',
      daily_loss_limit_pct:'Daily Loss Limit %', min_confidence:'Min AI Confidence %',
      trade_market_hours_only:'Trade Market Hours Only', dca_mode:'DCA Mode',
      dca_drop_trigger_pct:'DCA Drop Trigger %',
    };
    document.getElementById('settings-tbody').innerHTML = Object.entries(d).map(([k,v]) =>
      `<tr><td>${labels[k]||k}</td><td>${typeof v==='boolean'?(v?'✓ Enabled':'✗ Disabled'):v}</td></tr>`
    ).join('');
  } catch(e) {}
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadDashboard();
loadSettings();
setInterval(loadAlerts, 30000);
