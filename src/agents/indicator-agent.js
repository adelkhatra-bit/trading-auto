/**
 * Indicator Agent — Generates adaptive technical indicators based on market data
 * Role: Produce custom indicators and confluences for technical analysis
 * 
 * Features:
 * - Calculate RSI, EMA, MACD, Bollinger Bands
 * - Detect confluences and signals
 * - Generate MQL5 code for MT5
 * - Adaptive to market type (Forex, Equity, Crypto, Metal)
 */

class IndicatorAgent {
  constructor() {
    this.name = 'indicator-agent';
    this.role = 'Technical indicator generator';
    this.indicators = {};
    this.lastCandles = {};
  }

  /**
   * Calculate RSI (Relative Strength Index)
   * @param {array} closes - Array of closing prices
   * @param {number} period - Period (default 14)
   */
  calculateRSI(closes, period = 14) {
    if (closes.length < period + 1) return null;
    
    let gains = 0, losses = 0;
    for (let i = closes.length - period; i < closes.length; i++) {
      const change = closes[i] - closes[i - 1];
      if (change > 0) gains += change;
      else losses += Math.abs(change);
    }
    
    const avgGain = gains / period;
    const avgLoss = losses / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));
    
    return Math.round(rsi * 100) / 100;
  }

  /**
   * Calculate EMA (Exponential Moving Average)
   * @param {array} closes - Array of closing prices
   * @param {number} period - Period
   */
  calculateEMA(closes, period = 20) {
    if (closes.length < period) return null;
    
    let sma = closes.slice(-period).reduce((a, b) => a + b, 0) / period;
    const multiplier = 2 / (period + 1);
    
    for (let i = closes.length - period; i < closes.length; i++) {
      const ema = (closes[i] - sma) * multiplier + sma;
      sma = ema;
    }
    
    return Math.round(sma * 10000) / 10000;
  }

  /**
   * Calculate MACD (Moving Average Convergence Divergence)
   * @param {array} closes - Array of closing prices
   */
  calculateMACD(closes) {
    const ema12 = this.calculateEMA(closes, 12);
    const ema26 = this.calculateEMA(closes, 26);
    
    if (!ema12 || !ema26) return null;
    
    const macd = ema12 - ema26;
    return {
      macd: Math.round(macd * 10000) / 10000,
      ema12: Math.round(ema12 * 10000) / 10000,
      ema26: Math.round(ema26 * 10000) / 10000
    };
  }

  /**
   * Calculate Bollinger Bands
   * @param {array} closes - Array of closing prices
   * @param {number} period - Period (default 20)
   * @param {number} stdDev - Standard deviations (default 2)
   */
  calculateBollingerBands(closes, period = 20, stdDev = 2) {
    if (closes.length < period) return null;
    
    const lastPrices = closes.slice(-period);
    const sma = lastPrices.reduce((a, b) => a + b, 0) / period;
    const variance = lastPrices.reduce((sum, price) => sum + Math.pow(price - sma, 2), 0) / period;
    const std = Math.sqrt(variance);
    
    return {
      upper: Math.round((sma + stdDev * std) * 10000) / 10000,
      middle: Math.round(sma * 10000) / 10000,
      lower: Math.round((sma - stdDev * std) * 10000) / 10000
    };
  }

  /**
   * Generate indicators for a symbol
   * @param {string} symbol - Asset symbol
   * @param {array} candles - Array of candles {o, h, l, c, v, t}
   */
  async generateIndicators(symbol, candles = []) {
    if (!candles || candles.length < 26) {
      return {
        symbol,
        error: 'Insufficient data (need 26+ candles)',
        indicators: []
      };
    }

    const closes = candles.map(c => parseFloat(c.c || c.close || 0));
    const highs = candles.map(c => parseFloat(c.h || c.high || 0));
    const lows = candles.map(c => parseFloat(c.l || c.low || 0));

    const rsi = this.calculateRSI(closes);
    const ema20 = this.calculateEMA(closes, 20);
    const ema50 = this.calculateEMA(closes, 50);
    const macd = this.calculateMACD(closes);
    const bb = this.calculateBollingerBands(closes);

    // Detect confluences
    const confluences = [];
    
    if (rsi && rsi > 70) confluences.push('RSI Overbought');
    if (rsi && rsi < 30) confluences.push('RSI Oversold');
    if (ema20 && ema50 && ema20 > ema50) confluences.push('EMA20 > EMA50 (Bullish)');
    if (ema20 && ema50 && ema20 < ema50) confluences.push('EMA20 < EMA50 (Bearish)');
    if (macd && macd.macd > 0) confluences.push('MACD Positive');
    if (macd && macd.macd < 0) confluences.push('MACD Negative');

    const indicators = [
      { name: 'RSI(14)', value: rsi, signal: rsi > 70 ? 'Overbought' : rsi < 30 ? 'Oversold' : 'Neutral' },
      { name: 'EMA(20)', value: ema20 },
      { name: 'EMA(50)', value: ema50 },
      { name: 'MACD', value: macd?.macd, signal: macd?.macd > 0 ? 'Bullish' : 'Bearish' },
      { name: 'BB Upper', value: bb?.upper },
      { name: 'BB Middle', value: bb?.middle },
      { name: 'BB Lower', value: bb?.lower }
    ];

    const aggregateSignal = confluences.length >= 3 ? 'STRONG' : confluences.length >= 2 ? 'MODERATE' : 'WEAK';

    return {
      symbol,
      timestamp: new Date().toISOString(),
      indicators: indicators.filter(i => i.value !== null),
      confluences,
      aggregateSignal,
      mql5Code: this.generateMQL5Code(symbol, indicators)
    };
  }

  /**
   * Generate MQL5 code for indicators
   * @param {string} symbol - Asset symbol
   * @param {array} indicators - Indicators array
   */
  generateMQL5Code(symbol, indicators) {
    const indicatorNames = indicators.map(i => `${i.name.replace(/[()]/g, '')}`).join(', ');
    return `
// Auto-generated indicators for ${symbol}
#property indicator_buffers 3
#property indicator_plots   3

Buffer handle_rsi = iRSI(_Symbol, _Period, 14, PRICE_CLOSE);
Buffer handle_ema20 = iMA(_Symbol, _Period, 20, 0, MODE_EMA, PRICE_CLOSE);
Buffer handle_ema50 = iMA(_Symbol, _Period, 50, 0, MODE_EMA, PRICE_CLOSE);

// Indicators: ${indicatorNames}
// Access: iGetArray(handle_rsi, 0, rsi_buffer);
    `.trim();
  }

  /**
   * Get agent state
   */
  getState() {
    return {
      name: this.name,
      role: this.role,
      indicatorsGenerated: Object.keys(this.indicators).length,
      lastUpdate: Object.values(this.indicators)[0]?.timestamp || null
    };
  }
}

module.exports = new IndicatorAgent();
