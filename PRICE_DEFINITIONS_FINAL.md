# 🔒 DÉFINITIONS PRÉCISES DES 3 PRIX

Status: **FINAL SPECIFICATION — Ready for validation**

---

# A. systemPrice — Définition Exacte

## Qu'est-ce que c'est?

Le prix remonté **AUTOMATIQUEMENT** par les sources locale.

```
Source: mt5_data.json (MT5 local)
Fraîcheur: Max ~2-4 secondes (temps de poll)
Historique: Oui (stocké dans klines)
Niveau: GLOBAL par symbole (pas de session/user spécifique)
Scope: Système entier
Persistance: Oui (reste après redémarrage)
```

## Cycle de Vie de systemPrice

```
┌─────────────────────────────────┐
│ MT5 EA écrit à mt5_data.json    │
│ XAUUSD price: 2375.30          │
│ timestamp: T0                   │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│ server.js poll toutes les 2s    │
│ Lit mt5_data.json               │
│ systemPrice = 2375.30           │
│ age = 2000ms                    │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│ market-store cache              │
│ XAUUSD.lastSystemPrice = 2375.30│
│ XAUUSD.lastSystemTimestamp = T0 │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│ Clients consultent via API      │
│ GET /symbol/reference/XAUUSD    │
│ → systemPrice: 2375.30          │
│ → age: 2000ms                   │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│ If systemPrice > 60s old:       │
│ ⚠️ WARNING: "Stale data"         │
│ Do NOT use for analysis         │
│ Require user reference instead  │
└─────────────────────────────────┘
```

## Propriétés de systemPrice

```javascript
{
  symbol: "XAUUSD",
  price: 2375.30,
  source: "mt5_file",           // Where it came from
  timestamp: 1712145600000,      // When fetched
  age_ms: 2000,                  // How old (now - timestamp)
  freshness_status: "fresh",     // fresh | stale | old | unusable
  is_live: true,                 // Has MT5 data
  has_klines: true,              // Has historique
  has_indicators: true           // Has analysis data
}
```

## Quand systemPrice Est Utilisé?

| Cas | Utilisé? | Notes |
|-----|----------|-------|
| Utilisateur n'a pas enregistré référence | ✅ OUI | Fallback system |
| Utilisateur a enregistré référence | ❌ NON | User ref prend le pas |
| Utilisateur a verrouillé prix | ❌ NON | Locked price prend le pas |
| Age < 60 secondes | ✅ Acceptable | Fresh enough |
| Age > 60 secondes | ⚠️ WARNING | Acceptable avec warning |
| Age > 5 minutes | ❌ NO | Trop vieux, ne pas utiliser |
| NO MT5 source (EURUSD) | ❌ NO | Null, n'utiliser pas |

---

# B. userReferencePrice — Définition Exacte

## Qu'est-ce que c'est?

Le prix que l'**UTILISATEUR** a enregistré comme référence de travail.

```
Créateur: Utilisateur manuel (via Studio UI)
Niveau: GLOBAL par symbole (partagé système entier)
Scope: Pas par session (persiste redémarrage)
Persistance: OUI (sauvegardé symbol-preferences.json)
Modifiable: OUI (utilisateur peut changer anytime)
Traçabilité: Complete (qui, quand, ancien prix, nouveau prix)
```

## Cycle de Vie de userReferencePrice

```
┌──────────────────────────────────┐
│ User selects GOLD in Studio UI  │
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ Symbol matcher: GOLD → XAUUSD   │
│ System proposes systemPrice:     │
│ 2375.30 (from MT5)               │
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ User sees UI:                    │
│ "System suggests: 2375.30"       │
│ Input field: [____]              │
│ User types: 2375.50              │
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ Real-time validation:            │
│ validate(2375.50 vs 2375.30)    │
│ → δ = 0.2, 0.0084% < 5% ✅     │
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ User clicks "Register Reference" │
│ POST /symbol/register-reference  │
│ {                                │
│   canonical: "XAUUSD",          │
│   userPrice: 2375.50,           │
│   systemPrice: 2375.30,         │
│   validated: true               │
│ }                                │
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ Backend: registerUserReference() │
│ Save to symbol-preferences.json: │
│ {                                │
│   "_userReference": {            │
│     price: 2375.50,              │
│     validated: true,             │
│     timestamp: T_registered,     │
│     systemPrice_at_time: 2375.30 │
│   }                              │
│ }                                │
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ Broadcast SSE to ALL clients:    │
│ type: "SYMBOL_REGISTERED"        │
│ userReferencePrice: 2375.50      │
│ source: "user_reference"         │
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ STAYS IN EFFECT until:           │
│ 1. User modifies it              │
│ 2. User clears it                │
│ 3. Never expires (global)        │
│                                  │
│ NEVER overridden by:             │
│ - systemPrice changing           │
│ - MT5 update                     │
│ - Server restart                 │
└──────────────────────────────────┘
```

## Propriétés de userReferencePrice

```javascript
{
  symbol: "XAUUSD",
  price: 2375.50,                    // User's chosen price
  validated: true,                   // User confirmed it
  created_at: 1712145600000,        // When registered
  system_price_at_registration: 2375.30, // Reference for audit
  delta_from_system: 0.2,
  delta_percent: 0.0084,
  modified_history: [
    {
      old_price: null,
      new_price: 2375.50,
      timestamp: 1712145600000,
      reason: "initial_registration"
    }
  ],
  locked: false  // Can be changed unless explicitly locked
}
```

## Quand userReferencePrice Est Utilisé?

| Cas | Utilisé? | Notes |
|-----|----------|-------|
| Utilisateur a enregistré référence | ✅ OUI | Priorité #1 |
| Utilisateur modifie (tape nouveau prix) | ✅ OUI | Update immédiat, nouveau prix |
| systemPrice change (MT5 update) | ❌ NON | userReference reste, systemPrice update seul |
| User clear preference | ❌ NON (anymore) | Fallback à systemPrice |
| Utilisateur verrouille prix | ❌ NON (overshadowed) | Locked price prend le pas |
| Redémarrage serveur | ✅ OUI | Rechargé de symbol-preferences.json |

## Modification de userReferencePrice

User peut modifier SANS verrouillage:

```
POST /symbol/update-reference {
  canonical: "XAUUSD",
  newPrice: 2375.60
}

Backend:
1. Valide (check tolerance vs systemPrice)
2. Sauvegarde old_price → history
3. Update price
4. Broadcast SSE
5. Agents reçoivent nouvelle valeur

History:
[
  { old: null, new: 2375.50, ts: T1, reason: "initial" },
  { old: 2375.50, new: 2375.60, ts: T2, reason: "user_update" }
]
```

## Annulation de userReferencePrice

User peut annuler (revert à systemPrice):

```
POST /symbol/clear-reference {
  canonical: "XAUUSD"
}

Backend:
1. Delete _userReference
2. Fall back to systemPrice
3. Broadcast: "User reference cleared for XAUUSD"
4. Agents now use systemPrice

History logged:
{ old: 2375.50, new: null, ts: T3, reason: "user_clear" }
```

---

# C. lockedPrice — Définition Exacte

## Qu'est-ce que c'est?

Un prix **GELÉ** pour une durée déterminée (session/analyse/position).

```
Créateur: Utilisateur (explicitement)
Niveau: GLOBAL par symbole
Scope: Pendant session/analyse (puis levé)
Duree: Fixe ou jusqu'à unlock manuel
Traçabilité: Complete (pourquoi, jusqu'à quand)
Priorité: ABSOLUE (override tout)
```

## Cycle de Vie de lockedPrice

```
┌────────────────────────────────────┐
│ User in middle of analysis         │
│ Current working price: 2375.50     │
│ (userReference or systemPrice)     │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│ User says: "Lock this price"       │
│ Reason: analysis, position, etc.   │
│ Duration: next 60 min (or manual)  │
│                                    │
│ POST /symbol/lock {               │
│   canonical: "XAUUSD",            │
│   price: 2375.50,                 │
│   reason: "active_analysis",      │
│   expiresIn_min: 60               │
│ }                                  │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│ Backend: lockPrice()               │
│ Save to symbol-preferences.json:   │
│ {                                  │
│   "_locked": {                     │
│     price: 2375.50,                │
│     locked_at: T_lock,             │
│     locked_until: T_lock + 60min,  │
│     lock_reason: "active_analysis",│
│     locked_by: "user"              │
│   }                                │
│ }                                  │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│ DURING LOCK (next 60 min):         │
│ getEffectivePrice() → 2375.50      │
│ Source: "locked"                   │
│                                    │
│ Even if:                           │
│ - MT5 price = 2376.0               │
│ - User tries to change reference   │
│ - systemPrice updates              │
│                                    │
│ Still returns: 2375.50 (locked)    │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│ AFTER 60 MIN expiry:               │
│ Automatic unlock                   │
│ lockedPrice = null                 │
│ Fall back to:                      │
│ 1. userReferencePrice (if exists)  │
│ 2. systemPrice (if not)            │
└──────────────┬─────────────────────┘
               ▼
┌────────────────────────────────────┐
│ OR: User manual unlock             │
│ POST /symbol/unlock/XAUUSD         │
│                                    │
│ Immediately:                       │
│ lockedPrice.price = null           │
│ Fall back to userReference/system  │
└────────────────────────────────────┘
```

## Propriétés de lockedPrice

```javascript
{
  symbol: "XAUUSD",
  price: 2375.50,                // Locked value (inviolable)
  locked_at: 1712145600000,      // When locked
  locked_until: 1712149200000,   // Expiry time (null = manual unlock)
  lock_reason: "active_analysis", // Why locked (for audit)
  locked_by: "user",             // Always user (not system)
  can_unlock_early: true,        // User can unlock anytime
  audit_reason: "Position open, need price stability"
}
```

## Quand lockedPrice Est Utilisée?

| Cas | Utilisé? | Notes |
|-----|----------|-------|
| Price est locked & not expired | ✅ OUI (ABSOLU) | Override user/system |
| Price est locked & EXPIRED | ❌ NON | Auto-unlock, fall back |
| User unlock manuellement | ❌ NON (anymore) | Fall back à user/system |
| MT5 price change | ❌ NO EFFECT | Locked price inviolable |
| User tries change reference | ❌ NO EFFECT | Locked price inviolable |
| Server restart | ✅ OUI | Locked state reloadé |

## Cas d'Usage de lockedPrice

```
Cas 1: Position actuelle
  - User has open position at 2375.50
  - Lock price pour durée position
  - Agents analysis use 2375.50
  - Even if MT5 shows 2376, agents stay at locked

Cas 2: Session d'analyse
  - User analyzing trades for 1 hour
  - Lock reference price pour session
  - All agents use same base price
  - After analysis done → unlock

Cas 3: Cohérence multi-symboles
  - Multiple symbols locked
  - All agents use locked prices
  - Consistent analysis across symbols
```

---

# D. CHART: Quel Prix Pour Quel Cas?

## Effective Price Hierarchy

```
Agent demande: getEffectivePrice("XAUUSD")

Check 1: Est-ce lockedPrice non-expiré?
  ✅ YES → return locked price
     { effectivePrice: 2375.50, source: "locked", ... }
  ❌ NO → continue

Check 2: Est-ce userReferencePrice enregistrée?
  ✅ YES → return user reference
     { effectivePrice: 2375.50, source: "user_reference", ... }
  ❌ NO → continue

Check 3: Existe-t-il systemPrice fiable?
  ✅ YES → return system price
     { effectivePrice: 2375.30, source: "system", warning: "No user reference set" }
  ❌ NO → ERROR
     throw Error("No price available for XAUUSD")
```

## Matrix: Agents Use Which Price?

```
Symbol: XAUUSD

Scenario 1: User lockée, userRef exist, MT5 live
  getEffectivePrice() → 2375.50 (locked)
  source: "locked"
  why: Locked takes absolute priority

Scenario 2: User ref exists, NO lock, MT5 has price
  getEffectivePrice() → 2375.50 (user ref)
  source: "user_reference"
  why: User ref has priority over system

Scenario 3: NO user ref, NO lock, MT5 live
  getEffectivePrice() → 2375.30 (system)
  source: "system"
  why: System is fallback when no user choice

Scenario 4: NO user ref, LOCK expired, MT5 live
  getEffectivePrice() → 2375.30 (system)
  source: "system"
  why: Lock expired, no user ref, use system

Scenario 5: NO user ref, NO MT5 (EURUSD)
  getEffectivePrice() → ERROR
  source: null
  why: No source available, user must register reference

Symbol: EURUSD (no MT5 data)

Scenario 1: User registered reference only
  getEffectivePrice() → 1.0850 (user ref)
  source: "user_reference"
  why: Only option available

Scenario 2: User registered + locked
  getEffectivePrice() → 1.0850 (locked)
  source: "locked"
  why: Locked override user ref
```

---

# E. TRAÇABILITÉ DANS LA DONNÉE (CRITICAL)

## Quand Agent Travaille, Doit Indiquer Source

```javascript
// When orchestrator.run() calls for price:

const priceData = await preferences.getEffectivePrice("XAUUSD");

// Result ALWAYS includes:
{
  effectivePrice: 2375.50,
  source: "locked" | "user_reference" | "system",
  sourceDetails: {
    locked: true/false,
    paid_by_user: true/false (if user_reference),
    system_price_at_time: 2375.30,
    age_ms: 2000
  },
  timestamp: Date.now()
}

// Agent analysis MUST include this in output:
{
  symbol: "XAUUSD",
  priceSource: priceData.source,
  priceDetails: priceData,
  analysis: { ... },
  alert: {
    signal: "BUY",
    entryPrice: priceData.effectivePrice,
    priceBasis: priceData.source,
    __AUDIT__: "Price basis: user_reference @ 2375.50 (locked until 14:00)"
  }
}

// In storage (agent-log, history):
{
  timestamp: "2026-04-03T12:30:00Z",
  symbol: "XAUUSD",
  priceUsed: 2375.50,
  priceSource: "locked",
  priceBasis: {
    locked: { price: 2375.50, until: "2026-04-03T13:30:00Z" }
  },
  analysis: { ... },
  alert: { ... }
}
```

## Audit Trail Example

```json
{
  "symbol": "XAUUSD",
  "session": "2026-04-03T12:00:00Z",
  "price_history": [
    {
      "timestamp": "2026-04-03T12:05:00Z",
      "type": "user_reference",
      "price": 2375.50,
      "action": "registered",
      "system_price_at_time": 2375.30
    },
    {
      "timestamp": "2026-04-03T12:10:00Z",
      "type": "locked",
      "price": 2375.50,
      "action": "locked",
      "until": "2026-04-03T13:10:00Z",
      "reason": "active_trading_session"
    },
    {
      "timestamp": "2026-04-03T12:15:00Z",
      "type": "system",
      "price": 2376.00,
      "action": "updated",
      "status": "ignored (locked price in effect)"
    }
  ],
  "agent_calls": [
    {
      "timestamp": "2026-04-03T12:20:00Z",
      "agent": "momentum-analyzer",
      "price_requested": "getEffectivePrice(XAUUSD)",
      "price_returned": 2375.50,
      "source": "locked",
      "analysis": { "signal": "HOLD", "confidence": 0.75 }
    }
  ]
}
```

---

# F. TRANSITIONS ENTRE LES PRIX

## Timeline Exemple

```
T0: User selects GOLD
    systemPrice: 2375.30 (from MT5)
    userReferencePrice: null
    lockedPrice: null
    effectivePrice: 2375.30 (system)

T1: User registers reference @ 2375.50
    systemPrice: 2375.30
    userReferencePrice: 2375.50 ← NEW
    lockedPrice: null
    effectivePrice: 2375.50 (user_ref)

T2: MT5 updates to 2376.0
    systemPrice: 2376.0 ← UPDATED
    userReferencePrice: 2375.50 (UNCHANGED)
    lockedPrice: null
    effectivePrice: 2375.50 (user_ref, NOT 2376!)

T3: User locks price for session
    systemPrice: 2376.0
    userReferencePrice: 2375.50
    lockedPrice: 2375.50 ← NEW
    effectivePrice: 2375.50 (locked, ABSOLUTE)

T4: Lock expires (after 60 min)
    systemPrice: 2376.0
    userReferencePrice: 2375.50
    lockedPrice: null (expired) ← CLEARED
    effectivePrice: 2375.50 (user_ref, back to this)

T5: User modifies reference to 2376.50
    systemPrice: 2376.0
    userReferencePrice: 2376.50 ← UPDATED
    lockedPrice: null
    effectivePrice: 2376.50 (user_ref)

T6: User clears reference
    systemPrice: 2376.0
    userReferencePrice: null ← CLEARED
    lockedPrice: null
    effectivePrice: 2376.0 (system, fallback)

T7: Server restart
    All states reloaded from symbol-preferences.json
    (preserves userRef & locked settings)
```

---

# SUMMARY: BEFORE IMPLEMENTATION

These are the exact definitions:

1. **systemPrice**: Auto-updated from MT5, max 60s old, fallback only
2. **userReferencePrice**: User-registered, persistent, never silently overridden
3. **lockedPrice**: Session-scoped, time-limited, absolute priority

Hierarchy: locked > user_ref > system

Every agent action MUST report which price was used (audit trail).

---

Ready for validation?
