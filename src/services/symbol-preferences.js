/**
 * SymbolPreferences Service
 * 
 * Manages:
 * - systemPrice (live from MT5)
 * - userReferencePrice (user-registered, persistent)
 * - lockedPrice (contextual, temporary, tied to analysis/position/session)
 * 
 * HIERARCHY: locked(contextual) > userReference > system
 * 
 * NO SILENT OVERRIDES: User price never overridden by system
 */

const fs = require('fs');
const path = require('path');

class SymbolPreferences {
  constructor() {
    this.filePath = path.join(__dirname, '../../store/symbol-preferences.json');
    this.data = null;
  }

  /**
   * Load preferences from disk
   */
  async load() {
    try {
      if (fs.existsSync(this.filePath)) {
        const content = fs.readFileSync(this.filePath, 'utf8');
        this.data = JSON.parse(content);
      } else {
        this.data = { preferences: {}, metadata: { lastUpdated: Date.now(), version: "2.0" } };
        this._ensureFileExists();
      }
      return this.data;
    } catch (error) {
      console.error(`[SymbolPreferences] Load error: ${error.message}`);
      this.data = { preferences: {}, metadata: { lastUpdated: Date.now(), version: "2.0" } };
      return this.data;
    }
  }

  /**
   * Save preferences to disk
   */
  async save() {
    try {
      this.data.metadata.lastUpdated = Date.now();
      fs.writeFileSync(this.filePath, JSON.stringify(this.data, null, 2), 'utf8');
      return true;
    } catch (error) {
      console.error(`[SymbolPreferences] Save error: ${error.message}`);
      throw error;
    }
  }

  /**
   * Ensure file exists (create if not)
   */
  _ensureFileExists() {
    const dir = path.dirname(this.filePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    this.save();
  }

  /**
   * Initialize preference entry for a symbol
   */
  _initializeSymbol(canonical) {
    if (!this.data.preferences[canonical]) {
      this.data.preferences[canonical] = {
        _systemData: {
          price: null,
          source: null,
          timestamp: null,
          age_ms: 0,
          reliable: false
        },
        _userReference: {
          price: null,
          validated: false,
          timestamp: null,
          tolerance_absolute: null,
          tolerance_percent: null,
          variants: []
        },
        _locks: {},
        _metadata: {
          canonical: canonical
        }
      };
    }
  }

  /**
   * GET EFFECTIVE PRICE (The Critical Method)
   * 
   * HIERARCHY:
   * 1. Context-specific lock (if contextId provided & not expired)
   * 2. User reference (if exists & validated)
   * 3. System price (if available & fresh)
   * 4. ERROR
   * 
   * @param {string} canonical - Symbol canonical name
   * @param {string} contextId - Optional context ID (analysis-X, position-Y, etc.)
   * @returns {object} { effectivePrice, source, details... }
   */
  async getEffectivePrice(canonical, contextId = null) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];

    // Priority 1: Context-specific lock (if context provided)
    if (contextId) {
      const lock = pref._locks[contextId];
      if (lock && !this._isLockExpired(lock)) {
        return {
          effectivePrice: lock.price,
          source: "locked",
          context_type: lock.context_type,
          context_id: contextId,
          lock_reason: lock.lock_reason,
          locked_until: lock.locked_until,
          userControlled: true,
          canBeChanged: false
        };
      }
    }

    // Priority 2: User reference (if exists & validated)
    if (pref._userReference.price !== null && pref._userReference.validated) {
      return {
        effectivePrice: pref._userReference.price,
        source: "user_reference",
        context_type: null,
        context_id: null,
        systemPrice: pref._systemData.price,
        userControlled: true,
        canBeChanged: true
      };
    }

    // Priority 3: System price (if available & reliable)
    if (pref._systemData.price !== null && pref._systemData.reliable) {
      return {
        effectivePrice: pref._systemData.price,
        source: "system",
        context_type: null,
        context_id: null,
        userControlled: false,
        canBeChanged: false,
        warning: "No user reference set. Using system default."
      };
    }

    // No price available
    throw new Error(`No price available for ${canonical}. Please register a user reference price.`);
  }

  /**
   * Register user reference price
   * Called when user selects symbol, overrides, validates
   */
  async registerUserReference(canonical, { userPrice, systemPrice, validated = false, variants = [] }) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];

    const delta = Math.abs(userPrice - (systemPrice || userPrice));
    const deltaPercent = systemPrice ? (delta / systemPrice * 100) : 0;

    pref._userReference = {
      price: userPrice,
      validated: validated,
      timestamp: Date.now(),
      tolerance_absolute: delta,
      tolerance_percent: deltaPercent,
      variants: variants,
      system_price_at_registration: systemPrice || null
    };

    // Update audit history (add to array)
    if (!pref._modification_history) {
      pref._modification_history = [];
    }
    pref._modification_history.push({
      old_price: null,
      new_price: userPrice,
      timestamp: Date.now(),
      reason: "initial_registration"
    });

    await this.save();
    return pref;
  }

  /**
   * Check if user has registered reference for symbol
   */
  async hasUserReference(canonical) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];
    return pref._userReference.price !== null && pref._userReference.validated;
  }

  /**
   * Update user reference price (user modification)
   */
  async updateUserReference(canonical, newPrice) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];

    if (!pref._userReference.price) {
      throw new Error(`No existing reference for ${canonical}`);
    }

    const oldPrice = pref._userReference.price;
    const delta = Math.abs(newPrice - (pref._systemData.price || newPrice));
    const deltaPercent = pref._systemData.price ? (delta / pref._systemData.price * 100) : 0;

    pref._userReference.price = newPrice;
    pref._userReference.timestamp = Date.now();
    pref._userReference.tolerance_absolute = delta;
    pref._userReference.tolerance_percent = deltaPercent;

    if (!pref._modification_history) {
      pref._modification_history = [];
    }
    pref._modification_history.push({
      old_price: oldPrice,
      new_price: newPrice,
      timestamp: Date.now(),
      reason: "user_update"
    });

    await this.save();
    return pref;
  }

  /**
   * Clear user reference (revert to system)
   */
  async clearUserReference(canonical) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];

    if (!pref._modification_history) {
      pref._modification_history = [];
    }
    pref._modification_history.push({
      old_price: pref._userReference.price,
      new_price: null,
      timestamp: Date.now(),
      reason: "user_clear"
    });

    pref._userReference = {
      price: null,
      validated: false,
      timestamp: null,
      tolerance_absolute: null,
      tolerance_percent: null,
      variants: []
    };

    await this.save();
  }

  /**
   * Lock price for a context (analysis, position, session)
   * 
   * @param {string} canonical
   * @param {string} contextId - Unique context identifier
   * @param {object} lockData - { price, contextType, reason, expiresIn_ms }
   */
  async lockPrice(canonical, contextId, { price, contextType, reason, expiresIn_ms = null }) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];

    const lockedAt = Date.now();
    const lockedUntil = expiresIn_ms ? lockedAt + expiresIn_ms : null;

    pref._locks[contextId] = {
      symbol: canonical,
      context_type: contextType,
      context_id: contextId,
      price: price,
      locked_at: lockedAt,
      locked_until: lockedUntil,
      lock_reason: reason,
      created_by: "user",
      is_active: true,
      is_expired: false
    };

    // Audit
    if (!pref._lock_history) {
      pref._lock_history = [];
    }
    pref._lock_history.push({
      action: "locked",
      context_id: contextId,
      price: price,
      timestamp: lockedAt,
      reason: reason
    });

    await this.save();
    return pref._locks[contextId];
  }

  /**
   * Unlock price for a context
   */
  async unlockPrice(canonical, contextId) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];

    if (!pref._locks[contextId]) {
      throw new Error(`No lock found for ${canonical}:${contextId}`);
    }

    const lock = pref._locks[contextId];
    
    if (!pref._lock_history) {
      pref._lock_history = [];
    }
    pref._lock_history.push({
      action: "unlocked",
      context_id: contextId,
      price: lock.price,
      timestamp: Date.now(),
      reason: "manual_unlock"
    });

    delete pref._locks[contextId];

    await this.save();
  }

  /**
   * Check if lock is expired
   */
  _isLockExpired(lock) {
    if (!lock.locked_until) return false; // Never expires
    return Date.now() > lock.locked_until;
  }

  /**
   * Clean expired locks
   */
  async cleanExpiredLocks(canonical) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];

    const contextIds = Object.keys(pref._locks);
    for (const contextId of contextIds) {
      if (this._isLockExpired(pref._locks[contextId])) {
        await this.unlockPrice(canonical, contextId);
      }
    }
  }

  /**
   * Get all locks for a symbol
   */
  async getAllLocks(canonical) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];
    return pref._locks || {};
  }

  /**
   * Get specific context lock
   */
  async getContextLock(canonical, contextId) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];
    return pref._locks[contextId] || null;
  }

  /**
   * Update system price (from MT5)
   * CRITICAL: Does NOT override user reference
   */
  async syncSystemPrice(canonical, newSystemPrice, source = "mt5_file") {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];

    const oldPrice = pref._systemData.price;
    const priceChanged = oldPrice && newSystemPrice && oldPrice !== newSystemPrice;
    const percentChange = oldPrice ? Math.abs((newSystemPrice - oldPrice) / oldPrice * 100) : 0;

    pref._systemData = {
      price: newSystemPrice,
      source: source,
      timestamp: Date.now(),
      age_ms: 0,
      reliable: true
    };

    // Audit significant changes
    if (priceChanged && percentChange > 1.0) {
      if (!pref._price_update_history) {
        pref._price_update_history = [];
      }
      pref._price_update_history.push({
        old_price: oldPrice,
        new_price: newSystemPrice,
        percent_change: percentChange,
        timestamp: Date.now(),
        user_reference_at_time: pref._userReference.price,
        status: pref._userReference.price ? "ignored (user ref exists)" : "applied"
      });
    }

    // Don't save on every system update (too frequent)
    // Save only when called explicitly or on interval
    // return without saving by default

    return {
      systemPriceUpdated: true,
      userPricePreserved: pref._userReference.price !== null,
      warning: priceChanged && percentChange > 1.0 ? `System price changed ${percentChange.toFixed(2)}%` : null
    };
  }

  /**
   * Save system price updates (called periodically)
   */
  async saveSystemUpdates() {
    await this.save();
  }

  /**
   * Validate user price vs system price
   * Shows tolerance but doesn't enforce
   */
  validate(canonical, userPrice, systemPrice, maxTolerance_percent = 5.0) {
    if (!systemPrice) {
      return {
        ok: true,
        message: "No system price to compare",
        canUse: true // User price always usable
      };
    }

    const delta = Math.abs(userPrice - systemPrice);
    const deltaPercent = (delta / systemPrice) * 100;

    return {
      ok: deltaPercent <= maxTolerance_percent,
      deltaAbsolute: delta,
      deltaPercent: deltaPercent,
      maxTolerance: maxTolerance_percent,
      message: `Price diff: ${deltaPercent.toFixed(4)}% ${deltaPercent > maxTolerance_percent ? '(>5%)' : '(OK)'}`,
      canUse: true // Always allow user to decide
    };
  }

  /**
   * Get all user preferences (for dashboard, audit)
   */
  async getAllUserReferences() {
    await this.load();
    const result = [];
    for (const canonical of Object.keys(this.data.preferences)) {
      const pref = this.data.preferences[canonical];
      if (pref._userReference.price) {
        result.push({
          canonical,
          userPrice: pref._userReference.price,
          systemPrice: pref._systemData.price,
          locked: Object.keys(pref._locks).length > 0,
          validated: pref._userReference.validated,
          timestamp: pref._userReference.timestamp
        });
      }
    }
    return result;
  }

  /**
   * Get preference summary for single symbol
   */
  async getSummary(canonical) {
    await this.load();
    this._initializeSymbol(canonical);
    const pref = this.data.preferences[canonical];

    return {
      canonical,
      systemPrice: pref._systemData,
      userReference: pref._userReference,
      locks: pref._locks || {},
      modificationHistory: pref._modification_history || [],
      lockHistory: pref._lock_history || []
    };
  }
}

// Singleton export
let instance = null;

async function getSymbolPreferences() {
  if (!instance) {
    instance = new SymbolPreferences();
    await instance.load();
  }
  return instance;
}

module.exports = {
  SymbolPreferences,
  getSymbolPreferences
};
