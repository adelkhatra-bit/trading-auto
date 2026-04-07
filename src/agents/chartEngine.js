/**
 * Agent: Chart Engine
 * 
 * Responsabilité:
 * - Gérer refresh temps réel du graphique
 * - Optimiser performance (pas de freeze)
 * - Gérer clôture de bougies
 * - Afficher chrono avant clôture
 */

const TIMEFRAMES = {
  'M1': 60,
  'M2': 120,
  'M3': 180,
  'M5': 300,
  'M10': 600,
  'M15': 900,
  'M30': 1800,
  'H1': 3600,
  'H4': 14400,
  'D1': 86400
};

const candles = new Map(); // Cache bougies
let refreshRate = 1000; // ms

/**
 * Initialiser engine
 */
function init(options = {}) {
  refreshRate = options.refreshRate || 1000;
  console.log(`[ChartEngine] Initialisé (refresh=${refreshRate}ms)`);
  
  return {
    status: 'initialized',
    refreshRate,
    timeframes: Object.keys(TIMEFRAMES)
  };
}

/**
 * Calculer temps avant clôture de bougie
 */
function getTimeUntilClose(timeframe) {
  const tf_seconds = TIMEFRAMES[timeframe];
  if (!tf_seconds) return null;

  const now = Math.floor(Date.now() / 1000);
  const secondsSinceOpen = now % tf_seconds;
  const secondsUntilClose = tf_seconds - secondsSinceOpen;

  return {
    timeframe,
    seconds: secondsUntilClose,
    percentage: ((secondsUntilClose / tf_seconds) * 100).toFixed(1),
    textFormat: formatTimeRemaining(secondsUntilClose)
  };
}

/**
 * Formater temps restant (ex: "2m 30s")
 */
function formatTimeRemaining(seconds) {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

/**
 * Vérifier si bougie est sur le point de fermer
 */
function isClosing(timeframe, threshold = 0.1) {
  const remaining = getTimeUntilClose(timeframe);
  if (!remaining) return false;

  const threshold_seconds = TIMEFRAMES[timeframe] * threshold;
  return remaining.seconds < threshold_seconds;
}

/**
 * Obtenir bougies du cache
 */
function getCandles(symbol, timeframe, count = 100) {
  const key = `${symbol}_${timeframe}`;
  return candles.get(key) || [];
}

/**
 * Ajouter/mettre à jour bougie
 */
function updateCandle(symbol, timeframe, candle) {
  const key = `${symbol}_${timeframe}`;
  let candleList = candles.get(key) || [];

  // Vérifier si dernière bougie existe
  const now = Math.floor(Date.now() / 1000);
  const tf_seconds = TIMEFRAMES[timeframe];
  const currentCandleTime = now - (now % tf_seconds);

  // If new candle started
  if (!candleList.length || candleList[candleList.length - 1].time < currentCandleTime) {
    candleList.push({
      time: currentCandleTime,
      ...candle,
      isComplete: false
    });
  } else {
    // Update last candle
    const lastIdx = candleList.length - 1;
    candleList[lastIdx] = {
      ...candleList[lastIdx],
      ...candle,
      time: currentCandleTime,
      isComplete: false
    };
  }

  // Limiter à 500 bougies en cache
  if (candleList.length > 500) {
    candleList = candleList.slice(-500);
  }

  candles.set(key, candleList);
  return candleList[candleList.length - 1];
}

/**
 * Marquer une bougie comme complète
 */
function completeCandle(symbol, timeframe) {
  const key = `${symbol}_${timeframe}`;
  const candleList = candles.get(key);
  
  if (candleList && candleList.length > 0) {
    candleList[candleList.length - 1].isComplete = true;
    return true;
  }
  
  return false;
}

/**
 * Obtenir données pour graphique TradingView
 */
function getChartDataForTV(symbol, timeframe, count = 100) {
  const candleList = getCandles(symbol, timeframe, count);
  
  return candleList.map(candle => ({
    time: candle.time, // Unix timestamp (seconds)
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close
  }));
}

/**
 * Obtenir état temps réel
 */
function getRealTimeStatus(symbol, timeframe) {
  const timeUntilClose = getTimeUntilClose(timeframe);
  const candleList = getCandles(symbol, timeframe, 1);
  const currentCandle = candleList.length > 0 ? candleList[candleList.length - 1] : null;

  return {
    symbol,
    timeframe,
    timeUntilClose,
    isClosing: isClosing(timeframe, 0.15),
    currentCandle: currentCandle ? {
      open: currentCandle.open,
      high: currentCandle.high,
      low: currentCandle.low,
      close: currentCandle.close,
      isComplete: currentCandle.isComplete || false
    } : null
  };
}

/**
 * Récupérer un snapshot unique de prix (PAS une boucle infinie)
 */
function priceSnapshot(symbol, interval = refreshRate) {
  const tf_seconds = TIMEFRAMES['M1'] || 60;
  const now = Math.floor(Date.now() / 1000);
  
  // CORRIGÉ: while(true) était UNE BOUCLE INFINIE
  // RAISON: Cause 100% CPU, freeze du navigateur
  // NEW: Retourner UN seul snapshot à la demande
  
  const price = 1.0856 + (Math.random() - 0.5) * 0.001;
  
  return {
    symbol,
    price,
    bid: price - 0.0001,
    ask: price + 0.0001,
    timestamp: Date.now(),
    timeRemaining: formatTimeRemaining((tf_seconds) - (now % tf_seconds)),
    note: 'POLLING DISABLED - Use HTTP requests instead'
  };
}

/**
 * Obtenir statistiques du graphique
 */
function getChartStats(symbol, timeframe) {
  const candleList = getCandles(symbol, timeframe);
  
  if (candleList.length < 2) {
    return {
      candles: 0,
      message: 'Pas assez de données'
    };
  }

  const closes = candleList.map(c => c.close);
  const highs = candleList.map(c => c.high);
  const lows = candleList.map(c => c.low);

  const highest = Math.max(...highs);
  const lowest = Math.min(...lows);
  const avg = closes.reduce((a, b) => a + b, 0) / closes.length;
  const range = highest - lowest;

  return {
    candles: candleList.length,
    highest,
    lowest,
    range,
    average: avg.toFixed(5),
    volatility: ((range / avg) * 100).toFixed(2) + '%'
  };
}

/**
 * Performance: activer/désactiver selon charge CPU
 */
function optimizePerformance(cpuLoad) {
  if (cpuLoad > 80) {
    refreshRate = 2000; // Réduire fréquence
    console.warn('[ChartEngine] CPU élevé, refresh réduit à 2s');
  } else if (cpuLoad > 50) {
    refreshRate = 1500;
  } else {
    refreshRate = 1000; // Normal
  }

  return { refreshRate, optimized: true };
}

module.exports = {
  init,
  getTimeUntilClose,
  isClosing,
  formatTimeRemaining,
  getCandles,
  updateCandle,
  completeCandle,
  getChartDataForTV,
  getRealTimeStatus,
  getChartStats,
  optimizePerformance,
  TIMEFRAMES
};
