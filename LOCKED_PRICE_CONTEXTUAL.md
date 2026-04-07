# 🔒 LOCKED PRICE — CLARIFICATION FINALE

Status: **CRITICAL SPECIFICATION — Last point before coding**

---

# Le Problème Avec Ma Proposition Initiale

❌ J'avais proposé: UN seul lockedPrice par symbole

```
XAUUSD: {
  _locked: {
    price: 2375.50,
    locked_until: T
  }
}
```

**Problème**: Si un contexte (analyse A) verrouille XAUUSD à 2375.50, et qu'un autre contexte (analyse B) veut travailler avec 2375.60, c'est foutu. Contamination.

---

# LA SOLUTION: lockedPrice CONTEXTUEL

✅ lockedPrice DOIT être lié à UN contexte spécifique:

```
XAUUSD: {
  _locks: {
    "analysis-20260403-001": {
      price: 2375.50,
      locked_at: 1712145600000,
      locked_until: 1712149200000,
      lock_reason: "momentum_analysis_session",
      context_type: "analysis",
      context_id: "analysis-20260403-001"
    },
    
    "position-GOLD-001": {
      price: 2376.00,
      locked_at: 1712140000000,
      locked_until: 1712150000000,
      lock_reason: "active_position_hedge",
      context_type: "position",
      context_id: "position-GOLD-001"
    },
    
    "session-trader-morning": {
      price: 2375.80,
      locked_at: 1712130000000,
      locked_until: 1712152000000,
      lock_reason: "trading_session_locked_prices",
      context_type: "session",
      context_id: "session-trader-morning"
    }
  }
}
```

**Result**: 3 verrous DIFFÉRENTS sur XAUUSD, chacun indépendant. Aucune contamination.

---

# Structure Exacte de lockedPrice

## Key Format

```
Key: `${symbol}:${contextId}`
Example: "XAUUSD:analysis-20260403-001"
Example: "XAUUSD:position-TRADE-XYZ"
Example: "XAUUSD:session-morning-session"

Context Types:
- "analysis": Lié à une analyse spécifique
- "position": Lié à une position actuelle
- "session": Lié à une session de trading
- "custom": Autres usages
```

## Properties

```javascript
{
  symbol: "XAUUSD",
  context_type: "analysis" | "position" | "session" | "custom",
  context_id: "unique-identifier-123",
  price: 2375.50,
  locked_at: 1712145600000,
  locked_until: 1712149200000,  // null = manual unlock needed
  lock_reason: "momentum_analysis_session",  // Human-readable
  created_by: "user",  // Always user for now
  
  // For audit
  is_active: true,
  is_expired: false,
  time_remaining_ms: 3600000,
  
  // Metadata
  analysis_details: {
    signal: "BUY",
    confidence: 0.75
  } | null,
  position_details: {
    symbol: "XAUUSD",
    volume: 1.0,
    direction: "LONG"
  } | null
}
```

---

# getEffectivePrice() — CONTEXTUAL

## Signature

```javascript
async getEffectivePrice(canonical, contextId = null) {
  // If contextId provided, check context-specific lock first
  if (contextId) {
    const contextLock = await this.getContextLock(canonical, contextId);
    if (contextLock && !contextLock.is_expired) {
      return {
        effectivePrice: contextLock.price,
        source: "locked",
        context_type: contextLock.context_type,
        context_id: contextId,
        lock_reason: contextLock.lock_reason
      };
    }
  }
  
  // Fall back to userReferencePrice
  if (userRef && userRef.validated) {
    return {
      effectivePrice: userRef.price,
      source: "user_reference",
      context_type: null,
      context_id: null
    };
  }
  
  // Fall back to systemPrice
  if (systemPrice && fresh) {
    return {
      effectivePrice: systemPrice.price,
      source: "system",
      context_type: null,
      context_id: null
    };
  }
  
  throw Error("No price available");
}
```

## Usage

```javascript
// Case 1: Agent analysis with context
const analysisId = "analysis-20260403-001";
const price = await preferences.getEffectivePrice("XAUUSD", analysisId);
// If lock exists for this analysis → use it
// Otherwise → use userRef/system

// Case 2: Agent trading (no specific context)
const price = await preferences.getEffectivePrice("XAUUSD", null);
// Always uses userRef or system (no context-specific locks)

// Case 3: Position hedge
const positionId = "position-TRADE-XYZ";
const price = await preferences.getEffectivePrice("XAUUSD", positionId);
// If lock for this position → use it
// Otherwise → use userRef/system
```

---

# Comment Éviter Contamination

## Scenario: 2 Analyses en Même Temps

**Analyse A** (momentum):
```
symbol: XAUUSD
analysisId: "analysis-momentum-001"
locked_price: 2375.50
locked_until: 14:30
lock_reason: "Momentum analysis, stable base"
```

**Analyse B** (trend):
```
symbol: XAUUSD
analysisId: "analysis-trend-001"
locked_price: 2375.80
locked_until: 15:00
lock_reason: "Trend analysis, different base"
```

**Isolation**:
```
Locks stored as:
  "XAUUSD:analysis-momentum-001" → 2375.50
  "XAUUSD:analysis-trend-001" → 2375.80

Agent A queries: getEffectivePrice("XAUUSD", "analysis-momentum-001")
  → Returns 2375.50 (context-specific lock)

Agent B queries: getEffectivePrice("XAUUSD", "analysis-trend-001")
  → Returns 2375.80 (context-specific lock)

Agent C queries: getEffectivePrice("XAUUSD", null)  // No context
  → Returns userReferencePrice or systemPrice (no locks)

ZERO CONTAMINATION ✅
```

---

# Clé Unique Pour Le Verrou

## Format

```
Primary Key: `${symbol}:${contextId}`

contextId = unique identifier for context

Examples:
  - "XAUUSD:analysis-UUID"
  - "XAUUSD:position-12345"
  - "XAUUSD:session-morning-2026-04-03"
  - "XAUUSD:custom-context-XYZ"

Generation:
  analysisId = `analysis-${uuid()}` or `analysis-${timestamp}-${analysisName}`
  positionId = `position-${ticket}` or `position-UUID`
  sessionId = `session-${sessionName}-${date}` or `session-UUID`
```

## Storage Structure

```javascript
// In symbol-preferences.json
{
  preferences: {
    XAUUSD: {
      _systemData: { ... },
      _userReference: { ... },
      _locks: {
        "analysis-uuid-1": { price, until, reason, ... },
        "analysis-uuid-2": { price, until, reason, ... },
        "position-ticket-123": { price, until, reason, ... }
        // Multiple locks can coexist
      }
    }
  }
}
```

## Query Method

```javascript
async getContextLock(canonical, contextId) {
  const locks = await this.get(canonical)._locks;
  return locks[`${canonical}:${contextId}`];
  // or just: return locks[contextId], depends on nesting
}

async setContextLock(canonical, contextId, lockData) {
  const pref = await this.get(canonical);
  if (!pref._locks) pref._locks = {};
  pref._locks[contextId] = {
    price: lockData.price,
    locked_at: Date.now(),
    locked_until: lockData.locked_until,
    lock_reason: lockData.lock_reason,
    context_type: lockData.context_type,
    context_id: contextId
  };
  await this.save();
}

async clearContextLock(canonical, contextId) {
  const pref = await this.get(canonical);
  delete pref._locks[contextId];
  await this.save();
}

async getAllContextLocks(canonical) {
  const pref = await this.get(canonical);
  return pref._locks || {};
}
```

---

# AGENT AUDIT TRAIL

## What Agent Must Report

```javascript
{
  symbol: "XAUUSD",
  
  // Price source (MANDATORY)
  priceSource: {
    type: "locked" | "user_reference" | "system",
    value: 2375.50,
    context_type: "analysis" | "position" | "session" | null,
    context_id: "analysis-20260403-001" | null,
    timestamp: 1712145600000,
    age_ms: 2000,
    lock_reason: "momentum_analysis_session" | null,
    locked_until: 1712149200000 | null
  },
  
  // Analysis
  analysis: {
    signal: "BUY",
    confidence: 0.75,
    reasoning: "..."
  },
  
  // Alert (if any)
  alert: {
    type: "BUY_SIGNAL",
    entry_price: 2375.50,
    ...
  }
}
```

## Storage Example

```json
{
  "timestamp": "2026-04-03T12:30:00Z",
  "symbol": "XAUUSD",
  "context": {
    "type": "analysis",
    "id": "analysis-momentum-001"
  },
  "priceUsed": 2375.50,
  "priceSource": "locked",
  "priceDetails": {
    "type": "locked",
    "value": 2375.50,
    "context_id": "analysis-momentum-001",
    "context_type": "analysis",
    "locked_until": "2026-04-03T13:30:00Z",
    "lock_reason": "momentum_analysis_session"
  },
  "analysis": {
    "signal": "BUY",
    "confidence": 0.75
  },
  "alert": {
    "type": "BUY_SIGNAL",
    "entry_price": 2375.50,
    "basis": "Price locked for analysis momentum-001"
  }
}
```

---

# SUMMARY: 4 QUESTIONS ANSWERED

### 1. Est-ce que lockedPrice est global ou contextuel?

**CONTEXTUEL**
- Lié à un analyse/position/session spécifique
- Pas global par symbole
- Peut avoir plusieurs verrous simultanés sur même symbole
- Aucune contamination

### 2. Si contextuel, quelle est sa structure exacte?

```javascript
{
  symbol: "XAUUSD",
  context_type: "analysis" | "position" | "session",
  context_id: "unique-identifier-123",
  price: 2375.50,
  locked_at: timestamp,
  locked_until: timestamp,
  lock_reason: "human-readable-reason"
}
```

### 3. Comment évites-tu qu'un verrou contamine un autre contexte?

**Key = `${symbol}:${contextId}`**

Chaque contexte a sa propre clé. Pas de collision possible.

```
XAUUSD:analysis-001 → 2375.50
XAUUSD:analysis-002 → 2375.80
XAUUSD:position-XYZ → 2376.00
```

Chacun totalement indépendant.

### 4. Quelle clé unique utilises-tu pour le verrou?

**`${symbol}:${contextId}`**

Où contextId peut être:
- `analysis-${uuid}` ou `analysis-${timestamp}-${name}`
- `position-${ticket}` ou `position-${uuid}`
- `session-${sessionName}-${date}` ou `session-${uuid}`
- `custom-${identifier}`

---

# HIERARCHY UPDATE (Avec Contexte)

```javascript
async getEffectivePrice(canonical, contextId = null) {
  
  // Priority 1: Context-specific lock (if context provided)
  if (contextId) {
    const lock = await getContextLock(canonical, contextId);
    if (lock && !lock.is_expired) {
      return { effectivePrice: lock.price, source: "locked", context_id: contextId };
    }
  }
  
  // Priority 2: User reference (global, always available if set)
  if (userRef && userRef.validated) {
    return { effectivePrice: userRef.price, source: "user_reference" };
  }
  
  // Priority 3: System price (fallback)
  if (systemPrice && systemPrice.fresh) {
    return { effectivePrice: systemPrice.price, source: "system" };
  }
  
  // No price available
  throw Error("No price available");
}
```

---

# READY FOR FINAL VALIDATION

✅ lockedPrice is CONTEXTUAL, not global
✅ Structure includes context_id, context_type, lock_reason
✅ NO CONTAMINATION between contexts
✅ Unique key prevents collisions
✅ Agent MUST report context when using locked price
✅ Full audit trail with context info

Ready to code?
