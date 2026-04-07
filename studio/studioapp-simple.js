// studioapp-simple.js — Trading Studio (Lightweight)
// Routes du serveur Node 4000 — TRADING AUTO EXCLUSIVE

'use strict';

const API = 'http://127.0.0.1:4000';
const STORE_KEY = 'studio_state';

// ── STATE ─────────────────────────────────────────────────────────────────────
var state = {
  symbol: 'XAUUSD',
  timeframe: 'H1',
  mode: 'manual',
  tvEnabled: true,
  mt5Enabled: false,
  syncStatus: 'OFFLINE',
  logs: []
};

// ── CHART STATE ───────────────────────────────────────────────────────────────
var chart = null;
var candleSeries = null;

// ── HELPERS ───────────────────────────────────────────────────────────────────
function saveState() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({
      symbol: state.symbol,
      timeframe: state.timeframe,
      mode: state.mode,
      tvEnabled: state.tvEnabled,
      mt5Enabled: state.mt5Enabled
    }));
  } catch (e) {
    console.error('Error saving state:', e);
  }
}

function loadState() {
  try {
    var saved = JSON.parse(localStorage.getItem(STORE_KEY));
    if (saved) {
      state = { ...state, ...saved };
    }
  } catch (e) {
    console.error('Error loading state:', e);
  }
}

function log(msg, level = 'info') {
  var ts = new Date().toLocaleTimeString('fr-FR');
  var entry = { ts: ts, msg: msg, level: level };
  
  state.logs.unshift(entry);
  if (state.logs.length > 100) state.logs.pop();
  
  console.log(`[${level}] ${ts} — ${msg}`);
  
  var panel = document.getElementById('log-panel');
  if (panel) {
    var color = level === 'error' ? '#ff4444' : level === 'warning' ? '#ffaa00' : '#00ff88';
    var line = document.createElement('div');
    line.style.color = color;
    line.textContent = `[${level}] ${ts}: ${msg}`;
    panel.appendChild(line);
    panel.scrollTop = panel.scrollHeight;
    
    // Limite à 100 lignes en DOM
    while (panel.children.length > 100) {
      panel.removeChild(panel.firstChild);
    }
  }
}

async function fetchAPI(endpoint) {
  try {
    var url = API + endpoint;
    var r = await fetch(url, { signal: AbortSignal.timeout(4000) });
    if (!r.ok) {
      log(`❌ ${endpoint} → HTTP ${r.status}`, 'error');
      return null;
    }
    return await r.json();
  } catch (e) {
    if (e.name !== 'AbortError') log(`❌ ${endpoint} → ${e.message}`, 'error');
    return null;
  }
}

// ── SERVER HEALTH ─────────────────────────────────────────────────────────────
var _serverOnline = true;
function setToggleButtonState() {
  var tvBtn = document.getElementById('btn-toggle-tv');
  var mt5Btn = document.getElementById('btn-toggle-mt5');
  if (tvBtn) tvBtn.textContent = state.tvEnabled ? '📺 TradingView ON' : '📺 TradingView OFF';
  if (mt5Btn) mt5Btn.textContent = state.mt5Enabled ? '🧩 MT5 ON' : '🧩 MT5 OFF';
}

async function patchBridgeConfig(patch) {
  try {
    var resp = await fetch(API + '/extension/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: 'set-bridge-config',
        payload: patch
      }),
      signal: AbortSignal.timeout(4000)
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch (_) {
    return null;
  }
}

async function checkBridge() {
  var health = await fetchAPI('/live/state');
  var dot = document.getElementById('server-dot');
  var badge = document.getElementById('sync-badge');
  _serverOnline = !!(health && health.ok);

  if (_serverOnline) {
    if (dot) { dot.style.backgroundColor = '#00ff88'; dot.title = 'Server OK'; }
    var tvConnected = !!health?.tradingview?.connected;
    state.tvEnabled = health?.bridge?.tradingviewEnabled !== false;
    state.mt5Enabled = health?.bridge?.mt5Enabled === true;
    state.syncStatus = tvConnected && state.tvEnabled ? 'TV LIVE' : 'ONLINE';
    if (badge) {
      badge.textContent = state.syncStatus;
      badge.style.borderColor = state.syncStatus === 'TV LIVE' ? '#10b981' : '#3b82f6';
      badge.style.color = state.syncStatus === 'TV LIVE' ? '#10b981' : '#3b82f6';
    }
    setToggleButtonState();
  } else {
    if (dot) { dot.style.backgroundColor = '#ff4444'; dot.title = 'Server offline'; }
    state.syncStatus = 'OFFLINE';
    if (badge) {
      badge.textContent = 'OFFLINE';
      badge.style.borderColor = '#ef4444';
      badge.style.color = '#ef4444';
    }
  }
}

// ── STRICT MIRROR: EXTENSION SNAPSHOT ────────────────────────────────────────
async function syncFromExtensionSnapshot() {
  var data = await fetchAPI('/extension/data');
  if (!data || !data.ok) return;

  var active = data.activeSymbol || {};
  var current = data.currentData || {};
  var sourceCtx = data.sourceContexts || {};
  var bridge = data.bridgeConfig || {};
  var tv = sourceCtx.tradingview || {};

  if (active.symbol) state.symbol = String(active.symbol).toUpperCase();
  if (active.timeframe) state.timeframe = String(active.timeframe).toUpperCase();
  state.tvEnabled = bridge.tradingviewEnabled !== false;
  state.mt5Enabled = bridge.mt5Enabled === true;

  var livePrice = Number(current.price != null ? current.price : active.price);
  var priceEl = document.getElementById('critical-price');
  if (priceEl && Number.isFinite(livePrice) && livePrice > 0) {
    priceEl.textContent = livePrice > 10 ? livePrice.toFixed(2) : livePrice.toFixed(5);
  }

  var sessionEl = document.getElementById('session');
  if (sessionEl) {
    sessionEl.textContent = tv.connected ? 'TradingView LIVE' : (state.tvEnabled ? 'TradingView WAIT' : 'TradingView OFF');
  }

  var symbolSel = document.getElementById('symbol-select');
  if (symbolSel && state.symbol) symbolSel.value = state.symbol;

  document.querySelectorAll('.tfbtn').forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.tf === state.timeframe);
  });

  setToggleButtonState();
  saveState();
}

// ── INIT CHART ────────────────────────────────────────────────────────────────
function initChart() {
  var container = document.getElementById('chart-container');
  if (!container || typeof LightweightCharts === 'undefined') {
    log('LightweightCharts not available', 'warning');
    return;
  }
  
  try {
    chart = LightweightCharts.createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        textColor: '#00d4ff',
        backgroundColor: '#0f0f1e',
        fontFamily: 'Courier New'
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      grid: {
        hStyle: LightweightCharts.GridLineStyle.Dashed,
        vStyle: LightweightCharts.GridLineStyle.Dashed,
        color: '#333'
      }
    });
    
    candleSeries = chart.addCandlestickSeries({
      upColor: '#00ff88',
      downColor: '#ff4444',
      borderVisible: false,
      wickUpColor: '#00ff88',
      wickDownColor: '#ff4444'
    });
    
    window.addEventListener('resize', function() {
      if (chart && container) {
        chart.applyOptions({
          width: container.clientWidth,
          height: container.clientHeight
        });
      }
    });
    
    log('Chart initialized', 'info');
  } catch (e) {
    log(`Chart init error: ${e.message}`, 'error');
  }
}

// ── LOAD & RENDER CHART ───────────────────────────────────────────────────────
async function loadChart() {
  if (!chart || !candleSeries) {
    log('Chart not initialized', 'warning');
    return;
  }
  
  var sym = state.symbol;
  var tf = state.timeframe;
  
  var data = await fetchAPI(`/klines?symbol=${sym}&tf=${tf}&limit=80`);
  if (!data || !data.candles || data.candles.length === 0) {
    log(`No klines for ${sym} ${tf}`, 'warning');
    return;
  }

  var count = data.candles.length;
  var el = document.getElementById('chart-count');
  if (el) el.textContent = `${count} bougies`;
  
  var candles = data.candles.map(function(k) {
    var time = k.time || k.timestamp || k.date;
    if (typeof time === 'string') {
      time = Math.floor(new Date(time).getTime() / 1000);
    }
    return {
      time: time,
      open: parseFloat(k.open || 0),
      high: parseFloat(k.high || 0),
      low: parseFloat(k.low || 0),
      close: parseFloat(k.close || 0)
    };
  }).sort((a, b) => a.time - b.time);
  
  try {
    candleSeries.setData(candles);
    chart.timeScale().fitContent();
    log(`Graphique ${sym} ${tf}: ${count} bougies rendu`, 'info');
  } catch (e) {
    log(`Chart render error: ${e.message}`, 'error');
  }
}

// ── LOAD ANALYSIS & INDICATORS ────────────────────────────────────────────────
async function loadAnalysis() {
  var data = await fetchAPI('/analysis');
  if (!data || !data.analysis) {
    log('No analysis available', 'warning');
    return;
  }
  
  var panel = document.getElementById('analysis-panel');
  if (panel) {
    var html = '<pre style="font-size:10px;color:#00ff88;overflow-x:auto;white-space:pre-wrap;word-wrap:break-word;">';
    html += JSON.stringify(data.analysis, null, 2);
    html += '</pre>';
    panel.innerHTML = html;
  }
  
  log('Analysis loaded', 'info');
}

async function loadIndicators() {
  var data = await fetchAPI('/indicators');
  if (!data || !data.indicators) {
    log('No indicators', 'warning');
    return;
  }
  
  var panel = document.getElementById('indicators-panel');
  if (panel) {
    var html = '<table style="width:100%;font-size:11px;">';
    for (var key in data.indicators) {
      var val = data.indicators[key];
      var display = typeof val === 'number' ? val.toFixed(2) : JSON.stringify(val);
      html += `<tr style="border-bottom:1px solid #333;"><td style="padding:4px;">${key}</td><td style="padding:4px;text-align:right;color:#00ff88;">${display}</td></tr>`;
    }
    html += '</table>';
    panel.innerHTML = html;
  }
  
  log('Indicators loaded', 'info');
}

// ── T006: SYMBOL VALIDATION ───────────────────────────────────────────────────
async function validateSymbol(sym) {
  var panel = document.getElementById('symbol-validation-panel');
  var badge = document.getElementById('sync-badge');
  var price = null;

  // Get current price for validation
  var qData = await fetchAPI('/quote?symbol=' + encodeURIComponent(sym));
  if (qData) price = qData.price || qData.bid || 0;

  var url = '/match-symbol/' + encodeURIComponent(sym);
  if (price) url += '?price=' + price;
  var data = await fetchAPI(url);

  if (!data || !data.match) {
    if (panel) panel.innerHTML = '<span style="color:#ef4444;">⚠️ Symbole non reconnu: ' + sym + '</span>';
    if (badge) { badge.textContent = '? Sync'; badge.style.borderColor = '#ef4444'; badge.style.color = '#ef4444'; }
    return;
  }

  var m   = data.match;
  var col = m.syncStatus === 'SYNCHRONIZED' ? '#10b981' : m.syncStatus === 'ALIGNED' ? '#3b82f6' : '#f59e0b';
  var icon = m.syncStatus === 'SYNCHRONIZED' ? '✅' : m.syncStatus === 'ALIGNED' ? '🔵' : '⚠️';

  if (badge) {
    badge.textContent = icon + ' ' + (m.syncStatus || 'OK');
    badge.style.borderColor = col;
    badge.style.color = col;
  }

  if (panel) {
    panel.innerHTML =
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;">' +
        '<div><span style="color:#666;">TV Symbol:</span> <b style="color:#00d4ff;">' + (m.tvSymbol || sym) + '</b></div>' +
        '<div><span style="color:#666;">Canonical:</span> <b style="color:#00d4ff;">' + (m.canonical || m.selectedSymbol || sym) + '</b></div>' +
        '<div><span style="color:#666;">Type:</span> <span>' + (m.type || '—') + '</span></div>' +
        '<div><span style="color:#666;">Sync:</span> <span style="color:' + col + ';font-weight:bold;">' + (m.syncStatus || '—') + '</span></div>' +
      '</div>';
    if (m.tvPrice && m.backendPrice) {
      var diff = Math.abs(m.tvPrice - m.backendPrice);
      var pct  = ((diff / m.backendPrice) * 100).toFixed(3);
      panel.innerHTML += '<div style="margin-top:6px;color:#666;font-size:10px;">Écart TV↔backend: ' + pct + '%</div>';
    }
  }
}

// ── T007: AGENT ANALYSIS / INSTANT TRADE ─────────────────────────────────────
async function loadInstantTrade() {
  var sym = state.symbol.replace('/', '').toUpperCase();
  var data = await fetchAPI('/instant-trade-live?symbol=' + encodeURIComponent(sym) + '&mode=SNIPER');

  var dirEl    = document.getElementById('trade-direction');
  var scoreEl  = document.getElementById('trade-score');
  var rrEl     = document.getElementById('trade-rr');
  var levelsEl = document.getElementById('trade-levels');

  if (!data || !data.ok || !data.trade) {
    if (dirEl)   { dirEl.textContent = '—'; dirEl.style.color = '#888'; }
    if (scoreEl) scoreEl.textContent = '—';
    if (rrEl)    rrEl.textContent = '—';
    if (levelsEl) levelsEl.innerHTML = '<em style="color:#666;">Pas de signal TradingView live disponible</em>';
    return;
  }

  var t   = data.trade;
  var dir = t.direction || 'WAIT';
  var col = dir === 'LONG' ? '#10b981' : dir === 'SHORT' ? '#ef4444' : '#888';
  var score = typeof t.score === 'number' ? (t.score > 1 ? Math.round(t.score) : Math.round(t.score * 100)) : '—';

  if (dirEl)   { dirEl.textContent = dir; dirEl.style.color = col; }
  if (scoreEl) { scoreEl.textContent = score + '%'; scoreEl.style.color = col; }
  if (rrEl)    { rrEl.textContent = t.rrRatio ? '1:' + t.rrRatio : '—'; rrEl.style.color = '#00d4ff'; }

  if (levelsEl) {
    levelsEl.innerHTML =
      '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;text-align:center;">' +
        '<div><div style="color:#666;font-size:10px;">ENTRY</div><div style="color:#fff;font-weight:bold;">' + (t.entry || '—') + '</div></div>' +
        '<div><div style="color:#666;font-size:10px;">STOP LOSS</div><div style="color:#ef4444;font-weight:bold;">' + (t.sl || '—') + '</div></div>' +
        '<div><div style="color:#666;font-size:10px;">TAKE PROFIT</div><div style="color:#10b981;font-weight:bold;">' + (t.tp || '—') + '</div></div>' +
      '</div>' +
      (t.setup_type ? '<div style="margin-top:6px;color:#666;font-size:10px;">Setup: ' + t.setup_type + ' · ' + (t.expected_duration || '') + '</div>' : '') +
      (t.trade_status ? '<div style="margin-top:3px;font-size:10px;color:' + (t.trade_status === 'LIVE' ? '#10b981' : t.trade_status === 'CONDITIONAL' ? '#f59e0b' : '#888') + ';">Status: ' + t.trade_status + '</div>' : '');
  }

  log('Signal ' + dir + ' ' + sym + ' @ ' + (t.entry || '—') + ' score:' + score + '%', 'info');
}

async function loadEconomicEvents() {
  var data = await fetchAPI('/economic-events');
  if (!data || !data.events) {
    log('No economic events', 'warning');
    return;
  }
  
  var panel = document.getElementById('events-panel');
  if (panel) {
    if (data.events.length === 0) {
      panel.innerHTML = '<em style="color:#666;">No events</em>';
    } else {
      var html = '';
      data.events.forEach(function(e) {
        html += `<div style="padding:6px;border-bottom:1px solid #333;font-size:11px;">
          <strong style="color:#00d4ff;">${e.name || e.title || 'Event'}</strong><br/>
          <small style="color:#888;">${e.time || e.date || '—'}</small>
        </div>`;
      });
      panel.innerHTML = html;
    }
  }
  
  log(`${data.events.length} economic events loaded`, 'info');
}

// ── TEST ALL ROUTES ──────────────────────────────────────────────────────────
async function testAllRoutes() {
  log('Testing bridge routes...', 'info');
  
  var routes = [
    '/health',
    '/data',
    '/symbol',
    '/mt5/latest',
    '/mt5/price?symbol=EURUSD',
    '/mt5/klines?symbol=EURUSD&tf=H1&count=10',
    '/mt5/current-chart',
    '/analysis',
    '/indicators',
    '/economic-events',
    '/mapping/list'
  ];
  
  var passed = 0;
  for (var i = 0; i < routes.length; i++) {
    var r = routes[i];
    var result = await fetchAPI(r);
    if (result && result.ok) {
      log(`✅ ${r}`, 'info');
      passed++;
    } else {
      log(`⚠️ ${r}`, 'warning');
    }
  }
  
  log(`Routes: ${passed}/${routes.length} OK`, passed === routes.length ? 'info' : 'warning');
}

// ── EVENT LISTENERS ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  // Buttons
  document.getElementById('btn-refresh')?.addEventListener('click', async function() {
    log('Refreshing...', 'info');
    await syncFromExtensionSnapshot();
    await loadChart();
  });
  
  document.getElementById('btn-analyze')?.addEventListener('click', async function() {
    log('Analyzing...', 'info');
    await loadInstantTrade();
    await validateSymbol(state.symbol.replace('/', '').toUpperCase());
    await loadAnalysis();
    await loadIndicators();
  });
  
  document.getElementById('btn-news')?.addEventListener('click', async function() {
    log('Loading events...', 'info');
    await loadEconomicEvents();
  });
  
  document.getElementById('btn-test-routes')?.addEventListener('click', testAllRoutes);

  document.getElementById('btn-toggle-tv')?.addEventListener('click', async function() {
    var next = !state.tvEnabled;
    var d = await patchBridgeConfig({ tradingviewEnabled: next, updatedBy: 'studio-simple' });
    if (d && d.ok && d.bridgeConfig) {
      state.tvEnabled = d.bridgeConfig.tradingviewEnabled !== false;
      setToggleButtonState();
      log('TradingView ' + (state.tvEnabled ? 'ON' : 'OFF'), 'info');
    } else {
      log('Échec toggle TradingView', 'error');
    }
  });

  document.getElementById('btn-toggle-mt5')?.addEventListener('click', async function() {
    var next = !state.mt5Enabled;
    var d = await patchBridgeConfig({ mt5Enabled: next, updatedBy: 'studio-simple' });
    if (d && d.ok && d.bridgeConfig) {
      state.mt5Enabled = d.bridgeConfig.mt5Enabled === true;
      setToggleButtonState();
      log('MT5 ' + (state.mt5Enabled ? 'ON' : 'OFF'), 'info');
    } else {
      log('Échec toggle MT5', 'error');
    }
  });
  
  document.getElementById('btn-debug')?.addEventListener('click', async function() {
    log(`Symbol: ${state.symbol}`, 'info');
    log(`Timeframe: ${state.timeframe}`, 'info');
    log(`Mode: ${state.mode}`, 'info');
    var health = await fetchAPI('/health');
    if (health) log(`Bridge: ${health.status || 'OK'}`, 'info');
  });
  
  document.getElementById('btn-clear-logs')?.addEventListener('click', function() {
    state.logs = [];
    var panel = document.getElementById('log-panel');
    if (panel) panel.innerHTML = '';
    log('Logs cleared', 'info');
  });
  
  document.getElementById('btn-toggle-mode')?.addEventListener('click', function() {
    state.mode = state.mode === 'manual' ? 'auto' : 'manual';
    saveState();
    var btn = document.getElementById('btn-toggle-mode');
    if (btn) btn.textContent = state.mode === 'auto' ? '🤖 Mode Auto' : '👤 Mode Manual';
    log(`Mode: ${state.mode.toUpperCase()}`, 'info');
  });
  
  // Symbol selector
  document.getElementById('symbol-select')?.addEventListener('change', function(e) {
    // Source of truth is TradingView extension. Revert manual changes.
    var sel = document.getElementById('symbol-select');
    if (sel) sel.value = state.symbol;
    log('Symbole piloté par TradingView (miroir strict)', 'warning');
  });
  
  // Timeframe buttons
  document.querySelectorAll('.tfbtn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      // Timeframe follows TradingView only.
      document.querySelectorAll('.tfbtn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tf === state.timeframe);
      });
      log('Timeframe piloté par TradingView (miroir strict)', 'warning');
    });
  });
  
  // Initialize
  log('Studio initializing...', 'info');
  loadState();
  
  // Set UI state
  var symSel = document.getElementById('symbol-select');
  if (symSel) symSel.value = state.symbol;
  
  document.querySelectorAll('.tfbtn').forEach(function(btn) {
    if (btn.dataset.tf === state.timeframe) {
      btn.classList.add('active');
    }
  });
  
  var modeBtn = document.getElementById('btn-toggle-mode');
  if (modeBtn) modeBtn.textContent = state.mode === 'auto' ? '🤖 Mode Auto' : '👤 Mode Manual';
  setToggleButtonState();
  
  // Wait for LightweightCharts
  var lwWait = setInterval(function() {
    if (typeof LightweightCharts !== 'undefined') {
      clearInterval(lwWait);
      
      initChart();
      checkBridge();
      syncFromExtensionSnapshot();
      loadChart();
      loadInstantTrade();
      validateSymbol(state.symbol.replace('/', '').toUpperCase());

      // Auto-refresh — guarded by _serverOnline flag
      setInterval(checkBridge, 10000);
      setInterval(function() { if (_serverOnline) syncFromExtensionSnapshot(); }, 3000);
      setInterval(function() { if (_serverOnline) loadChart(); }, 5000);
      setInterval(function() { if (_serverOnline) loadInstantTrade(); }, 15000);
      
      log('Studio ready ✅', 'info');
    }
  }, 100);
});
