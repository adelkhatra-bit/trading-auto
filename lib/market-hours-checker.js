/**
 * MarketHoursChecker v2 — 100% LOCAL Market Hours Detection
 * 
 * ✅ 100% LOCAL (aucune API externe)
 * ✅ Sessions hardcoded UTC (aucun DST problem)
 * ✅ Synchrone (<1ms)
 * 
 * Branche: POST /mt5 endpoint (server.js)
 * 
 * Supports:
 * - Forex: 24h/5 (dim 22h → ven 22h UTC)
 * - Metal: suit Forex (XAUUSD)
 * - Equity: 13:30-20:00 UTC weekdays only
 * - Crypto: 24/7
 */

class MarketHoursChecker {
  constructor() {
    // Sessions en UTC (aucun changement DST)
    this.sessions = {
      forex: [
        { name: 'Sydney',  openH: 21, openM: 0,  closeH: 6,  closeM: 0  },   // Sun-Thu
        { name: 'Tokyo',   openH: 0,  openM: 0,  closeH: 9,  closeM: 0  },   // Sun-Thu
        { name: 'London',  openH: 7,  openM: 0,  closeH: 16, closeM: 0  },   // Mon-Fri
        { name: 'NewYork', openH: 13, openM: 0, closeH: 22, closeM: 0  }    // Mon-Fri
      ],
      
      metal: [
        // XAU/XAG follow FOREX hours
        { name: 'Sydney',  openH: 21, openM: 0,  closeH: 6,  closeM: 0  },
        { name: 'Tokyo',   openH: 0,  openM: 0,  closeH: 9,  closeM: 0  },
        { name: 'London',  openH: 7,  openM: 0,  closeH: 16, closeM: 0  },
        { name: 'NewYork', openH: 13, openM: 0, closeH: 22, closeM: 0  }
      ],
      
      equity: [
        // US Equity: weekdays ONLY, 13:30-20:00 UTC (9:30-16:00 ET)
        { name: 'RegularCash', openH: 13, openM: 30, closeH: 20, closeM: 0 }
      ],
      
      crypto: [
        // Always open
        { name: '24/7', openH: 0, openM: 0, closeH: 24, closeM: 0 }
      ]
    };

    this.globalSessions = [
      { key: 'SYDNEY', label: 'Sydney', openH: 21, openM: 0, closeH: 6, closeM: 0, weekdaysOnly: true },
      { key: 'TOKYO', label: 'Tokyo', openH: 0, openM: 0, closeH: 9, closeM: 0, weekdaysOnly: true },
      { key: 'LONDON', label: 'London', openH: 7, openM: 0, closeH: 16, closeM: 0, weekdaysOnly: true },
      { key: 'NEW_YORK', label: 'New York (US)', openH: 13, openM: 0, closeH: 22, closeM: 0, weekdaysOnly: true }
    ];

    this.overlapWindows = [
      { key: 'ASIA_OPEN', label: 'Sydney + Tokyo', openH: 0, openM: 0, closeH: 6, closeM: 0, weekdaysOnly: true },
      { key: 'EUROPE_TRANSITION', label: 'Tokyo + London', openH: 7, openM: 0, closeH: 9, closeM: 0, weekdaysOnly: true },
      { key: 'LONDON_US', label: 'London + New York', openH: 13, openM: 0, closeH: 16, closeM: 0, weekdaysOnly: true }
    ];
  }

  /**
   * Classify asset by symbol pattern (regex)
   * Returns: 'forex' | 'equity' | 'crypto' | 'metal'
   */
  classify(symbol) {
    const s = (symbol || 'EURUSD').toUpperCase();
    
    // Metal
    if (/XAU|XAG|XPT|XPD|GOLD|SILVER|PLATINUM|PALLADIUM/.test(s)) return 'metal';
    
    // Crypto
    // Supports BTCUSD, ETHUSDT, BINANCE:BTCUSDT, BTC/USD, etc.
    if (/(^|[^A-Z])(BTC|ETH|XRP|ADA|SOL|AVAX|LINK|UNI|DOGE|LTC|BNB)(USD|USDT|USDC|EUR|JPY|GBP)?([^A-Z]|$)/.test(s) ||
        /(BTC|ETH|XRP|ADA|SOL|AVAX|LINK|UNI|DOGE|LTC|BNB)[/_:-]?(USD|USDT|USDC|EUR|JPY|GBP)/.test(s))
      return 'crypto';
    
    // US Equity (common ticker symbols)
    if (/\b(AAPL|MSFT|GOOGL|GOOG|AMZN|TSLA|META|NVDA|JPM|BAC|IBM|INTC|AMD|NFLX|UBER|LYFT|SPY|QQQ|IWM|DIA|SPLG|VOO)\b/.test(s)) 
      return 'equity';
    
    // Default: Forex (EURUSD, GBPUSD, etc)
    return 'forex';
  }

  /**
   * Check if time is within session range (handles midnight crossing)
   * All times in minutes since 00:00
   */
  _isTimeInRange(openH, openM, closeH, closeM, currentH, currentM) {
    const open = openH * 60 + openM;
    const close = closeH * 60 + closeM;
    const curr = currentH * 60 + currentM;

    if (open > close) {
      // Crosses midnight (e.g., 21:00 to 06:00)
      return curr >= open || curr < close;
    }

    // Normal range (e.g., 13:30 to 20:00)
    return curr >= open && curr < close;
  }

  /**
   * Calculate minutes until specific time
   */
  _minutesUntil(targetH, targetM, currentH, currentM) {
    const target = targetH * 60 + targetM;
    const curr = currentH * 60 + currentM;
    let diff = target - curr;

    if (diff <= 0) diff += 24 * 60;  // Add 24h if already passed

    return diff;
  }

  /**
   * Format minutes to readable string
   */
  _formatTime(mins) {
    if (mins < 1) return 'now';
    if (mins < 60) return `${mins}m`;

    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  }

  /**
   * Check if day is weekday (Mon-Fri)
   * JS Date: 0=Sun, 1=Mon, ..., 6=Sat
   */
  _isWeekday(dayOfWeek) {
    return dayOfWeek >= 1 && dayOfWeek <= 5;
  }

  _isSessionOpenWindow(windowDef, currentH, currentM, dayOfWeek) {
    if (windowDef.weekdaysOnly && !this._isWeekday(dayOfWeek)) return false;
    return this._isTimeInRange(windowDef.openH, windowDef.openM, windowDef.closeH, windowDef.closeM, currentH, currentM);
  }

  _nextSessionOpeningMinutes(windowDef, currentH, currentM, dayOfWeek) {
    const nowMinutes = currentH * 60 + currentM;
    const targetMinutes = windowDef.openH * 60 + windowDef.openM;
    let dayOffset = 0;

    if (targetMinutes <= nowMinutes) dayOffset = 1;

    if (windowDef.weekdaysOnly) {
      while (!this._isWeekday((dayOfWeek + dayOffset) % 7)) {
        dayOffset += 1;
      }
    }

    return dayOffset * 24 * 60 + Math.max(0, targetMinutes - nowMinutes);
  }

  getGlobalSessionInsights(symbol) {
    const assetClass = this.classify(symbol);
    const now = new Date();
    const currentH = now.getUTCHours();
    const currentM = now.getUTCMinutes();
    const dayOfWeek = now.getUTCDay();

    // Asset-aware sessions to avoid Forex labels for Crypto/Equity.
    if (assetClass === 'crypto') {
      return {
        symbol,
        assetClass,
        utcNow: now.toISOString(),
        sessions: [{
          key: 'CRYPTO_24_7',
          label: 'Crypto 24/7',
          isOpen: true,
          opensIn: 0,
          opensInFormatted: 'now',
          closesIn: null,
          closesInFormatted: null
        }],
        overlaps: [],
        nextSession: {
          key: 'CRYPTO_24_7',
          label: 'Crypto 24/7',
          isOpen: true,
          opensIn: 0,
          opensInFormatted: 'now'
        },
        nextOverlap: null
      };
    }

    if (assetClass === 'equity') {
      const isWeekday = this._isWeekday(dayOfWeek);
      const isOpen = isWeekday && this._isTimeInRange(13, 30, 20, 0, currentH, currentM);
      const opensIn = isOpen ? 0 : this._nextSessionOpeningMinutes(
        { openH: 13, openM: 30, weekdaysOnly: true },
        currentH,
        currentM,
        dayOfWeek
      );
      const closesIn = isOpen ? this._minutesUntil(20, 0, currentH, currentM) : null;
      return {
        symbol,
        assetClass,
        utcNow: now.toISOString(),
        sessions: [{
          key: 'US_EQUITY_CASH',
          label: 'US Equity Cash',
          isOpen,
          opensIn,
          opensInFormatted: this._formatTime(opensIn),
          closesIn,
          closesInFormatted: closesIn === null ? null : this._formatTime(closesIn)
        }],
        overlaps: [],
        nextSession: {
          key: 'US_EQUITY_CASH',
          label: 'US Equity Cash',
          isOpen,
          opensIn,
          opensInFormatted: this._formatTime(opensIn)
        },
        nextOverlap: null
      };
    }

    const sessions = this.globalSessions.map((session) => {
      const open = this._isSessionOpenWindow(session, currentH, currentM, dayOfWeek);
      const opensIn = open ? 0 : this._nextSessionOpeningMinutes(session, currentH, currentM, dayOfWeek);
      const closesIn = open
        ? this._minutesUntil(session.closeH, session.closeM, currentH, currentM)
        : null;
      return {
        key: session.key,
        label: session.label,
        isOpen: open,
        opensIn,
        opensInFormatted: this._formatTime(opensIn),
        closesIn,
        closesInFormatted: closesIn === null ? null : this._formatTime(closesIn)
      };
    });

    const overlaps = this.overlapWindows.map((windowDef) => {
      const open = this._isSessionOpenWindow(windowDef, currentH, currentM, dayOfWeek);
      const opensIn = open ? 0 : this._nextSessionOpeningMinutes(windowDef, currentH, currentM, dayOfWeek);
      const closesIn = open
        ? this._minutesUntil(windowDef.closeH, windowDef.closeM, currentH, currentM)
        : null;
      return {
        key: windowDef.key,
        label: windowDef.label,
        isOpen: open,
        opensIn,
        opensInFormatted: this._formatTime(opensIn),
        closesIn,
        closesInFormatted: closesIn === null ? null : this._formatTime(closesIn)
      };
    });

    return {
      symbol,
      assetClass,
      utcNow: now.toISOString(),
      sessions,
      overlaps,
      nextSession: sessions.slice().sort((a, b) => (a.opensIn || 0) - (b.opensIn || 0))[0] || null,
      nextOverlap: overlaps.slice().sort((a, b) => (a.opensIn || 0) - (b.opensIn || 0))[0] || null
    };
  }

  /**
   * Main API: Get market status for a symbol
   * Returns: { isOpen, market, session, reason, opensIn, closesIn, timestamp }
   */
  getStatus(symbol) {
    const assetClass = this.classify(symbol);
    const config = this.sessions[assetClass];

    if (!config) {
      return {
        symbol,
        isOpen: false,
        market: 'Unknown',
        reason: 'unknown_asset',
        timestamp: new Date().toISOString()
      };
    }

    // Get current UTC time
    const now = new Date();
    const currentH = now.getUTCHours();
    const currentM = now.getUTCMinutes();
    const dayOfWeek = now.getUTCDay();
    const isWeekday = this._isWeekday(dayOfWeek);

    // For equity: weekends closed
    if (assetClass === 'equity' && !isWeekday) {
      const daysUntilMonday = (1 - dayOfWeek + 7) % 7 || 7;
      const minsUntil = daysUntilMonday * 24 * 60;

      return {
        symbol,
        isOpen: false,
        market: 'US Equity',
        session: 'Closed',
        reason: 'weekend',
        opensIn: minsUntil,
        opensInFormatted: this._formatTime(minsUntil),
        sessions: this.getGlobalSessionInsights(symbol),
        timestamp: now.toISOString()
      };
    }

    // Check each session
    for (const session of config) {
      const isInSession = this._isTimeInRange(
        session.openH,
        session.openM,
        session.closeH,
        session.closeM,
        currentH,
        currentM
      );

      if (isInSession) {
        const closesIn = this._minutesUntil(
          session.closeH,
          session.closeM,
          currentH,
          currentM
        );

        const marketName = assetClass === 'forex' ? 'Forex' : 
                          assetClass === 'equity' ? 'US Equity' : 
                          assetClass === 'crypto' ? 'Crypto' : 'Metal';

        return {
          symbol,
          isOpen: true,
          market: marketName,
          session: session.name,
          closesIn,
          closesInFormatted: this._formatTime(closesIn),
          sessions: this.getGlobalSessionInsights(symbol),
          timestamp: now.toISOString()
        };
      }
    }

    // Market closed — find next open session
    const nextSession = config[0];  // First session of day/week
    const opensIn = this._minutesUntil(
      nextSession.openH,
      nextSession.openM,
      currentH,
      currentM
    );

    // If equity and it's still weekend, add days
    if (assetClass === 'equity' && !isWeekday) {
      const daysUntilMonday = (1 - dayOfWeek + 7) % 7 || 7;
      const additionalMins = daysUntilMonday * 24 * 60;
      
      return {
        symbol,
        isOpen: false,
        market: 'US Equity',
        session: 'Closed',
        reason: 'weekend',
        opensIn: additionalMins,
        opensInFormatted: this._formatTime(additionalMins),
        sessions: this.getGlobalSessionInsights(symbol),
        timestamp: now.toISOString()
      };
    }

    const marketName = assetClass === 'forex' ? 'Forex' : 
                      assetClass === 'equity' ? 'US Equity' : 
                      assetClass === 'crypto' ? 'Crypto' : 'Metal';

    return {
      symbol,
      isOpen: false,
      market: marketName,
      session: 'Closed',
      reason: 'closed',
      opensIn,
      opensInFormatted: this._formatTime(opensIn),
      sessions: this.getGlobalSessionInsights(symbol),
      timestamp: now.toISOString()
    };
  }
}

// Export singleton (100% local, no external API)
module.exports = new MarketHoursChecker();
