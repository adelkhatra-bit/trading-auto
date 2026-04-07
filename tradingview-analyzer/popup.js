// popup.js v4.1 — Trading Auto — Unified Color System
// COLOR SYSTEM (NON NEGOTIABLE):
//   ORANGE  #f97316 = pending / signal incertain / "va se passer"
//   VERT    #22c55e = confirmé LONG / achat / haussier / signal validé
//   ROUGE   #ef4444 = confirmé SHORT / vente / baissier / signal invalidé
//   JAUNE   #eab308 = WAIT / neutre / attention / news
//   GRIS    #64748b = neutre / pas de signal / inactif
//   BLANC   #f1f5f9 = texte principal
const COL_LONG    = '#22c55e';
const COL_SHORT   = '#ef4444';
const COL_PENDING = '#f97316';
const COL_WAIT    = '#eab308';
const COL_NEUTRAL = '#64748b';
const COL_TEXT    = '#f1f5f9';
'use strict';

const API = 'http://127.0.0.1:4000';
const TFS  = ['M1','M5','M15','M30','H1','H4','D1','W1'];
const MTFS = ['M1','M5','M15','H1'];
const POPUP_STATE_KEY = 'taa_popup_state_v2';

const state = {
  symbol:      'XAUUSD',
  timeframe:   'H1',
  tradeMode:   'AUTO',
  price:       null,
  sse:         null,
  live:        null,
  tradeState:  null,
  persistent:  false,
  lastRec:     null,
  chartOpen:   false,
  userLocked:  false,   // true = user manually selected, no auto-override
  agentSessionActive: false,
  bridgeConfig: {
    agentName: 'orchestrator',
    bridgeSource: 'tradingview',
    activeSource: 'tradingview',
    bridgeMode: 'AUTO',
    bridgeEnabled: true,
    tradingviewEnabled: true,
    mt5Enabled: false,
    sendPreAlerts: true,
    sendSignals: true,
    symbolAliasBridge: ''
  },
  lastLiveCoachRefreshAt: 0,
  stats: { signals: 0, trades: 0, lastEvent: '--' },
  conn: { healthFails: 0, sseFails: 0, lastOkAt: 0 },
  beepCtx: null,
  alertedEntryKeys: {}
};

let saveStateTimer = null;

function loadPersistedState() {
  try {
    var raw = localStorage.getItem(POPUP_STATE_KEY);
    if (!raw) return;
    var saved = JSON.parse(raw);
    if (!saved || typeof saved !== 'object') return;
    if (saved.symbol) state.symbol = String(saved.symbol).toUpperCase();
    if (saved.timeframe && TFS.indexOf(String(saved.timeframe).toUpperCase()) >= 0) state.timeframe = String(saved.timeframe).toUpperCase();
    if (saved.tradeMode) state.tradeMode = String(saved.tradeMode).toUpperCase();
    if (Number.isFinite(Number(saved.price))) state.price = Number(saved.price);
    if (typeof saved.chartOpen === 'boolean') state.chartOpen = saved.chartOpen;
    if (typeof saved.userLocked === 'boolean') state.userLocked = saved.userLocked;
    if (typeof saved.agentSessionActive === 'boolean') state.agentSessionActive = saved.agentSessionActive;
    if (saved.stats && typeof saved.stats === 'object') state.stats = Object.assign({}, state.stats, saved.stats);
    if (saved.alertedEntryKeys && typeof saved.alertedEntryKeys === 'object') state.alertedEntryKeys = saved.alertedEntryKeys;
  } catch (_) {}
}

function savePersistedState() {
  try {
    localStorage.setItem(POPUP_STATE_KEY, JSON.stringify({
      symbol: state.symbol,
      timeframe: state.timeframe,
      tradeMode: state.tradeMode,
      price: state.price,
      chartOpen: !!state.chartOpen,
      userLocked: !!state.userLocked,
      agentSessionActive: !!state.agentSessionActive,
      stats: state.stats,
      alertedEntryKeys: state.alertedEntryKeys
    }));
  } catch (_) {}
}

function scheduleSaveState() {
  try {
    if (saveStateTimer) clearTimeout(saveStateTimer);
    saveStateTimer = setTimeout(savePersistedState, 120);
  } catch (_) {}
}

function setConnStable(label, cls) {
  setConn(label, cls);
}

function markConnectionOk(label) {
  state.conn.healthFails = 0;
  state.conn.sseFails = 0;
  state.conn.lastOkAt = Date.now();
  setConnStable(label || 'ONLINE', 'ok');
}

function markConnectionTransientFail() {
  var now = Date.now();
  var graceMs = 20000;
  if ((now - Number(state.conn.lastOkAt || 0)) <= graceMs || state.conn.healthFails < 3 || state.conn.sseFails < 2) {
    setConnStable('RETRY', 'warn');
  } else {
    setConnStable('OFFLINE', 'bad');
  }
}

function ensureBeepContext() {
  try {
    if (!state.beepCtx) {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      state.beepCtx = new Ctx();
    }
    if (state.beepCtx.state === 'suspended') {
      state.beepCtx.resume().catch(function() {});
    }
    return state.beepCtx;
  } catch (_) {
    return null;
  }
}

function playEntryBeepOnce(entryKey) {
  if (!entryKey || state.alertedEntryKeys[entryKey]) return;
  var ctx = ensureBeepContext();
  if (!ctx) return;
  try {
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 980;
    gain.gain.value = 0.0001;
    osc.connect(gain);
    gain.connect(ctx.destination);
    var now = ctx.currentTime;
    gain.gain.exponentialRampToValueAtTime(0.12, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
    osc.start(now);
    osc.stop(now + 0.24);
    state.alertedEntryKeys[entryKey] = Date.now();
    scheduleSaveState();
    flowLog('ENTRY_BEEP_TRIGGERED', { entryKey: entryKey });
  } catch (_) {}
}

function checkEntryProximityAndBeep(live) {
  try {
    var vp = live && live.virtualPosition ? live.virtualPosition : null;
    var it = live && live.instantTrade ? live.instantTrade : null;
    var lvl = (vp && Number.isFinite(Number(vp.entry))) ? Number(vp.entry)
      : ((it && Number.isFinite(Number(it.entry))) ? Number(it.entry)
      : Number(live && live.levelTrace && live.levelTrace.received ? live.levelTrace.received.entry : NaN));
    var px = Number(state.price || (live && live.currentPrice) || NaN);
    if (!Number.isFinite(lvl) || !Number.isFinite(px) || lvl <= 0 || px <= 0) return;
    var proximity = Math.max(0.10, lvl * 0.0001);
    var diff = Math.abs(px - lvl);
    if (diff <= proximity) {
      var key = [state.symbol, state.timeframe, lvl.toFixed(5)].join('|');
      playEntryBeepOnce(key);
    }
  } catch (_) {}
}

// ── COACH STREAM SSE ─────────────────────────────────────────────────────────
let coachSse = null;

function connectCoachStream(symbol) {
  if (coachSse) { try { coachSse.close(); } catch (_) {} }
  coachSse = new EventSource(`${API}/coach/stream?symbol=${encodeURIComponent(symbol || state.symbol || 'XAUUSD')}`);
  coachSse.onmessage = function(e) {
    try {
      const d = JSON.parse(e.data);
      if (d.coachMessage) {
        const el = document.getElementById('coachText');
        if (el) {
          const msg = d.coachMessage;
          const isAlert = msg.includes('SL') || msg.includes('Attention') || msg.includes('coupe');
          const isGood  = msg.includes('TP') || msg.includes('avance') || msg.includes('trail') || msg.includes('break-even');
          el.style.color = isAlert ? COL_SHORT : isGood ? COL_LONG : COL_PENDING;
          el.textContent = msg;
        }
      }
      if (d.price) state.price = d.price;
      // Fermer automatiquement le stream si le trade est terminé
      if (d.tradeState && d.tradeState.phase === 'closed') {
        disconnectCoachStream();
      }
    } catch (_) {}
  };
  coachSse.onerror = function() {
    setTimeout(() => {
      if (state.agentSessionActive) connectCoachStream(symbol || state.symbol);
    }, 3000);
  };
  console.log('[COACH STREAM] Connecté pour', symbol);
}

function disconnectCoachStream() {
  if (coachSse) { try { coachSse.close(); } catch (_) {} coachSse = null; }
  console.log('[COACH STREAM] Déconnecté');
}
// ─────────────────────────────────────────────────────────────────────────────

async function setAgentSession(active, trigger) {
  try {
    if (active) {
      await fetchJson('/orchestration/enable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval: 30000, trigger: trigger || 'manual' })
      });
      state.agentSessionActive = true;
      scheduleSaveState();
      // Ouvrir le flux coach SSE en continu sur la position
      connectCoachStream(state.symbol);
      try {
        await fetchJson('/orchestration/run-now', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ trigger: trigger || 'manual' })
        });
      } catch (_) {}
      return;
    }
    await fetchJson('/orchestration/disable', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trigger: trigger || 'manual' })
    });
    state.agentSessionActive = false;
    // Fermer le flux coach SSE à la sortie de position
    disconnectCoachStream();
    scheduleSaveState();
  } catch (_) {}
}

// ─── UTILS ────────────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }

function isPersistent() {
  try { return new URLSearchParams(window.location.search).get('persistent') === '1'; }
  catch (_) { return false; }
}

function fmtPrice(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return '--';
  return Math.abs(n) > 1000 ? n.toFixed(2) : n.toFixed(5);
}

function fmtTime() { return new Date().toLocaleTimeString('fr'); }

function flowLog(message, data) {
  try {
    var payload = data || {};
    console.log('[EXT_FLOW]', message, payload);
    fetch(API + '/studio/system-log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'extension-popup',
        message: message,
        data: payload,
        ts: new Date().toISOString()
      })
    }).catch(function() {});
  } catch (_) {}
}

async function fetchJson(path, options) {
  const opts = options || {};
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 5000);
  try {
    const r = await fetch(API + path, Object.assign({}, opts, {
      signal: ctrl.signal,
      headers: Object.assign({ Accept: 'application/json' }, opts.headers || {})
    }));
    const t = await r.text();
    let d = {};
    try { d = JSON.parse(t || '{}'); } catch (_) { throw new Error('Non-JSON'); }
    if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
    return d;
  } finally { clearTimeout(timer); }
}

function getAgents(live) {
  return (live && (live.agents || (live.coach && live.coach.agents))) || {};
}

function getCoachPayload(live) {
  return (live && live.coach) ? live.coach : (live || {});
}

// ─── HEADER ───────────────────────────────────────────────────────────────────
function setConn(label, cls) {
  const el = $('conn');
  if (!el) return;
  el.textContent = label;
  el.className = cls + '-badge';
}

function applyBridgeConfig(cfg) {
  if (!cfg) return;
  state.bridgeConfig = Object.assign({}, state.bridgeConfig, cfg);
  if (state.bridgeConfig.activeSource !== 'mt5') state.bridgeConfig.activeSource = 'tradingview';
  var enabled = state.bridgeConfig.bridgeEnabled !== false;
  var bb = $('bridgeBadge');
  if (bb) {
    bb.textContent = enabled ? 'BRIDGE ON' : 'BRIDGE OFF';
    bb.className = 'bdg ' + (enabled ? 'ok' : 'bad');
    bb.title = 'Cliquez pour basculer ON/OFF';
    bb.style.cursor = 'pointer';
  }
  var bt = $('btnBridgeToggle');
  if (bt) {
    bt.textContent = enabled ? 'BRIDGE ACTIF' : 'BRIDGE OFF';
    bt.className = enabled ? 'btn-sub buy' : 'btn-sub sell';
    bt.title = enabled ? 'Cliquer pour désactiver le bridge' : 'Cliquer pour activer le bridge';
  }
  if (state.bridgeConfig.bridgeMode) {
    var bm = String(state.bridgeConfig.bridgeMode).toUpperCase();
    state.tradeMode = bm;
    var ms = $('modeSelect');
    if (ms && Array.from(ms.options).some(function(o) { return o.value === bm; })) ms.value = bm;
  }
  if (state.bridgeConfig.agentName) {
    var ha = $('headAgent');
    if (ha && ha.textContent.indexOf('AGENT ') !== 0) {
      ha.textContent = 'AGENT ' + String(state.bridgeConfig.agentName).toUpperCase();
    }
  }

  setSourceButtons();
}

function setSourceButtons() {
  var tvBtn = $('btnSourceTv');
  var mt5Btn = $('btnSourceMt5');
  var active = String(state.bridgeConfig.activeSource || 'tradingview').toLowerCase() === 'mt5' ? 'mt5' : 'tradingview';
  var tvOn = active === 'tradingview' && state.bridgeConfig.tradingviewEnabled !== false;
  var mt5On = active === 'mt5' && state.bridgeConfig.mt5Enabled === true;
  if (tvBtn) {
    tvBtn.textContent = tvOn ? 'TRADINGVIEW ON' : 'TRADINGVIEW OFF';
    tvBtn.className = tvOn ? 'btn-sub buy' : 'btn-sub';
  }
  if (mt5Btn) {
    mt5Btn.textContent = mt5On ? 'MT5 ON' : 'MT5 OFF';
    mt5Btn.className = mt5On ? 'btn-sub sell' : 'btn-sub';
  }
}

async function setActiveSource(source) {
  var src = String(source || '').toLowerCase() === 'mt5' ? 'mt5' : 'tradingview';
  await fetchJson('/extension/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      command: 'set-bridge-config',
      payload: src === 'tradingview'
        ? {
            activeSource: 'tradingview',
            tradingviewEnabled: true,
            mt5Enabled: false,
            updatedBy: 'extension-popup-source'
          }
        : {
            activeSource: 'mt5',
            tradingviewEnabled: false,
            mt5Enabled: true,
            updatedBy: 'extension-popup-source'
          }
    })
  });
}

function updateHeader() {
  const sym  = $('headSym');   if (sym)  sym.textContent  = state.symbol;
  const tf   = $('headTF');    if (tf)   tf.textContent   = state.timeframe;
  const mode = $('headMode');  if (mode) mode.textContent = state.tradeMode;
  const pr   = $('headPrice');
  if (pr) {
    pr.textContent = state.price ? fmtPrice(state.price) : '';
    // Couleur du prix selon état position
    var live = state.live || {};
    var vp = live.virtualPosition || live.coach && live.coach.virtualPosition || null;
    var it = live.instantTrade || null;
    var posDir = String((vp && vp.direction) || (it && it.direction) || '').toUpperCase();
    var phase  = String((vp && vp.status) || (live.tradeState && live.tradeState.phase) || '').toUpperCase();
    var isPending = phase.indexOf('PENDING') >= 0 || phase.indexOf('WAIT') >= 0;
    if (isPending) {
      pr.style.color = COL_PENDING;
    } else if (posDir.indexOf('BUY') >= 0 || posDir.indexOf('LONG') >= 0) {
      pr.style.color = COL_LONG;
    } else if (posDir.indexOf('SELL') >= 0 || posDir.indexOf('SHORT') >= 0) {
      pr.style.color = COL_SHORT;
    } else {
      pr.style.color = COL_TEXT;
    }
  }
  // Highlight active TF card
  MTFS.forEach(function(tf) { var c = $('tfc-' + tf); if (c) c.classList.toggle('active', tf === state.timeframe); });
  scheduleSaveState();
}

function updateAgentStatus(live) {
  const el = $('headAgent');
  if (!el) return;
  const agents = getAgents(live);
  const rec = String((agents.analysis && agents.analysis.recommendation) || '').toUpperCase();
  if (rec.indexOf('BUY') >= 0 || rec.indexOf('ACHAT') >= 0 || rec.indexOf('LONG') >= 0) {
    el.textContent = 'AGENT ACHAT';
    el.style.background = 'rgba(34,197,94,.2)'; el.style.color = COL_LONG; el.style.borderColor = 'rgba(34,197,94,.4)';
  } else if (rec.indexOf('SELL') >= 0 || rec.indexOf('VENTE') >= 0 || rec.indexOf('SHORT') >= 0) {
    el.textContent = 'AGENT VENTE';
    el.style.background = 'rgba(239,68,68,.2)'; el.style.color = COL_SHORT; el.style.borderColor = 'rgba(239,68,68,.4)';
  } else {
    el.textContent = 'AGENT ATTENTE';
    el.style.background = ''; el.style.color = COL_WAIT; el.style.borderColor = '';
  }
}

// ─── SIGNAL ───────────────────────────────────────────────────────────────────
function renderSignal(live) {
  const agents = getAgents(live);
  const analysis = agents.analysis || {};
  const rec    = String(analysis.recommendation || 'ATTENTE').toUpperCase();
  const reason = analysis.reason || (agents.risk && agents.risk.riskReason) || 'Analyse indisponible';
  const risk   = (agents.risk && agents.risk.riskLevel) || null;
  const logic  = (agents.strategy && agents.strategy.logic) || null;

  const sigEl = $('signalText');
  if (sigEl) {
    sigEl.textContent = rec;
    if (rec.indexOf('BUY') >= 0 || rec.indexOf('ACHAT') >= 0 || rec.indexOf('LONG') >= 0) {
      sigEl.className = 'signal buy';
    } else if (rec.indexOf('SELL') >= 0 || rec.indexOf('VENTE') >= 0 || rec.indexOf('SHORT') >= 0) {
      sigEl.className = 'signal sell';
    } else {
      sigEl.className = 'signal wait';
    }
  }

  const stEl = $('sigTime');
  if (stEl) stEl.textContent = fmtTime();

  const anEl = $('analysisText');
  if (anEl) {
    var parts = [reason];
    if (risk)  parts.push('Risque: ' + risk);
    if (logic) parts.push(logic);
    anEl.textContent = parts.join(' — ');
  }

  if (rec !== 'ATTENTE' && rec !== state.lastRec) {
    state.stats.signals++;
    state.stats.lastEvent = rec + ' ' + fmtTime();
    state.lastRec = rec;
    renderStats();
  }
}

function renderBadges(health) {
  const wb = $('webhookBadge');
  const bb = $('bridgeBadge');
  if (wb) {
    const on = health && health.ok;
    wb.textContent = on ? 'WH ON' : 'WH OFF';
    wb.className = 'bdg ' + (on ? 'ok' : 'bad');
  }
  if (bb) {
    if (state.bridgeConfig.bridgeEnabled === false) {
      bb.textContent = 'BRIDGE OFF';
      bb.className = 'bdg bad';
    } else {
      const mt5 = health && health.mt5Status === 'mt5';
      bb.textContent = mt5 ? 'MT5' : (health && health.ok ? 'TV' : 'OFF');
      bb.className = 'bdg ' + (mt5 ? 'ok' : (health && health.ok ? 'warn' : 'bad'));
    }
  }
  if (health && health.activeContext) {
    if (!state.price && health.activeContext.price) {
      state.price = health.activeContext.price;
      updateHeader();
    }
    if (health.activeContext.symbol) state.symbol = String(health.activeContext.symbol).toUpperCase();
  }
}

// ─── MULTI-TF ─────────────────────────────────────────────────────────────────
async function renderMultiTF() {
  if (!state.agentSessionActive) {
    MTFS.forEach(function(tf) {
      var sigEl = $(('tfc-' + tf + '-t').replace(/\s/g,''));
      var subEl = $(('tfc-' + tf + '-s').replace(/\s/g,''));
      if (!sigEl) return;
      sigEl.textContent = '--';
      sigEl.className = 'tfc-sig wait';
      if (subEl) subEl.textContent = 'Session OFF';
    });
    flowLog('MULTI_TF SKIPPED (SESSION OFF)', { symbol: state.symbol, mode: state.tradeMode });
    return;
  }

  var promises = MTFS.map(function(tf) {
    return fetchJson('/coach/realtime?symbol=' + encodeURIComponent(state.symbol) +
      '&tf=' + encodeURIComponent(tf) + '&mode=' + encodeURIComponent(state.tradeMode) + '&lang=fr')
      .then(function(d) { return { tf: tf, data: d, source: 'coach/realtime' }; })
      .catch(function() {
        return fetchJson('/instant-trade-live?symbol=' + encodeURIComponent(state.symbol) + '&tf=' + encodeURIComponent(tf) + '&mode=' + encodeURIComponent(state.tradeMode))
          .then(function(d2) { return { tf: tf, data: d2, source: 'instant-trade-live' }; })
          .catch(function() { return { tf: tf, data: null, source: 'none' }; });
      });
  });
  var results = await Promise.all(promises);

  results.forEach(function(item) {
    var tf   = item.tf;
    var data = item.data;
    var sigEl = $(('tfc-' + tf + '-t').replace(/\s/g,''));
    var subEl = $(('tfc-' + tf + '-s').replace(/\s/g,''));
    if (!sigEl) return;

    if (!data) {
      sigEl.textContent = 'ATTENTE';
      sigEl.className = 'tfc-sig wait';
      if (subEl) subEl.textContent = 'RSI -- | Flux KO';
      flowLog('MULTI_TF MAP', { tf: tf, source: item.source || 'none', status: 'no-data' });
      return;
    }

    var normalized = data.trade ? {
      ok: !!data.ok,
      coach: null,
      agents: {
        analysis: {
          recommendation: data.trade.direction || 'WAIT',
          strength: data.trade.score || data.trade.confidence || null
        },
        risk: {}
      }
    } : data;

    var agents   = getAgents(normalized);
    var analysis = agents.analysis || {};
    var rec  = String(analysis.recommendation || 'WAIT').toUpperCase();
    var label = 'NEUTRE'; var cls = 'wait';
    var cardBg = 'rgba(234,179,8,0.1)'; var cardBorder = COL_WAIT;
    if (rec.indexOf('BUY') >= 0 || rec.indexOf('ACHAT') >= 0 || rec.indexOf('LONG') >= 0) {
      label = 'ACHAT'; cls = 'buy';
      cardBg = 'rgba(34,197,94,0.1)'; cardBorder = COL_LONG;
    } else if (rec.indexOf('SELL') >= 0 || rec.indexOf('VENTE') >= 0 || rec.indexOf('SHORT') >= 0) {
      label = 'VENTE'; cls = 'sell';
      cardBg = 'rgba(239,68,68,0.1)'; cardBorder = COL_SHORT;
    }

    // Appliquer couleurs à la carte entière
    var card = $('tfc-' + tf);
    if (card) { card.style.background = cardBg; card.style.borderColor = cardBorder; }

    var rsiRaw = (agents.technicals && agents.technicals.rsi) || (agents.risk && agents.risk.rsi) || null;
    var rsi = rsiRaw != null ? Number(rsiRaw).toFixed(0) : '--';
    var str = analysis.strength || analysis.confidence;

    sigEl.textContent = label;
    sigEl.className = 'tfc-sig ' + cls;
    if (subEl) subEl.textContent = 'RSI ' + rsi + (str ? ' | ' + str + '%' : '');
    flowLog('MULTI_TF MAP', {
      tf: tf,
      source: item.source || 'coach/realtime',
      recommendation: rec,
      label: label,
      rsi: rsi,
      strength: str || null
    });
  });
}

// ─── DECISION AGENT ───────────────────────────────────────────────────────────
function renderDecision(live) {
  var agents   = getAgents(live);
  var analysis = agents.analysis || {};
  var execution = (live && live.execution) || (live && live.coach && live.coach.execution) || {};
  var priceConsistency = (live && live.priceConsistency) || {};
  var canEnter = execution.canEnter === true;
  var execDecision = String(execution.decision || '').toUpperCase();
  var rec      = String(analysis.recommendation || 'ATTENTE').toUpperCase();
  var reason   = analysis.reason || (live && live.tradeReasoning && Array.isArray(live.tradeReasoning.whyEntry) && live.tradeReasoning.whyEntry[0]) || 'Pas de raison disponible';
  var risk     = (agents.risk && agents.risk.riskLevel) || '--';
  var anticip  = analysis.anticipation || (agents.strategy && agents.strategy.anticipation) || '--';
  var gate     = (live && live.tradeReasoning && live.tradeReasoning.marketGate) || null;
  var nextAct  = execution.reason || (live && live.nextAction && live.nextAction.primary) || reason;

  var enterBtn = document.querySelector('[data-action="ENTER"]');
  if (enterBtn) {
    enterBtn.disabled = !canEnter;
    enterBtn.title = canEnter
      ? 'Entrée validée: ENTRER autorisé.'
      : (execDecision === 'NO_ENTRY_CONFLICT'
        ? 'Entrée bloquée: conflit de signal.'
        : 'Entrée non validée: attendre confirmation.');
    // Couleur bouton ENTRER selon système couleur unifié
    if (!canEnter) {
      // Orange = signal en cours d'analyse / pending
      enterBtn.style.background = 'rgba(249,115,22,0.15)';
      enterBtn.style.borderColor = COL_PENDING;
      enterBtn.style.color = COL_PENDING;
    } else if (rec.indexOf('BUY') >= 0 || rec.indexOf('ACHAT') >= 0 || rec.indexOf('LONG') >= 0) {
      enterBtn.style.background = 'rgba(34,197,94,0.15)';
      enterBtn.style.borderColor = COL_LONG;
      enterBtn.style.color = COL_LONG;
    } else if (rec.indexOf('SELL') >= 0 || rec.indexOf('VENTE') >= 0 || rec.indexOf('SHORT') >= 0) {
      enterBtn.style.background = 'rgba(239,68,68,0.15)';
      enterBtn.style.borderColor = COL_SHORT;
      enterBtn.style.color = COL_SHORT;
    } else {
      enterBtn.style.background = '';
      enterBtn.style.borderColor = '';
      enterBtn.style.color = '';
    }
  }

  // Verdict
  var vEl = $('dg-verdict');
  if (vEl) {
    vEl.textContent = rec;
    if (rec.indexOf('BUY') >= 0 || rec.indexOf('ACHAT') >= 0 || rec.indexOf('LONG') >= 0)     vEl.className = 'verdict buy';
    else if (rec.indexOf('SELL') >= 0 || rec.indexOf('VENTE') >= 0 || rec.indexOf('SHORT') >= 0) vEl.className = 'verdict sell';
    else vEl.className = 'verdict wait';
  }

  // Risk tag
  var rEl = $('dg-risk');
  if (rEl) {
    rEl.textContent = risk;
    var r = String(risk).toUpperCase();
    rEl.className = 'tag ' + (r === 'LOW' ? 'ok' : r === 'MEDIUM' ? 'warn' : r === 'HIGH' ? 'bad' : 'warn');
  }

  // Anticip tag
  var aEl = $('dg-anticip');
  if (aEl) {
    aEl.textContent = anticip !== '--' ? anticip : 'ATTENTE';
    aEl.className = 'tag blue';
  }

  // RAISON — très visible
  var rBox = $('dg-reason');
  if (rBox) {
    rBox.textContent = gate ? '🚫 BLOCAGE : ' + gate : reason;
    if      (gate) rBox.className = 'bad';
    else if (rec.indexOf('BUY') >= 0 || rec.indexOf('ACHAT') >= 0 || rec.indexOf('LONG') >= 0)     rBox.className = 'buy';
    else if (rec.indexOf('SELL') >= 0 || rec.indexOf('VENTE') >= 0 || rec.indexOf('SHORT') >= 0) rBox.className = 'sell';
    else rBox.className = '';
    rBox.id = 'dg-reason'; // keep id
  }

  // Prochaine action
  var naEl = $('dg-nextaction');
  if (naEl) {
    if (execDecision === 'NO_ENTRY_CONFLICT') naEl.textContent = 'Prochaine action : PAS D\'ENTRÉE / CONFLIT DE SIGNAL';
    else if (canEnter) naEl.textContent = 'Prochaine action : ENTRER (setup validé)';
    else naEl.textContent = 'Prochaine action : ATTENDRE confirmation';
    if (nextAct) naEl.textContent += ' | ' + nextAct;
    if (priceConsistency && typeof priceConsistency.coherent === 'boolean') {
      naEl.textContent += priceConsistency.coherent
        ? ' | Prix cohérent (décision/header/graph).'
        : ' | Incohérence prix détectée: attendre synchronisation.';
    }
  }
}

// ─── STATS ────────────────────────────────────────────────────────────────────
function renderStats() {
  var s = $('statSignals'); if (s) s.textContent = state.stats.signals;
  var t = $('statTrades');  if (t) t.textContent = state.stats.trades;
  var r = $('statRate');
  if (r) r.textContent = state.stats.signals > 0 ? Math.round(state.stats.trades / state.stats.signals * 100) + '%' : '--';
  var e = $('statLastEvent'); if (e) e.textContent = 'Dernier : ' + state.stats.lastEvent;
}

// ─── DIAGNOSTIC (1 ligne) ───────────────────────────────────────────────────
function renderDiag(live) {
  var el = $('diagLine');
  if (!el) return;
  var reasoning = (live && live.tradeReasoning) || {};
  var market    = (live && live.marketStatus)   || {};
  var agents    = getAgents(live);

  if (reasoning.marketGate) {
    el.textContent = '🚫 ' + reasoning.marketGate;
    el.className = 'blocking';
    el.id = 'diagLine';
    return;
  }

  var parts = [];
  var sessions = market.sessions || {};
  if (Array.isArray(sessions.sessions)) {
    var open = sessions.sessions.filter(function(s) { return s.isOpen; }).map(function(s) { return s.label; });
    if (open.length) parts.push('Sessions: ' + open.join(', '));
  }
  var whyEntry = reasoning.whyEntry;
  if (Array.isArray(whyEntry) && whyEntry.length) {
    parts.push(whyEntry[0]);
  } else if (typeof whyEntry === 'string' && whyEntry) {
    parts.push(whyEntry);
  }
  var aReason = (agents.analysis && agents.analysis.reason) || '';
  if (!parts.length && aReason) parts.push(aReason);
  if (!parts.length) {
    parts.push(market.isOpen ? 'Marche ouvert' : (market.isOpen === false ? 'Marche ferme' : 'Attente donnees'));
  }

  el.textContent = parts.join(' — ');
  el.className = '';
  el.id = 'diagLine';
}

// ─── COACH ────────────────────────────────────────────────────────────────────
function renderCoach(live) {
  var el = $('coachText');
  if (!el) return;
  var payload = (live && live.coach) ? live.coach : live;
  var isLiveIa = !!(payload && payload.lia && payload.lia.ok);
  var txt = (payload && payload.lia && payload.lia.response) ||
            (live && live.lia_response) || 'Coach indisponible.';
  var tag = isLiveIa ? '[IA LIVE]' : '[FALLBACK LIVE]';
  txt = tag + '\n' + txt;
  el.textContent = txt;

  var rec = String(((getAgents(live).analysis || {}).recommendation) || '').toUpperCase();
  var gate = String((live && live.tradeReasoning && live.tradeReasoning.marketGate) || '').toUpperCase();
  var txtLow = txt.toLowerCase();
  // Messages spéciaux : proche SL / proche TP / break-even
  if (txtLow.indexOf('break-even') >= 0 || txtLow.indexOf('breakeven') >= 0) {
    el.style.color = COL_PENDING;
    el.style.background = '';
  } else if (txtLow.indexOf('proche sl') >= 0 || txtLow.indexOf('near sl') >= 0) {
    el.style.color = COL_SHORT;
    el.style.background = 'rgba(239,68,68,0.1)';
  } else if (txtLow.indexOf('proche tp') >= 0 || txtLow.indexOf('near tp') >= 0) {
    el.style.color = COL_LONG;
    el.style.background = 'rgba(34,197,94,0.1)';
  } else if (gate.indexOf('FERM') >= 0 || gate.indexOf('BLOC') >= 0 || rec.indexOf('WAIT') >= 0 || rec.indexOf('ATTENTE') >= 0) {
    el.style.color = COL_WAIT;
    el.style.background = '';
  } else if (rec.indexOf('SELL') >= 0 || rec.indexOf('SHORT') >= 0 || rec.indexOf('VENTE') >= 0) {
    el.style.color = COL_SHORT;
    el.style.background = '';
  } else if (rec.indexOf('BUY') >= 0 || rec.indexOf('LONG') >= 0 || rec.indexOf('ACHAT') >= 0) {
    el.style.color = COL_LONG;
    el.style.background = '';
  } else {
    el.style.color = '#cbd5e1';
    el.style.background = '';
  }
}

function renderBridgeOffState() {
  state.live = null;
  setConn('BRIDGE OFF', 'bad');
  var wb = $('webhookBadge');
  if (wb) { wb.textContent = 'OFF'; wb.className = 'bdg bad'; }
  var sig = $('signalText');
  if (sig) { sig.textContent = 'OFF'; sig.className = 'signal wait'; }
  var an = $('analysisText');
  if (an) an.textContent = 'Bridge desactive. Donnees live gelees.';
  var coach = $('coachText');
  if (coach) {
    coach.textContent = 'Bridge desactive.\nCoach en pause jusqu\'a reactivation.';
    coach.style.color = '#cbd5e1';
  }
  var next = $('dg-nextaction');
  if (next) next.textContent = 'Prochaine action : Reactiver bridge puis analyser';
  var enterBtn = document.querySelector('[data-action="ENTER"]');
  if (enterBtn) {
    enterBtn.disabled = true;
    enterBtn.title = 'Bridge inactif: entrée désactivée.';
  }
}

function formatNewsEvent(e) {
  // Étoiles
  var stars = Math.min(5, Math.max(0, Number(e.stars) || 0));
  var starsHtml = '<span class="ns">' + '★'.repeat(stars) + '☆'.repeat(5 - stars) + '</span>';

  // Timing
  var mins = Number.isFinite(Number(e.minsUntil)) ? Number(e.minsUntil) : null;
  var timingHtml;
  if (mins === null) {
    timingHtml = '<span class="nt">--</span>';
  } else if (mins >= -5 && mins <= 5) {
    timingHtml = '<span class="nt nt-now">En cours</span>';
  } else if (mins > 0) {
    var h = Math.floor(mins / 60);
    timingHtml = h > 0
      ? '<span class="nt nt-soon">Dans ' + h + 'h' + (mins % 60 > 0 ? (mins % 60) + 'min' : '') + '</span>'
      : '<span class="nt nt-soon">Dans ' + mins + 'min</span>';
  } else {
    var absM = Math.abs(mins);
    var hP = Math.floor(absM / 60);
    timingHtml = hP > 0
      ? '<span class="nt nt-past">Il y a ' + hP + 'h' + (absM % 60 > 0 ? (absM % 60) + 'min' : '') + '</span>'
      : '<span class="nt nt-past">Il y a ' + absM + 'min</span>';
  }

  // Biais
  var bias = e.bias || {};
  var biasDir = String(bias.direction || 'UNCERTAIN').toUpperCase();
  var biasMap = {
    'BULLISH_USD': '📈 Haussier USD',
    'BEARISH_USD': '📉 Baissier USD',
    'NEUTRAL':     '➡️ Neutre',
    'UNCERTAIN':   '⚠️ Incertain'
  };
  var biasText = biasMap[biasDir] || '⚠️ Incertain';
  var biasCls = biasDir === 'BULLISH_USD' ? 'nb-bull' : biasDir === 'BEARISH_USD' ? 'nb-bear' : 'nb-neu';
  var biasHtml = '<span class="nb ' + biasCls + '">' + biasText + '</span>';

  // Actual vs Forecast
  var avfHtml = '';
  if (e.actual != null && e.actual !== '') {
    var isBetter = false, isWorse = false;
    var actualN = parseFloat(e.actual), forecastN = parseFloat(e.forecast);
    if (!isNaN(actualN) && !isNaN(forecastN)) {
      if (biasDir === 'BEARISH_USD') {
        isBetter = actualN < forecastN;
        isWorse  = actualN > forecastN;
      } else {
        isBetter = actualN > forecastN;
        isWorse  = actualN < forecastN;
      }
    }
    var avfCls = isBetter ? 'nav-good' : isWorse ? 'nav-bad' : '';
    var forecastStr = (e.forecast != null && e.forecast !== '') ? ' vs Prévu: ' + e.forecast : '';
    avfHtml = '<span class="nav ' + avfCls + '">Réel: ' + e.actual + forecastStr + '</span>';
  }

  var title = e.title || e.event || 'Événement';
  var country = e.country ? '<span class="nco">' + e.country + '</span>' : '';
  var time = e.time ? '<span class="ntime">' + e.time + '</span>' : '';

  return '<div class="ni">' +
    '<div class="ni-head">' + starsHtml + country + time + timingHtml + '</div>' +
    '<div class="ni-title"><strong>' + title + '</strong></div>' +
    '<div class="ni-foot">' + biasHtml + avfHtml + '</div>' +
  '</div>';
}

async function renderNews(live) {
  var root = $('newsList');
  if (!root) return;

  // Tenter d'abord les événements depuis le payload realtime (agents.news)
  var agents = getAgents(live);
  var newsAgent = agents.news || {};
  var events = Array.isArray(newsAgent.upcomingEvents) ? newsAgent.upcomingEvents : [];
  var headlines = [];

  // Appeler /news?symbol= pour obtenir events + headlines unifiés
  var hasNewFormat = events.length > 0 && events[0] && (events[0].stars != null || events[0].bias != null);
  if (!hasNewFormat) {
    try {
      var data = await fetchJson('/news?symbol=' + encodeURIComponent(state.symbol));
      if (Array.isArray(data.events) && data.events.length > 0) {
        events = data.events;
      } else if (Array.isArray(data)) {
        events = data;
      }
      if (Array.isArray(data.headlines)) {
        headlines = data.headlines;
      }
    } catch (_) {
      // Fallback sur /economic-events si /news indisponible
      try {
        var fallback = await fetchJson('/economic-events?symbol=' + encodeURIComponent(state.symbol));
        if (Array.isArray(fallback.events) && fallback.events.length > 0) {
          events = fallback.events;
        } else if (Array.isArray(fallback)) {
          events = fallback;
        }
      } catch (_2) {}
    }
  }

  var html = events.slice(0, 5).map(formatNewsEvent);

  if (html.length === 0 && newsAgent.symbolImpact) {
    html.push('<div class="ni"><span class="nav">' + newsAgent.symbolImpact + '</span></div>');
  }

  root.innerHTML = html.join('') || '<div class="ni"><span class="nt">Aucun événement à venir</span></div>';

  // --- Headlines RSS live ---
  if (headlines.length > 0) {
    var hdEl = document.getElementById('headlinesList');
    if (!hdEl) {
      hdEl = document.createElement('div');
      hdEl.id = 'headlinesList';
      hdEl.style.cssText = 'margin-top:8px;border-top:1px solid #334155;padding-top:6px;';
      root.appendChild(hdEl);
    }
    hdEl.innerHTML = '<div style="font-size:10px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:1px;">Headlines live</div>' +
      headlines.slice(0, 5).map(function(h) {
        var biasColor = h.bias === 'Bullish' ? '#86efac' : h.bias === 'Bearish' ? '#fca5a5' : '#94a3b8';
        var age = h.ageMinutes < 60 ? h.ageMinutes + 'min' : Math.round(h.ageMinutes / 60) + 'h';
        return '<div style="margin-bottom:6px;padding:4px 6px;background:#1e293b;border-radius:4px;border-left:2px solid ' + biasColor + '">' +
          '<div style="font-size:11px;color:#e2e8f0;line-height:1.3">' + h.title + '</div>' +
          '<div style="font-size:10px;color:#64748b;margin-top:2px">' + h.source + ' · ' + age + ' · <span style="color:' + biasColor + '">' + h.bias + '</span></div>' +
        '</div>';
      }).join('');
  }
}

// ─── MAIN REFRESH ────────────────────────────────────────────────────────────
async function refreshHealth() {
  try {
    flowLog('API REQUEST /health', { symbol: state.symbol, timeframe: state.timeframe });
    var h = await fetchJson('/health');
    flowLog('API RESPONSE /health', {
      ok: !!h.ok,
      mt5Status: h.mt5Status || null,
      activeContext: h.activeContext || null
    });
    renderBadges(h);
    markConnectionOk('ONLINE');
    return h;
  } catch (_) {
    state.conn.healthFails = Number(state.conn.healthFails || 0) + 1;
    flowLog('API ERROR /health', { symbol: state.symbol, timeframe: state.timeframe });
    renderBadges(null);
    markConnectionTransientFail();
    return null;
  }
}

async function loadRealtimePack() {
  var path = '/coach/realtime?symbol=' + encodeURIComponent(state.symbol) +
    '&tf=' + encodeURIComponent(state.timeframe) +
    '&mode=' + encodeURIComponent(state.tradeMode) + '&lang=fr';
  flowLog('API REQUEST /coach/realtime', {
    symbol: state.symbol,
    timeframe: state.timeframe,
    mode: state.tradeMode
  });
  var live = await fetchJson(path);
  flowLog('API RESPONSE /coach/realtime', {
    ok: !!live.ok,
    symbol: live.symbol || state.symbol,
    timeframe: live.timeframe || state.timeframe,
    hasCoach: !!live.coach,
    hasTradeState: !!live.tradeState,
    hasInstantTrade: !!live.instantTrade
  });
  state.live = live;
  if (Number.isFinite(Number(live.currentPrice)) && Number(live.currentPrice) > 0) {
    state.price = Number(live.currentPrice);
  }
  if (live.mode) state.tradeMode = String(live.mode).toUpperCase();
  var payload = getCoachPayload(live);
  renderSignal(payload);
  renderDecision(payload);
  renderDiag(payload);
  renderCoach(payload);
  renderNews(payload);
  updateAgentStatus(payload);
  updateHeader();

  // Chart: only load if open
  if (state.chartOpen && typeof ChartModule !== 'undefined' && ChartModule && ChartModule.loadChart) {
    var vp = live.virtualPosition || null;
    var it = live.instantTrade || null;
    var levels = vp
      ? { entry: vp.entry, sl: vp.sl, tp: vp.tp }
      : (it ? { entry: it.entry, sl: it.sl, tp: it.tp } : null);
    if (levels) {
      flowLog('LEVELS DISPLAYED', {
        source: (live.levelTrace && live.levelTrace.source) || (vp && vp.source) || (it && it.source) || 'unknown',
        backendReceived: live.levelTrace && live.levelTrace.received ? live.levelTrace.received : null,
        displayed: { entry: levels.entry, sl: levels.sl, tp: levels.tp }
      });
    }
    ChartModule.loadChart(state.symbol, state.timeframe, levels, state.price);
  }
  checkEntryProximityAndBeep(live);
  scheduleSaveState();
}

async function loadMirrorSnapshot() {
  // Source unique : TradingView live
  var ext = await fetchJson('/extension/data');
  if (!ext.ok || !ext.activeSymbol || !ext.currentData || typeof ext.currentData.price !== 'number') {
    setConn('NO DATA', 'bad');
    state.price = null;
    updateHeader();
    scheduleSaveState();
    return;
  }
  if (ext && ext.bridgeConfig) applyBridgeConfig(ext.bridgeConfig);
  var active = ext.activeSymbol;
  state.symbol = String(active.symbol).toUpperCase();
  state.timeframe = String(active.timeframe).toUpperCase();
  if (active.mode) {
    var m = String(active.mode).toUpperCase();
    if (['AUTO','SCALPER','SNIPER','SWING','ANALYSE','ALERTE','EXECUTION_PREPAREE'].indexOf(m) >= 0) state.tradeMode = m;
  }
  state.price = Number(ext.currentData.price);
  var ss = $('symbolSelect');
  if (ss && Array.from(ss.options).some(function(o) { return o.value === state.symbol; })) ss.value = state.symbol;
  var ts = $('tfSelect'); if (ts) ts.value = state.timeframe;
  var ms = $('modeSelect'); if (ms) ms.value = state.tradeMode;
  updateHeader();
  scheduleSaveState();
}

async function analyzeAllTimeframesAndPickSetup() {
  const allTFs = ['M1', 'M5', 'M15', 'H1', 'H4'];
  const snapshots = [];

  for (const tf of allTFs) {
    try {
      const r = await fetchJson('/coach/realtime?symbol=' + encodeURIComponent(state.symbol) +
        '&tf=' + encodeURIComponent(tf) + '&mode=' + encodeURIComponent(state.tradeMode) + '&lang=fr');
      const agents   = getAgents(r);
      const analysis = agents.analysis || {};
      const risk     = agents.risk || {};
      const it       = r.instantTrade || null;
      const vp       = r.virtualPosition || null;
      const lia      = (r.coach && r.coach.lia) || r.lia || null;

      const rec      = String(analysis.recommendation || (it && it.direction) || '').toUpperCase();
      const strength = Number(analysis.strength || analysis.confidence || (it && it.confidence) || 0);
      const reason   = analysis.reason || (it && (it.technical || it.sentiment)) || '';
      const directional = rec.includes('BUY') || rec.includes('LONG') || rec.includes('SELL') || rec.includes('SHORT');
      const setupType   = (it && it.setup_type) || null;
      const entry = Number((vp && vp.entry) || (it && it.entry) || NaN);
      const sl    = Number((vp && vp.sl)    || (it && it.sl)    || NaN);
      const tp    = Number((vp && vp.tp)    || (it && it.tp)    || NaN);
      const liaText = lia && lia.ok ? lia.response : null;
      const riskLevel = risk.riskLevel || null;

      snapshots.push({
        tf, rec, strength, directional, reason, setupType, riskLevel,
        entry: Number.isFinite(entry) ? entry : null,
        sl:    Number.isFinite(sl)    ? sl    : null,
        tp:    Number.isFinite(tp)    ? tp    : null,
        liaText
      });
    } catch (_) {
      snapshots.push({ tf, rec: 'WAIT', strength: 0, directional: false, reason: 'no-data' });
    }
  }

  // Sort: directional first, then by strength
  snapshots.sort(function(a, b) {
    if (a.directional !== b.directional) return a.directional ? -1 : 1;
    return (b.strength || 0) - (a.strength || 0);
  });

  const winner = snapshots[0] || { tf: state.timeframe, rec: 'WAIT', strength: 0, directional: false };
  const hasSetup = winner.directional;

  if (hasSetup) {
    state.timeframe = winner.tf;
    var ts = $('tfSelect');
    if (ts && Array.from(ts.options).some(function(o) { return o.value === winner.tf; })) ts.value = winner.tf;
    updateHeader();
    // Also sync TF with backend
    fetchJson('/extension/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'set-symbol', payload: { symbol: state.symbol, timeframe: state.timeframe, mode: state.tradeMode, price: state.price } })
    }).catch(function() {});
  }

  // Build analysisText summary
  var otherDirectionals = snapshots.filter(function(s) { return s.tf !== winner.tf && s.directional; });
  var dirLabel = (winner.rec.includes('BUY') || winner.rec.includes('LONG'))   ? '▲ LONG'  :
                 (winner.rec.includes('SELL') || winner.rec.includes('SHORT'))  ? '▼ SHORT' : 'NEUTRE';
  var analysisMsg;
  if (hasSetup) {
    analysisMsg = 'MTF → Unité de temps: ' + winner.tf + ' | ' + dirLabel +
      (winner.strength ? ' (' + winner.strength + '%)' : '') +
      (winner.setupType ? ' | Setup: ' + winner.setupType : '') +
      (otherDirectionals.length
        ? ' | Aussi: ' + otherDirectionals.map(function(s) {
            var d = (s.rec.includes('BUY') || s.rec.includes('LONG')) ? '▲' : '▼';
            return s.tf + d;
          }).join(' ')
        : '');
  } else {
    analysisMsg = 'MTF: Aucun setup directionnel sur ' + allTFs.join('/') + '. Attendre signal clair.';
  }
  var an = $('analysisText');
  if (an) an.textContent = analysisMsg;

  // Build coach narrative (conversational French)
  var coachEl = $('coachText');
  if (coachEl) {
    var tfResults = {};
    snapshots.forEach(function(s) {
      tfResults[s.tf] = { signal: s.rec, recommendation: s.rec };
    });
    var narrativeText = buildCoachNarrative(tfResults, hasSetup ? winner.tf : null, state.symbol);
    coachEl.textContent = narrativeText;
    var rDir = (winner.rec.includes('BUY') || winner.rec.includes('LONG')) ? '#86efac' :
               (winner.rec.includes('SELL') || winner.rec.includes('SHORT')) ? '#fca5a5' : '#fbbf24';
    coachEl.style.color = rDir;
  }

  flowLog('MTF ANALYSIS SUMMARY', {
    symbol: state.symbol,
    winner: winner,
    snapshots: snapshots.map(function(s) { return { tf: s.tf, rec: s.rec, strength: s.strength, directional: s.directional }; })
  });

  return { winner: winner, snapshots: snapshots };
}

async function refreshAll() {
  if (state.bridgeConfig.bridgeEnabled === false) {
    renderBridgeOffState();
    return;
  }

  if (!state.agentSessionActive) {
    try {
      await loadMirrorSnapshot();
      setConn('ONLINE', 'ok');
    } catch (_) {
      setConn('RETRY', 'warn');
      flowLog('MIRROR SNAPSHOT RETRY', { symbol: state.symbol, timeframe: state.timeframe });
    }

    var sig = $('signalText'); if (sig) { sig.textContent = 'ATTENTE'; sig.className = 'signal wait'; }
    var an = $('analysisText'); if (an) an.textContent = 'Session agent inactive. Cliquez ANALYSER pour lancer une analyse réelle.';
    var coach = $('coachText'); if (coach) { coach.textContent = 'Coach inactif. Cliquez ENTRER après validation pour activer le suivi live.'; coach.style.color = '#cbd5e1'; }
    var next = $('dg-nextaction'); if (next) next.textContent = 'Prochaine action : ANALYSER';
    var enterBtn = document.querySelector('[data-action="ENTER"]');
    if (enterBtn) {
      enterBtn.disabled = true;
      enterBtn.title = 'Analyse requise avant entrée.';
    }
    return;
  }

  try {
    await loadRealtimePack();
    setConn('ONLINE', 'ok');
  } catch (e) {
    state.conn.healthFails = Number(state.conn.healthFails || 0) + 1;
    markConnectionTransientFail();
    flowLog('API RETRY /coach/realtime', {
      symbol: state.symbol,
      timeframe: state.timeframe,
      mode: state.tradeMode,
      error: e && e.message ? e.message : 'unknown'
    });
  }
}

// ─── COACH NARRATIVE ──────────────────────────────────────────────────────────
function buildCoachNarrative(tfResults, bestTf, symbol) {
  var lines = [];
  lines.push('J\'analyse ' + symbol + ' sur toutes les unités de temps...');

  var tfLabels = { M1:'le M1', M5:'le M5', M15:'le M15', H1:'le H1', H4:'le H4', D1:'le Daily' };
  var noisy = [];
  var clean = [];

  for (var tf in tfResults) {
    if (!Object.prototype.hasOwnProperty.call(tfResults, tf)) continue;
    var r = tfResults[tf];
    if (!r) continue;
    var sig = (r.signal || r.recommendation || '').toUpperCase();
    if (sig === 'WAIT' || sig === 'NEUTRE' || sig === 'NEUTRAL') noisy.push(tf);
    else clean.push(tf);
  }

  if (noisy.length > 0) {
    lines.push(noisy.map(function(t) { return tfLabels[t] || t; }).join(', ') + ' ' + (noisy.length > 1 ? 'sont bruyants' : 'est bruyant') + ' — pas de setup clair là.');
  }
  if (clean.length > 0) {
    lines.push(clean.map(function(t) { return tfLabels[t] || t; }).join(', ') + ' ' + (clean.length > 1 ? 'montrent' : 'montre') + ' quelque chose de plus propre.');
  }

  if (bestTf && tfResults[bestTf]) {
    var br = tfResults[bestTf];
    var bsig = (br.signal || br.recommendation || '').toUpperCase();
    var isBuy = bsig.includes('BUY') || bsig.includes('LONG') || bsig.includes('ACHAT');
    var isSell = bsig.includes('SELL') || bsig.includes('SHORT') || bsig.includes('VENTE');
    lines.push('→ ' + (tfLabels[bestTf] || bestTf) + ' est l\'unité de temps clé aujourd\'hui.');
    if (isBuy) lines.push('Je vois une pression haussière. Si tu veux entrer, regarde ' + (tfLabels[bestTf] || bestTf) + '.');
    else if (isSell) lines.push('La pression est baissière. Le ' + (tfLabels[bestTf] || bestTf) + ' donne le vrai contexte.');
    else lines.push('Le marché hésite encore. On attend une confirmation.');
  } else {
    lines.push('Pas de setup structurant clair pour l\'instant. On observe.');
  }

  return lines.join('\n');
}

// ─── ENTRY BIP ────────────────────────────────────────────────────────────────
function playEntryBip() {
  try {
    var ctx = new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.15, 0.3].forEach(function(delay) {
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.3, ctx.currentTime + delay);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.12);
      osc.start(ctx.currentTime + delay);
      osc.stop(ctx.currentTime + delay + 0.15);
    });
  } catch(_) {}
}

// ─── TRADE ACTIONS ────────────────────────────────────────────────────────────
async function sendTradeAction(action) {
  try {
    var upperAction = String(action || '').toUpperCase();
    if (upperAction === 'ENTER' || upperAction === 'OPEN') {
      var liveExec = (state.live && state.live.execution) || (state.live && state.live.coach && state.live.coach.execution) || {};
      if (liveExec.canEnter !== true) {
        var blockedMsg = liveExec.reason || (String(liveExec.decision || '').toUpperCase() === 'NO_ENTRY_CONFLICT'
          ? 'Entrée bloquée: conflit de signal TradingView.'
          : 'Entrée non validée: attendre confirmation.');
        var nextBlocked = $('dg-nextaction');
        if (nextBlocked) nextBlocked.textContent = 'Prochaine action : ' + blockedMsg;
        var coachBlocked = $('coachText');
        if (coachBlocked) coachBlocked.textContent = '[IA LIVE]\n' + blockedMsg + '\nNe pas entrer maintenant.';
        return;
      }
    }

    var nextEl = $('dg-nextaction');
    if (nextEl) nextEl.textContent = 'Action en cours : ' + upperAction;
    flowLog('API REQUEST /coach/trade-action', {
      action: upperAction,
      symbol: state.symbol,
      timeframe: state.timeframe,
      mode: state.tradeMode
    });

    var liveHint = state.live || {};
    var vpHint = liveHint.virtualPosition || {};
    var itHint = liveHint.instantTrade || {};
    var metricsHint = (liveHint.tradeReasoning && liveHint.tradeReasoning.metrics) || {};
    var tradeHint = {
      direction: vpHint.direction || itHint.direction || 'WAIT',
      entry: vpHint.entry != null ? vpHint.entry : (itHint.entry != null ? itHint.entry : metricsHint.entry),
      sl: vpHint.sl != null ? vpHint.sl : (itHint.sl != null ? itHint.sl : metricsHint.stopLoss),
      tp: vpHint.tp != null ? vpHint.tp : (itHint.tp != null ? itHint.tp : metricsHint.takeProfit),
      setup_type: itHint.setup_type || (liveHint.tradeReasoning && liveHint.tradeReasoning.setupType) || state.tradeMode,
      rrRatio: itHint.rrRatio || metricsHint.rrRatio || '--',
      source: 'tradingview-indicator-mirror'
    };

    var d = await fetchJson('/coach/trade-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: state.symbol, timeframe: state.timeframe, mode: state.tradeMode, action: action, trade: tradeHint })
    });
    flowLog('API RESPONSE /coach/trade-action', {
      ok: !!d.ok,
      action: String(action || '').toUpperCase(),
      phase: d.state && d.state.phase,
      entered: d.state && d.state.entered
    });
    state.tradeState = d.state || state.tradeState;
    if (upperAction === 'ENTER' || upperAction === 'OPEN') {
      await setAgentSession(true, 'enter');
    } else if (upperAction === 'EXIT' || upperAction === 'RETEST') {
      await setAgentSession(false, 'exit');
    }
    state.stats.trades++;
    state.stats.lastEvent = action + ' ' + fmtTime();
    renderStats();
    await refreshAll();
    if (nextEl) nextEl.textContent = 'Action appliquée : ' + upperAction;

    // ENTER/OPEN: bip d'engagement + message coach avec SL/TP.
    if (upperAction === 'ENTER' || upperAction === 'OPEN') {
      playEntryBip();
      try {
        var live = await fetchJson('/coach/realtime?symbol=' + encodeURIComponent(state.symbol) +
          '&tf=' + encodeURIComponent(state.timeframe) + '&mode=' + encodeURIComponent(state.tradeMode) + '&lang=fr');
        var analysis = (live && live.coach && live.coach.agents && live.coach.agents.analysis) || {};
        var risk = (live && live.coach && live.coach.agents && live.coach.agents.risk) || {};
        var tr = live && live.tradeReasoning ? live.tradeReasoning : {};
        var m = tr.metrics || {};

        // Resolve entry/sl/tp from live state or tradeHint
        var lh = state.live || {};
        var vp = lh.virtualPosition || {};
        var it = lh.instantTrade || {};
        var entryVal = vp.entry != null ? vp.entry : (it.entry != null ? it.entry : (m.entry != null ? m.entry : null));
        var slVal    = vp.sl    != null ? vp.sl    : (it.sl    != null ? it.sl    : (m.stopLoss  != null ? m.stopLoss  : null));
        var tpVal    = vp.tp    != null ? vp.tp    : (it.tp    != null ? it.tp    : (m.takeProfit != null ? m.takeProfit : null));
        var rrVal    = it.rrRatio || m.rrRatio || null;

        var entryMessages = [
          'Je reste avec toi. On la fait ensemble.',
          'Position prise. Je surveille le marché pour toi.',
          'Je te guide jusqu\'à la sortie. On y est.',
          'Je suis là. Je te dis quand bouger.'
        ];
        var engagementMsg = entryMessages[Math.floor(Math.random() * entryMessages.length)];

        var msgLines = [];
        if (entryVal != null) msgLines.push('Entrée : ' + fmtPrice(entryVal));
        if (slVal    != null) msgLines.push('SL : '     + fmtPrice(slVal));
        if (tpVal    != null) msgLines.push('TP : '     + fmtPrice(tpVal));
        if (rrVal    != null) msgLines.push('RR : 1:' + (typeof rrVal === 'number' ? rrVal.toFixed(1) : rrVal));
        msgLines.push(engagementMsg);

        var coach = $('coachText');
        if (coach) {
          coach.textContent = msgLines.join('\n');
          coach.style.color = '#86efac';
        }
        var next = $('dg-nextaction');
        if (next) next.textContent = 'Prochaine action : ' + ((tr.management && tr.management.nextAction) || 'Monitoring live');
      } catch (_) {
        var entryMessages2 = [
          'Je reste avec toi. On la fait ensemble.',
          'Position prise. Je surveille le marché pour toi.',
          'Je te guide jusqu\'à la sortie. On y est.',
          'Je suis là. Je te dis quand bouger.'
        ];
        var fallbackMsg = entryMessages2[Math.floor(Math.random() * entryMessages2.length)];
        var coach2 = $('coachText');
        if (coach2) { coach2.textContent = fallbackMsg; coach2.style.color = '#86efac'; }
      }
    }
  } catch (e) {
    setConn('KO', 'bad');
    var errEl = $('dg-nextaction');
    if (errEl) errEl.textContent = 'Echec action: ' + (e && e.message ? e.message : 'inconnue');
    flowLog('API ERROR /coach/trade-action', {
      action: String(action || '').toUpperCase(),
      error: e && e.message ? e.message : 'unknown'
    });
  }
}

// ─── SYMBOL LIST ─────────────────────────────────────────────────────────────
function markLiveSymbols(symbols) {
  var symSelect = $('symbolSelect');
  if (!symSelect) return;
  var unique = [];
  (Array.isArray(symbols) ? symbols : []).forEach(function(s) {
    var u = String(s || '').toUpperCase();
    if (u && unique.indexOf(u) < 0) unique.push(u);
  });
  Array.from(symSelect.options).forEach(function(opt) {
    var isLive = unique.indexOf(opt.value) >= 0;
    var base = opt.textContent.replace(/^● /, '');
    opt.textContent = isLive ? '● ' + base : base;
    opt.style.color = isLive ? '#22c55e' : '';
    opt.style.fontWeight = isLive ? '800' : '';
  });
  unique.forEach(function(sym) {
    var existing = Array.from(symSelect.options).map(function(o) { return o.value; });
    if (existing.indexOf(sym) < 0) {
      var o = document.createElement('option');
      o.value = sym; o.textContent = '● ' + sym;
      o.style.color = '#22c55e'; o.style.fontWeight = '800';
      symSelect.appendChild(o);
    }
  });
}

async function loadLiveSymbols() {
  try {
    var d = await fetchJson('/mt5/live-symbols');
    var symbols = Array.isArray(d.symbols) ? d.symbols.map(function(s) { return s.symbol; }) : [];
    markLiveSymbols(symbols);
  } catch (_) {}
}

// ─── SSE ──────────────────────────────────────────────────────────────────────
function handleSync(msg) {
  if (!msg || typeof msg !== 'object') return;
  if (msg.type === 'bridge-config') {
    applyBridgeConfig(msg.bridgeConfig || msg);
    updateHeader();
    return;
  }
  // Symbol is lockable by user; timeframe/mode remain shared and always synced.
  var isInitial = msg.type === 'initial-sync';
  var isActiveSymbol = msg.type === 'active-symbol';
  var _msgSrc = String(msg.source || (msg.activeSymbol && msg.activeSymbol.source) || '').toLowerCase();
  var fromTradingviewRuntime = _msgSrc === 'tradingview' || _msgSrc === 'tradingview-extension'
    || String(msg.resolvedBy || (msg.activeSymbol && msg.activeSymbol.resolvedBy) || '').toLowerCase() === 'tv-runtime-fresh';
  if (fromTradingviewRuntime && isActiveSymbol) state.userLocked = false;
  var canUpdateSymbol = isInitial || (isActiveSymbol && (!state.userLocked || fromTradingviewRuntime));
  var shouldSyncContext = isInitial || isActiveSymbol;

  if (shouldSyncContext) {
    if (canUpdateSymbol && msg.symbol) state.symbol = String(msg.symbol).toUpperCase();
    if (msg.timeframe && TFS.indexOf(String(msg.timeframe).toUpperCase()) >= 0)
      state.timeframe = String(msg.timeframe).toUpperCase();
    if (msg.mode) state.tradeMode = String(msg.mode).toUpperCase();
    if (Number.isFinite(Number(msg.price))) state.price = Number(msg.price);
    if (msg.activeSymbol) {
      var as = msg.activeSymbol;
      if (canUpdateSymbol && as.symbol) state.symbol = String(as.symbol).toUpperCase();
      if (as.timeframe && TFS.indexOf(String(as.timeframe).toUpperCase()) >= 0)
        state.timeframe = String(as.timeframe).toUpperCase();
      if (as.mode) state.tradeMode = String(as.mode).toUpperCase();
      if (Number.isFinite(Number(as.price))) state.price = Number(as.price);
    }
    if (msg.bridgeConfig) applyBridgeConfig(msg.bridgeConfig);
    var ss = $('symbolSelect');
    if (ss && Array.from(ss.options).some(function(o) { return o.value === state.symbol; })) ss.value = state.symbol;
    var ts = $('tfSelect');    if (ts) ts.value = state.timeframe;
    var ms = $('modeSelect');
    if (ms && Array.from(ms.options).some(function(o) { return o.value === state.tradeMode; })) ms.value = state.tradeMode;
    updateHeader();
    scheduleSaveState();
  } else if (msg.type === 'mt5-data' || msg.type === 'tradingview-data') {
    // Price-only tick from TV webhook — only apply if symbol matches current state
    var tickSym = String(msg.symbol || '').toUpperCase();
    var activeSrc = String(state.bridgeConfig.activeSource || 'tradingview').toLowerCase() === 'mt5' ? 'mt5' : 'tradingview';
    var symbolMatches = !tickSym || tickSym === state.symbol;
    if (!(activeSrc === 'tradingview' && msg.type === 'mt5-data') && symbolMatches) {
      if (Number.isFinite(Number(msg.price))) { state.price = Number(msg.price); updateHeader(); }
      else if (Number.isFinite(Number(msg.bid))) { state.price = Number(msg.bid); updateHeader(); }
      // B4 FIX: also update TF if TV sends a different one for this same symbol
      if (msg.timeframe && TFS.indexOf(String(msg.timeframe).toUpperCase()) >= 0) {
        var newTf = String(msg.timeframe).toUpperCase();
        if (newTf !== state.timeframe) {
          state.timeframe = newTf;
          var _ts = $('tfSelect'); if (_ts) _ts.value = newTf;
          updateHeader();
        }
      }
    }
    // Bot-alive visual: show live data arriving
    showLiveFlux(msg);
    checkEntryProximityAndBeep(state.live || {});
  }
}

function showLiveFlux(msg) {
  var sym   = msg.symbol || state.symbol;
  var px    = msg.price || msg.bid || null;
  var rsiRaw = msg.indicators && msg.indicators.rsi;
  var rsi   = Number.isFinite(Number(rsiRaw)) ? ' RSI:' + Number(rsiRaw).toFixed(0) : '';
  var pxStr = px ? ' @ ' + fmtPrice(px) : '';
  var src   = msg.type === 'mt5-data' ? 'MT5' : 'TV';
  markConnectionOk(src + ' LIVE \u26a1');
  // Update webhook badge with last received symbol
  var wb = $('webhookBadge');
  if (wb) { wb.textContent = sym + pxStr + rsi; wb.className = 'bdg ok'; }
  flowLog('SSE DATA RECEIVED', {
    type: msg.type || null,
    symbol: sym,
    timeframe: msg.timeframe || null,
    price: px || null,
    source: src
  });

  // Keep coach/decision truly live without flooding API.
  var now = Date.now();
  if (state.bridgeConfig.bridgeEnabled !== false && state.agentSessionActive && (now - state.lastLiveCoachRefreshAt) >= 1500) {
    state.lastLiveCoachRefreshAt = now;
    loadRealtimePack().catch(function() {});
  }
}

function connectSSE() {
  if (state.sse) { try { state.sse.close(); } catch (_) {} state.sse = null; }
  var es = new EventSource(API + '/extension/sync');
  state.sse = es;
  es.onopen = function() { markConnectionOk('ONLINE'); };
  es.onmessage = function(ev) {
    try {
      var msg = JSON.parse(ev.data || '{}');
      handleSync(msg);
      // Full refresh only on structural state changes, not on every price tick
      var needsRefresh = ['initial-sync', 'active-symbol', 'bridge-config'];
      if (needsRefresh.indexOf(msg.type) >= 0) refreshAll();
    } catch (_) {}
  };
  es.onerror = function() {
    state.conn.sseFails = Number(state.conn.sseFails || 0) + 1;
    markConnectionTransientFail();
    try { es.close(); } catch (_) {}
    setTimeout(connectSSE, 3000);
  };
}

// ─── PERSISTENT WINDOW ───────────────────────────────────────────────────────
function openWindow() {
  try {
    var url = chrome.runtime.getURL('popup.html?persistent=1');
    chrome.windows.create({ url: url, type: 'popup', width: 460, height: 820, focused: true });
    window.close();
  } catch (_) {
    window.open(window.location.href + '?persistent=1', '_blank', 'width=460,height=820');
  }
}

// ─── BIND ─────────────────────────────────────────────────────────────────────
function bindAll() {
  var ss = $('symbolSelect');
  var ts = $('tfSelect');
  var ms = $('modeSelect');

  if (ss) ss.addEventListener('change', function() {
    state.symbol = ss.value || 'XAUUSD';
    state.userLocked = true;  // user choice = source of truth
    fetchJson('/extension/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: 'set-symbol',
        payload: { symbol: state.symbol, timeframe: state.timeframe, mode: state.tradeMode, price: state.price }
      })
    }).catch(function() {});
    refreshAll();
    renderMultiTF();
    scheduleSaveState();
  });
  if (ts) ts.addEventListener('change', function() {
    var tf = String(ts.value || 'H1').toUpperCase();
    state.timeframe = TFS.indexOf(tf) >= 0 ? tf : 'H1';
    fetchJson('/extension/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: 'set-symbol',
        payload: { symbol: state.symbol, timeframe: state.timeframe, mode: state.tradeMode, price: state.price }
      })
    }).catch(function() {});
    refreshAll();
    renderMultiTF();
    scheduleSaveState();
  });
  if (ms) ms.addEventListener('change', function() {
    var m = String(ms.value || 'AUTO').toUpperCase();
    state.tradeMode = ['AUTO','SCALPER','SNIPER','SWING','ANALYSE','ALERTE','EXECUTION_PREPAREE'].indexOf(m) >= 0 ? m : 'AUTO';
    fetchJson('/extension/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: 'set-bridge-config',
        payload: { bridgeMode: state.tradeMode, updatedBy: 'extension-popup' }
      })
    }).catch(function() {});
    refreshAll();
    scheduleSaveState();
  });

  var bd = $('btnDetach');
  if (bd) {
    if (!state.persistent) {
      bd.addEventListener('click', openWindow);
    } else {
      bd.hidden = true;
    }
  }

  var ftv = $('focusTradingViewBtn');
  if (ftv) ftv.addEventListener('click', async function() {
    try {
      var tabs = await chrome.tabs.query({ url: 'https://*.tradingview.com/*' });
      var t = tabs.find(function(x) { return x.active; }) || tabs[0];
      if (!t || typeof t.id !== 'number') return;
      await chrome.tabs.update(t.id, { active: true });
      if (typeof t.windowId === 'number') await chrome.windows.update(t.windowId, { focused: true });
    } catch (_) {}
  });

  var cw = $('closeWindowBtn');
  if (cw) cw.addEventListener('click', function() { window.close(); });

  var tc = $('toggleChart');
  if (tc) tc.addEventListener('click', function() {
    state.chartOpen = !state.chartOpen;
    var cb = $('chartBody');
    if (cb) cb.classList.toggle('hidden', !state.chartOpen);
    tc.innerHTML = state.chartOpen
      ? '&#128200; GRAPHIQUE &#9660;'
      : '&#128200; GRAPHIQUE &#9654;';
    if (state.chartOpen) {
      if (typeof ChartModule !== 'undefined' && ChartModule) {
        if (ChartModule.init) ChartModule.init('chart-container');
          ChartModule.loadChart(state.symbol, state.timeframe, null, state.price);
      }
    }
      scheduleSaveState();
  });

  // Multi-TF cards — click switches TF
  document.querySelectorAll('.tfc[data-tfc]').forEach(function(card) {
    card.addEventListener('click', function() {
      var tf = card.getAttribute('data-tfc');
      if (TFS.indexOf(tf) >= 0) {
        state.timeframe = tf;
        var ts2 = $('tfSelect'); if (ts2) ts2.value = tf;
        fetchJson('/extension/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            command: 'set-symbol',
            payload: { symbol: state.symbol, timeframe: state.timeframe, mode: state.tradeMode, price: state.price }
          })
        }).catch(function() {});
        updateHeader();
        refreshAll();
        scheduleSaveState();
      }
    });
  });

  // Trade action buttons
  document.querySelectorAll('[data-action]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var a = btn.getAttribute('data-action');
      if (a) sendTradeAction(a);
    });
  });

  // ANALYSE button: inserted dynamically to keep existing layout untouched.
  var acts = document.querySelector('.acts-grid');
  if (acts && !document.getElementById('btnAnalyzeNow')) {
    var b = document.createElement('button');
    b.id = 'btnAnalyzeNow';
    b.className = 'btn-sub';
    b.textContent = 'ANALYSER';
    b.addEventListener('click', async function() {
      // B5 FIX: always freshen state from TV/backend before analysing.
      // Clears userLocked so analysis always runs on the live TV context.
      state.userLocked = false;
      try {
        var freshExt = await fetchJson('/extension/data');
        var freshActive = (freshExt && freshExt.activeSymbol) || {};
        if (freshActive.symbol) state.symbol = String(freshActive.symbol).toUpperCase();
        if (freshActive.timeframe && TFS.indexOf(String(freshActive.timeframe).toUpperCase()) >= 0)
          state.timeframe = String(freshActive.timeframe).toUpperCase();
        var freshPrice = Number(freshActive.price);
        if (!Number.isFinite(freshPrice) || freshPrice <= 0) {
          var cd = (freshExt && freshExt.currentData) || {};
          var cdSym = String(cd.symbol || '').toUpperCase();
          var stSym = String(state.symbol || '').toUpperCase();
          var cdSymNorm = cdSym.replace(/[\/-]/g, '');
          var stSymNorm = stSym.replace(/[\/-]/g, '');
          if (cdSym && stSym && (cdSym === stSym || cdSymNorm === stSymNorm)) {
            var cdPrice = Number(cd.price);
            if (Number.isFinite(cdPrice) && cdPrice > 0) freshPrice = cdPrice;
          }
        }
        if (Number.isFinite(freshPrice) && freshPrice > 0) state.price = freshPrice;
        else state.price = null;
        if (freshExt && freshExt.bridgeConfig) applyBridgeConfig(freshExt.bridgeConfig);
        if (freshActive.mode) {
          var _fm = String(freshActive.mode).toUpperCase();
          if (['AUTO','SCALPER','SNIPER','SWING','ANALYSE','ALERTE','EXECUTION_PREPAREE'].indexOf(_fm) >= 0) state.tradeMode = _fm;
        }
        var _fss = $('symbolSelect'); if (_fss && Array.from(_fss.options).some(function(o){return o.value===state.symbol;})) _fss.value = state.symbol;
        var _fts = $('tfSelect'); if (_fts) _fts.value = state.timeframe;
        updateHeader();
      } catch(_) {}
      flowLog('ANALYSE TRIGGERED', {
        symbol: state.symbol,
        timeframe: state.timeframe,
        mode: state.tradeMode
      });
      setConn('ANALYSE...', 'warn');
      var an = $('analysisText'); if (an) an.textContent = 'ANALYSE EN COURS...';
      try {
        await setAgentSession(true, 'analyze');
        var resp = await fetchJson('/extension/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: 'analyze', payload: { symbol: state.symbol, timeframe: state.timeframe, mode: state.tradeMode } })
        });
        var mtf = await analyzeAllTimeframesAndPickSetup();
        flowLog('ANALYSE RESPONSE RECEIVED', {
          ok: !!resp.ok,
          message: resp.message || null,
          analysisTriggered: resp.analysisTriggered === true,
          selectedTimeframe: mtf && mtf.winner ? mtf.winner.tf : state.timeframe,
          selectedRecommendation: mtf && mtf.winner ? mtf.winner.rec : null
        });
        await refreshAll();
        await renderMultiTF();
        state.stats.lastEvent = 'ANALYSE ' + fmtTime();
        renderStats();
        var connLabel = (mtf && mtf.winner && mtf.winner.directional)
          ? 'MTF ' + mtf.winner.tf + ' OK'
          : 'ANALYSE OK';
        setConn(connLabel, 'ok');
        // analysisText already set by analyzeAllTimeframesAndPickSetup; only fallback if still blank
        var an2 = $('analysisText');
        if (an2 && !an2.textContent) an2.textContent = 'Analyse reçue. Mise à jour UI terminée.';
      } catch (_) {
        setConn('ANALYSE KO', 'bad');
        var an3 = $('analysisText'); if (an3) an3.textContent = 'Échec analyse. Vérifier flux backend.';
        flowLog('ANALYSE ERROR', {
          symbol: state.symbol,
          timeframe: state.timeframe,
          mode: state.tradeMode
        });
      }
    });
    acts.appendChild(b);
  }

  if (acts && !document.getElementById('btnSourceTv')) {
    var stv = document.createElement('button');
    stv.id = 'btnSourceTv';
    stv.className = 'btn-sub buy';
    stv.textContent = 'TRADINGVIEW ON';
    stv.addEventListener('click', async function() {
      try {
        await setActiveSource('tradingview');
        state.stats.lastEvent = 'SOURCE TV ' + fmtTime();
        renderStats();
        await refreshAll();
      } catch (_) {
        setConn('SOURCE KO', 'bad');
      }
    });
    acts.appendChild(stv);
  }

  if (acts && !document.getElementById('btnSourceMt5')) {
    var smt5 = document.createElement('button');
    smt5.id = 'btnSourceMt5';
    smt5.className = 'btn-sub';
    smt5.textContent = 'MT5 OFF';
    smt5.addEventListener('click', async function() {
      try {
        await setActiveSource('mt5');
        state.stats.lastEvent = 'SOURCE MT5 ' + fmtTime();
        renderStats();
        await refreshAll();
      } catch (_) {
        setConn('SOURCE KO', 'bad');
      }
    });
    acts.appendChild(smt5);
  }

  // Explicit BRIDGE ON/OFF button in extension controls.
  if (acts && !document.getElementById('btnBridgeToggle')) {
    var bt = document.createElement('button');
    bt.id = 'btnBridgeToggle';
    bt.className = 'btn-sub';
    bt.textContent = 'BRIDGE ACTIF';
    bt.addEventListener('click', async function() {
      var next = state.bridgeConfig.bridgeEnabled === false;
      try {
        await fetchJson('/extension/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            command: 'set-bridge-config',
            payload: { bridgeEnabled: next, updatedBy: 'extension-popup-button' }
          })
        });
      } catch (_) {}
    });
    acts.appendChild(bt);
    applyBridgeConfig(state.bridgeConfig);
  }

  // Bridge ON/OFF toggle using existing badge (no design refactor).
  var bridgeBadge = $('bridgeBadge');
  if (bridgeBadge) {
    bridgeBadge.addEventListener('click', async function() {
      var next = state.bridgeConfig.bridgeEnabled === false;
      try {
        await fetchJson('/extension/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: 'set-bridge-config', payload: { bridgeEnabled: next, updatedBy: 'extension-popup' } })
        });
      } catch (_) {}
    });
  }
}

// ─── INIT ─────────────────────────────────────────────────────────────────────
async function bootstrapSymbolFromExtension() {
  // 1. Essayer le background de l'extension (symbole détecté depuis TradingView DOM)
  try {
    if (typeof chrome !== 'undefined' && chrome.runtime) {
      const ctx = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ type: 'GET_ACTIVE_CONTEXT' }, (resp) => {
          if (chrome.runtime.lastError) reject(chrome.runtime.lastError);
          else resolve(resp);
        });
      });
      if (ctx?.ok && ctx.context?.symbol) {
        state.symbol = ctx.context.symbol;
        if (ctx.context.timeframe) state.timeframe = ctx.context.timeframe;
        if (ctx.context.price) state.price = ctx.context.price;
        console.log('[BOOT] Symbole depuis TradingView extension:', state.symbol);
        return true;
      }
    }
  } catch (_) {}

  // 2. Fallback localStorage (déjà géré par loadPersistedState, rien à faire)
  // 3. Fallback XAUUSD reste en dernier recours
  console.log('[BOOT] Aucun contexte TradingView live — fallback localStorage/XAUUSD');
  return false;
}

async function boot() {
  loadPersistedState();
  await bootstrapSymbolFromExtension();
  updateHeader();
  state.persistent = isPersistent();
  if (state.persistent) {
    document.body.classList.add('win');
    var wa = $('windowActions'); if (wa) wa.hidden = false;
    var bd = $('btnDetach');     if (bd) bd.hidden = true;
  }

  bindAll();

  // Load initial state from extension data
  try {
    var d = await fetchJson('/extension/data');
    var ext = d.activeSymbol || {};
    applyBridgeConfig(d.bridgeConfig || null);
    if (ext.symbol) state.symbol = String(ext.symbol).toUpperCase();
    if (ext.timeframe && TFS.indexOf(String(ext.timeframe).toUpperCase()) >= 0)
      state.timeframe = String(ext.timeframe).toUpperCase();
    if (ext.mode) {
      var m = String(ext.mode).toUpperCase();
      state.tradeMode = ['AUTO','SCALPER','SNIPER','SWING','ANALYSE','ALERTE','EXECUTION_PREPAREE'].indexOf(m) >= 0 ? m : 'AUTO';
    }
    var _cd = d.currentData || {};
    var _cand = Number(_cd.price);
    if (!Number.isFinite(_cand) || _cand <= 0) _cand = Number(ext.price);
    if (Number.isFinite(_cand) && _cand > 0) state.price = _cand;
    else state.price = null;
  } catch (_) {}

  // Sync selects
  var ss = $('symbolSelect');
  if (ss && Array.from(ss.options).some(function(o) { return o.value === state.symbol; })) ss.value = state.symbol;
  var ts = $('tfSelect'); if (ts) ts.value = state.timeframe;
  var ms = $('modeSelect'); if (ms) ms.value = state.tradeMode;

  updateHeader();

  // Init chart module (but don't load yet — chart starts collapsed)
  if (typeof ChartModule !== 'undefined' && ChartModule && ChartModule.init) {
    ChartModule.init('chart-container');
  }

  // Start in manual mode: orchestration only on ANALYSE/ENTER session.
  fetchJson('/orchestration/disable', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trigger: 'boot-manual' })
  }).catch(function() {});

  // Connect SSE first (real-time updates)
  connectSSE();

  // First load
  await refreshHealth();
  await refreshAll();
  loadLiveSymbols();
  renderMultiTF();

  // Intervals
  setInterval(refreshAll,       8000);   // refresh core data every 8s
  setInterval(renderMultiTF,   30000);   // refresh multi-TF every 30s
  setInterval(refreshHealth,   10000);   // check health every 10s
  setInterval(loadLiveSymbols, 15000);   // refresh symbol list every 15s
}

window.addEventListener('load', function() { boot().catch(function() {}); });
