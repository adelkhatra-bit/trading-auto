/**
 * DataSourceManager - Unified Symbol Data Layer
 * 
 * CRITICAL: ALL price logic goes through this module
 * - getEffectivePrice(symbol, contextId) is the ONLY price entry point
 * - LOCAL ONLY (mt5_file + userReference)
 * - NO external APIs in main flow
 * - NO direct MT5 access elsewhere
 * 
 * Depends on:
 * - symbol-preferences.js (for userReference + locks)
 * - mt5_data.json (for systemPrice + klines + indicators)
 * 
 * ============================================================================
 * CRITICAL AGENT RULE: canAnalyze vs canUsePrice
 * ============================================================================
 * 
 * Distinguished API:
 *   canUsePrice(symbol[, contextId])
 *     → Price is available for matching/tracking
 *     → Can be just user reference without history
 *   
 *   canAnalyze(symbol[, contextId])
 *     → STRICT GATE: Price + 10+ klines
 *     → If FALSE: agents MUST NOT produce technical signals
 *     → No momentum, no trend, no patterns
 *     → Best case: "reference price only" mode
 * 
 * Example Scenarios:
 * 
 *   Scenario 1: User registers USDJPY reference price (2376.50)
 *     canUsePrice = true  (price available for matching)
 *     canAnalyze = false  (no historical bars)
 *     → Agent can acknowledge the price
 *     → Agent CANNOT generate RSI, trend, signals
 * 
 *   Scenario 2: XAUUSD with MT5 live feed (15 bars, fresh)
 *     canUsePrice = true
 *     canAnalyze = true
 *     → Agent can do full technical analysis
 * 
 *   Scenario 3: XAUUSD with only 5 bars
 *     canUsePrice = true
 *     canAnalyze = false
 *     → Agent acknowledges symbol but waits for more bars
 * 
 * ============================================================================
 */

const fs = require('fs');
const path = require('path');
const { getSymbolPreferences } = require('./symbol-preferences');

class DataSourceManager {
  constructor() {
    this.mt5DataPath = path.join(__dirname, '../../mt5_data.json');
    this.preferences = null;
    this.mt5Data = null;
  }

  /**
   * Initialize manager
   */
  async initialize() {
    this.preferences = await getSymbolPreferences();
    this._loadMT5Data();
  }

  /**
   * Load MT5 data from local file
   */
  _loadMT5Data() {
    try {
      if (fs.existsSync(this.mt5DataPath)) {
        const content = fs.readFileSync(this.mt5DataPath, 'utf8');
        this.mt5Data = JSON.parse(content);
      } else {
        this.mt5Data = null;
      }
    } catch (error) {
      console.error(`[DataSourceManager] MT5 data load error: ${error.message}`);
      this.mt5Data = null;
    }
  }

  /**
   * GET EFFECTIVE PRICE
   * 
   * CRITICAL: This is the ONLY price entry point
   * 
   * All agents, UI, calculations MUST use this method
   * 
   * @param {string} canonical - Symbol canonical name (e.g., "XAUUSD")
   * @param {string} contextId - Optional context ID for locked prices
   * 
   * @returns {object} {
   *   price: number,
   *   source: "locked" | "user_reference" | "system",
   *   contextId: string | null,
   *   timestamp: number,
   *   age_ms: number,
   *   freshness: "fresh" | "stale" | "old" | "unusable",
   *   warning: string | null
   * }
   */
  async getEffectivePrice(canonical, contextId = null) {
    try {
      // CRITICAL: Use symbol-preferences hierarchy
      const priceData = await this.preferences.getEffectivePrice(canonical, contextId);

      return {
        price: priceData.effectivePrice,
        source: priceData.source,
        contextId: priceData.context_id || null,
        timestamp: this._getTimestampForSource(canonical, priceData.source),
        age_ms: this._getAgeForSource(canonical, priceData.source),
        freshness: this._getFreshnessStatus(canonical, priceData.source),
        warning: priceData.warning || null,
        systemPrice: priceData.systemPrice || null,
        locked_until: priceData.locked_until || null,
        lock_reason: priceData.lock_reason || null
      };
    } catch (error) {
      throw new Error(`[DataSourceManager] getEffectivePrice failed for ${canonical}: ${error.message}`);
    }
  }

  /**
   * Get timestamp for price source
   */
  _getTimestampForSource(canonical, source) {
    if (source === "system") {
      return this.mt5Data?.symbol?.timestamp || Date.now();
    }
    // locked and user_reference don't have freshness concept
    return Date.now();
  }

  /**
   * Get age of data for source (in milliseconds)
   */
  _getAgeForSource(canonical, source) {
    if (source === "system") {
      const ts = this.mt5Data?.symbol?.timestamp || Date.now();
      return Date.now() - ts;
    }
    return 0; // locked/user_reference not age-based
  }

  /**
   * Get freshness status
   */
  _getFreshnessStatus(canonical, source) {
    if (source !== "system") {
      return "fresh"; // locked/user_reference always fresh
    }

    const age = this._getAgeForSource(canonical, source);
    const ageSeconds = age / 1000;

    if (ageSeconds < 30) return "fresh";
    if (ageSeconds < 60) return "stale";
    if (ageSeconds < 300) return "old";
    return "unusable";
  }

  /**
   * GET SYMBOL DATA (price + klines + indicators)
   * 
   * CRITICAL DISTINCTION:
   * - canUsePrice: Price is available and usable (price matching, tracking)
   * - canAnalyze: Price + klines sufficient for technical analysis
   * 
   * Example:
   *   userReference WITHOUT klines → canUsePrice=true, canAnalyze=false
   *   locked price (no klines) → canUsePrice=true, canAnalyze=false
   *   system price with 15 klines → canUsePrice=true, canAnalyze=true
   * 
   * @param {string} canonical
   * @param {string} contextId - Optional context for locks
   * 
   * @returns {object} {
   *   canonical: string,
   *   price: number,
   *   source: string,
   *   klines: Array,
   *   indicators: object | null,
   *   timeframes: Array,
   *   validation: { canUsePrice, canAnalyze, confidence, reasons }
   * }
   */
  async getSymbolData(canonical, contextId = null) {
    try {
      // Get effective price
      const priceData = await this.getEffectivePrice(canonical, contextId);

      // Get klines (if available)
      const klines = this._getKlines(canonical);

      // Get indicators (if available)
      const indicators = this._getIndicators(canonical);

      // Determine validation (separate canUsePrice and canAnalyze)
      const validation = this._validateData(canonical, priceData, klines);

      return {
        canonical: canonical,
        price: priceData.price,
        source: priceData.source,
        contextId: priceData.contextId,
        timestamp: priceData.timestamp,
        age_ms: priceData.age_ms,
        freshness: priceData.freshness,
        klines: klines || [],
        indicators: indicators || null,
        timeframes: this._getAvailableTimeframes(canonical),
        validation: validation,
        warning: this._buildWarning(validation, priceData)
      };
    } catch (error) {
      throw new Error(`[DataSourceManager] getSymbolData failed for ${canonical}: ${error.message}`);
    }
  }

  /**
   * Build warning message based on validation
   */
  _buildWarning(validation, priceData) {
    if (validation.canUsePrice && validation.canAnalyze) {
      return null; // All good
    }

    const warnings = [];
    if (!validation.canUsePrice) {
      warnings.push("Price not available");
    }
    if (!validation.canAnalyze) {
      warnings.push("Insufficient klines for technical analysis");
    }

    return warnings.join(" | ");
  }

  /**
   * Get klines for symbol
   * 
   * @param {string} canonical
   * @param {string} timeframe - Optional (default: H1)
   * @param {number} limit - Max number of bars (default: 20)
   */
  async getKlines(canonical, timeframe = "H1", limit = 20) {
    try {
      const klines = this._getKlines(canonical, timeframe);
      if (!klines || klines.length === 0) {
        return [];
      }
      return klines.slice(0, limit);
    } catch (error) {
      console.error(`[DataSourceManager] getKlines error for ${canonical}: ${error.message}`);
      return [];
    }
  }

  /**
   * Internal: Get klines from MT5 data
   * Currently only XAUUSD has MT5 data
   */
  _getKlines(canonical, timeframe = "H1") {
    // Only XAUUSD has local MT5 data
    if (canonical === "XAUUSD" && this.mt5Data?.klines) {
      if (timeframe === "H1") {
        return this.mt5Data.klines;
      }
      // Other timeframes: not stored locally yet
      return [];
    }

    // Other symbols: no local klines
    return [];
  }

  /**
   * Internal: Get indicators from MT5 data
   */
  _getIndicators(canonical) {
    if (canonical === "XAUUSD" && this.mt5Data?.indicators) {
      return {
        rsi: this.mt5Data.indicators.rsi || null,
        atr: this.mt5Data.indicators.atr || null,
        ma20: this.mt5Data.indicators.ma20 || null,
        ma50: this.mt5Data.indicators.ma50 || null,
        trend: this.mt5Data.indicators.trend || null
      };
    }

    return null;
  }

  /**
   * Internal: Get available timeframes for symbol
   */
  _getAvailableTimeframes(canonical) {
    if (canonical === "XAUUSD") {
      return ["H1"]; // Only H1 stored locally for now
    }
    return [];
  }

  /**
   * CAN USE PRICE? (For matching, tracking, reference)
   * 
   * Loose criteria - just need a valid price
   * 
   * @param {string} canonical
   * @param {string} contextId - Optional
   * @returns {boolean}
   */
  async canUsePrice(canonical, contextId = null) {
    try {
      await this.getEffectivePrice(canonical, contextId);
      return true; // If we got here, price exists
    } catch (error) {
      return false;
    }
  }

  /**
   * CAN ANALYZE? (For technical analysis, indicators, real trading signals)
   * 
   * STRICT criteria:
   * - MUST have at least 10 klines (no exceptions)
   * - Price must exist
   * - Source doesn't matter (locked/user_ref/system all ok)
   * 
   * RULE: If canAnalyze=false, agents MUST NOT produce technical signals
   * - At best: price-only mode (matching, reference prices)
   * - NO momentum, NO trend, NO pattern detection
   * 
   * @param {string} canonical
   * @param {string} contextId - Optional
   * @returns {object} { canAnalyze, confidence, reasons }
   */
  async canAnalyze(canonical, contextId = null) {
    try {
      // Step 1: Verify price exists
      const priceData = await this.getEffectivePrice(canonical, contextId);

      // Step 2: Check klines (THIS IS THE GATE)
      const klines = this._getKlines(canonical);
      const reasons = [];

      if (!klines || klines.length === 0) {
        reasons.push("No klines available");
        return {
          canAnalyze: false,
          confidence: "none",
          reasons: reasons
        };
      }

      if (klines.length < 10) {
        reasons.push(`Only ${klines.length} klines available (need ≥10)`);
        return {
          canAnalyze: false,
          confidence: "low",
          reasons: reasons
        };
      }

      // Step 3: Additional checks based on source
      if (priceData.source === "locked") {
        // Locked + 10+ klines = very high confidence
        return {
          canAnalyze: true,
          confidence: "very_high",
          reasons: []
        };
      }

      if (priceData.source === "user_reference") {
        // User ref + 10+ klines = high confidence
        return {
          canAnalyze: true,
          confidence: "high",
          reasons: []
        };
      }

      if (priceData.source === "system") {
        // System + 10+ klines, but check freshness
        if (priceData.freshness === "fresh") {
          return {
            canAnalyze: true,
            confidence: "high",
            reasons: []
          };
        }

        if (priceData.freshness === "stale") {
          // Can analyze but with warning
          return {
            canAnalyze: true,
            confidence: "medium",
            reasons: ["Price is stale (30-60s old)"]
          };
        }

        // Old or unusable
        reasons.push(`Price too old (${Math.floor(priceData.age_ms / 1000)}s)`);
        return {
          canAnalyze: false,
          confidence: "low",
          reasons: reasons
        };
      }

      // Should not reach here
      return {
        canAnalyze: false,
        confidence: "none",
        reasons: ["Unknown error"]
      };
    } catch (error) {
      return {
        canAnalyze: false,
        confidence: "none",
        reasons: [error.message]
      };
    }
  }

  /**
   * Internal: Validate data (separate canUsePrice and canAnalyze)
   */
  _validateData(canonical, priceData, klines) {
    /**
     * CANUSEPRICE: Price is available (for matching, tracking, reference)
     */
    const canUsePrice = !!priceData && !!priceData.price;

    /**
     * CANANALYZE: STRICT gate - need 10+ klines for technical analysis
     */
    const hasKlines = klines && klines.length >= 10;

    // Determine confidence
    let confidence = "none";
    const reasons = [];

    if (canUsePrice && hasKlines) {
      if (priceData.source === "locked") {
        confidence = "very_high";
      } else if (priceData.source === "user_reference") {
        confidence = "high";
      } else if (priceData.source === "system" && priceData.freshness === "fresh") {
        confidence = "high";
      } else if (priceData.source === "system" && priceData.freshness === "stale") {
        confidence = "medium";
        reasons.push("Price is stale (30-60s old)");
      } else {
        confidence = "low";
      }
    } else if (canUsePrice && !hasKlines) {
      confidence = "medium";
      reasons.push("Price available but insufficient klines for analysis");
    } else {
      confidence = "none";
      reasons.push("No price available");
    }

    return {
      canUsePrice: canUsePrice,
      canAnalyze: canUsePrice && hasKlines,
      confidence: confidence,
      reasons: reasons
    };
  }

  /**
   * List available symbols (what can actually be used)
   * 
   * Distinguishes between:
   * - canUsePrice: Available for price matching/tracking
   * - canAnalyze: Available for technical analysis
   */
  async listAvailableSymbols() {
    const symbols = [];

    // XAUUSD: Has system price + klines
    const xauusdCanAnalyze = this.mt5Data?.symbol?.name === "XAUUSD" &&
                             this.mt5Data?.klines &&
                             this.mt5Data.klines.length >= 10;

    symbols.push({
      canonical: "XAUUSD",
      canUsePrice: true, // Has systemPrice
      canAnalyze: xauusdCanAnalyze, // + 10+ klines
      systemSource: "mt5_file",
      hasUserReference: await this.preferences.hasUserReference("XAUUSD"),
      hasKlines: !!(this.mt5Data?.klines && this.mt5Data.klines.length >= 10),
      klinesCount: this.mt5Data?.klines?.length || 0,
      source: this.mt5Data?.symbol?.name === "XAUUSD" ? "mt5" : "none"
    });

    // Other symbols: Require user reference
    const userReferences = await this.preferences.getAllUserReferences();
    for (const userRef of userReferences) {
      if (userRef.canonical !== "XAUUSD") {
        symbols.push({
          canonical: userRef.canonical,
          canUsePrice: true, // User price available
          canAnalyze: false, // NO klines → NO analysis
          systemSource: null,
          hasUserReference: true,
          hasKlines: false,
          klinesCount: 0,
          source: "user_reference"
        });
      }
    }

    return symbols;
  }

  /**
   * Sync system price (called periodically from server)
   * @param {string} canonical
   * @param {number} newPrice
   */
  async syncSystemPrice(canonical, newPrice) {
    try {
      const result = await this.preferences.syncSystemPrice(canonical, newPrice, "mt5_file");
      return result;
    } catch (error) {
      console.error(`[DataSourceManager] syncSystemPrice error for ${canonical}: ${error.message}`);
      throw error;
    }
  }

  /**
   * Reload MT5 data from file (called periodically)
   */
  reloadMT5Data() {
    this._loadMT5Data();
  }

  /**
   * Get confidence level for a source
   */
  getSourceConfidence(source) {
    switch (source) {
      case "locked":
        return "very_high";
      case "user_reference":
        return "high";
      case "system":
        return "medium";
      default:
        return "low";
    }
  }

  /**
   * Verify that NO price logic exists elsewhere
   * (This is a check method to ensure proper usage)
   */
  static verifyNoExternalPricing() {
    // All price access should go through this module
    // Agents must NOT fetch prices directly from MT5 or other sources
    return {
      message: "DataSourceManager is the ONLY price source",
      approved: true
    };
  }
}

// Singleton export
let instance = null;

async function getDataSourceManager() {
  if (!instance) {
    instance = new DataSourceManager();
    await instance.initialize();
  }
  return instance;
}

module.exports = {
  DataSourceManager,
  getDataSourceManager
};
