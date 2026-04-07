// In-memory market data store — single source of truth for MT5 data

const EventEmitter = require('events');

class MarketStore extends EventEmitter {
  constructor() {
    super();
    this.lastMT5Payload  = null;  // raw last payload from MT5
    this.bySymbol        = {};    // { XAUUSD: { latestPayload, latestAnalysis, updatedAt } }
    this.sseClients      = [];    // SSE response objects
    this.systemStatus    = { source: 'offline', lastUpdate: null, fluxStatus: 'OFFLINE' };
    this.analysisCache   = {};    // { XAUUSD: analysisResult }
  }

  // ⚠️ RÈGLE ABSOLUE : MT5 = exécution uniquement
  // Cette méthode N'ÉCRIT PAS dans price/symbol/timeframe
  // Ces champs sont réservés à TradingView (source unique d'affichage)
  updateFromMT5(payload, normalizedSymbol) {
    const sym = normalizedSymbol || payload.symbol;
    const enrichedPayload = { ...payload, receivedAt: Date.now() };

    if (!this.bySymbol[sym]) this.bySymbol[sym] = {};

    // MT5 écrit UNIQUEMENT dans mt5Execution — jamais dans les champs UI
    this.bySymbol[sym].mt5Execution = {
      lastTick: enrichedPayload,
      latestPayload: enrichedPayload,  // alias maintenu pour compatibilité server.js (exécution)
      updatedAt: new Date().toISOString(),
      bridgeStatus: 'connected'
    };
    // Alias de compatibilité — server.js lit encore latestPayload à la racine
    this.bySymbol[sym].latestPayload = this.bySymbol[sym].mt5Execution.latestPayload;

    // lastMT5Payload maintenu pour compatibilité (server.js lignes 4868, 4886)
    this.lastMT5Payload = enrichedPayload;

    // Mise à jour du statut bridge global
    this.systemStatus.mt5Connected = true;
    this.systemStatus.mt5LastUpdate = new Date().toISOString();

    // PAS de mise à jour de price, symbol, timeframe ici
    // Ces champs sont réservés à updateFromTV() / TradingView
    this.emit('mt5-update', sym, payload);
  }

  updateAnalysis(symbol, analysis) {
    this.analysisCache[symbol] = { ...analysis, computedAt: Date.now() };
    if (this.bySymbol[symbol]) this.bySymbol[symbol].latestAnalysis = analysis;
    this.broadcast({ type: 'analysis', symbol, analysis });
  }

  // SSE management
  addSSEClient(res) {
    this.sseClients.push(res);
    // Immediately send current state
    const state = this.getState();
    try { res.write(`data: ${JSON.stringify({ type: 'state', ...state })}\n\n`); } catch {}
    res.once('close', () => { this.sseClients = this.sseClients.filter(c => c !== res); });
  }

  broadcast(data) {
    const msg = `data: ${JSON.stringify(data)}\n\n`;
    this.sseClients = this.sseClients.filter(res => {
      try { res.write(msg); return true; } catch { return false; }
    });
  }

  getState() {
    return {
      systemStatus: this.systemStatus,
      lastPayload:  this.lastMT5Payload,
      symbols:      Object.keys(this.bySymbol),
      analysisCache: this.analysisCache,
    };
  }

  getLatestForSymbol(symbol) {
    return this.bySymbol[symbol] || null;
  }
}

module.exports = new MarketStore(); // singleton
