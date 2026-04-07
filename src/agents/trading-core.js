// Agent: trading-core — technical structure analysis from MT5 data

const { calcLevels } = require('../../lib/symbol-normalizer');

function analyzeRSI(rsi) {
  if (!rsi) return { signal: 'NEUTRAL', note: 'RSI indisponible' };
  if (rsi >= 70) return { signal: 'OVERBOUGHT', note: `RSI=${rsi.toFixed(1)} — zone de surachat, prudence LONG` };
  if (rsi <= 30) return { signal: 'OVERSOLD',   note: `RSI=${rsi.toFixed(1)} — zone de survente, prudence SHORT` };
  if (rsi >= 50) return { signal: 'BULLISH',    note: `RSI=${rsi.toFixed(1)} — momentum haussier` };
  return                 { signal: 'BEARISH',    note: `RSI=${rsi.toFixed(1)} — momentum baissier` };
}

function analyzeEMA(price, ema20, ema50, ema200) {
  const signals = [];
  if (ema20 && ema50) {
    if (ema20 > ema50) signals.push('EMA20 > EMA50 — tendance haussière court terme');
    else                signals.push('EMA20 < EMA50 — tendance baissière court terme');
  }
  if (ema200 && price) {
    if (price > ema200) signals.push(`Prix > EMA200 (${ema200?.toFixed(2)}) — structure long terme haussière`);
    else                 signals.push(`Prix < EMA200 (${ema200?.toFixed(2)}) — structure long terme baissière`);
  }
  const bullish = signals.filter(s => s.includes('haussl')).length;
  const bearish = signals.filter(s => s.includes('baussl')).length || signals.filter(s => s.includes('baissi')).length;
  return { bullish, bearish, signals };
}

function detectStructure(ohlcBars) {
  // Simple BOS / CHoCH detection from OHLC array (newest last)
  if (!ohlcBars || ohlcBars.length < 4) return { bos: null, choch: null, note: 'Données insuffisantes' };
  const highs  = ohlcBars.map(b => b.high);
  const lows   = ohlcBars.map(b => b.low);
  const lastH  = highs[highs.length - 1];
  const prevH  = highs[highs.length - 3];
  const lastL  = lows[lows.length - 1];
  const prevL  = lows[lows.length - 3];
  const bos    = lastH > prevH ? 'BOS HAUSSIER — cassure de la résistance précédente'
               : lastL < prevL ? 'BOS BAISSIER — cassure du support précédent'
               : null;
  const choch  = (lastH > prevH && lastL > prevL) ? 'CHoCH potentiel haussier'
               : (lastL < prevL && lastH < prevH) ? 'CHoCH potentiel baissier'
               : null;
  return { bos, choch, note: bos || choch || 'Pas de BOS/CHoCH clair' };
}

function detectFVG(ohlcBars) {
  // Fair Value Gap: gap between bar[i-1].high and bar[i+1].low (bullish) or reverse
  if (!ohlcBars || ohlcBars.length < 3) return [];
  const fvgs = [];
  for (let i = 1; i < ohlcBars.length - 1; i++) {
    const prev = ohlcBars[i - 1], curr = ohlcBars[i], next = ohlcBars[i + 1];
    if (next.low > prev.high) {
      fvgs.push({ type: 'BULLISH_FVG', top: next.low, bottom: prev.high, midpoint: (next.low + prev.high) / 2 });
    }
    if (next.high < prev.low) {
      fvgs.push({ type: 'BEARISH_FVG', top: prev.low, bottom: next.high, midpoint: (prev.low + next.high) / 2 });
    }
  }
  return fvgs.slice(-3); // last 3 FVGs
}

function detectLiquidityZones(ohlcBars) {
  if (!ohlcBars || ohlcBars.length < 5) return { aboveLiquidity: null, belowLiquidity: null };
  const highs = ohlcBars.map(b => b.high).sort((a, b) => b - a);
  const lows  = ohlcBars.map(b => b.low).sort((a, b) => a - b);
  return {
    aboveLiquidity: highs.slice(0, 3).reduce((a, b) => a + b, 0) / 3, // cluster of recent highs
    belowLiquidity: lows.slice(0, 3).reduce((a, b) => a + b, 0) / 3,  // cluster of recent lows
  };
}

async function analyze(mt5Data, profile) {
  const { symbol, price, bid, ask, timeframe, ohlc, rsi, ema20, ema50, ema200, atr } = mt5Data;

  const rsiAnalysis  = analyzeRSI(rsi);
  const emaAnalysis  = analyzeEMA(price, ema20, ema50, ema200);
  const structure    = detectStructure(ohlc || []);
  const fvgs         = detectFVG(ohlc || []);
  const liquidity    = detectLiquidityZones(ohlc || []);

  // Direction scoring
  let bullScore = 0, bearScore = 0;
  if (rsiAnalysis.signal === 'BULLISH' || rsiAnalysis.signal === 'OVERSOLD')  bullScore += 2;
  if (rsiAnalysis.signal === 'BEARISH' || rsiAnalysis.signal === 'OVERBOUGHT') bearScore += 2;
  bullScore += emaAnalysis.bullish;
  bearScore += emaAnalysis.bearish;
  if (structure.bos?.includes('HAUSSIER')) bullScore += 2;
  if (structure.bos?.includes('BAISSIER')) bearScore += 2;

  const direction = bullScore > bearScore ? 'LONG' : bearScore > bullScore ? 'SHORT' : 'NEUTRAL';
  const score     = Math.min(95, 55 + Math.abs(bullScore - bearScore) * 8);
  const levels    = direction !== 'NEUTRAL' ? calcLevels(price, direction, profile, atr) : null;

  // Nearest FVG to current price as target
  const relevantFVG = fvgs.find(f =>
    (direction === 'LONG' && f.type === 'BULLISH_FVG') ||
    (direction === 'SHORT' && f.type === 'BEARISH_FVG')
  );

  return {
    agent: 'trading-core',
    symbol, timeframe, price, direction, score,
    levels,
    rsi: rsiAnalysis,
    ema: emaAnalysis,
    structure,
    fvgs,
    relevantFVG,
    liquidity,
    atr,
    bid, ask,
    spread: ask && bid ? (ask - bid) : null,
  };
}

module.exports = { analyze };
