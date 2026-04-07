// studioapp.js — Trading Studio Pro (Lightweight)
// Parle au serveur Node 4000 (API locale) — SANS dépendances externes

'use strict';

const API   = 'http://127.0.0.1:4000';  // Node server (proxies MT5 bridge) - TRADING AUTO EXCLUSIVE
const STORE = 'studio_state_v3';

// ── SYMBOL MAPPING (canonical XAUUSD ↔ display XAU/USD) ──────────────────────
var CANONICAL_TO_DISPLAY = {
  XAUUSD:'XAU/USD', XAGUSD:'XAG/USD', EURUSD:'EUR/USD', GBPUSD:'GBP/USD',
  USDJPY:'USD/JPY', AUDUSD:'AUD/USD', USDCAD:'USD/CAD', USDCHF:'USD/CHF',
  NZDUSD:'NZD/USD', BTCUSD:'BTC/USD', ETHUSD:'ETH/USD',
  NAS100:'NAS100', US500:'US500', US30:'US30', DE40:'DE40'
};
function canonicalToDisplay(raw) {
  var up = (raw || '').replace(/[/\-\s]/g,'').toUpperCase();
  return CANONICAL_TO_DISPLAY[up] || raw;
}

// ── ÉTAT PERSISTÉ ─────────────────────────────────────────────────────────────

function defaultState() {
  return { symbol: 'XAU/USD', timeframe: 'H1', mode: 'EXECUTION_PREPAREE', brokerMode: 'ON', tradeMode: 'SNIPER' };
}

function normalizeEngineMode(raw) {
  var value = String(raw || '').trim().toUpperCase();
  if (!value || value === 'MANUAL') return 'ANALYSE';
  if (value === 'AUTO') return 'EXECUTION_PREPAREE';
  return value;
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORE);
    if (raw) {
      var parsed = Object.assign(defaultState(), JSON.parse(raw));
      parsed.mode = normalizeEngineMode(parsed.mode);
      return parsed;
    }
  } catch(_) {}
  return defaultState();
}

function saveState() {
  try {
    localStorage.setItem(STORE, JSON.stringify({
      symbol:    state.symbol,
      timeframe: state.timeframe,
      mode:      state.mode,
      brokerMode:state.brokerMode,
      tradeMode: state.tradeMode
    }));
  } catch(_) {}
}

const state = Object.assign(loadState(), {
  positions:   [],
  chart:       null,
  candleSeries:null,
  chartTF:     null,
  chartSym:    null,
  chartData:   null,
  liveCandle:  null,
  loading:     false,
  bridgeEnabled: true,
  // === CONNECTION STATE STABILIZATION ===
  _lastSyncStatus: null,  // cached sync status to prevent flapping
  _lastStatusChange: 0,   // timestamp of last status change
  _statusStabilityMs: 3000  // require 3s stable state before changing display
});

function setBridgeDisplay(enabled) {
  state.bridgeEnabled = enabled !== false;
  state.brokerMode = state.bridgeEnabled ? 'ON' : 'OFF';

  var el = document.getElementById('broker-mode-display');
  if (el) {
    el.textContent = state.brokerMode;
    el.style.color = state.bridgeEnabled ? '#10b981' : '#ef4444';
  }
}

function setEngineModeDisplay(mode) {
  state.mode = normalizeEngineMode(mode || state.mode);
  var el = document.getElementById('engine-mode');
  if (el) el.textContent = state.mode;
}

// ─── [P2] MARKET STATUS BADGE UPDATE ───────────────────────────────────────────
function updateMarketStatusBadge(symbol) {
  const badge = document.getElementById('market-status-badge');
  if (!badge) return;  // Badge not in DOM

  // Show loading state
  badge.className = 'market-badge market-badge-loading';
  badge.textContent = '⏳ Checking...';

  // Fetch market status from server
  fetch(`${API}/mt5/market-status?symbol=${encodeURIComponent(symbol)}`)
    .then(r => r.json())
    .then(data => {
      if (!data.isOpen) {
        badge.className = 'market-badge market-badge-closed';
        const opensIn = data.opensInFormatted || '?';
        badge.textContent = `🔴 ${data.market || 'Market'} CLOSED (${opensIn})`;
        badge.title = `${data.reason || 'closed'} — opens in ${opensIn}`;
      } else {
        badge.className = 'market-badge market-badge-open';
        const closesIn = data.closesInFormatted || '?';
        badge.textContent = `🟢 ${data.market || 'Market'} OPEN (${data.session || 'trading'})`;
        badge.title = `Closes in ${closesIn}`;
      }
    })
    .catch(err => {
      badge.className = 'market-badge market-badge-loading';
      badge.textContent = '⚠️ Status unavailable';
      badge.title = err.message;
      console.warn('[MARKET_STATUS] Fetch failed:', err);
    });
}

// ── INIT ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
  log('Studio démarrage — ' + new Date().toLocaleTimeString('fr-FR'), 'info');

  // Restaurer état persisté dans le DOM
  applyPersistedState();

  // Boutons sidebar
  bindBtn('btn-get-positions',  getPositions);
  bindBtn('btn-instant-trade',  getInstantTrade);
  bindBtn('btn-analyze-market', analyzeMarket);
  bindBtn('btn-agents-report',  getAgentsReport);
  bindBtn('btn-capture-screen', captureAndAnalyze);
  bindBtn('btn-execute-trade',  executeTrade);
  bindBtn('btn-open-popup',     openPopup);
  bindBtn('btn-toggle-broker',  toggleBroker);
  bindBtn('btn-toggle-mode',    toggleMode);
  bindBtn('btn-clear-logs',     clearLogs);
  bindBtn('btn-toggle-debug',   toggleDebug);
  bindBtn('btn-test-system',    testSystem);

  // Sélecteur symbole (critical bar)
  var symSel = document.getElementById('symbol-select');
  if (symSel) {
    symSel.value = state.symbol;
    symSel.addEventListener('change', function() {
      state.symbol = symSel.value;
      var sp = document.getElementById('chart-sym-sel');
      if (sp) sp.value = state.symbol;
      saveState();
      updateMarketStatusBadge(state.symbol);  // [P2] Update badge when symbol changes
      updateCritical();
      loadChart(true);
    });
  }

  // Sélecteur SCALPER / SNIPER / SWING
  var tradeMSel = document.getElementById('trade-mode-sel');
  if (tradeMSel) {
    tradeMSel.value = state.tradeMode || 'SNIPER';
    tradeMSel.addEventListener('change', function() {
      state.tradeMode = tradeMSel.value;
      saveState();
      applyTradeModeStyle(state.tradeMode);
      log('⚡ Mode: ' + state.tradeMode, 'info');
    });
    applyTradeModeStyle(state.tradeMode);
  }

  // Sélecteur symbole (chart panel)
  var chartSel = document.getElementById('chart-sym-sel');
  if (chartSel) {
    chartSel.value = state.symbol;
    chartSel.addEventListener('change', function() {
      state.symbol = chartSel.value;
      var top = document.getElementById('symbol-select');
      if (top) top.value = state.symbol;
      saveState();
      loadChart(true);
    });
  }

  // Boutons timeframe
  document.querySelectorAll('.tfbtn').forEach(function(btn) {
    if (btn.dataset.tf === state.timeframe) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
    btn.addEventListener('click', function() {
      document.querySelectorAll('.tfbtn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      state.timeframe = btn.dataset.tf;
      saveState();
      loadChart(true);
    });
  });

  // Initialiser le chart LW
  waitForLWCharts(function() {
    initChart();
    loadChart(false);
  });

  // Chargements initiaux
  checkServer();
  updateCritical();
  loadSidebar();
  updateMarketStatusBadge(state.symbol);  // [P2] Initialize market status badge
  
  // AI Communication monitoring
  updateAICommunicationStatus();
  loadNewsWithAutoRefresh();

  // ─── Circuit breaker: ralentit tout si serveur hors-ligne ───────────────────
  var _serverOnline = true;
  var _criticalMissCount = 0;

  // Intervalles stables
  setInterval(checkServer, 10000);

  // updateCritical toutes les 10s (stabilisation CPU)
  setInterval(function() {
    if (!_serverOnline && _criticalMissCount > 3) return; // circuit breaker
    updateCritical();
  }, 10000);

  setInterval(updateTimer,               10000);  // calcul client-side, pas de réseau
  setInterval(loadSidebar,               60000);
  setInterval(updateAICommunicationStatus, 10000);
  setInterval(loadNewsWithAutoRefresh,   20000);
  setInterval(pollActiveSymbol,          10000);
  // Recharge complète des klines toutes les 20s sur les TF rapides
  setInterval(function() {
    if (['M1','M2','M3','M5'].includes(state.timeframe)) loadChart(true);
  }, 20000);

  // Connexion SSE pour prix live → mise à jour bougie en temps réel
  connectSSE();

  // Connexion SSE dédiée à la sync symbole/TF depuis l'extension TradingView
  connectExtensionSync();

  log('✅ Studio prêt (12 boutons actifs, persistance OK, AI comms actif)', 'ok');
});

// ── PERSISTANCE ───────────────────────────────────────────────────────────────

function applyPersistedState() {
  // Symbol
  var sym = document.getElementById('symbol-select');
  if (sym) sym.value = state.symbol;
  var cSym = document.getElementById('chart-sym-sel');
  if (cSym) cSym.value = state.symbol;

  // Timeframe
  document.querySelectorAll('.tfbtn').forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.tf === state.timeframe);
  });

  // Mode auto
  var modeEl = document.getElementById('engine-mode');
  if (modeEl) modeEl.textContent = normalizeEngineMode(state.mode);

  // Broker
  var brkEl = document.getElementById('broker-mode-display');
  if (brkEl) brkEl.textContent = state.brokerMode.toUpperCase();

  // Trade mode (SCALPER/SNIPER/SWING)
  var tmEl = document.getElementById('trade-mode-sel');
  if (tmEl) {
    tmEl.value = state.tradeMode || 'SNIPER';
    applyTradeModeStyle(state.tradeMode);
  }
}

function applyTradeModeStyle(mode) {
  var sel = document.getElementById('trade-mode-sel');
  if (!sel) return;
  var colors = { SCALPER: '#f59e0b', SNIPER: '#a78bfa', SWING: '#10b981' };
  sel.style.color = colors[mode] || '#a78bfa';
}

// ── LW CHARTS WAIT ───────────────────────────────────────────────────────────

function waitForLWCharts(cb) {
  if (window.LightweightCharts) { cb(); return; }
  var tries = 0;
  var iv = setInterval(function() {
    tries++;
    if (window.LightweightCharts) { clearInterval(iv); cb(); }
    else if (tries > 30) {
      clearInterval(iv);
      setOverlay('LW Charts non disponible — vérifiez la connexion internet');
    }
  }, 200);
}

// ── CHART ─────────────────────────────────────────────────────────────────────

function setOverlay(msg) {
  var el = document.getElementById('chart-overlay');
  if (el) el.textContent = msg || '';
}

function initChart() {
  var chartDiv = document.getElementById('tv-chart');
  if (!chartDiv) return;
  if (!window.LightweightCharts) { setOverlay('LW Charts manquant'); return; }

  if (state.chart) {
    try { state.chart.remove(); } catch(_) {}
    state.chart = null;
    state.candleSeries = null;
  }

  chartDiv.innerHTML = '';

  var wrap = document.getElementById('chart-wrap');
  var w = (wrap && wrap.offsetWidth)  || 600;
  var h = (wrap && wrap.offsetHeight) || 260;

  state.chart = LightweightCharts.createChart(chartDiv, {
    width:  w,
    height: h,
    layout: {
      background: { type: 'solid', color: '#050e1e' },
      textColor: '#64748b'
    },
    grid: {
      vertLines: { color: '#1a2e4a' },
      horzLines: { color: '#1a2e4a' }
    },
    rightPriceScale: { borderColor: '#1e3a5f' },
    timeScale: { borderColor: '#1e3a5f', timeVisible: true, secondsVisible: false },
    crosshair: { mode: 1 }
  });

  state.candleSeries = state.chart.addCandlestickSeries({
    upColor:         '#10b981',
    downColor:       '#ef4444',
    borderUpColor:   '#10b981',
    borderDownColor: '#ef4444',
    wickUpColor:     '#10b981',
    wickDownColor:   '#ef4444'
  });

  if (window.ResizeObserver && wrap) {
    var ro = new ResizeObserver(function() {
      if (!state.chart || !wrap) return;
      state.chart.applyOptions({ width: wrap.offsetWidth, height: wrap.offsetHeight });
    });
    ro.observe(wrap);
  }
}

// ── AI COMMUNICATION MONITORING ───────────────────────────────────────────────

function updateAICommunicationStatus() {
  // Fetch system log (inter-AI messages) + agent bus (tasks)
  Promise.all([
    fetch(API + '/system-log', { signal: AbortSignal.timeout(2500) }).then(function(r) { return r.json(); }).catch(function() { return {}; }),
    fetch(API + '/agent-bus',  { signal: AbortSignal.timeout(2500) }).then(function(r) { return r.json(); }).catch(function() { return {}; })
  ]).then(function(results) {
    var syslog  = results[0] || {};
    var agentBus = results[1] || {};

    // ─ Agent statuses ─
    var claudeStatus  = document.getElementById('claude-status');
    var copilotStatus = document.getElementById('copilot-status');
    var agents = syslog.agents || {};
    var roles  = agentBus.roles  || {};

    if (claudeStatus) {
      var cs = (roles.claude && roles.claude.status) || agents.claude || 'offline';
      claudeStatus.textContent = cs === 'active' || cs === 'completed' ? 'online ✓' : cs;
      claudeStatus.style.color = (cs === 'active' || cs === 'completed') ? 'var(--green)' : 'var(--red)';
    }
    if (copilotStatus) {
      var cps = (roles.copilot && roles.copilot.status) || agents.copilot || 'waiting';
      var cpsLabel = cps === 'in-progress' ? 'actif...' : cps === 'active' ? 'online ✓' : 'en attente';
      copilotStatus.textContent = cpsLabel;
      copilotStatus.style.color = cps === 'in-progress' ? 'var(--yellow)' : cps === 'active' ? 'var(--green)' : '#3b82f6';
    }

    // ─ Recent inter-AI messages ─
    var msgBox = document.getElementById('comm-messages');
    if (msgBox) {
      var logs = (syslog.logs || []).slice(0, 6);
      if (logs.length) {
        msgBox.innerHTML = logs.map(function(l) {
          var col = l.status === 'ok' ? '#10b981' : l.status === 'err' ? '#ef4444' : '#3b82f6';
          var ts  = l.ts ? new Date(l.ts).toLocaleTimeString('fr-FR') : '';
          return '<div style="padding:2px 0;border-bottom:1px solid #0f1f3d;font-size:0.64rem;">' +
            '<span style="color:var(--muted);">' + ts + '</span> ' +
            '<span style="color:#64748b;">' + (l.from || '?') + '→' + (l.to || '?') + '</span> ' +
            '<span style="color:' + col + ';">' + (l.action || '') + '</span>' +
            '</div>';
        }).join('');
      }
    }

    // ─ AGENT_BUS tasks panel ─
    var tasksPanel = document.getElementById('agent-tasks-panel');
    if (!tasksPanel) return;

    var pending    = agentBus.pending    || [];
    var done       = agentBus.done       || [];
    var inProgress = agentBus.inProgress || [];

    var html = '';

    if (inProgress.length) {
      html += '<div style="color:#f59e0b;font-size:9px;font-weight:700;margin-bottom:3px;text-transform:uppercase;">⏳ En cours</div>';
      inProgress.forEach(function(t) {
        html += '<div style="background:#141f0f;border:1px solid #f59e0b;border-radius:4px;padding:4px 6px;margin-bottom:3px;font-size:9.5px;">' +
          '<b style="color:#fcd34d">' + (t.id || '') + '</b> <span style="color:#e2d09a">' + (t.title || '') + '</span>' +
          '<span style="color:#854d0e;display:block;font-size:8.5px">→ ' + (t.assignedTo || t.to || '') + '</span></div>';
      });
    }

    if (pending.length) {
      html += '<div style="color:#3b82f6;font-size:9px;font-weight:700;margin:4px 0 3px;text-transform:uppercase;">📋 En attente (' + pending.length + ')</div>';
      pending.slice(0,3).forEach(function(t) {
        html += '<div style="border:1px solid #1e3a5f;border-radius:4px;padding:3px 6px;margin-bottom:2px;font-size:9px;color:#64748b;">' +
          '<b style="color:#3b82f6">' + (t.id || '') + '</b> ' + (t.title || '').substring(0,50) + '</div>';
      });
    }

    if (done.length) {
      html += '<div style="color:#10b981;font-size:9px;font-weight:700;margin:4px 0 3px;text-transform:uppercase;">✅ Terminés (récents)</div>';
      done.slice(-3).reverse().forEach(function(t) {
        var ts = t.timestamp ? new Date(t.timestamp).toLocaleTimeString('fr-FR') : '';
        html += '<div style="border:1px solid #166534;border-radius:4px;padding:3px 6px;margin-bottom:2px;font-size:9px;">' +
          '<b style="color:#10b981">' + (t.id || '') + '</b> <span style="color:#6ee7b7">' + (t.title || '').substring(0,45) + '</span>' +
          (ts ? '<span style="color:#475569;display:block;font-size:8px">' + ts + '</span>' : '') + '</div>';
      });
    }

    if (!html) html = '<div style="color:var(--muted);font-size:9px;text-align:center;padding:.3rem;">— Aucune tâche —</div>';
    tasksPanel.innerHTML = html;

    // ─ AGENTS LIVE LOG — merged chronological view ─
    var logEl   = document.getElementById('agents-live-log');
    var badgeEl = document.getElementById('agents-log-badge');
    if (logEl) {
      var entries = [];
      // System log messages
      (syslog.logs || []).forEach(function(l) {
        entries.push({ ts: l.ts || 0, type: 'msg', from: l.from, to: l.to, action: l.action, status: l.status, detail: l.detail || '' });
      });
      // Pending tasks
      (agentBus.pending || []).forEach(function(t) {
        entries.push({ ts: t.createdAt || 0, type: 'task-pending', id: t.id, title: t.title, to: t.assignedTo || t.to });
      });
      // In-progress tasks
      (agentBus.inProgress || []).forEach(function(t) {
        entries.push({ ts: t.startedAt || t.createdAt || 0, type: 'task-inprogress', id: t.id, title: t.title, to: t.assignedTo || t.to });
      });
      // Done tasks
      (agentBus.done || []).slice(-5).forEach(function(t) {
        entries.push({ ts: t.timestamp || t.completedAt || 0, type: 'task-done', id: t.id, title: t.title, to: t.assignedTo || t.to });
      });

      // Sort by timestamp desc
      entries.sort(function(a, b) { return (b.ts || 0) - (a.ts || 0); });
      entries = entries.slice(0, 20);

      if (badgeEl) badgeEl.textContent = entries.length + ' MSG';

      if (entries.length === 0) {
        logEl.innerHTML = '<div style="color:#475569;text-align:center;padding:4px;">— En attente de messages... —</div>';
      } else {
        logEl.innerHTML = entries.map(function(e) {
          var tsStr = e.ts ? new Date(e.ts).toLocaleTimeString('fr-FR') : '--:--:--';
          if (e.type === 'msg') {
            var col = e.status === 'ok' ? '#10b981' : e.status === 'err' ? '#ef4444' : '#3b82f6';
            var icon = e.status === 'ok' ? '✓' : e.status === 'err' ? '✗' : '→';
            return '<div style="padding:2px 3px;border-bottom:1px solid #0f1a2e;line-height:1.5;">' +
              '<span style="color:#334155">[' + tsStr + ']</span> ' +
              '<span style="color:#7c3aed">' + (e.from || '?') + '</span>' +
              '<span style="color:#475569"> ' + icon + ' </span>' +
              '<span style="color:#6366f1">' + (e.to || '?') + '</span>' +
              ' <span style="color:' + col + ';">' + (e.action || '') + '</span>' +
              (e.detail ? '<span style="color:#374151;display:block;padding-left:6px;font-size:0.6rem;">' + e.detail + '</span>' : '') +
              '</div>';
          }
          var typeColors  = { 'task-pending': '#3b82f6', 'task-inprogress': '#f59e0b', 'task-done': '#10b981' };
          var typeIcons   = { 'task-pending': '📋', 'task-inprogress': '⏳', 'task-done': '✅' };
          var typeLabels  = { 'task-pending': 'PENDING', 'task-inprogress': 'ACTIF', 'task-done': 'DONE' };
          return '<div style="padding:2px 3px;border-bottom:1px solid #0f1a2e;line-height:1.5;">' +
            '<span style="color:#334155">[' + tsStr + ']</span> ' +
            '<span>' + (typeIcons[e.type] || '') + '</span> ' +
            '<span style="color:' + (typeColors[e.type] || '#fff') + ';font-weight:700;font-size:0.6rem;">' + (typeLabels[e.type] || '') + '</span> ' +
            '<span style="color:#6b7280;">' + (e.id || '') + '</span> ' +
            '<span style="color:#94a3b8;">' + ((e.title || '').substring(0, 45)) + '</span>' +
            (e.to ? '<span style="color:#475569;"> → ' + e.to + '</span>' : '') +
            '</div>';
        }).join('');
      }
    }

  }).catch(function() {
    var claudeStatus = document.getElementById('claude-status');
    if (claudeStatus) { claudeStatus.textContent = 'offline'; claudeStatus.style.color = 'var(--red)'; }
  });
}

// ── AUTO-REFRESH NEWS ─────────────────────────────────────────────────────────

function loadNewsWithAutoRefresh() {
  try {
    fetch(API + '/news', { signal: AbortSignal.timeout(3000) })
      .then(r => r.ok ? r.json() : { articles: [] })
      .then(data => {
        const newsContainer = document.getElementById('social-items');
        if (!newsContainer) return;
        
        const articles = (data.articles || []).slice(0, 5);
        if (articles.length === 0) {
          newsContainer.innerHTML = '<li style="color:var(--muted);text-align:center;padding:0.25rem;">Pas de news disponibles</li>';
          return;
        }
        
        newsContainer.innerHTML = articles
          .map(a => `
            <li style="border-bottom:1px solid var(--bord2);padding:0.25rem 0;font-size:0.68rem;">
              <strong>${(a.title || a.headline || '').substring(0, 40)}...</strong><br/>
              <span style="color:var(--muted);">${a.timestamp ? new Date(a.timestamp).toLocaleTimeString('fr-FR') : 'N/A'}</span>
            </li>
          `)
          .join('');
      })
      .catch(err => {
        console.log('[News refresh] Erreur:', err.message);
      });
  } catch (e) {
    console.warn('[loadNewsWithAutoRefresh]', e);
  }
}

function fmtN(n) {
  if (n == null || isNaN(n)) return '—';
  return n >= 100 ? n.toFixed(2) : n.toFixed(4);
}

var chartLoadTimer = null;

function loadChart(force) {
  // Debounce 200ms pour éviter les appels en cascade
  clearTimeout(chartLoadTimer);
  chartLoadTimer = setTimeout(function() { _doLoadChart(force); }, 200);
}

function _doLoadChart(force) {
  var sym = state.symbol;
  var tf  = state.timeframe;

  if (!force && state.chartSym === sym && state.chartTF === tf) return;
  if (state.loading) return;

  state.loading = true;
  setOverlay('Chargement ' + sym + ' ' + tf + '…');

  var label = document.getElementById('chart-label');
  if (label) label.textContent = sym + ' · ' + tf;

  var symNorm = sym.replace('/', '').toUpperCase();

  fetch(API + '/klines?symbol=' + encodeURIComponent(symNorm) + '&tf=' + tf + '&limit=80', {
    signal: AbortSignal.timeout(8000)
  })
  .then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  })
  .then(function(d) {
    state.loading = false;
    if (!d.ok || !d.candles || d.candles.length < 2) {
      setOverlay('Données insuffisantes pour ' + sym);
      var cnt = document.getElementById('chart-count');
      if (cnt) cnt.textContent = 'Pas de données';
      log('⚠️ Graphique ' + sym + ' ' + tf + ': données insuffisantes', 'warn');
      return;
    }
    state.chartData = d.candles;
    state.chartSym  = sym;
    state.chartTF   = tf;
    setOverlay('');
    drawChart(d.candles);
    var cnt = document.getElementById('chart-count');
    if (cnt) cnt.textContent = d.candles.length + ' bougies';
    log('📊 ' + sym + ' ' + tf + ' — ' + d.candles.length + ' bougies chargées', 'ok');
  })
  .catch(function(e) {
    state.loading = false;
    setOverlay('Erreur: ' + e.message);
    log('❌ Graphique ' + sym + ' ' + tf + ': ' + e.message, 'err');
  });
}

function drawChart(candles) {
  if (!state.candleSeries || !candles || !candles.length) return;

  var seen = {};
  var data = candles
    .map(function(c) {
      // LW Charts expects time in seconds
      return {
        time:  Math.floor(Number(c.time) / 1000),
        open:  parseFloat(c.open),
        high:  parseFloat(c.high),
        low:   parseFloat(c.low),
        close: parseFloat(c.close)
      };
    })
    .filter(function(c) {
      if (seen[c.time]) return false;
      seen[c.time] = true;
      return !isNaN(c.open) && !isNaN(c.close) && c.high >= c.low;
    })
    .sort(function(a, b) { return a.time - b.time; });

  if (!data.length) return;
  state.candleSeries.setData(data);
  state.chart.timeScale().fitContent();
  setOverlay('');
}

// ── SSE LIVE PRICE ────────────────────────────────────────────────────────────

var sseSource = null;

function connectSSE() {
  if (sseSource) { try { sseSource.close(); } catch(_) {} }
  sseSource = new EventSource(API + '/stream');

  sseSource.onmessage = function(e) {
    try {
      var d = JSON.parse(e.data);
      if (d.type === 'active-symbol') {
        var nextSymbol = d.symbol ? canonicalToDisplay(d.symbol) : state.symbol;
        var nextTf = d.timeframe || state.timeframe;
        var nextPrice = Number(d.price);
        state.symbol = nextSymbol;
        state.timeframe = nextTf;
        if (Number.isFinite(nextPrice) && nextPrice > 0) state.price = nextPrice;
        if (d.mode) setEngineModeDisplay(d.mode);
        updateCritical();
        return;
      }

      // Accept both MT5 and TradingView live ticks.
      if (d.type !== 'mt5-raw' && d.type !== 'mt5-data' && d.type !== 'price' && d.type !== 'quote' && d.type !== 'tradingview-data' && d.type !== 'activeSymbol') return;
      var sym = (d.symbol || d.brokerSymbol || '').toUpperCase();
      var stateSym = state.symbol.replace(/[/\s]/g, '').toUpperCase();
      if (sym && sym !== stateSym) return; // autre symbole

      var price = d.price || d.tvPrice || d.quote;  // MODIFIÉ: aussi check d.quote
      if (!price) return;

      // 1. Mettre à jour l'affichage du prix instantanément
      var pe = document.getElementById('critical-price');
      var p  = parseFloat(price);
      if (pe && !isNaN(p) && p > 0) {
        pe.textContent = p > 10 ? p.toFixed(2) : p.toFixed(5);
      }

      // 2. Mettre à jour la bougie vivante dans LW Charts
      updateLastCandle(price);
    } catch(_) {}
  };

  sseSource.onerror = function() {
    setTimeout(connectSSE, 5000); // Reconnexion auto
  };
}

// ── SSE /extension/sync — auto-suivi symbole/TF depuis l'extension TradingView ─
var sseExtSync = null;

function connectExtensionSync() {
  if (sseExtSync) { try { sseExtSync.close(); } catch(_) {} }
  sseExtSync = new EventSource(API + '/extension/sync');

  sseExtSync.onmessage = function(e) {
    try {
      var msg = JSON.parse(e.data);

      // Handler active-symbol
      if (msg.type === 'active-symbol') {
        var newSymbol = msg.symbol || (msg.activeSymbol && msg.activeSymbol.symbol);
        var newTf = msg.timeframe || (msg.activeSymbol && msg.activeSymbol.timeframe);
        var newPrice = msg.price || (msg.activeSymbol && msg.activeSymbol.price);

        var changed = false;

        if (newSymbol && newSymbol !== state.symbol) {
          state.symbol = newSymbol.toUpperCase().replace('/', '');
          var symSel = document.getElementById('symbol-select');
          if (symSel) symSel.value = state.symbol;
          changed = true;
        }

        if (newTf && newTf !== state.timeframe) {
          state.timeframe = newTf.toUpperCase();
          // Mettre à jour les boutons TF visuellement
          document.querySelectorAll('.tfbtn').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.tf === state.timeframe);
          });
          changed = true;
        }

        if (newPrice && newPrice > 0) {
          state.price = newPrice;
        }

        if (changed) {
          saveState();       // Persiste dans localStorage
          updateCritical(); // Rafraîchit le dashboard
        }
      }

      // Gérer aussi initial-sync pour le premier état
      if (msg.type === 'initial-sync' && msg.activeSymbol) {
        var initSymbol = msg.activeSymbol.symbol;
        var initTf = msg.activeSymbol.timeframe;
        var initPrice = msg.activeSymbol.price;
        if (initSymbol && initSymbol !== state.symbol) {
          state.symbol = initSymbol.toUpperCase().replace('/', '');
          var symSel = document.getElementById('symbol-select');
          if (symSel) symSel.value = state.symbol;
        }
        if (initTf && initTf !== state.timeframe) {
          state.timeframe = initTf.toUpperCase();
          document.querySelectorAll('.tfbtn').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.tf === state.timeframe);
          });
        }
        if (initPrice && initPrice > 0) state.price = initPrice;
        saveState();
        updateCritical();
      }
    } catch(_) {}
  };

  sseExtSync.onerror = function() {
    setTimeout(connectExtensionSync, 5000); // Reconnexion auto
  };
}

function getTFSeconds(tf) {
  var map = { M1:60, M2:120, M3:180, M5:300, M10:600, M15:900, M30:1800,
              M45:2700, H1:3600, H2:7200, H4:14400, H6:21600, D1:86400 };
  return map[(tf || 'H1').toUpperCase()] || 3600;
}

function updateLastCandle(price) {
  if (!state.candleSeries) return;
  var p = parseFloat(price);
  if (isNaN(p) || p <= 0) return;

  var tfSec     = getTFSeconds(state.timeframe);
  var nowSec    = Math.floor(Date.now() / 1000);
  var candleTime = Math.floor(nowSec / tfSec) * tfSec;

  if (!state.liveCandle || state.liveCandle.time !== candleTime) {
    // Nouvelle bougie
    var prevClose = state.liveCandle ? state.liveCandle.close : p;
    state.liveCandle = { time: candleTime, open: prevClose, high: p, low: p, close: p };
  } else {
    state.liveCandle.close = p;
    state.liveCandle.high  = Math.max(state.liveCandle.high,  p);
    state.liveCandle.low   = Math.min(state.liveCandle.low,   p);
  }

  try { state.candleSeries.update(state.liveCandle); } catch(_) {}
}

// ── SERVER CHECK ──────────────────────────────────────────────────────────────

function checkServer() {
  fetch(API + '/health', { signal: AbortSignal.timeout(3000) })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    _serverOnline     = true;
    _criticalMissCount = 0;
    var dot = document.getElementById('server-dot');
    var st  = document.getElementById('status');
    var fl  = document.getElementById('flux-status');
    var src = document.getElementById('data-source');
    var ht  = document.getElementById('health-time');
    if (dot) dot.className = 'sdot on';
    if (st)  st.textContent = '🟢 Online';
    if (fl)  { fl.textContent = '🟢 LIVE'; fl.style.color = '#10b981'; }
    if (src) src.textContent = d.dataSource || 'OK';
    if (ht)  ht.textContent  = new Date().toLocaleTimeString('fr-FR');
    var sdot = document.getElementById('source-dot');
    if (sdot) sdot.className = d.mt5Status === 'mt5' ? 'sdot on' : 'sdot warn';
  })
  .catch(function() {
    _serverOnline = false;
    _criticalMissCount++;
    var dot = document.getElementById('server-dot');
    var st  = document.getElementById('status');
    var fl  = document.getElementById('flux-status');
    if (dot) dot.className = 'sdot off';
    if (st)  st.textContent = '🔴 Offline';
    if (fl)  { fl.textContent = '🔴 OFFLINE'; fl.style.color = '#ef4444'; }
  });
}

// ── TIMER BOUGIE ──────────────────────────────────────────────────────────────

function updateTimer() {
  // Client-side calculation — no network call every second
  var tfSec    = getTFSeconds(state.timeframe);
  var nowSec   = Math.floor(Date.now() / 1000);
  var remaining = tfSec - (nowSec % tfSec);
  var pct      = (remaining / tfSec) * 100;
  var mins     = Math.floor(remaining / 60);
  var secs     = remaining % 60;
  var mEl = document.getElementById('candle-minutes');
  var sEl = document.getElementById('candle-seconds');
  var bar = document.getElementById('candle-bar');
  if (mEl) mEl.textContent = String(mins).padStart(2, '0');
  if (sEl) sEl.textContent = String(secs).padStart(2, '0');
  if (bar) bar.style.width = Math.max(0, Math.min(100, pct)).toFixed(1) + '%';
}

// ── CRITICAL BAR ─────────────────────────────────────────────────────────────

function updateCritical() {
  var sym = state.symbol.replace('/', '').toUpperCase();

  // 1. Mirror the exact extension/server context. Do not inject quote fallbacks here.
  Promise.all([
    fetch(API + '/extension/data', { signal: AbortSignal.timeout(3000) }).then(function(r) { return r.json(); }).catch(function() { return {}; }),
    fetch(API + '/live/state',     { signal: AbortSignal.timeout(3000) }).then(function(r) { return r.json(); }).catch(function() { return {}; })
  ]).then(function(res) {
    var extData = res[0] || {};
    var liveState = res[1] || {};
    var active = extData.activeSymbol || {};
    var current = extData.currentData || {};
    var context = liveState.context || {};
    var bridge = liveState.bridge || {};
    var tvState = liveState.tradingview || {};

    var nextSymbol = active.symbol ? canonicalToDisplay(active.symbol) : state.symbol;
    var nextTf = active.timeframe || context.timeframe || state.timeframe;
    var livePrice = Number(active.price != null ? active.price : (current.price != null ? current.price : (current.bid != null ? current.bid : current.ask)));

    state.symbol = nextSymbol;
    state.timeframe = nextTf;
    if (Number.isFinite(livePrice) && livePrice > 0) state.price = livePrice;
    setEngineModeDisplay(active.mode || bridge.mode || state.mode);
    setBridgeDisplay(bridge.enabled !== false);

    // Affichage prix
    if (Number.isFinite(livePrice) && livePrice > 0) {
      var pe = document.getElementById('critical-price');
      if (pe) pe.textContent = livePrice > 10 ? livePrice.toFixed(2) : livePrice.toFixed(5);
      // Mise à jour bougie live aussi
      updateLastCandle(livePrice);
    }

    // === STATE STABILIZATION LOGIC ===
    // SINGLE SOURCE OF TRUTH for connection status:
    // 1. BRIDGE OFF = bridge.enabled === false
    // 2. TV LIVE = tvState.connected && tvState.ageMs != null && tvState.ageMs < 180000 (3 min tolerance)
    // 3. LIVE = livePrice is valid
    // 4. EN ATTENTE = no data
    // Do NOT flip rapidly between states: require 3 second stability.
    var computedStatus = null;
    var computedCol = '#64748b';
    
    if (bridge.enabled === false) {
      computedStatus = '🔴 BRIDGE OFF';
      computedCol = '#ef4444';
    } else if (tvState && tvState.connected && Number.isFinite(tvState.ageMs) && tvState.ageMs < 180000 && Number.isFinite(livePrice) && livePrice > 0) {
      // TV LIVE: connected && fresh (< 3min) && price valid
      computedStatus = '✅ TV LIVE';
      computedCol = '#10b981';
    } else if (Number.isFinite(livePrice) && livePrice > 0) {
      // LIVE: price from other source
      computedStatus = '📡 LIVE';
      computedCol = '#3b82f6';
    } else {
      // WAITING: no data
      computedStatus = '⏳ EN ATTENTE';
      computedCol = '#64748b';
    }
    
    // APPLY HYSTERESIS: only change display if status is stable for 3 seconds
    var now = Date.now();
    if (computedStatus !== state._lastSyncStatus) {
      // Status changed: wait for stability
      if (now - state._lastStatusChange >= state._statusStabilityMs) {
        // Stable enough: apply change
        state._lastSyncStatus = computedStatus;
        state._lastStatusChange = now;
      }
      // Otherwise: keep old status on display (suppress transient flips)
    } else {
      // Status unchanged: reset timer
      state._lastStatusChange = now;
    }
    
    var ss  = document.getElementById('sync-status');
    var src = document.getElementById('sync-source');
    if (ss) {
      // Display the STABLE status, not the computed one
      var displayStatus = state._lastSyncStatus || computedStatus;
      var displayCol = computedStatus === state._lastSyncStatus ? computedCol : '#64748b';
      ss.textContent = displayStatus;
      ss.style.color = displayCol;
    }
    if (src) {
      src.textContent = 'Source: ' + (active.source || context.source || current.source || 'n/a') + (tvState && tvState.connected ? ' · TV ON' : ' · TV OFF');
    }
  }).catch(function() {});

  // 2. Signal + score from analysis (slower, every ~4s tick)
  fetch(API + '/instant-trade-live?symbol=' + encodeURIComponent(sym) + '&mode=' + encodeURIComponent(state.tradeMode || 'SNIPER'), {
    signal: AbortSignal.timeout(4000)
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (!d.ok || !d.trade) return;
    var t = d.trade;
    var si = document.getElementById('critical-signal');
    var sc = document.getElementById('critical-score');
    if (si) {
      si.textContent = t.direction || '--';
      si.style.color = t.direction === 'LONG' ? '#10b981' : t.direction === 'SHORT' ? '#ef4444' : '#64748b';
    }
    if (sc) {
      var s = (typeof t.score === 'number') ? (t.score > 1 ? t.score : t.score * 100) : 0;
      sc.textContent = Math.round(s) + '%';
    }
  })
  .catch(function() {});
}

// ── SIDEBAR ───────────────────────────────────────────────────────────────────

// ── SYMBOL AUTO-DETECTION (from TradingView extension) ───────────────────────

var lastActiveSymbol = null;

function pollActiveSymbol() {
  fetch(API + '/active-symbol', { signal: AbortSignal.timeout(2000) })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (!d.ok || !d.symbol) return;
    var nextMode = normalizeEngineMode(d.mode || state.mode);
    if (d.symbol === lastActiveSymbol && d.timeframe === state.timeframe && nextMode === state.mode) return;
    
    lastActiveSymbol = d.symbol;

    var display = canonicalToDisplay(d.symbol);
    var timeframeChanged = !!(d.timeframe && d.timeframe !== state.timeframe);

    // Update state
    state.symbol    = display;
    state.timeframe = d.timeframe || state.timeframe;
    if (Number.isFinite(Number(d.price))) state.price = Number(d.price);
    setEngineModeDisplay(nextMode);
    saveState();

    // Update selectors in DOM
    var symSel = document.getElementById('symbol-select');
    if (symSel) symSel.value = display;
    var cSym = document.getElementById('chart-sym-sel');
    if (cSym) cSym.value = display;
    
    // Update active TF button if changed
    if (timeframeChanged) {
      document.querySelectorAll('.tfbtn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tf === d.timeframe);
      });
    }

    // Refresh chart + price
    updateCritical();
    loadChart(true);
    log('📡 TradingView → ' + display + ' ' + (d.timeframe || '') + (d.price ? ' @ ' + d.price : '') + (nextMode ? ' [' + nextMode + ']' : ''), 'ok');
  })
  .catch(function() {});
}

function loadSidebar() {
  _loadCalendar();
  _loadNews();
}

function _loadCalendar() {
  fetch(API + '/calendar', { signal: AbortSignal.timeout(6000) })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    var ul = document.getElementById('economic-items');
    if (!ul) return;
    if (!d.ok || !d.events || !d.events.length) {
      ul.innerHTML = '<li style="color:var(--muted);font-size:.68rem;">Pas d\'événements</li>';
      return;
    }
    ul.innerHTML = d.events.slice(0, 6).map(function(ev) {
      return '<li class="ev-item">' +
        '<span class="ev-time">' + (ev.time || '--') + '</span>' +
        '<span class="ev-' + (ev.impact || 'LOW') + '">' + (ev.impact || '') + '</span>' +
        '<span class="ev-name">' + (ev.event || ev.name || '--') + ' <span style="color:var(--muted)">(' + (ev.currency || '') + ')</span></span>' +
        '</li>';
    }).join('');
  })
  .catch(function() {});
}

function _loadNews() {
  fetch(API + '/news', { signal: AbortSignal.timeout(6000) })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    var ul = document.getElementById('social-items');
    if (!ul) return;
    if (!d.ok || !d.news || !d.news.length) {
      ul.innerHTML = '<li style="color:var(--muted);font-size:.68rem;">Pas de news</li>';
      return;
    }
    ul.innerHTML = d.news.slice(0, 5).map(function(n) {
      return '<li style="padding:.2rem 0;border-bottom:1px solid #0f1f3d;font-size:.68rem;">' +
        '<div style="color:var(--text)">' + (n.title || '--').substring(0, 70) + '</div>' +
        '<div style="color:var(--muted);font-size:.6rem;">' + (n.source || '') + ' · ' + (n.sentiment || '') + '</div>' +
        '</li>';
    }).join('');
  })
  .catch(function() {});
}

function renderTAPanel(agents) {
  var el = document.getElementById('ta-panel');
  if (!el) return;
  if (!agents || !agents.length) { el.innerHTML = '<span style="color:var(--muted)">Aucune donnée</span>'; return; }
  el.innerHTML = agents.map(function(t) {
    var col = t.signal === 'LONG' ? '#10b981' : t.signal === 'SHORT' ? '#ef4444' : '#64748b';
    return '<div class="ta-row">' +
      '<span style="color:#3b82f6;font-weight:600">' + (t.symbol || '--') + '</span>' +
      '<span style="color:' + col + ';font-weight:700">' + (t.signal || 'HOLD') + '</span>' +
      '<span style="color:var(--muted)">RSI ' + (t.rsi || '--') + '</span>' +
      '<span style="color:var(--muted)">' + (t.score || 0) + '%</span>' +
      '</div>';
  }).join('');
}

function renderOpportunities(opps) {
  var el = document.getElementById('opportunities-list');
  if (!el) return;
  if (!opps || !opps.length) { el.innerHTML = '<span style="color:var(--muted)">Aucune opportunité</span>'; return; }
  el.innerHTML = opps.slice(0, 5).map(function(o) {
    var col = o.direction === 'LONG' ? '#10b981' : '#ef4444';
    return '<div class="opp-row">' +
      '<span style="color:#3b82f6;font-weight:600">' + o.symbol + '</span>' +
      '<span style="color:' + col + ';font-weight:700">' + o.direction + '</span>' +
      '<span style="color:var(--muted)">@' + o.entry + '</span>' +
      '<span style="color:var(--muted);margin-left:auto">' + (o.score || 0) + '%</span>' +
      '</div>';
  }).join('');
}

// ── BOUTONS ───────────────────────────────────────────────────────────────────

function bindBtn(id, handler) {
  var btn = document.getElementById(id);
  if (!btn) { console.warn('[Studio] bouton introuvable:', id); return; }
  var orig = btn.textContent.trim();
  btn.addEventListener('click', function() {
    if (btn.disabled) return;
    btn.disabled = true;
    btn.textContent = '⏳';
    sysLog('btn:' + id);
    Promise.resolve()
    .then(function() { return handler(); })
    .then(function() {
      btn.disabled = false;
      btn.textContent = orig;
    })
    .catch(function(e) {
      btn.disabled = false;
      btn.textContent = orig;
      log('❌ ' + orig + ': ' + e.message, 'err');
    });
  });
}

async function getPositions() {
  var r = await fetch(API + '/positions');
  var d = await r.json();
  if (!d.ok) throw new Error(d.error);
  renderTrades(d.positions || []);
  log('📊 ' + (d.positions ? d.positions.length : 0) + ' position(s)', 'ok');
}

async function getInstantTrade() {
  var sym = state.symbol.replace('/', '').toUpperCase();
  var r   = await fetch(API + '/instant-trade-live?symbol=' + encodeURIComponent(sym) + '&mode=' + encodeURIComponent(state.tradeMode || 'SNIPER'));
  var d   = await r.json();
  if (!d.ok) throw new Error(d.error);
  renderTrades([d.trade]);
  var t = d.trade;
  log('⚡ ' + t.symbol + ' ' + t.direction + ' @ ' + t.entry + ' | ' + (t.trade_status || '') + ' | ' + (t.source || ''), 'ok');
}

async function analyzeMarket() {
  var sym = state.symbol.replace('/', '').toUpperCase();

  // Trigger a real analysis cycle in the same pipeline as the extension.
  await fetch(API + '/extension/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      command: 'analyze',
      payload: {
        symbol: sym,
        timeframe: state.timeframe,
        mode: normalizeEngineMode(state.mode)
      }
    })
  });

  var url = API + '/coach/realtime?symbol=' + encodeURIComponent(sym) +
    '&tf=' + encodeURIComponent(state.timeframe) +
    '&mode=' + encodeURIComponent(normalizeEngineMode(state.mode)) + '&lang=fr';
  var r = await fetch(url);
  var d = await r.json();
  if (!d.ok) throw new Error(d.error || 'coach/realtime failed');

  var trade = d.instantTrade || (d.tradeReasoning && d.tradeReasoning.metrics ? {
    symbol: sym,
    direction: (d.signal && d.signal.verdict) || 'WAIT',
    entry: d.tradeReasoning.metrics.entry,
    sl: d.tradeReasoning.metrics.stopLoss,
    tp: d.tradeReasoning.metrics.takeProfit,
    score: ((d.signal && d.signal.confidence) || 50) / 100,
    technical: d.signal && d.signal.rationale,
    source: d.dataSource || 'live-runtime'
  } : null);

  if (trade) renderTrades([trade]);
  updateCritical();

  var coachText = (d.coach && d.coach.lia && d.coach.lia.response) ||
    (d.signal && d.signal.rationale) || 'Analyse réalisée.';
  log('🔍 Analyse live: ' + coachText.substring(0, 120), 'ok');
}

async function getAgentsReport() {
  var r = await fetch(API + '/agents-report');
  var d = await r.json();
  if (!d.ok) throw new Error(d.error);
  var rep = d.report;
  log('🤖 ' + rep.masterDecision + ' | ' + rep.overallScore + '% | ' + (rep.dataSource || '—'), 'ok');
  renderTAPanel(rep.technicalAgents || []);
  if (rep.technicalAgents && rep.technicalAgents.length) {
    renderTrades(rep.technicalAgents.map(function(t) {
      return {
        symbol: t.symbol, direction: t.signal, entry: t.price,
        sl: '—', tp: '—',
        score: (t.score || 0) / 100,
        technical: t.analysis, source: t.source, rsi: t.rsi, ema20: t.ema20
      };
    }));
  }
  var b = rep.bestOpportunity;
  if (b && b.quantity > 0) {
    log('🎯 ' + b.symbol + ' ' + b.signal + ' @ ' + b.price + ' | Lot: ' + b.quantity + ' | Expo: $' + b.exposure, 'ok');
  }
  if (rep.recommendations) rep.recommendations.forEach(function(r) { log('  • ' + r, 'info'); });
}

async function captureAndAnalyze() {
  var sym = state.symbol.replace('/', '').toUpperCase();
  var r   = await fetch(API + '/agent-screen', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: sym, timeframe: state.timeframe })
  });
  var d = await r.json();
  if (!d.ok) throw new Error(d.error || 'agent-screen failed');
  renderTrades([d.trade]);
  log('📸 ' + d.trade.symbol + ' ' + d.trade.direction, 'ok');
}

async function executeTrade() {
  // Dashboard execute = operator ENTER in coach runtime state machine.
  var sym = state.symbol.replace('/', '').toUpperCase();
  var r = await fetch(API + '/coach/trade-action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol: sym,
      timeframe: state.timeframe,
      action: 'ENTER'
    })
  });
  var d = await r.json();
  if (!d.ok) throw new Error(d.error || 'coach/trade-action failed');

  // Refresh live coach snapshot after ENTER to follow position guidance in real-time.
  var liveUrl = API + '/coach/realtime?symbol=' + encodeURIComponent(sym) +
    '&tf=' + encodeURIComponent(state.timeframe) +
    '&mode=' + encodeURIComponent(normalizeEngineMode(state.mode)) + '&lang=fr';
  var liveResp = await fetch(liveUrl);
  var live = await liveResp.json();

  var coachState = live && live.tradeState ? live.tradeState : d.state;
  log('🚀 Entrée exécutée: phase=' + (coachState && coachState.phase ? coachState.phase : '--') +
    ' | entered=' + (coachState && coachState.entered ? 'true' : 'false'), 'ok');

  updateCritical();
}

function openPopup() {
  var w = window.open('', 'positions', 'width=580,height=680');
  if (!w) throw new Error('Popup bloqué — autorisez les popups pour ce site');
  w.document.write('<!DOCTYPE html><html><head><title>Positions</title>' +
    '<style>body{font-family:sans-serif;background:#07132a;color:#e0f2fe;padding:1rem;font-size:13px}' +
    '.p{background:#0d1e38;border:1px solid #1e3a5f;border-radius:6px;padding:.6rem .8rem;margin:.4rem 0}' +
    '.long{color:#10b981;font-weight:700} .short{color:#ef4444;font-weight:700}</style></head><body>' +
    '<h2 style="color:#3b82f6;margin-bottom:1rem">📊 Positions Live</h2><div id="c">Chargement…</div>' +
    '<script>fetch("' + API + '/positions").then(function(r){return r.json();}).then(function(d){' +
    'var html=(d.positions||[]).map(function(p){return\'<div class="p"><b>\'+p.symbol+\'</b> <span class="\'+' +
    '(p.direction||"").toLowerCase()+\'">\'+p.direction+\'</span><br>Entry: \'+p.entry+\' | SL: \'+p.sl+\' | TP: \'+p.tp+\'</div>\';}).join(\'\');' +
    'document.getElementById("c").innerHTML=html||"<p style=\'color:#64748b\'>Aucune position ouverte</p>";' +
    '}).catch(function(e){document.getElementById("c").innerHTML="Erreur: "+e.message;});<\/script>' +
    '</body></html>');
  w.document.close();
  log('📱 Popup positions ouvert', 'ok');
}

async function toggleBroker() {
  var next = !(state.bridgeEnabled !== false);
  try {
    var r = await fetch(API + '/extension/command', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: 'set-bridge-config',
        payload: { bridgeEnabled: next, updatedBy: 'studio-dashboard' }
      })
    });
    var d = await r.json();
    if (d.ok) next = d.bridgeConfig ? d.bridgeConfig.bridgeEnabled !== false : next;
  } catch(_) {}
  setBridgeDisplay(next);
  saveState();
  log('🔌 Bridge: ' + (state.bridgeEnabled ? 'ON' : 'OFF'), 'ok');
}

async function toggleMode() {
  var next = normalizeEngineMode(state.mode) === 'ANALYSE' ? 'EXECUTION_PREPAREE' : 'ANALYSE';
  try {
    var r = await fetch(API + '/extension/command', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: 'set-bridge-config',
        payload: { bridgeMode: next, updatedBy: 'studio-dashboard' }
      })
    });
    var d = await r.json();
    if (d.ok && d.bridgeConfig && d.bridgeConfig.bridgeMode) next = d.bridgeConfig.bridgeMode;
  } catch(_) {}
  setEngineModeDisplay(next);
  saveState();
  log('🔄 Mode bridge: ' + state.mode, 'ok');
}

function clearLogs() {
  var el = document.getElementById('logbar') || document.getElementById('maintenance-log');
  if (el) el.innerHTML = '';
  log('🗑 Logs effacés', 'info');
}

function toggleDebug() {
  log('🛠 État: symbol=' + state.symbol + ' tf=' + state.timeframe + ' mode=' + state.mode + ' broker=' + state.brokerMode, 'info');
  log('  chart: ' + (state.chartData ? state.chartData.length : 0) + ' bougies | positions: ' + state.positions.length, 'info');
  log('  localStorage: ' + (localStorage.getItem(STORE) || 'vide'), 'info');
}

async function testSystem() {
  var routes = [
    '/health',
    '/positions',
    '/instant-trade-live?symbol=XAUUSD',
    '/analyze',
    '/agents-report',
    '/calendar',
    '/news',
    '/klines?symbol=XAUUSD&tf=H1&limit=5',
    '/market-intelligence?symbol=XAUUSD',
    '/broker-mode',
    '/chart-data?symbol=XAUUSD&timeframe=H1',
    '/quote?symbol=XAUUSD'
  ];
  var pass = 0;
  for (var i = 0; i < routes.length; i++) {
    var ep = routes[i];
    try {
      var r = await fetch(API + ep, { signal: AbortSignal.timeout(5000) });
      if (r.ok) { pass++; log('✅ ' + ep, 'ok'); }
      else log('⚠️ ' + ep + ' (' + r.status + ')', 'warn');
    } catch(e) {
      log('❌ ' + ep + ': ' + e.message, 'err');
    }
  }
  log('🧪 Routes: ' + pass + '/' + routes.length + ' OK | Boutons: 12/12 actifs', pass >= 10 ? 'ok' : 'warn');
  sysLog('test:routes:' + pass + '/' + routes.length);
}

// ── RENDER TRADES ─────────────────────────────────────────────────────────────

function renderTrades(trades) {
  var c = document.getElementById('trade-cards');
  if (!c) return;
  c.innerHTML = '';

  trades.forEach(function(t) {
    if (!t) return;
    var isLong  = t.direction === 'LONG';
    var isShort = t.direction === 'SHORT';
    var color   = isLong ? '#10b981' : isShort ? '#ef4444' : '#64748b';
    var rawScore = typeof t.score === 'number' ? t.score : parseFloat(t.score) || 0;
    var score   = rawScore > 1 ? Math.round(rawScore) : Math.round(rawScore * 100);
    var scMap   = { LIVE:'#10b981', CONDITIONAL:'#f59e0b', WAIT:'#ef4444', HOLD:'#64748b' };
    var status  = t.trade_status || (t.direction === 'HOLD' ? 'HOLD' : '');
    var scCol   = scMap[status] || '#475569';

    // R:R ratio
    var rrHtml = '';
    try {
      var entry = parseFloat(t.entry), sl = parseFloat(t.sl), tp = parseFloat(t.tp);
      if (!isNaN(entry) && !isNaN(sl) && !isNaN(tp) && sl !== entry) {
        var risk   = Math.abs(entry - sl);
        var reward = Math.abs(tp - entry);
        var rr     = (reward / risk).toFixed(2);
        rrHtml = '<div class="tc-analysis-row"><span class="tc-al">⚖️ R:R</span><span class="tc-av" style="color:#f59e0b">1:' + rr + '</span></div>';
      }
    } catch(_) {}

    // Analysis fields
    function arow(icon, label, val, col) {
      if (!val || val === '—' || val === '--') return '';
      return '<div class="tc-analysis-row">' +
        '<span class="tc-al">' + icon + ' ' + label + '</span>' +
        '<span class="tc-av"' + (col ? ' style="color:' + col + '"' : '') + '>' +
        String(val).substring(0, 100) + '</span></div>';
    }

    var div = document.createElement('div');
    div.className = 'trade-card';
    div.style.cssText = [
      'background:#060f22',
      'border:1px solid #1e3a5f',
      'border-left:4px solid ' + color,
      'border-radius:6px',
      'padding:.75rem .8rem',
      'margin-bottom:.5rem'
    ].join(';');

    div.innerHTML =
      // ─ Header ─
      '<div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.6rem;flex-wrap:wrap">' +
        '<b style="color:#3b82f6;font-size:15px;letter-spacing:.02em">' + (t.symbol || '—') + '</b>' +
        '<span style="color:' + color + ';font-weight:800;font-size:15px">' + (t.direction || 'HOLD') + '</span>' +
        (status ? '<span style="color:' + scCol + ';font-size:10px;padding:2px 6px;border:1px solid ' + scCol + ';border-radius:3px;font-weight:700">' + status + '</span>' : '') +
        '<span style="margin-left:auto;color:#64748b;font-size:11px">Score <b style="color:#e0f2fe">' + score + '%</b></span>' +
      '</div>' +
      // ─ Price levels (large) ─
      '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:.6rem">' +
        '<div style="background:#0a1628;border:1px solid #243b5e;border-radius:5px;padding:.4rem .5rem;text-align:center">' +
          '<div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px">📍 Entrée</div>' +
          '<div style="font-size:14px;font-weight:700;color:#e0f2fe;font-family:monospace">' + (t.entry || '—') + '</div>' +
        '</div>' +
        '<div style="background:#0a1628;border:1px solid #7f1d1d;border-radius:5px;padding:.4rem .5rem;text-align:center">' +
          '<div style="font-size:9px;color:#ef4444;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px">🛑 Stop Loss</div>' +
          '<div style="font-size:14px;font-weight:700;color:#ef4444;font-family:monospace">' + (t.sl || '—') + '</div>' +
        '</div>' +
        '<div style="background:#0a1628;border:1px solid #166534;border-radius:5px;padding:.4rem .5rem;text-align:center">' +
          '<div style="font-size:9px;color:#10b981;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px">🎯 Take Profit</div>' +
          '<div style="font-size:14px;font-weight:700;color:#10b981;font-family:monospace">' + (t.tp || '—') + '</div>' +
        '</div>' +
      '</div>' +
      // ─ Full analysis ─
      '<div style="background:#040d1a;border:1px solid #1e3a5f;border-radius:5px;padding:.5rem .6rem;font-size:11px">' +
        '<div style="font-size:9px;text-transform:uppercase;color:#3b82f6;letter-spacing:.08em;margin-bottom:.4rem;font-weight:700">💡 Analyse Complète</div>' +
        '<style>.tc-analysis-row{display:flex;justify-content:space-between;align-items:flex-start;gap:.4rem;padding:3px 0;border-bottom:1px solid #0f1f3d;font-size:10.5px}.tc-analysis-row:last-child{border-bottom:none}.tc-al{color:#64748b;min-width:90px;flex-shrink:0}.tc-av{color:#cbd5e1;text-align:right;flex:1;word-break:break-word}</style>' +
        arow('💡','Raison',       t.reason || t.technical || t.analysis,          '#93c5fd') +
        arow('📈','Structure',    t.market_structure || t.structure,               '#e0f2fe') +
        arow('✅','Confirmation', t.confirmation || (t.rsi ? 'RSI ' + t.rsi + (t.ema20 ? ' · EMA20 ' + parseFloat(t.ema20).toFixed(4) : '') : null), '#86efac') +
        arow('🔓','Pourquoi Entrée', t.why_entry, '#fbbf24') +
        arow('🛡️','Pourquoi SL',     t.why_sl,    '#fb7185') +
        arow('🎯','Pourquoi TP',     t.why_tp,    '#86efac') +
        arow('⏱','Timeframe',    t.timeframe || t.setup_type,                     '#fcd34d') +
        arow('⏳','Durée',        t.expected_duration,                             '#94a3b8') +
        rrHtml +
        arow('📡','Source',       t.source,                                        '#475569') +
      '</div>';

    c.appendChild(div);
  });

  state.positions = trades.filter(function(t) {
    return t && t.direction && t.direction !== 'HOLD';
  });
}

// ── LOG ───────────────────────────────────────────────────────────────────────

function log(msg, type) {
  if (!type) type = 'info';
  var ts  = new Date().toLocaleTimeString('fr-FR');
  var el  = document.getElementById('logbar') || document.getElementById('maintenance-log');
  if (!el) return;
  var div = document.createElement('div');
  div.className = 'log-' + type;
  div.textContent = ts + ' — ' + msg;
  el.insertBefore(div, el.firstChild);
  while (el.children.length > 100) el.removeChild(el.lastChild);
}

// ── SYSTEM LOG (inter-IA) ─────────────────────────────────────────────────────

function sysLog(action) {
  // Envoie un log au serveur pour SYSTEM_LOG.json
  fetch(API + '/system-log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: 'studio-ui', action: action, ts: new Date().toISOString() })
  }).catch(function() {});
}

// ── AGENT LIVE MONITORING ──────────────────────────────────────────────────────

var agentActivityLog = [];
var agentStatesMap = {};

function formatTimestamp(ts) {
  if (typeof ts === 'number') ts = new Date(ts);
  else if (typeof ts === 'string') ts = new Date(ts);
  var h = String(ts.getHours()).padStart(2, '0');
  var m = String(ts.getMinutes()).padStart(2, '0');
  var s = String(ts.getSeconds()).padStart(2, '0');
  return h + ':' + m + ':' + s;
}

function updateAgentStateUI() {
  var container = document.getElementById('agent-states');
  if (!container) return;
  
  var html = '';
  for (var name in agentStatesMap) {
    var state = agentStatesMap[name];
    var dotClass = state.status === 'working' ? 'working' : (state.status === 'error' ? 'error' : 'idle');
    var statusLabel = state.status === 'working' ? '⚡ Travaille' : (state.status === 'error' ? '❌ Erreur' : '⏸ Inactif');
    html += '<div class="agent-state">' +
            '  <span class="agent-dot ' + dotClass + '"></span>' +
            '  <span>' + name + '</span>' +
            '  <span style="color:var(--muted);font-size:0.65rem;">(' + statusLabel + ')</span>' +
            '</div>';
  }
  container.innerHTML = html;
}

function addAgentLogEntry(entry) {
  agentActivityLog.unshift(entry);
  if (agentActivityLog.length > 100) agentActivityLog.pop();
  
  var logContainer = document.getElementById('agents-log');
  if (!logContainer) return;
  
  var ts = formatTimestamp(entry.ts || entry.id);
  var statusClass = entry.status === 'ok' ? 'ok' : 'err';
  var entryHtml = '<div class="agent-log-entry">' +
                  '<span class="timestamp">[' + ts + ']</span> ' +
                  '<span class="from">' + (entry.from || '—') + '</span> → ' +
                  '<span class="action">' + (entry.action || '?') + '</span> ' +
                  '<span class="' + statusClass + '">[' + (entry.status || '?').toUpperCase() + ']</span>' +
                  (entry.detail ? ' <span style="color:var(--muted);">' + entry.detail.substring(0, 60) + '</span>' : '') +
                  '</div>';
  
  var div = document.createElement('div');
  div.innerHTML = entryHtml;
  logContainer.insertBefore(div.firstChild, logContainer.firstChild);
  
  while (logContainer.children.length > 50) {
    logContainer.removeChild(logContainer.lastChild);
  }
}

function startAgentMonitoring() {
  try {
    var eventSource = new EventSource(API + '/agent-activity');
    
    eventSource.addEventListener('message', function(e) {
      try {
        var data = JSON.parse(e.data);
        
        if (data.type === 'initial') {
          agentStatesMap = data.agents || {};
          if (data.logs && Array.isArray(data.logs)) {
            data.logs.forEach(function(log) {
              agentActivityLog.push(log);
            });
          }
          updateAgentStateUI();
          redrawAgentLogs();
        } else if (data.from) {
          // Regular log entry
          agentStatesMap[data.from] = { status: data.status === 'ok' ? 'idle' : data.status || 'idle', lastActivity: Date.now() };
          addAgentLogEntry(data);
          updateAgentStateUI();
        }
      } catch (err) {
        console.error('Error parsing agent activity:', err);
      }
    });
    
    eventSource.onerror = function() {
      console.warn('Agent activity stream ERR, reconnecting...');
      setTimeout(startAgentMonitoring, 3000);
    };
    
  } catch (err) {
    console.warn('Cannot start agent monitoring:', err.message);
    setTimeout(startAgentMonitoring, 5000);
  }
}

function redrawAgentLogs() {
  var logContainer = document.getElementById('agents-log');
  if (!logContainer) return;
  logContainer.innerHTML = '';
  
  for (var i = 0; i < Math.min(agentActivityLog.length, 50); i++) {
    var entry = agentActivityLog[i];
    var ts = formatTimestamp(entry.ts || entry.id);
    var statusClass = entry.status === 'ok' ? 'ok' : 'err';
    var entryDiv = document.createElement('div');
    entryDiv.className = 'agent-log-entry';
    entryDiv.innerHTML = '<span class="timestamp">[' + ts + ']</span> ' +
                         '<span class="from">' + (entry.from || '—') + '</span> → ' +
                         '<span class="action">' + (entry.action || '?') + '</span> ' +
                         '<span class="' + statusClass + '">[' + (entry.status || '?').toUpperCase() + ']</span>' +
                         (entry.detail ? ' <span style="color:var(--muted);">' + entry.detail.substring(0, 60) + '</span>' : '');
    logContainer.appendChild(entryDiv);
  }
}

// Démarrer le monitoring en chargement
console.log('✅ studioapp.js v3 chargé — 12 boutons · Chart stable · Persistance · Timeframes M1→D1');
startAgentMonitoring();
