// technicalAgent.js — Analyse technique RÉELLE
// Sources: MT5 (RSI/EMA/ATR live) → Yahoo klines (calcul indicateurs) → prix seul (neutre)
// AUCUN Math.random() — toutes les valeurs sont calculées depuis des données réelles

'use strict';

// ─── Calculs d'indicateurs depuis un tableau de closes ───────────────────────

function calcEMA(closes, period) {
  if (!closes || closes.length < period) return null;
  const k = 2 / (period + 1);
  let ema = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < closes.length; i++) {
    ema = closes[i] * k + ema * (1 - k);
  }
  return ema;
}

function calcRSI(closes, period) {
  if (!period) period = 14;
  if (!closes || closes.length < period + 1) return null;
  let gains = 0, losses = 0;
  for (let i = closes.length - period; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) gains += diff; else losses -= diff;
  }
  const avgGain = gains / period;
  const avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

function calcATR(candles, period) {
  if (!period) period = 14;
  if (!candles || candles.length < period + 1) return null;
  const trs = candles.slice(-(period + 1)).map(function(c, i, arr) {
    if (i === 0) return c.high - c.low;
    const prevClose = arr[i - 1].close;
    return Math.max(c.high - c.low, Math.abs(c.high - prevClose), Math.abs(c.low - prevClose));
  });
  return trs.slice(1).reduce(function(a, b) { return a + b; }, 0) / period;
}

// ─── Score depuis indicateurs calculés — AUCUN Math.random() ─────────────────

function scoreFromIndicators(opts) {
  const rsi = opts.rsi, ema20 = opts.ema20, ema50 = opts.ema50, price = opts.price, atr = opts.atr;
  let score = 50; // neutre de base
  const signals = [];

  if (rsi !== null && rsi !== undefined) {
    if (rsi < 30)      { score += 15; signals.push('RSI oversold (<30)'); }
    else if (rsi > 70) { score -= 15; signals.push('RSI overbought (>70)'); }
    else if (rsi < 45) { score -= 5;  signals.push('RSI bearish zone'); }
    else if (rsi > 55) { score += 5;  signals.push('RSI bullish zone'); }
  }

  if (ema20 && ema50 && price) {
    if (price > ema20 && ema20 > ema50) { score += 12; signals.push('Price>EMA20>EMA50 (uptrend)'); }
    if (price < ema20 && ema20 < ema50) { score -= 12; signals.push('Price<EMA20<EMA50 (downtrend)'); }
    if (price > ema20 && ema20 < ema50) { score += 5;  signals.push('EMA20 crossing above EMA50'); }
    if (price < ema20 && ema20 > ema50) { score -= 5;  signals.push('EMA20 crossing below EMA50'); }
  }

  const volatilityNote = atr ? ('ATR=' + atr.toFixed(4)) : 'ATR N/A';
  return { score: Math.min(100, Math.max(0, Math.round(score))), signals: signals, volatilityNote: volatilityNote };
}

// ─── Analyse depuis données MT5 live ─────────────────────────────────────────

function analyzeFromMT5(symbol, mt5data) {
  const price = parseFloat(mt5data.price);
  const rsi   = mt5data.rsi   ? parseFloat(mt5data.rsi)   : null;
  const ema20 = mt5data.ema20 ? parseFloat(mt5data.ema20) : null;
  const ema50 = mt5data.ema50 ? parseFloat(mt5data.ema50) : null;
  const atr   = mt5data.atr   ? parseFloat(mt5data.atr)   : null;

  // NOUVEAU: Calculer confirmation
  const confirmation = (rsi && rsi > 55) ? 'BULLISH' : (rsi && rsi < 45) ? 'BEARISH' : 'NEUTRAL';
  const structure = mt5data.structure || 'UNDEFINED';

  // MT5 fournit score + direction → on lui fait confiance directement
  if (mt5data.score && mt5data.direction) {
    const score = Math.round(parseFloat(mt5data.score) * 100);
    const signal = score >= 65 ? 'LONG' : score <= 35 ? 'SHORT' : 'HOLD';
    const why = generateWhyFields({ rsi, ema20, ema50, price, structure, signal });
    
    return {
      name: 'Technical Agent (MT5-live)',
      symbol: symbol,
      price: price.toFixed(4),
      source: 'mt5-live',
      rsi: rsi !== null ? rsi.toFixed(2) : '—',
      ema20: ema20 !== null ? ema20.toFixed(4) : '—',
      ema50: ema50 !== null ? ema50.toFixed(4) : '—',
      atr: atr !== null ? atr.toFixed(4) : '—',
      score: score,
      signal: signal,
      analysis: 'MT5 live: RSI=' + (rsi !== null ? rsi.toFixed(1) : '—') + ' direction=' + mt5data.direction,
      // NOUVEAU
      structure: structure,
      confirmation: confirmation,
      why_entry: why.why_entry,
      why_sl: why.why_sl,
      why_tp: why.why_tp
    };
  }

  // MT5 fournit indicateurs mais pas de score → on calcule
  const result = scoreFromIndicators({ rsi: rsi, ema20: ema20, ema50: ema50, price: price, atr: atr });
  const signal = result.score >= 65 ? 'LONG' : result.score <= 35 ? 'SHORT' : 'HOLD';
  const why = generateWhyFields({ rsi, ema20, ema50, price, structure, signal });
  
  return {
    name: 'Technical Agent (MT5-indicators)',
    symbol: symbol,
    price: price.toFixed(4),
    source: 'mt5-indicators',
    rsi: rsi !== null ? rsi.toFixed(2) : '—',
    ema20: ema20 !== null ? ema20.toFixed(4) : '—',
    ema50: ema50 !== null ? ema50.toFixed(4) : '—',
    volatility: result.volatilityNote,
    score: result.score,
    signal: signal,
    analysis: result.signals.join(' | ') || 'Neutre',
    // NOUVEAU
    structure: structure,
    confirmation: confirmation,
    why_entry: why.why_entry,
    why_sl: why.why_sl,
    why_tp: why.why_tp
  };
}

// ─── Analyse depuis klines Yahoo ─────────────────────────────────────────────

function analyzeFromKlines(symbol, candles, currentPrice) {
  if (!candles || candles.length < 20) {
    return {
      name: 'Technical Agent',
      symbol: symbol,
      price: currentPrice ? parseFloat(currentPrice).toFixed(4) : '—',
      source: 'price-only',
      score: 50,
      signal: 'HOLD',
      analysis: 'Données insuffisantes — connectez MT5'
    };
  }

  const closes = candles.map(function(c) { return c.close; }).filter(Boolean);
  const candlesOk = candles.filter(function(c) { return c.high && c.low && c.close; });

  const rsi   = calcRSI(closes, 14);
  const ema20 = calcEMA(closes, 20);
  const ema50 = calcEMA(closes, Math.min(50, closes.length - 1));
  const atr   = calcATR(candlesOk, 14);
  const price = currentPrice || closes[closes.length - 1];
  
  // NOUVEAU: Calculer market structure + confirmation
  const structure = calculateMarketStructure(candlesOk);
  const confirmation = (rsi && rsi > 55) ? 'BULLISH' : (rsi && rsi < 45) ? 'BEARISH' : 'NEUTRAL';

  const result = scoreFromIndicators({ rsi: rsi, ema20: ema20, ema50: ema50, price: price, atr: atr });
  const signal = result.score >= 65 ? 'LONG' : result.score <= 35 ? 'SHORT' : 'HOLD';
  
  // NOUVEAU: Générer les champs why
  const why = generateWhyFields({ rsi, ema20, ema50, price, structure, signal });

  return {
    name: 'Technical Agent (Klines)',
    symbol: symbol,
    price: parseFloat(price).toFixed(4),
    source: 'klines-calculated',
    rsi: rsi !== null ? rsi.toFixed(2) : '—',
    ema20: ema20 !== null ? ema20.toFixed(4) : '—',
    ema50: ema50 !== null ? ema50.toFixed(4) : '—',
    volatility: result.volatilityNote,
    score: result.score,
    signal: signal,
    analysis: result.signals.join(' | ') || 'Neutre — pas de signal clair',
    // NOUVEAU: Champs enrichis
    structure: structure,
    confirmation: confirmation,
    why_entry: why.why_entry,
    why_sl: why.why_sl,
    why_tp: why.why_tp
  };
}

// ─── Point d'entrée principal ────────────────────────────────────────────────

async function analyzeTechnical(symbol, priceOrData) {
  if (!symbol) return { name: 'Technical Agent', score: 0, analysis: 'Symbol manquant' };

  // Cas 1: objet MT5 complet avec price + indicateurs
  if (priceOrData && typeof priceOrData === 'object' && priceOrData.price) {
    return analyzeFromMT5(symbol, priceOrData);
  }

  // Cas 2: prix numérique → bridge TV uniquement (Yahoo supprimé)
  const price = parseFloat(priceOrData);
  if (!price || isNaN(price)) {
    return { name: 'Technical Agent', symbol: symbol, score: 0, signal: 'HOLD', analysis: 'Prix manquant' };
  }

  // Yahoo Finance supprimé — klines via bridge TV uniquement (/klines endpoint)
  return {
    name: 'Technical Agent',
    symbol: symbol,
    price: price.toFixed(4),
    source: 'bridge-tv',
    score: 50,
    signal: 'HOLD',
    analysis: 'Klines via bridge TV — score neutre en attente flux live'
  };
}

async function analyzeMultiPair(pairs, priceMap) {
  const analyses = await Promise.all(
    pairs.map(function(pair) { return analyzeTechnical(pair, priceMap ? priceMap[pair] : null); })
  );
  return analyses;
}

// ─── Détection de structure du marché (HH/HL=BULLISH, LH/LL=BEARISH) ─────────

function calculateMarketStructure(candles) {
  if (!candles || candles.length < 3) return 'UNDEFINED';
  
  const recent = candles.slice(-3);
  const highs = recent.map(c => c.high);
  const lows = recent.map(c => c.low);
  
  if (highs[2] > highs[1] && highs[1] > highs[0]) return 'BULLISH';   // HH
  if (lows[2] < lows[1] && lows[1] < lows[0]) return 'BEARISH';       // LL
  if (highs[2] < highs[1] && highs[1] > highs[0]) return 'BEARISH';   // HL
  if (lows[2] > lows[1] && lows[1] < lows[0]) return 'BULLISH';       // LH
  
  return 'UNDEFINED';
}

// ─── Génération des champs why_entry, why_sl, why_tp ──────────────────────

function generateWhyFields(opts) {
  const rsi = opts.rsi, ema20 = opts.ema20, ema50 = opts.ema50, price = opts.price, structure = opts.structure, signal = opts.signal;
  
  let why_entry = signal === 'LONG' ? 'Structure haussière + RSI bullish' : signal === 'SHORT' ? 'Structure baissière + RSI bearish' : 'Attendre clarification';
  let why_sl = signal === 'LONG' ? 'SL sous plus bas récent' : 'SL au-dessus plus haut récent';
  let why_tp = signal === 'LONG' ? 'TP au SL×2 (R:R 1:2)' : 'TP au SL×2 (R:R 1:2)';
  
  return { why_entry, why_sl, why_tp };
}

module.exports = { analyzeTechnical, analyzeMultiPair, analyzeFromMT5, analyzeFromKlines, calcRSI, calcEMA, calcATR, calculateMarketStructure, generateWhyFields };
