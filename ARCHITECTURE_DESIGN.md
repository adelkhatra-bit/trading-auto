# 🏗️ ARCHITECTURE DESIGN — Before Implementation

Date: 2026-04-03  
Status: **PROPOSAL REVISED — Awaiting validation before coding**  
Goal: Base propre → testable → cohérent → LOCAL ONLY

---

# CRITICAL PRINCIPLE

🔴 **Prix utilisateur validé JAMAIS écrasé par système**

- Si utilisateur enregistre XAUUSD @ 2375.50, ce prix est la référence
- MT5 peut proposer mise à jour (2375.3), pas la remplacer silencieusement
- Flux principal = LOCAL ONLY (no yahoo/fixture dans priorités)
- Mode dégradé (fallback externe) = désactivé par défaut, marqué explicitement

---

# A. STRUCTURE symbol-preferences.js

## Data Model (3 Concepts Distincts)

```javascript
/**
 * File: store/symbol-preferences.json
 * Persistent layer for user symbol preferences & system state
 * 
 * CONCEPTS:
 * 1. systemPrice = prix remonté automatiquement par source locale (MT5, Bridge)
 * 2. userReferencePrice = prix que l'utilisateur a validé/enregistré comme référence
 * 3. lockedPrice = prix figé temporairement pour cohérence analyse/session
 */

{
  "preferences": {
    "XAUUSD": {
      // ① PRIX SYSTÈME (automatique, remonté par source locale)
      "_system": {
        "price": 2375.3,
        "source": "mt5_file",           // "mt5_file" | "mt5_bridge" | "local_source"
        "timestamp": 1712145600000,     // When fetched
        "age_ms": 2000,
        "reliable": true
      },
      
      // ② PRIX DE RÉFÉRENCE UTILISATEUR (validé par utilisateur)
      "_user_reference": {
        "price": 2375.50,               // Prix que l'utilisateur a enregistré
        "validated": true,              // Utilisateur a vérifié ce prix
        "timestamp": 1712144000000,     // When user set it
        "tolerance": 0.2,               // Δ from system default
        "tolerance_percent": 0.0084,    // % difference (0.0084% < 5% tolerance ✅)
        "variants": ["GOLD", "XAU/USD"] // Alternative names for this symbol
      },
      
      // ③ PRIX VERROUILLÉ (optionnel, pour cohérence session/analyse)
      "_locked": {
        "price": null,                  // null = not locked, or number = locked price
        "locked_until": null,           // Timestamp when lock expires
        "lock_reason": null,            // "session_analysis" | "position_risk" | "manual"
        "locked_by": null               // Who set this lock
      },
      
      // MÉTADONNÉES
      "_metadata": {
        "canonical": "XAUUSD",
        "symbol_type": "metal",
        "last_modified": 1712144000000
      }
    },
    
    "EURUSD": {
      "_system": {
        "price": null,                  // No MT5 data (not in mt5_data.json)
        "source": null,
        "timestamp": null,
        "reliable": false
      },
      "_user_reference": {
        "price": 1.0850,                // User has registered this
        "validated": true,
        "timestamp": 1712100000000,
        "tolerance": 0.0002,
        "tolerance_percent": 0.018,
        "variants": ["EUR/USD", "EURUSD"]
      },
      "_locked": {
        "price": 1.0850,                // User locked this for session
        "locked_until": 1712231600000,  // Until end of analysis session
        "lock_reason": "session_analysis",
        "locked_by": "user"
      },
      "_metadata": {
        "canonical": "EURUSD",
        "symbol_type": "forex",
        "last_modified": 1712144000000
      }
    }
  },
  
  "metadata": {
    "lastUpdated": 1712145600000,
    "version": "2.0"
  }
}
```

## Module API (Core Logic)

```javascript
// store/symbol-preferences.js

class SymbolPreferences {
  
  /**
   * Load all preferences from disk
   * @returns { XAUUSD: {...}, EURUSD: {...}, ... }
   */
  async load()
  
  /**
   * Get EFFECTIVE price to use for a symbol
   * HIERARCHY (in order):
   *   1. Is price locked? → use lockedPrice
   *   2. Does user have validated reference? → use userReferencePrice
   *   3. Fallback to systemPrice (but return metadata to show it's system, not user)
   * 
   * @param {string} canonical - e.g., "XAUUSD"
   * @returns {
   *   effectivePrice: number,        // The price to actually use
   *   source: "locked" | "user_reference" | "system",
   *   systemPrice: number,           // Reference system price (for comparison)
   *   userReferencePrice: number,    // User's registered price (if exists)
   *   locked: boolean,               // Is price locked?
   *   validated: boolean,            // User validated this?
   *   age_ms: number                 // How old is this data?
   * }
   */
  async getEffectivePrice(canonical)
  
  /**
   * Check if user has any preference registered for symbol
   * @param {string} canonical
   * @returns boolean
   */
  async hasUserReference(canonical)
  
  /**
   * Register or update user's reference price for a symbol
   * This is what happens when user selects GOLD, overrides price, validates
   * 
   * @param {string} canonical
   * @param {object} data {
   *   userPrice: number,           // Price user entered
   *   systemPrice: number,         // Current system price (for comparison)
   *   validated: boolean,          // User confirmed this?
   *   variants: Array<string>      // GOLD, XAU/USD, etc.
   * }
   * @returns true if saved successfully
   */
  async registerUserReference(canonical, data)
  
  /**
   * Lock a price for a session/analysis (prevents updates from system)
   * @param {string} canonical
   * @param {number} price
   * @param {string} reason - "session_analysis" | "position_risk" | "manual"
   * @param {number} expiresIn_ms - How long to lock (null = permanent until user unlocks)
   */
  async lockPrice(canonical, price, reason, expiresIn_ms = null)
  
  /**
   * Unlock a price
   * @param {string} canonical
   */
  async unlockPrice(canonical)
  
  /**
   * Update system price (called when MT5 has new data)
   * Does NOT override user reference price
   * @param {string} canonical
   * @param {number} newSystemPrice
   * @param {string} source - "mt5_file" | "mt5_bridge" | "local_source"
   * @returns {
   *   updated: boolean,
   *   userPriceKept: boolean,  // Was user price preserved?
   *   warning: string | null   // "System price changed significantly" etc.
   * }
   */
  async syncSystemPrice(canonical, newSystemPrice, source)
  
  /**
   * Validate user price against system price
   * IMPORTANT: Shows tolerance check, but doesn't enforce
   * User decision is final
   * 
   * @param {string} canonical
   * @param {number} userPrice
   * @param {number} systemPrice
   * @param {number} maxTolerance (%) - e.g., 0.05 = 5%
   * @returns {
   *   ok: boolean,
   *   tolerancePercent: number,
   *   message: string,
   *   canUse: boolean          // Always true - user decides, not system
   * }
   */
  validate(canonical, userPrice, systemPrice, maxTolerance = 0.05)
  
  /**
   * Clear user preference (revert to system default only)
   * @param {string} canonical
   */
  async clearUserReference(canonical)
  
  /**
   * Get all user preferences (for dashboard, audit)
   * @returns Array<{ canonical, userPrice, systemPrice, locked, validated }>
   */
  async getAllUserReferences()
}
```

## Key Behavior Rules

| Scenario | Behavior | Logic |
|----------|----------|-------|
| **Scenario 1**: User registers XAUUSD @ 2375.50 | Save userReferencePrice | This becomes the reference for agents |
| **System updates**: MT5 now shows 2376.0 | Update systemPrice only | Don't touch userReferencePrice |
| **User sees price**: Studio asks for XAUUSD | Return userReferencePrice (2375.50) | NOT system price |
| **Agent requests price**: orchestrator.run() | Get effectivePrice() | Uses hierarchy: locked > user_ref > system |
| **User locks for session**: EURUSD @ 1.0850 | Set lockedPrice + expiry | Even if MT5 changes, use locked |
| **User overrides temporarily**: Change GOLD to 2374.00 | Update userReferencePrice immediately | Not a lock, user can change anytime |

---

# B. FLOW COMPLET (Selection → Usage)

## Visual Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       USER SELECTS SYMBOL (STUDIO)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 1: SYMBOL MATCHING                                                │
│  ────────────────────────                                               │
│                                                                          │
│  Input: User types "GOLD" (or selects from dropdown)                   │
│                                                                          │
│  symbol-matcher.findCanonicalSymbol("GOLD")                            │
│  → { canonical: "XAUUSD", type: "metal", variants: [...] }            │
│                                                                          │
│  ✅ Output: canonical = "XAUUSD"                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 2: FETCH DEFAULT PRICE (BY PRIORITY)                             │
│  ──────────────────────────────────────                                 │
│                                                                          │
│  data-source-manager.getDefaultPrice("XAUUSD")                         │
│  in this order:                                                         │
│                                                                          │
│  ┌─ Priority 1: User locked preference?                                │
│  │  symbol-preferences.get("XAUUSD")                                   │
│  │  → If locked=true: use userPrice (2375.50)                          │
│  │     Return: { price: 2375.50, source: "user_locked", age: 0ms }    │
│  │                                                                      │
│  ├─ Priority 2: MT5 local live data?                                   │
│  │  mt5_data.json read                                                 │
│  │  → { price: 2375.3, source: "mt5", age: 2000ms } ✅               │
│  │                                                                      │
│  ├─ Priority 3: User has previous override?                            │
│  │  symbol-preferences.get("XAUUSD") [not locked]                      │
│  │  → { price: 2375.50, source: "user_manual", age: 1min }            │
│  │                                                                      │
│  ├─ Priority 4: Yahoo fallback                                         │
│  │  fetchYahooPrice("GC=F")                                             │
│  │  → { price: 2410.00, source: "yahoo", age: 15min } ⚠️              │
│  │                                                                      │
│  └─ Priority 5: Hardcoded fixture (last resort)                        │
│     SYMBOL_PRICES constant                                              │
│     → { price: 2412.50, source: "fixture", age: ??? } ❌              │
│                                                                          │
│  ✅ Output: { defaultPrice: 2375.3, source: "mt5", age: 2000 }        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 3: SEND TO UI (Studio)                                           │
│  ───────────────────────────                                            │
│                                                                          │
│  Response to GET /symbol/reference/XAUUSD:                             │
│  {                                                                      │
│    canonical: "XAUUSD",                                                │
│    displayName: "Gold (XAUUSD)",                                       │
│    defaultPrice: 2375.3,                                               │
│    source: "mt5",                                                       │
│    freshness: "2 seconds old",                                         │
│    warning: null,                                                       │
│    canOverride: true                                                    │
│  }                                                                      │
│                                                                          │
│  ✅ UI shows: "Gold (XAUUSD) — 2375.30 (MT5, fresh)"                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 4: USER INPUTS PRICE (Optional Override)                         │
│  ──────────────────────────────────────────────                         │
│                                                                          │
│  User sees: 2375.30 (default)                                          │
│  User types: 2375.50 (manual override)                                │
│                                                                          │
│  System validates immediately (real-time):                             │
│  symbol-preferences.validate("XAUUSD", 2375.50, 2375.3, maxTol=5%)   │
│  → {                                                                    │
│      ok: true,                                                         │
│      tolerancePercent: 0.0084,  // (2375.50 - 2375.3) / 2375.3 * 100  │
│      message: "Within tolerance (0.0084% < 5%)",                      │
│      canUse: true                                                      │
│    }                                                                    │
│                                                                          │
│  ✅ UI shows: "✅ OK (δ = 0.2, 0.0084%)"                              │
│              OR shows warning if out of tolerance                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 5: USER VALIDATES / REGISTERS                                    │
│  ──────────────────────────────────                                     │
│                                                                          │
│  User clicks "Confirm & Register" button                               │
│                                                                          │
│  POST /studio/symbol/register-reference {                              │
│    canonical: "XAUUSD",                                                │
│    userPrice: 2375.50,                                                 │
│    validated: true                                                      │
│  }                                                                      │
│                                                                          │
│  Backend executes:                                                      │
│  symbol-preferences.set("XAUUSD", {                                    │
│    userPrice: 2375.50,                                                 │
│    systemDefaultPrice: 2375.3,                                         │
│    source: "user_manual",                                              │
│    validated: true,                                                    │
│    tolerance: 0.2,                                                     │
│    locked: false                                                       │
│  })                                                                     │
│                                                                          │
│  ✅ Saved to symbol-preferences.json                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 6: BROADCAST TO ALL CLIENTS (SSE)                                │
│  ─────────────────────────────────────────                              │
│                                                                          │
│  market-store.broadcast({                                              │
│    type: "SYMBOL_REGISTERED",                                          │
│    symbol: {                                                            │
│      canonical: "XAUUSD",                                              │
│      displayName: "Gold (XAUUSD)",                                     │
│      price: 2375.50,            // NOW USE USER PRICE                 │
│      source: "user_manual",                                            │
│      systemDefault: 2375.3,                                            │
│      tolerance: 0.2,                                                   │
│      validated: true                                                   │
│    }                                                                    │
│  })                                                                     │
│                                                                          │
│  SSE /stream sends to:                                                 │
│  ✅ Studio (studioapp.js listens)                                      │
│  ✅ Extension (background.js listens)                                  │
│  ✅ Dashboard (index.html polls)                                       │
│  ✅ Agent Log (agent-log-page.html listens)                            │
│                                                                          │
│  All clients now have: XAUUSD = 2375.50 (user registered)              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 7: AGENTS USE REGISTERED PRICE                                   │
│  ────────────────────────────────────                                   │
│                                                                          │
│  orchestrator.run({                                                    │
│    symbol: "XAUUSD",                                                   │
│    price: 2375.50  // ← NOW USES USER REGISTERED PRICE               │
│  })                                                                     │
│                                                                          │
│  ✅ Agent analysis based on user's reference price                     │
│  ✅ Position calculations use 2375.50                                  │
│  ✅ Alerts generated based on 2375.50                                  │
│                                                                          │
│  NO DIVERGENCE: User sees 2375.50, Agent uses 2375.50, Orders at 2375.50
└─────────────────────────────────────────────────────────────────────────┘
```

## Timing & Performance

| Step | Operation | Duration | Notes |
|------|-----------|----------|-------|
| 1 | Symbol matching | ~5ms | symbol-matcher.js (pure logic) |
| 2 | Fetch default price | ~20ms | MT5 file read or user prefs query |
| 3 | Send to UI | ~10ms | JSON response |
| 4 | User input validation | ~2ms | Tolerance check |
| 5 | Register to backend | ~30ms | File write + in-memory update |
| 6 | Broadcast SSE | ~50ms | Send to all connected clients |
| **Total** | **Complete flow** | **~120ms** | **User experience: instant** |

## Error Handling

```javascript
// What happens if:

❌ Symbol not found?
   → Return error with suggestions
   → "Did you mean EUR/USD?"

❌ Price divergence > 5%?
   → Allow but show WARNING
   → "Price >>5% different from system. Continue?"

❌ MT5 data offline AND user has no preference?
   → Fall back to Yahoo
   → Show warning: "Using 15min delayed price"

❌ All sources offline?
   → Show error: "No price sources available"
   → Don't allow registration
```

---

# C. STRUCTURE data-source-manager.js

## Module Purpose

Single source of truth for symbol prices and metadata. All other modules ask this for prices, not directly MT5/Yahoo.

## API (What Methods Exist)

```javascript
// lib/data-source-manager.js

class DataSourceManager {
  
  /**
   * Get price for symbol with source priority logic
   * @param {string} canonical - e.g., "XAUUSD"
   * @returns Promise<{
   *   symbol: string,
   *   canonical: string,
   *   price: number,
   *   source: "user_locked" | "mt5" | "user_manual" | "yahoo" | "fixture",
   *   freshness: string (e.g., "2 seconds old"),
   *   age: number (milliseconds),
   *   warning: string | null,
   *   canAnalyze: boolean
   * }>
   */
  async getPrice(canonical)
  
  /**
   * Get complete symbol data (price + klines + indicators)
   * @param {string} canonical
   * @returns Promise<{
   *   symbol: string,
   *   canonical: string,
   *   price: number,
   *   source: string,
   *   klines: Array (OHLCV bars),
   *   indicators: { rsi, atr, ma20 },
   *   timeframes: ["H1", "H4", "D1"] (available),
   *   validation: { fresh: boolean, reliable: boolean },
   *   warning: string | null
   * }>
   */
  async getSymbolData(canonical)
  
  /**
   * Get klines (OHLCV bars) for symbol
   * @param {string} canonical
   * @param {string} timeframe - "H1", "H4", "D1"
   * @param {number} limit - how many bars (default: 20)
   * @returns Promise<Array> - OHLCV array
   */
  async getKlines(canonical, timeframe = "H1", limit = 20)
  
  /**
   * Validate if symbol data is reliable enough for analysis
   * @param {string} canonical
   * @returns Promise<{
   *   canAnalyze: boolean,
   *   reasons: Array<string>,
   *   confidence: "high" | "medium" | "low"
   * }>
   */
  async canAnalyze(canonical)
  
  /**
   * List all available symbols from all sources
   * @returns Promise<Array<{ canonical, source, available: boolean }>>
   */
  async listAvailableSymbols()
  
  /**
   * Register user preference and update internal state
   * @param {string} canonical
   * @param {object} preference - { userPrice, systemDefault, source, locked }
   */
  async registerUserPreference(canonical, preference)
  
  /**
   * Get source priority for a symbol
   * @returns { primary: string, fallback: string[], strategy: string }
   */
  getSourceStrategy(canonical)
  
  /**
   * Refresh all cached data (called periodically)
   * @param {string} canonical - optional, if null: refresh all
   */
  async refresh(canonical = null)
}
```

## Internal Source Priority Matrix

```javascript
/**
 * Source priority is SYMBOL-SPECIFIC, not global
 */

const SOURCE_STRATEGY = {
  "XAUUSD": {
    primary: "mt5",           // MT5 local (EA writes to file)
    fallback: [
      "user_locked",          // If user has locked preference
      "user_manual",          // If user set override
      "mt5_bridge",           // MT5 Bridge Python (if online)
      "yahoo",                // Yahoo ("GC=F")
      "fixture"               // Hardcoded fallback
    ],
    minFreshness: 5000,       // Must be < 5 seconds old
    maxAge: 60000             // Reject if > 1 minute old
  },
  
  "EURUSD": {
    primary: "user_manual",   // Prefer user input (no live MT5 data)
    fallback: [
      "user_locked",
      "mt5_bridge",           // If Bridge online
      "yahoo",                // Yahoo ("EURUSD=X")
      "fixture"
    ],
    minFreshness: 10000,
    maxAge: 300000            // More tolerance (MT5 Bridge offline)
  },
  
  "BTCUSD": {
    primary: "user_manual",   // No MT5 for crypto
    fallback: [
      "user_locked",
      "mt5_bridge",           // If Bridge has crypto
      "yahoo",                // Yahoo ("BTC-USD")
      "fixture"
    ],
    minFreshness: 15000,
    maxAge: 600000            // Yahoo delay acceptable for crypto
  },
  
  "US500": {
    primary: "user_manual",   // No direct MT5 support
    fallback: [
      "user_locked",
      "yahoo",                // Yahoo S&P500 proxy
      "fixture"
    ],
    minFreshness: 30000,      // Index, less frequent
    maxAge: 900000            // Market hours only
  }
};
```

## Freshness Management

```javascript
/**
 * Check if data is "fresh enough" for analysis
 */

class FreshnessValidator {
  
  isFresh(timestamp, symbol) {
    const age = Date.now() - timestamp;
    const maxFresh = SOURCE_STRATEGY[symbol].minFreshness;
    return age < maxFresh;  // true = data fresh enough for alerts
  }
  
  getWarning(timestamp, symbol) {
    const age = Date.now() - timestamp;
    const maxAge = SOURCE_STRATEGY[symbol].maxAge;
    
    if (age < 5000) return null;
    if (age < 30000) return "data is 30s old";
    if (age < maxAge) return "data is stale, use caution";
    return "data too old, CANNOT USE";
  }
  
  getReliability(source, symbol) {
    // Returns "high", "medium", "low"
    if (source === "user_locked") return "high";      // User confirmed
    if (source === "mt5") return "high";              // Real-time
    if (source === "mt5_bridge") return "high";       // Real-time
    if (source === "user_manual") return "medium";    // Verified by user
    if (source === "yahoo") return "low";             // 15min delay
    if (source === "fixture") return "danger";        // Never use for analysis
  }
}
```

## Real-Time Updates

```javascript
/**
 * Listen to MT5 changes and auto-refresh
 */

class MT5Listener {
  
  async watchMT5Changes(symbol) {
    // Poll mt5_data.json every 2 seconds
    setInterval(() => {
      const currentData = readMT5FileSync(symbol);
      const cached = cache.get(symbol);
      
      if (currentData.price !== cached.price) {
        // Price changed → refresh cache → broadcast via SSE
        cache.set(symbol, currentData);
        market-store.broadcast({
          type: "PRICE_UPDATE",
          symbol,
          price: currentData.price,
          source: "mt5",
          age: 2000
        });
      }
    }, 2000);  // 2 second poll
  }
}
```

---

# D. MULTI-SYMBOL REAL SOLUTION

## Problem Statement

Today:
- ✅ XAUUSD works (mt5_data.json has it)
- ❌ EURUSD doesn't (mt5_data.json doesn't have it)
- ❌ BTCUSD doesn't
- ❌ US500 doesn't

Why? Because `mt5_data.json` is written by only ONE EA (Bridge_MT5_Studio.mq5) and it's configured to output only XAUUSD.

## Solution A: Activate MT5 Bridge Python (Fastest)

```
Current state:
  mt5_bridge.py exists (complete, port 5000)
  BUT: Not running
  
Step 1: Start MT5 Bridge Python on port 5000
  $ python mt5_bridge.py
  
Step 2: Verify it connects to MT5 Terminal
  GET http://localhost:5000/mt5/symbol/EURUSD
  → Should return live EURUSD data
  
Step 3: data-source-manager uses it as fallback
  "if mt5_data.json doesn't have symbol → try mt5_bridge:5000"
  
Result: All symbols work (MT5 can provide them all)
Timeline: 30 minutes setup
Cost: None (local)
```

## Solution B: Extend EA to Write Multiple Symbols (Better Long-term)

```
Current EA (Bridge_MT5_Studio.mq5):
  Writes only XAUUSD to mt5_data.json
  
Extended EA:
  Writes MULTIPLE symbols:
  {
    "symbols": {
      "XAUUSD": { price, bid, ask, klines, ... },
      "EURUSD": { price, bid, ask, klines, ... },
      "BTCUSD": { price, bid, ask, klines, ... },
      ...
    },
    "timestamp": unix_ms
  }
  
In MT5:
  // OnTick() of EA
  UPDATE mt5_data.json with ALL watched symbols
  
Result: All symbols in local file, no Python bridge needed
Timeline: 1-2 hours (requires MT5 access)
Cost: None (modify existing EA)
Risk: Low (just adding more symbols to JSON output)
```

## Solution C: Hybrid (Recommended)

```
Priority:
  1. User preference (symbol-preferences.js) - INSTANT
  2. MT5 local file (mt5_data.json) - IMMEDIATE
  3. MT5 Bridge Python (if running) - FAST
  4. Yahoo fallback - SLOW (15min)
  5. Hardcoded fixture - INVALID

Implementation:
  ✅ symbol-preferences.js → stores user overrides
  ✅ data-source-manager.js → tries all sources in order
  ⚠️ Optional: user provides their own EURUSD price manually
  ⚠️ Optional: activate MT5 Bridge Python when needed
  
Result: 
  - XAUUSD 100% reliable (has mt5_data.json)
  - Other symbols: User can register manual reference
  - If MT5 Bridge online: All symbols auto-available
  
Timeline: Immediate (for symbol-preferences)
         + 30min if user decides to activate Bridge
```

## Proposed Implementation Plan

### Phase 1: Implement Locally (No Infrastructure Changes)
```
1. Create symbol-preferences.js ✅
2. Create data-source-manager.js ✅
3. Add endpoints:
   - GET /symbol/reference/:symbol
   - POST /symbol/register-reference
   - GET /symbol/available
   
Result: User can register any symbol manually
Cost: No MT5 changes needed
Works for: XAUUSD (mt5) + User manual input for others
```

### Phase 2: Activate MT5 Bridge (Optional, Future)
```
1. Start mt5_bridge.py (or user does manually)
2. Update data-source-manager to check Bridge as fallback
3. Auto-discover all MT5 symbols
4. User experience: System auto-finds EURUSD, BTCUSD, etc.

Timeline: When user decides
```

## Real Exploitation Matrix

| Symbol | Phase 1 (Now) | Phase 2 (w/ Bridge) | Notes |
|--------|---------------|-------------------|-------|
| **XAUUSD** | ✅ MT5 file | ✅ MT5 file | Highest priority source |
| **EURUSD** | ✅ User manual | ✅ MT5 Bridge auto | User can set reference |
| **BTCUSD** | ✅ User manual | ✅ MT5 Bridge auto | User can set reference |
| **US500** | ✅ User manual | ✅ Yahoo proxy | User can set reference |
| **Others** | ✅ User manual | ✅ MT5 Bridge auto | Infinitely extensible |

## Testing This

```javascript
// After implementation, test with:

// Test 1: XAUUSD (should use mt5_data.json)
GET /symbol/reference/XAUUSD?canonical=true
→ Should return: { price: 2375.3, source: "mt5", age: 2000 }

// Test 2: EURUSD user registration (user manual)
POST /symbol/register-reference {
  canonical: "EURUSD",
  userPrice: 1.0850,
  validated: true
}
→ Should broadcast via SSE

// Test 3: After registration, check broadcast
GET /symbol/reference/EURUSD?canonical=true
→ Should return: { price: 1.0850, source: "user_manual" }

// Test 4: Verify SSE broadcast (all clients updated)
Subscribe to GET /stream
→ Should see: { type: "SYMBOL_REGISTERED", symbol: { canonical: "EURUSD", price: 1.0850 } }
```

---

# SUMMARY: What Gets Built

## Files to Create

1. **store/symbol-preferences.json** (data file)
   - Persistent storage of user symbol registrations
   - Schema: { preferences: { XAUUSD: {...}, EURUSD: {...} }, metadata }

2. **src/services/symbol-preferences.js** (new module)
   - Load/get/set/validate/lock/clear user preferences
   - Methods: .load(), .get(), .set(), .validate(), .lock(), .clear(), .syncSystemUpdate()

3. **lib/data-source-manager.js** (new module)
   - Unified price fetch with source priority
   - Methods: .getPrice(), .getSymbolData(), .getKlines(), .canAnalyze(), .listAvailableSymbols()

4. **Endpoints in server.js** (modifications)
   - GET /symbol/reference/:canonical
   - POST /symbol/register-reference
   - GET /symbol/available
   - GET /symbol/validate

## Dependencies

- symbol-preferences.js → No deps (pure file I/O + logic)
- data-source-manager.js → Depends on symbol-preferences, market-store, symbol-matcher

## Testing Strategy

Each module independently:
1. symbol-preferences.js → Unit tests on file ops
2. data-source-manager.js → Test with XAUUSD (known working)

Integration:
1. User selects GOLD → Test flow end-to-end
2. Verify SSE broadcast to Studio + Extension + Dashboard
3. Verify orchestrator gets user-registered price, not system default

---

# READY FOR VALIDATION

**Questions for you:**

1. ✅ Does this data structure look right for symbol-preferences.json?
2. ✅ Is the flow (selection → registration → broadcast) clear?
3. ✅ Does the source priority make sense (user > mt5 > user_manual > yahoo > fixture)?
4. ✅ Is the multi-symbol solution realistic (User manual NOW + Bridge later)?
5. ✅ Anything missing or wrong in the proposal?

**Once validated, I can code all 3 modules and tests.**

