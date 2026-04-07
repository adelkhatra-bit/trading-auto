/**
 * Agent: Sync Manager
 * 
 * Responsabilité:
 * - Garantir cohérence TOTALE entre:
 *   → Prix live
 *   → Graphique (bougies)
 *   → Trade proposé
 *   → Analyse
 * 
 * Détecte et bloque incohérences
 */

const dataSourceManager = require('./dataSourceManager');

// Cache de synchronisation
const syncState = {
  lastPrice: null,
  lastChart: null,
  lastTrade: null,
  lastAnalysis: null,
  syncedAt: null,
  inconsistencies: []
};

/**
 * Synchroniser TOUS les flux
 */
async function syncAll(symbol, timeframe) {
  const result = {
    symbol,
    timeframe,
    synchronized: true,
    components: {}
  };

  try {
    // 1. Récupérer prix live
    const priceData = await dataSourceManager.getPrice(symbol, 'auto');
    if (!priceData.valid) {
      result.synchronized = false;
      result.error = `Prix invalide: ${priceData.error}`;
      return result;
    }
    result.components.price = priceData;

    // 2. Récupérer données chart (simulées, en prod: API TradingView)
    const chartData = getChartData(symbol, timeframe);
    if (!chartData.valid) {
      result.synchronized = false;
      result.error = `Chart invalide: ${chartData.error}`;
      return result;
    }
    result.components.chart = chartData;

    // 3. Vérifier cohérence prix ↔ chart
    const priceChartCoherence = validatePriceChartCoherence(priceData, chartData);
    result.components.priceChartCheck = priceChartCoherence;
    
    if (!priceChartCoherence.coherent) {
      result.synchronized = false;
      result.error = `Incohérence prix/chart: ${priceChartCoherence.reason}`;
      recordInconsistency('price_chart_mismatch', priceChartCoherence.reason);
      return result;
    }

    // 4. Valider qualité source
    const sourceQuality = validateSourceQuality(priceData);
    result.components.sourceQuality = sourceQuality;

    if (sourceQuality.confidence < 0.8) {
      result.synchronized = false;
      result.warning = `Source faible confiance: ${sourceQuality.reason}`;
    }

    syncState.lastPrice = priceData;
    syncState.lastChart = chartData;
    syncState.syncedAt = Date.now();

    return result;
  } catch (err) {
    result.synchronized = false;
    result.error = `Sync error: ${err.message}`;
    console.error('[SyncManager]', err);
    return result;
  }
}

/**
 * Vérifier cohérence prix ↔ chart
 */
function validatePriceChartCoherence(priceData, chartData) {
  if (!priceData || !chartData) {
    return {
      coherent: false,
      reason: 'Données manquantes'
    };
  }

  const price = priceData.price;
  const chartHigh = chartData.high;
  const chartLow = chartData.low;
  const chartClose = chartData.close;

  // Le prix live doit être proche de la dernière bougie
  const tolerance = chartClose * 0.001; // 0.1% de tolérance
  
  const priceInRange = price >= (chartLow - tolerance) && price <= (chartHigh + tolerance);
  
  if (!priceInRange) {
    return {
      coherent: false,
      reason: `Prix (${price}) hors rangé chart (${chartLow}-${chartHigh})`
    };
  }

  // Score de cohérence
  const deviationFromClose = Math.abs(price - chartClose) / chartClose;
  const confidence = Math.max(0, 1 - deviationFromClose * 100); // 0-1

  return {
    coherent: true,
    confidence: Math.round(confidence * 100),
    priceVsClose: `+${((price - chartClose) / chartClose * 10000).toFixed(1)} pips`
  };
}

/**
 * Valider qualité de la source
 */
function validateSourceQuality(priceData) {
  if (!priceData) {
    return {
      confidence: 0,
      reason: 'Prix invalide'
    };
  }

  const isMT5 = priceData.source === dataSourceManager.SOURCES.MT5;
  const isLive = priceData.freshness === 'live';
  const age = Date.now() - priceData.timestamp;
  const maxAge = 1000; // 1s max

  let confidence = 1.0;
  let issues = [];

  if (!isMT5) {
    confidence *= 0.8;
    issues.push('Source non-MT5');
  }

  if (!isLive) {
    confidence *= 0.9;
    issues.push('Données décalées');
  }

  if (age > maxAge) {
    confidence *= (Math.max(0.5, 1 - age / (maxAge * 2)));
    issues.push(`Données anciennes (${age}ms)`);
  }

  return {
    confidence,
    source: priceData.source,
    freshness: priceData.freshness,
    age: age,
    issues,
    reason: issues.join(', ') || 'Qualité excellente'
  };
}

/**
 * Récupérer données chart
 * (En production: connecter API TradingView)
 */
function getChartData(symbol, timeframe) {
  try {
    // Simulation de données OHLC
    const base = 1.0856; // Example for EURUSD
    const volatility = 0.001;
    
    const open = base + (Math.random() - 0.5) * volatility;
    const close = open + (Math.random() - 0.5) * volatility;
    const high = Math.max(open, close) + Math.abs(Math.random() * volatility);
    const low = Math.min(open, close) - Math.abs(Math.random() * volatility);

    return {
      valid: true,
      symbol,
      timeframe,
      open: parseFloat(open.toFixed(5)),
      high: parseFloat(high.toFixed(5)),
      low: parseFloat(low.toFixed(5)),
      close: parseFloat(close.toFixed(5)),
      volume: Math.floor(Math.random() * 1000000),
      timestamp: Date.now()
    };
  } catch (err) {
    return {
      valid: false,
      error: err.message
    };
  }
}

/**
 * Valider qu'un trade est cohérent avec prix/chart
 */
function validateTradeCoherence(trade, priceData, chartData) {
  if (!trade || !priceData || !chartData) {
    return {
      coherent: false,
      reason: 'Données manquantes'
    };
  }

  const entryPrice = parseFloat(trade.entry);
  const currentPrice = priceData.price;
  const sl = parseFloat(trade.sl);
  const tp = parseFloat(trade.tp);

  // Vérifier que l'entrée est réaliste
  const tolerance = currentPrice * 0.005; // 0.5%
  const entryRealistic = Math.abs(entryPrice - currentPrice) < tolerance;

  if (!entryRealistic) {
    return {
      coherent: false,
      reason: `Entrée (${entryPrice}) trop loin du prix (${currentPrice})`,
      distancePercent: Math.abs((entryPrice - currentPrice) / currentPrice * 100).toFixed(2)
    };
  }

  // Vérifier que SL/TP sont valides
  if (trade.direction === 'LONG') {
    if (sl >= entryPrice || tp <= entryPrice) {
      return {
        coherent: false,
        reason: 'SL/TP invalides pour LONG'
      };
    }
  } else {
    if (sl <= entryPrice || tp >= entryPrice) {
      return {
        coherent: false,
        reason: 'SL/TP invalides pour SHORT'
      };
    }
  }

  return {
    coherent: true,
    entryDistance: `${Math.abs((entryPrice - currentPrice) * 10000).toFixed(1)} pips`,
    riskReward: (Math.abs(entryPrice - tp) / Math.abs(entryPrice - sl)).toFixed(2)
  };
}

/**
 * Enregistrer incohérence
 */
function recordInconsistency(type, reason) {
  syncState.inconsistencies.push({
    type,
    reason,
    timestamp: Date.now()
  });

  if (syncState.inconsistencies.length > 100) {
    syncState.inconsistencies.shift(); // Limiter à 100 entrées
  }
}

/**
 * Status du manager
 */
function getStatus() {
  return {
    synchronized: syncState.syncedAt && (Date.now() - syncState.syncedAt) < 5000,
    lastSync: syncState.syncedAt ? new Date(syncState.syncedAt).toISOString() : null,
    inconsistencies: syncState.inconsistencies.length,
    recentInconsistencies: syncState.inconsistencies.slice(-5)
  };
}

module.exports = {
  syncAll,
  validatePriceChartCoherence,
  validateTradeCoherence,
  validateSourceQuality,
  getStatus,
  getChartData
};
