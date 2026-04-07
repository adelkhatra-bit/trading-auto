/**
 * Surveillance Agent — Monitors MT5 updates and triggers analysis when needed
 * Role: Event-driven analyst trigger (replaces CPU-heavy continuous loop)
 * 
 * Features:
 * - Listens to MT5 price changes
 * - Triggers orchestrator analysis when price changes >0.5% OR >30s elapsed
 * - Emits events for other agents to listen to
 * - Non-blocking, event-driven architecture
 */

const EventEmitter = require('events');
const path = require('path');

class SurveillanceAgent extends EventEmitter {
  constructor() {
    super();
    this.name = 'surveillance-agent';
    this.role = 'Monitors MT5 activity, triggers analysis intelligently';
    this.lastAnalysis = {};  // {symbol: {price, timestamp}}
    this.priceThreshold = 0.005;  // 0.5% change threshold
    this.timeThreshold = 30000;   // 30 seconds
    this.isActive = false;
    this.lastIndicators = {};  // {symbol: {rsi, macd, trend, strength, context, zones}}
  }

  /**
   * Initialize surveillance agent
   */
  initialize() {
    console.log('[SURVEILLANCE] Agent initialized — listening for MT5 updates');
    this.isActive = true;
  }

  /**
   * Check if analysis should be triggered for this symbol
   * @param {string} symbol - Asset symbol
   * @param {number} currentPrice - Current price
   * @returns {boolean} true if should trigger analysis
   */
  shouldTriggerAnalysis(symbol, currentPrice) {
    if (!this.lastAnalysis[symbol]) {
      this.lastAnalysis[symbol] = { price: currentPrice, timestamp: Date.now() };
      return true;  // First tick always triggers
    }

    const last = this.lastAnalysis[symbol];
    const timeSinceLastAnalysis = Date.now() - last.timestamp;
    const priceChange = Math.abs((currentPrice - last.price) / last.price);

    // Trigger if: price moved >0.5% OR >30s since last analysis
    if (priceChange > this.priceThreshold || timeSinceLastAnalysis > this.timeThreshold) {
      this.lastAnalysis[symbol] = { price: currentPrice, timestamp: Date.now() };
      return true;
    }

    return false;
  }

  /**
   * Update indicators for symbol (called from /tv-webhook)
   * @param {string} symbol - Symbol
   * @param {object} indicators - {rsi, macd, trend, strength, context, zones}
   */
  updateIndicators(symbol, indicators = {}) {
    this.lastIndicators[symbol] = {
      ...this.lastIndicators[symbol],
      ...indicators,
      timestamp: Date.now()
    };
  }

  /**
   * Multi-factor decision: evaluate if signal is exploitable
   * SI: tendance alignée + force >70% + RSI cohérent + contexte avec avantage → EXPLOITABLE
   * SINON → NON EXPLOITABLE
   * @param {string} symbol - Symbol
   * @returns {object} {exploitable: boolean, reasoning: string, score: number}
   */
  evaluateSignal(symbol) {
    const ind = this.lastIndicators[symbol];
    if (!ind) return { exploitable: false, reasoning: 'Pas d\'indicateurs', score: 0 };

    let score = 0;
    let factors = '';

    // Factor 1: Tendance alignée (micro + macro)
    const trendAligned = ind.trend && (ind.trend.micro === ind.trend.macro);
    if (trendAligned) {
      score += 25;
      factors += '[✅ TREND] ';
    } else {
      factors += '[❌ TREND] ';
    }

    // Factor 2: Force > 70%
    const strength = parseFloat(ind.strength) || 0;
    if (strength > 70) {
      score += 25;
      factors += `[✅ FORCE ${strength}%] `;
    } else {
      factors += `[❌ FORCE ${strength}%] `;
    }

    // Factor 3: RSI cohérent (30-70 zone, pas suracheté/survendu)
    const rsi = parseFloat(ind.rsi);
    if (rsi && rsi > 30 && rsi < 70) {
      score += 20;
      factors += `[✅ RSI ${rsi.toFixed(1)}] `;
    } else {
      factors += `[❌ RSI ${rsi ? rsi.toFixed(1) : '?'}] `;
    }

    // Factor 4: Contexte avec avantage
    const contextAdvantage = ind.context && ind.context.includes('with-advantage');
    if (contextAdvantage) {
      score += 15;
      factors += '[✅ CONTEXT] ';
    } else {
      factors += '[❌ CONTEXT] ';
    }

    // Factor 5: Zones (liquidité/retournement)
    const goodZones = ind.zones && (ind.zones.includes('liquidity') || ind.zones.includes('reversal'));
    if (goodZones) {
      score += 10;
      factors += '[✅ ZONES] ';
    } else {
      factors += '[❌ ZONES] ';
    }

    // Factor 6: Multi-timeframe alignment
    const mtfAligned = ind.trend && ind.trend.mtf_aligned;
    if (mtfAligned) {
      score += 5;
      factors += '[✅ MTF] ';
    } else {
      factors += '[❌ MTF] ';
    }

    const exploitable = score >= 60; // Besoin de >= 60 points pour exploiter

    return {
      exploitable,
      reasoning: factors,
      score,
      timestamp: ind.timestamp,
      details: {
        trendAligned,
        strength,
        rsi,
        contextAdvantage,
        goodZones,
        mtfAligned
      }
    };
  }

  /**
   * Handle incoming MT5 tick
   * @param {string} symbol - Symbol name
   * @param {object} tickData - {price, bid, ask, volume, etc}
   */
  onMT5Tick(symbol, tickData = {}) {
    if (!this.isActive) return;

    const price = tickData.price || tickData.bid || tickData.ask;
    if (!price) return;

    // Check if we should trigger analysis
    const shouldTrigger = this.shouldTriggerAnalysis(symbol, price);

    if (shouldTrigger) {
      // Evaluate multi-factor signal
      const signalEval = this.evaluateSignal(symbol);

      // Only emit if signal is exploitable or indicators not yet available
      if (signalEval.exploitable || !this.lastIndicators[symbol]) {
        this.emit('trigger-analysis', {
          symbol,
          price,
          bid: tickData.bid,
          ask: tickData.ask,
          volume: tickData.volume,
          timestamp: Date.now(),
          reason: this.lastAnalysis[symbol].timestamp ? 'price-change' : 'first-tick',
          signalEvaluation: signalEval
        });

        console.log(`[SURVEILLANCE] ✅ Analysis triggered for ${symbol} @ ${price} | Score: ${signalEval.score}/100 ${signalEval.reasoning}`);
      } else {
        console.log(`[SURVEILLANCE] ℹ️ Signal not exploitable for ${symbol} | Score: ${signalEval.score}/100 ${signalEval.reasoning}`);
      }
    }
  }

  /**
   * Add symbol to active surveillance
   * @param {string} symbol - Symbol to watch
   */
  watchSymbol(symbol) {
    if (!this.lastAnalysis[symbol]) {
      this.lastAnalysis[symbol] = null;
      console.log(`[SURVEILLANCE] Now watching: ${symbol}`);
    }
  }

  /**
   * Remove symbol from surveillance
   * @param {string} symbol - Symbol to stop watching
   */
  unwatchSymbol(symbol) {
    delete this.lastAnalysis[symbol];
    console.log(`[SURVEILLANCE] Stopped watching: ${symbol}`);
  }

  /**
   * Get agent state
   */
  getState() {
    return {
      name: this.name,
      role: this.role,
      active: this.isActive,
      watching: Object.keys(this.lastAnalysis),
      priceThreshold: `${this.priceThreshold * 100}%`,
      timeThreshold: `${this.timeThreshold / 1000}s`,
      lastAnalysis: this.lastAnalysis
    };
  }

  /**
   * Enable/disable surveillance
   * @param {boolean} enabled - Whether to enable
   */
  setActive(enabled) {
    this.isActive = !!enabled;
    console.log(`[SURVEILLANCE] ${enabled ? '✅ ACTIVE' : '⏸️ PAUSED'}`);
  }
}

module.exports = new SurveillanceAgent();
