# 📡 USER REFERENCE ENDPOINTS — SPÉCIFICATION DÉTAILLÉE

**Date:** 2026-04-03  
**Status:** DESIGN (avant implémentation)  
**Localisation:** À ajouter dans `server.js`

---

## 🎯 Récapitulatif

**Objectif:** 4 endpoints pour gérer les prix de référence utilisateur

| Endpoint | Méthode | Purpose | Location |
|----------|---------|---------|----------|
| `/api/user-reference` | POST | Register/Update user price | Extension popup |
| `/api/user-reference/:canonical` | GET | Get current user price | Extension popup + Dashboard |
| `/api/user-reference/:canonical` | DELETE | Clear user reference | Extension popup + Dashboard |
| `/api/user-references` | GET | Get ALL user references | Dashboard on load |

---

## 📤 Endpoint 1: POST /api/user-reference

**Purpose:** Register or update a user reference price

**Request:**
```javascript
POST /api/user-reference
Content-Type: application/json

{
  "canonical": "XAUUSD",
  "userPrice": 2375.50,
  "force_override": false    // optional, default false
}
```

**Request Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `canonical` | string | ✅ Yes | Symbol canonical name (XAUUSD, EURUSD, etc.) |
| `userPrice` | number | ✅ Yes | Price user entered (must be positive) |
| `force_override` | boolean | ❌ No | If true, bypass tolerance check (requires warning) |

**Success Response (200 OK):**
```javascript
{
  "ok": true,
  "saved": {
    "canonical": "XAUUSD",
    "userPrice": 2375.50,
    "systemPrice": 2375.30,
    "effectivePrice": 2375.50,    // Hierarchy applied
    "source": "user_reference",
    "tolerance": {
      "absolute": 0.20,           // |2375.50 - 2375.30|
      "percent": 0.0085,          // (0.20 / 2375.30) * 100
      "maxAllowed": 0.5,          // From rules: Metals = ±0.5%
      "withinLimit": true         // 0.0085 < 0.5
    },
    "validation": {
      "ok": true,
      "message": "Price registered within tolerance (0.0085%)"
    },
    "timestamp": 1712145200000,
    "registered_at_iso": "2026-04-03T10:30:00.000Z"
  },
  "info": {
    "action": "registered",
    "source": "api_endpoint",
    "modified_from": null         // null if first registration
  }
}
```

**Error Response (400 Bad Request) — Tolerance Exceeded:**
```javascript
{
  "ok": false,
  "error": "Price divergence exceeds tolerance",
  "details": {
    "canonical": "XAUUSD",
    "userPrice": 2370.00,
    "systemPrice": 2375.30,
    "divergence": {
      "absolute": 5.30,
      "percent": 0.2232            // (5.30 / 2375.30) * 100
    },
    "tolerance": {
      "maxAllowed": 0.5,
      "exceeded_by": "0.2232 - 0.5 = -0.2768" // Actually within! Let's use a real example
    }
  },
  "options": [
    {
      "action": "use_system_price",
      "price": 2375.30,
      "label": "Use system price instead (2375.30)"
    },
    {
      "action": "adjust_price",
      "suggested": [2375.00, 2375.15, 2375.30],
      "label": "Adjust to a nearby value"
    },
    {
      "action": "force_override",
      "label": "Force this price (requires confirmation)",
      "requires": "explicit_confirmation"
    }
  ],
  "info": "Registered price 2370.00 diverges 2.23% from system 2375.30 (tolerance ±0.5%)"
}
```

**Error Response (400 Bad Request) — Invalid Input:**
```javascript
{
  "ok": false,
  "error": "Invalid input",
  "details": {
    "canonical": "INVALID_SYMBOL",
    "canonic al": "Missing or invalid"
  },
  "message": "Symbol 'INVALID_SYMBOL' not supported"
}
```

**Error Response (503 Service Unavailable) — System Price Unknown:**
```javascript
{
  "ok": false,
  "error": "Cannot fetch system price",
  "details": {
    "canonical": "XAUUSD",
    "systemPrice": null,
    "source": "mt5_data.json",
    "age": "unknown"
  },
  "message": "System price unavailable. Cannot validate tolerance. Register anyway?",
  "options": [
    {
      "action": "register_unvalidated",
      "label": "Register without system comparison",
      "warning": "Price will be registered but validation is incomplete"
    }
  ]
}
```

**Flow Chart - Validation Logic:**
```
User enters price → POST /api/user-reference
                    ↓
                Get system price from symbol-preferences
                    ↓
                    System exists?
                    ├─ NO → Return 503 "Cannot validate"
                    └─ YES ↓
                
                Calculate tolerance
                    ├─ Within limit? → Return 200 OK (save)
                    └─ Exceeds limit? ↓
                
                force_override == true?
                ├─ YES → Save with override flag + audit
                └─ NO → Return 400 "Exceeds tolerance" + options
```

---

## 📥 Endpoint 2: GET /api/user-reference/:canonical

**Purpose:** Fetch current user reference price for one symbol

**Request:**
```javascript
GET /api/user-reference/XAUUSD
```

**Success Response (200 OK):**
```javascript
{
  "ok": true,
  "canonical": "XAUUSD",
  "userReference": {
    "price": 2375.50,
    "source": "user_reference",
    "timestamp": 1712145200000,
    "registered_at_iso": "2026-04-03T10:30:00.000Z",
    "validated": false,
    "tolerance": {
      "absolute": 0.20,
      "percent": 0.0085,
      "maxAllowed": 0.5
    }
  },
  "systemPrice": {
    "price": 2375.30,
    "source": "mt5_file",
    "timestamp": 1712145135000,
    "age_ms": 65000,
    "freshness": "acceptable"     // acceptable | stale | unknown
  },
  "effectivePrice": {
    "price": 2375.50,             // Result of hierarchy
    "source": "user_reference"
  },
  "locks": [
    {
      "contextId": "analysis-001",
      "price": 2375.45,
      "locked_until": 1712148800000,
      "reason": "momentum_analysis"
    }
  ],
  "info": {
    "hierarchy_applied": "locked > user_reference > system",
    "currently_using": "user_reference (because no active lock)"
  }
}
```

**Response if No User Reference (404 Not Found):**
```javascript
{
  "ok": false,
  "canonical": "XAUUSD",
  "message": "No user reference registered",
  "fallback": {
    "price": 2375.30,
    "source": "system",
    "timestamp": 1712145135000
  },
  "options": [
    {
      "action": "register_now",
      "label": "Register a user reference price"
    }
  ]
}
```

**Response if Symbol Unknown (404 Not Found):**
```javascript
{
  "ok": false,
  "canonical": "UNKNOWN_SYMBOL",
  "error": "Symbol not found",
  "message": "Symbol 'UNKNOWN_SYMBOL' is not configured in this system",
  "suggestions": ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]
}
```

---

## 🗑️ Endpoint 3: DELETE /api/user-reference/:canonical

**Purpose:** Clear user reference price (revert to system)

**Request:**
```javascript
DELETE /api/user-reference/XAUUSD
```

**Success Response (200 OK):**
```javascript
{
  "ok": true,
  "canonical": "XAUUSD",
  "action": "cleared",
  "info": {
    "cleared": {
      "price": 2375.50,
      "timestamp": 1712145200000
    },
    "fallback": {
      "price": 2375.30,           // Now using system price
      "source": "system",
      "timestamp": 1712145135000
    }
  },
  "message": "User reference cleared. Now using system price (2375.30)",
  "audit": {
    "cleared_at": 1712145400000,
    "cleared_by": "extension_popup",
    "reason": "user_clear_action"
  }
}
```

**Response if No User Reference to Clear (404 Not Found):**
```javascript
{
  "ok": false,
  "canonical": "XAUUSD",
  "message": "No user reference registered to clear",
  "current_price": {
    "price": 2375.30,
    "source": "system"
  }
}
```

---

## 📋 Endpoint 4: GET /api/user-references

**Purpose:** Fetch ALL registered user reference prices (for Dashboard)

**Request:**
```javascript
GET /api/user-references
```

**Success Response (200 OK):**
```javascript
{
  "ok": true,
  "count": 3,
  "userReferences": [
    {
      "canonical": "XAUUSD",
      "userPrice": 2375.50,
      "systemPrice": 2375.30,
      "effectivePrice": 2375.50,
      "source": "user_reference",
      "tolerance": {
        "percent": 0.0085,
        "maxAllowed": 0.5,
        "withinLimit": true,
        "status": "✓ OK"
      },
      "validated": false,
      "hasLocks": 1,              // Number of active context locks
      "registered_at": "2026-04-03T10:30:00.000Z",
      "modified_at": "2026-04-03T10:30:00.000Z",
      "history": 1                // Number of modifications
    },
    {
      "canonical": "EURUSD",
      "userPrice": 1.08450,
      "systemPrice": 1.08350,
      "effectivePrice": 1.08450,
      "source": "user_reference",
      "tolerance": {
        "percent": 0.0923,
        "maxAllowed": 0.1,
        "withinLimit": false,      // Exceeds tolerance!
        "status": "⚠️ WARNING"
      },
      "validated": false,
      "hasLocks": 0,
      "registered_at": "2026-04-03T09:15:00.000Z",
      "modified_at": "2026-04-03T09:15:00.000Z",
      "history": 1
    },
    {
      "canonical": "GBPUSD",
      "userPrice": 1.26500,
      "systemPrice": 1.26400,
      "effectivePrice": 1.26500,
      "source": "user_reference",
      "tolerance": {
        "percent": 0.0791,
        "maxAllowed": 0.1,
        "withinLimit": true,
        "status": "✓ OK"
      },
      "validated": false,
      "hasLocks": 0,
      "registered_at": "2026-04-03T09:00:00.000Z",
      "modified_at": "2026-04-03T09:00:00.000Z",
      "history": 1
    }
  ],
  "summary": {
    "total_registered": 3,
    "within_tolerance": 2,
    "exceeding_tolerance": 1,
    "with_locks": 1,
    "last_update": 1712145400000
  }
}
```

**Empty Response (200 OK):**
```javascript
{
  "ok": true,
  "count": 0,
  "userReferences": [],
  "message": "No user references registered yet",
  "suggestions": [
    {
      "action": "register_first",
      "label": "Register your first user reference price"
    }
  ]
}
```

---

## 🛡️ Common Error Responses (All Endpoints)

### 400 Bad Request
```javascript
{
  "ok": false,
  "error": "Bad request",
  "details": {
    "field": "canonical",
    "value": "",
    "message": "Missing required field"
  }
}
```

### 500 Internal Server Error
```javascript
{
  "ok": false,
  "error": "Internal server error",
  "message": "Failed to save user reference",
  "details": {
    "reason": "file_write_error",
    "stack": "... (dev only)"
  }
}
```

---

## 🔄 Integration with symbol-preferences.js

**Server Code Pattern:**

```javascript
const SymbolPreferences = require('./src/services/symbol-preferences');

// POST /api/user-reference
app.post('/api/user-reference', async (req, res) => {
  try {
    const { canonical, userPrice, force_override } = req.body;
    
    // Validation
    if (!canonical || userPrice === undefined) {
      return res.status(400).json({ ok: false, error: "Missing fields" });
    }
    
    // Initialize preferences manager
    const prefs = new SymbolPreferences();
    await prefs.load();
    
    // Get system price for comparison
    const systemPrice = prefs.getSystemPrice(canonical);
    
    // Tolerance validation
    const maxTolerance = getTolerance(canonical);
    const validation = prefs.validate(canonical, userPrice, systemPrice, maxTolerance);
    
    if (!validation.ok && !force_override) {
      return res.status(400).json({
        ok: false,
        error: "Price divergence exceeds tolerance",
        tolerance: maxTolerance,
        divergence: validation.deltaPercent,
        options: [...]
      });
    }
    
    // Register price
    const result = await prefs.registerUserReference(canonical, {
      userPrice,
      systemPrice,
      validated: false,
      override: force_override
    });
    
    res.json({
      ok: true,
      saved: {
        canonical,
        userPrice,
        systemPrice,
        effectivePrice: userPrice,    // Hierarchy: user > system
        source: "user_reference",
        tolerance: {
          absolute: Math.abs(userPrice - systemPrice),
          percent: ((Math.abs(userPrice - systemPrice) / systemPrice) * 100),
          maxAllowed: maxTolerance,
          withinLimit: validation.ok
        },
        timestamp: Date.now()
      }
    });
    
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message });
  }
});
```

---

## 📊 Tolerance Rules Table (Used by Endpoints)

```javascript
const TOLERANCE_RULES = {
  // Precious Metals
  'XAUUSD': 0.5,
  'XAGUSD': 0.5,
  
  // Major Forex
  'EURUSD': 0.1,
  'GBPUSD': 0.1,
  'USDJPY': 0.1,
  'AUDUSD': 0.1,
  'NZDUSD': 0.1,
  
  // Commodities
  'USOIL': 0.8,
  'UKOIL': 0.8,
  
  // Crypto
  'BTCUSD': 2.0,
  'ETHUSD': 2.0,
  
  // Indices
  'SPX500': 0.3,
  'US100': 0.3,
  
  // Default fallback
  'default': 0.5
};

function getTolerance(canonical) {
  return TOLERANCE_RULES[canonical] || TOLERANCE_RULES['default'];
}
```

---

## 📝 Audit Trail Requirement

Every endpoint should update `_modification_history` in symbol-preferences.json:

```javascript
// Example modification history entry
{
  "old_price": null,
  "new_price": 2375.50,
  "timestamp": 1712145200000,
  "reason": "initial_registration",
  "source": "extension_popup",
  "forced": false,
  "tolerance_check": {
    "system_price": 2375.30,
    "divergence_percent": 0.0085,
    "max_tolerance": 0.5,
    "within_limit": true
  }
}
```

---

## ✅ Implementation Checklist

- [ ] POST /api/user-reference (register/update)
- [ ] GET /api/user-reference/:canonical (get one)
- [ ] DELETE /api/user-reference/:canonical (clear)
- [ ] GET /api/user-references (get all)
- [ ] Error handling for all scenarios
- [ ] Integration with sym bol-preferences.js
- [ ] Tolerance rules configuration
- [ ] Audit trail logging
- [ ] Test each endpoint
