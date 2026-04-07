// popup.js — Localhost Mirror of Extension (SSE Real-Time Sync)
'use strict';

const API = 'http://127.0.0.1:4000';
let eventSource = null;
let reconnectTimer = null;

const state = {
  symbol: '--',
  timeframe: 'H1',
  price: null,
  source: 'offline',
  userLocked: false,   // true = user manually selected, never auto-override
  bridgeConfig: {
    agentName: 'orchestrator',
    bridgeSource: 'tradingview',
    bridgeMode: 'AUTO',
    bridgeEnabled: true,
    sendPreAlerts: true,
    sendSignals: true,
    symbolAliasBridge: ''
  }
};

if (typeof chrome === 'undefined') {
  window.chrome = {
    storage: { local: { get: () => {}, set: () => {} } },
    runtime: { onMessage: { addListener: () => {} } }
  };
}

function $(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function setClassState(id, tone) {
  const el = $(id);
  if (!el) return;
  el.classList.remove('ok', 'err', 'warn');
  if (tone) el.classList.add(tone);
}

function fmtOnOff(v) {
  return v ? 'ON' : 'OFF';
}

function renderBridgeConfig() {
  const root = $('agents-report');
  if (!root) return;
  const c = state.bridgeConfig || {};
  root.innerHTML = [
    '<div class="row"><span class="r-lbl">Nom agent</span><span class="r-val">' + (c.agentName || '--') + '</span></div>',
    '<div class="row"><span class="r-lbl">Source bridge</span><span class="r-val">' + String(c.bridgeSource || '--').toUpperCase() + '</span></div>',
    '<div class="row"><span class="r-lbl">Mode bridge</span><span class="r-val blue">' + (c.bridgeMode || '--') + '</span></div>',
    '<div class="row"><span class="r-lbl">Envoyer pré-alertes</span><span class="r-val">' + fmtOnOff(!!c.sendPreAlerts) + '</span></div>',
    '<div class="row"><span class="r-lbl">Envoyer signaux</span><span class="r-val">' + fmtOnOff(!!c.sendSignals) + '</span></div>',
    '<div class="row"><span class="r-lbl">Alias symbole bridge</span><span class="r-val">' + (c.symbolAliasBridge || '--') + '</span></div>'
  ].join('');
}

function applyBridgeConfig(data) {
  if (!data) return;
  const next = data.bridgeConfig || data;
  state.bridgeConfig = {
    ...state.bridgeConfig,
    ...next
  };
  if (state.bridgeConfig.bridgeEnabled === false) {
    updateStatus('BRIDGE OFF', 'err');
  }
  renderBridgeConfig();
}

function formatPrice(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '--';
  return Math.abs(num) >= 1000 ? num.toFixed(2) : num.toFixed(5);
}

function updateClock() {
  const now = new Date();
  setText('hdr-time', now.toLocaleTimeString('fr-FR', { hour12: false }));
}

function updateStatus(message, tone) {
  const el = $('sts');
  if (!el) return;
  el.textContent = message;
  el.className = tone || '';
}

function syncSymbolSelect() {
  const select = $('symbol-select');
  if (!select) return;
  if ([...select.options].some((option) => option.value === state.symbol)) {
    select.value = state.symbol;
  }
}

function applyActiveSymbol(data) {
  if (!data) return;
  if (data.symbol) state.symbol = String(data.symbol).replace(/[/\-]/g, '').toUpperCase();
  if (data.timeframe) state.timeframe = String(data.timeframe).toUpperCase();
  if (data.price != null && Number.isFinite(Number(data.price))) state.price = Number(data.price);

  setText('hdr-sym', state.symbol);
  setText('hdr-tf', state.timeframe || '--');
  setText('hdr-price', state.price != null ? formatPrice(state.price) : '--');
  setText('ctx-sym', state.symbol);
  setText('ctx-tf', state.timeframe || '--');
  syncSymbolSelect();
}

function applyCurrentData(data) {
  if (!data) return;
  // NEVER update state.symbol here — symbol is source-of-truth via applyActiveSymbol() only

  const bid = Number(data.bid);
  const ask = Number(data.ask);
  if (Number.isFinite(bid) && Number.isFinite(ask)) {
    state.price = bid;
    setText('hdr-price', formatPrice(bid));
    setText('ctx-price', formatPrice(bid) + ' / ' + formatPrice(ask));
    setText('ctx-spread', formatPrice(ask - bid));
  } else if (data.price != null && Number.isFinite(Number(data.price))) {
    state.price = Number(data.price);
    setText('hdr-price', formatPrice(state.price));
    setText('ctx-price', formatPrice(state.price));
    setText('ctx-spread', '--');
  } else {
    setText('ctx-price', state.price != null ? formatPrice(state.price) : '--');
    setText('ctx-spread', '--');
  }

  const assetType = data.assetType || (data.type !== 'mt5-data' && data.type !== 'tradingview-data' ? data.type : null);
  setText('ctx-type', assetType || '--');
  setText('ctx-tv', data.source || state.source || '--');
}

function applySystemStatus(status) {
  const source = status && status.source ? String(status.source).toLowerCase() : 'offline';
  state.source = source;
  const isMt5 = source === 'mt5';
  const isOnline = source !== 'offline';

  setClassState('dot-srv', isOnline ? 'ok' : 'err');
  setClassState('dot-mt5', isMt5 ? 'ok' : (isOnline ? 'warn' : 'err'));
  setClassState('dot-ext', eventSource ? 'ok' : 'warn');

  setClassState('si-srv', isOnline ? 'ok' : 'err');
  setClassState('si-mt5', isMt5 ? 'ok' : (isOnline ? 'warn' : 'err'));
  setClassState('si-det', isOnline ? (isMt5 ? 'ok' : 'warn') : 'err');

  setText('sv-srv', isOnline ? 'ONLINE' : 'OFFLINE');
  setText('sv-mt5', isMt5 ? 'MT5 LIVE' : (isOnline ? 'TV LIVE' : 'OFFLINE'));
  setText('sv-det', source.toUpperCase());
  setText('vol-pill', status && status.fluxStatus ? String(status.fluxStatus).toUpperCase() : 'LOW');
}

async function fetchJson(path, options) {
  const response = await fetch(API + path, options || {});
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}

async function postCommand(command, payload) {
  return fetchJson('/extension/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, payload })
  });
}

async function hydrateFromSnapshot() {
  try {
    const data = await fetchJson('/extension/data');
    applySystemStatus(data.systemStatus || null);
    applyActiveSymbol(data.activeSymbol || null);
    applyCurrentData(data.currentData || data.activeSymbol || null);
    applyBridgeConfig(data.bridgeConfig || null);
    updateStatus('Snapshot chargé', 'ok');
  } catch (error) {
    updateStatus('Snapshot indisponible: ' + error.message, 'err');
  }
}

function handleSseMessage(data) {
  if (data.systemStatus) {
    applySystemStatus(data.systemStatus);
  }

  if (data.type === 'initial-sync') {
    applyActiveSymbol(data.activeSymbol || null);
    applyCurrentData(data.currentData || data.activeSymbol || null);
    applyBridgeConfig(data.bridgeConfig || null);
    updateStatus('Synchronisé', 'ok');
    return;
  }

  if (data.type === 'bridge-config') {
    applyBridgeConfig(data.bridgeConfig || data);
    updateStatus('Paramètres bridge sync', 'ok');
    return;
  }

  if (data.type === 'active-symbol') {
    // lock only symbol; timeframe/mode stay synced.
    if (!state.userLocked) {
      applyActiveSymbol(data);
    } else {
      applyActiveSymbol({ timeframe: data.timeframe, price: data.price });
    }
    updateStatus('Symbole actif: ' + state.symbol, 'ok');
    return;
  }

  if (data.type === 'mt5-data' || data.type === 'tradingview-data') {
    // Update price/market data ONLY — never override the locked symbol
    applyCurrentData(data);
    const sym = state.symbol;
    const px = data.price || data.bid || null;
    const rsiRaw = data.indicators && data.indicators.rsi;
    const rsiStr = Number.isFinite(Number(rsiRaw)) ? ' RSI:' + Number(rsiRaw).toFixed(0) : '';
    const pxStr = px ? ' @ ' + formatPrice(px) : '';
    const prefix = data.type === 'mt5-data' ? '📡 MT5' : '⚡ FLUX';
    updateStatus(prefix + ': ' + sym + pxStr + rsiStr, 'ok');
  }
}

function connectSse() {
  if (eventSource) {
    eventSource.close();
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  updateStatus('Connexion SSE...', '');
  eventSource = new EventSource(API + '/extension/sync');

  eventSource.onopen = () => {
    setClassState('dot-ext', 'ok');
    updateStatus('SSE connecté', 'ok');
  };

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data || '{}');
      handleSseMessage(data);
      updateClock();
    } catch (error) {
      updateStatus('Erreur SSE: ' + error.message, 'err');
    }
  };

  eventSource.onerror = () => {
    setClassState('dot-ext', 'warn');
    updateStatus('SSE interrompu, reconnexion...', 'err');
    try { eventSource.close(); } catch (_) {}
    eventSource = null;
    reconnectTimer = setTimeout(connectSse, 3000);
  };
}

function bindControls() {
  const symbolSelect = $('symbol-select');
  if (symbolSelect) {
    symbolSelect.addEventListener('change', async () => {
      const symbol = symbolSelect.value;
      state.userLocked = true;  // user choice = source of truth, block auto-overrides
      try {
        await postCommand('set-symbol', {
          symbol,
          timeframe: state.timeframe || 'H1',
          price: state.price,
          mode: 'SNIPER'
        });
        applyActiveSymbol({ symbol, timeframe: state.timeframe, price: state.price });
        updateStatus('Symbole forcé: ' + symbol, 'ok');
      } catch (error) {
        updateStatus('Commande refusée: ' + error.message, 'err');
      }
    });
  }

  const refreshTargets = ['btn-refresh', 'btn-debug-send'];
  refreshTargets.forEach((id) => {
    const button = $(id);
    if (button) button.addEventListener('click', hydrateFromSnapshot);
  });

  const bridgeCfgBtn = $('btn-agents-config');
  if (bridgeCfgBtn) {
    bridgeCfgBtn.addEventListener('click', async () => {
      const c = state.bridgeConfig || {};
      const agentName = window.prompt('Nom agent bridge', c.agentName || 'orchestrator');
      if (agentName === null) return;
      const bridgeSource = window.prompt('Source bridge (tradingview/mt5/extension)', c.bridgeSource || 'tradingview');
      if (bridgeSource === null) return;
      const bridgeMode = window.prompt('Mode bridge (AUTO/ANALYSE/ALERTE/EXECUTION_PREPAREE)', c.bridgeMode || 'AUTO');
      if (bridgeMode === null) return;
      const preAlerts = window.prompt('Envoyer pré-alertes (ON/OFF)', c.sendPreAlerts ? 'ON' : 'OFF');
      if (preAlerts === null) return;
      const sendSignals = window.prompt('Envoyer signaux (ON/OFF)', c.sendSignals ? 'ON' : 'OFF');
      if (sendSignals === null) return;
      const alias = window.prompt('Alias symbole bridge (vide = aucun)', c.symbolAliasBridge || state.symbol || '');
      if (alias === null) return;

      try {
        await postCommand('set-bridge-config', {
          agentName,
          bridgeSource,
          bridgeMode,
          sendPreAlerts: String(preAlerts).trim().toUpperCase() === 'ON',
          sendSignals: String(sendSignals).trim().toUpperCase() === 'ON',
          symbolAliasBridge: alias,
          updatedBy: 'popup'
        });
        updateStatus('Bridge config mis à jour', 'ok');
      } catch (error) {
        updateStatus('Bridge config refusé: ' + error.message, 'err');
      }
    });

    const analyzeBtn = $('btn-analyze');
    if (analyzeBtn) {
      analyzeBtn.addEventListener('click', async () => {
        try {
          updateStatus('ANALYSE EN COURS...', '');
          await postCommand('analyze', {
            symbol: state.symbol,
            timeframe: state.timeframe || 'H1',
            mode: state.bridgeConfig.bridgeMode || 'AUTO'
          });
          await hydrateFromSnapshot();
          updateStatus('ANALYSE OK', 'ok');
        } catch (error) {
          updateStatus('ANALYSE KO: ' + error.message, 'err');
        }
      });
    }
  }
}

document.addEventListener('DOMContentLoaded', async function() {
  updateClock();
  setInterval(updateClock, 1000);
  bindControls();
  await hydrateFromSnapshot();
  connectSse();
  console.log('[LOCALHOST-POPUP] Initialized - listening to real-time SSE stream');
});

window.addEventListener('beforeunload', function() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (eventSource) eventSource.close();
});
