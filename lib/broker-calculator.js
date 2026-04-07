// broker-calculator.js - Multi-Plateforme TP/SL Calculator
// Recalcule les niveaux TP/SL selon la plateforme (Topstep, Google, TradingView, etc)

'use strict';

// Configuration par plateforme
const BROKER_CONFIG = {
  tradingview: {
    name: 'TradingView',
    digits: 5,
    pip: 0.1,
    slMultiplier: 1.0,     // SL standard
    tpMultiplier: 0.8,     // TP ratio
    minLevel: 1,
    maxLevel: 100000,
    supportsMicro: true,
    supportsMini: true,
  },
  
  topstep: {
    name: 'TopStep (Futures)',
    digits: 2,
    pip: 0.01,
    slMultiplier: 0.95,    // SL serré (TopStep pénalise les larges SL)
    tpMultiplier: 1.0,     // TP plus agressif
    minLevel: 100,
    maxLevel: 10000,
    supportsMicro: false,
    supportsMini: true,
    contracts: ['MES', 'MNQ', 'MYM'], // Micro ES, Micro NQ, Micro YM
  },
  
  google: {
    name: 'Google Finance',
    digits: 2,
    pip: 0.01,
    slMultiplier: 1.05,    // SL plus large (moins de liquidity)
    tpMultiplier: 0.85,    // TP modéré
    minLevel: 10,
    maxLevel: 5000,
    supportsMicro: true,
    supportsMini: true,
  },
  
  xm: {
    name: 'XM Trading',
    digits: 4,
    pip: 0.0001,
    slMultiplier: 1.1,     // SL très large (forex)
    tpMultiplier: 0.7,     // TP conservateur
    minLevel: 0.01,
    maxLevel: 1000,
    supportsMicro: true,
    supportsMini: true,
  },

  mt5: {
    name: 'MetaTrader 5',
    digits: 5,
    pip: 0.1,
    slMultiplier: 1.0,
    tpMultiplier: 0.8,
    minLevel: 1,
    maxLevel: 100000,
    supportsMicro: true,
    supportsMini: true,
  }
};

// Mapping symboles par plateforme
const SYMBOL_MAPPING = {
  // XAUUSD (Gold)
  XAUUSD: {
    tradingview: 'XAUUSD',
    topstep: 'GC=F',         // Gold Futures (CBOT)
    mt5: 'XAUUSD',
    google: 'XAUUSD',
    xm: 'XAUUSD',
  },
  
  // EURUSD
  EURUSD: {
    tradingview: 'EURUSD',
    topstep: '6EU=F',        // Euro Futures
    mt5: 'EURUSD',
    google: 'EURUSD',
    xm: 'EURUSD',
  },
  
  // GBPUSD
  GBPUSD: {
    tradingview: 'GBPUSD',
    topstep: '6GB=F',        // GBP Futures
    mt5: 'GBPUSD',
    google: 'GBPUSD',
    xm: 'GBPUSD',
  },
  
  // BTCUSD
  BTCUSD: {
    tradingview: 'BTCUSD',
    topstep: 'XBTU4',        // Bitcoin Futures (CME)
    mt5: 'BTCUSD',
    google: 'BTCUSD',
    xm: 'BTCUSD',
  },
};

/**
 * Convertir symbole pour une plateforme
 * @param {string} symbol - Symbole d'entrée (ex: XAUUSD)
 * @param {string} broker - Plateforme cible (tradingview, topstep, etc)
 * @returns {string} Symbole de la plateforme ou symbole d'entrée
 */
function convertSymbol(symbol, broker = 'tradingview') {
  const sym = symbol.toUpperCase();
  if (SYMBOL_MAPPING[sym] && SYMBOL_MAPPING[sym][broker]) {
    return SYMBOL_MAPPING[sym][broker];
  }
  return symbol;
}

/**
 * Calculer TP et SL adaptés à la plateforme
 * @param {number} price - Prix d'entrée
 * @param {string} direction - 'LONG' ou 'SHORT'
 * @param {string} broker - Plateforme cible
 * @param {number} atr - ATR (optional)
 * @returns {object} {sl, tp, slDist, tpDist, slPct, tpPct, slPips, tpPips}
 */
function calculateLevels(price, direction, broker = 'tradingview', atr = null) {
  const config = BROKER_CONFIG[broker] || BROKER_CONFIG.tradingview;
  const digits = config.digits;
  const pip = config.pip;
  
  let slDist, tpDist;
  
  // Utiliser ATR si disponible, sinon use profile percentages
  if (atr && atr > 0) {
    slDist = atr * config.slMultiplier;
    tpDist = atr * config.tpMultiplier;
  } else {
    // Default percentages si pas ATR
    const slPct = digits === 2 ? 0.005 : (digits === 4 ? 0.0025 : 0.001);  // 0.5% forex, 0.25% stocks
    const tpPct = slPct * 1.5 * config.tpMultiplier;
    slDist = price * slPct;
    tpDist = price * tpPct;
  }
  
  // Vérifier limites plateforme
  if (slDist < config.minLevel) slDist = config.minLevel;
  if (slDist > config.maxLevel) slDist = config.maxLevel;
  if (tpDist < config.minLevel) tpDist = config.minLevel;
  if (tpDist > config.maxLevel) tpDist = config.maxLevel;
  
  // Calculer niveaux finaux
  const sl = direction === 'LONG' ? price - slDist : price + slDist;
  const tp = direction === 'LONG' ? price + tpDist : price - tpDist;
  
  // Risk reward ratio
  const rr = (tpDist / slDist).toFixed(2);
  
  // Format pour display
  const slFormatted = sl.toFixed(digits);
  const tpFormatted = tp.toFixed(digits);
  const slPct = ((slDist / price) * 100).toFixed(2);
  const tpPct = ((tpDist / price) * 100).toFixed(2);
  const slPips = (slDist / pip).toFixed(1);
  const tpPips = (tpDist / pip).toFixed(1);
  
  return {
    sl: parseFloat(slFormatted),
    tp: parseFloat(tpFormatted),
    slDist: slDist.toFixed(digits),
    tpDist: tpDist.toFixed(digits),
    slPct: slPct + '%',
    tpPct: tpPct + '%',
    slPips: slPips,
    tpPips: tpPips,
    rrRatio: rr,
    broker: broker,
    brokerName: config.name,
  };
}

/**
 * Recalculer trade pour plateforme (top-level function)
 * @param {object} trade - Original trade object
 * @param {string} sourceBroker - Plateforme d'origine
 * @param {string} targetBroker - Plateforme cible
 * @returns {object} Trade adapté
 */
function recalculateForBroker(trade, targetBroker = 'tradingview') {
  if (!trade || !trade.entry) return trade;
  
  const price = parseFloat(trade.entry);
  const direction = trade.direction || 'LONG';
  const atr = trade.atr || null;
  
  // Recalculer les niveaux
  const newLevels = calculateLevels(price, direction, targetBroker, atr);
  
  // Convertir symbole si nécessaire
  const newSymbol = convertSymbol(trade.symbol, targetBroker);
  
  // Retourner trade augmenté
  return {
    ...trade,
    symbol: newSymbol,
    entry: newLevels.sl > 0 ? trade.entry : trade.entry,  // Keep original entry
    sl: newLevels.sl,
    tp: newLevels.tp,
    slDist: newLevels.slDist,
    tpDist: newLevels.tpDist,
    slPct: newLevels.slPct,
    tpPct: newLevels.tpPct,
    slPips: newLevels.slPips,
    tpPips: newLevels.tpPips,
    rrRatio: newLevels.rrRatio,
    broker: targetBroker,
    brokerName: newLevels.brokerName,
    recalculatedAt: Date.now(),
    recalcReason: `Converted from original levels for ${newLevels.brokerName}`,
  };
}

/**
 * Batch recalculate pour multiple brokers
 * @param {object} trade - Trade object
 * @param {array} brokers - Liste de brokers cibles
 * @returns {object} {original, topstep, google, xm, ...}
 */
function recalculateForAllBrokers(trade) {
  const result = {
    original: trade,
  };
  
  for (const broker in BROKER_CONFIG) {
    if (broker !== 'tradingview') {  // Skip original
      result[broker] = recalculateForBroker(trade, broker);
    }
  }
  
  return result;
}

// Export
module.exports = {
  BROKER_CONFIG,
  SYMBOL_MAPPING,
  convertSymbol,
  calculateLevels,
  recalculateForBroker,
  recalculateForAllBrokers,
  getBrokerList: () => Object.keys(BROKER_CONFIG),
  getBrokerConfig: (broker) => BROKER_CONFIG[broker] || BROKER_CONFIG.tradingview,
};
