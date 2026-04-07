# 🔧 ARCHITECTURE DESIGN — CORRECTED

Date: 2026-04-03  
Status: **PROPOSAL REVISED — Awaiting final validation**  
Goal: Base propre → LOCAL ONLY → No silent override

---

# 🔴 CRITICAL PRINCIPLE: USER PRICE NEVER SILENTLY OVERRIDDEN

If user registers XAUUSD @ 2375.50, this is the reference.
MT5/System can propose update (2375.3), but NEVER replaces user price.

---

# A. STRUCTURE symbol-preferences.js — 3 Distinct Concepts

## Data Model: systemPrice vs userReferencePrice vs lockedPrice

```javascript
/**
 * File: store/symbol-preferences.json
 * 
 * TROIS concepts distincts:
 * 1. systemPrice = prix automatiquement remonté (MT5, Bridge local)
 * 2. userReferencePrice = prix que l'utilisateur a validé
 * 3. lockedPrice = prix figé pour cohérence session/analyse
 */

{
  "preferences": {
    "XAUUSD": {
      // ① PRIX SYSTÈME (MT5, Bridge, source locale)
      "_systemData": {
        "price": 2375.3,
        "source": "mt5_file",
        "timestamp": 1712145600000,
        "age_ms": 2000,
        "reliable": true
      },
      
      // ② PRIX DE RÉFÉRENCE UTILISATEUR (validé/enregistré)
      "_userReference": {
        "price": 2375.50,          // What user set as reference
        "validated": true,         // User confirmed this
        "timestamp": 1712144000000,
        "tolerance_absolute": 0.2,
        "tolerance_percent": 0.0084,
        "variants": ["GOLD", "XAU/USD"]
      },
      
      // ③ PRIX VERROUILLÉ (pour cohérence session)
      "_locked": {
        "price": null,
        "locked_until": null,
        "lock_reason": null
      }
    },
    
    "EURUSD": {
      "_systemData": {
        "price": null,             // No MT5 data for EURUSD
        "source": null,
        "reliable": false
      },
      "_userReference": {
        "price": 1.0850,           // User registered this
        "validated": true,
        "timestamp": 1712100000000,
        "tolerance_absolute": 0.0002,
        "tolerance_percent": 0.018,
        "variants": ["EUR/USD"]
      },
      "_locked": {
        "price": 1.0850,           // User locked for session
        "locked_until": 1712231600000,
        "lock_reason": "session_analysis"
      }
    }
  }
}
```

## Module API: Core Methods

```javascript
// src/services/symbol-preferences.js

class SymbolPreferences {
  
  /**
   * GET EFFECTIVE PRICE (The Critical Method)
   * HIERARCHY (strict order):
   *   1. Is price locked? → use lockedPrice (inviolable)
   *   2. User reference exists & validated? → use userReferencePrice
   *   3. Fallback to systemPrice (only if user hasn't set reference)
   * 
   * CRITICAL: User price is NEVER silently overridden by system
   */
  async getEffectivePrice(canonical) {
    const pref = await this.get(canonical);
    
    // Step 1: Locked price takes absolute priority
    if (pref._locked.price !== null && !this.isLockExpired(pref._locked.locked_until)) {
      return {
        effectivePrice: pref._locked.price,
        source: "locked",
        userControlled: true,
        canBeChanged: false,
        reason: pref._locked.lock_reason
      };
    }
    
    // Step 2: User reference is primary (NOT system)
    if (pref._userReference.price !== null && pref._userReference.validated) {
      return {
        effectivePrice: pref._userReference.price,
        source: "user_reference",
        userControlled: true,
        canBeChanged: true,
        systemPrice: pref._systemData.price  // For comparison/audit only
      };
    }
    
    // Step 3: System price only if user hasn't set reference
    if (pref._systemData.price !== null && pref._systemData.reliable) {
      return {
        effectivePrice: pref._systemData.price,
        source: "system",
        userControlled: false,
        canBeChanged: false,
        warning: "No user reference. Using system default."
      };
    }
    
    // Nothing available
    throw new Error(`No price available for ${canonical}`);
  }
  
  /**
   * Register user reference price
   * When user selects GOLD, overrides, validates → this is called
   */
  async registerUserReference(canonical, {
    userPrice,
    systemPrice,
    validated = false,
    variants = []
  }) {
    const pref = await this.get(canonical);
    if (!pref) throw new Error(`Unknown symbol: ${canonical}`);
    
    pref._userReference = {
      price: userPrice,
      validated: validated,
      timestamp: Date.now(),
      tolerance_absolute: Math.abs(userPrice - systemPrice),
      tolerance_percent: ((userPrice - systemPrice) / systemPrice * 100),
      variants: variants
    };
    
    // CRITICAL: Do NOT lock automatically
    // User can change this anytime
    
    await this.save();
    return pref;
  }
  
  /**
   * Lock price for session (prevents any changes)
   * User explicitly chooses to lock for analysis
   */
  async lockPrice(canonical, price, reason = "manual", expiresIn_ms = null) {
    const pref = await this.get(canonical);
    pref._locked = {
      price: price,
      locked_until: expiresIn_ms ? Date.now() + expiresIn_ms : null,
      lock_reason: reason
    };
    await this.save();
  }
  
  /**
   * Unlock price
   */
  async unlockPrice(canonical) {
    const pref = await this.get(canonical);
    pref._locked = { price: null, locked_until: null, lock_reason: null };
    await this.save();
  }
  
  /**
   * Update system price (called when MT5 has new data)
   * CRITICAL: Does NOT override user reference
   */
  async syncSystemPrice(canonical, newSystemPrice, source = "mt5_file") {
    const pref = await this.get(canonical);
    const oldSystemPrice = pref._systemData.price;
    
    pref._systemData = {
      price: newSystemPrice,
      source: source,
      timestamp: Date.now(),
      age_ms: 0,
      reliable: true
    };
    
    // Check if system price changed significantly
    if (oldSystemPrice && pref._userReference.price) {
      const priceChange = Math.abs(newSystemPrice - oldSystemPrice) / oldSystemPrice * 100;
      if (priceChange > 1.0) {  // More than 1% change
        console.warn(`System price for ${canonical} changed ${priceChange}%`);
        // Don't override user price, just log warning
      }
    }
    
    await this.save();
    return { systemPriceUpdated: true, userPricePreserved: true };
  }
  
  /**
   * Validate user price vs system price
   * Shows tolerance but doesn't enforce
   * User decision is final
   */
  validate(canonical, userPrice, systemPrice, maxTolerance_percent = 5.0) {
    if (!systemPrice) {
      return {
        ok: true,
        message: "No system price to compare",
        canUse: true  // User price is always usable
      };
    }
    
    const delta = Math.abs(userPrice - systemPrice);
    const deltaPercent = (delta / systemPrice) * 100;
    
    return {
      ok: deltaPercent <= maxTolerance_percent,
      deltaAbsolute: delta,
      deltaPercent: deltaPercent,
      maxTolerance: maxTolerance_percent,
      message: `Price diff: ${deltaPercent.toFixed(4)}% ${deltaPercent > maxTolerance_percent ? '(>5%)' : '(ok)'}`,
      canUse: true  // Always allow user to decide
    };
  }
  
  /**
   * Get single preference (full data)
   */
  async get(canonical) {
    const data = await this.load();
    return data.preferences[canonical] || null;
  }
  
  /**
   * Load from file
   */
  async load() {
    // Read symbol-preferences.json
  }
  
  /**
   * Save to file
   */
  async save() {
    // Write symbol-preferences.json
  }
  
  /**
   * Clear user reference (keep system price as fallback)
   */
  async clearUserReference(canonical) {
    const pref = await this.get(canonical);
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
}
```

## When Each Price is Used

| User State | getEffectivePrice() Returns | Used By | Result |
|-----------|---------------------------|---------|--------|
| User locked XAUUSD @ 2375.50 | 2375.50 | Agent | ✅ Inviolable for session |
| User registered @ 2375.50 (not locked) | 2375.50 | Agent | ✅ User's choice |
| MT5 updates to 2376.0 | Still 2375.50 | Agent | ✅ User price kept, system updated silently |
| User cleared reference | 2375.3 (system) | Agent | ✅ Falls back to system |
| No reference, no system | ERROR | None | ✅ Explicit error, not silent |

---

# B. FLOW COMPLET MÉTIER (8 Steps)

## Step-by-Step Flow

```
┌───────────────────────────────────────────────────────────────────────┐
│ STEP 1: USER SÉLECTIONNE SYMBOLE                                      │
│ Utilisateur clique "GOLD" ou tape dans input                         │
├───────────────────────────────────────────────────────────────────────┤
│ Output: canonical = "XAUUSD" via symbol-matcher                       │
└───────────────────────────────────────────────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEP 2: SYSTÈME PROPOSE PRIX PAR DÉFAUT                              │
│ data-source-manager recherche source locale uniquement:              │
│   1. MT5 file (mt5_data.json) → 2375.3 ✅                             │
│   2. User reference (si existe) → 2375.50                             │
│ Output: systemPrice = 2375.3 (MT5, frais)                             │
│ Note: XAUUSD seul a MT5 real, autres = null                          │
└───────────────────────────────────────────────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEP 3: SEND TO UI (STUDIO)                                          │
│ GET /symbol/reference/XAUUSD                                         │
│ Response:                                                              │
│ {                                                                      │
│   canonical: "XAUUSD",                                               │
│   systemPrice: 2375.3,   ← Système propose                           │
│   userReferencePrice: null,  ← Aucune référence utilisateur encore  │
│   inputField: "empty"    ← Utilisateur peut saisir                   │
│ }                                                                      │
│                                                                        │
│ UI shows: "Gold (XAUUSD) — system: 2375.30 [input: ____]"           │
└───────────────────────────────────────────────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEP 4: USER SAISIT PRIX DE RÉFÉRENCE (optionnel)                    │
│ User voit: 2375.30 (système)                                          │
│ User tape: 2375.50 (manual override OR validation)                   │
│                                                                        │
│ Validation instantanée:                                               │
│ symbol-preferences.validate("XAUUSD", 2375.50, 2375.3)              │
│ Returns: {                                                             │
│   ok: true,                                                            │
│   deltaPercent: 0.0084,                                               │
│   message: "Within tolerance",                                        │
│   canUse: true  ← User decision final, not enforced                  │
│ }                                                                      │
│                                                                        │
│ UI shows: "✅ OK (0.0084% diff)"                                      │
└───────────────────────────────────────────────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEP 5: USER VALIDE & ENREGISTRE                                      │
│ User clicks "Confirm & Register as Reference"                        │
│                                                                        │
│ POST /symbol/register-reference {                                    │
│   canonical: "XAUUSD",                                               │
│   userPrice: 2375.50,                                                │
│   validated: true                                                    │
│ }                                                                      │
│                                                                        │
│ Backend calls:                                                         │
│ preferences.registerUserReference("XAUUSD", {                        │
│   userPrice: 2375.50,                                                │
│   systemPrice: 2375.3,                                               │
│   validated: true                                                    │
│ })                                                                     │
│                                                                        │
│ Internal state becomes:                                               │
│ _userReference = { price: 2375.50, validated: true }                 │
│ _locked = { price: null }  ← NOT locked (can change)                 │
│                                                                        │
│ ✅ Saved to symbol-preferences.json                                   │
└───────────────────────────────────────────────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEP 6: BROADCAST À TOUS LES CLIENTS (SSE)                           │
│ market-store.broadcast({                                             │
│   type: "SYMBOL_REGISTERED",                                         │
│   canonical: "XAUUSD",                                               │
│   userPrice: 2375.50,    ← CECI DEVIENT LA RÉFÉRENCE                 │
│   systemPrice: 2375.3,   ← Pour comparaison seulement                │
│   locked: false                                                      │
│ })                                                                    │
│                                                                        │
│ SSE /stream to:                                                       │
│ ✅ Studio (studioapp.js)                                              │
│ ✅ Extension (background.js)                                          │
│ ✅ Dashboard                                                           │
│ ✅ Agent Log                                                           │
│                                                                        │
│ All clients: XAUUSD = 2375.50 (USER REGISTERED)                      │
└───────────────────────────────────────────────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEP 7: AGENTS UTILISENT LE PRIX ENREGISTRÉ                          │
│                                                                        │
│ Quand orchestrator.run() appelle pour prix:                          │
│ const price = await preferences.getEffectivePrice("XAUUSD")          │
│                                                                        │
│ Hierarchy check:                                                       │
│ 1. Locked? No                                                        │
│ 2. User reference exists? YES → return 2375.50                       │
│ 3. (never reach system price)                                         │
│                                                                        │
│ Returns: {                                                             │
│   effectivePrice: 2375.50,                                            │
│   source: "user_reference",     ← Clear it's from user              │
│   userControlled: true,                                              │
│   systemPrice: 2375.3           ← For audit                          │
│ }                                                                      │
│                                                                        │
│ ✅ Agent uses 2375.50 (not 2375.3)                                   │
│ ✅ Position calculations use 2375.50                                  │
│ ✅ Alerts based on 2375.50                                            │
│ ✅ COHERENCE: User sees 2375.50, Agent uses 2375.50                  │
└───────────────────────────────────────────────────────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│ STEP 8: MT5 UPDATES (NO SILENT OVERRIDE)                             │
│                                                                        │
│ MT5 price changes to 2376.0:                                          │
│ preferences.syncSystemPrice("XAUUSD", 2376.0, "mt5_file")           │
│                                                                        │
│ Internal state:                                                        │
│ _systemData.price = 2376.0    ← UPDATED                              │
│ _userReference.price = 2375.50 ← UNCHANGED                           │
│                                                                        │
│ When agent asks for price again:                                      │
│ getEffectivePrice("XAUUSD") → Still 2375.50                          │
│                                                                        │
│ ✅ NO SILENT OVERRIDE                                                 │
│ ✅ User's reference respected                                         │
│ ✅ System update logged for audit                                     │
│ ✅ If user unlocks: can access new system price                      │
└───────────────────────────────────────────────────────────────────────┘
```

## Price Lock Mechanism (Optional)

User can manually lock a price for a session:

```
POST /symbol/lock {
  canonical: "EURUSD",
  price: 1.0850,
  reason: "session_analysis",
  expiresIn_min: 60
}

Result:
_locked = {
  price: 1.0850,
  locked_until: Date.now() + 60*60*1000,
  lock_reason: "session_analysis"
}

getEffectivePrice("EURUSD") now returns 1.0850 (locked)
Even if MT5 changes, returns 1.0850
User cannot change until unlock expires
```

---

# C. STRUCTURE data-source-manager.js — LOCAL ONLY

## Module Purpose

Unified layer for fetching symbol data. All queries go through this.
LOCAL SOURCES ONLY (no Yahoo/Fixture in main flow).

## Core API

```javascript
// lib/data-source-manager.js

class DataSourceManager {
  
  /**
   * GET PRICE FOR SYMBOL
   * Only uses LOCAL sources:
   *   1. User preference (if registered & validated)
   *   2. MT5 local file
   *   3. Error if neither available
   * 
   * NO YAHOO, NO FIXTURE in main flow
   */
  async getPrice(canonical) {
    // Check user reference first
    const userRef = await preferences.getEffectivePrice(canonical);
    if (userRef && userRef.source !== "system") {
      return userRef;  // User-controlled price
    }
    
    // Fallback to system (MT5 file only)
    if (userRef && userRef.source === "system") {
      return userRef;
    }
    
    // Error: no local source
    throw new Error(`No local price source for ${canonical}`);
  }
  
  /**
   * GET FULL SYMBOL DATA (price + klines + indicators)
   * Still local only
   */
  async getSymbolData(canonical) {
    const price = await this.getPrice(canonical);
    
    // Get klines from MT5 file (only available for XAUUSD currently)
    const klines = await this.getKlines(canonical);
    
    return {
      canonical: canonical,
      price: price.effectivePrice,
      source: price.source,
      klines: klines || [],
      validation: {
        canAnalyze: !!price && price.source !== "system",
        confidence: this.getConfidence(price.source)
      }
    };
  }
  
  /**
   * GET KLINES (OHLCV bars)
   * Only from mt5_data.json (XAUUSD)
   */
  async getKlines(canonical, timeframe = "H1", limit = 20) {
    // For XAUUSD: read mt5_data.json
    // For others: return empty (until multi-symbol source available)
    
    if (canonical === "XAUUSD") {
      const data = readMT5FileSync(canonical);
      return data.klines.slice(0, limit);
    }
    
    return [];  // No klines for other symbols yet
  }
  
  /**
   * CAN ANALYZE?
   * Check if data is reliable enough for agent analysis
   */
  async canAnalyze(canonical) {
    try {
      const data = await this.getSymbolData(canonical);
      const isUserControlled = data.source !== "system";
      const hasKlines = data.klines && data.klines.length > 0;
      
      return {
        canAnalyze: isUserControlled || hasKlines,
        confidence: isUserControlled ? "high" : (hasKlines ? "medium" : "low"),
        reason: isUserControlled ? "User price registered" : "Using system data"
      };
    } catch (e) {
      return {
        canAnalyze: false,
        confidence: "none",
        reason: e.message
      };
    }
  }
  
  /**
   * LIST AVAILABLE SYMBOLS
   * What can we actually work with?
   */
  async listAvailableSymbols() {
    return [
      {
        canonical: "XAUUSD",
        hasSystemPrice: true,
        systemSource: "mt5_file",
        hasUserReference: await preferences.hasUserReference("XAUUSD"),
        canAnalyze: true
      },
      {
        canonical: "EURUSD",
        hasSystemPrice: false,
        systemSource: null,
        hasUserReference: await preferences.hasUserReference("EURUSD"),
        canAnalyze: await preferences.hasUserReference("EURUSD")  // Requires user input
      },
      // For any other symbol, user must register manually
    ];
  }
  
  /**
   * CONFIDENCE RATING
   */
  getConfidence(source) {
    if (source === "locked") return "very_high";
    if (source === "user_reference") return "high";
    if (source === "system") return "medium";
    return "low";
  }
}
```

---

# D. MULTI-SYMBOLES RÉEL — Phase 1 & 2

## Problem: Why Only XAUUSD Works

```
Right now:
- Code supports: XAUUSD, EURUSD, BTCUSD, US500, NAS100, etc.
- Data available: XAUUSD only (mt5_data.json)
- Result: Others require user manual input (or external API)
```

## Phase 1: Exploitable NOW (Local Only)

```
XAUUSD:
  ✅ MT5 file provides price + klines
  ✅ System price available immediately
  ✅ No user input needed
  ✅ Production ready: YES

EURUSD, BTCUSD, US500, etc:
  ❌ No system price (no MT5 data)
  ✅ User can register manually
  ✅ System remembers user price
  ✅ Agents use user price
  ✅ Production ready: YES (user-dependent)
```

## Phase 2: Better Sources (Future, Optional)

If activated later:

```
Option A: Extend MT5 EA
  Modify Bridge_MT5_Studio.mq5 to write multiple symbols
  mt5_data.json contains: XAUUSD, EURUSD, BTCUSD, etc.
  Timeline: 1-2 hours
  Cost: MT5 access needed

Option B: Activate MT5 Bridge Python
  Start: python mt5_bridge.py (port 5000)
  Bridge auto-discovers all MT5 symbols
  Timeline: 30 minutes setup
  Cost: None (already coded)

Result: All symbols have system prices + klines + indicators
```

## Matrix: What Works When

| Symbol | Phase 1 (TODAY) | Phase 2 (Later) | How Phase 1 Works |
|--------|-----------------|-----------------|-------------------|
| XAUUSD | ✅ System auto | ✅ System auto | MT5 file provides |
| EURUSD | ✅ User manual | ✅ System auto | User registers once |
| BTCUSD | ✅ User manual | ✅ System auto | User registers once |
| US500 | ✅ User manual | ✅ System auto | User registers once |
| Others | ✅ User manual | ✅ System auto | Infinitely scalable |

---

# E. ENDPOINTS REQUIRED

```javascript
// In server.js

// Get symbol reference (system proposal or user registered)
GET /symbol/reference/:canonical
  Response: { systemPrice, userReferencePrice, locked, validated }

// Register user price
POST /symbol/register-reference
  Body: { canonical, userPrice, validated }

// Validate price vs system
GET /symbol/validate/:canonical?price=2375.50
  Response: { ok, deltaPercent, message }

// Lock/unlock price for session
POST /symbol/lock
  Body: { canonical, price, reason, expiresIn_ms }

POST /symbol/unlock/:canonical

// List available symbols
GET /symbol/available
  Response: Array of { canonical, hasSystemPrice, canAnalyze }

// Get effective price (what agents should use)
GET /symbol/effective-price/:canonical
  Response: { effectivePrice, source, userControlled }
```

---

# F. VALIDATION QUESTIONS

1. ✅ **3 concepts clear?** systemPrice vs userReference vs locked
2. ✅ **Hierarchy correct?** locked > user_reference > system (never override)
3. ✅ **LOCAL ONLY?** No Yahoo/Fixture in main flow
4. ✅ **Phase 1 realistic?** User manual for others, automatic for XAUUSD
5. ✅ **Flow clear?** Selection → proposal → override → validation → registration → broadcast → usage
6. ✅ **User price protected?** MT5 update doesn't wipe user's reference

---

# NEXT STEPS (After Approval)

1. Create symbol-preferences.js (20 min)
2. Create data-source-manager.js (45 min)
3. Add endpoints to server.js (15 min)
4. Test end-to-end (30 min)
5. Then → alert-manager.js

