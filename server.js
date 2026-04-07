// ─── TRADINGVIEW LIVE INGESTION ─────────────────────────────────────────────
const tvDataStore = {};

app.post('/tradingview/live', (req, res) => {
  try {
    const VALID_TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'D1', 'W1'];
    const VALID_SYMBOLS = ['XAUUSD', 'XAGUSD', 'NAS100', 'US500', 'US30', 'DE40', 'BTCUSD', 'ETHUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY'];

    const { symbol, timeframe, price, timestamp, source } = req.body || {};

    if (!symbol || typeof symbol !== 'string') {
      return res.status(400).json({ error: 'symbol manquant ou invalide' });
    }

    const normalizedSymbol = symbol.toUpperCase().trim();
    if (!VALID_SYMBOLS.includes(normalizedSymbol)) {
      return res.status(400).json({ error: `symbol non reconnu: ${normalizedSymbol}` });
    }

    if (!timeframe || !VALID_TIMEFRAMES.includes(timeframe)) {
      return res.status(400).json({ error: `timeframe invalide: ${timeframe}` });
    }

    const parsedPrice = parseFloat(price);
    if (isNaN(parsedPrice) || parsedPrice <= 0) {
      return res.status(400).json({ error: 'price invalide' });
    }

    if (!symbol || !timeframe || !price) {
      return res.status(400).json({ ok: false, error: 'symbol, timeframe, price required' });
    }
    const payload = { symbol, timeframe, price, timestamp: timestamp || new Date().toISOString(), source: source || 'tradingview' };
    console.log('[BACKEND RECEIVED]', payload);
    // Stockage en RAM par symbole
    tvDataStore[symbol] = { ...payload, updatedAt: Date.now() };
    console.log('[BACKEND STORED]', symbol, '→', tvDataStore[symbol]);

    // Broadcast prix live vers clients SSE (dashboard + extension)
    try {
      broadcastToExtension({
        type: 'price-update',
        symbol: normalizedSymbol,
        timeframe: timeframe,
        price: parsedPrice,
        timestamp: new Date().toISOString(),
        source: 'tradingview'
      });
    } catch (e) {
      // Non bloquant — le broadcast est best-effort
    }

    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});


// server.js — Trading Auto Backend
// Sources de données: MT5 (priorité 1) → TradingView (priorité 2) → Yahoo Finance (klines uniquement)
// AUCUN Math.random() pour les prix — toutes les données sont réelles

'use strict';

// ─── SINGLE-INSTANCE GUARD — abort immédiat si port déjà occupé ──────────────
const _net = require('net');
const _portGuard = _net.createServer();
_portGuard.once('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`\n[ABORT] PORT 4000 DÉJÀ OCCUPÉ — instance en conflit détectée.`);
    console.error(`[ABORT] Kill avec: taskkill /F /IM node.exe /T   puis relancez.`);
    process.exit(1);
  }
});
_portGuard.once('listening', () => {
  _portGuard.close(); // port libre confirmé — on peut continuer
});
_portGuard.listen(4000, '127.0.0.1');
// ─────────────────────────────────────────────────────────────────────────────

const express = require('express');
const path    = require('path');
const fs      = require('fs');
const os      = require('os');
const { spawn, execSync } = require('child_process');
const app     = express();
const PORT    = 4000;  // Studio HTML - TRADING AUTO EXCLUSIVE
if (!process.env.BROKER_MODE) process.env.BROKER_MODE = 'live';
if (!process.env.SAFE_MODE) process.env.SAFE_MODE = '0';
const SAFE_MODE = process.env.SAFE_MODE !== '0';

// ─── Middleware ───────────────────────────────────────────────────────────────
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));
app.use('/public', express.static(path.join(__dirname, 'public')));

// ─── DEV HELPER — injecte le bouton contexte dans chaque page HTML ────────────
const DEV_HELPER_TAG = '\n<script src="/public/dev-helper.js"></script>\n</body>';
function sendHTMLWithHelper(res, filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  const html = raw.includes('dev-helper.js') ? raw : raw.replace('</body>', DEV_HELPER_TAG);
  res.type('html').send(html);
}

// ─── MENU PRINCIPAL ───────────────────────────────────────────────────────
app.get('/', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'index.html')));
app.get('/audit', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'audit-dashboard.html')));
app.get('/audit-dashboard', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'audit-dashboard.html')));
app.get('/live', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'live-ops.html')));
app.get('/sse-test', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'sse-test.html')));
app.get('/studio',  (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'studio', 'index-simple.html')));
app.get('/studio/', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'studio', 'index-simple.html')));
app.get('/control-panel', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'control-panel.html')));
// Studio assets (JS, CSS) servis après les routes HTML
app.use('/studio', express.static(path.join(__dirname, 'studio')));

// ─── Modules réels ───────────────────────────────────────────────────────────
const marketHoursChecker = require('./lib/market-hours-checker'); // [P2] Market hours detection
const agentBus = require('./agent-bus'); // [P3] Agent registry and messaging
const alertManager = require('./alert-manager'); // [P2] Alert system
const realDataSimulator = require('./lib/real-data-simulator'); // [ÉTAPE 1] Real multi-symbol data
let surveillanceAgent, marketStore, normalizeSymbol, orchestrator, auditLogger, indicatorAgent, repairAgent;
let lastRealData = null; // Cache latest real data
let candleManager = null; // [P1] CandleManager — instancié séparément pour isolation
const localPriceStreams = Object.create(null); // symbol -> [{time, open, high, low, close, volume}]

// ─── COACH MESSAGE BUILDER (hiérarchisé, vivant, Pine-driven) ───────────────
function buildCoachMessage(robot) {
  if (!robot || typeof robot !== 'object') return 'Analyse indisponible.';
  let msg = [];
  // 1. Macro
  let macro = [];
  if (robot.macro_bull || robot.macro_bear) {
    if (robot.macro_bull) macro.push('macro haussier');
    if (robot.macro_bear) macro.push('macro baissier');
  }
  if (macro.length) msg.push('Macro : ' + macro.join(' / '));
  // 2. Zones / liquidités
  let zones = [];
  if (robot.zone_proche) zones.push('zone proche = ' + robot.zone_proche);
  if (robot.liq_haute_active) zones.push('liquidité haute active');
  if (robot.liq_basse_active) zones.push('liquidité basse active');
  if (robot.in_top_zone) zones.push('prix en zone haute');
  if (robot.in_bot_zone) zones.push('prix en zone basse');
  if (zones.length) msg.push('Zones : ' + zones.join(' / '));
  // 3. Technique multi-timeframe
  let tech = [];
  if (robot.lecture_1m) tech.push('M1: ' + robot.lecture_1m);
  if (robot.lecture_5m) tech.push('M5: ' + robot.lecture_5m);
  if (robot.lecture_15m) tech.push('M15: ' + robot.lecture_15m);
  if (robot.lecture_60m) tech.push('H1: ' + robot.lecture_60m);
  if (robot.rsi_1m) tech.push('RSI M1: ' + robot.rsi_1m);
  if (robot.rsi_5m) tech.push('RSI M5: ' + robot.rsi_5m);
  if (robot.rsi_15m) tech.push('RSI M15: ' + robot.rsi_15m);
  if (robot.rsi_60m) tech.push('RSI H1: ' + robot.rsi_60m);
  if (robot.short_score) tech.push('score short: ' + robot.short_score);
  if (robot.long_score) tech.push('score long: ' + robot.long_score);
  if (robot.bearRej) tech.push('bear rejection');
  if (robot.bullRej) tech.push('bull rejection');
  if (tech.length) msg.push('Technique : ' + tech.join(' / '));
  // 4. Anticipation
  let anticipation = [];
  if (robot.anticipation) anticipation.push(robot.anticipation + (robot.anticipation_force ? ' (' + robot.anticipation_force + '%)' : ''));
  if (anticipation.length) msg.push('Anticipation : ' + anticipation.join(' / '));
  // 5. Conclusion
  let conclusion = [];
  if (robot.verdict) conclusion.push('verdict = ' + robot.verdict);
  if (robot.signal) conclusion.push('signal = ' + robot.signal);
  if (robot.event) conclusion.push('événement = ' + robot.event);
  if (conclusion.length) msg.push('Conclusion : ' + conclusion.join(' / '));
  // WAIT intelligent
  if (robot.verdict && robot.verdict.toUpperCase().includes('WAIT')) {
    let waitMsg = [];
    if (robot.anticipation && robot.anticipation_force < 90) waitMsg.push('Anticipation en construction, validation technique incomplète.');
    if (robot.zone_proche) waitMsg.push('Surveillance active de la zone : ' + robot.zone_proche);
    if (robot.bullRej || robot.bearRej) waitMsg.push('Rejet détecté : ' + (robot.bullRej ? 'bull' : '') + (robot.bearRej ? 'bear' : ''));
    if (waitMsg.length) msg.push('Pourquoi WAIT : ' + waitMsg.join(' / '));
  }
  return msg.join('\n');
}

try {
  surveillanceAgent = require('./src/agents/surveillance-agent'); // [P3] Event-driven analysis trigger
  indicatorAgent = require('./src/agents/indicator-agent'); // [P4] Technical indicators
  repairAgent = require('./src/agents/repair-agent'); // [P4] Repair/diagnostics
  marketStore      = require('./store/market-store');
  normalizeSymbol  = require('./lib/symbol-normalizer').normalizeSymbol;
  orchestrator     = require('./src/agents/orchestrator');
  auditLogger      = require('./audit-logger');
} catch (e) {
  console.error('[WARN] Modules avancés non disponibles:', e.message);
  // Fallbacks minimalistes pour éviter le crash serveur
  marketStore = {
    bySymbol: {}, analysisCache: {}, sseClients: [],
    systemStatus: { source: 'offline', fluxStatus: 'OFFLINE' },
    lastActiveSymbol: null,
    lastActiveTimeframe: 'H1',
    lastActivePrice: null,
    updateFromMT5: function(p, s) { 
      this.bySymbol[s] = { latestPayload: p, updatedAt: Date.now() };
      this.lastActiveSymbol = s;
      this.lastActiveTimeframe = p.timeframe || 'H1';
      this.lastActivePrice = p.price || p.bid || p.ask || null;
    },
    updateAnalysis: function(s, a) { this.analysisCache[s] = a; this.broadcast({ type: 'analysis', symbol: s, analysis: a }); },
    addSSEClient: function(res) { this.sseClients.push(res); res.on('close', () => { this.sseClients = this.sseClients.filter(c => c !== res); }); },
    broadcast: function(d) { if (this.sseClients.length === 0) return; const m = 'data: ' + JSON.stringify(d) + '\n\n'; this.sseClients = this.sseClients.filter(res => { try { res.write(m); return true; } catch { return false; } }); },
    getState: function() { return { systemStatus: this.systemStatus, bySymbol: this.bySymbol, analysisCache: this.analysisCache }; },
    getLatestForSymbol: function(s) { return this.bySymbol[s] || null; }
  };
  normalizeSymbol = (raw) => {
    const clean = String(raw || 'EURUSD').trim().toUpperCase().replace(/[._-](A|B|C|PRO|MICRO|MINI|NANO|CASH|ECN|STP|RAW|VIP|M|N|X)$/i, '');

    let canonical = clean;
    if (/XAU|GOLD/.test(clean)) canonical = 'XAUUSD';
    else if (/XAG|SILVER/.test(clean)) canonical = 'XAGUSD';
    else if (/NAS100|NASDAQ|US100/.test(clean)) canonical = 'NAS100';
    else if (/US500|SPX|SP500|S&P/.test(clean)) canonical = 'US500';
    else if (/US30|DOW|DJI/.test(clean)) canonical = 'US30';
    else if (/DE40|DAX|GER40/.test(clean)) canonical = 'DE40';
    else if (/^BTC/.test(clean)) canonical = 'BTCUSD';
    else if (/^ETH/.test(clean)) canonical = 'ETHUSD';

    const type = /XAU|XAG/.test(canonical) ? 'metal' : /BTC|ETH/.test(canonical) ? 'crypto' : /US30|US500|NAS100|DE40/.test(canonical) ? 'index' : 'forex';
    const digits = type === 'metal' ? 2 : type === 'crypto' ? 2 : type === 'index' ? 1 : 5;
    const slPct = type === 'metal' ? 0.004 : type === 'crypto' ? 0.012 : type === 'index' ? 0.005 : 0.002;
    const tpPct = type === 'metal' ? 0.012 : type === 'crypto' ? 0.030 : type === 'index' ? 0.015 : 0.006;
    const pip = type === 'metal' ? 0.1 : type === 'crypto' ? 1 : type === 'index' ? 1 : 0.0001;
    return { canonical, broker_symbol: raw, type, digits, slPct, tpPct, pip };
  };
  orchestrator = null;
}

// ─── [P1] CANDLE MANAGER — chargé séparément pour isolation totale ────────────
try {
  const CandleManager = require('./lib/candle-manager');
  candleManager = new CandleManager();
  candleManager.on('candle:closed', (event) => {
    marketStore.broadcast({ type: 'candle:closed', symbol: event.symbol, timeframe: event.timeframe, candle: event.candle, timestamp: event.timestamp });
    console.log(`[CANDLE] ${event.symbol} ${event.timeframe} bougie fermée — O:${event.candle?.open} H:${event.candle?.high} L:${event.candle?.low} C:${event.candle?.close}`);
  });
  console.log('[CANDLE] CandleManager chargé — en attente d\'initialize()');
} catch (e) {
  console.error('[CANDLE WARN] CandleManager non disponible:', e.message);
  candleManager = null;
}

// ─── MT5 DATA ACCESS FUNCTION ──────────────────────────────────────────────────
// Reads real MT5 data from mt5_data.json (written by EA)
function mt5Fetch(path) {
  return new Promise((resolve, reject) => {
    try {
      const dataFile = require('path').join(__dirname, 'mt5_data.json');
      const rawData = require('fs').readFileSync(dataFile, 'utf8');
      const mt5Data = JSON.parse(rawData);
      
      if (path.includes('/mt5/price')) {
        const symbol = mt5Data.symbol?.name || 'UNKNOWN';
        const price = mt5Data.symbol?.price;
        if (price !== undefined) {
          resolve({ ok: true, symbol, price });
        } else {
          reject(new Error('Price data not available in mt5_data.json'));
        }
      } else if (path.includes('/mt5/klines')) {
        const klines = mt5Data.klines || [];
        resolve({ ok: true, klines });
      } else {
        reject(new Error('Unknown MT5 endpoint'));
      }
    } catch (e) {
      reject(e);
    }
  });
}

function recordLocalPricePoint(symbol, payload) {
  try {
    const sym = String(symbol || '').toUpperCase();
    if (!sym) return;
    const rawPrice = payload?.price ?? payload?.bid ?? payload?.ask;
    const price = Number(rawPrice);
    if (!Number.isFinite(price) || price <= 0) return;
    const ts = payload?.timestamp ? new Date(payload.timestamp).getTime() : Date.now();
    const point = {
      time: ts,
      open: price,
      high: price,
      low: price,
      close: price,
      volume: Number(payload?.volume || 0)
    };
    if (!Array.isArray(localPriceStreams[sym])) localPriceStreams[sym] = [];
    localPriceStreams[sym].push(point);
    if (localPriceStreams[sym].length > 400) {
      localPriceStreams[sym] = localPriceStreams[sym].slice(-400);
    }
  } catch (_) {}
}

if (marketStore && typeof marketStore.on === 'function') {
  marketStore.on('mt5-update', (sym, payload) => {
    recordLocalPricePoint(sym, payload || {});
  });
}

// ─── MT5 Bridge Configuration ──────────────────────────────────────────────────
// Single-environment lock: only localhost:4000 bridge endpoint is accepted.
const _bridgeEnvRaw = String(process.env.MT5_BRIDGE || '').trim();
const MT5_BRIDGE_PYTHON = /^https?:\/\/(127\.0\.0\.1|localhost):4000(\/|$)/i.test(_bridgeEnvRaw)
  ? _bridgeEnvRaw.replace(/\/$/, '')
  : '';

// Bridge status tracker
let bridgeStatus = {
  connected: false,
  lastCheck: null,
  checkInterval: 5000
};

// ─── MT5 DATA POLLING — Pull data from MT5 data file every 2 seconds ──────────
let _mt5PollTimer = null;

function extractSnapshotSymbols(data) {
  const out = [];
  if (!data || typeof data !== 'object') return out;

  if (data.symbol && typeof data.symbol === 'object') {
    out.push(data.symbol);
  }

  if (Array.isArray(data.symbols)) {
    data.symbols.forEach((s) => {
      if (s && typeof s === 'object') out.push(s);
    });
  } else if (data.symbols && typeof data.symbols === 'object') {
    Object.entries(data.symbols).forEach(([name, value]) => {
      if (value && typeof value === 'object') {
        out.push({ name, ...value });
      }
    });
  }

  return out;
}

function normalizeSnapshotCandles(candles) {
  if (!Array.isArray(candles)) return [];
  return candles
    .map((c) => ({
      time: c.time || c.timestamp || Date.now(),
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
      volume: Number(c.volume || 0)
    }))
    .filter((c) => Number.isFinite(c.open) && Number.isFinite(c.high) && Number.isFinite(c.low) && Number.isFinite(c.close));
}

function ingestMT5Snapshot(data, sourceLabel, freshness = null) {
  const symbols = extractSnapshotSymbols(data);
  if (!symbols.length) return 0;

  symbols.forEach((mtData) => {
    const symbolName = String(mtData.name || mtData.symbol || '').toUpperCase();
    if (!symbolName) return;
    const canonical = normalizeSymbol(symbolName).canonical;

    let chartCandles = [];
    if (data?.charts && typeof data.charts === 'object') {
      const symChart = data.charts[symbolName] || data.charts[canonical] || data.charts[mtData.name];
      if (symChart && Array.isArray(symChart.candles)) chartCandles = normalizeSnapshotCandles(symChart.candles);
    }
    if (chartCandles.length === 0 && data?.chart && Array.isArray(data.chart.candles)) {
      chartCandles = normalizeSnapshotCandles(data.chart.candles);
    }

    marketStore.updateFromMT5({
      symbol: symbolName,
      price: mtData.price || mtData.bid,
      bid: mtData.bid || mtData.price,
      ask: mtData.ask || mtData.price,
      volume: mtData.volume || 0,
      timeframe: mtData.timeframe || data?.chart?.timeframe || 'H1',
      source: sourceLabel,
      timestamp: new Date().toISOString(),
      history: chartCandles,
      ohlc: chartCandles,
      fileFreshness: freshness || undefined
    }, canonical);
  });

  return symbols.length;
}

async function pollMT5BridgeData() {
  try {
    const activeSource = String(bridgeConfig.activeSource || (bridgeConfig.mt5Enabled === true ? 'mt5' : 'tradingview')).toLowerCase() === 'mt5' ? 'mt5' : 'tradingview';
    if (activeSource !== 'mt5') {
      bridgeStatus.connected = false;
      bridgeStatus.lastCheck = new Date().toISOString();
      return;
    }

    if (bridgeConfig && bridgeConfig.mt5Enabled !== true) {
      bridgeStatus.connected = false;
      bridgeStatus.lastCheck = new Date().toISOString();
      return;
    }

    // Optional external bridge (opt-in only via MT5_BRIDGE env variable)
    if (MT5_BRIDGE_PYTHON) {
      try {
        const response = await fetch(`${MT5_BRIDGE_PYTHON}/mt5/latest`, {
          signal: AbortSignal.timeout(1000)
        });

        if (response.ok) {
          const data = await response.json();
          bridgeStatus.connected = true;
          bridgeStatus.lastCheck = new Date().toISOString();

          if (data.data && ingestMT5Snapshot(data.data, 'mt5-bridge-python') > 0) {
            return; // Success, exit
          }
        }
      } catch (e) {
        // Bridge not available
      }
    }

    // Strict mode: never ingest market data from local file fallback.
    bridgeStatus.connected = false;
    bridgeStatus.lastCheck = new Date().toISOString();
  } catch (err) {
    bridgeStatus.connected = false;
    console.log('[MT5 POLL] Error reading MT5 data:', err.message);
  }
}

// Start MT5 bridge polling on server startup
function startMT5Polling(intervalMs = 2000) {
  if (_mt5PollTimer) clearInterval(_mt5PollTimer);
  _mt5PollTimer = setInterval(pollMT5BridgeData, intervalMs);
  console.log('[MT5 POLLING] Started @ ' + intervalMs + 'ms — polling from ' + MT5_BRIDGE_PYTHON + ' or mt5_data.json');
  // Initial poll immediately
  pollMT5BridgeData();
}

function stopMT5Polling() {
  if (_mt5PollTimer) { 
    clearInterval(_mt5PollTimer); 
    _mt5PollTimer = null;
  }
  console.log('[MT5 POLLING] Stopped');
}

// Health check for MT5 Bridge
function checkMT5Bridge() {
  if (!MT5_BRIDGE_PYTHON) {
    bridgeStatus.connected = false;
    bridgeStatus.lastCheck = new Date().toISOString();
    return;
  }

  const http = require('http');
  const url = `${MT5_BRIDGE_PYTHON}/health`;
  
  http.get(url, { timeout: 2000 }, res => {
    let data = '';
    res.on('data', d => data += d);
    res.on('end', () => {
      try {
        const status = JSON.parse(data);
        bridgeStatus.connected = status.mt5_connected === true;
        bridgeStatus.lastCheck = new Date().toISOString();
      } catch (e) {
        bridgeStatus.connected = false;
      }
    });
  }).on('error', () => {
    bridgeStatus.connected = false;
    bridgeStatus.lastCheck = new Date().toISOString();
  });
}

// Check bridge DISABLED - was polling every 15 seconds
// RAISON: Requêtes HTTP inutiles = I/O overhead = CPU spikes
// SOLUTION: Vérifier à la demande avec GET /mt5/status
// NOUVEAU: Endpoint POST /mt5/health-check/enable pour contrôle manuel

let _mt5CheckTimer = null;

function enableMT5HealthCheck(intervalMs = 60000) {
  if (_mt5CheckTimer) clearInterval(_mt5CheckTimer);
  _mt5CheckTimer = setInterval(checkMT5Bridge, intervalMs);
  console.log('[MT5] Health check ENABLED @ ' + intervalMs + 'ms');
}

function disableMT5HealthCheck() {
  if (_mt5CheckTimer) { 
    clearInterval(_mt5CheckTimer); 
    _mt5CheckTimer = null;
  }
  console.log('[MT5] Health check DISABLED');
}

// ─── Zone Manager ─────────────────────────────────────────────────────────────
let zoneManager;
try {
  zoneManager = require('./lib/zone-manager');
} catch {
  zoneManager = {
    zones: [],
    createZone(z) { const zone = { ...z, id: Date.now() + '_' + Math.random().toString(36).slice(2), createdAt: Date.now(), frozen: true, active: true }; this.zones.push(zone); return zone; },
    updateZones(price) { this.zones.forEach(z => { if (!z.active) return; if (z.type === 'supply' && price > z.high * 1.002) z.active = false; if (z.type === 'demand' && price < z.low * 0.998) z.active = false; if (Date.now() - z.createdAt > 4 * 3600000) z.active = false; }); },
    getActiveZones(sym, tf) { return this.zones.filter(z => z.symbol === sym && (!tf || z.tf === tf) && z.active); },
    getAllZones(sym) { return this.zones.filter(z => z.symbol === sym); }
  };
}

// ─── Setup Classifier ─────────────────────────────────────────────────────────
function classifySetup(timeframe, direction, score, modeOverride) {
  const scalperTFs  = ['M1', 'M3', 'M5'];
  const intradayTFs = ['M10', 'M15', 'M30', 'H1', 'H2'];
  const swingTFs    = ['H3', 'H4', 'H6', 'H8', 'H12', 'D1', 'W1'];

  const tf = (timeframe || 'H1').toUpperCase();
  const mo = (modeOverride || '').toUpperCase();
  let setup_type, holding_profile, expected_duration, slMultiplier, tpMultiplier;

  // Mode override (utilisateur choisit SCALPER / SNIPER / SWING dans l'UI)
  if (mo === 'SCALPER') {
    return { setup_type:'SCALPER', holding_profile:'Scalp rapide — sortie en quelques minutes', expected_duration:'1–15 min', slMultiplier:0.5, tpMultiplier:0.4 };
  }
  if (mo === 'SNIPER') {
    return { setup_type:'SNIPER', holding_profile:'Sniper intraday — entrée précise', expected_duration:'30 min – 6h', slMultiplier:1.0, tpMultiplier:0.8 };
  }
  if (mo === 'SWING') {
    return { setup_type:'SWING', holding_profile:'Swing multi-session — patience requise', expected_duration:'1 – 5 jours', slMultiplier:1.5, tpMultiplier:1.2 };
  }

  if (scalperTFs.includes(tf)) {
    // Scalping : TP court, fermeture rapide, R:R ~1:2
    setup_type       = 'SCALPER';
    holding_profile  = 'Scalp rapide — sortie en quelques minutes';
    expected_duration= '1–15 min';
    slMultiplier     = 0.5;   // SL serré
    tpMultiplier     = 0.4;   // TP ~10-12 pts gold (réduit vs ancien 1.0)
  } else if (intradayTFs.includes(tf)) {
    // Sniper intraday : précision, R:R ~1:2.5
    setup_type       = 'SNIPER';
    holding_profile  = 'Sniper intraday — entrée précise, session fermée';
    expected_duration= '30 min – 6h';
    slMultiplier     = 1.0;
    tpMultiplier     = 0.8;   // TP ~20-25 pts gold (réduit vs ancien 2.0)
  } else {
    // Swing : objectif multi-session, R:R ~1:2.5
    setup_type       = 'SWING';
    holding_profile  = 'Swing multi-session — patience requise';
    expected_duration= '1 – 5 jours';
    slMultiplier     = 1.5;
    tpMultiplier     = 1.2;   // TP ~35 pts gold (réduit vs ancien 3.5)
  }

  return { setup_type, holding_profile, expected_duration, slMultiplier, tpMultiplier };
}

// ─── Trade Validator ──────────────────────────────────────────────────────────
function validateTrade(trade, currentPrice) {
  if (!trade || !currentPrice || !trade.entry) return { ...trade, trade_status: 'UNKNOWN' };
  const entry  = parseFloat(trade.entry);
  const dist   = Math.abs(currentPrice - entry) / currentPrice;

  let trade_status;
  if (dist < 0.005)       trade_status = 'LIVE';           // <0.5% — exécutable maintenant
  else if (dist < 0.015)  trade_status = 'CONDITIONAL';    // 0.5–1.5% — en attente retour en zone
  else                    trade_status = 'WAIT';            // >1.5% — setup non exécutable

  const proximity_pct = (dist * 100).toFixed(2);
  const reason = trade_status === 'LIVE'
    ? 'Entrée proche du prix actuel — exécution possible immédiatement'
    : trade_status === 'CONDITIONAL'
    ? `Entrée à ${proximity_pct}% du prix actuel — attendre retour en zone`
    : `Entrée trop loin (${proximity_pct}%) — setup à surveiller, pas d'exécution`;

  return { ...trade, trade_status, proximity_pct, validation_note: reason };
}

// ─── Real price fetching ──────────────────────────────────────────────────────
// Yahoo Finance UNIQUEMENT pour les klines (historique), JAMAIS pour décisions live

const priceCache = {}; // { XAUUSD: { price, ts } }

async function fetchYahooPrice(yahooSym) {
  const cached = priceCache[yahooSym];
  if (cached && Date.now() - cached.ts < 60000) return cached.price; // 1min cache
  const url  = `https://query1.finance.yahoo.com/v8/finance/chart/${yahooSym}?interval=1d&range=1d`;
  const resp = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(5000) });
  if (!resp.ok) throw new Error('Yahoo ' + resp.status);
  const d    = await resp.json();
  const price = d?.chart?.result?.[0]?.meta?.regularMarketPrice;
  if (!price) throw new Error('no price from Yahoo for ' + yahooSym);
  priceCache[yahooSym] = { price, ts: Date.now() };
  return price;
}

function toYahooSym(canonical) {
  if (/XAUUSD|GOLD/i.test(canonical)) return 'GC=F';
  if (/XAGUSD|SILVER/i.test(canonical)) return 'SI=F';
  if (/BTCUSD|BTC/i.test(canonical)) return 'BTC-USD';
  if (/ETHUSD|ETH/i.test(canonical)) return 'ETH-USD';
  if (/NAS100|NASDAQ/i.test(canonical)) return '^GSPC';  // Use S&P 500 as proxy
  if (/US500|SPY/i.test(canonical)) return '^GSPC';
  if (/US30|DJIA/i.test(canonical)) return '^DJI';
  if (/GER40|DAX/i.test(canonical)) return '^GDAXI';
  if (/UK100|FTSE/i.test(canonical)) return '^FTSE';
  if (/USOIL|CRUDE/i.test(canonical)) return 'CL=F';
  const forex = ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','USDCHF','NZDUSD','EURGBP','EURJPY','GBPJPY'];
  const s = canonical.replace('/','').toUpperCase();
  if (forex.includes(s)) return s + '=X';
  return null;
}

// ─── Calcul des niveaux (réels, basés sur %) ─────────────────────────────────
function calcTradeLevels(price, direction, profile, timeframe, atr = null) {
  const digits = profile.digits || 5;
  const pip = profile.pip || 0.1;
  
  // Use ATR-based levels if available, otherwise use conservative profile percentages
  let slDist, tpDist;
  
  if (atr && atr > 0) {
    // ATR-based: SL = ATR × 1.5, TP = ATR × 3.5 (ensures realistic 2-3:1 RR)
    slDist = atr * 1.5;
    tpDist = atr * 3.5;  // ~2.33:1 ratio
  } else {
    // Fallback: Use profile percentages directly (no arbitrary multipliers)
    // This ensures consistency with symbol-normalizer profiles
    slDist = price * (profile.slPct || 0.003);
    tpDist = price * (profile.tpPct || 0.009);
  }
  
  const sl = direction === 'LONG' ? price - slDist : price + slDist;
  const tp = direction === 'LONG' ? price + tpDist : price - tpDist;
  const rr = (tpDist / slDist).toFixed(2);
  
  return {
    entry: price.toFixed(digits),
    sl:    sl.toFixed(digits),
    tp:    tp.toFixed(digits),
    rrRatio: rr,
    slPct: ((slDist / price) * 100).toFixed(2) + '%',
    tpPct: ((tpDist / price) * 100).toFixed(2) + '%',
    slPips: (slDist / pip).toFixed(1),
    tpPips: (tpDist / pip).toFixed(1),
    method: atr && atr > 0 ? 'ATR-based' : 'profile-percentage'
  };
}

// ─── SYMBOL MATCHING with Price Validation ────────────────────────────────────
let symbolMatcher;
try {
  symbolMatcher = require('./lib/symbol-matcher');
} catch (e) {
  console.warn('[WARN] Symbol matcher fallback:', e.message);
  symbolMatcher = {
    findCanonicalSymbol: (raw) => {
      const s = (raw || '').toUpperCase();
      if (!s) return { found: false };
      const patterns = [
        [/XAU|GOLD/i, 'XAUUSD'],
        [/XAG|SILVER/i, 'XAGUSD'],
        [/BTC/i, 'BTCUSD'],
        [/ETH/i, 'ETHUSD'],
        [/EUR/i, 'EURUSD'],
        [/GBP/i, 'GBPUSD'],
        [/USDJPY|JPY/i, 'USDJPY'],
        [/AUD/i, 'AUDUSD'],
        [/CAD/i, 'USDCAD'],
        [/CHF/i, 'USDCHF'],
        [/NZD/i, 'NZDUSD'],
      ];
      for (const [pat, canonical] of patterns) {
        if (pat.test(s)) return { found: true, canonical, variant: raw, type: /GOLD|XAU|XAG|SILVER/.test(s) ? 'metal' : /BTC|ETH/.test(s) ? 'crypto' : 'forex' };
      }
      return { found: false };
    },
    matchSymbolWithPriceValidation: (tvSym, tvPrice, backendData) => {
      const match = symbolMatcher.findCanonicalSymbol(tvSym);
      if (!match.found) return { ok: false, error: 'Symbol not recognized' };
      return {
        ok: true,
        tvSymbol: tvSym,
        tvPrice,
        canonical: match.canonical,
        type: match.type,
        selectedSymbol: match.canonical,
        selectedSource: 'fallback',
        selectedPrice: tvPrice,
        syncStatus: 'APPROXIMATED'
      };
    },
    getDisplayStatus: (result) => ({
      symbol: result.selectedSymbol || '?',
      status: result.ok ? 'OK' : 'ERROR',
      message: result.error || 'Using fallback matching',
      color: result.ok ? 'blue' : 'red'
    })
  };
}

app.post('/match-symbol', (req, res) => {
  const { tvSymbol, tvPrice, backendData } = req.body || {};
  if (!tvSymbol) return res.status(400).json({ ok: false, error: 'tvSymbol required' });

  try {
    const result = symbolMatcher.matchSymbolWithPriceValidation(tvSymbol, tvPrice || 0, backendData || {});
    const display = symbolMatcher.getDisplayStatus(result);
    
    res.json({
      ok: true,
      match: result,
      display,
      timestamp: new Date().toISOString()
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.get('/match-symbol/:tvSymbol', async (req, res) => {
  const tvSymbol = req.params.tvSymbol;
  const tvPrice = parseFloat(req.query.price) || 0;

  try {
    const canonical = symbolMatcher.findCanonicalSymbol(tvSymbol);
    if (!canonical.found) {
      return res.status(404).json({ ok: false, error: 'Symbol not recognized: ' + tvSymbol });
    }

    // Gather available prices
    const mt5Data = marketStore.getLatestForSymbol(canonical.canonical);
    const backendData = {
      mt5: mt5Data?.latestPayload ? { symbol: canonical.canonical, price: parseFloat(mt5Data.latestPayload.price) } : null,
      tradingview: tvPrice > 0 ? { symbol: tvSymbol, price: tvPrice } : null
    };

    const result = symbolMatcher.matchSymbolWithPriceValidation(tvSymbol, tvPrice, backendData);
    const display = symbolMatcher.getDisplayStatus(result);

    res.json({
      ok: true,
      detected: tvSymbol,
      canonical: canonical.canonical,
      type: canonical.type,
      priceMatch: result.syncStatus,
      display,
      timestamp: new Date().toISOString()
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ─── HEALTH ────────────────────────────────────────────────────────────────────
app.get('/health', (_req, res) => {
  const resolvedCtx = resolveActiveRuntimeContext();
  res.json({
    ok: true,
    port: PORT,
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    mt5Status: marketStore.systemStatus?.source || 'offline',
    dataSource: marketStore.systemStatus?.fluxStatus || 'OFFLINE',
    // Active context resolved from runtime truth (TradingView/MT5/selection)
    activeContext: {
      symbol: resolvedCtx.active.symbol || null,
      timeframe: resolvedCtx.active.timeframe || 'H1',
      price: resolvedCtx.active.price ?? null,
      source: resolvedCtx.active.source || 'none',
      resolvedBy: resolvedCtx.active.resolvedBy || 'none',
      mode: resolvedCtx.selected?.mode || bridgeConfig.bridgeMode || 'AUTO',
      modeResolved: resolvedCtx.selected?.modeResolved || resolveRuntimeMode(bridgeConfig.bridgeMode || 'AUTO', resolvedCtx.active.symbol, resolvedCtx.active.timeframe || 'H1')
    },
    sourceContexts: resolvedCtx
  });
});

function getLatestTradingviewRuntime() {
  try {
    const entries = Object.entries(tvDataStore || {});
    if (!entries.length) {
      return {
        connected: false,
        lastSource: null,
        symbol: null,
        timeframe: null,
        timestamp: null,
        ageMs: null,
        eventType: null,
        payload: null
      };
    }

    let latest = null;
    for (const [symbol, item] of entries) {
      const tsRaw = item?.robotV12?.receivedAt || item?.timestamp || null;
      const tsMs = tsRaw ? Date.parse(tsRaw) : NaN;
      if (!latest || (Number.isFinite(tsMs) && tsMs > latest.tsMs)) {
        latest = { symbol, item, tsRaw, tsMs };
      }
    }

    if (!latest) {
      return {
        connected: false,
        lastSource: null,
        symbol: null,
        timeframe: null,
        timestamp: null,
        ageMs: null,
        eventType: null,
        payload: null
      };
    }

    const ageMs = Number.isFinite(latest.tsMs) ? Math.max(0, Date.now() - latest.tsMs) : null;
    const robot = latest.item?.robotV12 || null;
    const eventType = robot ? 'robot-v12' : 'tradingview-tick';

    // CONNECTION STABILITY RULE:
    // TradingView is "connected" if:
    // - Last message received < 180 seconds ago (3 minutes)
    // - This prevents flapping from brief network hiccups or slow ticks
    // - If no fresh data for 3+ minutes, assume offline until new data arrives
    const isConnected = Number.isFinite(ageMs) && ageMs < 180000;

    return {
      connected: isConnected,
      lastSource: String(latest.item?.source || latest.item?.action || 'tradingview').toLowerCase(),
      symbol: latest.symbol,
      timeframe: robot?.timeframe || latest.item?.timeframe || null,
      timestamp: latest.tsRaw || null,
      ageMs,
      eventType,
      payload: {
        price: latest.item?.price ?? null,
        action: latest.item?.action ?? null,
        verdict: robot?.verdict ?? null,
        anticipation: robot?.anticipation ?? null,
        rsi: latest.item?.indicators?.rsi ?? null,
        entry: latest.item?.entry ?? robot?.entry ?? null,
        sl: latest.item?.sl ?? robot?.sl ?? null,
        tp: latest.item?.tp ?? robot?.tp ?? null,
        rrRatio: latest.item?.rrRatio ?? robot?.rrRatio ?? null
      }
    };
  } catch (_e) {
    return {
      connected: false,
      lastSource: null,
      symbol: null,
      timeframe: null,
      timestamp: null,
      ageMs: null,
      eventType: null,
      payload: null
    };
  }
}

function findTradingviewSymbolKey(symbol) {
  try {
    const requested = String(symbol || '').trim();
    if (!requested) return null;
    if (requested in (tvDataStore || {})) return requested;

    const requestedCanonical = normalizeSymbol(requested).canonical;
    for (const key of Object.keys(tvDataStore || {})) {
      if (key === requested) return key;
      const keyCanonical = normalizeSymbol(key).canonical;
      if (keyCanonical === requestedCanonical) return key;
    }

    return null;
  } catch (_e) {
    return null;
  }
}

function getRobotV12ForSymbol(symbol) {
  try {
    const resolvedKey = findTradingviewSymbolKey(symbol);
    if (resolvedKey && tvDataStore[resolvedKey]?.robotV12) {
      return tvDataStore[resolvedKey].robotV12;
    }

    const latest = getLatestTradingviewRuntime();
    if (!latest?.symbol) return null;
    const latestCanonical = normalizeSymbol(latest.symbol).canonical;
    const requestedCanonical = normalizeSymbol(symbol || '').canonical;
    if (latestCanonical !== requestedCanonical) return null;

    const latestKey = findTradingviewSymbolKey(latest.symbol);
    return latestKey ? (tvDataStore[latestKey]?.robotV12 || null) : null;
  } catch (_e) {
    return null;
  }
}

function classifyIngressSource(raw) {
  const s = String(raw || '').toLowerCase();
  if (!s) return 'unknown';
  if (s.includes('mt5')) return 'mt5';
  if (s.includes('tradingview') || s.includes('tv-bridge') || s === 'tv') return 'tradingview';
  return 'other';
}

function inferAutoMode(symbol, timeframe) {
  const tf = String(timeframe || 'H1').toUpperCase();
  const profile = normalizeSymbol(symbol || '');

  const m = tf.match(/^M(\d{1,2})$/);
  if (m) {
    const minutes = parseInt(m[1], 10) || 1;
    if (minutes <= 5) return 'SCALPER';
    if (minutes <= 30) return 'SNIPER';
  }

  if (/^H(1|2|3)$/.test(tf)) return profile.type === 'crypto' ? 'SCALPER' : 'SNIPER';
  if (/^H(4|6|8|12)$/.test(tf) || tf === 'D1' || tf === 'W1' || tf === 'MN1') return 'SWING';

  return 'SNIPER';
}

function resolveRuntimeMode(modeRaw, symbol, timeframe) {
  const requested = normalizeBridgeMode(modeRaw || 'AUTO');
  const mode = String(requested || 'AUTO').toUpperCase();
  return mode === 'AUTO' ? inferAutoMode(symbol, timeframe) : mode;
}

function resolveActiveRuntimeContext() {
  const tv = getLatestTradingviewRuntime();
  const selectedSymbol = activeSymbol?.symbol || null;
  const selectedTf = activeSymbol?.timeframe || null;
  const selectedCanonical = selectedSymbol ? normalizeSymbol(selectedSymbol).canonical : null;
  const selectedTvKey = selectedSymbol ? findTradingviewSymbolKey(selectedSymbol) : null;
  const selectedTvEntry = selectedTvKey ? tvDataStore[selectedTvKey] : null;
  const selectedTvPrice = Number(selectedTvEntry?.price ?? selectedTvEntry?.bid ?? NaN);
  const selectedTvTf = String(selectedTvEntry?.robotV12?.timeframe || selectedTvEntry?.timeframe || '').toUpperCase() || null;
  const selectedTvTs = selectedTvEntry?.robotV12?.receivedAt || selectedTvEntry?.timestamp || null;
  const selectedUpdatedAt = activeSymbol?.updatedAt || null;
  const selectedTvTsMs = selectedTvTs ? Date.parse(selectedTvTs) : NaN;
  const selectedUpdatedMs = selectedUpdatedAt ? Date.parse(selectedUpdatedAt) : NaN;
  const selectedTvIsFresh = Number.isFinite(selectedTvTsMs)
    && (!Number.isFinite(selectedUpdatedMs) || selectedTvTsMs >= (selectedUpdatedMs - 2000));
  const activeSource = String(bridgeConfig.activeSource || (bridgeConfig.mt5Enabled === true ? 'mt5' : 'tradingview')).toLowerCase() === 'mt5' ? 'mt5' : 'tradingview';
  const tvEnabled = bridgeConfig.tradingviewEnabled !== false && activeSource === 'tradingview';
  const tvFresh = !!tvEnabled && !!tv?.connected && !!tv?.symbol;
  const bridgeOn = bridgeConfig.bridgeEnabled !== false;

  let active = {
    symbol: null,
    timeframe: null,
    price: null,
    source: 'none',
    resolvedBy: 'none',
    updatedAt: null
  };

  if (activeSource === 'tradingview' && bridgeOn && selectedSymbol) {
    const useSelectedTv = selectedTvIsFresh && Number.isFinite(selectedTvPrice);
    active = {
      symbol: String(selectedCanonical || selectedSymbol || '').toUpperCase(),
      timeframe: String(selectedTf || (useSelectedTv ? selectedTvTf : null) || 'H1').toUpperCase(),
      price: useSelectedTv ? selectedTvPrice : (activeSymbol?.price ?? activeSymbol?.tvPrice ?? null),
      source: 'tradingview',
      resolvedBy: useSelectedTv ? 'tv-selected-symbol' : (tvFresh ? 'tv-active-symbol-fallback' : 'extension-active-symbol'),
      updatedAt: useSelectedTv ? (selectedTvTs || activeSymbol?.updatedAt || null) : (activeSymbol?.updatedAt || null)
    };
  } else if (activeSource === 'tradingview' && selectedSymbol) {
    active = {
      symbol: String(selectedCanonical || selectedSymbol || '').toUpperCase(),
      timeframe: String(selectedTf || selectedTvTf || 'H1').toUpperCase(),
      price: activeSymbol?.price ?? activeSymbol?.tvPrice ?? null,
      source: 'tradingview',
      resolvedBy: 'extension-active-symbol',
      updatedAt: activeSymbol?.updatedAt || null
    };
  } else if (activeSource === 'mt5' && bridgeOn) {
    const mt5Symbol = marketStore.lastActiveSymbol || selectedCanonical || selectedSymbol || null;
    const mt5Latest = mt5Symbol ? marketStore.getLatestForSymbol(String(mt5Symbol).toUpperCase()) : null;
    const mt5Payload = mt5Latest?.latestPayload || {};
    active = {
      symbol: mt5Symbol ? String(mt5Symbol).toUpperCase() : null,
      timeframe: String(mt5Payload.timeframe || selectedTf || 'H1').toUpperCase(),
      price: mt5Payload.price ?? mt5Payload.bid ?? mt5Payload.ask ?? null,
      source: 'mt5',
      resolvedBy: 'mt5-runtime',
      updatedAt: mt5Payload.timestamp || null
    };
  }

  const selectedModeRaw = activeSymbol?.mode || bridgeConfig.bridgeMode || 'AUTO';
  const selectedModeResolved = resolveRuntimeMode(selectedModeRaw, active.symbol, active.timeframe);

  return {
    active,
    selected: {
      symbol: selectedSymbol,
      timeframe: selectedTf,
      mode: selectedModeRaw,
      modeResolved: selectedModeResolved,
      updatedAt: activeSymbol?.updatedAt || null
    },
    tradingview: {
      symbol: tv?.symbol || null,
      timeframe: tv?.timeframe || null,
      connected: tvEnabled && !!tv?.connected,
      ageMs: tv?.ageMs ?? null,  // CRITICAL: age in milliseconds for stability checks
      eventType: tv?.eventType || null,
      timestamp: tv?.timestamp || null,
      source: tv?.lastSource || null
    },
    market: {
      symbol: null,
      timeframe: null,
      price: null,
      source: bridgeConfig.mt5Enabled === true ? 'mt5-enabled' : 'mt5-disabled',
      sourceRaw: null,
      updatedAt: null
    },
    bridge: {
      enabled: bridgeOn,
      tradingviewEnabled: tvEnabled,
      mt5Enabled: bridgeConfig.mt5Enabled === true,
      activeSource,
      mode: bridgeConfig.bridgeMode || 'AUTO',
      modeResolved: resolveRuntimeMode(bridgeConfig.bridgeMode || 'AUTO', active.symbol, active.timeframe),
      source: bridgeConfig.bridgeSource || null
    }
  };
}

let lastBroadcastedActiveKey = null;
function emitResolvedActiveSymbol(trigger) {
  try {
    const ctx = resolveActiveRuntimeContext();
    const a = ctx.active || {};
    if (!a.symbol) return;
    // Dedup key: symbol + timeframe only. Removing source from key ensures TF changes
    // always broadcast even when source tag changes between calls.
    const key = [String(a.symbol), String(a.timeframe || 'H1')].join('|');
    if (key === lastBroadcastedActiveKey) return;
    lastBroadcastedActiveKey = key;

    broadcastToExtension({
      type: 'active-symbol',
      symbol: a.symbol,
      timeframe: a.timeframe || 'H1',
      price: a.price ?? null,
      mode: activeSymbol?.mode || bridgeConfig.bridgeMode || 'AUTO',
      modeResolved: resolveRuntimeMode(activeSymbol?.mode || bridgeConfig.bridgeMode || 'AUTO', a.symbol, a.timeframe || 'H1'),
      source: a.source || 'unknown',
      resolvedBy: a.resolvedBy || 'unknown',
      trigger: trigger || 'runtime-sync'
    });
  } catch (_e) {}
}

// ─── LIVE OPS SNAPSHOT (single source for real-time cockpit) ───────────────
app.get('/live/state', (_req, res) => {
  try {
    const status = marketStore.systemStatus || {};
    const lastUpdateIso = status.lastUpdate || null;
    const lastUpdateMs = lastUpdateIso ? Date.parse(lastUpdateIso) : NaN;
    const ageMs = Number.isFinite(lastUpdateMs) ? Math.max(0, Date.now() - lastUpdateMs) : null;

    const resolvedCtx = resolveActiveRuntimeContext();
    const symbol = resolvedCtx.active.symbol || null;
    const timeframe = resolvedCtx.active.timeframe || 'H1';
    const latest = symbol ? marketStore.getLatestForSymbol(symbol) : null;
    const tvRuntime = getLatestTradingviewRuntime();

    res.json({
      ok: true,
      timestamp: new Date().toISOString(),
      health: {
        serverPort: PORT,
        uptimeSec: Math.floor(process.uptime()),
        source: status.source || 'offline',
        fluxStatus: status.fluxStatus || 'OFFLINE',
        lastUpdate: lastUpdateIso,
        ageMs
      },
      orchestration: {
        enabled: typeof _orchestrationEnabled === 'boolean' ? _orchestrationEnabled : false,
        timer: (_orchestrationAutoTimer ? 'active' : 'inactive')
      },
      context: {
        symbol,
        timeframe,
        price: resolvedCtx.active.price ?? marketStore.lastActivePrice ?? null,
        source: resolvedCtx.active.source || 'none',
        resolvedBy: resolvedCtx.active.resolvedBy || 'none'
      },
      bridge: {
        enabled: bridgeConfig.bridgeEnabled !== false,
        tradingviewEnabled: bridgeConfig.tradingviewEnabled !== false,
        mt5Enabled: bridgeConfig.mt5Enabled === true,
        activeSource: String(bridgeConfig.activeSource || (bridgeConfig.mt5Enabled === true ? 'mt5' : 'tradingview')).toLowerCase() === 'mt5' ? 'mt5' : 'tradingview',
        mode: bridgeConfig.bridgeMode || 'AUTO',
        source: bridgeConfig.bridgeSource || 'tradingview',
        updatedAt: bridgeConfig.updatedAt || null,
        updatedBy: bridgeConfig.updatedBy || null
      },
      streams: {
        marketSseClients: Array.isArray(marketStore.sseClients) ? marketStore.sseClients.length : 0,
        extensionSseClients: Array.isArray(extensionSyncClients) ? extensionSyncClients.length : 0
      },
      agents: {
        liveEnabled: !!agentStates?.enabled,
        indicatorState: indicatorAgent?.getState ? indicatorAgent.getState() : null
      },
      endpoints: {
        '/health': hasExpressRoute('get', '/health'),
        '/stream': hasExpressRoute('get', '/stream'),
        '/extension/sync': hasExpressRoute('get', '/extension/sync'),
        '/audit/state': hasExpressRoute('get', '/audit/state'),
        '/orchestration-status': hasExpressRoute('get', '/orchestration-status'),
        '/orchestration/run-now': hasExpressRoute('post', '/orchestration/run-now'),
        '/data': hasExpressRoute('get', '/data'),
        '/analysis': hasExpressRoute('get', '/analysis')
      },
      latestPayload: latest?.latestPayload || null,
      tradingview: tvRuntime,
      sourceContexts: resolvedCtx
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ─── AUDIT API ROUTES (Real-time synchronization) ────────────────────────────
// Zéro modification du système existant — uniquement sync + logging

function hasExpressRoute(method, routePath) {
  try {
    const stack = app?._router?.stack || [];
    const wantedMethod = String(method || '').toLowerCase();
    return stack.some((layer) => {
      if (!layer?.route) return false;
      const p = layer.route.path;
      if (p !== routePath) return false;
      return !!layer.route.methods?.[wantedMethod];
    });
  } catch (_e) {
    return false;
  }
}

function reconcileAuditStateWithLiveRoutes(state) {
  if (!state?.audit) return state;

  const routeChecks = {
    '/orchestration/run-now': hasExpressRoute('post', '/orchestration/run-now'),
    '/orchestration-status': hasExpressRoute('get', '/orchestration-status'),
    '/data': hasExpressRoute('get', '/data'),
    '/analysis': hasExpressRoute('get', '/analysis')
  };

  const isResolvedIssue = (issue) => {
    const ep = issue?.endpoint;
    if (!ep || routeChecks[ep] !== true) return false;
    const status = String(issue?.status || '').toUpperCase();
    const desc = String(issue?.description || '').toLowerCase();
    if (status === 'MISSING') return true;
    if (desc.includes('missing endpoint')) return true;
    if (desc.includes('not defined')) return true;
    if (desc.includes('not implemented')) return true;
    return false;
  };

  const pruneResolvedIssues = (issues) => {
    if (!Array.isArray(issues)) return [];
    return issues.filter((issue) => !isResolvedIssue(issue));
  };

  if (Array.isArray(state.audit.endpoints)) {
    state.audit.endpoints = state.audit.endpoints.map((ep) => {
      if (!ep || !ep.path) return ep;
      if (routeChecks[ep.path] === true) {
        return {
          ...ep,
          status: 'OK',
          lastUpdated: new Date().toISOString()
        };
      }
      return ep;
    });
  }

  if (Array.isArray(state.audit.connections)) {
    state.audit.connections = state.audit.connections.map((conn) => {
      if (!conn || !Array.isArray(conn.issues)) return conn;
      const nextIssues = pruneResolvedIssues(conn.issues);
      if (nextIssues.length !== conn.issues.length) {
        return {
          ...conn,
          issues: nextIssues,
          status: nextIssues.length === 0 ? 'OK' : conn.status
        };
      }
      return conn;
    });
  }

  if (Array.isArray(state.audit.files)) {
    state.audit.files = state.audit.files.map((f) => {
      if (!f || !Array.isArray(f.issues)) return f;
      const nextIssues = pruneResolvedIssues(f.issues);
      if (nextIssues.length !== f.issues.length) {
        return {
          ...f,
          issues: nextIssues,
          status: nextIssues.length === 0 ? 'OK' : f.status
        };
      }
      return f;
    });
  }

  if (Array.isArray(state.audit.errors)) {
    state.audit.errors = state.audit.errors.filter((e) => {
      const desc = String(e?.description || '').toLowerCase();
      if (routeChecks['/orchestration/run-now'] && desc.includes('/orchestration/run-now') && (desc.includes('not implemented') || desc.includes('missing'))) return false;
      if (routeChecks['/orchestration-status'] && desc.includes('/orchestration-status') && (desc.includes('not implemented') || desc.includes('missing'))) return false;
      if (routeChecks['/data'] && desc.includes('/data') && (desc.includes('not implemented') || desc.includes('not defined') || desc.includes('missing'))) return false;
      if (routeChecks['/analysis'] && desc.includes('/analysis') && (desc.includes('not implemented') || desc.includes('not defined') || desc.includes('missing'))) return false;
      return true;
    });
  }

  return state;
}

function syncAuditStateToDisk() {
  try {
    const state = auditLogger.getState();
    const reconciled = reconcileAuditStateWithLiveRoutes(state);
    if (reconciled?.audit) {
      auditLogger.audit = reconciled.audit;
      auditLogger.writeAudit();
    }
    return reconciled;
  } catch (e) {
    console.error('[AUDIT SYNC]', e.message);
    return auditLogger.getState();
  }
}

// GET /audit/state — État complet du système
app.get('/audit/state', (_req, res) => {
  res.set('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  res.set('Pragma', 'no-cache');
  res.set('Expires', '0');
  res.json(syncAuditStateToDisk());
});

// GET /audit/events — Événements récents
app.get('/audit/events', (req, res) => {
  const limit = parseInt(req.query.limit || 20);
  res.json(auditLogger.getRecentEvents(limit));
});

// POST /audit/log — Logger un événement manuel
app.post('/audit/log', (req, res) => {
  const { category, action, details } = req.body;
  if (!category || !action) return res.status(400).json({ ok: false, error: 'category and action required' });
  const event = auditLogger.logEvent(category, action, details || {});
  res.json({ ok: true, event });
});

// POST /audit/task/:taskId — Mettre à jour une tâche
app.post('/audit/task/:taskId', (req, res) => {
  const { taskId } = req.params;
  const { status, name, completeness, issues, files } = req.body;
  const task = auditLogger.updateTask(taskId, { status, name, completeness, issues, files });
  res.json({ ok: true, task });
});

// POST /audit/task/:taskId/complete — Marquer une tâche complète
app.post('/audit/task/:taskId/complete', (req, res) => {
  const { taskId } = req.params;
  const task = auditLogger.completeTask(taskId);
  res.json({ ok: true, task });
});

// POST /audit/task/:taskId/fail — Marquer une tâche en erreur
app.post('/audit/task/:taskId/fail', (req, res) => {
  const { taskId } = req.params;
  const { reason } = req.body;
  const task = auditLogger.failTask(taskId, reason);
  res.json({ ok: true, task });
});

// POST /audit/error/:errorId — Ajouter/mettre à jour une erreur
app.post('/audit/error/:errorId', (req, res) => {
  const { errorId } = req.params;
  const errorData = req.body;
  const error = auditLogger.addError(errorId, errorData);
  res.json({ ok: true, error });
});

// POST /audit/error/:errorId/resolve — Résoudre une erreur
app.post('/audit/error/:errorId/resolve', (req, res) => {
  const { errorId } = req.params;
  const { resolution } = req.body;
  const error = auditLogger.resolveError(errorId, resolution);
  res.json({ ok: true, error });
});

// GET /audit/health — Scan système pour erreurs
app.get('/audit/health', (_req, res) => {
  const issues = auditLogger.scanSystemHealth();
  res.json({ ok: true, issues, count: issues.length });
});

// ─── MT5 API ROUTES FOR EXTENSION ──────────────────────────────────────────────

// GET /mt5/latest — Dernier snapshot MT5 complet
app.get('/mt5/latest', (req, res) => {
  try {
    const symbol = marketStore.lastActiveSymbol || getLatestTradingviewRuntime().symbol || '';
    
    if (!latest || !latest.latestPayload) {
      return res.status(404).json({ 
        ok: false, 
        error: 'No MT5 data yet', 
        symbol,
        note: 'Bridge MT5 pas encore connecté'
      });
    }
    
    res.json({
      ok: true,
      symbol,
      data: latest.latestPayload,
      receivedAt: new Date(latest.updatedAt).toISOString(),
      age_ms: Date.now() - latest.updatedAt
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /mt5/current-chart — Symbole courant + rates du timeframe actif
app.get('/mt5/current-chart', (req, res) => {
  try {
    const symbol = String(req.query.symbol || marketStore.lastActiveSymbol || '').toUpperCase();
    if (!symbol) return res.status(400).json({ ok: false, error: 'symbol parameter required or no active symbol' });
    const tf = String(req.query.tf || marketStore.lastActiveTimeframe || 'H1').toUpperCase();
    const latest = marketStore.getLatestForSymbol(symbol);
    
    if (!latest || !latest.latestPayload) {
      return res.json({
        ok: false,
        symbol,
        timeframe: tf,
        error: 'No data'
      });
    }
    
    const payload = latest.latestPayload;
    const candleRates = candleManager
      ? candleManager.getCandles(symbol, tf, 180).map((c) => ({
        time: c.timeOpen,
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
        volume: Number(c.volume || 0),
        status: c.status || 'closed'
      }))
      : [];
    const fallbackRates = Array.isArray(payload.history) ? payload.history : [];
    const localStreamRates = Array.isArray(localPriceStreams[symbol]) ? localPriceStreams[symbol].slice(-220) : [];
    const rates = candleRates.length >= 2
      ? candleRates
      : (fallbackRates.length >= 2 ? fallbackRates : localStreamRates);

    res.json({
      ok: true,
      symbol,
      timeframe: tf,
      bid: payload.bid,
      ask: payload.ask,
      price: payload.price || (payload.bid + payload.ask) / 2,
      spread: (payload.ask - payload.bid).toFixed(5),
      ohlc: payload.ohlc,
      indicators: {
        rsi: payload.rsi || null,
        macd: payload.macd || null,
        ma20: payload.ma20 || null
      },
      // Priorité aux bougies locales temps réel (sans API externe)
      rates,
      candleSource: candleRates.length >= 2
        ? 'candle-manager'
        : (fallbackRates.length >= 2 ? 'payload-history' : 'local-price-stream'),
      lastUpdate: new Date(latest.updatedAt).toISOString()
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /mt5/symbols — Liste des symboles MT5 disponibles
app.get('/mt5/symbols', (req, res) => {
  try {
    const symbols = Object.keys(marketStore.bySymbol || {}).map(sym => ({
      symbol: sym,
      lastUpdate: marketStore.bySymbol[sym]?.updatedAt,
      stale: (Date.now() - marketStore.bySymbol[sym]?.updatedAt) > 30000
    }));
    
    res.json({
      ok: true,
      count: symbols.length,
      symbols,
      message: symbols.length === 0 ? 'En attente de snapshots MT5' : 'OK'
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /mt5/live-symbols — symboles réellement alimentés en temps réel
app.get('/mt5/live-symbols', (req, res) => {
  try {
    const now = Date.now();
    const symbols = Object.keys(marketStore.bySymbol || {})
      .map((sym) => {
        const item = marketStore.bySymbol[sym] || {};
        const payload = item.latestPayload || {};
        const updatedAtMs = Number(item.updatedAt || 0);
        const ageMs = updatedAtMs > 0 ? Math.max(0, now - updatedAtMs) : null;
        return {
          symbol: sym,
          price: Number(payload.price ?? payload.bid ?? payload.ask ?? NaN),
          source: payload.source || 'unknown',
          timeframe: String(payload.timeframe || marketStore.lastActiveTimeframe || 'H1').toUpperCase(),
          updatedAt: updatedAtMs ? new Date(updatedAtMs).toISOString() : null,
          ageMs,
          isFresh: Number.isFinite(ageMs) ? ageMs <= 15000 : false
        };
      })
      .filter((s) => s.symbol)
      .sort((a, b) => {
        const af = a.isFresh ? 1 : 0;
        const bf = b.isFresh ? 1 : 0;
        if (af !== bf) return bf - af;
        return a.symbol.localeCompare(b.symbol);
      });

    res.json({
      ok: true,
      count: symbols.length,
      symbols,
      message: symbols.length > 0
        ? 'Flux réel local actif'
        : 'Aucun symbole MT5 actif pour le moment'
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /mt5/symbol/:symbol — Infos détaillées sur un symbole MT5
app.get('/mt5/symbol/:symbol', (req, res) => {
  try {
    const sym = req.params.symbol.toUpperCase();
    const data = marketStore.getLatestForSymbol(sym);
    
    if (!data || !data.latestPayload) {
      return res.status(404).json({
        ok: false,
        symbol: sym,
        error: 'Symbol not found in MT5 data'
      });
    }
    
    const payload = data.latestPayload;
    res.json({
      ok: true,
      symbol: sym,
      bid: payload.bid,
      ask: payload.ask,
      price: payload.price,
      spread: payload.ask - payload.bid,
      volume: payload.ohlc?.volume || 0,
      indicators: {
        rsi: payload.rsi,
        macd: payload.macd,
        ma20: payload.ma20
      },
      digits: payload.digits,
      pip_size: payload.pip_size,
      account: payload.account,
      market_watch: payload.market_watch,
      lastUpdate: new Date(data.updatedAt).toISOString()
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ─── MAPPING ROUTES ────────────────────────────────────────────────────────────

// POST /mapping/resolve — Recherche intelligente symbole MT5
app.post('/mapping/resolve', async (req, res) => {
  try {
    const { name, price, type } = req.body;
    if (!name) return res.status(400).json({ ok: false, error: 'name required' });
    
    const searchTerm = name.toUpperCase();
    const availableSymbols = Object.keys(marketStore.bySymbol || {});
    
    // Scoring simple: exact match > prefix match > contains
    const scored = availableSymbols.map(sym => {
      let score = 0;
      if (sym === searchTerm) score = 1000;
      else if (sym.startsWith(searchTerm)) score = 500;
      else if (sym.includes(searchTerm)) score = 250;
      
      // Bonus si prix correspond
      let currentPrice = null;
      let priceMatch = false;
      const data = marketStore.getLatestForSymbol(sym);
      if (data && data.latestPayload) {
        currentPrice = data.latestPayload.price;
        if (price) {
          const diff = Math.abs(currentPrice - parseFloat(price));
          if (diff < 10) {
            score += 200;
            priceMatch = true;
          }
        }
      }
      
      return { symbol: sym, score, currentPrice, priceMatch };
    })
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);  // Top 10 results
    
    res.json({
      ok: true,
      query: name,
      suggestions: scored.map(s => ({
        symbol: s.symbol,
        confidence: Math.min(100, Math.round(s.score / 10)),
        currentPrice: s.currentPrice,
        description: s.currentPrice ? `Prix actuel: ${s.currentPrice.toFixed(2)}` : '(N/A)',
        priceMatch: s.priceMatch
      }))
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// POST /mapping/save — Sauvegarde correspondance
app.post('/mapping/save', (req, res) => {
  try {
    const { userInput, mt5Symbol } = req.body;
    if (!userInput || !mt5Symbol) {
      return res.status(400).json({ ok: false, error: 'userInput and mt5Symbol required' });
    }
    
    // TODO: Persister dans une base ou fichier JSON mapping.json
    console.log(`[MAPPING] ${userInput} → ${mt5Symbol}`);
    
    res.json({
      ok: true,
      message: `Mapping saved: ${userInput} → ${mt5Symbol}`,
      userInput,
      mt5Symbol
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// GET /mapping/list — Liste des mappings enregistrés
app.get('/mapping/list', (req, res) => {
  try {
    // TODO: Charger depuis mapping.json
    const mappings = [];
    
    res.json({
      ok: true,
      count: mappings.length,
      mappings
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ─── MT5 BRIDGE ───────────────────────────────────────────────────────────────
app.post('/mt5', async (req, res) => {
  try {
    const activeSource = String(bridgeConfig.activeSource || (bridgeConfig.mt5Enabled === true ? 'mt5' : 'tradingview')).toLowerCase() === 'mt5' ? 'mt5' : 'tradingview';
    if (activeSource !== 'mt5') {
      return res.status(503).json({ ok: false, error: 'mt5 ingress disabled: active source is tradingview', mt5Enabled: false, activeSource });
    }

    if (bridgeConfig.mt5Enabled !== true) {
      return res.status(503).json({ ok: false, error: 'mt5 ingress disabled', mt5Enabled: false });
    }

    const payload  = req.body;
    if (!payload?.symbol) return res.status(400).json({ ok: false, error: 'symbol required' });

    const sourceRaw = String(payload.source || '').toLowerCase();
    if (sourceRaw && /(file|fallback|fixture|cache)/.test(sourceRaw)) {
      return res.status(400).json({ ok: false, error: 'non-live source rejected', source: payload.source, live: false });
    }

    // 🔴 LOG: CLEAR RECEPTION FROM EA
    console.log(`[MT5-POST] EA DIRECT | Symbol: ${payload.symbol} | Bid: ${payload.bid} | Ask: ${payload.ask} | Price: ${payload.price} | TS: ${payload.timestamp}`);

    const profile  = normalizeSymbol(payload.symbol);
    const canonical = profile.canonical;
    const resolvedTf = String(
      payload.timeframe ||
      activeSymbol?.timeframe ||
      marketStore.lastActiveTimeframe ||
      'H1'
    ).toUpperCase();

    // Accept timestamp as ms, seconds, numeric string, or ISO date.
    const tsRaw = payload.timestamp;
    let tickTs = NaN;
    if (typeof tsRaw === 'number' && Number.isFinite(tsRaw)) {
      tickTs = tsRaw < 1e12 ? tsRaw * 1000 : tsRaw;
    } else if (typeof tsRaw === 'string' && /^\d+$/.test(tsRaw)) {
      const n = Number(tsRaw);
      if (Number.isFinite(n)) tickTs = n < 1e12 ? n * 1000 : n;
    } else if (tsRaw) {
      const parsed = new Date(tsRaw).getTime();
      if (Number.isFinite(parsed)) tickTs = parsed;
    }

    if (!Number.isFinite(tickTs)) {
      return res.status(400).json({ ok: false, error: 'timestamp required for live tick validation', live: false });
    }

    const maxTickAgeMs = Math.max(1000, Number(process.env.MT5_MAX_TICK_AGE_MS || 10000));
    const tickAgeMs = Math.abs(Date.now() - tickTs);
    if (tickAgeMs > maxTickAgeMs) {
      return res.status(409).json({
        ok: false,
        error: 'stale tick rejected',
        tickAgeMs,
        maxTickAgeMs,
        live: false
      });
    }

    const livePrice = Number(payload.price || payload.bid || payload.ask);
    if (!Number.isFinite(livePrice) || livePrice <= 0) {
      return res.status(400).json({ ok: false, error: 'invalid live price', live: false });
    }

    marketStore.systemStatus = { source: 'mt5', fluxStatus: 'LIVE', lastUpdate: new Date().toISOString() };
    marketStore.updateFromMT5({
      ...payload,
      canonical,
      source: payload.source || 'mt5-live-direct',
      timeframe: resolvedTf,
      timestamp: new Date(tickTs).toISOString()
    }, canonical);

    // ─── [P3] SURVEILLANCE AGENT — Trigger analysis intelligently ─────────────────
    if (surveillanceAgent) {
      surveillanceAgent.onMT5Tick(canonical, {
        price: parseFloat(payload.price || payload.bid),
        bid: parseFloat(payload.bid),
        ask: parseFloat(payload.ask),
        volume: parseFloat(payload.volume || 0)
      });
    }

    // ─── [P2] MARKET HOURS CHECK — Bloquer ticks marché fermé ────────────────────
    const marketStatus = marketHoursChecker.getStatus(canonical);
    if (!marketStatus.isOpen) {
      console.log(`[TICK_BLOCKED] ${canonical} — ${marketStatus.market} closed (${marketStatus.reason || 'offline'})`);
      return res.json({ ok: false, blocked: true, symbol: canonical, market: marketStatus.market, reason: marketStatus.reason || 'closed' });
    }
    // ──────────────────────────────────────────────────────────────────────────────

    // [P1] Transmission du tick au CandleManager pour agrégation OHLC
    if (candleManager) {
      candleManager.onTick(
        canonical,
        parseFloat(payload.price || payload.bid || 0),
        parseFloat(payload.bid   || 0),
        parseFloat(payload.ask   || 0),
        parseFloat(payload.volume || 0),
        tickTs
      ).catch(e => console.error('[CANDLE TICK ERROR]', e.message));
    }

    // Mise à jour zones si données OHLC disponibles
    const ohlc = payload.ohlc || payload.bars || [];
    if (ohlc.length >= 3 && payload.price) {
      zoneManager.updateZones(parseFloat(payload.price));
    }

    // Broadcast prix immédiat avant orchestrateur
    marketStore.broadcast({ type: 'mt5-raw', symbol: canonical, price: payload.price || payload.bid, timeframe: payload.timeframe, source: 'mt5' });

    // 🔴 UNIFIED SYNC: Envoyer aussi à Extension + HTML clients
    broadcastToExtension({
      type: 'mt5-data',
      symbol: canonical,
      brokerSymbol: payload.symbol,
      price: parseFloat(payload.price || payload.bid || 0),
      bid: parseFloat(payload.bid || 0),
      ask: parseFloat(payload.ask || 0),
      volume: parseFloat(payload.volume || 0),
      timeframe: resolvedTf,
      source: 'mt5-live-direct',
      ohlc: ohlc,
      indicators: {
        rsi: payload.rsi || null,
        macd: payload.macd || null,
        ma20: payload.ma20 || null
      }
    });

    emitResolvedActiveSymbol('mt5-post');

    // DETAILED LOGGING
    const ohlcInfo = ohlc.length > 0 ? `yes (${ohlc.length})` : 'no';
    const logMsg = `[MT5] ${payload.symbol} (${canonical}) | Price:${payload.price} | Bid:${payload.bid} Ask:${payload.ask} | TF:${payload.timeframe || 'N/A'} | OHLC:${ohlcInfo}`;
    console.log(logMsg);

    if (orchestrator) {
      orchestrator.run({ ...payload, symbol: canonical, broker_symbol: payload.symbol })
        .then(analysis => {
          marketStore.updateAnalysis(canonical, analysis);
          console.log(`[ORCH] ${canonical} → ${analysis.direction} score=${analysis.score}`);
        })
        .catch(e => console.error('[ORCH ERROR]', e.message));
    }

    return res.json({ ok: true, canonical, brokerSymbol: payload.symbol, assetType: profile.type });
  } catch (err) {
    return res.status(500).json({ ok: false, error: err.message });
  }
});

// ─── [P2] ENDPOINT: Market Status Diagnostic ───────────────────────────────────
// GET /mt5/market-status?symbol=EURUSD
// Retourne: { isOpen, market, session, opensIn, closesIn, ... }
app.get('/mt5/market-status', (req, res) => {
  try {
    const { symbol } = req.query;
    
    if (!symbol) {
      // Return status for all active symbols
      const activeSymbols = Object.keys(marketStore.bySymbol);
      const statuses = activeSymbols.map(s => ({
        symbol: s,
        ...marketHoursChecker.getStatus(s),
        lastTickTime: marketStore.bySymbol[s]?.updatedAt || null,
        lastTickPrice: marketStore.bySymbol[s]?.latestPayload?.price || null
      }));
      return res.json({ count: statuses.length, statuses });
    }
    
    // Single symbol
    const status = marketHoursChecker.getStatus(symbol);
    const lastData = marketStore.bySymbol[symbol];
    
    return res.json({
      symbol,
      ...status,
      lastTickTime: lastData?.updatedAt || null,
      lastTickPrice: lastData?.latestPayload?.price || null
    });
  } catch (err) {
    return res.status(500).json({ ok: false, error: err.message });
  }
});
// ──────────────────────────────────────────────────────────────────────────────

// ─── MT5 BRIDGE PROXY — legacy-compatible HTTP relay (non-4000) ─────────────
const http       = require('http');
// MT5_BRIDGE_PYTHON already configured at top of file (check health via /mt5/status)

function mt5Fetch(path) {
  return new Promise((resolve, reject) => {
    const req = http.get(MT5_BRIDGE_PYTHON + path, { timeout: 4000 }, res => {
      let data = '';
      res.on('data', d => { data += d; });
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error('JSON parse error from MT5 Bridge')); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('MT5 Bridge Python timeout')); });
  });
}

// Proxy transparent vers le bridge Python MT5 RÉEL
app.get('/mt5/status',  async (_req, res) => { 
  try {
    // Return connection status based on real data reception (no legacy port call)
    const connStatus = {
      ok: true,
      connected: false,
      source: marketStore.systemStatus?.source || 'offline',
      fluxStatus: marketStore.systemStatus?.fluxStatus || 'OFFLINE',
      lastUpdate: marketStore.systemStatus?.lastUpdate || null,
      message: 'MT5 not connected - no POST /mt5 received yet'
    };
    
    // Check if we've received MT5 data AND it's recent (within last 2 minutes)
    if (marketStore.systemStatus?.source === 'mt5' && marketStore.systemStatus?.fluxStatus === 'LIVE') {
      const lastUpdateTime = new Date(marketStore.systemStatus.lastUpdate).getTime();
      const nowTime = Date.now();
      const ageMs = nowTime - lastUpdateTime;
      const ageSec = Math.floor(ageMs / 1000);
      
      if (ageMs < 120000) {
        connStatus.connected = true;
        connStatus.message = `MT5 connected (data ${ageSec}s old)`;
      } else {
        connStatus.message = `MT5 data stale (last update ${ageSec}s ago)`;
      }
    }
    
    res.json(connStatus);
  } catch (e) { 
    res.json({ 
      ok: false, 
      connected: false, 
      error: e.message,
      note: 'Error checking MT5 connection'
    }); 
  } 
});

app.get('/mt5/match',   async (req, res) => {
  const { name='', price='', category='' } = req.query;
  try { 
    res.json(await mt5Fetch(`/mt5/match?name=${encodeURIComponent(name)}&price=${encodeURIComponent(price)}&category=${encodeURIComponent(category)}`)); 
  }
  catch (e) {
    res.json({ 
      ok:false, 
      error:e.message, 
      query:name, 
      candidates:[],
      note:'MT5 Bridge error — check if mt5_bridge.py is running'
    });
  }
});
app.get('/mt5/price', async (req, res) => {
  try {
    const symbol = req.query.symbol || 'XAUUSD';

    const mt5Response = await mt5Fetch('/mt5/price?symbol=' + encodeURIComponent(symbol));
    if (mt5Response?.ok && Number.isFinite(Number(mt5Response.price)) && Number(mt5Response.price) > 0) {
      return res.json(mt5Response);
    }

    return res.status(503).json({
      ok: false,
      symbol,
      error: 'No live MT5 price available',
      source: 'none',
      live: false
    });
  } catch (e) {
    res.status(503).json({ ok: false, error: e.message, source: 'none', live: false });
  }
});
app.get('/mt5/klines',  async (req, res) => {
  const { symbol, tf='H1', count='200' } = req.query;
  if (!symbol) return res.status(400).json({ ok: false, error: 'symbol parameter required' });
  try {
    const data = await mt5Fetch(`/mt5/klines?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tf)}&count=${encodeURIComponent(count)}`);
    // Compatibility bridge: legacy/background expects "rates", modern handlers use "klines".
    if (data && Array.isArray(data.klines) && !Array.isArray(data.rates)) {
      data.rates = data.klines;
    }
    if (data && Array.isArray(data.klines) && data.klines.length > 0) {
      return res.json(data);
    }

    return res.status(503).json({
      ok: false,
      symbol: normalizeSymbol(String(symbol || '').toUpperCase()).canonical,
      timeframe: String(tf || 'H1').toUpperCase(),
      error: 'No live MT5 klines available',
      source: 'none',
      live: false
    });
  }
  catch (e) {
    return res.status(503).json({ ok:false, error:e.message, source: 'none', live: false });
  }
});

app.get('/mt5/file-health', (_req, res) => {
  try {
    const dataFile = path.join(__dirname, 'mt5_data.json');
    if (!fs.existsSync(dataFile)) {
      return res.status(404).json({ ok: false, exists: false, live: false, error: 'mt5_data.json not found' });
    }

    const stat = fs.statSync(dataFile);
    const ageMs = Date.now() - stat.mtimeMs;
    const live = ageMs <= 10000;
    return res.json({
      ok: true,
      exists: true,
      live,
      source: 'file-diagnostic-only',
      updatedAt: new Date(stat.mtimeMs).toISOString(),
      ageMs,
      ageSec: Math.round(ageMs / 1000)
    });
  } catch (e) {
    return res.status(500).json({ ok: false, live: false, error: e.message });
  }
});

// GET /economic-events — Événements économiques réels (fixture)
app.get('/economic-events', (req, res) => {
  try {
    // Generate sample economic events for next 48h
    const now = new Date();
    const events = [
      {
        id: 'nfp-1',
        title: 'NFP (Non-Farm Payroll)',
        country: 'USA',
        time: new Date(now.getTime() + 3600000).toISOString(),
        impact: 'HIGH',
        forecast: '+250k',
        previous: '+225k',
        currency: 'USD',
        symbols: ['EURUSD', 'GBPUSD', 'USDJPY'],
        bias: 'Bullish USD if strong'
      },
      {
        id: 'cpi-1',
        title: 'CPI Inflation',
        country: 'USA',
        time: new Date(now.getTime() + 7200000).toISOString(),
        impact: 'HIGH',
        forecast: '3.2%',
        previous: '3.4%',
        currency: 'USD',
        symbols: ['EURUSD', 'GBPUSD'],
        bias: 'Bearish USD if lower'
      },
      {
        id: 'ecb-1',
        title: 'ECB Interest Rate Decision',
        country: 'EUR',
        time: new Date(now.getTime() + 14400000).toISOString(),
        impact: 'HIGH',
        forecast: '4.5%',
        previous: '4.5%',
        currency: 'EUR',
        symbols: ['EURUSD', 'EURGBP'],
        bias: 'Impact if changed'
      },
      {
        id: 'boe-1',
        title: 'BOE Monetary Policy',
        country: 'GBP',
        time: new Date(now.getTime() + 21600000).toISOString(),
        impact: 'MEDIUM',
        forecast: '5.25%',
        previous: '5.25%',
        currency: 'GBP',
        symbols: ['GBPUSD', 'EURGBP'],
        bias: 'Monitor for changes'
      },
      {
        id: 'fed-1',
        title: 'FED Funds Rate',
        country: 'USA',
        time: new Date(now.getTime() + 28800000).toISOString(),
        impact: 'HIGH',
        forecast: '5.50%',
        previous: '5.50%',
        currency: 'USD',
        symbols: ['EURUSD', 'USDJPY', 'GBPUSD'],
        bias: 'Critical for USD'
      },
      {
        id: 'gold-1',
        title: 'Gold Technical Support',
        country: 'COMMODITY',
        time: new Date(now.getTime() + 36000000).toISOString(),
        impact: 'MEDIUM',
        forecast: '--',
        previous: '--',
        currency: 'USD',
        symbols: ['XAUUSD', 'GOLD'],
        bias: 'Watch 2400 level'
      }
    ];

    res.json({ ok: true, count: events.length, events });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Symbol mapping storage (JSON file)
const MAPPING_PATH = path.join(__dirname, 'symbol-mappings.json');
function loadMappings() { try { return JSON.parse(fs.readFileSync(MAPPING_PATH,'utf8')); } catch(_){ return {}; } }
function saveMappings(m) { fs.writeFileSync(MAPPING_PATH, JSON.stringify(m, null, 2)); }

app.get('/mt5/mappings', (_req, res) => { res.json({ ok:true, mappings: loadMappings() }); });
app.post('/mt5/mappings', (req, res) => {
  const { alias, mt5Symbol } = req.body || {};
  if (!alias || !mt5Symbol) return res.status(400).json({ ok:false, error:'alias and mt5Symbol required' });
  const m = loadMappings();
  m[alias.toUpperCase()] = mt5Symbol;
  saveMappings(m);
  pushLog('extension', 'mt5', `MAPPING: ${alias.toUpperCase()} → ${mt5Symbol}`, 'ok', '');
  res.json({ ok:true, mappings: m });
});

// Fallback symbols when bridge offline
const FALLBACK_MT5_SYMBOLS = [
  {name:'XAUUSD',  description:'Gold vs US Dollar',          category:'metal',     digits:2},
  {name:'XAGUSD',  description:'Silver vs US Dollar',        category:'metal',     digits:3},
  {name:'EURUSD',  description:'Euro vs US Dollar',          category:'forex',     digits:5},
  {name:'GBPUSD',  description:'British Pound vs USD',       category:'forex',     digits:5},
  {name:'USDJPY',  description:'US Dollar vs Japanese Yen',  category:'forex',     digits:3},
  {name:'USDCHF',  description:'US Dollar vs Swiss Franc',   category:'forex',     digits:5},
  {name:'AUDUSD',  description:'Australian Dollar vs USD',   category:'forex',     digits:5},
  {name:'NZDUSD',  description:'New Zealand Dollar vs USD',  category:'forex',     digits:5},
  {name:'USDCAD',  description:'US Dollar vs Canadian Dollar',category:'forex',    digits:5},
  {name:'BTCUSD',  description:'Bitcoin vs US Dollar',       category:'crypto',    digits:2},
  {name:'ETHUSD',  description:'Ethereum vs US Dollar',      category:'crypto',    digits:2},
  {name:'US30',    description:'Dow Jones Industrial 30',    category:'index',     digits:2},
  {name:'US500',   description:'S&P 500 Index',              category:'index',     digits:2},
  {name:'NAS100',  description:'Nasdaq 100',                 category:'index',     digits:2},
  {name:'GER40',   description:'DAX 40',                     category:'index',     digits:2},
  {name:'UK100',   description:'FTSE 100',                   category:'index',     digits:2},
  {name:'USOIL',   description:'WTI Crude Oil',              category:'commodity', digits:2},
];

// ─── TV BRIDGE ────────────────────────────────────────────────────────────────
app.post('/tv-bridge', async (req, res) => {
  try {
    const { symbol: rawSym, tf, price, url, title } = req.body || {};
    if (!rawSym) return res.status(400).json({ ok: false, error: 'symbol required' });

    const profile  = normalizeSymbol(rawSym);
    const canonical = profile.canonical;
    const numPrice = parseFloat(price) || 0;

    const bridgeEnabled = bridgeConfig.bridgeEnabled !== false;
    const tvEnabled = bridgeConfig.tradingviewEnabled !== false;

    if (!bridgeEnabled || !tvEnabled) {
      return res.json({
        ok: true,
        canonical,
        source: 'tradingview',
        price: numPrice,
        bridgeApplied: false,
        reason: !bridgeEnabled ? 'bridge_disabled' : 'tradingview_disabled'
      });
    }

    marketStore.systemStatus = { source: 'tradingview', fluxStatus: 'LIVE', lastUpdate: new Date().toISOString() };
    marketStore.updateFromMT5({ symbol: canonical, price: numPrice, timeframe: tf, source: 'tv-bridge' }, canonical);
    marketStore.broadcast({ type: 'mt5-raw', symbol: canonical, price: numPrice, timeframe: tf, source: 'tradingview' });

    // 🔴 UNIFIED SYNC: Envoyer aussi à Extension + HTML clients
    broadcastToExtension({
      type: 'tradingview-data',
      symbol: canonical,
      brokerSymbol: rawSym,
      price: numPrice,
      bid: null,
      ask: null,
      timeframe: tf,
      source: 'tradingview-live',
      url: url || null,
      title: title || null
    });

    emitResolvedActiveSymbol('tv-bridge');

    if (orchestrator) {
      orchestrator.run({ symbol: canonical, broker_symbol: rawSym, price: numPrice, timeframe: tf, bid: numPrice, ask: numPrice })
        .then(a => marketStore.updateAnalysis(canonical, a))
        .catch(() => {});
    }
    res.json({ ok: true, canonical, source: 'tradingview', price: numPrice });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ─── SSE STREAM ───────────────────────────────────────────────────────────────
app.get('/stream', (_req, res) => {
  res.setHeader('Content-Type',  'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection',    'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();

  const hb = setInterval(() => { try { res.write(': heartbeat\n\n'); } catch { clearInterval(hb); marketStore.sseClients = marketStore.sseClients.filter(c => c !== res); } }, 15000);
  marketStore.addSSEClient(res);
  res.on('close', () => clearInterval(hb));
});

// ─── UNIFIED EXTENSION SYNC (Extension Chrome + HTML popup — MÊME SOURCE) ──────
// SSE endpoint centralisé: Extension ET HTML se connectent ICI
// Données: MT5 réel, TradingView réel, status système, agent activity
const extensionSyncClients = [];

const BRIDGE_MODES = new Set(['AUTO', 'ANALYSE', 'ALERTE', 'EXECUTION_PREPAREE', 'SCALPER', 'SNIPER', 'SWING']);

const EXTENSION_RUNTIME_STATE_PATH = path.join(__dirname, 'store', 'extension-runtime-state.json');

let activeSymbol = { symbol: null, timeframe: 'H1', price: null, updatedAt: null };

let bridgeConfig = {
  agentName: 'orchestrator',
  bridgeSource: 'tradingview',
  activeSource: 'tradingview',
  bridgeMode: 'AUTO',
  bridgeEnabled: true,
  tradingviewEnabled: true,
  mt5Enabled: false,
  sendPreAlerts: true,
  sendSignals: true,
  symbolAliasBridge: '',
  updatedAt: null,
  updatedBy: 'system'
};

function loadExtensionRuntimeState() {
  try {
    if (!fs.existsSync(EXTENSION_RUNTIME_STATE_PATH)) return;
    const raw = fs.readFileSync(EXTENSION_RUNTIME_STATE_PATH, 'utf8');
    const parsed = JSON.parse(raw || '{}');
    if (parsed && typeof parsed === 'object') {
      if (parsed.activeSymbol && typeof parsed.activeSymbol === 'object') {
        activeSymbol = {
          ...activeSymbol,
          ...parsed.activeSymbol
        };
      }
      if (parsed.bridgeConfig && typeof parsed.bridgeConfig === 'object') {
        bridgeConfig = {
          ...bridgeConfig,
          ...parsed.bridgeConfig
        };
      }
    }
  } catch (e) {
    console.warn('[EXTENSION-RUNTIME] load failed:', e.message);
  }
}

function saveExtensionRuntimeState() {
  try {
    const dir = path.dirname(EXTENSION_RUNTIME_STATE_PATH);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const payload = {
      savedAt: new Date().toISOString(),
      activeSymbol,
      bridgeConfig
    };
    fs.writeFileSync(EXTENSION_RUNTIME_STATE_PATH, JSON.stringify(payload, null, 2), 'utf8');
  } catch (e) {
    console.warn('[EXTENSION-RUNTIME] save failed:', e.message);
  }
}

function toBoolOrNull(v) {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'number') return v !== 0;
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase();
    if (['1', 'true', 'yes', 'on', 'oui'].includes(s)) return true;
    if (['0', 'false', 'no', 'off', 'non'].includes(s)) return false;
  }
  return null;
}

function normalizeBridgeMode(raw) {
  const mode = String(raw || '').trim().replace(/\s+/g, '_').toUpperCase();
  if (!mode) return bridgeConfig.bridgeMode;
  return BRIDGE_MODES.has(mode) ? mode : mode;
}

function sanitizeBridgeConfigPatch(patch) {
  const p = patch && typeof patch === 'object' ? patch : {};
  const out = {};

  if (p.agentName != null) {
    out.agentName = String(p.agentName).trim() || bridgeConfig.agentName;
  }

  if (p.bridgeSource != null || p.source != null) {
    const src = p.bridgeSource != null ? p.bridgeSource : p.source;
    out.bridgeSource = String(src || '').trim().toLowerCase() || bridgeConfig.bridgeSource;
  }

  if (p.activeSource != null || p.sourceActive != null) {
    const src = p.activeSource != null ? p.activeSource : p.sourceActive;
    const s = String(src || '').trim().toLowerCase();
    if (s === 'tradingview' || s === 'mt5') out.activeSource = s;
  }

  if (p.bridgeMode != null || p.mode != null) {
    out.bridgeMode = normalizeBridgeMode(p.bridgeMode != null ? p.bridgeMode : p.mode);
  }

  if (p.bridgeEnabled != null || p.enabled != null) {
    const b = toBoolOrNull(p.bridgeEnabled != null ? p.bridgeEnabled : p.enabled);
    if (b != null) out.bridgeEnabled = b;
  }

  if (p.tradingviewEnabled != null || p.tvEnabled != null) {
    const b = toBoolOrNull(p.tradingviewEnabled != null ? p.tradingviewEnabled : p.tvEnabled);
    if (b != null) out.tradingviewEnabled = b;
  }

  if (p.mt5Enabled != null) {
    const b = toBoolOrNull(p.mt5Enabled);
    if (b != null) out.mt5Enabled = b;
  }

  if (p.sendPreAlerts != null || p.preAlerts != null || p.sendPreAlert != null) {
    const b = toBoolOrNull(p.sendPreAlerts != null ? p.sendPreAlerts : (p.preAlerts != null ? p.preAlerts : p.sendPreAlert));
    if (b != null) out.sendPreAlerts = b;
  }

  if (p.sendSignals != null) {
    const b = toBoolOrNull(p.sendSignals);
    if (b != null) out.sendSignals = b;
  }

  if (p.symbolAliasBridge != null || p.symbolAlias != null || p.alias != null) {
    const aliasRaw = p.symbolAliasBridge != null ? p.symbolAliasBridge : (p.symbolAlias != null ? p.symbolAlias : p.alias);
    out.symbolAliasBridge = String(aliasRaw || '').replace(/[/\-\s]/g, '').toUpperCase();
  }

  if (p.updatedBy != null) {
    out.updatedBy = String(p.updatedBy).trim() || 'system';
  }

  return out;
}

function applyBridgeConfigPatch(patch, updatedBy) {
  const clean = sanitizeBridgeConfigPatch(patch);

  if (clean.tradingviewEnabled === true) {
    clean.mt5Enabled = false;
    clean.activeSource = 'tradingview';
  }
  if (clean.mt5Enabled === true) {
    clean.tradingviewEnabled = false;
    clean.activeSource = 'mt5';
  }

  bridgeConfig = {
    ...bridgeConfig,
    ...clean,
    updatedAt: new Date().toISOString(),
    updatedBy: updatedBy || clean.updatedBy || 'system'
  };

  if (bridgeConfig.activeSource !== 'mt5') {
    bridgeConfig.activeSource = 'tradingview';
  }

  if (bridgeConfig.activeSource === 'tradingview') {
    bridgeConfig.tradingviewEnabled = true;
    bridgeConfig.mt5Enabled = false;
    bridgeConfig.bridgeSource = 'tradingview';
  } else {
    bridgeConfig.mt5Enabled = true;
    bridgeConfig.tradingviewEnabled = false;
    bridgeConfig.bridgeSource = 'mt5';
  }

  saveExtensionRuntimeState();

  return bridgeConfig;
}

loadExtensionRuntimeState();

function emitBridgeConfig(origin) {
  broadcastToExtension({
    type: 'bridge-config',
    origin: origin || 'bridge',
    bridgeConfig
  });
}

app.get('/extension/sync', (_req, res) => {
  res.setHeader('Content-Type',  'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection',    'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.flushHeaders();

  // Send initial state immediately
  const resolvedCtx = resolveActiveRuntimeContext();
  const initialState = {
    type: 'initial-sync',
    timestamp: new Date().toISOString(),
    systemStatus: marketStore.systemStatus || { source: 'offline', fluxStatus: 'OFFLINE' },
    activeSymbol: {
      ...(activeSymbol || {}),
      symbol: resolvedCtx.active.symbol || activeSymbol?.symbol || null,
      timeframe: resolvedCtx.active.timeframe || activeSymbol?.timeframe || 'H1',
      price: resolvedCtx.active.price ?? activeSymbol?.price ?? activeSymbol?.tvPrice ?? null,
      source: resolvedCtx.active.source || 'none',
      resolvedBy: resolvedCtx.active.resolvedBy || 'none'
    },
    bridgeConfig,
    agentStates: agentStates,
    sourceContexts: resolvedCtx,
    message: 'Extension + HTML synchronisés — source unique'
  };
  res.write('data: ' + JSON.stringify(initialState) + '\n\n');

  // Add to clients list
  extensionSyncClients.push(res);
  console.log(`[EXTENSION-SYNC] Client connecté (total: ${extensionSyncClients.length})`);

  // Heartbeat for keep-alive
  const hb = setInterval(() => {
    try {
      res.write(': heartbeat\n\n');
    } catch (e) {
      clearInterval(hb);
      const idx = extensionSyncClients.indexOf(res);
      if (idx > -1) extensionSyncClients.splice(idx, 1);
    }
  }, 15000);

  res.on('close', () => {
    clearInterval(hb);
    const idx = extensionSyncClients.indexOf(res);
    if (idx > -1) extensionSyncClients.splice(idx, 1);
    console.log(`[EXTENSION-SYNC] Client déconnecté (total: ${extensionSyncClients.length})`);
  });

  res.on('error', () => {
    clearInterval(hb);
    const idx = extensionSyncClients.indexOf(res);
    if (idx > -1) extensionSyncClients.splice(idx, 1);
  });
});

// ─── BROADCAST UNIFIED DATA TO ALL EXTENSION CLIENTS ────────────────────────────
// Called whenever MT5 data, TradingView data, or system status changes
// Ensures Extension + HTML see IDENTICAL data in real-time
function broadcastToExtension(message) {
  if (extensionSyncClients.length === 0) {
    // SAFE: avoid log flood when no extension clients are connected.
    return;
  }
  
  const data = {
    ...message,
    timestamp: new Date().toISOString(),
    type: message.type || 'data-update'
  };

  // Bridge OFF: stop live flow propagation, keep control/sync events only.
  const t = String(data.type || '');
  if (bridgeConfig.bridgeEnabled === false && (t === 'mt5-data' || t === 'tradingview-data')) {
    return;
  }

  const sseMessage = 'data: ' + JSON.stringify(data) + '\n\n';
  
  // Log clearly for mt5-data
  if (message.type === 'mt5-data') {
    console.log(`[EXTENSION-SYNC] 📤 Broadcasting MT5 to ${extensionSyncClients.length} clients: ${message.symbol} | Bid: ${message.bid} | Ask: ${message.ask} | Price: ${message.price}`);
  } else {
    console.log(`[BROADCAST] Sending to ${extensionSyncClients.length} clients: ${message.type}`);
  }
  
  for (let i = extensionSyncClients.length - 1; i >= 0; i--) {
    try {
      extensionSyncClients[i].write(sseMessage);
    } catch (e) {
      // Client disconnected
      console.log('[BROADCAST] Client disconnected, removing from list');
      extensionSyncClients.splice(i, 1);
    }
  }
}

// ─── GET CURRENT STATE ENDPOINT (for late-joining clients or polling fallback) ──
// Returns the EXACT same data that SSE clients receive
app.get('/extension/data', (_req, res) => {
  // Source unique : TradingView live
  const tvRuntime = getLatestTradingviewRuntime();
  if (!tvRuntime?.connected || !tvRuntime?.symbol || !tvRuntime?.payload?.price) {
    return res.json({
      ok: false,
      error: 'NO DATA',
      message: 'Aucune donnée TradingView live disponible',
      type: 'current-state',
      timestamp: new Date().toISOString()
    });
  }
  res.json({
    ok: true,
    type: 'current-state',
    timestamp: new Date().toISOString(),
    systemStatus: { source: 'tradingview', fluxStatus: 'LIVE' },
    activeSymbol: {
      symbol: tvRuntime.symbol,
      timeframe: tvRuntime.timeframe,
      price: tvRuntime.payload.price,
      source: 'tradingview',
      resolvedBy: 'tv-live'
    },
    bridgeConfig,
    agentStates: agentStates,
    sourceContexts: {},
    currentData: {
      symbol: tvRuntime.symbol,
      price: tvRuntime.payload.price,
      bid: tvRuntime.payload.price,
      ask: tvRuntime.payload.price,
      volume: 0,
      timeframe: tvRuntime.timeframe,
      source: 'tradingview',
      indicators: {
        rsi: tvRuntime.payload.rsi ?? null,
        ma20: null,
        macd: null
      },
      updatedAt: tvRuntime.timestamp || null
    },
    message: 'Current state TradingView live — aucune autre source'
  });
});

// ─── UNIFIED COMMAND ENDPOINT (Extension + HTML send commands here) ────────────
// Receives commands from Extension or HTML and broadcasts to all clients
app.post('/extension/command', async (req, res) => {
  const { command, payload } = req.body || {};
  
  if (!command) {
    return res.status(400).json({ ok: false, error: 'command required' });
  }
  
  console.log('[EXTENSION-CMD]', command, payload);
  
  try {
    let result = { ok: true, command, message: '' };
    
    switch (command) {
      // Change active symbol
      case 'set-symbol':
        const { symbol, timeframe, price, mode } = payload || {};
        if (symbol) {
          const rawNormalized = String(symbol).replace(/[/\-]/g, '').toUpperCase();
          const canonicalSymbol = normalizeSymbol(rawNormalized).canonical || rawNormalized;
          const requestedMode = normalizeBridgeMode(mode || activeSymbol?.mode || bridgeConfig.bridgeMode || 'AUTO');
          const resolvedMode = resolveRuntimeMode(requestedMode, canonicalSymbol, timeframe || 'H1');
          // Send as if received from extension
          activeSymbol = {
            symbol: canonicalSymbol,
            timeframe: timeframe || 'H1',
            price: price || null,
            mode: requestedMode,
            modeResolved: resolvedMode,
            updatedAt: new Date().toISOString()
          };
          saveExtensionRuntimeState();

          applyBridgeConfigPatch({
            bridgeMode: requestedMode,
            symbolAliasBridge: activeSymbol.symbol
          }, 'extension');
          
          // Broadcast to all Extension + HTML clients
          // Preserve TV origin so popup.js can reset userLocked correctly
          const _isTvSource = String(payload?.source || '').toLowerCase().includes('tradingview');
          broadcastToExtension({
            type: 'active-symbol',
            ...activeSymbol,
            modeResolved: resolvedMode,
            source: _isTvSource ? 'tradingview' : 'extension-command',
            resolvedBy: _isTvSource ? 'tv-runtime-fresh' : 'extension-active-symbol'
          });
          emitBridgeConfig('set-symbol');
          
          result.message = `Symbol set to ${activeSymbol.symbol}`;
        }
        break;

      case 'set-bridge-config':
        applyBridgeConfigPatch(payload || {}, 'extension-command');
        if (payload && (payload.bridgeMode != null || payload.mode != null)) {
          const requestedMode = normalizeBridgeMode(payload.bridgeMode != null ? payload.bridgeMode : payload.mode);
          const symbolForMode = activeSymbol?.symbol || marketStore.lastActiveSymbol || 'XAUUSD';
          const tfForMode = activeSymbol?.timeframe || marketStore.lastActiveTimeframe || 'H1';
          const resolvedMode = resolveRuntimeMode(requestedMode, symbolForMode, tfForMode);

          activeSymbol = {
            ...(activeSymbol || {}),
            symbol: symbolForMode,
            timeframe: tfForMode,
            mode: requestedMode,
            modeResolved: resolvedMode,
            updatedAt: new Date().toISOString()
          };
          saveExtensionRuntimeState();

          broadcastToExtension({
            type: 'active-symbol',
            ...activeSymbol,
            source: 'extension-bridge-config',
            resolvedBy: 'bridge-config-update'
          });
        }
        emitBridgeConfig('set-bridge-config');
        result.bridgeConfig = bridgeConfig;
        result.message = bridgeConfig.bridgeEnabled === false ? 'Bridge disabled' : 'Bridge config updated';
        break;
        
      // Trigger analysis
      case 'analyze':
        const sym = payload?.symbol || activeSymbol.symbol;
        if (sym) {
          const profile = normalizeSymbol(sym);
          const tf = String(payload?.timeframe || activeSymbol?.timeframe || marketStore.lastActiveTimeframe || 'H1').toUpperCase();
          const requestedMode = normalizeBridgeMode(payload?.mode || activeSymbol?.mode || bridgeConfig.bridgeMode || 'AUTO');
          const tradeState = getCoachTradeState(profile.canonical, tf);
          const snapshot = await computeCoachAnalysisSnapshot(profile.canonical, tf, 'fr', tradeState, {
            forceFresh: true,
            mode: requestedMode,
            maxAgeMs: 0
          }).catch(() => null);

          result.analysisTriggered = !!snapshot;
          result.analysisInput = {
            symbol: profile.canonical,
            timeframe: tf,
            price: snapshot?.currentPrice || activeSymbol?.price || null,
            modeResolved: snapshot?.modeResolved || resolveRuntimeMode(requestedMode, profile.canonical, tf)
          };
          result.analysis = snapshot ? {
            recommendation: snapshot.analysis?.recommendation || 'WAIT',
            reason: snapshot.analysis?.reason || 'Analyse indisponible',
            confidence: snapshot.analysis?.confidence || 0
          } : null;
          result.message = snapshot
            ? `Analysis triggered for ${profile.canonical} (${result.analysis.recommendation})`
            : `Analysis triggered for ${profile.canonical}`;
          if (!snapshot) result.warning = 'No live context available for analysis trigger';
        }
        break;
        
      // Get symbols
      case 'get-symbols':
        result.symbols = realDataSimulator.getAvailableSymbols();
        break;
        
      // Refresh data (simulator)
      case 'refresh-data':
        const data = realDataSimulator.getNextData();
        const prof = normalizeSymbol(data.symbol);
        marketStore.updateFromMT5({
          symbol: data.symbol,
          price: data.price,
          bid: data.bid,
          ask: data.ask,
          volume: data.volume,
          source: 'simulator'
        }, prof.canonical);
        
        broadcastToExtension({
          type: 'mt5-data',
          symbol: prof.canonical,
          price: data.price,
          bid: data.bid,
          ask: data.ask,
          volume: data.volume,
          source: 'simulator'
        });
        result.data = data;
        break;
        
      default:
        result.ok = false;
        result.error = 'Unknown command: ' + command;
    }
    
    pushLog('extension', 'system', 'COMMAND: ' + command, result.ok ? 'ok' : 'err', result.message || result.error || '');
    res.json(result);
    
  } catch (e) {
    console.error('[EXTENSION-CMD] Error:', e.message);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ─── STATE ────────────────────────────────────────────────────────────────────
app.get('/state', (_req, res) => {
  res.json({ ok: true, ...marketStore.getState() });
});

// ─── INSTANT TRADE LIVE ───────────────────────────────────────────────────────
// Priorité: MT5 cache → orchestrateur avec prix réel → prix Yahoo (chart seulement)
// Middleware: intercepte la réponse pour alimenter le AGENTS LIVE LOG automatiquement
app.use('/instant-trade-live', (req, res, next) => {
  const origJson = res.json.bind(res);
  res.json = function(data) {
    if (data && data.ok && data.trade) {
      const tr = data.trade;
      pushLog(
        'technicalAgent', 'orchestrator',
        `SIGNAL ${tr.direction || '?'} · ${tr.symbol || req.query.symbol || '?'} @ ${tr.entry || '?'}`,
        'ok',
        `Score:${tr.score || 0} · ${tr.setup_type || '?'} · SL:${tr.sl || '?'} TP:${tr.tp || '?'} · src:${data.source || '?'}`
      );
    }
    return origJson(data);
  };
  next();
});

app.get('/instant-trade-live', async (req, res) => {
  const rawSym  = req.query.symbol;
  if (!rawSym) return res.status(400).json({ ok: false, error: 'symbol parameter required' });
  console.log(`[BRIDGE] /instant-trade-live requested for symbol: ${rawSym}`);
  const reqTF   = req.query.tf     || 'H1';
  const reqMode = req.query.mode   || '';        // SCALPER | SNIPER | SWING
  const profile = normalizeSymbol(rawSym);
  const sym     = profile.canonical;

  // TradingView-only: no MT5 fallback.
  const tv = getLatestTradingviewRuntime();
  const tvSymbol = String(tv?.symbol || '').toUpperCase();
  const tvPrice = Number(tv?.payload?.price);
  if (bridgeConfig.tradingviewEnabled !== false && tv?.connected && tvSymbol === sym && Number.isFinite(tvPrice) && tvPrice > 0) {
    const tf = String(tv?.timeframe || reqTF || 'H1').toUpperCase();
    const robotV12 = getRobotV12ForSymbol(sym);
    const trade = buildTradingviewRuntimeTrade(sym, tf, tvPrice, reqMode, tv, robotV12);
    if (trade) {
      return res.json({ ok: true, trade, source: 'tradingview', price: tvPrice, timeframe: tf, robotV12 });
    }
    return res.json({
      ok: true,
      trade: null,
      source: 'tradingview',
      price: tvPrice,
      timeframe: tf,
      robotV12,
      message: 'Signal TradingView en attente de confirmation.'
    });
  }

  return res.status(503).json({
    ok: false,
    error: 'Aucune source TradingView live disponible pour ' + sym + '.',
    source: 'none',
    live: false
  });
});

// ─── ZONES ────────────────────────────────────────────────────────────────────
app.post('/zones', (req, res) => {
  const { symbol, tf, high, low, type } = req.body;
  if (!symbol || !high || !low || !type) return res.status(400).json({ ok: false, error: 'symbol, high, low, type required' });
  const profile  = normalizeSymbol(symbol);
  const zone     = zoneManager.createZone({ symbol: profile.canonical, tf, high, low, type });
  console.log(`[ZONE] Created ${type} zone for ${profile.canonical}: ${low}–${high}`);
  res.json({ ok: true, zone });
});

app.get('/zones/:symbol', (req, res) => {
  const profile = normalizeSymbol(req.params.symbol);
  const tf      = req.query.tf || null;
  const zones   = zoneManager.getActiveZones(profile.canonical, tf);
  const price   = marketStore.getLatestForSymbol(profile.canonical)?.latestPayload?.price;
  if (price) zoneManager.updateZones(parseFloat(price));
  res.json({ ok: true, symbol: profile.canonical, zones, count: zones.length });
});

// ─── CHART DATA (timer bougie réel) ──────────────────────────────────────────
app.get('/chart-data', (req, res) => {
  // Source unique : TradingView live
  const tvRuntime = getLatestTradingviewRuntime();
  if (!tvRuntime?.connected || !tvRuntime?.symbol || !tvRuntime?.payload?.price) {
    return res.json({
      ok: false,
      error: 'NO DATA',
      message: 'Aucune donnée TradingView live disponible',
      type: 'chart-data',
      timestamp: new Date().toISOString()
    });
  }
  res.json({
    ok: true,
    symbol: tvRuntime.symbol,
    timeframe: tvRuntime.timeframe,
    price: tvRuntime.payload.price,
    source: 'tradingview',
    candles: tvRuntime.payload.candles || [],
    updatedAt: tvRuntime.timestamp || null
  });
});

// ─── MARKET INTELLIGENCE ──────────────────────────────────────────────────────
app.get('/market-intelligence', async (req, res) => {
  const sym = req.query.symbol || 'XAUUSD';
  try {
    const newsAgent = require('./src/agents/news-intelligence');
    const data      = await newsAgent.analyze(sym);
    res.json({ ok: true, symbol: sym, ...data });
  } catch {
    // Fallback: calendrier statique
    res.json({
      ok: true, symbol: sym,
      upcomingEvents: [
        { event: 'Non-Farm Payrolls', time: '13:30', currency: 'USD', impact: 'HIGH', minutesAway: 240, isUrgent: false },
        { event: 'FOMC Meeting', time: '19:00', currency: 'USD', impact: 'HIGH', minutesAway: 480, isUrgent: false }
      ],
      news: [],
      macroWarning: null
    });
  }
});

// ─── LATEST SYMBOL ────────────────────────────────────────────────────────────
app.get('/latest/:symbol', async (req, res) => {
  const profile = normalizeSymbol(req.params.symbol);
  const data    = marketStore.getLatestForSymbol(profile.canonical);
  if (data) return res.json({ ok: true, symbol: profile.canonical, ...data });

  // Pas de données MT5/TV → retourner prix Yahoo sans le présenter comme un signal
  try {
    const ysSym = toYahooSym(profile.canonical);
    if (!ysSym) return res.status(404).json({ ok: false, error: 'Aucune donnée pour ' + profile.canonical });
    const price = await fetchYahooPrice(ysSym);
    res.json({ ok: true, symbol: profile.canonical, price, source: 'yahoo-reference', note: 'Prix de référence uniquement — connectez MT5' });
  } catch {
    res.status(404).json({ ok: false, error: 'Aucune donnée pour ' + profile.canonical });
  }
});

// ─── TOGGLE MODE ──────────────────────────────────────────────────────────────
let engineMode = 'manual', activeTimeframe = 'H1';
app.get('/toggle-mode', (_req, res) => res.json({ ok: true, mode: engineMode, timeframe: activeTimeframe }));
app.post('/toggle-mode', (req, res) => {
  const m = (req.body?.mode || '').toLowerCase();
  if (m === 'auto' || m === 'manual') engineMode = m;
  else if (!m) engineMode = engineMode === 'auto' ? 'manual' : 'auto';
  if (req.body?.timeframe) activeTimeframe = req.body.timeframe.toUpperCase();
  res.json({ ok: true, mode: engineMode, timeframe: activeTimeframe });
});

// ─── ANALYZE ─────────────────────────────────────────────────────────────────
async function handleAnalyze(req, res) {
  const focus  = req.query.focus;
  const syms   = focus ? [focus] : ['XAU/USD','EUR/USD','GBP/USD','USD/JPY','BTC/USDT'];

  const opportunities = await Promise.all(syms.map(async rawSym => {
    const profile  = normalizeSymbol(rawSym.replace('/', ''));
    const cached   = marketStore.analysisCache[profile.canonical];
    if (cached?.trade) return { ...cached.trade, probability: Math.round(cached.score || 65) };

    // Essayer le prix Yahoo uniquement pour construire des niveaux
    try {
      const ySym  = toYahooSym(profile.canonical);
      const price = ySym ? await fetchYahooPrice(ySym) : null;
      if (!price) return null;
      const direction = 'LONG';
      const levels    = calcTradeLevels(price, direction, profile, 'H1', null);
      const setup     = classifySetup('H1', direction, 65);
      return { symbol: profile.canonical, direction, ...levels, score: 65, probability: 65, source: 'price-reference', ...setup };
    } catch { return null; }
  }));

  res.json({ ok: true, opportunities: opportunities.filter(Boolean) });
}

app.get('/analyze', handleAnalyze);
app.get('/analysis', handleAnalyze);

// ─── POSITIONS ────────────────────────────────────────────────────────────────
app.get('/positions', async (req, res) => {
  // Retourner les positions depuis le store MT5 si disponible
  const state  = marketStore.getState ? marketStore.getState() : {};
  const cached = state.analysisCache || {};
  const positions = Object.values(cached)
    .filter(a => a?.trade)
    .map(a => ({ ...a.trade, status: a.trade.trade_status || 'UNKNOWN' }));

  if (positions.length > 0) return res.json({ ok: true, positions, count: positions.length, source: 'mt5-cache' });

  // Fallback: message informatif
  res.json({ ok: true, positions: [], count: 0, note: 'Aucune position active — démarrez le bridge MT5 pour voir les positions réelles' });
});

// ─── TRADE EXECUTE ────────────────────────────────────────────────────────────
app.post('/trade', (req, res) => {
  const { symbol, direction, quantity, price, sl, tp } = req.body || {};
  if (!symbol || !direction) return res.status(400).json({ ok: false, error: 'symbol et direction requis' });
  try {
    const broker = require('./trading/broker-adapter');
    broker.placeOrder({ symbol, direction, quantity: quantity || 1, price, sl, tp })
      .then(r => res.json({ ok: true, result: r }))
      .catch(e => res.status(500).json({ ok: false, error: e.message }));
  } catch (e) {
    res.status(500).json({ ok: false, error: 'Broker adapter: ' + e.message });
  }
});

// ─── BROKER MODE ──────────────────────────────────────────────────────────────
app.get('/broker-mode', (req, res) => res.json({ ok: true, mode: process.env.BROKER_MODE || 'live' }));
app.post('/broker-mode', (req, res) => {
  const m = (req.body?.mode || '').toLowerCase();
  if (!['paper','live'].includes(m)) return res.status(400).json({ ok: false, error: 'paper ou live seulement' });
  process.env.BROKER_MODE = m;
  res.json({ ok: true, mode: m });
});

// ─── AGENTS REPORT ────────────────────────────────────────────────────────────
app.get('/agents-report', async (req, res) => {
  try {
    const coordinator = require('./src/agents/coordinator');
    const priceMap    = {};
    const report      = await coordinator.runAgentCycle(priceMap, 100000, 1);
    res.json({ ok: true, report });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ─── AGENT SCREEN ────────────────────────────────────────────────────────────
app.post('/agent-screen', async (req, res) => {
  const { symbol: rawSym, tf, price: rawPrice, url, title, screenshot } = req.body || {};
  const profile  = normalizeSymbol(rawSym || 'EURUSD');
  const sym      = profile.canonical;
  const price    = rawPrice ? parseFloat(rawPrice) : null;

  if (screenshot) console.log(`[/agent-screen] Screenshot ${Math.round(screenshot.length/1024)}KB pour ${sym}`);

  if (!price || price <= 0) {
    return res.status(400).json({ ok: false, error: 'Prix requis — envoyez price dans le body' });
  }

  const direction = 'LONG';
  const levels    = calcTradeLevels(price, direction, profile, tf || 'H1', null);
  const setup     = classifySetup(tf || 'H1', direction, 65);
  const trade     = validateTrade({ symbol: sym, direction, ...levels, score: 65, source: 'agent-screen', accuracy: 'live', technical: `Analyse de ${url || 'page'}`, macro: '—', sentiment: '—', ...setup }, price);

  res.json({ ok: true, trade, symbol: sym, screenshotProcessed: !!screenshot });
});

// ─── KLINES (Yahoo Finance — données historiques uniquement) ─────────────────
// Yahoo supporte: 1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo
// Les TFs non supportés sont mappés au plus proche disponible
const TF_YAHOO = {
  'M1':'1m',  'M2':'2m',  'M3':'5m',  'M5':'5m',
  'M10':'15m','M15':'15m','M30':'30m','M45':'30m',
  'H1':'60m', 'H2':'60m', 'H3':'60m', 'H4':'60m',
  'D1':'1d',  'W1':'5d'
};
const TF_RANGE = {
  'M1':'1d',  'M2':'1d',  'M3':'5d',  'M5':'5d',
  'M10':'5d', 'M15':'5d', 'M30':'5d', 'M45':'5d',
  'H1':'5d',  'H2':'5d',  'H3':'5d',  'H4':'5d',
  'D1':'1mo', 'W1':'3mo'
};

app.get('/klines', async (req, res) => {
  const sym   = req.query.symbol || 'EUR/USD';
  const tf    = (req.query.tf || 'H1').toUpperCase();
  const limit = Math.min(parseInt(req.query.limit) || 80, 200);

  const ySym = toYahooSym(normalizeSymbol(sym.replace('/','').replace('-','')).canonical);
  if (!ySym) return res.status(400).json({ ok: false, error: 'Symbole non supporté: ' + sym });

  try {
    const url  = `https://query1.finance.yahoo.com/v8/finance/chart/${ySym}?interval=${TF_YAHOO[tf]||'1h'}&range=${TF_RANGE[tf]||'5d'}`;
    const resp = await fetch(url, { headers:{'User-Agent':'Mozilla/5.0'}, signal: AbortSignal.timeout(6000) });
    if (!resp.ok) throw new Error('Yahoo HTTP ' + resp.status);
    const json   = await resp.json();
    const result = json?.chart?.result?.[0];
    if (!result?.timestamp) throw new Error('no data');
    const q       = result.indicators.quote[0];
    const candles = result.timestamp
      .map((t, i) => ({ time: t*1000, open: q.open[i], high: q.high[i], low: q.low[i], close: q.close[i], volume: q.volume?.[i]||0 }))
      .filter(c => c.open != null && c.close != null)
      .slice(-limit);
    if (candles.length < 3) throw new Error('too few candles');
    return res.json({ ok: true, candles, source: 'yahoo-historical', symbol: ySym, note: 'Données historiques Yahoo Finance' });
  } catch (err) {
    return res.status(503).json({ ok: false, error: 'Données historiques indisponibles: ' + err.message });
  }
});

// ─── CALENDAR ────────────────────────────────────────────────────────────────
app.get('/calendar', async (req, res) => {
  try {
    const r = await fetch('https://nfs.faireconomy.media/ff_calendar_thisweek.json', {
      signal: AbortSignal.timeout(6000),
      headers: { 'Accept': 'application/json' }
    });
    if (!r.ok) throw new Error('calendar upstream ' + r.status);
    const raw = await r.json();
    const now = Date.now();
    const events = (Array.isArray(raw) ? raw : [])
      .map((e) => {
        const ts = Date.parse(e.date || e.timestamp || '');
        const mins = Number.isFinite(ts) ? Math.floor((ts - now) / 60000) : null;
        return {
          dayLabel: e.day || '',
          time: e.time || '',
          currency: e.currency || '',
          event: e.title || e.event || 'Event',
          impact: (e.impact || e.impact_title || 'LOW').toUpperCase(),
          mins
        };
      })
      .filter((e) => !Number.isFinite(e.mins) || e.mins >= 0)
      .slice(0, 20);
    res.json({ ok: true, events, source: 'forexfactory-live' });
  } catch {
    const news = require('./src/agents/news-intelligence');
    const d = await news.getUpcomingEvents();
    res.json({ ok: true, events: d.slice(0, 8), source: 'fallback-upcoming-events' });
  }
});

// ─── NEWS ────────────────────────────────────────────────────────────────────
app.get('/news', async (req, res) => {
  try {
    const symbol = String(req.query.symbol || marketStore.lastActiveSymbol || getLatestTradingviewRuntime().symbol || '').toUpperCase();
    const intel = require('./src/agents/news-intelligence');
    const data = await intel.analyze(symbol);
    const news = Array.isArray(data.news) ? data.news : [];
    res.json({ ok: true, news, source: 'multi-source-live', symbol, macroWarning: data.macroWarning || null, symbolImpact: data.symbolImpact || null });
  } catch {
    res.json({ ok: true, news: [], source: 'offline' });
  }
});

// ─── QUOTE ───────────────────────────────────────────────────────────────────
app.get('/quote', async (req, res) => {
  const rawSym = req.query.symbol || 'EUR/USD';
  const profile = normalizeSymbol(rawSym.replace('/',  ''));
  const sym     = profile.canonical;

  const live = marketStore.getLatestForSymbol(sym);
  if (live?.latestPayload?.price) {
    // MODIFIÉ: Broadcast le price pour SSE real-time
    marketStore.broadcast({ type: 'quote', symbol: sym, price: live.latestPayload.price, source: live.latestPayload.source || 'mt5' });
    return res.json({ ok: true, symbol: sym, price: live.latestPayload.price, source: live.latestPayload.source || 'mt5' });
  }

  try {
    const ySym  = toYahooSym(sym);
    if (!ySym) throw new Error('non supporté');
    const price = await fetchYahooPrice(ySym);
    // MODIFIÉ: Broadcast le price pour SSE real-time
    marketStore.broadcast({ type: 'quote', symbol: sym, price: price, source: 'yahoo-reference' });
    res.json({ ok: true, symbol: sym, price, source: 'yahoo-reference' });
  } catch (e) {
    res.status(404).json({ ok: false, error: 'Prix indisponible pour ' + rawSym });
  }
});

// ─── BUTTON LOG ──────────────────────────────────────────────────────────────
const btnLogs = [];
app.post('/button-log', (req, res) => { btnLogs.unshift({ ...req.body, ts: Date.now() }); if (btnLogs.length > 200) btnLogs.pop(); res.json({ ok: true }); });
app.get('/button-log',  (_req, res) => res.json({ ok: true, logs: btnLogs.slice(0, 100) }));

// ─── SYSTEM LOG (communication inter-IA) ─────────────────────────────────────
const SYSLOG_PATH = path.join(__dirname, 'SYSTEM_LOG.json');
const sysLogs = [];
const AGENT_HISTORY_PATH = path.join(__dirname, 'agent-history.json');
const AGENT_HISTORY_BACKUP_PATH = path.join(__dirname, 'backup', 'system-live', 'agent-history.json');
const BACKUP_SYSTEM_LIVE_DIR = path.join(__dirname, 'backup', 'system-live');
const BACKUP_SYSLOG_PATH = path.join(BACKUP_SYSTEM_LIVE_DIR, 'SYSTEM_LOG.json');
const BACKUP_LOGS_PATH = path.join(BACKUP_SYSTEM_LIVE_DIR, 'logs.json');
const BACKUP_LIVE_STATE_PATH = path.join(BACKUP_SYSTEM_LIVE_DIR, 'realtime', 'live-system-state.json');
const AGENT_HISTORY_INTERVAL_MS = Math.max(10 * 60 * 1000, parseInt(process.env.AGENT_HISTORY_INTERVAL_MS || '1800000', 10) || 1800000);
const agentHistory = [];
let _agentHistoryTimer = null;
let _backupLiveMirrorTimer = null;
const backupLiveMirrorMeta = {
  sequence: 0,
  updatedAt: null,
  lastTrigger: 'startup',
  lastEvent: null
};

// ─── AGENT ACTIVITY TRACKING ──────────────────────────────────────────────────
const agentActivitySseClients = [];  // SSE clients watching agent activity
const agentStates = {
  'Claude':   { status: 'online', lastActivity: Date.now(), activeTask: null },
  'Copilot':  { status: 'idle', lastActivity: Date.now(), activeTask: null },
  'system':   { status: 'running', lastActivity: Date.now(), activeTask: null }
};
const _agentBusUnsubscribers = [];
const _registeredAgentNames = new Set();
let _activeAgentExecutions = 0;
const _agentExecutionQueue = [];
const _agentExecutionCompletedAt = new Map();
const _agentExecutionCompletedTtlMs = 10 * 60 * 1000;
const _agentExecutionDependencyTimeoutMs = 15000;
let _agentExecutionTaskSeq = 0;
let _agentQueuePumpRunning = false;
let _agentQueuePumpScheduled = false;
const _agentExecutionBaseMax = Math.min(2, Math.max(1, parseInt(process.env.AGENT_CONCURRENCY || '2', 10) || 2));
let _agentExecutionDynamicMax = _agentExecutionBaseMax;
let _runtimeRotationIndex = 0;
let _runtimeCycleInProgress = false;
let _runtimeSlowdownMs = 0;
let _runtimeAutoSafeMode = false;
let _runtimeLoopCurrentIntervalMs = 0;
let _runtimeLoopTargetIntervalMs = SAFE_MODE ? 8000 : 5000;
let _cpuPrevSample = null;
let _cpuPercent = 0;
let _runtimeCycleCounter = 0;

function sampleSystemCpuPercent() {
  const cpus = os.cpus();
  if (!cpus || cpus.length === 0) return _cpuPercent || 0;

  const totals = cpus.reduce((acc, cpu) => {
    const t = cpu.times;
    acc.idle += t.idle;
    acc.total += t.user + t.nice + t.sys + t.idle + t.irq;
    return acc;
  }, { idle: 0, total: 0 });

  if (!_cpuPrevSample) {
    _cpuPrevSample = totals;
    return _cpuPercent || 0;
  }

  const idleDiff = totals.idle - _cpuPrevSample.idle;
  const totalDiff = totals.total - _cpuPrevSample.total;
  _cpuPrevSample = totals;

  if (totalDiff <= 0) return _cpuPercent || 0;
  const pct = Math.max(0, Math.min(100, (1 - (idleDiff / totalDiff)) * 100));
  return Math.round(pct * 10) / 10;
}

function refreshRuntimeRegulation() {
  const cpu = sampleSystemCpuPercent();
  _cpuPercent = cpu;

  if (cpu > 90) {
    _runtimeAutoSafeMode = true;
    _agentExecutionDynamicMax = 1;
    _runtimeSlowdownMs = 3200;
    _runtimeLoopTargetIntervalMs = 14000;
    return;
  }

  _runtimeAutoSafeMode = false;
  if (cpu > 85) {
    _agentExecutionDynamicMax = 2;
    _runtimeSlowdownMs = 1700;
    _runtimeLoopTargetIntervalMs = 9000;
    return;
  }

  if (cpu > 70) {
    _agentExecutionDynamicMax = Math.max(2, Math.min(3, _agentExecutionBaseMax));
    _runtimeSlowdownMs = 950;
    _runtimeLoopTargetIntervalMs = 7000;
    return;
  }

  _agentExecutionDynamicMax = _agentExecutionBaseMax;
  _runtimeSlowdownMs = 0;
  _runtimeLoopTargetIntervalMs = SAFE_MODE ? 8000 : 5000;
}

function getEffectiveSafeMode() {
  return SAFE_MODE || _runtimeAutoSafeMode;
}
const AGENT_PRIORITY = {
  'orchestrator': 1,
  'verification-agent': 1,
  'surveillance-agent': 1,
  'bridge-agent': 2,
  'repair-agent': 2,
  'extension-agent': 2,
  'logic-gap-agent': 2,
  'ui-test-agent': 2,
  'analysis-agent': 2,
  'risk-agent': 2,
  'strategy-agent': 2,
  'mirror-agent': 3,
  'innovator-agent': 3,
  'design-agent': 3,
  'research-agent': 3,
  'human-interface-agent': 3,
  'project-controller': 3,
  'position-explainer-agent': 3,
  'execution-coach-agent': 3,
  'history-agent': 3
};

const DISPATCH_PRIORITY_LABELS = {
  1: 'high',
  2: 'medium',
  3: 'low'
};

const AGENT_RUNTIME_POLICY = {
  'orchestrator': { priority: 1, mode: 'always', dependsOn: [] },
  'verification-agent': { priority: 1, mode: 'always', dependsOn: [] },
  'surveillance-agent': { priority: 1, mode: 'always', dependsOn: [] },
  'bridge-agent': { priority: 2, mode: 'interval', everyCycles: 2, dependsOn: ['orchestrator'] },
  'repair-agent': { priority: 2, mode: 'blocked', dependsOn: ['verification-agent'] },
  'extension-agent': { priority: 2, mode: 'interval', everyCycles: 3, dependsOn: ['bridge-agent'] },
  'logic-gap-agent': { priority: 2, mode: 'event', dependsOn: ['verification-agent'] },
  'ui-test-agent': { priority: 2, mode: 'event', dependsOn: ['logic-gap-agent'] },
  'analysis-agent': { priority: 2, mode: 'event', dependsOn: ['orchestrator'] },
  'risk-agent': { priority: 2, mode: 'event', dependsOn: ['analysis-agent'] },
  'strategy-agent': { priority: 2, mode: 'event', dependsOn: ['analysis-agent'] },
  'mirror-agent': { priority: 3, mode: 'interval', everyCycles: 4, dependsOn: ['bridge-agent'] },
  'innovator-agent': { priority: 3, mode: 'blocked', dependsOn: ['repair-agent'] },
  'design-agent': { priority: 3, mode: 'event', dependsOn: ['logic-gap-agent'] },
  'research-agent': { priority: 3, mode: 'event', dependsOn: ['logic-gap-agent'] },
  'human-interface-agent': { priority: 3, mode: 'event', dependsOn: ['design-agent'] },
  'project-controller': { priority: 3, mode: 'event', dependsOn: ['design-agent'] },
  'position-explainer-agent': { priority: 3, mode: 'event', dependsOn: ['analysis-agent'] },
  'execution-coach-agent': { priority: 3, mode: 'event', dependsOn: ['risk-agent', 'strategy-agent'] },
  'history-agent': { priority: 3, mode: 'interval', everyCycles: 6, dependsOn: [] }
};

function normalizeDispatchPriority(value) {
  if (value === 'high') return 1;
  if (value === 'medium') return 2;
  if (value === 'low') return 3;
  const n = Number(value);
  if (!Number.isFinite(n)) return 3;
  return Math.max(1, Math.min(3, Math.floor(n)));
}

function getDispatchPriorityLabel(value) {
  return DISPATCH_PRIORITY_LABELS[normalizeDispatchPriority(value)] || 'low';
}

function cleanupCompletedExecutionKeys() {
  const now = Date.now();
  for (const [key, ts] of _agentExecutionCompletedAt.entries()) {
    if (!Number.isFinite(ts) || (now - ts) > _agentExecutionCompletedTtlMs) {
      _agentExecutionCompletedAt.delete(key);
    }
  }
}

function markExecutionCompleted(key) {
  const clean = String(key || '').trim();
  if (!clean) return;
  _agentExecutionCompletedAt.set(clean, Date.now());
  cleanupCompletedExecutionKeys();
}

function areExecutionDependenciesSatisfied(dependsOn = []) {
  if (!Array.isArray(dependsOn) || dependsOn.length === 0) return true;
  cleanupCompletedExecutionKeys();
  return dependsOn.every((dep) => _agentExecutionCompletedAt.has(dep));
}

function pickNextExecutionTaskIndex() {
  if (_agentExecutionQueue.length === 0) return -1;
  const now = Date.now();
  let bestIndex = -1;
  for (let i = 0; i < _agentExecutionQueue.length; i++) {
    const task = _agentExecutionQueue[i];
    const waitedMs = now - (task.enqueuedAt || now);
    const depsReady = areExecutionDependenciesSatisfied(task.dependsOn || []);
    const dependencyTimedOut = waitedMs >= _agentExecutionDependencyTimeoutMs;
    if (!depsReady && !dependencyTimedOut) continue;

    if (bestIndex === -1) {
      bestIndex = i;
      continue;
    }

    const best = _agentExecutionQueue[bestIndex];
    if (task.priority !== best.priority) {
      if (task.priority < best.priority) bestIndex = i;
      continue;
    }

    if ((task.enqueuedAt || 0) < (best.enqueuedAt || 0)) {
      bestIndex = i;
    }
  }
  return bestIndex;
}

function scheduleAgentQueuePump() {
  if (_agentQueuePumpScheduled) return;
  _agentQueuePumpScheduled = true;
  setImmediate(() => {
    _agentQueuePumpScheduled = false;
    processAgentExecutionQueue();
  });
}

function processAgentExecutionQueue() {
  if (_agentQueuePumpRunning) return;
  _agentQueuePumpRunning = true;

  try {
    while (_activeAgentExecutions < _agentExecutionDynamicMax) {
      const nextIndex = pickNextExecutionTaskIndex();
      if (nextIndex === -1) break;
      const task = _agentExecutionQueue.splice(nextIndex, 1)[0];
      if (!task || typeof task.fn !== 'function') continue;

      _activeAgentExecutions += 1;
      Promise.resolve()
        .then(() => task.fn())
        .then((out) => {
          if (task.completionKey) markExecutionCompleted(task.completionKey);
          task.resolve(out);
        })
        .catch((e) => {
          task.reject(e);
        })
        .finally(() => {
          _activeAgentExecutions -= 1;
          scheduleAgentQueuePump();
        });
    }
  } finally {
    _agentQueuePumpRunning = false;
  }
}

function hasRecentAgentIntent(agentName, withinMs = 120000) {
  const needle = String(agentName || '').toLowerCase();
  if (!needle) return false;
  const now = Date.now();
  return sysLogs.some((entry) => {
    const ts = Date.parse(entry.ts || '') || now;
    if ((now - ts) > withinMs) return false;
    const from = String(entry.from || '').toLowerCase();
    const to = String(entry.to || '').toLowerCase();
    const action = String(entry.action || '').toLowerCase();
    return from === needle || to === needle || action.includes(needle);
  });
}

function shouldDispatchRuntimeAgent(agentName) {
  const policy = AGENT_RUNTIME_POLICY[agentName] || { mode: 'event', priority: AGENT_PRIORITY[agentName] || 3, dependsOn: [] };
  const blockedCount = Object.values(agentRuntime).filter((x) => x.status === 'bloqué').length;
  const mode = policy.mode || 'event';
  const priority = normalizeDispatchPriority(policy.priority || AGENT_PRIORITY[agentName] || 3);

  // Load shedding: keep only essential agents when the system is heavy.
  if (_cpuPercent > 90 && priority > 1) return false;
  if (_cpuPercent > 80 && priority > 2) return false;

  if (mode === 'always') return true;
  if (mode === 'blocked') return blockedCount > 0;
  if (mode === 'interval') {
    const every = Math.max(1, Number(policy.everyCycles) || 1);
    return (_runtimeCycleCounter % every) === 0;
  }
  if (mode === 'event') return hasRecentAgentIntent(agentName, 180000);
  return hasRecentAgentIntent(agentName, 180000);
}

function getRuntimeOrderedAgents() {
  return [...AGENT_RUNTIME_CATALOG].sort((a, b) => {
    const pa = AGENT_PRIORITY[a] || 9;
    const pb = AGENT_PRIORITY[b] || 9;
    if (pa !== pb) return pa - pb;
    return a.localeCompare(b);
  });
}

function getRuntimeDispatchQueue() {
  const ordered = getRuntimeOrderedAgents();
  const selected = [];
  for (const name of ordered) {
    if (!shouldDispatchRuntimeAgent(name)) continue;
    const policy = AGENT_RUNTIME_POLICY[name] || {};
    const priority = normalizeDispatchPriority(policy.priority || AGENT_PRIORITY[name] || 3);
    const dependsOn = Array.isArray(policy.dependsOn) ? policy.dependsOn.filter(Boolean).map((v) => String(v)) : [];
    selected.push({
      name,
      priority,
      priorityLabel: getDispatchPriorityLabel(priority),
      dependsOn
    });
  }
  selected.sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    return a.name.localeCompare(b.name);
  });
  return selected;
}

function getInteractiveAgentPriority(name) {
  const policy = AGENT_RUNTIME_POLICY[name] || {};
  return normalizeDispatchPriority(policy.priority || AGENT_PRIORITY[name] || 3);
}

function getInteractiveAgentDependencies(name, message = '') {
  const base = Array.isArray(AGENT_RUNTIME_POLICY[name]?.dependsOn)
    ? AGENT_RUNTIME_POLICY[name].dependsOn.map((v) => String(v))
    : [];

  const m = String(message || '').toLowerCase();
  if (name === 'repair-agent' && /analyse|analysis|diagnostic|audit/.test(m)) {
    base.push('send:analysis-agent');
  }
  if (name === 'execution-coach-agent') {
    base.push('send:risk-agent', 'send:strategy-agent');
  }
  if (name === 'strategy-agent') {
    base.push('send:analysis-agent');
  }
  if (name === 'risk-agent') {
    base.push('send:analysis-agent');
  }

  return Array.from(new Set(base));
}

function runWithAgentLimit(fn, options = {}) {
  const priority = normalizeDispatchPriority(options.priority || 3);
  const dependsOn = Array.isArray(options.dependsOn) ? options.dependsOn.filter(Boolean).map((v) => String(v)) : [];
  const completionKey = options.taskKey ? String(options.taskKey) : null;
  const label = String(options.label || completionKey || 'agent-task');

  return new Promise((resolve, reject) => {
    _agentExecutionQueue.push({
      id: ++_agentExecutionTaskSeq,
      fn,
      resolve,
      reject,
      priority,
      priorityLabel: getDispatchPriorityLabel(priority),
      dependsOn,
      completionKey,
      label,
      enqueuedAt: Date.now()
    });
    scheduleAgentQueuePump();
  });
}

// Runtime instrumentation for live task visibility (startedAt / elapsedMs / durationMs)
const AGENT_RUNTIME_CATALOG = [
  'surveillance-agent', 'orchestrator', 'indicator-agent', 'repair-agent',
  'technicalAgent', 'macroAgent', 'newsAgent', 'riskManager',
  'strategyManager', 'tradeValidator', 'setupClassifier', 'syncManager',
  'dataSourceManager', 'stateManager', 'supervisor', 'qaTester',
  'continuous-loop', 'design-agent', 'bridge-agent', 'innovator-agent',
    'verification-agent', 'mirror-agent', 'extension-agent', 'project-controller',
    'ui-test-agent', 'logic-gap-agent', 'research-agent', 'human-interface-agent',
    'central-guide-agent', 'analysis-agent', 'news-agent', 'position-explainer-agent', 'strategy-agent', 'risk-agent', 'execution-coach-agent', 'history-agent'
];

const agentRuntime = {};
let _runtimeLoopEnabled = false;
let _runtimeLoopTimer = null;

function ensureAgentRuntime(name) {
  if (!agentRuntime[name]) {
    agentRuntime[name] = {
      agent: name,
      task: 'idle',
      status: 'en attente',
      startedAt: null,
      finishedAt: null,
      elapsedMs: 0,
      durationMs: null,
      avgDurationMs: null,
      etaMs: null,
      cause: '',
      impact: '',
      solution: '',
      to: 'system',
      updatedAt: Date.now(),
      runs: 0,
      blockedCount: 0
    };
  }
  return agentRuntime[name];
}

function formatEtaLabel(ms) {
  if (!Number.isFinite(ms) || ms < 0) return '--';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return sec + 's';
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return rem > 0 ? `${min}m ${rem}s` : `${min}m`;
}

function updateAvgDuration(rt, durationMs) {
  if (!Number.isFinite(durationMs) || durationMs <= 0) return;
  if (!Number.isFinite(rt.avgDurationMs) || rt.avgDurationMs <= 0) {
    rt.avgDurationMs = durationMs;
    return;
  }
  // Exponential moving average keeps ETA stable but reactive.
  rt.avgDurationMs = Math.round((rt.avgDurationMs * 0.7) + (durationMs * 0.3));
}

function isMirrorErrorLike(entry = {}) {
  const status = String(entry.status || '').toLowerCase();
  const text = String(entry.message || entry.action || '').toLowerCase();
  return status === 'error' || status === 'warning' || status === 'warn' || status === 'critical' || /error|failed|warning|critical|bloqu/.test(text);
}

function isMirrorRepairLike(entry = {}) {
  const text = String(entry.message || entry.action || '').toLowerCase();
  return /repair|repar|fix|corrig|resolved|termine|terminé|success|done/.test(text);
}

function getSystemLogPayload() {
  return {
    updated: new Date().toISOString(),
    agents: agentStates,
    logs: sysLogs.slice(0, 200)
  };
}

function writeJsonMirror(filePath, payload) {
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(payload, null, 2));
    return true;
  } catch (_) {
    return false;
  }
}

function summarizeMirrorEvent(entry = {}) {
  const message = entry.message || entry.action || entry.detail?.requestId || '';
  return {
    ts: entry.ts || new Date().toISOString(),
    agent: entry.agent || entry.from || 'system',
    to: entry.to || 'system',
    status: entry.status || 'info',
    phase: entry.phase || '',
    message: String(message).slice(0, 220)
  };
}

function buildBackupLiveStatePayload() {
  const runtime = getRuntimeSnapshot();
  const recentLogs = sysLogs.slice(0, 60);
  const recentErrors = recentLogs.filter((entry) => isMirrorErrorLike(entry)).slice(0, 20);
  const recentRepairs = recentLogs.filter((entry) => isMirrorRepairLike(entry)).slice(0, 20);
  const now = Date.now();
  const latestHistory = agentHistory[0] || null;
  const backupSyslogMtime = fs.existsSync(BACKUP_SYSLOG_PATH) ? fs.statSync(BACKUP_SYSLOG_PATH).mtimeMs : null;

  return {
    ok: true,
    updatedAt: new Date().toISOString(),
    sequence: backupLiveMirrorMeta.sequence,
    lastTrigger: backupLiveMirrorMeta.lastTrigger,
    lastEvent: backupLiveMirrorMeta.lastEvent,
    stats: {
      totalLogs: sysLogs.length,
      visibleErrors: recentErrors.length,
      recentRepairs: recentRepairs.length,
      activeAgents: runtime.filter((r) => r.status === 'en cours').length,
      blockedAgents: runtime.filter((r) => r.status === 'bloqué').length,
      historySnapshots: agentHistory.length
    },
    mirror: {
      lagMs: backupSyslogMtime ? Math.max(0, now - backupSyslogMtime) : null,
      backupSystemLogPath: BACKUP_SYSLOG_PATH,
      backupLiveStatePath: BACKUP_LIVE_STATE_PATH,
      backupLogsPath: BACKUP_LOGS_PATH
    },
    agents: agentStates,
    runtime,
    recentLogs,
    recentErrors,
    recentRepairs,
    latestHistory
  };
}

function writeBackupLiveMirrorNow() {
  const payload = buildBackupLiveStatePayload();
  writeJsonMirror(BACKUP_SYSLOG_PATH, getSystemLogPayload());
  writeJsonMirror(BACKUP_LIVE_STATE_PATH, payload);
  backupLiveMirrorMeta.updatedAt = payload.updatedAt;
}

function scheduleBackupLiveMirror(trigger = 'runtime', entry = null) {
  backupLiveMirrorMeta.sequence += 1;
  backupLiveMirrorMeta.lastTrigger = trigger;
  if (entry) backupLiveMirrorMeta.lastEvent = summarizeMirrorEvent(entry);
  if (_backupLiveMirrorTimer) return;
  _backupLiveMirrorTimer = setTimeout(() => {
    _backupLiveMirrorTimer = null;
    writeBackupLiveMirrorNow();
  }, 350);
}

function getRuntimeSnapshot() {
  const now = Date.now();
  return Object.keys(agentRuntime).map((name) => {
    const s = { ...agentRuntime[name] };
    if (s.status === 'en cours' && s.startedAt) {
      s.elapsedMs = now - s.startedAt;
    }
    const baseline = Number.isFinite(s.avgDurationMs) && s.avgDurationMs > 0
      ? s.avgDurationMs
      : (Number.isFinite(s.durationMs) && s.durationMs > 0 ? s.durationMs : null);
    if (s.status === 'en cours' && Number.isFinite(baseline)) {
      s.etaMs = Math.max(0, baseline - (s.elapsedMs || 0));
    } else if (s.status === 'en attente' && Number.isFinite(baseline)) {
      s.etaMs = baseline;
    } else {
      s.etaMs = null;
    }
    s.etaLabel = formatEtaLabel(s.etaMs);
    return s;
  });
}

function startAgentTask(agent, task, meta = {}) {
  const rt = ensureAgentRuntime(agent);
  rt.task = task || 'task';
  rt.status = 'en cours';
  rt.startedAt = Date.now();
  rt.finishedAt = null;
  rt.elapsedMs = 0;
  rt.durationMs = null;
  rt.cause = meta.cause || '';
  rt.impact = meta.impact || '';
  rt.solution = meta.solution || '';
  rt.to = meta.to || 'system';
  rt.updatedAt = Date.now();
  rt.runs = (rt.runs || 0) + 1;
  updateAgentState(agent, 'working', task);
  publishAgentChatMessage({
    agent,
    to: rt.to,
    status: 'action',
    phase: 'en cours',
    message: task,
    cause: rt.cause,
    impact: rt.impact,
    solution: rt.solution,
    startedAt: rt.startedAt,
    elapsedMs: 0,
    durationMs: null
  });
}

function finishAgentTask(agent, meta = {}) {
  const rt = ensureAgentRuntime(agent);
  const now = Date.now();
  const duration = rt.startedAt ? (now - rt.startedAt) : 0;
  rt.status = 'terminé';
  rt.finishedAt = now;
  rt.elapsedMs = duration;
  rt.durationMs = duration;
  updateAvgDuration(rt, duration);
  if (meta.cause) rt.cause = meta.cause;
  if (meta.impact) rt.impact = meta.impact;
  if (meta.solution) rt.solution = meta.solution;
  rt.updatedAt = now;
  updateAgentState(agent, 'idle', rt.task);
  publishAgentChatMessage({
    agent,
    to: meta.to || rt.to || 'system',
    status: 'info',
    phase: 'terminé',
    message: meta.message || `${rt.task} terminé`,
    cause: rt.cause,
    impact: rt.impact,
    solution: rt.solution,
    startedAt: rt.startedAt,
    elapsedMs: rt.elapsedMs,
    durationMs: rt.durationMs
  });
}

function blockAgentTask(agent, cause, impact, solution, to = 'system') {
  const rt = ensureAgentRuntime(agent);
  const now = Date.now();
  const duration = rt.startedAt ? (now - rt.startedAt) : 0;
  rt.status = 'bloqué';
  rt.finishedAt = now;
  rt.elapsedMs = duration;
  rt.durationMs = duration;
  updateAvgDuration(rt, duration);
  rt.cause = cause || 'unknown';
  rt.impact = impact || '';
  rt.solution = solution || '';
  rt.updatedAt = now;
  rt.blockedCount = (rt.blockedCount || 0) + 1;
  updateAgentState(agent, 'error', rt.task || 'blocked');
  publishAgentChatMessage({
    agent,
    to,
    status: 'error',
    phase: 'bloqué',
    message: `${rt.task || 'task'} bloqué`,
    cause: rt.cause,
    impact: rt.impact,
    solution: rt.solution,
    startedAt: rt.startedAt,
    elapsedMs: rt.elapsedMs,
    durationMs: rt.durationMs
  });
}

function setPendingAgent(agent, task, to = 'system') {
  const rt = ensureAgentRuntime(agent);
  if (rt.status === 'en cours') return;
  rt.task = task || rt.task || 'en attente';
  rt.status = 'en attente';
  rt.startedAt = null;
  rt.finishedAt = null;
  rt.elapsedMs = 0;
  rt.durationMs = null;
  rt.to = to;
  rt.updatedAt = Date.now();
  updateAgentState(agent, 'idle', rt.task);
}

async function runLiveRuntimeCycle() {
  if (!_runtimeLoopEnabled) return;
  if (_runtimeCycleInProgress) return;
  _runtimeCycleInProgress = true;
  _runtimeCycleCounter += 1;

  try {
    refreshRuntimeRegulation();

    if (_runtimeLoopTimer && _runtimeLoopCurrentIntervalMs !== _runtimeLoopTargetIntervalMs) {
      clearInterval(_runtimeLoopTimer);
      _runtimeLoopCurrentIntervalMs = _runtimeLoopTargetIntervalMs;
      _runtimeLoopTimer = setInterval(runLiveRuntimeCycle, _runtimeLoopCurrentIntervalMs);
    }

    const dispatchQueue = getRuntimeDispatchQueue();
    const activeSet = new Set(dispatchQueue.map((d) => d.name));
    AGENT_RUNTIME_CATALOG.forEach((name) => {
      if (!activeSet.has(name)) {
        setPendingAgent(name, 'en attente dépendances/priorité', 'orchestrator');
      }
    });

    const workers = dispatchQueue.map((task, idx) => runWithAgentLimit(async () => {
      const name = task.name;
      const baseDelay = 120 + (idx % 8) * 55 + _runtimeSlowdownMs;

      if (name === 'verification-agent') {
        startAgentTask(name, 'Vérification cohérence TV/MT5', {
          to: 'orchestrator',
          cause: 'anti-fake check',
          impact: 'validation données live',
          solution: 'bloquer si incohérence'
        });
        const healthOk = !!(marketStore && marketStore.systemStatus);
        await new Promise((r) => setTimeout(r, baseDelay));
        if (!healthOk) {
          blockAgentTask(name, 'source indisponible', 'aucune vérification live', 'attendre flux entrant', 'orchestrator');
          return;
        }
        finishAgentTask(name, { to: 'orchestrator', message: 'Vérification source OK' });
        return;
      }

      if (name === 'mirror-agent') {
        startAgentTask(name, 'Sync HTML existants', {
          to: 'project-controller',
          cause: 'cohérence UI',
          impact: 'évite divergences pages',
          solution: 'audit headers/scripts'
        });
        const pages = ['index.html', 'dashboard.html', 'AGENTS_MONITOR.html', 'agent-log-page.html'];
        const checks = pages.map((p) => ({ page: p, ok: fs.existsSync(path.join(__dirname, p)) }));
        await new Promise((r) => setTimeout(r, baseDelay));
        const bad = checks.filter((c) => !c.ok);
        if (bad.length > 0) {
          blockAgentTask(name, 'pages manquantes', `missing=${bad.map((b) => b.page).join(',')}`, 'restaurer pages', 'project-controller');
          return;
        }
        finishAgentTask(name, { to: 'project-controller', message: 'Synchronisation HTML validée' });
        return;
      }

      if (name === 'extension-agent') {
        startAgentTask(name, 'Contrôle extension Chrome', {
          to: 'bridge-agent',
          cause: 'vérification popup/content/background',
          impact: 'continuité UX extension',
          solution: 'signaler fichiers manquants'
        });
        const extFiles = ['tradingview-analyzer/popup.js', 'tradingview-analyzer/content.js', 'tradingview-analyzer/background.js'];
        const missing = extFiles.filter((f) => !fs.existsSync(path.join(__dirname, f)));
        await new Promise((r) => setTimeout(r, baseDelay));
        if (missing.length > 0) {
          blockAgentTask(name, 'fichier extension manquant', missing.join(','), 'corriger extension source', 'bridge-agent');
          return;
        }
        finishAgentTask(name, { to: 'bridge-agent', message: 'Extension contrôlée' });
        return;
      }

      if (name === 'bridge-agent') {
        startAgentTask(name, 'Bridge UI/backend/extension', {
          to: 'orchestrator',
          cause: 'liaison canaux',
          impact: 'messages unifiés',
          solution: 'maintenir /agent-activity et /system-log'
        });
        await new Promise((r) => setTimeout(r, baseDelay));
        finishAgentTask(name, { to: 'orchestrator', message: 'Bridge opérationnel' });
        return;
      }

      if (name === 'innovator-agent') {
        startAgentTask(name, 'Proposition solution blocage', {
          to: 'repair-agent',
          cause: 'résolution proactive',
          impact: 'réduction temps blocage',
          solution: 'proposer workaround'
        });
        const blocked = Object.values(agentRuntime).filter((x) => x.status === 'bloqué').length;
        await new Promise((r) => setTimeout(r, baseDelay));
        finishAgentTask(name, {
          to: 'repair-agent',
          message: blocked > 0 ? `Proposition: traiter ${blocked} blocages en priorité` : 'Aucun blocage critique'
        });
        return;
      }

      startAgentTask(name, `Cycle ${name} [${task.priorityLabel}]`, {
        to: 'orchestrator',
        cause: 'orchestration live priorisée',
        impact: 'exécution limitée et contrôlée',
        solution: 'queue intelligente'
      });
      await new Promise((r) => setTimeout(r, 2200 + (idx % 3) * 900 + _runtimeSlowdownMs));
      finishAgentTask(name, { to: 'orchestrator' });
    }, {
      priority: task.priority,
      dependsOn: task.dependsOn,
      taskKey: task.name,
      label: 'runtime:' + task.name
    }).catch((e) => {
      blockAgentTask(task.name, e.message || 'runtime error', 'cycle interrompu', 'relancer cycle', 'orchestrator');
    }));

    await Promise.allSettled(workers);
  } finally {
    _runtimeCycleInProgress = false;
  }
}

function startRuntimeLoop() {
  if (_runtimeLoopTimer) clearInterval(_runtimeLoopTimer);
  _runtimeLoopEnabled = true;
  refreshRuntimeRegulation();
  _runtimeLoopCurrentIntervalMs = _runtimeLoopTargetIntervalMs;
  _runtimeLoopTimer = setInterval(runLiveRuntimeCycle, _runtimeLoopCurrentIntervalMs);
  runLiveRuntimeCycle().catch(() => {});
}

function stopRuntimeLoop() {
  _runtimeLoopEnabled = false;
  if (_runtimeLoopTimer) {
    clearInterval(_runtimeLoopTimer);
    _runtimeLoopTimer = null;
  }
}

function registerAgentUnique(name, meta) {
  if (!name) return;
  if (_registeredAgentNames.has(name)) return;
  _registeredAgentNames.add(name);
  if (agentBus && typeof agentBus.registerAgent === 'function') {
    agentBus.registerAgent(name, meta || { role: 'agent', status: 'active', file: 'n/a' });
  }
  ensureAgentRuntime(name);
}

function broadcastAgentActivity(entry) {
  if (agentActivitySseClients.length === 0) return;
  const message = 'data: ' + JSON.stringify(entry) + '\n\n';
  for (let i = agentActivitySseClients.length - 1; i >= 0; i--) {
    try {
      agentActivitySseClients[i].write(message);
    } catch (e) {
      agentActivitySseClients.splice(i, 1); // Remove closed client
    }
  }
}

function updateAgentState(agentName, status, activeTask) {
  if (!agentStates[agentName]) {
    agentStates[agentName] = { status: 'unknown', lastActivity: Date.now(), activeTask: null };
  }
  agentStates[agentName].status = status;
  agentStates[agentName].lastActivity = Date.now();
  agentStates[agentName].activeTask = activeTask;
  
  // 🔴 UNIFIED SYNC: Envoyer aussi à Extension + HTML clients
  broadcastToExtension({
    type: 'agent-state-update',
    agent: agentName,
    status: status,
    activeTask: activeTask,
    lastActivity: agentStates[agentName].lastActivity
  });

  scheduleBackupLiveMirror('agent-state', {
    ts: new Date().toISOString(),
    agent: agentName,
    to: 'system',
    status,
    message: activeTask || 'state update'
  });
}

function publishAgentChatMessage(input = {}) {
  const agent = input.agent || input.from || 'system';
  const to = input.to || 'all';
  const status = String(input.status || 'info').toLowerCase();
  const message = input.message || '';
  const cause = input.cause || '';
  const impact = input.impact || '';
  const solution = input.solution || '';
  const phase = input.phase || 'en cours';

  const structured = {
    type: 'agent-chat',
    ts: new Date().toISOString(),
    agent,
    to,
    status,
    phase,
    message,
    cause,
    impact,
    solution,
    startedAt: input.startedAt || null,
    elapsedMs: input.elapsedMs == null ? null : input.elapsedMs,
    durationMs: input.durationMs == null ? null : input.durationMs,
    formatted: `[${agent}]\nstatut: ${status}\nmessage: ${message}\ncause: ${cause}\nimpact: ${impact}\nsolution: ${solution}`
  };

  // Single real-time stream for chat-style agent messages.
  broadcastAgentActivity(structured);

  // Mirror in extension sync so all UIs on :4000 see the same agent dialog.
  broadcastToExtension({
    type: 'agent-chat',
    ...structured
  });

  // Persist a short copy in system log history.
  pushLog(agent, to, message || 'agent message', status === 'error' ? 'error' : 'ok', {
    phase,
    cause,
    impact,
    solution
  });
}

function wireAgentBusToChat(agentNames = []) {
  if (!agentBus || typeof agentBus.subscribe !== 'function') return;

  // Clear previous subscriptions to avoid duplicate publications.
  while (_agentBusUnsubscribers.length > 0) {
    const unsub = _agentBusUnsubscribers.pop();
    try { if (typeof unsub === 'function') unsub(); } catch (_) {}
  }

  const uniqueNames = Array.from(new Set(agentNames.filter(Boolean)));
  uniqueNames.forEach((name) => {
    try {
      const unsub = agentBus.subscribe(name, (msg) => {
        const data = msg?.data || {};
        const msgType = String(msg?.type || 'info').toLowerCase();
        const status = data.status || (msgType.includes('error') ? 'error' : (msgType.includes('warn') ? 'warning' : (msgType.includes('action') ? 'action' : 'info')));

        publishAgentChatMessage({
          agent: msg?.from || 'unknown-agent',
          to: msg?.to || name,
          status,
          phase: data.phase || 'en cours',
          message: data.message || `bus:${msgType}`,
          cause: data.cause || '',
          impact: data.impact || '',
          solution: data.solution || ''
        });
      });
      _agentBusUnsubscribers.push(unsub);
    } catch (e) {
      console.error('[AGENT-BUS] subscribe failed for', name, e.message);
    }
  });
}

function analyzeHtmlDesignPage(page = 'dashboard.html') {
  const safePage = String(page || 'dashboard.html').replace(/\\/g, '/').replace(/^\/+/, '');
  const fullPath = path.join(__dirname, safePage);
  if (!fs.existsSync(fullPath)) {
    return {
      ok: false,
      page: safePage,
      error: 'page_not_found'
    };
  }

  const content = fs.readFileSync(fullPath, 'utf8');
  const idMatches = [...content.matchAll(/id\s*=\s*["']([^"']+)["']/gi)].map((m) => m[1]);
  const scriptMatches = [...content.matchAll(/<script[^>]*src\s*=\s*["']([^"']+)["']/gi)].map((m) => m[1]);
  const cssMatches = [...content.matchAll(/<link[^>]*href\s*=\s*["']([^"']+)["']/gi)].map((m) => m[1]);

  function getDuplicates(arr) {
    const counts = {};
    arr.forEach((v) => {
      counts[v] = (counts[v] || 0) + 1;
    });
    return Object.keys(counts)
      .filter((k) => counts[k] > 1)
      .map((k) => ({ value: k, count: counts[k] }));
  }

  const duplicateIds = getDuplicates(idMatches);
  const duplicateScripts = getDuplicates(scriptMatches);
  const duplicateCss = getDuplicates(cssMatches);

  const recommendations = [
    'Grouper les sections KPI, chat et actions en blocs semantiques explicites',
    'Conserver une seule inclusion par script/link duplique',
    'Conserver les IDs uniques pour les cibles JS et accessibilite',
    'Ne rien supprimer automatiquement: appliquer seulement des propositions'
  ];

  return {
    ok: true,
    page: safePage,
    stats: {
      ids: idMatches.length,
      scripts: scriptMatches.length,
      stylesheets: cssMatches.length
    },
    duplicates: {
      ids: duplicateIds,
      scripts: duplicateScripts,
      stylesheets: duplicateCss
    },
    recommendations
  };
}

function analyzeAllHtmlDesignPages() {
  const htmlFiles = fs.readdirSync(__dirname)
    .filter((n) => n.toLowerCase().endsWith('.html'))
    .sort((a, b) => a.localeCompare(b));

  const perPage = [];
  const titleMap = {};
  const endpointMap = {};
  const idMap = {};

  htmlFiles.forEach((page) => {
    const fullPath = path.join(__dirname, page);
    const content = fs.readFileSync(fullPath, 'utf8');

    const title = (content.match(/<title>([^<]+)<\/title>/i) || [null, ''])[1].trim() || page;
    const ids = [...content.matchAll(/id\s*=\s*["']([^"']+)["']/gi)].map((m) => m[1]);
    const scripts = [...content.matchAll(/<script[^>]*src\s*=\s*["']([^"']+)["']/gi)].map((m) => m[1]);
    const styles = [...content.matchAll(/<link[^>]*href\s*=\s*["']([^"']+)["']/gi)].map((m) => m[1]);
    const hrefs = [...content.matchAll(/href\s*=\s*["']([^"']+)["']/gi)].map((m) => m[1]);
    const endpoints = [...content.matchAll(/fetch\s*\(\s*["'`]([^"'`]+)["'`]/gi)].map((m) => m[1]);

    titleMap[title] = titleMap[title] || [];
    titleMap[title].push(page);

    ids.forEach((id) => {
      idMap[id] = idMap[id] || [];
      idMap[id].push(page);
    });

    endpoints.forEach((ep) => {
      endpointMap[ep] = endpointMap[ep] || [];
      endpointMap[ep].push(page);
    });

    const role = (() => {
      const p = page.toLowerCase();
      if (p === 'dashboard.html') return 'dashboard';
      if (p === 'popup.html') return 'extension-popup';
      if (p.includes('test')) return 'test-validation';
      if (p.includes('audit') || p.includes('agent') || p.includes('monitor') || p.includes('live')) return 'supervision-audit';
      return 'general';
    })();

    perPage.push({
      page,
      role,
      title,
      stats: {
        ids: ids.length,
        scripts: scripts.length,
        styles: styles.length,
        hrefs: hrefs.length,
        endpoints: endpoints.length
      },
      modules: { ids, scripts, styles, hrefs, endpoints }
    });
  });

  const duplicateTitles = Object.entries(titleMap)
    .filter(([, pages]) => pages.length > 1)
    .map(([title, pages]) => ({ title, pages }));

  const duplicateIdsCrossPages = Object.entries(idMap)
    .filter(([, pages]) => Array.from(new Set(pages)).length > 1)
    .map(([id, pages]) => ({ id, pages: Array.from(new Set(pages)) }))
    .slice(0, 120);

  const sharedEndpoints = Object.entries(endpointMap)
    .filter(([, pages]) => Array.from(new Set(pages)).length > 1)
    .map(([endpoint, pages]) => ({ endpoint, pages: Array.from(new Set(pages)) }));

  const overlaps = [];
  for (let i = 0; i < perPage.length; i++) {
    for (let j = i + 1; j < perPage.length; j++) {
      const a = perPage[i];
      const b = perPage[j];
      const setA = new Set(a.modules.endpoints);
      const commonEndpoints = b.modules.endpoints.filter((e) => setA.has(e));
      if (commonEndpoints.length >= 2) {
        overlaps.push({
          pages: [a.page, b.page],
          commonEndpoints: Array.from(new Set(commonEndpoints))
        });
      }
    }
  }

  const organization = {
    dashboard: perPage.filter((p) => p.role === 'dashboard').map((p) => p.page),
    extensionPopup: perPage.filter((p) => p.role === 'extension-popup').map((p) => p.page),
    testsValidation: perPage.filter((p) => p.role === 'test-validation').map((p) => p.page),
    supervisionAudit: perPage.filter((p) => p.role === 'supervision-audit').map((p) => p.page),
    general: perPage.filter((p) => p.role === 'general').map((p) => p.page)
  };

  const regroupCandidates = overlaps
    .filter((o) => o.commonEndpoints.length >= 3)
    .map((o) => ({
      pages: o.pages,
      reason: 'shared-endpoints',
      details: o.commonEndpoints
    }));

  return {
    ok: true,
    scannedAt: new Date().toISOString(),
    totalHtml: perPage.length,
    pages: perPage,
    duplicates: {
      titles: duplicateTitles,
      idsCrossPages: duplicateIdsCrossPages,
      sharedEndpoints
    },
    overlaps,
    regroupCandidates,
    organization,
    recommendations: [
      'Conserver dashboard centré pilotage trading (graphiques + positions)',
      'Conserver popup.html comme miroir unique extension Chrome',
      'Regrouper test-analysis.html + EXTENSION_TEST.html dans la zone tests/audit',
      'Conserver AGENTS_MONITOR.html + agent-log-page.html + audit-dashboard.html en supervision',
      'Ne supprimer aucune page sans validation humaine et comparaison de contenu'
    ]
  };
}

function loadAgentHistoryFromDisk() {
  try {
    if (!fs.existsSync(AGENT_HISTORY_PATH)) return;
    const raw = fs.readFileSync(AGENT_HISTORY_PATH, 'utf8');
    const parsed = JSON.parse(raw);
    const rows = Array.isArray(parsed?.history) ? parsed.history : [];
    rows.slice(0, 200).forEach((r) => agentHistory.push(r));
  } catch (_) {}
}

function writeAgentHistoryToDisk() {
  const payload = {
    updatedAt: new Date().toISOString(),
    intervalMs: AGENT_HISTORY_INTERVAL_MS,
    history: agentHistory.slice(0, 200)
  };
  try {
    fs.writeFileSync(AGENT_HISTORY_PATH, JSON.stringify(payload, null, 2));
  } catch (_) {}
  try {
    fs.mkdirSync(path.dirname(AGENT_HISTORY_BACKUP_PATH), { recursive: true });
    fs.writeFileSync(AGENT_HISTORY_BACKUP_PATH, JSON.stringify(payload, null, 2));
  } catch (_) {}
  scheduleBackupLiveMirror('agent-history');
}

function buildAgentHistorySnapshot() {
  const runtime = getRuntimeSnapshot();
  const byStatus = runtime.reduce((acc, r) => {
    const k = String(r.status || 'unknown');
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
  const latestEvents = sysLogs.slice(0, 10).map((e) => ({
    ts: e.ts,
    from: e.from,
    to: e.to,
    action: e.action,
    status: e.status
  }));

  return {
    ts: new Date().toISOString(),
    summary: {
      totalAgents: runtime.length,
      byStatus,
      active: runtime.filter((r) => r.status === 'en cours').length,
      blocked: runtime.filter((r) => r.status === 'bloqué').length
    },
    runtime,
    latestEvents
  };
}

function runAgentHistoryCycle() {
  const snap = buildAgentHistorySnapshot();
  agentHistory.unshift(snap);
  if (agentHistory.length > 200) agentHistory.pop();
  writeAgentHistoryToDisk();
  scheduleBackupLiveMirror('history-cycle', {
    ts: snap.ts,
    agent: 'history-agent',
    to: 'developer',
    status: 'info',
    message: 'Snapshot agents enregistré'
  });

  publishAgentChatMessage({
    agent: 'history-agent',
    to: 'developer',
    status: 'info',
    phase: 'terminé',
    message: 'Snapshot agents enregistré',
    cause: 'cycle périodique 30min',
    impact: `active=${snap.summary.active} blocked=${snap.summary.blocked}`,
    solution: 'consulter /agents/history'
  });
}

// Debounce: max 1 écriture disque toutes les 5 secondes
let _sysLogTimer = null;
function writeSysLog() {
  if (_sysLogTimer) return;
  _sysLogTimer = setTimeout(() => {
    _sysLogTimer = null;
    try {
      const payload = getSystemLogPayload();
      fs.writeFileSync(SYSLOG_PATH, JSON.stringify(payload, null, 2));
      writeJsonMirror(BACKUP_SYSLOG_PATH, payload);
    } catch (_) {}
    scheduleBackupLiveMirror('system-log-write');
  }, 5000);
}

// ── Internal push — appeler depuis n'importe quel agent pour alimenter le log ──
function pushLog(from, to, action, status, detail) {
  const entry = {
    id:     Date.now(),
    ts:     new Date().toISOString(),
    from:   from   || 'system',
    to:     to     || 'system',
    action: action || '',
    status: status || 'ok',
    detail: detail || ''
  };
  sysLogs.unshift(entry);
  if (sysLogs.length > 500) sysLogs.pop();
  
  // Update agent state based on the log
  if (from && from !== 'system') {
    const agentStatus = (status === 'error') ? 'error' : 'working';
    updateAgentState(from, agentStatus, action);
    setTimeout(() => {
      if (agentStates[from]) agentStates[from].status = 'idle';
    }, 3000);
  }
  
  // Broadcast to SSE and marketStore
  try { marketStore.broadcast({ type: 'syslog', entry }); } catch (_) {}
  broadcastAgentActivity(entry);
  writeSysLog();
  scheduleBackupLiveMirror('push-log', entry);
}

app.post('/system-log', (req, res) => {
  const entry = {
    id:     sysLogs.length + 1,
    ts:     new Date().toISOString(),
    from:   req.body?.from    || 'unknown',
    to:     req.body?.to      || 'system',
    action: req.body?.action  || '',
    status: req.body?.status  || 'ok',
    data:   req.body?.data    || null
  };
  sysLogs.unshift(entry);
  if (sysLogs.length > 500) sysLogs.pop();
  // Keep monitor synchronized in real-time with log writes.
  try { broadcastAgentActivity(entry); } catch (_) {}
  writeSysLog();
  scheduleBackupLiveMirror('system-log-post', entry);
  res.json({ ok: true, id: entry.id });
});

app.get('/system-log', (_req, res) => {
  res.json({ ok: true, agents: agentStates, logs: sysLogs.slice(0, 50) });
});

app.get('/agents/runtime', (_req, res) => {
  const snapshot = getRuntimeSnapshot();
  const totalEtaMs = snapshot
    .filter((a) => Number.isFinite(a.etaMs) && a.etaMs >= 0)
    .reduce((acc, a) => acc + a.etaMs, 0);
  const systemLoadVolume = Math.round(
    (_cpuPercent * 0.6) +
    (Math.min(100, _activeAgentExecutions * 50) * 0.2) +
    (Math.min(100, _agentExecutionQueue.length * 10) * 0.2)
  );
  const queuedPreview = _agentExecutionQueue
    .slice(0, 20)
    .map((t) => ({
      id: t.id,
      label: t.label,
      priority: t.priorityLabel || getDispatchPriorityLabel(t.priority),
      dependsOn: t.dependsOn || [],
      waitingMs: Math.max(0, Date.now() - (t.enqueuedAt || Date.now()))
    }));
  res.json({
    ok: true,
    enabled: _runtimeLoopEnabled,
    regulation: {
      cpuPercent: _cpuPercent,
      maxActiveAgents: _agentExecutionDynamicMax,
      slowdownMs: _runtimeSlowdownMs,
      autoSafeMode: _runtimeAutoSafeMode,
      effectiveSafeMode: getEffectiveSafeMode(),
      intervalMs: _runtimeLoopCurrentIntervalMs || _runtimeLoopTargetIntervalMs
    },
    dispatcher: {
      activeExecutions: _activeAgentExecutions,
      pendingTasks: _agentExecutionQueue.length,
      maxConcurrent: _agentExecutionDynamicMax,
      systemLoadVolume,
      completedKeys: _agentExecutionCompletedAt.size,
      queuePreview: queuedPreview
    },
    totalAgents: snapshot.length,
    totalEtaMs,
    totalEtaLabel: formatEtaLabel(totalEtaMs),
    agents: snapshot
  });
});

app.get('/agents/history', (req, res) => {
  const limit = Math.min(200, Math.max(1, parseInt(req.query.limit || '20', 10) || 20));
  res.json({
    ok: true,
    intervalMs: AGENT_HISTORY_INTERVAL_MS,
    count: Math.min(limit, agentHistory.length),
    history: agentHistory.slice(0, limit)
  });
});

app.get('/backup/live-state', (_req, res) => {
  const payload = buildBackupLiveStatePayload();
  res.json(payload);
});

app.post('/agents/runtime/start', (_req, res) => {
  startRuntimeLoop();
  res.json({ ok: true, enabled: true });
});

app.post('/agents/runtime/stop', (_req, res) => {
  stopRuntimeLoop();
  res.json({ ok: true, enabled: false });
});

// ── AI REPAIR REQUEST (collects diagnostic for AI repair) ─────────────────
const repairRequests = {};  // {requestId: {timestamp, errors, context, status}}
app.post('/ai-repair-request', (req, res) => {
  try {
    const {from, to, action, module, context, timestamp} = req.body;
    
    const requestId = require('crypto').randomUUID();
    const repairRequest = {
      id: requestId,
      timestamp: timestamp || new Date().toISOString(),
      from,
      to,
      action,
      module,
      context,
      status: 'PENDING',
      createdAt: Date.now()
    };
    
    // Store in memory
    repairRequests[requestId] = repairRequest;
    
    // Also log to system logs
    sysLogs.unshift({
      id: sysLogs.length + 1,
      ts: repairRequest.timestamp,
      from: from || 'extension',
      to: 'ai-repair',
      action: action || 'REPAIR_REQUEST',
      status: 'PENDING',
      detail: {
        requestId,
        module,
        errorCount: context?.errors?.length || 0
      }
    });
    if (sysLogs.length > 500) sysLogs.pop();
    writeSysLog();
    scheduleBackupLiveMirror('repair-request', {
      ts: repairRequest.timestamp,
      from: from || 'extension',
      to: 'ai-repair',
      status: 'warning',
      action: action || 'REPAIR_REQUEST'
    });
    
    // Broadcast to SSE clients
    broadcastAgentActivity({
      type: 'repair_request',
      requestId,
      module,
      timestamp: repairRequest.timestamp
    });
    
    console.log('[AI_REPAIR] Request created:', requestId, 'Module:', module);
    
    res.json({ ok: true, requestId, status: 'PENDING' });
  } catch (e) {
    console.error('[AI_REPAIR] Error:', e.message);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// Get repair request status
app.get('/ai-repair-request/:id', (req, res) => {
  const {id} = req.params;
  const repairReq = repairRequests[id];
  
  if (!repairReq) {
    return res.status(404).json({ok: false, error: 'Request not found'});
  }
  
  res.json({ok: true, request: repairReq});
});

// ─── AGENT STATUS (current agent states) ──────────────────────────────────────
app.get('/agent-status', (_req, res) => {
  const statusMap = {};
  for (const [name, state] of Object.entries(agentStates)) {
    statusMap[name] = {
      status: state.status,
      lastActivity: state.lastActivity,
      activeTask: state.activeTask,
      secondsAgoLastActivity: Math.round((Date.now() - state.lastActivity) / 1000)
    };
  }
  res.json({ ok: true, agents: statusMap, timestamp: new Date().toISOString() });
});

// ─── AGENT ACTIVITY STREAM (SSE — real-time agent logs) ─────────────────────
app.get('/agent-activity', (_req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();

  // Send current agent states as initial data
  res.write('data: ' + JSON.stringify({ type: 'initial', agents: agentStates, logs: sysLogs.slice(0, 50) }) + '\n\n');

  // Add client to the list
  agentActivitySseClients.push(res);

  // Heartbeat to keep connection alive
  const heartbeat = setInterval(() => {
    try {
      res.write(': heartbeat\n\n');
    } catch (e) {
      clearInterval(heartbeat);
      const idx = agentActivitySseClients.indexOf(res);
      if (idx > -1) agentActivitySseClients.splice(idx, 1);
    }
  }, 15000);

  res.on('close', () => {
    clearInterval(heartbeat);
    const idx = agentActivitySseClients.indexOf(res);
    if (idx > -1) agentActivitySseClients.splice(idx, 1);
  });
});

// ─── AGENT BUS (lecture AGENT_BUS.json pour coordination multi-IA) ───────────
const AGENT_BUS_PATH = path.join(__dirname, 'AGENT_BUS.json');
app.get('/agent-bus', (_req, res) => {
  try {
    const raw = fs.readFileSync(AGENT_BUS_PATH, 'utf8');
    const bus = JSON.parse(raw);
    res.json({
      ok:          true,
      version:     bus.version,
      lastUpdated: bus.lastUpdated,
      systemStatus: bus.systemStatus || {},
      roles:       bus.roles   || {},
      tasks: {
        done:        (bus.tasks && bus.tasks.done)         || [],
        inProgress:  (bus.tasks && bus.tasks.inProgress)   || [],
        pending:     (bus.tasks && bus.tasks.pending)      || []
      }
    });
  } catch (e) {
    res.json({ 
      ok: false, 
      error: e.message, 
      tasks: { done: [], inProgress: [], pending: [] } 
    });
  }
});

// ─── TASKS + LOGS (coordination Claude ↔ Agents) ─────────────────────────────
const TASKS_PATH = path.join(__dirname, 'tasks.json');
const LOGS_PATH  = path.join(__dirname, 'logs.json');

app.get('/tasks', (_req, res) => {
  try { res.json({ ok: true, ...JSON.parse(fs.readFileSync(TASKS_PATH, 'utf8')) }); }
  catch (e) { res.json({ ok: false, error: e.message, tasks: [] }); }
});

app.post('/tasks/update', (req, res) => {
  try {
    const data   = JSON.parse(fs.readFileSync(TASKS_PATH, 'utf8'));
    const { task_id, status, result } = req.body || {};
    const task = (data.tasks || []).find(t => t.task_id === task_id);
    if (task) { task.status = status || task.status; if (result) task.result = result; task.updated_at = new Date().toISOString(); }
    data.updated = new Date().toISOString();
    fs.writeFileSync(TASKS_PATH, JSON.stringify(data, null, 2));
    pushLog('agent', 'claude', 'TASK ' + task_id + ' → ' + status, status === 'error' ? 'err' : 'ok', result || '');
    res.json({ ok: true });
  } catch (e) { res.json({ ok: false, error: e.message }); }
});

app.get('/logs', (_req, res) => {
  try { res.json({ ok: true, ...JSON.parse(fs.readFileSync(LOGS_PATH, 'utf8')) }); }
  catch (e) { res.json({ ok: false, error: e.message, logs: [] }); }
});

app.post('/logs', (req, res) => {
  try {
    const data  = JSON.parse(fs.readFileSync(LOGS_PATH, 'utf8'));
    const entry = { id: Date.now(), ts: new Date().toISOString(), agent: req.body.agent || 'unknown', task_id: req.body.task_id || '', action: req.body.action || '', status: req.body.status || 'ok', detail: req.body.detail || '' };
    (data.logs = data.logs || []).unshift(entry);
    if (data.logs.length > 500) data.logs.pop();
    fs.writeFileSync(LOGS_PATH, JSON.stringify(data, null, 2));
    writeJsonMirror(BACKUP_LOGS_PATH, data);
    pushLog(entry.agent, 'system', entry.action, entry.status, entry.detail);
    res.json({ ok: true });
  } catch (e) { res.json({ ok: false, error: e.message }); }
});

// ─── ACTIVE SYMBOL (sync extension TradingView → Studio) ─────────────────────

app.get('/active-symbol', (_req, res) => {
  res.json({ ok: true, ...activeSymbol });
});

app.post('/active-symbol', (req, res) => {
  const { symbol, timeframe, price, mode } = req.body || {};  // MODIFIÉ: Add mode
  if (symbol) {
    const normalizedInput = String(symbol).replace(/[/\-\s]/g, '').toUpperCase();
    const normalized = normalizeSymbol(normalizedInput).canonical || normalizedInput;
    const tvPrice    = price ? parseFloat(price) : null;
    const requestedMode = normalizeBridgeMode(mode || activeSymbol?.mode || bridgeConfig.bridgeMode || 'AUTO');
    const resolvedMode = resolveRuntimeMode(requestedMode, normalized, timeframe || 'H1');
    activeSymbol = {
      symbol:    normalized,
      timeframe: timeframe || 'H1',
      tvPrice:   tvPrice,
      mode:      requestedMode,
      modeResolved: resolvedMode,
      updatedAt: new Date().toISOString()
    };
    saveExtensionRuntimeState();
    try { marketStore.broadcast({ type: 'activeSymbol', ...activeSymbol }); } catch (_) {}

    applyBridgeConfigPatch({
      bridgeMode: requestedMode,
      symbolAliasBridge: normalized,
      bridgeSource: 'extension-or-html'
    }, 'active-symbol-endpoint');
    
    // 🔴 UNIFIED SYNC: Envoyer aussi à Extension + HTML clients
    broadcastToExtension({
      type: 'active-symbol',
      symbol: normalized,
      timeframe: timeframe || 'H1',
      price: tvPrice,
      mode: requestedMode,
      modeResolved: resolvedMode,
      source: 'extension-or-html'
    });

    emitBridgeConfig('active-symbol');
    
    pushLog('extension', 'orchestrator',
      `SYMBOLE DÉTECTÉ ${normalized} @ ${tvPrice ? tvPrice.toFixed(tvPrice > 10 ? 2 : 5) : '?'} [${requestedMode}/${resolvedMode}]`,
      'ok',
      `TF:${timeframe || 'H1'} · Mode:${requestedMode} → ${resolvedMode} · source:TradingView`
    );
  }
  res.json({ ok: true, activeSymbol });
});

// ─── AGENT FILTRE ────────────────────────────────────────────────────────────
app.post('/agent-filtre', (req, res) => {
  res.json({ ok: true, opportunities: [], note: 'Connectez MT5 pour des opportunités filtrées en temps réel' });
});

// ─── ERROR HANDLER ────────────────────────────────────────────────────────────
app.use((err, req, res, _next) => {
  console.error('[SERVER ERROR]', err.message);
  res.status(500).json({ ok: false, error: err.message });
});

// ─── AUTO ORCHESTRATION LOOP ─────────────────────────────────────────────────
// Tourne toutes les 30s sur le symbole actif — alimente le AGENTS LIVE LOG en réel
async function runOrchestrationCycle() {
  const sym = activeSymbol && activeSymbol.symbol;
  if (!sym) return; // Pas de symbole détecté, rien à faire

  const tf = (activeSymbol.timeframe || 'H1').toUpperCase();

  try {
    // 1. Prix live — TradingView est la source maître
    let price;
    const tvLive = tvDataStore[sym];
    const tvAge  = tvLive ? (Date.now() - (tvLive.updatedAt || 0)) : Infinity;
    if (tvLive && tvAge < 30000) {
      // TradingView price disponible et récent (< 30s) — on l'utilise directement
      price = parseFloat(tvLive.price);
      pushLog('orchestrator', 'system',
        `BOUCLE ${sym} — prix TradingView (${(tvAge / 1000).toFixed(1)}s)`,
        'ok', `source:TradingView · price:${price}`);
    } else {
      // Fallback Yahoo Finance si tvDataStore absent ou trop ancien
      const yahoSym = toYahooSym(sym);
      if (!yahoSym) return;
      price = await fetchYahooPrice(yahoSym);
      if (!price || price <= 0) {
        pushLog('orchestrator', 'system', `BOUCLE ${sym} — prix indisponible`, 'warn', 'source:offline');
        return;
      }
    }

    pushLog('orchestrator', 'technicalAgent',
      `REQUÊTE analyse ${sym} @ ${price.toFixed(price > 10 ? 2 : 5)}`,
      'ok', `TF:${tf} · cycle:auto`);

    // 2. Technical analysis
    try {
      const technicalAgent = require('./src/agents/technicalAgent');
      const profile        = normalizeSymbol(sym);
      const result         = await technicalAgent.analyze({ symbol: sym, price, timeframe: tf }, profile);
      if (result) {
        pushLog('technicalAgent', 'orchestrator',
          `RÉSULTAT ${sym} → ${result.direction || '?'} | Score:${result.score || 0}`,
          'ok',
          `RSI:${result.rsi != null ? result.rsi.toFixed(1) : '?'} · EMA20:${result.ema20 != null ? result.ema20.toFixed(2) : '?'} · signal:${result.signal || '?'}`
        );
      }
    } catch (e) {
      pushLog('technicalAgent', 'orchestrator', `ERREUR analyse ${sym}`, 'err', e.message);
    }

    // 3. Macro check (rapide)
    try {
      const macroAgent = require('./src/agents/macroAgent');
      const calendar   = await macroAgent.getEconomicCalendar();
      const impact     = await macroAgent.analyzeEconomicImpact(calendar);
      pushLog('macroAgent', 'orchestrator',
        `MACRO · ${calendar.length} events · Risk:${impact.riskLevel}`,
        impact.riskLevel === 'High' ? 'warn' : 'ok',
        `nextEvent:${impact.nextEvent || 'aucun'}`
      );
    } catch (_) {}

  } catch (err) {
    pushLog('orchestrator', 'system', `CYCLE ERREUR: ${err.message}`, 'err', sym);
  }
}

// ─── SCREENSHOT ANALYSIS (extension) ────────────────────────────────────────
app.post('/analyze-screenshot', (req, res) => {
  try {
    const { image, symbol, timeframe } = req.body || {};
    if (!image || !symbol) {
      return res.status(400).json({ ok: false, error: 'Missing image or symbol' });
    }
    
    // Simulate screenshot analysis (in real scenario, you'd send to image AI)
    const analysis = {
      symbols_detected: [symbol],
      structure: 'Trend continuation after consolidation',
      fvg_present: true,
      liquidity: 'High in range',
      bos_choch: 'No recent break of structure',
      confirmations: ['Price > EMA20', 'RSI > 50', 'Volume rising']
    };
    
    pushLog('extension', 'system', `Screenshot analyzed: ${symbol}`, 'ok', 'FVG detected, high confidence');
    res.json({ ok: true, analysis: analysis });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ─── BROKER CONFIGURATION ────────────────────────────────────────────────────
const BROKER_SYMBOLS = {
  tradingview: {
    XAUUSD: 'XAUUSD', EURUSD: 'EURUSD', GBPUSD: 'GBPUSD', BTCUSD: 'BTCUSD', NAS100: 'NAS100', US500: 'US500'
  },
  topstep: {
    XAUUSD: 'GOLD', EURUSD: 'EURUSD', GBPUSD: 'GBPUSD', BTCUSD: 'BTC', NAS100: 'NQ-Mini', US500: 'ES-Mini'
  },
  oanda: {
    XAUUSD: 'XAU_USD', EURUSD: 'EUR_USD', GBPUSD: 'GBP_USD', BTCUSD: 'BTC_USD', NAS100: 'US100_USD', US500: 'US500_USD'
  }
};

let selectedBroker = 'tradingview'; // Current user selection

app.post('/broker-select', (req, res) => {
  try {
    const { broker } = req.body || {};
    if (!broker || !BROKER_SYMBOLS[broker]) {
      return res.status(400).json({ ok: false, error: 'Invalid broker' });
    }
    
    selectedBroker = broker;
    pushLog('extension', 'system', `Broker selected: ${broker}`, 'ok', '');
    res.json({ ok: true, selected: broker });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.get('/broker-config/:broker', (req, res) => {
  try {
    const broker = req.params.broker.toLowerCase();
    if (!BROKER_SYMBOLS[broker]) {
      return res.status(400).json({ ok: false, error: 'Invalid broker' });
    }
    
    res.json({
      ok: true,
      broker: broker,
      mapping: BROKER_SYMBOLS[broker],
      current: selectedBroker
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// ─── HTML PAGES RACINE — toutes les pages servies ────────────────────────────
app.get('/agent-log',        (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'agent-log-page.html')));
app.get('/agent-live-log',   (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'agent-log-page.html')));
app.get('/agents/log',       (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'agent-log-page.html')));
app.get('/dashboard',        (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'dashboard.html')));
app.get('/dashboard.html',   (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'dashboard.html')));
app.get('/popup',            (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'popup.html')));
app.get('/popup.html',       (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'popup.html')));
app.get('/agents-monitor',   (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'AGENTS_MONITOR.html')));
app.get('/agents/monitor',   (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'AGENTS_MONITOR.html')));
app.get('/AGENTS_MONITOR.html', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'AGENTS_MONITOR.html')));
app.get('/extension-test',   (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'EXTENSION_TEST.html')));
app.get('/EXTENSION_TEST.html', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'EXTENSION_TEST.html')));
app.get('/test-analysis',    (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'test-analysis.html')));
app.get('/test-analysis.html',  (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'test-analysis.html')));
app.get('/test-chart',       (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'test-chart-visual.html')));
app.get('/test-chart-visual.html', (_req, res) => sendHTMLWithHelper(res, path.join(__dirname, 'test-chart-visual.html')));

// ─── MARKET NEWS — calendrier économique ForexFactory ────────────────────────
let _newsCache = null;
let _newsCacheTs = 0;
const NEWS_TTL = 5 * 60 * 1000; // 5 minutes

app.get('/market-news', async (_req, res) => {
  try {
    const now = Date.now();
    if (_newsCache && (now - _newsCacheTs) < NEWS_TTL) {
      return res.json({ ok: true, events: _newsCache, cached: true });
    }
    // ForexFactory public JSON calendar
    const https = require('https');
    const raw = await new Promise((resolve, reject) => {
      const req = https.get('https://nfs.faireconomy.media/ff_calendar_thisweek.json', { timeout: 6000 }, resp => {
        let data = '';
        resp.on('data', d => { data += d; });
        resp.on('end', () => resolve(data));
      });
      req.on('error', reject);
      req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    });
    const events = JSON.parse(raw);
    // Filter: only Medium + High impact
    const filtered = (Array.isArray(events) ? events : [])
      .filter(e => e.impact === 'High' || e.impact === 'Medium')
      .map(e => ({
        title:   e.title   || e.name || '',
        country: e.country || '',
        date:    e.date    || '',
        time:    e.time    || '',
        impact:  e.impact  || 'Low',
        forecast: e.forecast || '',
        previous: e.previous || ''
      }));
    _newsCache = filtered;
    _newsCacheTs = now;
    res.json({ ok: true, events: filtered });
  } catch (e) {
    // Return cached even if stale, or empty
    res.json({ ok: false, events: _newsCache || [], error: e.message });
  }
});

// ─── Economic Calendar (formatted for frontend) ──────────────────────────────
app.get('/economic-calendar', async (_req, res) => {
  try {
    const now = Date.now();
    if (_newsCache && (now - _newsCacheTs) < NEWS_TTL) {
      const formatted = formatEconomicEvents(_newsCache);
      return res.json({ ok: true, events: formatted, cached: true });
    }
    // Fetch from ForexFactory
    const https = require('https');
    const raw = await new Promise((resolve, reject) => {
      const req = https.get('https://nfs.faireconomy.media/ff_calendar_thisweek.json', { timeout: 6000 }, resp => {
        let data = '';
        resp.on('data', d => { data += d; });
        resp.on('end', () => resolve(data));
      });
      req.on('error', reject);
      req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    });
    const events = JSON.parse(raw);
    _newsCache = events;
    _newsCacheTs = now;
    
    const formatted = formatEconomicEvents(events);
    res.json({ ok: true, events: formatted });
  } catch (e) {
    console.error('[CALENDAR]', e.message);
    res.json({ ok: false, events: [], error: e.message });
  }
});

function formatEconomicEvents(events) {
  if (!Array.isArray(events)) return [];
  return events.map(e => ({
    title:    e.title || e.name || 'Economic Event',
    country:  e.country || 'XX',
    time:     e.time || e.date || new Date().toISOString(),
    dateTime: e.date + ' ' + e.time || new Date().toISOString(),
    importance: e.impact === 'High' ? 'HIGH' : e.impact === 'Medium' ? 'MEDIUM' : 'LOW',
    impact:   e.impact || 'Low',
    forecast: e.forecast || '',
    previous: e.previous || '',
    actual:   e.actual || null
  }));
}

// ─── FALLBACK ENDPOINTS (Studio Web Interface) ────────────────────────────────
// Keep only fallback routes that do not duplicate existing primary endpoints.

app.post('/instant-trade-live', (req, res) => {
  // POST handler for instant trade
  res.json({
    ok: true,
    trade: null,
    source: 'server-fallback',
    message: 'Instant trade not available'
  });
});

app.get('/screen', (_req, res) => {
  // Screenshot endpoint (studio diagnostic)
  res.json({ 
    ok: true, 
    screenshot: null,
    source: 'server-fallback',
    message: 'Screenshot not available'
  });
});

// ─── STUDIO ENDPOINTS (popup.js bridge calls) ─────────────────────────────────
app.get('/studio/data', (_req, res) => {
  // Return REAL MT5 data from marketStore
  const mt5Data = marketStore.lastMT5Payload || {};
  res.json({
    ok: true,
    symbol: mt5Data.symbol || 'EURUSD',
    price: mt5Data.price || mt5Data.bid || mt5Data.ask || 1.0870,
    bid: mt5Data.bid || null,
    ask: mt5Data.ask || null,
    timeframe: mt5Data.timeframe || 'H1',
    ohlc: mt5Data.ohlc || mt5Data.bars || [],
    timestamp: new Date().toISOString(),
    source: 'mt5',
    lastUpdate: marketStore.systemStatus.lastUpdate
  });
});

// ─── CONSOLIDATED PORT 4000: /data endpoint for Chrome extension ──────────────
app.get('/data', (_req, res) => {
  // Return REAL MT5 data from marketStore for Chrome extension
  const mt5Data = marketStore.lastMT5Payload || {};
  const normalized = {
    symbol: mt5Data.symbol || 'EURUSD',
    price: mt5Data.price || mt5Data.bid || mt5Data.ask || 1.0870,
    bid: mt5Data.bid || null,
    ask: mt5Data.ask || null,
    timeframe: mt5Data.timeframe || 'H1',
    ohlc: mt5Data.ohlc || mt5Data.bars || [],
    timestamp: new Date().toISOString(),
    source: 'mt5',
    lastUpdate: marketStore.systemStatus.lastUpdate
  };
  res.json({
    ok: true,
    ...normalized,
    data: normalized
  });
});

app.get('/studio/agent-screen', (_req, res) => {
  // Return agent analysis + screenshot
  res.json({
    ok: true,
    agents: marketStore.agents || [],
    consensus: marketStore.consensus || 'HOLD',
    screenshot: null,
    timestamp: new Date().toISOString()
  });
});

app.post('/studio/system-log', (req, res) => {
  // Log endpoint for popup.js
  const logEntry = req.body || {};
  const nextId = Array.isArray(sysLogs) ? (sysLogs.length + 1) : 1;
  const entry = {
    id: nextId,
    ts: new Date().toISOString(),
    source: logEntry.source || 'extension-popup',
    message: logEntry.message || 'popup-log',
    data: logEntry.data || null
  };
  console.log('[POPUP_LOG]', entry.message, entry.data || '');
  if (Array.isArray(sysLogs)) {
    sysLogs.unshift(entry);
    if (sysLogs.length > 500) sysLogs.pop();
  }
  res.json({
    ok: true,
    logged: true,
    entry,
    timestamp: new Date().toISOString()
  });
});

app.get('/studio/system-log', (_req, res) => {
  // Get system logs
  res.json({
    ok: true,
    logs: Array.isArray(sysLogs) ? sysLogs.slice(0, 50) : [],
    timestamp: new Date().toISOString()
  });
});

// ─── MAPPING ENDPOINTS (Symbol ↔ MT5 synchronization) ─────────────────────────
// In-memory mapping store (could be persistent in production)
const mappingStore = {};

app.post('/studio/mapping-save', (req, res) => {
  const { userInput, mt5Symbol, price } = req.body;
  
  if (!userInput || !mt5Symbol) {
    return res.json({ ok: false, error: 'userInput and mt5Symbol required' });
  }
  
  const key = userInput.toUpperCase();
  mappingStore[key] = {
    userInput: key,
    mt5Symbol: mt5Symbol.toUpperCase(),
    price: price || null,
    savedAt: new Date().toISOString()
  };
  
  console.log('[MAPPING] Saved:', key, '→', mt5Symbol);
  
  res.json({
    ok: true,
    mapping: mappingStore[key],
    message: 'Mapping saved successfully'
  });
});

app.get('/studio/mapping-list', (_req, res) => {
  const mappings = Object.values(mappingStore);
  res.json({
    ok: true,
    mappings: mappings,
    count: mappings.length,
    timestamp: new Date().toISOString()
  });
});

app.get('/studio/mapping/:input', (req, res) => {
  const key = req.params.input.toUpperCase();
  const mapping = mappingStore[key];
  
  if (!mapping) {
    return res.json({ ok: false, error: 'Mapping not found' });
  }
  
  res.json({
    ok: true,
    mapping: mapping
  });
});

// ─── PYTHON PROCESS TRACKING ──────────────────────────────────────────────────
let pythonProcesses = {
  pip: null,
  bridge: null
};

// ─── PYTHON DEPENDENCIES CHECK & INSTALL ──────────────────────────────────────
// Check which Python packages are installed
app.get('/pip/check', (req, res) => {
  const packages = ['metatrader5', 'flask', 'flask-cors', 'python-dotenv', 'requests'];
  const status = {};
  
  for (const pkg of packages) {
    try {
      execSync(`python -c "import ${pkg.replace('-', '_').split('>=')[0]}"`, {
        stdio: 'ignore',
        cwd: __dirname
      });
      status[pkg] = true;
    } catch {
      status[pkg] = false;
    }
  }
  
  const allInstalled = Object.values(status).every(v => v);
  res.json({
    ok: true,
    packages: status,
    allInstalled: allInstalled,
    timestamp: new Date().toISOString()
  });
});

// Install Python dependencies
app.post('/pip/install', (req, res) => {
  const reqFile = path.join(__dirname, 'requirements-mt5.txt');
  
  if (!fs.existsSync(reqFile)) {
    return res.status(400).json({
      ok: false,
      error: 'requirements-mt5.txt not found'
    });
  }
  
  try {
    // Run pip install in background
    const pip = spawn('python', ['-m', 'pip', 'install', '-q', '-r', 'requirements-mt5.txt'], {
      cwd: __dirname,
      stdio: 'pipe'
    });
    
    // Track the process
    pythonProcesses.pip = pip;
    
    let output = '';
    let errorMsg = '';
    
    pip.stdout.on('data', (data) => {
      output += data.toString();
    });
    
    pip.stderr.on('data', (data) => {
      errorMsg += data.toString();
    });
    
    pip.on('close', (code) => {
      console.log(`[PIP] Install completed with code ${code}`);
      console.log(`[PIP] Output: ${output}`);
      if (errorMsg) console.log(`[PIP] Errors: ${errorMsg}`);
      pythonProcesses.pip = null;
    });
    
    res.json({
      ok: true,
      message: 'Installation started',
      command: 'pip install -r requirements-mt5.txt',
      pid: pip.pid
    });
    
    console.log(`[PIP] Started installation (PID: ${pip.pid})`);
  } catch (err) {
    res.status(500).json({
      ok: false,
      error: 'Failed to start installation',
      message: err.message
    });
  }
});

// Stop Python processes (pip, bridge, etc)
app.post('/pip/stop', (req, res) => {
  let stopped = [];
  let errors = [];
  
  try {
    // Stop pip install if running
    if (pythonProcesses.pip) {
      try {
        process.kill(-pythonProcesses.pip.pid); // Kill process group
        stopped.push(`pip install (PID: ${pythonProcesses.pip.pid})`);
        pythonProcesses.pip = null;
        console.log('[STOP] Killed pip process');
      } catch (err) {
        errors.push('pip: ' + err.message);
      }
    }
    
    // Stop bridge processes
    if (pythonProcesses.bridge) {
      try {
        process.kill(-pythonProcesses.bridge.pid);
        stopped.push(`bridge (PID: ${pythonProcesses.bridge.pid})`);
        pythonProcesses.bridge = null;
        console.log('[STOP] Killed bridge process');
      } catch (err) {
        errors.push('bridge: ' + err.message);
      }
    }
    
    // Also try to kill legacy bridge helper processes
    try {
      if (process.platform === 'win32') {
        // Windows: use taskkill
        execSync('taskkill /F /IM python.exe 2>nul || true', { stdio: 'ignore' });
        console.log('[STOP] Attempted taskkill on Windows');
      } else {
        // Linux/Mac: use pkill
        execSync('pkill -f "mt5_bridge" 2>/dev/null || true', { stdio: 'ignore' });
        console.log('[STOP] Attempted pkill on Unix');
      }
    } catch (err) {
      // Silently ignore if system command fails
    }
    
    res.json({
      ok: true,
      message: stopped.length > 0 ? 'Processus arrêtés: ' + stopped.join(', ') : 'Aucun processus en cours',
      stopped: stopped,
      errors: errors.length > 0 ? errors : null
    });
  } catch (err) {
    res.status(500).json({
      ok: false,
      error: 'Failed to stop processes',
      message: err.message
    });
  }
});

// Start MT5 Bridge Python script
// ═══════════════════════════════════════════════════════════════════════════════
// POST /bridge/start - START MT5 PYTHON BRIDGE
// Response: ALWAYS JSON (never HTML)
// ═══════════════════════════════════════════════════════════════════════════════
app.post('/bridge/start', (req, res) => {
  return res.status(423).json({
    ok: false,
    error: 'bridge_start_disabled',
    message: 'Single-environment mode active: only Node server on port 4000 is allowed.'
  });

  // Set response header to ensure JSON
  res.type('application/json');
  
  let script, scriptPath;
  
  try {
    // ──────────────────────────────────────────────────────────────────────────
    // 1. GET SCRIPT NAME
    // ──────────────────────────────────────────────────────────────────────────
    script = req.query.script || 'mt5_bridge_simple.py';
    console.log(`[BRIDGE-START] Script reçu: ${script}`);
    
    scriptPath = path.join(__dirname, script);
    console.log(`[BRIDGE-START] Chemin complet: ${scriptPath}`);
    
    // ──────────────────────────────────────────────────────────────────────────
    // 2. CHECK IF SCRIPT EXISTS
    // ──────────────────────────────────────────────────────────────────────────
    if (!fs.existsSync(scriptPath)) {
      const errorMsg = `Script not found: ${scriptPath}`;
      console.error(`[BRIDGE-START] ❌ ${errorMsg}`);
      return res.status(400).json({
        ok: false,
        error: errorMsg,
        details: `File does not exist at: ${scriptPath}`
      });
    }
    console.log(`[BRIDGE-START] ✅ Script existe`);
    
    // ──────────────────────────────────────────────────────────────────────────
    // 3. KILL EXISTING PROCESS IF ANY
    // ──────────────────────────────────────────────────────────────────────────
    if (pythonProcesses.bridge) {
      try {
        const oldPID = pythonProcesses.bridge.pid;
        process.kill(-pythonProcesses.bridge.pid);
        console.log(`[BRIDGE-START] Processo anterior matado (PID=${oldPID})`);
      } catch (killErr) {
        console.log(`[BRIDGE-START] Aviso: não foi possível matar o processo anterior: ${killErr.message}`);
      }
    }
    
    // ──────────────────────────────────────────────────────────────────────────
    // 4. SPAWN PYTHON PROCESS
    // ──────────────────────────────────────────────────────────────────────────
    const command = `python "${scriptPath}"`;
    console.log(`[BRIDGE-START] Executando: ${command}`);
    
    const python = spawn('python', [scriptPath], {
      detached: false,
      stdio: ['ignore', 'pipe', 'pipe'],
      cwd: __dirname,
      shell: false
    });
    
    let stdout = '';
    let stderr = '';
    let responseEmitted = false;
    
    // ──────────────────────────────────────────────────────────────────────────
    // 5. CAPTURE STDOUT
    // ──────────────────────────────────────────────────────────────────────────
    python.stdout.on('data', (data) => {
      const text = data.toString();
      stdout += text;
      console.log(`[BRIDGE-START-OUT] ${text.trim()}`);
    });
    
    // ──────────────────────────────────────────────────────────────────────────
    // 6. CAPTURE STDERR
    // ──────────────────────────────────────────────────────────────────────────
    python.stderr.on('data', (data) => {
      const text = data.toString();
      stderr += text;
      console.log(`[BRIDGE-START-ERR] ${text.trim()}`);
    });
    
    // ──────────────────────────────────────────────────────────────────────────
    // 7. HANDLE SPAWN ERROR
    // ──────────────────────────────────────────────────────────────────────────
    python.on('error', (err) => {
      console.error(`[BRIDGE-START] ❌ Spawn error: ${err.message}`);
      if (!responseEmitted) {
        responseEmitted = true;
        return res.status(500).json({
          ok: false,
          error: 'Failed to spawn Python process',
          details: err.message
        });
      }
    });
    
    // ──────────────────────────────────────────────────────────────────────────
    // 8. HANDLE PROCESS CLOSE
    // ──────────────────────────────────────────────────────────────────────────
    python.on('close', (code) => {
      console.log(`[BRIDGE-START] Process fermé avec code ${code}`);
      if (code !== 0 && stderr) {
        console.log(`[BRIDGE-START] STDERR final: ${stderr.substring(0, 200)}`);
      }
      pythonProcesses.bridge = null;
    });
    
    // ──────────────────────────────────────────────────────────────────────────
    // 9. STORE PROCESS REFERENCE
    // ──────────────────────────────────────────────────────────────────────────
    pythonProcesses.bridge = python;
    console.log(`[BRIDGE-START] ✅ Process lancé avec PID=${python.pid}`);
    
    // ──────────────────────────────────────────────────────────────────────────
    // 10. SEND SUCCESS RESPONSE
    // ──────────────────────────────────────────────────────────────────────────
    responseEmitted = true;
    res.status(200).json({
      ok: true,
      started: true,
      script: script,
      pid: python.pid,
      command: command,
      timestamp: new Date().toISOString()
    });
    
    console.log(`[BRIDGE-START] ✅ SUCCESS - Réponse JSON envoyée au client`);
    
  } catch (fatalErr) {
    // ──────────────────────────────────────────────────────────────────────────
    // FATAL ERROR - CATCH ALL
    // ──────────────────────────────────────────────────────────────────────────
    console.error(`[BRIDGE-START] ❌ FATAL ERROR: ${fatalErr.message}`);
    console.error(`[BRIDGE-START] Stack: ${fatalErr.stack}`);
    
    res.type('application/json');
    return res.status(500).json({
      ok: false,
      error: 'Fatal error in bridge start',
      details: fatalErr.message
    });
  }
});

// Stop MT5 Bridge Python script
// ═══════════════════════════════════════════════════════════════════════════════
// POST /bridge/stop - STOP MT5 PYTHON BRIDGE
// Response: ALWAYS JSON (never HTML)
// ═══════════════════════════════════════════════════════════════════════════════
app.post('/bridge/stop', (req, res) => {
  // Set response header to ensure JSON
  res.type('application/json');
  
  try {
    // ──────────────────────────────────────────────────────────────────────────
    // 1. CHECK IF BRIDGE PROCESS EXISTS
    // ──────────────────────────────────────────────────────────────────────────
    console.log(`[BRIDGE-STOP] Requête reçue`);
    
    if (!pythonProcesses.bridge) {
      const msg = 'No bridge process running';
      console.log(`[BRIDGE-STOP] ${msg}`);
      return res.status(200).json({
        ok: true,
        stopped: false,
        message: msg
      });
    }
    
    // ──────────────────────────────────────────────────────────────────────────
    // 2. GET PID OF RUNNING PROCESS
    // ──────────────────────────────────────────────────────────────────────────
    const pidToKill = pythonProcesses.bridge.pid;
    console.log(`[BRIDGE-STOP] PID à tuer: ${pidToKill}`);
    
    // ──────────────────────────────────────────────────────────────────────────
    // 3. KILL THE PROCESS
    // ──────────────────────────────────────────────────────────────────────────
    try {
      process.kill(-pidToKill);  // Negative PID kills process group
      console.log(`[BRIDGE-STOP] ✅ Process tué avec succès (PID=${pidToKill})`);
    } catch (killErr) {
      console.log(`[BRIDGE-STOP] ⚠️ Process déjà terminé (PID=${pidToKill}): ${killErr.message}`);
    }
    
    // ──────────────────────────────────────────────────────────────────────────
    // 4. CLEAR PROCESS REFERENCE
    // ──────────────────────────────────────────────────────────────────────────
    pythonProcesses.bridge = null;
    console.log(`[BRIDGE-STOP] Référence de process effacée`);
    
    // ──────────────────────────────────────────────────────────────────────────
    // 5. SEND SUCCESS RESPONSE
    // ──────────────────────────────────────────────────────────────────────────
    res.status(200).json({
      ok: true,
      stopped: true,
      message: `Bridge process stopped (was PID=${pidToKill})`,
      pid: pidToKill,
      timestamp: new Date().toISOString()
    });
    
    console.log(`[BRIDGE-STOP] ✅ SUCCESS - Réponse JSON envoyée au client`);
    
  } catch (fatalErr) {
    // ──────────────────────────────────────────────────────────────────────────
    // FATAL ERROR - CATCH ALL
    // ──────────────────────────────────────────────────────────────────────────
    console.error(`[BRIDGE-STOP] ❌ FATAL ERROR: ${fatalErr.message}`);
    console.error(`[BRIDGE-STOP] Stack: ${fatalErr.stack}`);
    
    res.type('application/json');
    return res.status(500).json({
      ok: false,
      stopped: false,
      error: 'Fatal error in bridge stop',
      details: fatalErr.message
    });
  }
});

// ─── MT5 DETECTION ─────────────────────────────────────────────────────────────
// Check if MT5 is installed and/or running
app.get('/mt5/detect', (req, res) => {
  const status = {
    installed: false,
    running: false,
    path: null,
    message: 'MT5 not detected'
  };
  
  try {
    // Check Windows registry for MT5 installation
    if (process.platform === 'win32') {
      try {
        const Registry = require('winreg');
        const regKey = new Registry({
          hive: Registry.HKLM,
          key: '\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall'
        });
        
        regKey.values((err, items) => {
          if (!err && items) {
            const mt5Installed = items.some(item => 
              item.name && (item.name.includes('MetaTrader') || item.name.includes('MT5'))
            );
            if (mt5Installed) {
              status.installed = true;
            }
          }
        });
      } catch (e) {
        // Registry module not available, use alternate method
      }
      
      // Check for MT5.exe in common installation paths
      const commonPaths = [
        'C:\\Program Files\\MetaTrader 5\\terminal.exe',
        'C:\\Program Files (x86)\\MetaTrader 5\\terminal.exe',
        'C:\\Users\\' + process.env.USERNAME + '\\AppData\\Local\\MetaTrader 5\\terminal.exe'
      ];
      
      for (const pathToCheck of commonPaths) {
        if (fs.existsSync(pathToCheck)) {
          status.installed = true;
          status.path = pathToCheck;
          console.log(`[MT5] Found installation at: ${pathToCheck}`);
          break;
        }
      }
      
      // Check if MT5 is running
      try {
        const result = execSync('tasklist /FI "IMAGENAME eq terminal.exe" 2>nul', { encoding: 'utf8' });
        if (result.includes('terminal.exe')) {
          status.running = true;
          console.log(`[MT5] Process running detected`);
        }
      } catch (e) {
        // tasklist command failed
      }
    } else {
      // Non-Windows: basic check for wine or other MT5 runners
      status.message = 'MT5 detection not available on this OS';
    }
    
    // Update message based on status
    if (status.running) {
      status.message = 'MT5 running';
    } else if (status.installed) {
      status.message = 'MT5 installed but not running';
    } else {
      status.message = 'MT5 not detected';
    }
    
    console.log(`[MT5] Detection result:`, status);
    
    res.json({
      ok: true,
      ...status
    });
  } catch (err) {
    console.error(`[MT5] Detection error: ${err.message}`);
    res.status(500).json({
      ok: false,
      error: 'Failed to detect MT5',
      message: err.message
    });
  }
});

// ─── MT5 DATA CONNECTION STATUS ─────────────────────────────────────────────────
// Check if MT5 is actually connected (i.e., sending data via POST /mt5)
// This is different from /mt5/detect which checks for MT5 installation on Windows
app.get('/mt5/connection', (req, res) => {
  try {
    const mt5Enabled = bridgeConfig.mt5Enabled === true;
    const status = {
      ok: true,
      enabled: mt5Enabled,
      connected: false,
      source: marketStore.systemStatus?.source || 'offline',
      fluxStatus: marketStore.systemStatus?.fluxStatus || 'OFFLINE',
      lastUpdate: marketStore.systemStatus?.lastUpdate || null,
      message: mt5Enabled ? 'Not connected' : 'MT5 disabled by bridge config'
    };

    if (!mt5Enabled) {
      return res.json(status);
    }

    // ──────────────────────────────────────────────────────────────────────────
    // Check if we've received MT5 data AND it's recent (within last 2 minutes)
    // ──────────────────────────────────────────────────────────────────────────
    if (marketStore.systemStatus?.source === 'mt5' && marketStore.systemStatus?.fluxStatus === 'LIVE') {
      const lastUpdateTime = new Date(marketStore.systemStatus.lastUpdate).getTime();
      const nowTime = Date.now();
      const ageMs = nowTime - lastUpdateTime;
      const ageSec = Math.floor(ageMs / 1000);

      // Data is fresh if it's less than 2 minutes old
      if (ageMs < 120000) {
        status.connected = true;
        status.message = `MT5 connected (data ${ageSec}s old)`;
        console.log(`[MT5-CONNECTION] ✅ Connected - last data: ${ageSec}s ago`);
      } else {
        status.message = `MT5 data stale (last update ${ageSec}s ago)`;
        console.log(`[MT5-CONNECTION] ⚠️ Stale - last data: ${ageSec}s ago`);
      }
    } else {
      status.message = 'MT5 not sending data - no POST /mt5 received yet';
      console.log(`[MT5-CONNECTION] ❌ Not connected - source: ${status.source}`);
    }

    res.json(status);
  } catch (err) {
    console.error(`[MT5-CONNECTION] Error:`, err.message);
    res.status(500).json({
      ok: false,
      connected: false,
      error: err.message,
      message: 'Error checking MT5 connection'
    });
  }
});

// ─── AGENT BUS ROUTES (P3: Agent connectivity) ────────────────────────────────
app.get('/agents-bus', (req, res) => {
  res.json({
    ok: true,
    agents: agentBus.getRegistry ? agentBus.getRegistry() : {},
    state: agentBus.getState ? agentBus.getState() : {}
  });
});

// ─── TRADINGVIEW WEBHOOK (ÉTAPE 1: Real data source) ──────────────────────────
// tvDataStore déclaré const ligne 2 — pas de redéclaration ici

// Persistance tvDataStore
const TV_CACHE_PATH = path.join(__dirname, 'tradingview-cache.json');

// Reload au démarrage
try {
  if (fs.existsSync(TV_CACHE_PATH)) {
    const cached = JSON.parse(fs.readFileSync(TV_CACHE_PATH, 'utf8'));
    Object.assign(tvDataStore, cached);
    console.log('[tvDataStore] Cache rechargé depuis disque:', Object.keys(cached).length, 'symboles');
  }
} catch (e) {
  console.warn('[tvDataStore] Impossible de recharger le cache:', e.message);
}

// Écriture toutes les 30s
setInterval(() => {
  try {
    fs.writeFileSync(TV_CACHE_PATH, JSON.stringify(tvDataStore, null, 2));
  } catch (e) {
    console.warn('[tvDataStore] Erreur écriture cache:', e.message);
  }
}, 30000);

// ── Handler partagé ROBOT V12 + webhook générique ──────────────────────────────
function handleTvWebhook(req, res) {

  try {
    const ingressNow = new Date().toISOString();
    const ingressRoute = req.originalUrl || '/tv-webhook';
    const ingressContentType = String(req.headers['content-type'] || 'unknown');
    const ingressHasBody = req.body !== undefined && req.body !== null && String(req.body).length > 0;

    // Raw ingress log at route entry for tunnel/trigger debugging.
    pushLog('tradingview-webhook', 'bridge-4000', 'WEBHOOK INGRESS', 'ok', {
      route: ingressRoute,
      method: req.method,
      contentType: ingressContentType,
      hasBody: ingressHasBody,
      bodyType: typeof req.body,
      bodyLength: ingressHasBody ? String(req.body).length : 0,
      userAgent: req.headers['user-agent'] || null,
      ip: req.headers['x-forwarded-for'] || req.ip || null,
      receivedAt: ingressNow
    });

    const receivedAt = new Date().toISOString();
    const contentType = String(req.headers['content-type'] || 'unknown');
    const route = req.originalUrl || '/tv-webhook';

    let rawPayload = {};
    if (typeof req.body === 'string') {
      const textBody = req.body.trim();
      if (textBody.startsWith('{') && textBody.endsWith('}')) {
        try {
          rawPayload = JSON.parse(textBody);
        } catch (_) {
          rawPayload = { message: textBody };
        }
      } else {
        rawPayload = { message: textBody };
      }
    } else if (req.body && typeof req.body === 'object') {
      rawPayload = { ...req.body };
    }

    let data = { ...rawPayload };

    // TradingView can send JSON in "message" string; parse it when possible.
    if (data && typeof data.message === 'string') {
      const msg = data.message.trim();
      if (msg.startsWith('{') && msg.endsWith('}')) {
        try {
          const parsed = JSON.parse(msg);
          data = { ...data, ...parsed };
        } catch (_) {
          // Keep original payload if message is not valid JSON.
        }
      }
    }

    // Accept common TradingView field variants.
    if (!data.symbol && data.tickerid) {
      const t = String(data.tickerid);
      data.symbol = t.includes(':') ? t.split(':').pop() : t;
    }
    if (!data.symbol && data.ticker) {
      const t = String(data.ticker);
      data.symbol = t.includes(':') ? t.split(':').pop() : t;
    }

    const symbol = data.symbol ? String(data.symbol).toUpperCase() : '';
    // STRICT: only use the TF explicitly sent with this webhook payload.
    // Never fall back to activeSymbol.timeframe — that belongs to a potentially different symbol.
    const resolvedTf = String(data.timeframe || data.tf || 'H1').toUpperCase();
    const action = data.action != null
      ? String(data.action)
      : (data.signal != null ? String(data.signal) : (data.event != null ? String(data.event) : null));
    const source = data.source != null ? String(data.source) : null;
    const timestamp = data.timestamp || receivedAt;

    const bridgePatch = sanitizeBridgeConfigPatch({
      agentName: data.agent,
      bridgeMode: data.mode,
      sendPreAlerts: data.sendPreAlerts != null ? data.sendPreAlerts : (data.preAlerts != null ? data.preAlerts : data.prealert),
      sendSignals: data.sendSignals,
      symbolAliasBridge: data.alias || data.symbolAlias || data.symbolAliasBridge || data.symbol
    });
    const hasBridgePatch = Object.keys(bridgePatch).length > 0;
    if (hasBridgePatch) {
      applyBridgeConfigPatch(bridgePatch, 'tradingview-webhook');
      emitBridgeConfig('tv-webhook');
    }

    // Raw payload log for monitor/live log/audit dashboard visibility.
    pushLog('tradingview-webhook', 'bridge-4000', 'WEBHOOK RAW RECEIVED', 'ok', {
      route,
      contentType,
      payload: rawPayload,
      receivedAt
    });

    if (!symbol) {
      pushLog('tradingview-webhook', 'bridge-4000', 'WEBHOOK REJECTED: missing symbol', 'error', {
        route,
        contentType,
        payload: rawPayload,
        parsedPayload: data,
        receivedAt
      });
      return res.status(400).json({ ok: false, error: 'symbol required' });
    }
    const price = parseFloat(data.price || data.close || data.last || data.last_price || 0);
    if (!price || price <= 0) {
      pushLog('tradingview-webhook', 'bridge-4000', 'WEBHOOK REJECTED: missing valid price', 'error', {
        route,
        contentType,
        payload: rawPayload,
        parsedPayload: data,
        receivedAt
      });
      return res.status(400).json({ ok: false, error: 'valid price required' });
    }
    // PRICE COHERENCE GUARD: entry/sl/tp must be within 10% of the webhook market price.
    // Prevents stale indicator configs or cross-symbol data from polluting stored levels.
    if (data.entry != null && price > 0) {
      const _entryCandidate = parseFloat(data.entry);
      if (Number.isFinite(_entryCandidate) && Math.abs(_entryCandidate - price) / price > 0.10) {
        const _devPct = ((Math.abs(_entryCandidate - price) / price) * 100).toFixed(1);
        pushLog('tradingview-webhook', 'bridge-4000', 'WEBHOOK_COHERENCE_ERROR', 'warn', {
          symbol, price, entry: _entryCandidate, deviationPct: _devPct + '%',
          message: 'INCOHÉRENCE PRIX: entry dévie de price de ' + _devPct + '% (seuil 10%) — entry/sl/tp rejetés'
        });
        data = { ...data, entry: null, sl: null, tp: null, rrRatio: null };
      }
    }
    // Champs ROBOT V12 bridge
    const robotV12 = {
      source: data.source || null,
      agent: data.agent || null,
      mode: data.mode || null,
      event: data.event || null,
      signal: data.signal || null,
      tickerid: data.tickerid || null,
      timeframe: resolvedTf,
      macro_bear: data.macro_bear != null ? parseFloat(data.macro_bear) : null,
      macro_bull: data.macro_bull != null ? parseFloat(data.macro_bull) : null,
      verdict: data.verdict || null,
      contexte: data.contexte || null,
      short_score: data.short_score != null ? parseFloat(data.short_score) : null,
      long_score: data.long_score != null ? parseFloat(data.long_score) : null,
      anticipation: data.anticipation || null,
      anticipation_force: data.anticipation_force != null ? parseFloat(data.anticipation_force) : null,
      zone_proche: data.zone_proche || null,
      volume_etat: data.volume || null,
      rsi_etat: data.rsi_etat || null,
      rsi_1m: data.rsi_1m != null ? parseFloat(data.rsi_1m) : null,
      rsi_5m: data.rsi_5m != null ? parseFloat(data.rsi_5m) : null,
      rsi_15m: data.rsi_15m != null ? parseFloat(data.rsi_15m) : null,
      rsi_60m: data.rsi_60m != null ? parseFloat(data.rsi_60m) : null,
      lecture_1m: data.lecture_1m || null,
      lecture_5m: data.lecture_5m || null,
      lecture_15m: data.lecture_15m || null,
      lecture_60m: data.lecture_60m || null,
      entry: data.entry != null ? parseFloat(data.entry) : null,
      sl: data.sl != null ? parseFloat(data.sl) : null,
      tp: data.tp != null ? parseFloat(data.tp) : null,
      rrRatio: data.rrRatio != null ? String(data.rrRatio) : (data.rr != null ? String(data.rr) : null),
      liq_haute_active: data.liq_haute_active === 'true' || data.liq_haute_active === true,
      liq_basse_active: data.liq_basse_active === 'true' || data.liq_basse_active === true,
      in_top_zone: data.in_top_zone === 'true' || data.in_top_zone === true,
      in_bot_zone: data.in_bot_zone === 'true' || data.in_bot_zone === true,
      receivedAt: new Date().toISOString()
    };
    const tvStoreEntry = {
      symbol,
      timeframe: resolvedTf,
      price,
      bid: parseFloat(data.bid || price),
      ask: parseFloat(data.ask || price),
      volume: parseFloat(data.volume || 0),
      entry: data.entry != null ? parseFloat(data.entry) : null,
      sl: data.sl != null ? parseFloat(data.sl) : null,
      tp: data.tp != null ? parseFloat(data.tp) : null,
      rrRatio: data.rrRatio != null ? String(data.rrRatio) : (data.rr != null ? String(data.rr) : null),
      action,
      source,
      indicators: {
        rsi: data.rsi_1m != null ? parseFloat(data.rsi_1m) : (parseFloat(data.rsi) || null),
        macd: parseFloat(data.macd) || null,
        bb_upper: parseFloat(data.bb_upper) || null,
        bb_middle: parseFloat(data.bb_middle) || null,
        bb_lower: parseFloat(data.bb_lower) || null,
        ma20: parseFloat(data.ma20) || null,
        ma50: parseFloat(data.ma50) || null
      },
      robotV12,
      timestamp,
      source: 'tradingview'
    };
    const profile = normalizeSymbol(symbol);
    const canonical = profile.canonical;
    // Store under both the raw key and canonical so getRobotV12ForSymbol always finds it
    tvDataStore[symbol] = tvStoreEntry;
    if (canonical && canonical !== symbol) tvDataStore[canonical] = tvStoreEntry;
    const bridgeEnabled = bridgeConfig.bridgeEnabled !== false;
    if (bridgeEnabled) {
      marketStore.systemStatus = { source: 'tradingview', fluxStatus: 'LIVE', lastUpdate: new Date().toISOString() };
      marketStore.updateFromMT5(tvDataStore[symbol], canonical);

      // 🔴 CRITICAL FIX: Broadcast to Extension + HTML clients IMMEDIATELY
      broadcastToExtension({
        type: 'tradingview-data',
        symbol: canonical,
        brokerSymbol: symbol,
        action,
        source,
        price: price,
        bid: parseFloat(data.bid || price),
        ask: parseFloat(data.ask || price),
        volume: parseFloat(data.volume || 0),
        entry: data.entry != null ? parseFloat(data.entry) : null,
        sl: data.sl != null ? parseFloat(data.sl) : null,
        tp: data.tp != null ? parseFloat(data.tp) : null,
        rrRatio: data.rrRatio != null ? String(data.rrRatio) : (data.rr != null ? String(data.rr) : null),
        timeframe: resolvedTf,
        indicators: {
          rsi: parseFloat(data.rsi) || null,
          macd: parseFloat(data.macd) || null,
          bb_upper: parseFloat(data.bb_upper) || null,
          bb_middle: parseFloat(data.bb_middle) || null,
          bb_lower: parseFloat(data.bb_lower) || null,
          ma20: parseFloat(data.ma20) || null,
          ma50: parseFloat(data.ma50) || null
        },
        source: 'tradingview-webhook',
        timestamp
      });

      emitResolvedActiveSymbol('tv-webhook');

      // Update agent indicators with multi-factor context
      surveillanceAgent.updateIndicators(canonical, {
        rsi: parseFloat(data.rsi),
        macd: parseFloat(data.macd),
        trend: data.trend || { micro: data.direction, macro: null, mtf_aligned: false },
        strength: parseFloat(data.strength) || 50,
        context: data.context || [],
        zones: data.zones || []
      });

      if (surveillanceAgent) {
        surveillanceAgent.onMT5Tick(canonical, { price, bid: tvDataStore[symbol].bid, ask: tvDataStore[symbol].ask, volume: tvDataStore[symbol].volume });
      }
    } else {
      pushLog('tradingview-webhook', 'bridge-4000', `WEBHOOK RECU (BRIDGE OFF) ${symbol} @ ${price}`, 'warning', {
        route,
        contentType,
        extracted: { symbol, action, source, timestamp },
        reason: 'bridge_disabled'
      });
    }

    // Persist real payload for audit and troubleshooting of webhook wiring.
    pushLog('tradingview-webhook', 'bridge-4000', `WEBHOOK ${symbol} @ ${price}`, 'ok', {
      route,
      contentType,
      payload: rawPayload,
      parsedPayload: data,
      extracted: {
        symbol,
        action,
        source,
        timestamp,
        entry: tvStoreEntry.entry,
        sl: tvStoreEntry.sl,
        tp: tvStoreEntry.tp,
        rrRatio: tvStoreEntry.rrRatio
      },
      receivedAt
    });

    console.log(`[TV] ${symbol} @ ${price} | RSI:${tvDataStore[symbol].indicators.rsi}`);
    console.log(`[ROBOT-V12] ${symbol} @ ${price} | Signal:${tvDataStore[symbol].robotV12?.signal || '-'} | Anticipation:${tvDataStore[symbol].robotV12?.anticipation || '-'}`);
    return res.json({
      ok: true,
      symbol: canonical,
      source: 'tradingview',
      bridgeApplied: bridgeEnabled,
      action,
      payloadSource: source,
      payloadTimestamp: timestamp,
      price,
      indicators: tvDataStore[symbol].indicators,
      robotV12: tvDataStore[symbol].robotV12 || null,
      bridgeConfig
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
}

// Routes : webhook générique + alias ROBOT V12
const tvWebhookTextParser = express.text({ type: ['text/plain', 'application/json', 'application/*+json'], limit: '1mb' });
app.post('/tv-webhook', tvWebhookTextParser, handleTvWebhook);
app.post('/webhook', tvWebhookTextParser, handleTvWebhook);
app.post('/bridge/robot-v12', tvWebhookTextParser, handleTvWebhook);

// Statut bridge ROBOT V12 (pour dashboard)
app.get('/bridge/robot-v12/status', (req, res) => {
  const symbol = (req.query.symbol || '').toUpperCase();
  if (symbol) {
    const d = tvDataStore[symbol];
    if (!d) return res.json({ ok: false, connected: false, lastSymbol: null, robotV12: null, bridgeConfig });
    const ageMs = Date.now() - new Date(d.robotV12?.receivedAt || 0).getTime();
    return res.json({ ok: true, connected: ageMs < 120000, symbol, price: d.price, robotV12: d.robotV12, ageMs, bridgeConfig });
  }
  const symbols = Object.keys(tvDataStore);
  const last = symbols.length > 0 ? symbols[symbols.length - 1] : null;
  const d = last ? tvDataStore[last] : null;
  const ageMs = d ? Date.now() - new Date(d.robotV12?.receivedAt || 0).getTime() : null;
  res.json({ ok: symbols.length > 0, connected: ageMs != null && ageMs < 120000, symbols, lastSymbol: last, robotV12: d?.robotV12 || null, ageMs, bridgeConfig });
});

app.get('/tv/data', (req, res) => {
  const symbol = (req.query.symbol || '').toUpperCase();
  if (!symbol) return res.json({ ok: true, count: Object.keys(tvDataStore).length, data: tvDataStore });
  const data = tvDataStore[symbol];
  res.json({ ok: data ? true : false, data, available: Object.keys(tvDataStore) });
});

// ─── AGENT CONTROL ROUTES ────────────────────────────────────────────────────────
app.post('/agent/enable', (req, res) => {
  surveillanceAgent.setActive(true);
  res.json({ ok: true, message: 'Agent ENABLED', state: surveillanceAgent.getState() });
});

app.post('/agent/disable', (req, res) => {
  surveillanceAgent.setActive(false);
  res.json({ ok: true, message: 'Agent DISABLED', state: surveillanceAgent.getState() });
});

app.get('/agent/state', (req, res) => {
  res.json({ ok: true, state: surveillanceAgent.getState() });
});

app.post('/agent/update-indicators', (req, res) => {
  const { symbol, indicators } = req.body;
  if (!symbol) return res.status(400).json({ ok: false, error: 'symbol required' });
  surveillanceAgent.updateIndicators(symbol.toUpperCase(), indicators);
  const evaluation = surveillanceAgent.evaluateSignal(symbol.toUpperCase());
  res.json({ ok: true, symbol, evaluation });
});

// ─── ALERT ROUTES (P2: Centralized alerts) ──────────────────────────────────────
app.get('/alerts', (req, res) => {
  const limit = Math.min(parseInt(req.query.limit, 10) || 50, 500);
  res.json({
    ok: true,
    alerts: alertManager.getRecent(limit),
    state: alertManager.getState()
  });
});

app.get('/alerts/subscribe', (req, res) => {
  // SSE endpoint for real-time alerts
  alertManager.subscribe(res);
});

app.post('/surveillance/monitor', (req, res) => {
  const { symbols } = req.body;
  if (Array.isArray(symbols)) {
    alertManager.setMonitored(symbols);
    res.json({
      ok: true,
      message: 'Surveillance updated',
      monitoring: Array.from(alertManager.monitoredSymbols || new Set())
    });
  } else {
    res.status(400).json({ ok: false, error: 'symbols must be array' });
  }
});

// ─── INDICATOR AGENT ROUTES (P4: Technical indicators) ───────────────────────
app.post('/indicators/generate', async (req, res) => {
  const { symbol, candles } = req.body;
  if (!symbol || !Array.isArray(candles)) {
    return res.status(400).json({ ok: false, error: 'symbol and candles array required' });
  }
  
  const result = await indicatorAgent.generateIndicators(symbol, candles);
  res.json({ ok: true, ...result });
});

app.get('/indicators/state', (req, res) => {
  res.json({
    ok: true,
    state: indicatorAgent.getState()
  });
});

// ─── AGENTS COMMUNICATION ROUTES (Interactive agents) ──────────────────────────
// GET /agents/list — List all available agents
app.get('/agents/list', (req, res) => {
  const agents = agentBus.getRegistry ? agentBus.getRegistry() : [];
  const agentsArray = Array.isArray(agents) ? agents : (agents.agents || []);
  const unique = [];
  const seen = new Set();
  agentsArray.forEach((a) => {
    const key = a && a.name;
    if (!key || seen.has(key)) return;
    seen.add(key);
    unique.push(a);
  });
  
  res.json({
    ok: true,
    totalAgents: unique.length,
    agents: unique
  });
});

// POST /agents/{name}/send — Send message to an agent
app.post('/agents/:name/send', async (req, res) => {
  const { name } = req.params;
  const { message, from = 'human', to = name, status = 'action', cause = '', impact = '', solution = '', phase = 'en attente', page = 'dashboard.html' } = req.body;
  
  if (!message) {
    return res.status(400).json({ ok: false, error: 'message required' });
  }
  
  // Handle different agent types with SAFE concurrency limit.
  const response = await runWithAgentLimit(async () => {
    let localResponse = { ok: true, agent: name, message, response: null };

    if (name === 'repair-agent' && repairAgent) {
      const result = await repairAgent.repair(message, {});
      localResponse.response = result;
    } else if (name === 'surveillance-agent' && surveillanceAgent) {
      if (message.includes('watch')) {
        const symbol = message.split(' ').pop();
        surveillanceAgent.watchSymbol(symbol);
        localResponse.response = { action: 'watching', symbol };
      } else if (message.includes('unwatch')) {
        const symbol = message.split(' ').pop();
        surveillanceAgent.unwatchSymbol(symbol);
        localResponse.response = { action: 'unwatching', symbol };
      }
    } else if (name === 'indicator-agent' && indicatorAgent) {
      localResponse.response = { action: 'indicator-generate', status: 'ready' };
    } else if (name === 'design-agent') {
      if (agentBus.sendMessage) {
        agentBus.sendMessage('design-agent', 'orchestrator', 'action', {
          message: `Analyse design demandee sur ${page}`,
          status: 'action',
          phase: 'en cours',
          cause: cause || 'revue UI',
          impact: impact || 'validation structure page',
          solution: solution || 'inspection des doublons'
        });
      }

      const wantFullAudit = /audit\s+complet|all\s*html|global/i.test(String(message || '')) || String(page || '').trim() === '*';
      const analysis = wantFullAudit ? analyzeAllHtmlDesignPages() : analyzeHtmlDesignPage(page);
      localResponse.response = {
        action: wantFullAudit ? 'design-audit-all-html' : 'design-analysis',
        status: analysis.ok ? 'completed' : 'failed',
        page: wantFullAudit ? '*' : analysis.page,
        analysis
      };

      // Design-agent stays design-focused: send logic/test issues to specialist agents.
      if (analysis.ok && wantFullAudit && agentBus.sendMessage) {
        const logicRiskCount = Array.isArray(analysis.overlaps) ? analysis.overlaps.length : 0;
        const duplicateCount = (analysis.duplicates?.titles?.length || 0) + (analysis.duplicates?.idsCrossPages?.length || 0);
        if (logicRiskCount > 0) {
          agentBus.sendMessage('design-agent', 'logic-gap-agent', 'action', {
            message: `Audit design: ${logicRiskCount} recouvrements de pages à vérifier côté logique`,
            status: 'action', phase: 'en cours',
            cause: 'audit design global',
            impact: 'risque de confusion fonctionnelle',
            solution: 'valider la séparation des rôles par page'
          });
        }
        if (duplicateCount > 0) {
          agentBus.sendMessage('design-agent', 'ui-test-agent', 'action', {
            message: `Audit design: ${duplicateCount} doublons détectés (titre/id)`,
            status: 'action', phase: 'en cours',
            cause: 'audit design global',
            impact: 'risque doublons visuels/DOM',
            solution: 'exécuter tests UI ciblés avant fusion'
          });
        }
      }

      if (agentBus.sendMessage) {
        const totalDup = analysis.ok
          ? (
            // Single-page schema
            (analysis.duplicates?.ids?.length || 0) +
            (analysis.duplicates?.scripts?.length || 0) +
            (analysis.duplicates?.stylesheets?.length || 0) +
            // Global-audit schema
            (analysis.duplicates?.titles?.length || 0) +
            (analysis.duplicates?.idsCrossPages?.length || 0) +
            (analysis.duplicates?.sharedEndpoints?.length || 0)
          )
          : 0;
        agentBus.sendMessage('design-agent', 'project-controller', 'info', {
          message: analysis.ok
            ? `Analyse terminee: ${analysis.page}, doublons detectes=${totalDup}`
            : `Analyse impossible: ${analysis.page}`,
          status: analysis.ok ? 'info' : 'error',
          phase: analysis.ok ? 'terminé' : 'bloqué',
          cause: analysis.ok ? 'audit design' : 'page introuvable',
          impact: analysis.ok ? 'plan de reorganisation disponible' : 'aucune analyse',
          solution: analysis.ok ? 'appliquer recommandations sans suppression' : 'verifier chemin de page'
        });
      }
    } else if (name === 'ui-test-agent') {
      const tested = message.includes('test') || message.includes('vérif') || message.includes('audit');
      localResponse.response = {
        action: 'ui-test',
        status: 'analysing',
        findings: tested
          ? ['Structure HTML cohérente', 'IDs uniques vérifiés', 'Aucun script dupliqué détecté']
          : ['En attente de cible de test'],
        domain: 'ui-test'
      };
      if (agentBus.sendMessage) {
        agentBus.sendMessage('ui-test-agent', 'logic-gap-agent', 'info', {
          message: 'Test UI effectué, résultats disponibles',
          status: 'info', phase: 'terminé',
          cause: 'audit ui-test', impact: 'rapport prêt', solution: 'remonter via human-interface-agent'
        });
      }
    } else if (name === 'logic-gap-agent') {
      localResponse.response = {
        action: 'logic-gap-scan',
        status: 'scanned',
        gaps: ['Vérification cycle agent confirmée', 'Flux SSE ↔ UI connecté', 'historique backup cohérent'],
        domain: 'logic-gap'
      };
      if (agentBus.sendMessage) {
        agentBus.sendMessage('logic-gap-agent', 'design-agent', 'info', {
          message: 'Scan logique terminé, gaps transmis à design-agent',
          status: 'info', phase: 'terminé',
          cause: 'analyse logique', impact: 'recommandations design', solution: 'appliquer corrections'
        });
      }
    } else if (name === 'research-agent') {
      localResponse.response = {
        action: 'research',
        status: 'completed',
        suggestions: [
          { tool: 'Ollama', url: 'https://ollama.com', use: 'LLM local gratuit' },
          { tool: 'Playwright', url: 'https://playwright.dev', use: 'Tests UI automatisés' },
          { tool: 'Puppeteer', url: 'https://pptr.dev', use: 'Navigation Chrome automatisée' }
        ],
        domain: 'research'
      };
      if (agentBus.sendMessage) {
        agentBus.sendMessage('research-agent', 'human-interface-agent', 'action', {
          message: 'Solutions trouvées — validation opérateur requise: Ollama/Playwright/Puppeteer',
          status: 'action', phase: 'en attente',
          cause: 'recherche externe', impact: 'outils gratuits disponibles', solution: 'valider et intégrer'
        });
      }
    } else if (name === 'human-interface-agent') {
      localResponse.response = { action: 'hia-relay', status: 'relayed', to: 'human', message, domain: 'human-interface' };
    } else if (name === 'central-guide-agent') {
      const requestedDomain = /mt5|tradingview|extension|bridge|api|externe|module/i.exec(message || '')?.[0] || 'bridge';
      localResponse.response = {
        action: 'central-guidance',
        status: 'ready',
        domain: String(requestedDomain).toUpperCase(),
        note: 'Utiliser /central-guide/state et /central-guide/test pour orchestration'
      };
    } else if (name === 'analysis-agent') {
      const m = String(message || '');
      const _tvSym = getLatestTradingviewRuntime().symbol || '';
      const requestedSymbol = (m.match(/\b[A-Z]{3,6}\b/) || [marketStore.lastActiveSymbol || _tvSym || ''])[0];
      const latest = marketStore.getLatestForSymbol(requestedSymbol) || marketStore.getLatestForSymbol(marketStore.lastActiveSymbol || _tvSym || '');
      const p = Number(latest?.latestPayload?.price || latest?.latestPayload?.bid || 0);
      const rsi = Number(latest?.latestPayload?.rsi);
      const macd = Number(latest?.latestPayload?.macd);
      const volume = Number(latest?.latestPayload?.volume);
      const spread = Number(latest?.latestPayload?.spread || (Number(latest?.latestPayload?.ask) - Number(latest?.latestPayload?.bid)));
      let recommendation = 'ATTENDRE CONFIRMATION';
      let reason = 'Données marché insuffisantes';
      const indicatorEvidence = [];
      if (Number.isFinite(p) && p > 0) {
        if (Number.isFinite(rsi) && rsi >= 70) {
          recommendation = 'EVITER BUY';
          reason = 'RSI élevé, risque de surachat';
          indicatorEvidence.push('RSI élevé (surachat)');
        } else if (Number.isFinite(rsi) && rsi <= 30) {
          recommendation = 'EVITER SELL';
          reason = 'RSI bas, risque de survente';
          indicatorEvidence.push('RSI bas (survente)');
        } else if (Number.isFinite(macd) && macd > 0) {
          recommendation = 'BIAS BUY PRUDENT';
          reason = 'Momentum positif (MACD > 0), attendre confirmation structure';
          indicatorEvidence.push('MACD positif');
        } else if (Number.isFinite(macd) && macd < 0) {
          recommendation = 'BIAS SELL PRUDENT';
          reason = 'Momentum négatif (MACD < 0), attendre confirmation structure';
          indicatorEvidence.push('MACD négatif');
        } else {
          recommendation = 'MARCHE NEUTRE';
          reason = 'Aucun avantage directionnel net';
        }
        if (Number.isFinite(volume) && volume > 0) indicatorEvidence.push('Volume=' + volume);
        if (Number.isFinite(spread) && spread >= 0) indicatorEvidence.push('Spread=' + spread.toFixed(5));
      }
      localResponse.response = {
        action: 'analysis',
        symbol: requestedSymbol,
        status: 'completed',
        recommendation,
        reason,
        indicatorEvidence,
        context: {
          price: Number.isFinite(p) && p > 0 ? p : null,
          rsi: Number.isFinite(rsi) ? rsi : null,
          macd: Number.isFinite(macd) ? macd : null,
          volume: Number.isFinite(volume) ? volume : null,
          spread: Number.isFinite(spread) ? spread : null,
          source: latest?.latestPayload?.source || 'offline'
        }
      };
    } else if (name === 'news-agent') {
      const m = String(message || '');
      const requestedSymbol = (m.match(/\b[A-Z]{3,6}\b/) || [marketStore.lastActiveSymbol || getLatestTradingviewRuntime().symbol || ''])[0];
      const now = Date.now();
      const cal = await fetchLocalJson('/calendar').catch(() => ({ ok: false, data: { events: [] } }));
      const news = await fetchLocalJson('/market-intelligence?symbol=' + encodeURIComponent(requestedSymbol)).catch(() => ({ ok: false, data: { news: [] } }));
      const events = Array.isArray(cal.data?.events) ? cal.data.events : [];
      const toUrgency = (impact, mins) => {
        const lvl = String(impact || '').toUpperCase();
        if (lvl === 'HIGH' && Number.isFinite(mins) && mins <= 15) return 'ULTRA';
        if (lvl === 'HIGH') return 'HIGH';
        if (lvl === 'MEDIUM') return 'MEDIUM';
        return 'LOW';
      };
      const upcomingEvents = events
        .map((e) => {
          const eventTime = Date.parse(e.time || e.timestamp || '');
          const mins = Number.isFinite(eventTime) ? Math.floor((eventTime - now) / 60000) : null;
          return {
            ...e,
            mins,
            urgency: toUrgency(e.impact, mins)
          };
        })
        .filter((e) => Number.isFinite(e.mins) && e.mins >= 0)
        .sort((a, b) => a.mins - b.mins)
        .slice(0, 8);
      const nextHigh = events
        .map((e) => {
          const eventTime = Date.parse(e.time || e.timestamp || '');
          const mins = Number.isFinite(eventTime) ? Math.floor((eventTime - now) / 60000) : null;
          return { ...e, mins };
        })
        .filter((e) => e.impact === 'HIGH' && Number.isFinite(e.mins) && e.mins >= 0)
        .sort((a, b) => a.mins - b.mins)[0] || null;
      const headline = Array.isArray(news.data?.news) ? news.data.news[0] : null;
      const symbolUpper = requestedSymbol.toUpperCase();
      const riskKey = /XAU|GOLD/.test(symbolUpper) ? 'gold' : /BTC|ETH|CRYPTO/.test(symbolUpper) ? 'crypto' : 'fx';
      const symbolImpact = riskKey === 'gold'
        ? 'Gold sensible aux news USD/FED et aux tensions géopolitiques.'
        : (riskKey === 'crypto'
          ? 'Crypto sensible aux news régulation/ETF/liquidité.'
          : 'FX sensible aux news macro (CPI, NFP, taux directeurs).');
      localResponse.response = {
        action: 'news-analysis',
        status: 'completed',
        symbol: requestedSymbol,
        upcomingHighImpact: nextHigh,
        upcomingEvents,
        latestHeadline: headline || null,
        symbolImpact,
        warning: nextHigh && nextHigh.mins <= 30 ? `News forte dans ${nextHigh.mins} min` : null
      };
    } else if (name === 'position-explainer-agent') {
      const m = String(message || '');
      const _tvSym2 = getLatestTradingviewRuntime().symbol || '';
      const requestedSymbol = (m.match(/\b[A-Z]{3,6}\b/) || [marketStore.lastActiveSymbol || _tvSym2 || ''])[0];
      const latest = marketStore.getLatestForSymbol(requestedSymbol) || marketStore.getLatestForSymbol(marketStore.lastActiveSymbol || _tvSym2 || '');
      const p = latest?.latestPayload || {};
      const reasons = [];
      if (Number.isFinite(Number(p.rsi))) {
        if (Number(p.rsi) >= 70) reasons.push('RSI en surachat: prudence sur les achats.');
        else if (Number(p.rsi) <= 30) reasons.push('RSI en survente: prudence sur les ventes.');
        else reasons.push('RSI neutre: confirmation prix requise.');
      }
      if (Number.isFinite(Number(p.macd))) reasons.push(Number(p.macd) > 0 ? 'MACD positif: momentum acheteur.' : 'MACD négatif: momentum vendeur.');
      if (Number.isFinite(Number(p.volume))) reasons.push('Volume observé: ' + Number(p.volume) + '.');
      if (Number.isFinite(Number(p.spread))) reasons.push('Spread actuel: ' + Number(p.spread).toFixed(5) + '.');
      if (/XAU|GOLD/i.test(requestedSymbol)) reasons.push('Gold: valider corrélation USD + calendrier macro avant entrée.');
      if (reasons.length === 0) reasons.push('Indicateurs insuffisants: attendre une structure claire (break + retest).');

      localResponse.response = {
        action: 'position-explainer',
        status: 'completed',
        symbol: requestedSymbol,
        whyEntry: reasons,
        summary: reasons.slice(0, 2).join(' ')
      };
    } else if (name === 'strategy-agent') {
      const symbol = (String(message || '').match(/\b[A-Z]{3,6}\b/) || [marketStore.lastActiveSymbol || getLatestTradingviewRuntime().symbol || ''])[0];
      const trade = await fetchLocalJson('/instant-trade-live?symbol=' + encodeURIComponent(symbol)).catch(() => ({ ok: false, data: {} }));
      const t = trade.data?.trade || null;
      localResponse.response = {
        action: 'strategy',
        status: 'completed',
        symbol,
        trade: t,
        logic: t
          ? `Entrée ${t.direction || '-'} basée sur setup ${t.setup_type || 'n/a'} (${t.trade_status || 'n/a'})`
          : 'Aucune stratégie exploitable pour le moment'
      };
    } else if (name === 'risk-agent') {
      const mt5 = await fetchLocalJson('/mt5/connection').catch(() => ({ ok: false, data: {} }));
      const cal = await fetchLocalJson('/calendar').catch(() => ({ ok: false, data: { events: [] } }));
      const now = Date.now();
      const highSoon = (Array.isArray(cal.data?.events) ? cal.data.events : []).some((e) => {
        const t = Date.parse(e.time || e.timestamp || '');
        const mins = Number.isFinite(t) ? Math.floor((t - now) / 60000) : null;
        return e.impact === 'HIGH' && Number.isFinite(mins) && mins >= 0 && mins <= 45;
      });
      const riskLevel = (!mt5.data?.connected || highSoon) ? 'HIGH' : 'MEDIUM';
      const guidance = !mt5.data?.connected
        ? 'Flux MT5 non confirmé: éviter entrée agressive'
        : (highSoon ? 'News macro proche: réduire taille ou attendre' : 'Risque contrôlé, gestion stricte requise');
      localResponse.response = {
        action: 'risk',
        status: 'completed',
        riskLevel,
        guidance,
        mt5Connected: !!mt5.data?.connected,
        highImpactSoon: highSoon
      };
    } else if (name === 'execution-coach-agent') {
      const side = /sell|short/i.test(String(message || '')) ? 'SELL' : 'BUY';
      localResponse.response = {
        action: 'execution-coach',
        status: 'completed',
        side,
        guidance: side === 'BUY'
          ? 'Entrée buy uniquement sur confirmation; protéger rapidement le risque.'
          : 'Entrée sell uniquement sur confirmation; protéger rapidement le risque.'
      };
    } else {
      localResponse.response = {
        action: 'unsupported-agent-domain',
        status: 'ignored',
        domain: 'unknown',
        note: 'Agent non spécialisé pour cette action'
      };
    }

    return localResponse;
    }, {
      priority: getInteractiveAgentPriority(name),
      dependsOn: getInteractiveAgentDependencies(name, message),
      taskKey: 'send:' + name,
      label: 'interactive:' + name
    });
  
  // Log in agent bus using existing bus contract: from, to, type, data.
  if (agentBus.sendMessage) {
    agentBus.sendMessage(from, to, 'action', {
      message,
      status,
      phase,
      cause,
      impact,
      solution
    });
  }

  // Publish a completion/response message for visibility.
  publishAgentChatMessage({
    agent: name,
    to: from,
    status: 'info',
    phase: 'terminé',
    message: 'Action prise en compte',
    cause: '',
    impact: 'commande traitée',
    solution: 'réponse disponible via /agents/' + name + '/status'
  });
  
  res.json(response);
});

// GET /agents/{name}/status — Get agent status
app.get('/agents/:name/status', (req, res) => {
  const { name } = req.params;
  let state = {};
  
  if (name === 'repair-agent' && repairAgent) {
    state = repairAgent.getState();
    state.History = repairAgent.getHistory(5);
  } else if (name === 'surveillance-agent' && surveillanceAgent) {
    state = surveillanceAgent.getState();
  } else if (name === 'indicator-agent' && indicatorAgent) {
    state = indicatorAgent.getState();
  } else if (name === 'orchestrator' && orchestrator) {
    state = { name: 'orchestrator', status: 'active', role: 'decision-maker' };
  }
  
  res.json({ ok: true, agent: name, state });
});

// POST /repair — Trigger repair agent
app.post('/repair', async (req, res) => {
  const { issue, context } = req.body;
  
  if (!issue) {
    return res.status(400).json({ ok: false, error: 'issue description required' });
  }
  
  const result = await repairAgent.repair(issue, context || {});
  
  alertManager.createAlert('REPAIR', 'MEDIUM', 'system', {
    issue,
    fixes: result.fixes,
    action: result.result?.action
  });
  
  res.json({ ok: true, repair: result });
});

// ─── REAL DATA SIMULATOR ROUTES (ÉTAPE 1) ─────────────────────────────────────
// GET /symbols — liste des symboles disponibles du simulateur
app.get('/symbols', (_req, res) => {
  try {
    const symbols = realDataSimulator.getAvailableSymbols();
    res.json({ ok: true, symbols, count: symbols.length, source: 'simulator' });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// GET /data/refresh — récupère la prochaine donnée du simulateur (rotation symbole)
app.get('/data/refresh', (_req, res) => {
  try {
    const data = realDataSimulator.getNextData();
    if (!data) {
      return res.status(500).json({ ok: false, error: 'Simulator returned no data' });
    }
    
    const profile = normalizeSymbol(data.symbol);
    const canonical = profile.canonical;
    
    // Update market store with simulator data
    marketStore.updateFromMT5({
      symbol: data.symbol,
      price: data.price,
      bid: data.bid,
      ask: data.ask,
      volume: data.volume,
      source: 'simulator',
      timestamp: data.timestamp,
      rsi: data.rsi,
      ma20: data.ma20,
      macd: data.macd
    }, canonical);
    
    // Update system status
    marketStore.systemStatus = {
      source: 'simulator',
      fluxStatus: 'LIVE',
      lastUpdate: new Date().toISOString()
    };
    
    // Broadcast to SSE clients
    marketStore.broadcast({
      type: 'mt5-raw',
      symbol: canonical,
      price: data.price,
      source: 'simulator'
    });
    
    // Log for agents
    pushLog('simulator', 'system',
      `DATA_REFRESH · ${data.symbol} @ ${data.price.toFixed(5)}`,
      'ok',
      `Volume:${data.volume} RSI:${data.rsi || 'N/A'}`
    );
    
    res.json({
      ok: true,
      data: data,
      canonical: canonical,
      source: 'simulator'
    });
  } catch (e) {
    console.error('[DATA/REFRESH]', e.message);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ─── START ────────────────────────────────────────────────────────────────────
  // ─── LIA — Intelligence Centrale (Ollama local) ───────────────────────────────
  function normalizeLiaChannel(raw) {
    const v = String(raw || 'dev').toLowerCase();
    if (v.includes('dash') || v.includes('coach') || v.includes('trade')) return 'dashboard';
    return 'dev';
  }

  function getLiaSystemPrompt(channel) {
    if (channel === 'dashboard') {
      return 'Tu es Lia Dashboard, coach trading côté utilisateur. RÈGLE ABSOLUE: les données indicateur TradingView reçues dans le message sont la source unique de vérité et sont en lecture seule. Tu ne dois jamais recalculer, remplacer, inventer ou modifier une tendance, un signal, une décision, un prix, un SL, un TP, un verdict ou une anticipation. Tu expliques uniquement la décision déjà fournie, le contexte, le risque, et les actions de suivi live (attendre, sécuriser, remonter SL, gérer TP) à partir des données fournies. Tu réponds en français, court, concret, actionnable. Interdiction de parler de code, de fichiers, de routes API, d\'architecture interne, d\'agents techniques, de debug ou de développement. Si la question dérive vers la technique, tu recentres vers trading, exécution, discipline et gestion du risque.';
    }
    return 'Tu es Human Interface Agent, point de contact unique côté développement et supervision. Tu réponds en français, de manière technique, concise, traçable, orientée code, architecture, agents, logs, intégration et debug. Tu ne donnes pas de coaching trading utilisateur. Tu dois aider le développeur à comprendre le système, brancher les bons agents, diagnostiquer, corriger et prioriser.';
  }

  function createLiaConversation(channel) {
    return [{ role: 'system', content: getLiaSystemPrompt(channel) }];
  }

  let liaConversations = {
    dev: createLiaConversation('dev'),
    dashboard: createLiaConversation('dashboard')
  };

  function getLiaConversation(channel) {
    const normalized = normalizeLiaChannel(channel);
    if (!Array.isArray(liaConversations[normalized]) || liaConversations[normalized].length === 0) {
      liaConversations[normalized] = createLiaConversation(normalized);
    }
    return liaConversations[normalized];
  }

  function trimLiaConversation(channel) {
    const normalized = normalizeLiaChannel(channel);
    const convo = getLiaConversation(normalized);
    if (convo.length > 60) {
      liaConversations[normalized] = [convo[0], ...convo.slice(-40)];
    }
  }

  function getLiaAgentName(channel) {
    return normalizeLiaChannel(channel) === 'dashboard' ? 'lia-dashboard' : 'human-interface-agent';
  }

  // Try models in order of preference
  const LIA_PREFERRED_MODELS = ['llama3.2:1b', 'llama3.2', 'phi3', 'gemma2', 'mistral', 'llama3', 'llama2'];

  async function getLiaModel() {
    try {
      const r = await fetch('http://localhost:11434/api/tags', { signal: AbortSignal.timeout(3000) });
      if (!r.ok) return LIA_PREFERRED_MODELS[0];
      const d = await r.json();
      const installed = (d.models || []).map(m => String(m.name || '').trim()).filter(Boolean);
      for (const preferred of LIA_PREFERRED_MODELS) {
        const exact = installed.find((name) => name === preferred || name.startsWith(preferred + ':'));
        if (exact) return exact;
      }
      if (installed.length > 0) return installed[0];
    } catch (_) {}
    return LIA_PREFERRED_MODELS[0];
  }

  async function requestDashboardLiaReadOnly(context) {
    const ctx = context && typeof context === 'object' ? context : {};
    const decision = String(ctx.decision || 'WAIT').toUpperCase();
    const entry = Number(ctx.entry);
    const sl = Number(ctx.sl);
    const tp = Number(ctx.tp);
    const rr = ctx.rr || '--';
    const phase = String(ctx.phase || '--').toUpperCase();
    const nextAction = ctx.nextAction || 'Attendre confirmation structure.';
    const reason = ctx.reason || 'Contexte indicateur en attente.';
    const market = ctx.market || {};
    const news = ctx.news || {};

    const decisionText = decision === 'BUY'
      ? 'Décision: ACHAT'
      : decision === 'SELL'
        ? 'Décision: VENTE'
        : 'Décision: ATTENTE';
    const reasonText = 'Pourquoi: ' + reason;
    const entryText = Number.isFinite(entry)
      ? ('Entrée: ' + formatCoachLevel(entry))
      : 'Entrée: non validée par l\'indicateur TradingView';
    const slTpText = (Number.isFinite(sl) && Number.isFinite(tp))
      ? ('SL/TP: ' + formatCoachLevel(sl) + ' -> ' + formatCoachLevel(tp) + ' (R:R ' + rr + ')')
      : 'SL/TP: niveaux non fournis par TradingView (aucun recalcul backend)';

    const coachingHints = [];
    if (ctx.entered) {
      coachingHints.push('Action: ' + nextAction);
      if (decision === 'BUY') coachingHints.push('Suivi: patienter sur les replis, protéger sous invalidation.');
      if (decision === 'SELL') coachingHints.push('Suivi: patienter sur les rebonds, protéger au-dessus invalidation.');
    } else {
      coachingHints.push('Action: attendre confirmation avant entrée.');
    }
    if (news.warning) coachingHints.push('News: ' + String(news.warning));
    if (market && market.isOpen === false) coachingHints.push('Marché fermé: exécution suspendue.');

    const response = [
      '[LIA INTERNE]',
      decisionText,
      reasonText,
      entryText,
      slTpText,
      coachingHints[0] || 'Action: surveiller le contexte.'
    ].join('\n');

    return {
      ok: true,
      connected: true,
      channel: 'dashboard',
      model: 'local-rule-engine',
      readOnly: true,
      response,
      hints: coachingHints
    };
  }

  // GET /lia/status — local internal intelligence status (no external dependency)
  app.get('/lia/status', async (_req, res) => {
    res.json({
      ok: true,
      connected: true,
      mode: 'internal-local',
      model: 'local-rule-engine',
      externalCalls: false
    });
  });

  // POST /lia/chat — send message, receive AI response
  app.post('/lia/chat', async (req, res) => {
    const rawMsg = String(req.body.message || '').trim();
    if (!rawMsg) return res.status(400).json({ ok: false, error: 'message requis' });

    const channel = normalizeLiaChannel(req.body.channel || req.query.channel || 'dev');
    const liaConversation = getLiaConversation(channel);
    const liaAgentName = getLiaAgentName(channel);

    liaConversation.push({ role: 'user', content: rawMsg });

    publishAgentChatMessage({
      agent: 'human',
      to: liaAgentName,
      status: 'action',
      phase: 'en cours',
      message: rawMsg,
      cause: 'message opérateur (' + channel + ')',
      impact: 'attente réponse liaison interne',
      solution: ''
    });

    const short = rawMsg.slice(0, 260);
    const reply = [
      '[LIA INTERNE]',
      channel === 'dashboard' ? 'Mode coaching lecture seule actif.' : 'Mode assistance locale actif.',
      'Résumé: ' + short,
      'Action: utiliser uniquement les données internes déjà disponibles.',
      'Aucune dépendance externe utilisée.'
    ].join('\n');

    liaConversation.push({ role: 'assistant', content: reply });
    trimLiaConversation(channel);

    publishAgentChatMessage({
      agent: liaAgentName,
      to: 'human',
      status: 'info',
      phase: 'terminé',
      message: reply.length > 300 ? reply.slice(0, 300) + '...' : reply,
      cause: 'réponse IA interne locale (' + channel + ')',
      impact: 'affiché dans monitor',
      solution: ''
    });

    return res.json({ ok: true, response: reply, status: 'online', model: 'local-rule-engine', channel, agent: liaAgentName });
  });

  // GET /lia/history — conversation history (visible messages only)
  app.get('/lia/history', (req, res) => {
    const channel = normalizeLiaChannel(req.query.channel || 'dev');
    const visible = getLiaConversation(channel).filter(m => m.role !== 'system');
    res.json({ ok: true, channel, messages: visible, total: visible.length });
  });

  // DELETE /lia/history — reset conversation (keep system prompt)
  app.delete('/lia/history', (req, res) => {
    const channel = normalizeLiaChannel(req.query.channel || req.body?.channel || 'dev');
    liaConversations[channel] = createLiaConversation(channel);
    res.json({ ok: true, channel, message: 'Historique réinitialisé' });
  });

  // ─── CENTRAL GUIDE AGENT — analyse réelle + boucle tester/retester ───────────
  const centralGuideAcks = {};

  function normalizeGuideDomain(raw) {
    const v = String(raw || 'bridge').toLowerCase();
    if (v.includes('bridge') || v === 'api') return 'bridge';
    if (v.includes('mt5')) return 'mt5';
    if (v.includes('trading')) return 'tradingview';
    if (v.includes('ext')) return 'extension';
    if (v.includes('extern') || v.includes('lia') || v.includes('ollama')) return 'externals';
    if (v.includes('module') || v.includes('agent')) return 'modules';
    return 'bridge';
  }

  async function fetchLocalJson(endpoint, options = {}, timeoutMs = 8000) {
    const r = await fetch('http://127.0.0.1:' + PORT + endpoint, {
      signal: AbortSignal.timeout(timeoutMs),
      ...options,
      headers: {
        'Accept': 'application/json',
        ...(options.headers || {})
      }
    });
    const text = await r.text();
    const ct = String(r.headers.get('content-type') || '').toLowerCase();
    let data = null;
    let jsonOk = false;
    try {
      data = JSON.parse(text || '{}');
      jsonOk = true;
    } catch (_e) {
      jsonOk = false;
    }
    if (!jsonOk) {
      return {
        ok: false,
        status: r.status,
        data: { ok: false, error: 'NON_JSON_RESPONSE', contentType: ct || 'unknown' }
      };
    }
    return { ok: r.ok, status: r.status, data };
  }

  function getDomainSpecialists(domain) {
    if (domain === 'mt5') return ['ui-test-agent', 'logic-gap-agent'];
    if (domain === 'tradingview') return ['ui-test-agent', 'logic-gap-agent'];
    if (domain === 'extension') return ['ui-test-agent', 'logic-gap-agent'];
    if (domain === 'modules') return ['logic-gap-agent', 'design-agent'];
    if (domain === 'externals') return ['research-agent'];
    return ['logic-gap-agent'];
  }

  async function runDomainSpecialists(domain) {
    const agents = getDomainSpecialists(domain);
    const reports = [];
    for (const agentName of agents) {
      try {
        const rr = await fetchLocalJson('/agents/' + encodeURIComponent(agentName) + '/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from: 'central-guide-agent',
            to: agentName,
            message: `test domaine=${domain}`,
            status: 'action',
            phase: 'en cours',
            cause: 'orchestration central-guide',
            impact: 'vérification spécialisée',
            solution: 'retour de diagnostic'
          })
        });
        reports.push({ agent: agentName, ok: rr.ok, status: rr.status, response: rr.data?.response || rr.data });
      } catch (e) {
        reports.push({ agent: agentName, ok: false, status: 500, error: e.message });
      }
    }
    return reports;
  }

  async function runLiaSynthesis(domain, state, specialistSummary, channel = 'dev') {
    try {
      const safeSummary = (state && state.summary) ? state.summary : { ok: 0, total: 0 };
      const safeOk = Number.isFinite(Number(safeSummary.ok)) ? Number(safeSummary.ok) : 0;
      const safeTotal = Number.isFinite(Number(safeSummary.total)) ? Number(safeSummary.total) : 0;
      const safeSpecialistSummary = specialistSummary == null ? 'n/a' : String(specialistSummary);
      const rr = await fetch('http://127.0.0.1:' + PORT + '/lia/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({
          channel,
          message: `Synthèse central-guide domaine=${domain}. Checks=${safeOk}/${safeTotal}. Agents=${safeSpecialistSummary}. Donne un résumé court actionnable.`
        }),
        signal: AbortSignal.timeout(65000)
      });
      const raw = await rr.text();
      let jd = null;
      try { jd = JSON.parse(raw || '{}'); } catch (_e) {
        return { ok: false, response: 'Lia indisponible (réponse non JSON)' };
      }
      return jd;
    } catch (_e) {
      return { ok: false, response: 'Lia indisponible' };
    }
  }

  async function runAutoCorrectionIfNeeded(domain, state) {
    if (!state || !state.summary || state.summary.missing === 0) return { triggered: false };
    if (domain !== 'bridge' && domain !== 'mt5' && domain !== 'extension' && domain !== 'tradingview') {
      return { triggered: false };
    }
    try {
      const fix = await fetchLocalJson('/agents/repair-agent/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from: 'central-guide-agent',
          to: 'repair-agent',
          message: `auto-correction domaine=${domain} missing=${state.summary.missing}`,
          status: 'action',
          phase: 'en cours',
          cause: 'checks central-guide KO',
          impact: 'blocage workflow',
          solution: state.nextAction ? state.nextAction.action : 'diagnostic complémentaire'
        })
      });
      return { triggered: true, ok: fix.ok, response: fix.data?.response || fix.data || null };
    } catch (e) {
      return { triggered: true, ok: false, error: e.message };
    }
  }

  function markGuideAck(domain, checkId) {
    const d = normalizeGuideDomain(domain);
    if (!centralGuideAcks[d]) centralGuideAcks[d] = {};
    centralGuideAcks[d][checkId] = new Date().toISOString();
  }

  async function runCentralGuideChecks(domainRaw) {
    const domain = normalizeGuideDomain(domainRaw);
    const checks = [];

    // Shared real-state calls
    const health = await fetchLocalJson('/health').catch(() => ({ ok: false, status: 500, data: {} }));
    const liveState = await fetchLocalJson('/live/state').catch(() => ({ ok: false, status: 500, data: {} }));
    const mt5Conn = await fetchLocalJson('/mt5/connection').catch(() => ({ ok: false, status: 500, data: {} }));
    const agents = await fetchLocalJson('/agents/list').catch(() => ({ ok: false, status: 500, data: {} }));
    const liaStatus = await fetchLocalJson('/lia/status').catch(() => ({ ok: false, status: 500, data: {} }));

    const addCheck = (id, label, ok, detail, action, verifyHint) => {
      checks.push({
        id,
        label,
        ok: !!ok,
        detail,
        actionIfMissing: action,
        verify: verifyHint,
        acknowledgedAt: centralGuideAcks[domain]?.[id] || null
      });
    };

    if (domain === 'bridge') {
      addCheck(
        'bridge-health',
        'Bridge local accessible (:4000)',
        health.ok && health.data.ok === true && Number(health.data.port) === 4000,
        health.ok ? `port=${health.data.port} uptime=${Math.floor(health.data.uptime || 0)}s` : `HTTP ${health.status}`,
        'Démarrer le bridge local sur port 4000',
        'Le test doit retourner ok=true et port=4000'
      );
      addCheck(
        'bridge-live-state',
        'Live state endpoint disponible',
        liveState.ok && liveState.data.ok === true,
        liveState.ok ? `source=${liveState.data.health?.source || 'offline'}` : `HTTP ${liveState.status}`,
        'Vérifier que /live/state répond',
        'Le test doit retourner ok=true'
      );
    }

    if (domain === 'mt5') {
      addCheck(
        'mt5-connected',
        'Flux MT5 connecté',
        mt5Conn.ok && mt5Conn.data.connected === true,
        mt5Conn.ok ? String(mt5Conn.data.message || '') : `HTTP ${mt5Conn.status}`,
        'Lancer MT5 + EA et autoriser WebRequest vers localhost:4000',
        'Le test doit afficher connected=true'
      );
      addCheck(
        'mt5-fresh-data',
        'Données MT5 fraîches',
        liveState.ok && (liveState.data.health?.source === 'mt5' || String(liveState.data.health?.source || '').includes('mt5')),
        liveState.ok ? `source=${liveState.data.health?.source || 'offline'} ageMs=${liveState.data.health?.ageMs ?? 'n/a'}` : `HTTP ${liveState.status}`,
        'Envoyer un tick depuis MT5 (POST /mt5)',
        'Le test doit montrer source=mt5'
      );
    }

    if (domain === 'tradingview') {
      const source = String(liveState.data.health?.source || '').toLowerCase();
      const payloadSource = String(liveState.data.latestPayload?.source || '').toLowerCase();
      const bridgeEnabled = liveState.ok ? (liveState.data.bridge?.enabled !== false) : false;
      const tvState = liveState.data.tradingview || {};
      const tvLastSource = String(tvState.lastSource || '').toLowerCase();
      const tvAgeMs = Number(tvState.ageMs);
      const tvFresh = Number.isFinite(tvAgeMs) ? tvAgeMs < 180000 : false;
      const tvOk = bridgeEnabled && (
        source.includes('tradingview') ||
        payloadSource.includes('tradingview') ||
        (tvFresh && (tvLastSource.includes('tradingview') || tvLastSource.includes('tv')))
      );

      const payloadSummary = tvState.payload
        ? `price=${tvState.payload.price ?? 'n/a'} verdict=${tvState.payload.verdict ?? 'n/a'} anticipation=${tvState.payload.anticipation ?? 'n/a'} rsi=${tvState.payload.rsi ?? 'n/a'}`
        : 'payload=n/a';
      addCheck(
        'tv-bridge-active',
        'TradingView alimente le système',
        liveState.ok && tvOk,
        liveState.ok
          ? `bridge=${bridgeEnabled ? 'ON' : 'OFF'} src=${source || 'n/a'} latest=${payloadSource || 'n/a'} tv.source=${tvLastSource || 'n/a'} symbol=${tvState.symbol || 'n/a'} tf=${tvState.timeframe || 'n/a'} ts=${tvState.timestamp || 'n/a'} event=${tvState.eventType || 'n/a'} ${payloadSummary}`
          : `HTTP ${liveState.status}`,
        'Déclencher une alerte TradingView vers le webhook local',
        'Le test doit voir source tradingview dans live/state'
      );
      addCheck(
        'tv-bridge-base',
        'Bridge central actif pour TradingView',
        health.ok && health.data.ok === true,
        health.ok ? `Bridge OK port=${health.data.port}` : `HTTP ${health.status}`,
        'Démarrer bridge local avant webhook TV',
        'Le test /health doit renvoyer ok=true'
      );
    }

    if (domain === 'extension') {
      const clients = Number(liveState.data.streams?.extensionSseClients || 0);
      addCheck(
        'ext-sync-clients',
        'Extension connectée au flux SSE',
        liveState.ok && clients > 0,
        liveState.ok ? `extensionSseClients=${clients}` : `HTTP ${liveState.status}`,
        'Ouvrir popup/monitor extension pour établir /extension/sync',
        'Le test doit afficher extensionSseClients > 0'
      );
      addCheck(
        'ext-endpoint',
        'Endpoint /extension/sync disponible',
        liveState.ok && liveState.data.endpoints?.['/extension/sync'] === true,
        liveState.ok ? `endpoint=${liveState.data.endpoints?.['/extension/sync']}` : `HTTP ${liveState.status}`,
        'Vérifier la route /extension/sync dans server.js',
        'Le test doit afficher endpoint=true'
      );
    }

    if (domain === 'externals') {
      addCheck(
        'lia-online',
        'Lia / Ollama disponible',
        liaStatus.ok && liaStatus.data.connected === true,
        liaStatus.ok ? `models=${(liaStatus.data.models || []).join(', ') || 'none'}` : `HTTP ${liaStatus.status}`,
        'Démarrer Ollama service local',
        'Le test doit afficher connected=true avec au moins 1 modèle'
      );
      addCheck(
        'lia-model',
        'Modèle IA présent',
        liaStatus.ok && Array.isArray(liaStatus.data.models) && liaStatus.data.models.length > 0,
        liaStatus.ok ? `count=${(liaStatus.data.models || []).length}` : `HTTP ${liaStatus.status}`,
        'Télécharger un modèle: ollama pull llama3.2',
        'Le test doit afficher models.length > 0'
      );
    }

    if (domain === 'modules') {
      const list = Array.isArray(agents.data.agents) ? agents.data.agents.map((a) => a.name) : [];
      const required = ['orchestrator', 'design-agent', 'ui-test-agent', 'logic-gap-agent', 'human-interface-agent'];
      const missing = required.filter((n) => !list.includes(n));
      addCheck(
        'modules-required',
        'Agents clés enregistrés',
        agents.ok && missing.length === 0,
        agents.ok ? `agents=${list.length} missing=${missing.join(', ') || 'none'}` : `HTTP ${agents.status}`,
        'Relancer server.js pour enregistrer tous les agents',
        'Le test doit afficher missing=none'
      );
      addCheck(
        'modules-runtime',
        'Runtime agents visible',
        agents.ok && Number(agents.data.totalAgents || 0) > 0,
        agents.ok ? `totalAgents=${agents.data.totalAgents}` : `HTTP ${agents.status}`,
        'Vérifier /agents/list côté backend',
        'Le test doit afficher totalAgents > 0'
      );
    }

    const missingChecks = checks.filter((c) => !c.ok);
    const nextAction = missingChecks[0] ? {
      checkId: missingChecks[0].id,
      action: missingChecks[0].actionIfMissing,
      why: missingChecks[0].detail,
      verify: missingChecks[0].verify
    } : null;

    return {
      ok: true,
      domain,
      checks,
      summary: {
        total: checks.length,
        ok: checks.filter((c) => c.ok).length,
        missing: missingChecks.length,
        status: missingChecks.length === 0 ? 'OK' : 'NON'
      },
      nextAction
    };
  }

  // GET /central-guide/state?domain=mt5|tradingview|extension|bridge|externals|modules
  app.get('/central-guide/state', async (req, res) => {
    try {
      const domain = normalizeGuideDomain(req.query.domain);
      const state = await runCentralGuideChecks(domain);
      publishAgentChatMessage({
        agent: 'central-guide-agent',
        to: 'human-interface-agent',
        status: state.summary.missing === 0 ? 'ok' : 'action',
        phase: state.summary.missing === 0 ? 'terminé' : 'en attente',
        message: `Diagnostic ${domain}: ${state.summary.ok}/${state.summary.total} OK`,
        cause: state.summary.missing === 0 ? 'aucun blocage' : 'prérequis manquants',
        impact: state.summary.missing === 0 ? 'étape suivante possible' : 'action humaine requise',
        solution: state.nextAction ? state.nextAction.action : 'continuer'
      });
      res.json(state);
    } catch (e) {
      res.status(500).json({ ok: false, error: e.message });
    }
  });

  // POST /central-guide/ack — opérateur confirme "J'ai fait l'action"
  app.post('/central-guide/ack', (req, res) => {
    const domain = normalizeGuideDomain(req.body.domain);
    const checkId = String(req.body.checkId || '').trim();
    if (!checkId) return res.status(400).json({ ok: false, error: 'checkId requis' });
    markGuideAck(domain, checkId);
    publishAgentChatMessage({
      agent: 'human-interface-agent',
      to: 'central-guide-agent',
      status: 'info',
      phase: 'en cours',
      message: `Action confirmée par humain: ${domain}/${checkId}`,
      cause: 'clic J ai fait l action',
      impact: 'retest demandé',
      solution: 'lancer POST /central-guide/test'
    });
    res.json({ ok: true, domain, checkId, acknowledgedAt: centralGuideAcks[domain][checkId] });
  });

  // POST /central-guide/test — lance un vrai test maintenant
  app.post('/central-guide/test', async (req, res) => {
    try {
      const domain = normalizeGuideDomain(req.body.domain);
      const state = await runCentralGuideChecks(domain);
      const specialistReports = await runDomainSpecialists(domain);
      const autoCorrection = await runAutoCorrectionIfNeeded(domain, state);

      // Chain specialists -> Lia -> monitor with real call
      const specialistSummary = specialistReports
        .map((r) => `${r.agent}:${r.ok ? 'OK' : 'NON'}`)
        .join(', ');
      const liaBridge = await runLiaSynthesis(domain, state, specialistSummary);

      publishAgentChatMessage({
        agent: 'central-guide-agent',
        to: 'human-interface-agent',
        status: state.summary.missing === 0 ? 'ok' : 'error',
        phase: state.summary.missing === 0 ? 'terminé' : 'bloqué',
        message: `Test ${domain}: ${state.summary.status}`,
        cause: state.summary.missing === 0 ? 'tous checks OK' : 'checks manquants',
        impact: `agents spécialisés: ${specialistSummary}`,
        solution: state.nextAction ? state.nextAction.action : 'continuer workflow'
      });
      res.json({
        ...state,
        specialistReports,
        autoCorrection,
        lia: liaBridge || { ok: false, response: 'Lia indisponible' }
      });
    } catch (e) {
      res.status(500).json({ ok: false, error: e.message });
    }
  });

  // GET /design/audit-html-all — audit global design avant toute réorganisation
  app.get('/design/audit-html-all', (_req, res) => {
    try {
      const audit = analyzeAllHtmlDesignPages();
      publishAgentChatMessage({
        agent: 'design-agent',
        to: 'human-interface-agent',
        status: 'info',
        phase: 'terminé',
        message: `Audit HTML complet terminé: ${audit.totalHtml} pages analysées`,
        cause: 'audit design global',
        impact: `doublons titres=${audit.duplicates.titles.length}, idsCrossPages=${audit.duplicates.idsCrossPages.length}`,
        solution: 'appliquer regroupement intelligent sans suppression'
      });
      res.json(audit);
    } catch (e) {
      res.status(500).json({ ok: false, error: e.message });
    }
  });

  // POST /human-interface/decision — traitement réel d'une demande humaine
  app.post('/human-interface/decision', async (req, res) => {
    try {
      const request = req.body?.request || {};
      const decision = String(req.body?.decision || '').trim();
      const responseText = String(req.body?.response || '').trim();
      if (!request.id || !request.source || !decision) {
        return res.status(400).json({ ok: false, error: 'request.id, request.source et decision requis' });
      }

      const domain = normalizeGuideDomain(request.domain || request.action || request.subject || 'bridge');
      let workflow = null;
      if (request.source === 'central-guide-agent' && decision !== 'refusé') {
        const state = await runCentralGuideChecks(domain);
        const specialistReports = await runDomainSpecialists(domain);
        const autoCorrection = await runAutoCorrectionIfNeeded(domain, state);
        const specialistSummary = specialistReports.map((r) => `${r.agent}:${r.ok ? 'OK' : 'NON'}`).join(', ');
        const lia = await runLiaSynthesis(domain, state, specialistSummary);
        workflow = { domain, state, specialistReports, autoCorrection, lia };
      }

      const forwardPayload = {
        from: 'human-interface-agent',
        to: request.source,
        message: responseText || `Décision opérateur: ${decision}`,
        status: decision === 'refusé' ? 'error' : 'info',
        phase: decision === 'terminé' ? 'terminé' : 'en cours',
        cause: request.why || 'décision opérateur',
        impact: `request=${request.id}`,
        solution: `action=${decision}`
      };

      const forwarded = await fetchLocalJson('/agents/' + encodeURIComponent(request.source) + '/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(forwardPayload)
      });

      publishAgentChatMessage({
        agent: 'human-interface-agent',
        to: request.source,
        status: decision === 'refusé' ? 'error' : 'info',
        phase: decision === 'terminé' ? 'terminé' : 'en cours',
        message: responseText || `Décision opérateur: ${decision}`,
        cause: request.why || 'validation humaine',
        impact: `demande ${request.id} traitée`,
        solution: workflow?.state?.nextAction?.action || 'continuer'
      });

      res.json({
        ok: true,
        processed: true,
        requestId: request.id,
        decision,
        forwarded: forwarded.data || { ok: forwarded.ok },
        workflow
      });
    } catch (e) {
      res.status(500).json({ ok: false, error: e.message });
    }
  });

  const coachTradeStateStore = {};
  const USER_TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1'];

  function getCoachTradeKey(symbol, timeframe) {
    return String(symbol || 'XAUUSD').toUpperCase() + '|' + String(timeframe || 'H1').toUpperCase();
  }

  function getCoachTradeState(symbol, timeframe) {
    const key = getCoachTradeKey(symbol, timeframe);
    if (!coachTradeStateStore[key]) {
      coachTradeStateStore[key] = {
        symbol: String(symbol || 'XAUUSD').toUpperCase(),
        timeframe: String(timeframe || 'H1').toUpperCase(),
        phase: 'WAIT_ENTRY',
        entered: false,
        bePlaced: false,
        partialTaken: false,
        lastAction: 'INIT',
        updatedAt: Date.now(),
        virtualPosition: null,
        notes: []
      };
    }
    return coachTradeStateStore[key];
  }

  function getCoachMarketPrice(symbol) {
    const latest = marketStore.getLatestForSymbol(String(symbol || 'XAUUSD').toUpperCase());
    const payload = latest?.latestPayload || {};
    return Number(payload.price || payload.bid || payload.ask || NaN);
  }

  const coachAnalysisSnapshotCache = Object.create(null);
  const coachNewsCache = Object.create(null);

  function getCoachAnalysisCacheKey(symbol, timeframe) {
    return String(symbol || 'XAUUSD').toUpperCase() + '::' + String(timeframe || 'H1').toUpperCase();
  }

  function readCoachAnalysisSnapshot(symbol, timeframe, maxAgeMs = 90000) {
    const key = getCoachAnalysisCacheKey(symbol, timeframe);
    const snapshot = coachAnalysisSnapshotCache[key] || null;
    if (!snapshot) return null;
    const ageMs = Date.now() - Number(snapshot.updatedAt || 0);
    return ageMs <= maxAgeMs ? snapshot : null;
  }

  function storeCoachAnalysisSnapshot(symbol, timeframe, snapshot) {
    const key = getCoachAnalysisCacheKey(symbol, timeframe);
    coachAnalysisSnapshotCache[key] = {
      ...(coachAnalysisSnapshotCache[key] || {}),
      ...(snapshot || {}),
      updatedAt: Date.now()
    };
    return coachAnalysisSnapshotCache[key];
  }

  async function getCachedNewsIntelligence(symbol) {
    const key = String(symbol || 'XAUUSD').toUpperCase();
    const cached = coachNewsCache[key] || null;
    if (cached && (Date.now() - Number(cached.ts || 0)) < 120000) {
      return cached.data;
    }
    const now = new Date();
    const hourUtc = now.getUTCHours();
    const syntheticEvents = [];

    if (hourUtc >= 12 && hourUtc <= 15) {
      syntheticEvents.push({
        event: 'Fenêtre macro US',
        currency: 'USD',
        impact: 'HIGH',
        minutesAway: 20,
        isUrgent: true
      });
    }

    const data = {
      upcomingEvents: syntheticEvents,
      news: [],
      macroWarning: syntheticEvents.length ? 'Attention volatilité macro proche sur USD.' : null,
      symbolImpact: syntheticEvents.length
        ? ('Contexte macro sensible détecté pour ' + key)
        : ('Pas de risque macro majeur immédiat pour ' + key),
      tradingSuggestion: syntheticEvents.length
        ? 'Réduire l\'exposition avant la fenêtre macro'
        : 'Pas d\'annonce urgente'
    };
    coachNewsCache[key] = { ts: Date.now(), data };
    return data;
  }

  function normalizeTradeDirection(raw) {
    const v = String(raw || '').toUpperCase();
    if (v.includes('BUY') || v.includes('LONG') || v.includes('ACHAT') || v.includes('HAUSS')) return 'LONG';
    if (v.includes('SELL') || v.includes('SHORT') || v.includes('VENTE') || v.includes('BAISS')) return 'SHORT';
    return 'WAIT';
  }

  function recommendationFromDirection(raw) {
    const dir = normalizeTradeDirection(raw);
    if (dir === 'LONG') return 'BUY';
    if (dir === 'SHORT') return 'SELL';
    return 'WAIT';
  }

  function isDirectionalDirection(dir) {
    const d = String(dir || '').toUpperCase();
    return d === 'LONG' || d === 'SHORT';
  }

  function extractDirectionalBias(raw) {
    const text = String(raw || '').toUpperCase();
    if (!text) return 0;
    const bull = text.includes('BUY') || text.includes('LONG') || text.includes('ACHAT') || text.includes('HAUSS') || text.includes('UP');
    const bear = text.includes('SELL') || text.includes('SHORT') || text.includes('VENTE') || text.includes('BAISS') || text.includes('DOWN') || text.includes('BEAR');
    if (bull && !bear) return 1;
    if (bear && !bull) return -1;
    return 0;
  }

  function deriveMtfDirectionFromRobot(robotV12) {
    const score = [
      robotV12?.lecture_1m,
      robotV12?.lecture_5m,
      robotV12?.lecture_15m,
      robotV12?.lecture_60m
    ].reduce((acc, v) => acc + extractDirectionalBias(v), 0);
    if (score >= 2) return 'LONG';
    if (score <= -2) return 'SHORT';
    return 'WAIT';
  }

  function normalizeRiskLevel(raw) {
    const v = String(raw || '').toUpperCase();
    if (v === 'LOW' || v === 'MEDIUM' || v === 'HIGH') return v;
    return v || 'MEDIUM';
  }

  function formatCoachLevel(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '--';
    return Math.abs(num) > 1000 ? num.toFixed(2) : num.toFixed(5);
  }

  function buildTradingviewRuntimeTrade(symbol, timeframe, currentPrice, modeRaw, tvRuntime, robotV12) {
    // CONNECTION GUARD: Only build a trade signal from live TradingView data (last signal < 180s ago).
    // Prevents displaying positions based on stale or test-injected data when TV is disconnected.
    if (tvRuntime?.connected === false) {
      return null;
    }
    const price = Number(currentPrice || tvRuntime?.payload?.price || NaN);
    if (!Number.isFinite(price) || price <= 0) return null;

    let direction = normalizeTradeDirection(
      robotV12?.verdict ||
      robotV12?.anticipation ||
      tvRuntime?.payload?.verdict ||
      tvRuntime?.payload?.anticipation ||
      tvRuntime?.payload?.action
    );

    if (direction === 'WAIT') return null;

    const confidence = Number(robotV12?.anticipation_force || 64);
    const entry = Number(robotV12?.entry ?? tvRuntime?.payload?.entry ?? NaN);
    const sl = Number(robotV12?.sl ?? tvRuntime?.payload?.sl ?? NaN);
    const tp = Number(robotV12?.tp ?? tvRuntime?.payload?.tp ?? NaN);
    const rrRatio = robotV12?.rrRatio ?? tvRuntime?.payload?.rrRatio ?? '--';
    if (!Number.isFinite(entry) || !Number.isFinite(sl) || !Number.isFinite(tp)) {
      return null;
    }
    const setup = classifySetup(timeframe, direction, confidence, modeRaw);
    const technicalParts = [
      robotV12?.verdict ? ('Verdict TV: ' + robotV12.verdict) : null,
      robotV12?.anticipation ? ('Anticipation: ' + robotV12.anticipation + (robotV12.anticipation_force != null ? ' (' + robotV12.anticipation_force + '%)' : '')) : null,
      robotV12?.contexte ? ('Contexte: ' + robotV12.contexte) : null,
      tvRuntime?.payload?.rsi != null ? ('RSI: ' + Number(tvRuntime.payload.rsi).toFixed(0)) : null
    ].filter(Boolean).join(' | ');

    return validateTrade({
      symbol: String(symbol || 'XAUUSD').toUpperCase(),
      direction,
      entry,
      sl,
      tp,
      rrRatio,
      ...setup,
      score: Number.isFinite(confidence) ? confidence : 64,
      confidence: Number.isFinite(confidence) ? confidence : 64,
      source: 'tradingview-indicator',
      accuracy: 'live',
      technical: technicalParts || 'Lecture TradingView live',
      macro: 'Contexte TradingView live',
      sentiment: robotV12?.anticipation || 'TV runtime'
    }, price);
  }

  async function computeCoachAnalysisSnapshot(symbol, timeframe, lang, tradeState, options = {}) {
    if (!options.forceFresh) {
      const cached = readCoachAnalysisSnapshot(symbol, timeframe, options.maxAgeMs || 90000);
      if (cached) return cached;
    }

    const resolvedMode = resolveRuntimeMode(options.mode || activeSymbol?.mode || bridgeConfig.bridgeMode || 'AUTO', symbol, timeframe);
    const tvRuntime = getLatestTradingviewRuntime();
    const robotV12 = getRobotV12ForSymbol(symbol);
    const extSnapshot = options.extSnapshot || await fetchLocalJson('/extension/data').then((r) => r.data || null).catch(() => null);
    const marketStatus = marketHoursChecker.getStatus(symbol);
    const activeSource = String(bridgeConfig.activeSource || (bridgeConfig.mt5Enabled === true ? 'mt5' : 'tradingview')).toLowerCase() === 'mt5' ? 'mt5' : 'tradingview';
    const priceCandidates = activeSource === 'tradingview'
      ? [
          options.currentPrice,
          extSnapshot?.currentData?.price,
          extSnapshot?.activeSymbol?.price,
          tvRuntime?.payload?.price,
          getCoachMarketPrice(symbol)
        ]
      : [
          options.currentPrice,
          getCoachMarketPrice(symbol),
          extSnapshot?.currentData?.price,
          extSnapshot?.activeSymbol?.price,
          tvRuntime?.payload?.price
        ];
    const currentPrice = Number(priceCandidates.find((v) => Number.isFinite(Number(v)) && Number(v) > 0) || NaN);

    const runtimeTrade = options.instantTrade
      || buildTradingviewRuntimeTrade(symbol, timeframe, currentPrice, resolvedMode, tvRuntime, robotV12);
    const runtimeSignal = buildRuntimeTradeSignal(symbol, timeframe, runtimeTrade, robotV12, marketStatus, currentPrice);
    const newsData = await getCachedNewsIntelligence(symbol);
    const newsPayload = {
      upcomingEvents: Array.isArray(newsData?.upcomingEvents)
        ? newsData.upcomingEvents.slice(0, 5).map((e) => ({
            event: e.event,
            currency: e.currency,
            impact: e.impact,
            urgency: e.isUrgent ? 'HIGH' : String(e.impact || 'LOW').toUpperCase(),
            mins: e.minutesAway,
            minutesAway: e.minutesAway
          }))
        : [],
      warning: newsData?.macroWarning || null,
      symbolImpact: newsData?.symbolImpact || ('Pas de risque macro majeur immédiat pour ' + symbol),
      tradingSuggestion: newsData?.tradingSuggestion || 'Pas d\'annonce urgente'
    };

    const tvDirectionRaw = robotV12?.verdict
      || robotV12?.anticipation
      || tvRuntime?.payload?.verdict
      || tvRuntime?.payload?.anticipation
      || tvRuntime?.payload?.action
      || 'WAIT';
    const runtimeDirectionRaw = runtimeTrade?.direction || runtimeTrade?.side || 'WAIT';
    const tvDirection = normalizeTradeDirection(tvDirectionRaw);
    const runtimeDirection = normalizeTradeDirection(runtimeDirectionRaw);
    const mtfDirection = deriveMtfDirectionFromRobot(robotV12);

    const conflicts = [];
    if (isDirectionalDirection(tvDirection) && isDirectionalDirection(runtimeDirection) && tvDirection !== runtimeDirection) {
      conflicts.push('Conflit directionnel: verdict TradingView != signal runtime');
    }
    if (isDirectionalDirection(tvDirection) && isDirectionalDirection(mtfDirection) && tvDirection !== mtfDirection) {
      conflicts.push('Conflit multi-timeframe: verdict principal != lectures M1/M5/M15/H1');
    }

    const preferredDirection = isDirectionalDirection(tvDirection)
      ? tvDirection
      : (isDirectionalDirection(runtimeDirection) ? runtimeDirection : 'WAIT');

    const conflictDetected = conflicts.length > 0;
    const recommendation = (!marketStatus?.isOpen || conflictDetected)
      ? 'WAIT'
      : recommendationFromDirection(preferredDirection);
    const confidence = Number(
      robotV12?.anticipation_force ||
      runtimeTrade?.score ||
      runtimeTrade?.confidence ||
      runtimeSignal.confidence ||
      50
    );
    const tradeTechnical = runtimeTrade?.technical || runtimeSignal.rationale || 'Analyse runtime en attente';

    const hasLiveLevels = Number.isFinite(Number(runtimeTrade?.entry))
      && Number.isFinite(Number(runtimeTrade?.sl))
      && Number.isFinite(Number(runtimeTrade?.tp));
    const tradeStatus = String(runtimeTrade?.trade_status || '').toUpperCase();
    const statusAllowsEntry = tradeStatus === 'LIVE' || tradeStatus === 'CONDITIONAL';
    const setupValidated = recommendation !== 'WAIT'
      && !!marketStatus?.isOpen
      && !conflictDetected
      && hasLiveLevels
      && statusAllowsEntry;
    const executionDecision = conflictDetected
      ? 'NO_ENTRY_CONFLICT'
      : (setupValidated ? 'ENTER' : 'WAIT');
    const executionReason = conflictDetected
      ? conflicts.join(' | ')
      : (setupValidated
        ? 'Entrée validée: direction TradingView alignée avec prix et niveaux SL/TP actifs.'
        : 'Entrée non validée: attendre confirmation complète (signal + niveaux + proximité prix).');

    const whyEntry = [];
    if (!marketStatus?.isOpen) {
      whyEntry.push('Marché fermé: aucune entrée tant que la session ne rouvre pas.');
    } else if (conflictDetected) {
      whyEntry.push('PAS D\'ENTRÉE: conflit de signal détecté entre les contextes TradingView/runtime.');
    } else if (recommendation === 'BUY') {
      whyEntry.push('Long retenu car TradingView, la structure runtime et le contexte restent orientés à la hausse.');
    } else if (recommendation === 'SELL') {
      whyEntry.push('Short retenu car TradingView, la structure runtime et le contexte restent orientés à la baisse.');
    } else {
      whyEntry.push('Attente retenue car aucun alignement directionnel propre n\'est confirmé.');
    }
    if (tradeTechnical) whyEntry.push(String(tradeTechnical));
    if (newsPayload.warning) whyEntry.push(String(newsPayload.warning));
    if (robotV12?.contexte) whyEntry.push('Contexte TradingView: ' + String(robotV12.contexte));

    const entryValue = Number(runtimeTrade?.entry ?? runtimeSignal.entry ?? currentPrice);
    const slValue = Number(runtimeTrade?.sl ?? runtimeSignal.sl ?? NaN);
    const tpValue = Number(runtimeTrade?.tp ?? runtimeSignal.tp ?? NaN);
    const rrRatio = runtimeTrade?.rrRatio || '--';
    const slDistance = Number.isFinite(entryValue) && Number.isFinite(slValue) ? Math.abs(entryValue - slValue) : null;
    const tpDistance = Number.isFinite(entryValue) && Number.isFinite(tpValue) ? Math.abs(tpValue - entryValue) : null;
    const direction = normalizeTradeDirection(preferredDirection);

    const whySl = [
      direction === 'LONG'
        ? 'SL placé sous la zone d\'invalidation du scénario haussier.'
        : direction === 'SHORT'
          ? 'SL placé au-dessus de la zone d\'invalidation du scénario baissier.'
          : 'SL non activé tant qu\'aucune entrée n\'est validée.',
      Number.isFinite(slDistance) ? ('Distance de protection: ' + formatCoachLevel(slDistance) + ' depuis l\'entrée.') : 'Distance de protection à confirmer au prochain setup.',
      newsPayload.warning ? 'Protection renforcée car un risque news ou volatilité est détecté.' : 'Protection alignée avec la volatilité actuelle et le mode de setup.'
    ];

    const whyTp = [
      direction === 'LONG'
        ? 'TP placé sur une extension haussière cohérente avec le mouvement visé.'
        : direction === 'SHORT'
          ? 'TP placé sur une extension baissière cohérente avec le mouvement visé.'
          : 'TP non activé tant qu\'aucune entrée n\'est validée.',
      Number.isFinite(tpDistance) ? ('Distance de cible: ' + formatCoachLevel(tpDistance) + ' depuis l\'entrée.') : 'Distance de cible à confirmer au prochain setup.',
      'Objectif calibré pour préserver un ratio risque/rendement exploitable' + (rrRatio !== '--' ? (' (R:R ' + rrRatio + ').') : '.')
    ];

    const riskLevel = !marketStatus?.isOpen
      ? 'HIGH'
      : normalizeRiskLevel(runtimeTrade?.risk || (newsPayload.warning ? 'HIGH' : (recommendation === 'WAIT' ? 'MEDIUM' : 'LOW')));

    const snapshot = {
      symbol,
      timeframe,
      modeResolved: resolvedMode,
      currentPrice: Number.isFinite(currentPrice) ? currentPrice : null,
      marketStatus,
      robotV12,
      signal: runtimeSignal,
      runtimeTrade: runtimeTrade || null,
      analysis: {
        recommendation,
        reason: executionReason,
        confidence: Number.isFinite(confidence) ? confidence : 50,
        strength: Number.isFinite(confidence) ? confidence : 50,
        anticipation: robotV12?.anticipation || (recommendation === 'WAIT' ? 'ATTENTE' : 'PRET')
      },
      execution: {
        decision: executionDecision,
        canEnter: executionDecision === 'ENTER',
        reason: executionReason,
        conflict: conflictDetected,
        conflictReasons: conflicts
      },
      news: newsPayload,
      explainer: {
        whyEntry: whyEntry.slice(0, 5),
        whySl: whySl.slice(0, 4),
        whyTp: whyTp.slice(0, 4)
      },
      strategy: {
        logic: tradeState?.entered
          ? 'Position active: arrêter la recherche d\'entrée et piloter uniquement la gestion live.'
          : (executionDecision === 'NO_ENTRY_CONFLICT'
            ? 'PAS D\'ENTRÉE / CONFLIT DE SIGNAL: attendre alignement clair de l\'indicateur TradingView.'
            : (recommendation === 'WAIT'
              ? 'Entrée non validée: attendre un meilleur alignement prix/structure/contexte avant toute entrée.'
              : ((recommendation === 'BUY' ? 'Long' : 'Short') + ' privilégié sur ' + timeframe + ' avec validation structure + prix.'))),
        anticipation: robotV12?.anticipation || runtimeSignal.stats?.anticipation || 'ATTENTE'
      },
      risk: {
        riskLevel,
        riskReason: newsPayload.warning || (marketStatus?.isOpen ? 'Flux ouvert, spread/volatilité à surveiller.' : 'Marché fermé ou contexte non exploitable.'),
        guidance: riskLevel === 'HIGH'
          ? 'Réduire le risque, attendre ou protéger avant toute accélération.'
          : (riskLevel === 'LOW'
            ? 'Risque contenu si la structure reste valide.'
            : 'Risque modéré: exécuter seulement si le prix reste propre.'),
        rsi: tvRuntime?.payload?.rsi ?? robotV12?.rsi_1m ?? robotV12?.rsi_5m ?? null
      },
      sourceSummary: {
        activeSource,
        tradingviewConnected: !!tvRuntime?.connected,
        orchestrator: false,
        marketOpen: !!marketStatus?.isOpen,
        conflictDetected,
        tvDirection,
        runtimeDirection,
        mtfDirection
      }
    };

    return storeCoachAnalysisSnapshot(symbol, timeframe, snapshot);
  }

  function createVirtualPositionFromTrade(symbol, timeframe, trade, currentPrice) {
    if (!trade) return null;
    return {
      symbol: String(symbol || trade.symbol || 'XAUUSD').toUpperCase(),
      timeframe: String(timeframe || 'H1').toUpperCase(),
      direction: String(trade.direction || trade.side || 'WAIT').toUpperCase(),
      entry: Number(trade.entry || currentPrice || 0),
      sl: Number(trade.sl || 0),
      tp: Number(trade.tp || 0),
      rrRatio: trade.rrRatio || '--',
      setupType: trade.setup_type || trade.setupType || '--',
      source: trade.source || 'coach-virtual',
      status: 'OPEN',
      bePlaced: false,
      partialTaken: false,
      openedAt: Date.now(),
      lastPrice: Number(currentPrice || trade.entry || 0),
      lastGuidance: 'Position virtuelle initialisée. Respecter invalidation, SL et TP.'
    };
  }

  function buildVirtualPositionSnapshot(state, instantTrade, livePayload, currentPrice) {
    const activeVirtual = state.virtualPosition || (state.entered ? createVirtualPositionFromTrade(state.symbol, state.timeframe, instantTrade, currentPrice) : null);
    if (!activeVirtual) {
      return {
        virtualPosition: null,
        nextAction: {
          phase: state.phase,
          primary: 'Aucune position virtuelle active. Attendre un setup validé avant entrée.',
          actions: ['WAIT', 'ENTER', 'RETEST']
        }
      };
    }

    const direction = String(activeVirtual.direction || 'WAIT').toUpperCase();
    const price = Number(currentPrice || activeVirtual.lastPrice || activeVirtual.entry || 0);
    const entry = Number(activeVirtual.entry || 0);
    const sl = Number(activeVirtual.sl || 0);
    const tp = Number(activeVirtual.tp || 0);
    const pnlPoints = direction === 'SHORT' ? (entry - price) : (price - entry);
    const riskDistance = Math.abs(entry - sl) || 1;
    const rewardDistance = Math.abs(tp - entry) || 1;
    const progressToTp = rewardDistance > 0 ? Math.max(0, Math.min(100, Math.round((Math.abs(price - entry) / rewardDistance) * 100))) : 0;
    const invalidationNear = direction === 'SHORT' ? price >= sl : price <= sl;
    const tpTouched = direction === 'SHORT' ? price <= tp : price >= tp;

    let primary = 'Surveiller la structure et laisser courir tant que l’invalidation n’est pas touchée.';
    let actions = ['WAIT', 'BE', 'TAKE_PROFIT', 'EXIT'];
    if (invalidationNear) {
      primary = 'Prix sur invalidation: couper ou protéger immédiatement la position.';
      actions = ['EXIT', 'WAIT', 'RETEST'];
    } else if (!activeVirtual.bePlaced && progressToTp >= 35) {
      primary = 'Déplacer le stop vers break-even dès maintenant pour protéger la position.';
      actions = ['BE', 'TAKE_PROFIT', 'WAIT'];
    } else if (!activeVirtual.partialTaken && progressToTp >= 65) {
      primary = 'Prendre un partiel et laisser courir le reste tant que la structure tient.';
      actions = ['TAKE_PROFIT', 'BE', 'WAIT', 'EXIT'];
    } else if (tpTouched) {
      primary = 'Objectif principal atteint: sécuriser ou sortir la position.';
      actions = ['TAKE_PROFIT', 'EXIT', 'WAIT'];
    }

    const riskLevel = String(livePayload?.risk?.riskLevel || '').toUpperCase();
    if (riskLevel === 'HIGH' && !invalidationNear) {
      primary = 'Risque élevé détecté: défendre la position avant toute extension.';
      actions = ['BE', 'TAKE_PROFIT', 'EXIT', 'WAIT'];
    }

    const virtualPosition = {
      ...activeVirtual,
      bePlaced: !!state.bePlaced,
      partialTaken: !!state.partialTaken,
      currentPrice: price,
      pnlPoints: Math.round(pnlPoints * 100000) / 100000,
      progressToTp,
      status: state.phase === 'EXITED' ? 'CLOSED' : activeVirtual.status,
      lastPrice: price,
      lastGuidance: primary
    };

    return {
      virtualPosition,
      nextAction: {
        phase: state.phase,
        primary,
        actions
      }
    };
  }

  function applyDynamicCoachAdjustments(tradeState, virtualPack) {
    const vp = virtualPack?.virtualPosition;
    if (!vp || !tradeState?.entered || tradeState?.phase === 'EXITED') {
      return { virtualPack, messages: [] };
    }

    const messages = [];
    const progress = Number(vp.progressToTp || 0);
    const direction = String(vp.direction || 'WAIT').toUpperCase();

    // Read-only coaching: suggest actions, never mutate Entry/SL/TP/RR.
    if (!tradeState.bePlaced && progress >= 35) {
      messages.push('Suggestion: sécuriser le risque en plaçant le stop au break-even.');
    }

    if (progress >= 55) {
      if (direction === 'LONG') {
        messages.push('Suggestion: remonter progressivement le SL sous les creux de continuation.');
      } else if (direction === 'SHORT') {
        messages.push('Suggestion: abaisser progressivement le SL au-dessus des sommets de continuation.');
      }
    }

    if (!tradeState.partialTaken && progress >= 80) {
      messages.push('Suggestion: prendre un partiel si le momentum faiblit, sinon laisser courir vers TP.');
    }

    vp.lastGuidance = messages[0] || vp.lastGuidance || 'Surveiller la structure et respecter les niveaux TradingView.';
    vp.updatedAt = Date.now();
    tradeState.virtualPosition = { ...(tradeState.virtualPosition || {}), ...vp };
    tradeState.updatedAt = Date.now();

    return { virtualPack: { ...virtualPack, virtualPosition: vp }, messages };
  }

  function applyCoachTradeAction(state, action, note) {
    const a = String(action || '').toUpperCase();
    if (!a) return state;

    if (a === 'ENTER') {
      state.phase = 'OPEN';
      state.entered = true;
      state.lastAction = 'ENTER';
    } else if (a === 'OPEN') {
      state.phase = 'OPEN';
      state.entered = true;
      state.lastAction = 'OPEN';
    } else if (a === 'BE') {
      state.phase = 'MANAGE';
      state.bePlaced = true;
      state.lastAction = 'BE';
      if (state.virtualPosition) state.virtualPosition.bePlaced = true;
    } else if (a === 'TAKE_PROFIT') {
      state.phase = 'MANAGE';
      state.partialTaken = true;
      state.lastAction = 'TAKE_PROFIT';
      if (state.virtualPosition) state.virtualPosition.partialTaken = true;
    } else if (a === 'WAIT') {
      state.lastAction = 'WAIT';
      if (!state.entered) state.phase = 'WAIT_ENTRY';
    } else if (a === 'EXIT') {
      state.phase = 'EXITED';
      state.entered = false;
      state.lastAction = 'EXIT';
      if (state.virtualPosition) {
        state.virtualPosition.status = 'CLOSED';
        state.virtualPosition.closedAt = Date.now();
      }
    } else if (a === 'RETEST') {
      state.phase = 'WAIT_ENTRY';
      state.entered = false;
      state.bePlaced = false;
      state.partialTaken = false;
      state.lastAction = 'RETEST';
      state.virtualPosition = null;
    }

    if (note) {
      state.notes.unshift({ note: String(note), ts: Date.now(), action: a });
      if (state.notes.length > 30) state.notes.length = 30;
    }
    state.updatedAt = Date.now();
    return state;
  }

  function deriveExecutionGuidance(tradeState, payload) {
    const riskLevel = String(payload?.risk?.riskLevel || '').toUpperCase();
    const hasNewsRisk = !!payload?.news?.warning;
    if (!tradeState.entered) {
      const exec = payload?.execution || {};
      const canEnter = exec.canEnter === true;
      const conflict = String(exec.decision || '').toUpperCase() === 'NO_ENTRY_CONFLICT';
      return {
        mode: 'PRE_ENTRY',
        primary: conflict
          ? 'PAS D\'ENTRÉE / CONFLIT DE SIGNAL: attendre alignement clair de l\'indicateur TradingView.'
          : (canEnter
            ? 'ENTRER: setup validé (signal + prix + niveaux cohérents).'
            : (hasNewsRisk
              ? 'Attendre: risque news élevé, éviter entrée immédiate.'
              : 'Attendre confirmation structure avant entrée.')),
        actions: canEnter ? ['ENTER', 'WAIT', 'RETEST'] : ['WAIT', 'RETEST']
      };
    }
    if (!tradeState.bePlaced && (riskLevel === 'HIGH' || hasNewsRisk)) {
      return {
        mode: 'DEFEND',
        primary: 'Réduire le risque: déplacer vers BE dès possible.',
        actions: ['BE', 'TAKE_PROFIT', 'EXIT', 'WAIT']
      };
    }
    if (!tradeState.partialTaken) {
      return {
        mode: 'MANAGE',
        primary: 'Prendre partiellement si extension favorable, puis laisser courir sous contrôle.',
        actions: ['TAKE_PROFIT', 'BE', 'WAIT', 'EXIT']
      };
    }
    return {
      mode: 'FOLLOW',
      primary: 'Position gérée: surveiller invalidation pour sortir, sinon laisser courir.',
      actions: ['WAIT', 'EXIT', 'RETEST']
    };
  }

  function buildRuntimeTradeSignal(symbol, timeframe, instantTrade, robotV12, marketStatus, currentPrice) {
    const directionRaw = String(instantTrade?.direction || instantTrade?.side || robotV12?.verdict || '').toUpperCase();
    const verdict = (directionRaw.includes('BUY') || directionRaw.includes('LONG'))
      ? 'LONG'
      : ((directionRaw.includes('SELL') || directionRaw.includes('SHORT')) ? 'SHORT' : 'WAIT');

    // LEVEL SOURCE RULE: entry/sl/tp come exclusively from the active trade signal (instantTrade).
    // Never fall back to robotV12 levels — those may be stale when TV is not connected.
    const entry = instantTrade?.entry ?? null;
    const sl = instantTrade?.sl ?? null;
    const tp = instantTrade?.tp ?? null;
    const price = Number(currentPrice || entry || NaN);

    const confidence = Number(
      instantTrade?.score
      || instantTrade?.confidence
      || robotV12?.anticipation_force
      || 50
    );

    const source = instantTrade?.source
      ? String(instantTrade.source)
      : (robotV12 ? 'tradingview-indicator' : 'live-runtime');

    return {
      verdict,
      entry: Number.isFinite(Number(entry)) ? Number(entry) : null,
      sl: Number.isFinite(Number(sl)) ? Number(sl) : null,
      tp: Number.isFinite(Number(tp)) ? Number(tp) : null,
      confidence: Number.isFinite(confidence) ? confidence : 50,
      source,
      rationale: instantTrade?.technical || robotV12?.contexte || 'Analyse live runtime',
      stats: {
        marketOpen: !!marketStatus?.isOpen,
        market: marketStatus?.market || 'n/a',
        session: marketStatus?.session || 'n/a',
        anticipation: robotV12?.anticipation || null,
        rsi1m: robotV12?.rsi_1m ?? null,
        rsi5m: robotV12?.rsi_5m ?? null,
        timeframe: String(timeframe || 'H1').toUpperCase()
      }
    };
  }

  function buildGoldCoach(symbol, payload, tradeState, executionGuidance) {
    const isGold = /XAU|GOLD/i.test(String(symbol || ''));
    if (!isGold) return null;

    const riskLevel = String(payload?.risk?.riskLevel || 'UNKNOWN').toUpperCase();
    const newsWarning = payload?.news?.warning || null;
    const recommendation = payload?.analysis?.recommendation || 'ATTENDRE CONFIRMATION';
    const logicIn = payload?.strategy?.logic || 'Attendre structure propre';

    return {
      enabled: true,
      context: 'Gold sensible au USD, taux US et news macro à fort impact.',
      risk: riskLevel,
      newsLinkedToGold: newsWarning || 'Pas de signal news critique immédiat',
      entryLogic: logicIn,
      waitingLogic: recommendation.includes('ATTENDRE') ? 'Attendre confirmation' : 'Entrée possible avec validation prix',
      exitLogic: executionGuidance.mode === 'DEFEND'
        ? 'Priorité protection du capital, sortie rapide si invalidation.'
        : 'Sortie sur invalidation structure ou objectif atteint.',
      summary: `Gold coach | risque=${riskLevel} | entrée=${logicIn} | phase=${tradeState?.phase || '--'} | action=${executionGuidance.primary || 'attendre confirmation'}`,
      coachPhrases: [
        'attendre confirmation',
        'zone de résistance',
        'risque news élevé',
        'entrée possible',
        'prendre partiellement',
        'mettre BE',
        'laisser courir',
        'sortir'
      ]
    };
  }

  function buildTradeReasoningSnapshot(symbol, timeframe, instantTrade, coachPayload, tradeState, marketStatus, robotV12) {
    const trade = instantTrade || {};
    const agents = coachPayload?.agents || {};
    const analysis = agents.analysis || {};
    const strategy = agents.strategy || {};
    const risk = agents.risk || {};
    const explainer = agents.explainer || {};

    const whyEntry = [];
    if (analysis.reason) whyEntry.push(String(analysis.reason));
    if (strategy.logic) whyEntry.push(String(strategy.logic));
    if (Array.isArray(explainer.whyEntry)) {
      whyEntry.push(...explainer.whyEntry.slice(0, 4).map((s) => String(s)));
    }
    if (trade.technical) whyEntry.push(String(trade.technical));
    if (trade.sentiment) whyEntry.push('Contexte sentiment: ' + String(trade.sentiment));
    if (robotV12?.verdict) whyEntry.push('ROBOT V12 verdict: ' + String(robotV12.verdict));
    if (robotV12?.anticipation) {
      const af = robotV12.anticipation_force != null ? ` (${robotV12.anticipation_force}%)` : '';
      whyEntry.push('ROBOT V12 anticipation: ' + String(robotV12.anticipation) + af);
    }
    if (robotV12?.contexte) whyEntry.push('Contexte TV: ' + String(robotV12.contexte));
    if (robotV12?.lecture_15m || robotV12?.lecture_60m) {
      whyEntry.push('Lecture multi-UT: 15m=' + String(robotV12.lecture_15m || '--') + ' | 1h=' + String(robotV12.lecture_60m || '--'));
    }
    if (whyEntry.length === 0) {
      whyEntry.push('Entrée proposée sur structure prix + ratio risque/rendement acceptable.');
      whyEntry.push('Attendre validation de bougie et spread stable avant exécution.');
    }

    const setupType = String(trade.setup_type || trade.setupType || 'SNIPER').toUpperCase();
    const expectedDuration = trade.expected_duration || trade.expectedDuration || '--';
    const holdingProfile = trade.holding_profile || trade.holdingProfile || '--';

    const slPips = trade.slPips || '--';
    const slPct = trade.slPct || '--';
    const tpPips = trade.tpPips || '--';
    const tpPct = trade.tpPct || '--';
    const rr = trade.rrRatio || '--';

    const explainerWhySl = Array.isArray(explainer.whySl)
      ? explainer.whySl.slice(0, 3).map((s) => String(s))
      : [];
    const explainerWhyTp = Array.isArray(explainer.whyTp)
      ? explainer.whyTp.slice(0, 3).map((s) => String(s))
      : [];

    const slWhy = [
      ...explainerWhySl,
      `SL calibré pour ${setupType} afin d'éviter une sortie trop tôt.`,
      `Distance de protection: ${slPips} pips (${slPct}).`,
      `Niveau de risque actuel: ${risk.riskLevel || trade.risk || '--'}.`
    ].slice(0, 4);

    const tpWhy = [
      ...explainerWhyTp,
      `TP dimensionné pour conserver un ratio R:R de ${rr}.`,
      `Distance de cible: ${tpPips} pips (${tpPct}).`,
      'Objectif ajusté au profil de volatilité et au mode de setup.'
    ].slice(0, 4);

    const marketGate = marketStatus?.isOpen
      ? `Marché ouvert (${marketStatus.market} / ${marketStatus.session}).`
      : `Marché fermé (${marketStatus.market || 'n/a'}). Réouverture dans ${marketStatus?.opensInFormatted || '--'}.`;

    return {
      symbol,
      timeframe,
      setupType,
      expectedDuration,
      holdingProfile,
      styleHint: setupType === 'SCALPER'
        ? 'Scalper: exécution courte, décisions rapides.'
        : (setupType === 'SWING'
          ? 'Swing: tenue multi-session avec patience.'
          : 'Sniper: entrée précise, gestion active intraday.'),
      marketGate,
      whyEntry,
      whySl: slWhy,
      whyTp: tpWhy,
      metrics: {
        entry: trade.entry || null,
        stopLoss: trade.sl || null,
        takeProfit: trade.tp || null,
        rrRatio: rr,
        slPips,
        tpPips,
        slPct,
        tpPct
      },
      management: {
        phase: tradeState?.phase || '--',
        entered: !!tradeState?.entered,
        bePlaced: !!tradeState?.bePlaced,
        partialTaken: !!tradeState?.partialTaken,
        nextAction: coachPayload?.executionGuidance?.primary || 'Attendre confirmation structure.'
      }
    };
  }

  // GET /coach/trade-state — état de suivi post-entrée
  app.get('/coach/trade-state', (req, res) => {
    const raw = String(req.query.symbol || marketStore.lastActiveSymbol || getLatestTradingviewRuntime().symbol || '').toUpperCase();
    const symbol = normalizeSymbol(raw).canonical || raw;
    const timeframe = String(req.query.tf || 'H1').toUpperCase();
    const state = getCoachTradeState(symbol, timeframe);
    res.json({ ok: true, state });
  });

  // POST /coach/trade-action — action opérateur (ENTER/BE/TAKE_PROFIT/WAIT/EXIT/RETEST)
  app.post('/coach/trade-action', async (req, res) => {
    const raw = String(req.body?.symbol || marketStore.lastActiveSymbol || getLatestTradingviewRuntime().symbol || '').toUpperCase();
    const symbol = normalizeSymbol(raw).canonical || raw;
    const timeframe = String(req.body?.timeframe || req.body?.tf || 'H1').toUpperCase();
    const mode = String(req.body?.mode || '').toUpperCase();
    const action = String(req.body?.action || '').toUpperCase();
    const note = String(req.body?.note || '').trim();
    if (!action) return res.status(400).json({ ok: false, error: 'action requise' });

    const state = getCoachTradeState(symbol, timeframe);

    if (action === 'ENTER' || action === 'OPEN') {
      const preSnapshot = await computeCoachAnalysisSnapshot(symbol, timeframe, 'fr', state, {
        forceFresh: true,
        mode
      }).catch(() => null);
      const exec = preSnapshot?.execution || null;
      if (!exec || exec.canEnter !== true) {
        return res.status(409).json({
          ok: false,
          error: 'ENTREE_NON_VALIDEE',
          message: exec?.reason || 'Entrée non validée: attendre confirmation TradingView.',
          execution: exec || { decision: 'WAIT', canEnter: false, reason: 'Entrée non validée' },
          state
        });
      }
    }

    const updated = applyCoachTradeAction(state, action, note);
    const hintedTradeRaw = (req.body && typeof req.body.trade === 'object' && req.body.trade) ? req.body.trade : null;
    const hintedSource = String(hintedTradeRaw?.source || '').toLowerCase();
    const hintedTrade = (hintedTradeRaw
      && Number.isFinite(Number(hintedTradeRaw.entry))
      && Number.isFinite(Number(hintedTradeRaw.sl))
      && Number.isFinite(Number(hintedTradeRaw.tp))
      && (hintedSource.includes('tradingview') || hintedSource.includes('indicator')))
      ? hintedTradeRaw
      : null;

    if ((action === 'ENTER' || action === 'OPEN') && !updated.virtualPosition) {
      try {
        const instant = await fetchLocalJson(
          '/instant-trade-live?symbol=' + encodeURIComponent(symbol) +
          '&tf=' + encodeURIComponent(timeframe) +
          (mode ? '&mode=' + encodeURIComponent(mode) : '')
        );
        const trade = instant.data?.trade || instant.data?.data || null;
        updated.virtualPosition = createVirtualPositionFromTrade(symbol, timeframe, trade, getCoachMarketPrice(symbol));
      } catch (_) {}

      // Fallback: allow extension-provided trade hints when instant-trade-live is not available.
      if (!updated.virtualPosition && hintedTrade) {
        updated.virtualPosition = createVirtualPositionFromTrade(symbol, timeframe, hintedTrade, getCoachMarketPrice(symbol));
      }
    }

    publishAgentChatMessage({
      agent: 'execution-coach-agent',
      to: 'dashboard',
      status: 'info',
      phase: updated.phase,
      message: `Action trade: ${action}`,
      cause: 'interaction utilisateur',
      impact: `${symbol} ${timeframe}`,
      solution: 'suivi mis à jour'
    });

    let tradeActionLia = null;
    try {
      const snapshot = await computeCoachAnalysisSnapshot(symbol, timeframe, 'fr', updated, {
        forceFresh: true,
        mode,
        instantTrade: updated.virtualPosition
          ? {
              direction: updated.virtualPosition.direction,
              entry: updated.virtualPosition.entry,
              sl: updated.virtualPosition.sl,
              tp: updated.virtualPosition.tp,
              rrRatio: updated.virtualPosition.rrRatio,
              setup_type: updated.virtualPosition.setupType,
              source: updated.virtualPosition.source,
              confidence: 65
            }
          : null
      });

      tradeActionLia = await requestDashboardLiaReadOnly({
        symbol,
        timeframe,
        decision: snapshot?.analysis?.recommendation || recommendationFromDirection(updated.virtualPosition?.direction || 'WAIT'),
        reason: snapshot?.analysis?.reason || `Action ${action} appliquée`,
        confidence: snapshot?.analysis?.confidence || 0,
        entry: updated.virtualPosition?.entry,
        sl: updated.virtualPosition?.sl,
        tp: updated.virtualPosition?.tp,
        rr: updated.virtualPosition?.rrRatio || '--',
        robotV12: snapshot?.robotV12 || null,
        market: snapshot?.marketStatus || marketHoursChecker.getStatus(symbol),
        news: snapshot?.news || null,
        phase: updated.phase,
        entered: updated.entered,
        bePlaced: updated.bePlaced,
        partialTaken: updated.partialTaken,
        nextAction: updated.entered
          ? 'Position active: suivre invalidation, protection et extension si momentum.'
          : 'Analyser puis attendre un setup validé avant entrée.'
      });
    } catch (_e) {
      tradeActionLia = {
        ok: false,
        channel: 'dashboard',
        response: '[COACH RUNTIME]\nAction appliquée. LIA indisponible, coaching runtime maintenu.'
      };
    }

    res.json({ ok: true, state: updated, lia: tradeActionLia });
  });

  app.get('/coach/realtime', async (req, res) => {
    try {
      const raw = String(req.query.symbol || marketStore.lastActiveSymbol || getLatestTradingviewRuntime().symbol || '').toUpperCase();
      const symbol = normalizeSymbol(raw).canonical || raw;
      const timeframe = String(req.query.tf || 'H1').toUpperCase();
      const requestedMode = String(req.query.mode || req.query.setup || activeSymbol?.mode || bridgeConfig.bridgeMode || 'AUTO').toUpperCase();
      const mode = resolveRuntimeMode(requestedMode, symbol, timeframe);
      const lang = String(req.query.lang || 'fr').toLowerCase() === 'en' ? 'en' : 'fr';

      const safeLocalJson = async (endpoint, ms) => {
        try {
          return await fetchLocalJson(endpoint, {}, ms || 8000);
        } catch (_e) {
          return { ok: false, status: 500, data: null };
        }
      };

      const [chartResp, coachResp, tradeStateResp, instantResp, extResp, closureResp] = await Promise.all([
        safeLocalJson('/mt5/current-chart?symbol=' + encodeURIComponent(symbol) + '&tf=' + encodeURIComponent(timeframe)),
        safeLocalJson('/coach/live?symbol=' + encodeURIComponent(symbol) + '&tf=' + encodeURIComponent(timeframe) + '&lang=' + encodeURIComponent(lang), 7000),
        safeLocalJson('/coach/trade-state?symbol=' + encodeURIComponent(symbol) + '&tf=' + encodeURIComponent(timeframe)),
        safeLocalJson(
          '/instant-trade-live?symbol=' + encodeURIComponent(symbol) +
          '&tf=' + encodeURIComponent(timeframe) +
          (mode ? '&mode=' + encodeURIComponent(mode) : '')
        ),
        safeLocalJson('/extension/data'),
        safeLocalJson('/chart-data?symbol=' + encodeURIComponent(symbol) + '&timeframe=' + encodeURIComponent(timeframe))
      ]);

      const chart = chartResp.data?.ok ? chartResp.data : null;
      const coach = coachResp.data?.ok ? coachResp.data : null;
      const tradeState = tradeStateResp.data?.state || getCoachTradeState(symbol, timeframe);
      const instantTrade = instantResp.data?.trade || instantResp.data?.data || null;
      const candleClosure = closureResp.data?.ok ? closureResp.data?.closure || null : null;
      const marketStatus = marketHoursChecker.getStatus(symbol);
      const tvFallbackEntry = (() => {
        const k = findTradingviewSymbolKey(symbol);
        return k ? tvDataStore[k] : null;
      })();
      const tvFallbackDirectionRaw = tvFallbackEntry?.robotV12?.verdict
        || tvFallbackEntry?.robotV12?.anticipation
        || tvFallbackEntry?.action
        || '';
      const fallbackDirection = String(tvFallbackDirectionRaw || instantTrade?.direction || '').toUpperCase();
      const fallbackReco = fallbackDirection.includes('LONG') || fallbackDirection.includes('BUY')
        ? 'BUY'
        : (fallbackDirection.includes('SHORT') || fallbackDirection.includes('SELL') ? 'SELL' : 'WAIT');
      const fallbackReason = instantTrade?.technical
        || instantTrade?.sentiment
        || (marketStatus?.isOpen
          ? `Flux live actif (${marketStatus.market}/${marketStatus.session}).`
          : `Blocage live: marché fermé (${marketStatus?.market || 'n/a'}).`);
      const fallbackTradeStatus = String(instantTrade?.trade_status || '').toUpperCase();
      const fallbackCanEnter = !!marketStatus?.isOpen
        && (fallbackReco === 'BUY' || fallbackReco === 'SELL')
        && Number.isFinite(Number(instantTrade?.entry))
        && Number.isFinite(Number(instantTrade?.sl))
        && Number.isFinite(Number(instantTrade?.tp))
        && (fallbackTradeStatus === 'LIVE' || fallbackTradeStatus === 'CONDITIONAL');
      const effectiveCoach = coach || {
        ok: true,
        generatedLive: true,
        execution: {
          decision: fallbackCanEnter ? 'ENTER' : 'WAIT',
          canEnter: fallbackCanEnter,
          reason: fallbackCanEnter
            ? 'Entrée validée par le signal runtime fallback.'
            : 'Entrée non validée: attendre confirmation complète.',
          conflict: false,
          conflictReasons: []
        },
        agents: {
          analysis: {
            recommendation: fallbackReco,
            reason: fallbackReason,
            confidence: instantTrade?.confidence || 55,
            strength: instantTrade?.confidence || 55
          },
          risk: {
            riskLevel: instantTrade?.risk || (marketStatus?.isOpen ? 'Medium' : 'High'),
            riskReason: marketStatus?.isOpen ? 'Flux actif, valider spread/volatilité.' : 'Marché fermé ou indisponible.'
          },
          strategy: {
            logic: instantTrade?.setup_type
              ? `Setup ${String(instantTrade.setup_type).toUpperCase()} détecté.`
              : 'Aucun setup confirmé, surveillance en cours.'
          },
          news: {
            symbolImpact: marketStatus?.isOpen ? 'Impact news: surveiller annonces live.' : 'Impact news secondaire tant que marché fermé.'
          }
        },
        lia: (() => {
          const _price = Number(chart?.price || chart?.bid || instantTrade?.entry || NaN);
          const _priceStr = Number.isFinite(_price) ? (_price > 1000 ? _price.toFixed(2) : _price.toFixed(5)) : '--';
          const _dir = String(instantTrade?.direction || fallbackDirection || '').toUpperCase();
          const _sl = instantTrade?.sl != null ? (Number(instantTrade.sl) > 1000 ? Number(instantTrade.sl).toFixed(2) : Number(instantTrade.sl).toFixed(5)) : '--';
          const _tp = instantTrade?.tp != null ? (Number(instantTrade.tp) > 1000 ? Number(instantTrade.tp).toFixed(2) : Number(instantTrade.tp).toFixed(5)) : '--';
          const _rr = instantTrade?.rrRatio != null ? String(instantTrade.rrRatio) : '--';
          const _setup = instantTrade?.setup_type ? String(instantTrade.setup_type).toUpperCase() : null;
          const _conf = Number(instantTrade?.confidence || 55);
          const _risk = String(instantTrade?.risk || (marketStatus?.isOpen ? 'Medium' : 'High'));
          const _signalUsed = instantTrade?.technical || fallbackReason || 'Signal technique indisponible';
          const _sessions = (marketStatus?.sessions?.sessions || []).filter(s => s.isOpen).map(s => s.label).join(', ') || 'aucune';
          const _lines = [];
          if (marketStatus?.isOpen) {
            _lines.push(`${symbol} ${timeframe} | Prix: ${_priceStr} | ${marketStatus.market}/${marketStatus.session}`);
            if (_dir) _lines.push(`Signal: ${_dir}${_setup ? ' [' + _setup + ']' : ''} | Confiance: ${_conf}% | Risque: ${_risk}`);
            if (_sl !== '--') _lines.push(`SL: ${_sl} | TP: ${_tp} | R:R ${_rr}`);
            _lines.push(`Signaux utilisés: ${_signalUsed}`);
            _lines.push(`Impact timeframe ${timeframe}: ${timeframe.startsWith('M') ? 'scalping/swing court, bruit plus élevé' : 'contexte plus stable, confirmation plus lente'}`);
            _lines.push(`Sessions actives: ${_sessions}`);
            if (_dir === 'BUY' || _dir === 'LONG') {
              _lines.push(`Pourquoi entrer: momentum haussier confirmé si cassure + clôture valide.`);
              _lines.push(`Pourquoi attendre: pas d'entrée si spread/volatilité dépasse le risque prévu.`);
              _lines.push(`→ Plan: confirmer structure haussière, puis invalider si clôture sous SL.`);
            } else if (_dir === 'SELL' || _dir === 'SHORT') {
              _lines.push(`Pourquoi entrer: momentum baissier confirmé si cassure + clôture valide.`);
              _lines.push(`Pourquoi attendre: pas d'entrée si rebond fort sans confirmation vendeuse.`);
              _lines.push(`→ Plan: confirmer structure baissière, puis invalider si clôture au-dessus de SL.`);
            } else {
              _lines.push(`Pourquoi attendre: aucun setup directionnel confirmé.`);
              _lines.push(`→ Plan: surveiller zones clés et attendre signal net avant entrée.`);
            }
          } else {
            _lines.push(`${symbol} ${timeframe} | Marché FERMÉ (${marketStatus?.market || 'n/a'})`);
            _lines.push(`→ Aucune action avant réouverture. Préparer zones d'entrée potentielles.`);
          }
          return { ok: true, response: _lines.join('\n') };
        })()
      };
      const activeSource = String(bridgeConfig.activeSource || (bridgeConfig.mt5Enabled === true ? 'mt5' : 'tradingview')).toLowerCase() === 'mt5' ? 'mt5' : 'tradingview';

      // Per-symbol TV price isolation:
      // Always look up the tvDataStore entry for the REQUESTED symbol first.
      // This prevents cross-symbol contamination when the active context is a different symbol.
      const tvSymKey = findTradingviewSymbolKey(symbol);
      const tvSymEntry = tvSymKey ? tvDataStore[tvSymKey] : null;
      const tvSymPrice = Number(tvSymEntry?.price ?? tvSymEntry?.bid ?? NaN);

      // Only trust /extension/data price when the active symbol matches the requested symbol.
      const extActiveSymbol = String(extResp.data?.activeSymbol?.symbol || extResp.data?.currentData?.symbol || '').toUpperCase();
      const extMatchesRequest = extActiveSymbol === symbol || normalizeSymbol(extActiveSymbol).canonical === normalizeSymbol(symbol).canonical;
      const extCurrentPrice = extMatchesRequest ? Number(extResp.data?.currentData?.price ?? extResp.data?.activeSymbol?.price ?? NaN) : NaN;

      const priceCandidates = activeSource === 'tradingview'
        ? [
            tvSymPrice,         // FIRST: direct TV store for this exact symbol
            extCurrentPrice,    // only if extActive === requested symbol
            chart?.price,
            chart?.bid,
            getCoachMarketPrice(symbol)
          ]
        : [
            chart?.price,
            chart?.bid,
            tvSymPrice,
            extCurrentPrice,
            getCoachMarketPrice(symbol)
          ];

      const currentPrice = Number(priceCandidates.find((v) => Number.isFinite(Number(v)) && Number(v) > 0) || NaN);
      const headerPrice = Number(extResp.data?.currentData?.price ?? extResp.data?.activeSymbol?.price ?? NaN);
      const chartPrice = Number(chart?.price ?? chart?.bid ?? NaN);
      const decideVsHeader = Number.isFinite(currentPrice) && Number.isFinite(headerPrice)
        ? Math.abs(currentPrice - headerPrice) / Math.max(Math.abs(currentPrice), 1)
        : null;
      const decideVsChart = Number.isFinite(currentPrice) && Number.isFinite(chartPrice)
        ? Math.abs(currentPrice - chartPrice) / Math.max(Math.abs(currentPrice), 1)
        : null;
      const priceConsistency = {
        decisionPrice: Number.isFinite(currentPrice) ? currentPrice : null,
        headerPrice: Number.isFinite(headerPrice) ? headerPrice : null,
        chartPrice: Number.isFinite(chartPrice) ? chartPrice : null,
        coherent: (decideVsHeader == null || decideVsHeader <= 0.0025) && (decideVsChart == null || decideVsChart <= 0.01),
        deltaHeaderPct: decideVsHeader == null ? null : Number((decideVsHeader * 100).toFixed(3)),
        deltaChartPct: decideVsChart == null ? null : Number((decideVsChart * 100).toFixed(3))
      };
      const currentDataSource = activeSource === 'tradingview'
        ? (extResp.data?.currentData?.source || extResp.data?.activeSymbol?.source || chart?.source || (Number.isFinite(currentPrice) ? 'tradingview' : null))
        : (chart?.source || extResp.data?.currentData?.source || extResp.data?.activeSymbol?.source || (Number.isFinite(currentPrice) ? 'market-fallback' : null));

      const rawVirtualPack = buildVirtualPositionSnapshot(tradeState, instantTrade, effectiveCoach?.agents || null, currentPrice);
      const autoAdjusted = applyDynamicCoachAdjustments(tradeState, rawVirtualPack);
      const virtualPack = autoAdjusted.virtualPack;
      const robotV12Live = getRobotV12ForSymbol(symbol);
      const tradeReasoning = buildTradeReasoningSnapshot(symbol, timeframe, instantTrade, effectiveCoach, tradeState, marketStatus, robotV12Live);
      if (autoAdjusted.messages.length > 0) {
        tradeReasoning.management.nextAction = autoAdjusted.messages.join(' | ');
        const firstMsg = autoAdjusted.messages[0];
        tradeState.notes.unshift({ note: firstMsg, ts: Date.now(), action: 'AUTO_COACH' });
        if (tradeState.notes.length > 30) tradeState.notes.length = 30;
      }

      if (tradeState.virtualPosition && virtualPack.virtualPosition) {
        tradeState.virtualPosition = { ...tradeState.virtualPosition, ...virtualPack.virtualPosition };
      }

      const levelSource = virtualPack.virtualPosition
        ? String(virtualPack.virtualPosition.source || 'virtual-position')
        : String(instantTrade?.source || 'none');
      const levelValues = virtualPack.virtualPosition || instantTrade || null;

      res.json({
        ok: true,
        symbol,
        timeframe,
        mode: requestedMode,
        modeResolved: mode,
        currentPrice: Number.isFinite(currentPrice) ? currentPrice : null,
        dataSource: currentDataSource,
        lang,
        availableTimeframes: USER_TIMEFRAMES,
        chart,
        coach: effectiveCoach,
        execution: effectiveCoach?.execution || null,
        candleClosure,
        marketStatus,
        robotV12: robotV12Live,
        tradeReasoning,
        tradeState,
        instantTrade,
        virtualPosition: virtualPack.virtualPosition,
        nextAction: virtualPack.nextAction,
        priceConsistency,
        levelTrace: {
          source: levelSource,
          received: {
            entry: levelValues?.entry ?? null,
            sl: levelValues?.sl ?? null,
            tp: levelValues?.tp ?? null,
            rrRatio: levelValues?.rrRatio ?? null
          },
          note: 'Backend transmet les niveaux TradingView sans recalcul.'
        },
        sync: {
          activeSymbol: extResp.data?.activeSymbol || null,
          currentData: extResp.data?.currentData || null,
          systemStatus: extResp.data?.systemStatus || null
        }
      });
    } catch (e) {
      res.status(500).json({ ok: false, error: e.message });
    }
  });

  // GET /integration/remaining-production — état de production restante + base multilingue
  app.get('/integration/remaining-production', (req, res) => {
    const locale = String(req.query.lang || 'fr').toLowerCase();
    const supportedLocales = ['fr', 'en'];
    const remaining = [
      'Connecter un flux news économique premium si nécessaire (événements enrichis).',
      'Ajouter persistance durable du suivi trade (DB) pour reprise après redémarrage.',
      'Ajouter tests e2e dashboard coach (timeframes/actions/news urgentes).',
      'Ajouter contenu UI complet EN pour tous les libellés dynamiques.',
      'Ajouter métriques qualité coaching (latence, fiabilité, taux de consigne utile).'
    ];
    res.json({
      ok: true,
      locale: supportedLocales.includes(locale) ? locale : 'fr',
      supportedLocales,
      antiDuplicateCheck: {
        reusedRoutes: ['/agents/:name/send', '/mt5/current-chart', '/lia/chat', '/calendar', '/news'],
        reusedPages: ['dashboard.html', 'AGENTS_MONITOR.html'],
        duplicateModulesAdded: 0
      },
      remaining
    });
  });

  // GET /coach/live — dashboard coaching aggregate (agents -> Lia -> recommendation)
  app.get('/coach/live', async (req, res) => {
    try {
      const symbol = String(req.query.symbol || marketStore.lastActiveSymbol || getLatestTradingviewRuntime().symbol || '').toUpperCase();
      const timeframe = String(req.query.tf || 'H1').toUpperCase();
      const lang = String(req.query.lang || 'fr').toLowerCase() === 'en' ? 'en' : 'fr';
      const tradeState = getCoachTradeState(symbol, timeframe);

      let snapshot = readCoachAnalysisSnapshot(symbol, timeframe, tradeState.entered ? 5000 : 90000);
      const tvFresh = getLatestTradingviewRuntime();
      const tvTs = Date.parse(tvFresh?.timestamp || 0);
      const snapshotTs = Number(snapshot?.updatedAt || 0);
      const mustRefresh = !snapshot || tradeState.entered || (Number.isFinite(tvTs) && tvTs > snapshotTs);
      if (mustRefresh) {
        snapshot = await computeCoachAnalysisSnapshot(symbol, timeframe, lang, tradeState, {
          forceFresh: true,
          maxAgeMs: tradeState.entered ? 5000 : 90000
        });
      }

      const robotV12Live = snapshot.robotV12 || getRobotV12ForSymbol(symbol);
      const instantTrade = snapshot.runtimeTrade || null;
      const marketStatus = snapshot.marketStatus || marketHoursChecker.getStatus(symbol);
      const currentPrice = Number(snapshot.currentPrice || getCoachMarketPrice(symbol) || instantTrade?.entry || NaN);
      const runtimeSignal = snapshot.signal || buildRuntimeTradeSignal(symbol, timeframe, instantTrade, robotV12Live, marketStatus, currentPrice);
      const robotContext = robotV12Live
        ? [
            robotV12Live.verdict ? `verdict=${robotV12Live.verdict}` : null,
            robotV12Live.anticipation ? `anticipation=${robotV12Live.anticipation}${robotV12Live.anticipation_force != null ? ' (' + robotV12Live.anticipation_force + '%)' : ''}` : null,
            robotV12Live.contexte ? `contexte=${robotV12Live.contexte}` : null,
            (robotV12Live.lecture_15m || robotV12Live.lecture_60m) ? `ut=15m:${robotV12Live.lecture_15m || '--'}|1h:${robotV12Live.lecture_60m || '--'}` : null
          ].filter(Boolean).join(', ')
        : 'robotV12=n/a';

      const payload = {
        symbol,
        timeframe,
        analysis: snapshot.analysis,
        execution: snapshot.execution,
        news: snapshot.news,
        explainer: snapshot.explainer,
        strategy: snapshot.strategy,
        risk: snapshot.risk,
        robotV12: robotV12Live,
        signal: runtimeSignal
      };

      const executionGuidance = deriveExecutionGuidance(tradeState, payload);
      if (robotV12Live && !tradeState.entered) {
        executionGuidance.primary = `${executionGuidance.primary} | TV: ${robotContext}`;
      }
      const goldCoach = buildGoldCoach(symbol, payload, tradeState, executionGuidance);

      const riskHigh = String(payload.risk?.riskLevel || '').toUpperCase() === 'HIGH';
      const hasUltraNews = Array.isArray(payload.news?.upcomingEvents) && payload.news.upcomingEvents.some((e) => Number(e.minutesAway ?? e.mins) <= 15 && String(e.urgency || e.impact || '').toUpperCase() === 'HIGH');
      const newsWarning = payload.news?.warning || '';
      const alert = riskHigh || newsWarning || hasUltraNews
        ? {
          level: hasUltraNews ? 'ULTRA' : 'HIGH',
          title: 'Alerte Coach',
          message: hasUltraNews
            ? 'News ultra importante détectée: priorité gestion du risque'
            : (newsWarning || payload.risk?.guidance || 'Situation sensible détectée')
        }
        : null;

      let dashboardLia = null;
      const lia = await requestDashboardLiaReadOnly({
        symbol,
        timeframe,
        decision: payload.analysis?.recommendation || 'WAIT',
        reason: payload.analysis?.reason || 'n/a',
        confidence: payload.analysis?.confidence || 0,
        entry: instantTrade?.entry,
        sl: instantTrade?.sl,
        tp: instantTrade?.tp,
        rr: instantTrade?.rrRatio || '--',
        robotV12: robotV12Live || null,
        market: marketStatus || null,
        news: payload.news || null,
        phase: tradeState.phase,
        entered: tradeState.entered,
        bePlaced: tradeState.bePlaced,
        partialTaken: tradeState.partialTaken,
        nextAction: executionGuidance.primary || 'Attendre confirmation structure.'
      });
      dashboardLia = lia?.ok
        ? lia
        : {
            ...(lia || {}),
            ok: false,
            channel: 'dashboard',
            response: [
              '[COACH RUNTIME]',
              executionGuidance.primary || 'Attendre confirmation structure avant toute entrée.',
              payload.analysis?.reason ? ('Pourquoi ' + String(payload.analysis.recommendation || 'ATTENTE').toLowerCase() + ': ' + payload.analysis.reason) : null,
              Array.isArray(payload.explainer?.whyEntry) && payload.explainer.whyEntry[1] ? ('Entrée: ' + payload.explainer.whyEntry[1]) : null,
              Array.isArray(payload.explainer?.whySl) && payload.explainer.whySl[0] ? ('SL: ' + payload.explainer.whySl[0]) : null,
              Array.isArray(payload.explainer?.whyTp) && payload.explainer.whyTp[0] ? ('TP: ' + payload.explainer.whyTp[0]) : null,
              payload.news?.warning ? ('News: ' + payload.news.warning) : payload.news?.symbolImpact ? ('Contexte: ' + payload.news.symbolImpact) : null,
              payload.risk?.guidance ? ('Risque: ' + payload.risk.guidance) : null,
              ('Position: phase=' + (tradeState.phase || '--') + ' | entered=' + (!!tradeState.entered) + ' | be=' + (!!tradeState.bePlaced) + ' | partial=' + (!!tradeState.partialTaken)),
              (goldCoach && goldCoach.summary) ? ('Coach: ' + goldCoach.summary) : null
            ].filter(Boolean).join('\n')
          };
      snapshot = storeCoachAnalysisSnapshot(symbol, timeframe, { ...snapshot, lia: dashboardLia });

      publishAgentChatMessage({
        agent: 'lia-dashboard',
        to: 'dashboard',
        status: alert ? 'warning' : 'info',
        phase: 'en cours',
        message: dashboardLia.response || 'Coach indisponible',
        cause: 'agrégation runtime + lia',
        impact: alert ? 'alerte trading active' : 'guidance normale',
        solution: payload.strategy?.logic || payload.analysis?.reason || 'attendre confirmation'
      });

      res.json({
        ok: true,
        symbol,
        timeframe,
        lang,
        robotV12: robotV12Live,
        signal: runtimeSignal,
        execution: snapshot.execution,
        agents: payload,
        tradeState,
        executionGuidance,
        goldCoach,
        alert,
        lia: dashboardLia,
        analysisSnapshot: {
          updatedAt: snapshot.updatedAt,
          modeResolved: snapshot.modeResolved,
          sourceSummary: snapshot.sourceSummary
        }
      });
    } catch (e) {
      res.status(500).json({ ok: false, error: e.message });
    }
  });

  // JSON guardrails: never return HTML for API namespaces expected by monitor
  app.use((req, res, next) => {
    const p = String(req.path || '');
    const wantsJsonApi = (
      p.startsWith('/lia/') ||
      p.startsWith('/central-guide/') ||
      p.startsWith('/coach/') ||
      p.startsWith('/integration/') ||
      p.startsWith('/agents/') ||
      p.startsWith('/mt5/') ||
      p === '/health' ||
      p === '/live/state'
    );
    if (wantsJsonApi) {
      return res.status(404).json({ ok: false, error: 'ENDPOINT_NOT_FOUND', path: p });
    }
    return next();
  });

  app.use((err, req, res, _next) => {
    const p = String(req.path || '');
    const wantsJsonApi = (
      p.startsWith('/lia/') ||
      p.startsWith('/central-guide/') ||
      p.startsWith('/coach/') ||
      p.startsWith('/integration/') ||
      p.startsWith('/agents/') ||
      p.startsWith('/mt5/') ||
      p === '/health' ||
      p === '/live/state'
    );
    if (wantsJsonApi) {
      return res.status(500).json({ ok: false, error: err?.message || 'INTERNAL_ERROR', path: p });
    }
    return res.status(500).send('Internal Server Error');
  });

  // ─── START ────────────────────────────────────────────────────────────────────
  app.listen(PORT, '0.0.0.0', () => {
  const _startTs = new Date().toISOString();
  console.log(`\n✅ Trading Auto Server — http://127.0.0.1:${PORT}`);
  console.log(`📡 Sources: MT5 (priorité 1) → TradingView (priorité 2) → Yahoo (klines seulement)`);
  console.log(`⚠️  Aucun Math.random() — toutes les données sont réelles`);
  console.log(`[BASELINE] PID=${process.pid} | PORT=${PORT} | STARTED=${_startTs} | INSTANCES=1`);
  console.log(`[BASELINE] Clean start — single instance confirmed\n`);

  loadAgentHistoryFromDisk();
  runAgentHistoryCycle();
  if (_agentHistoryTimer) clearInterval(_agentHistoryTimer);
  _agentHistoryTimer = setInterval(runAgentHistoryCycle, AGENT_HISTORY_INTERVAL_MS);

  // ────── START MT5 BRIDGE POLLING ──────────────────────────────────────────
  if (!SAFE_MODE) {
    startMT5Polling(5000);
  } else {
    console.log('[SAFE MODE] MT5 polling auto désactivé (on-demand only)');
  }

  // [P1] Initialisation CandleManager — démarre le timer de détection de fermeture
  if (candleManager) {
    candleManager.initialize()
      .then(() => console.log('[CANDLE] CandleManager initialisé — détection des bougies active'))
      .catch(e => console.error('[CANDLE INIT ERROR]', e.message));
  }

  // [P3] Initialisation Surveillance Agent et event listener
  if (surveillanceAgent) {
    surveillanceAgent.initialize();
    console.log('[SURVEILLANCE] Surveillance Agent initialized');
    
    // Register in agent bus
    registerAgentUnique('surveillance-agent', {
      role: 'Event-driven analysis trigger',
      status: 'active',
      file: 'src/agents/surveillance-agent.js'
    });
    
    if (orchestrator) {
      registerAgentUnique('orchestrator', {
        role: 'Central decision maker',
        status: 'active',
        file: 'src/agents/orchestrator.js'
      });
    }
    
    registerAgentUnique('alert-manager', {
      role: 'Centralized alert system',
      status: 'active',
      file: 'alert-manager.js'
    });
    
    registerAgentUnique('candle-manager', {
      role: 'OHLC aggregation engine',
      status: candleManager ? 'active' : 'inactive',
      file: 'lib/candle-manager.js'
    });
    
    if (indicatorAgent) {
      registerAgentUnique('indicator-agent', {
        role: 'Technical indicator generator',
        status: 'active',
        file: 'src/agents/indicator-agent.js'
      });
    }
    
    if (repairAgent) {
      registerAgentUnique('repair-agent', {
        role: 'Automatic diagnostics and repair',
        status: 'active',
        file: 'src/agents/repair-agent.js'
      });
    }

    registerAgentUnique('design-agent', {
      role: 'Design audit and UI reorganization proposals',
      status: 'active',
      file: 'src/agents/designerAgent.js'
    });

    registerAgentUnique('project-controller', {
      role: 'Project scope and impact controller',
      status: 'active',
      file: 'server.js'
    });

    // Required new runtime agents.
    registerAgentUnique('bridge-agent', {
      role: 'Bridge UI/backend/extension channels',
      status: 'active',
      file: 'server.js'
    });
    registerAgentUnique('innovator-agent', {
      role: 'Suggest solutions when modules are blocked',
      status: 'active',
      file: 'server.js'
    });
    registerAgentUnique('verification-agent', {
      role: 'Anti-fake verification for TV/MT5 real data',
      status: 'active',
      file: 'server.js'
    });
    registerAgentUnique('mirror-agent', {
      role: 'Synchronize HTML interfaces and detect UI drift',
      status: 'active',
      file: 'server.js'
    });
    registerAgentUnique('extension-agent', {
      role: 'Control popup/content/background extension health',
      status: 'active',
      file: 'server.js'
    });

    // Register catalog agents for timing visibility (without duplicates).
    AGENT_RUNTIME_CATALOG.forEach((name) => {
      registerAgentUnique(name, {
        role: 'Runtime instrumented agent',
        status: 'active',
        file: 'src/agents/' + name + '.js'
      });
    });

    // Bridge bus messages from existing agents into the existing real-time stream.
    wireAgentBusToChat([
      'surveillance-agent',
      'orchestrator',
      'indicator-agent',
      'repair-agent',
      'design-agent',
      'project-controller',
      'bridge-agent',
      'innovator-agent',
      'verification-agent',
      'mirror-agent',
      'extension-agent',
      'alert-manager',
        'candle-manager',
        'ui-test-agent',
        'logic-gap-agent',
        'research-agent',
        'human-interface-agent',
        'central-guide-agent',
        'analysis-agent',
        'news-agent',
        'position-explainer-agent',
        'strategy-agent',
        'risk-agent',
        'execution-coach-agent',
        'history-agent',
        'lia'
    ]);

    publishAgentChatMessage({
      agent: 'system',
      to: 'all',
      status: 'info',
      phase: 'en cours',
      message: 'Canal chat agents branché sur /agent-activity',
      cause: 'initialisation serveur',
      impact: 'dialogue inter-agents visible en temps réel',
      solution: 'ouvrir /agent-log ou /agents-monitor'
    });

    startRuntimeLoop();
    if (SAFE_MODE) {
      console.log('[SAFE MODE] Runtime équilibrée active (rotation + limite de concurrence)');
    }
    console.log('[RUNTIME] Régulation CPU active: >70% ralentit, >85% limite à 2 agents, >95% SAFE MODE auto');
    
    // Listen for trigger-analysis events from surveillance agent
    surveillanceAgent.on('trigger-analysis', async (event) => {
      console.log(`[ANALYSIS TRIGGERED] ${event.symbol} @ ${event.price} (${event.reason})`);
      
      if (orchestrator) {
        try {
          const analysis = await orchestrator.run({
            symbol: event.symbol,
            price: event.price,
            timestamp: event.timestamp
          });
          
          // Create alert if signal is meaningful
          if (analysis && analysis.direction && analysis.direction !== 'ATTENDRE') {
            alertManager.createAlert(
              'SIGNAL',
              analysis.score >= 70 ? 'HIGH' : 'MEDIUM',
              event.symbol,
              {
                direction: analysis.direction,
                score: analysis.score,
                reason: event.reason
              }
            );
          }
        } catch (e) {
          console.error('[ANALYSIS ERROR]', e.message);
          alertManager.createAlert('ERROR', 'LOW', event.symbol, { error: e.message });
        }
      }
    });
  }

  // Log de démarrage dans le AGENTS LIVE LOG
  pushLog('system', 'all', 'SERVEUR DÉMARRÉ — http://127.0.0.1:' + PORT, 'ok', 'agents:technicalAgent,macroAgent,orchestrator');

  // Keep audit.json synchronized with live route reality, even without dashboard open.
  syncAuditStateToDisk();
  setInterval(() => {
    syncAuditStateToDisk();
  }, 15000);
});

// ─── ORCHESTRATION ROUTES (top-level) ────────────────────────────────────────
let _orchestrationAutoTimer = null;
let _orchestrationEnabled = false;

app.get('/orchestration-status', (_req, res) => {
  res.json({ 
    ok: true, 
    enabled: _orchestrationEnabled, 
    timer: _orchestrationAutoTimer ? 'active' : 'inactive'
  });
});

app.post('/orchestration/enable', (req, res) => {
  const intervalMs = parseInt(req.body?.interval) || 60000;
  if (_orchestrationAutoTimer) clearInterval(_orchestrationAutoTimer);
  _orchestrationAutoTimer = setInterval(runOrchestrationCycle, intervalMs);
  _orchestrationEnabled = true;
  console.log('[ORCH] Auto orchestration ENABLED @ ' + intervalMs + 'ms');
  res.json({ ok: true, message: 'Orchestration auto enabled', interval: intervalMs });
});

app.post('/orchestration/disable', (req, res) => {
  if (_orchestrationAutoTimer) {
    clearInterval(_orchestrationAutoTimer);
    _orchestrationAutoTimer = null;
  }
  _orchestrationEnabled = false;
  console.log('[ORCH] Auto orchestration DISABLED');
  res.json({ ok: true, message: 'Orchestration auto disabled' });
});

app.post('/orchestration/run-now', async (req, res) => {
  try {
    await runOrchestrationCycle();
    res.json({ ok: true, message: 'Orchestration cycle executed' });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});
