# 📊 User Reference Price Registration — Complete Analysis

**Date:** 2026-04-03  
**Status:** ANALYSIS PHASE (before implementation)  
**Scope:** Manual price registration feature through extension

---

## 🎯 Feature Goal

Allow users to **manually register reference prices** for symbols via the extension popup, stored persistently and used in the price hierarchy instead of live MT5 prices.

**Example Workflow:**
```
User opens extension popup
  ↓
Enters: XAUUSD = 2375.50 (manual reference)
  ↓
POST /api/user-reference with {symbol, userPrice}
  ↓
Server calls symbol-preferences.registerUserReference(XAUUSD, {userPrice: 2375.50})
  ↓
Saved to store/symbol-preferences.json (persisted)
  ↓
Agent queries getEffectivePrice(XAUUSD) → returns 2375.50 (user ref, not system)
  ↓
Dashboard shows: "Using user reference price 2375.50"
```

---

## ✅ What Already Exists

### File 1: symbol-preferences.js (COMPLETE)
**Location:** `src/services/symbol-preferences.js`  
**Status:** ✅ Fully implemented  
**Key Methods for User References:**

```javascript
// REGISTER user price for first time
async registerUserReference(canonical, {
  userPrice,      // Price user entered (e.g., 2375.50)
  systemPrice,    // Current system price (e.g., 2375.30 from MT5)
  validated = false
})
// → Stores in _userReference.price with tolerance calculated

// UPDATE existing user reference
async updateUserReference(canonical, newPrice)
// → Modifies price + maintains modification_history

// CLEAR user reference (revert to system)
async clearUserReference(canonical)
// → Removes user price, hierarchy falls back to system price

// GET ALL user references
async getAllUserReferences()
// → Returns { canonical, userPrice, systemPrice, locked, validated, timestamp }

// VALIDATE user price vs system
validate(canonical, userPrice, systemPrice, maxTolerance_percent = 5.0)
// → Shows {ok, deltaPercent, message, canUse: true}
```

**Data Structure Stored (in symbol-preferences.json):**
```json
{
  "preferences": {
    "XAUUSD": {
      "_systemData": {
        "price": 2375.30,
        "source": "mt5_file",
        "timestamp": 1712145135000,
        "age_ms": 2000,
        "reliable": true
      },
      "_userReference": {
        "price": 2375.50,
        "validated": false,
        "timestamp": 1712145200000,
        "tolerance_absolute": 0.20,
        "tolerance_percent": 0.0085,
        "variants": [],
        "system_price_at_registration": 2375.30
      },
      "_locks": {},
      "_modification_history": [
        {
          "old_price": null,
          "new_price": 2375.50,
          "timestamp": 1712145200000,
          "reason": "initial_registration"
        }
      ],
      "_lock_history": [],
      "_price_update_history": []
    }
  },
  "metadata": {
    "lastUpdated": 1712145200000,
    "version": "2.0"
  }
}
```

### File 2: data-source-manager.js (INTEGRATED)
**Location:** `lib/data-source-manager.js`  
**Status:** ✅ Fully integrated with symbol-preferences  
**Key Point:**

```javascript
async getEffectivePrice(canonical, contextId = null) {
  // CRITICAL: This method already delegates to symbol-preferences
  const priceData = await this.preferences.getEffectivePrice(canonical, contextId);
  // Already respects hierarchy: locked > user_reference > system
}
```

**Result:** When agent calls `getEffectivePrice(XAUUSD)`, it **automatically** gets user price if registered.

---

## 🔴 What's Missing

### 1. Server Endpoints for User Price Registration

**Missing Endpoints:**

#### Endpoint A: POST /api/user-reference (Register/Update)
```javascript
// Request
POST /api/user-reference
{
  "canonical": "XAUUSD",
  "userPrice": 2375.50
}

// Response: 200 OK
{
  "ok": true,
  "saved": {
    "canonical": "XAUUSD",
    "userPrice": 2375.50,
    "systemPrice": 2375.30,
    "tolerance_percent": 0.0085,
    "timestamp": 1712145200000
  }
}

// Error Response: 400
{
  "ok": false,
  "error": "Invalid user price for XAUUSD (tolerance > 5%)"
}
```

#### Endpoint B: GET /api/user-reference/:canonical (Get Current)
```javascript
// Request
GET /api/user-reference/XAUUSD

// Response: 200 OK
{
  "ok": true,
  "canonical": "XAUUSD",
  "userPrice": 2375.50,
  "systemPrice": 2375.30,
  "tolerance_percent": 0.0085,
  "validated": false,
  "timestamp": 1712145200000,
  "lockedPrices": [
    { "contextId": "analysis-001", "price": 2375.45, "locked_until": 1712148800000 }
  ]
}

// Response: 404 (no user ref registered)
{
  "ok": false,
  "message": "No user reference registered for XAUUSD"
}
```

#### Endpoint C: DELETE /api/user-reference/:canonical (Clear)
```javascript
// Request
DELETE /api/user-reference/XAUUSD

// Response: 200 OK
{
  "ok": true,
  "message": "User reference cleared for XAUUSD",
  "fallbackPrice": 2375.30,
  "fallbackSource": "mt5_file"
}
```

#### Endpoint D: GET /api/user-references (Get All)
```javascript
// Request
GET /api/user-references

// Response: 200 OK
{
  "ok": true,
  "userReferences": [
    {
      "canonical": "XAUUSD",
      "userPrice": 2375.50,
      "systemPrice": 2375.30,
      "tolerance_percent": 0.0085,
      "validated": false,
      "locked": false,
      "timestamp": 1712145200000
    },
    {
      "canonical": "EURUSD",
      "userPrice": 1.08450,
      "systemPrice": 1.08350,
      "tolerance_percent": 0.092,
      "validated": false,
      "locked": false,
      "timestamp": 1712145100000
    }
  ]
}
```

### 2. Extension UI for Price Entry

**Missing Component:** Extension popup with price registration form

**Required Additions to public/popup.html & public/popup.js:**

```html
<!-- New tab in popup -->
<div class="popup-tab" data-tab="settings">
  <div class="section">
    <h3>User Reference Prices</h3>
    
    <!-- Symbol + Price Entry Form -->
    <div class="price-form">
      <select id="symbol-select">
        <option value="XAUUSD">Gold (XAUUSD)</option>
        <option value="EURUSD">EUR/USD</option>
        <option value="GBPUSD">GBP/USD</option>
        <option value="USDJPY">USD/JPY</option>
      </select>
      
      <input type="number" id="user-price-input" placeholder="Enter reference price" step="0.01">
      
      <button id="register-price-btn">Register Price</button>
      <button id="clear-price-btn">Clear Reference</button>
    </div>
    
    <!-- Current Registered Prices -->
    <div class="registered-prices">
      <h4>Registered Prices</h4>
      <div id="price-list">
        <!-- Dynamically populated -->
      </div>
    </div>
    
    <!-- Tolerance Info -->
    <div class="tolerance-info">
      <p>Tolerance: <span id="tolerance-display"></span></p>
      <p class="system-price">System: <span id="system-price-display"></span></p>
    </div>
  </div>
</div>
```

---

## 🏗️ Complete Data Flow (Proposed)

### Flow 1: Register User Price (Extension → Server → Storage)

```
1. USER ACTION in Extension
   User selects symbol, enters price, clicks "Register"
   
   Data: { canonical: "XAUUSD", userPrice: 2375.50 }

2. EXTENSION (popup.js)
   fetch('POST /api/user-reference', {
     canonical: "XAUUSD",
     userPrice: 2375.50
   })

3. SERVER (server.js - NEW ENDPOINT)
   const SymbolPreferences = require('./src/services/symbol-preferences');
   const prefs = new SymbolPreferences();
   
   await prefs.registerUserReference("XAUUSD", {
     userPrice: 2375.50,
     systemPrice: mtCurrentPrice,  // Get from mt5_data.json
     validated: false
   });
   
   response: { ok: true, saved: {...} }

4. STORAGE (store/symbol-preferences.json)
   File created/updated with:
   {
     "preferences": {
       "XAUUSD": {
         "_userReference": {
           "price": 2375.50,
           "validated": false,
           "timestamp": 1712145200000,
           ...
         }
       }
     }
   }

5. CONFIRMATION
   Extension popup shows: "✓ Price registered: 2375.50"
   Displays tolerance vs system: "diff: +0.20 (0.0085%)"
```

### Flow 2: Agent Uses User Price

```
1. AGENT INITIALIZATION
   Agent calls: data-source-manager.getEffectivePrice("XAUUSD")

2. DATA SOURCE MANAGER (lib/data-source-manager.js)
   Calls: this.preferences.getEffectivePrice("XAUUSD", null)

3. SYMBOL PREFERENCES (src/services/symbol-preferences.js)
   Checks hierarchy:
   - Context locks? → No
   - User reference? → YES (2375.50, validated: false)
   - Return { effectivePrice: 2375.50, source: "user_reference" }

4. AGENT RECEIVES
   {
     price: 2375.50,
     source: "user_reference",
     systemPrice: 2375.30,
     warning: "Using user reference price (0.0085% diff from system)"
   }

5. AGENT USES
   All analysis: momentum, RSI, trends, signals
   Based on 2375.50 (user choice), NOT 2375.30 (system)
```

### Flow 3: Dashboard Displays User Prices

```
1. DASHBOARD INITIALIZATION
   fetch('GET /api/user-references')

2. SERVER ENDPOINT (NEW)
   const prefs = new SymbolPreferences();
   const allRefs = await prefs.getAllUserReferences();
   // Returns array of {canonical, userPrice, systemPrice, tolerance_percent}

3. DASHBOARD RENDERS
   Shows table:
   | Symbol  | User Price | System Price | Diff %  | Status    |
   |---------|-----------|-------------|---------|-----------|
   | XAUUSD  | 2375.50   | 2375.30     | 0.0085% | User Ref  |
   | EURUSD  | 1.08450   | 1.08350     | 0.092%  | User Ref  |
   | GBPUSD  | —         | 1.26500     | —       | System    |
```

---

## ⚙️ Persistence Strategy

### Where to Store User Prices?

**Rejected Options:**
- ❌ localStorage (extension storage): Not shared with server, dies on clear cache
- ❌ Extension chrome.storage.local: Browser-specific, not accessible to server
- ❌ Direct flat file in /public: Would require server interaction anyway

**Recommended Option: server/store/symbol-preferences.json**
- ✅ Persistent on server disk
- ✅ Accessible to all components (agent, dashboard, extension)
- ✅ Survives browser clear cache
- ✅ Easy to backup/export
- ✅ Already created by symbol-preferences.js

**File Lifecycle:**
```
1. First registration: store/symbol-preferences.json created
2. Each update: File written with complete state
3. Backup: Daily export to store/symbol-preferences-BACKUP-YYYY-MM-DD.json
4. Restoration: Can manually restore from backup
```

---

## 📏 Tolerance Rules by Asset Class

### Rule Set (Proposed)

| Asset Class | Symbol | Max Tolerance | Reason |
|---|---|---|---|
| **Precious Metals** | XAUUSD, XAGUSD | ±0.5% | Volatile intraday, 2-3 pt moves |
| **Major Forex** | EURUSD, GBPUSD, USDJPY, AUDUSD | ±0.1% | Multiple sources, tight spreads |
| **Commodity** | USOIL, UKOIL | ±0.8% | Volatile news reactions |
| **Crypto** | BTCUSD, ETHUSD | ±2.0% | High volatility, multiple exchanges |
| **Indices** | SPX500, US100 | ±0.3% | Derivative spreads |
| **Bonds/Rates** | EURIBOR, T10Y | ±0.05% | Very tight spreads |

### Logic Implementation

```javascript
// In server endpoint POST /api/user-reference
const TOLERANCE_RULES = {
  'XAUUSD': 0.5,    // 0.5%
  'XAGUSD': 0.5,
  'EURUSD': 0.1,    // 0.1%
  'GBPUSD': 0.1,
  'USDJPY': 0.1,
  'USOIL': 0.8,
  'BTCUSD': 2.0,
  'default': 0.5
};

const getMaxTolerance = (canonical) => {
  return TOLERANCE_RULES[canonical] || TOLERANCE_RULES['default'];
};

// Validation
const maxTolerance = getMaxTolerance(canonical);
const validation = prefs.validate(canonical, userPrice, systemPrice, maxTolerance);

if (!validation.ok) {
  return res.status(400).json({
    ok: false,
    error: `Price divergence ${validation.deltaPercent.toFixed(4)}% exceeds ${maxTolerance}%`,
    suggestion: `System price is ${systemPrice}. Consider ${systemPrice} instead?`
  });
}

// Allow override with confirmation
if (req.body.force_override === true) {
  // Save anyway, with warning flag
  await prefs.registerUserReference(canonical, {
    userPrice, systemPrice, validated: true, override: true
  });
}
```

---

## 🔐 Comparison Rules (User vs System)

### What Happens When Prices Diverge?

**Scenario 1: Minor divergence (within tolerance)**
```
User: 2375.50
System: 2375.30
Diff: 0.0085% (< 0.5% tolerance)

✅ ACCEPTED
Agent uses: 2375.50 (user price)
Dashboard shows: Green indicator "Within tolerance"
```

**Scenario 2: Major divergence (exceeds tolerance)**
```
User: 2370.00
System: 2375.30
Diff: 0.22% (> 0.5% tolerance? No, 0.22% < 0.5%)

Actually: 5.30 absolute = 0.22%
✅ ACCEPTED (within tolerance)
Dashboard shows: Yellow warning "Price divergence 0.22%"
```

**Scenario 3: Extreme divergence (far outside tolerance)**
```
User: 2300.00
System: 2375.30
Diff: 3.16% (> 0.5% tolerance)

❌ REJECTED (default behavior)
Server returns: 400 error
Extension shows: Red alert "Price divergence 3.16% exceeds 0.5% limit"
User option: ["Cancel", "Override (at own risk)"]

If override: Saved with validated=true, override_reason="user_confirmed"
```

---

## 📋 Data Structure for Storage

**Final Structure (symbol-preferences.json):**

```json
{
  "preferences": {
    "XAUUSD": {
      "_systemData": {
        "price": 2375.30,
        "source": "mt5_file",
        "timestamp": 1712145135000,
        "age_ms": 2000,
        "reliable": true
      },
      "_userReference": {
        "price": 2375.50,
        "validated": false,
        "timestamp": 1712145200000,
        "tolerance_absolute": 0.20,
        "tolerance_percent": 0.0085,
        "tolerance_max_allowed": 0.5,
        "variants": [],
        "system_price_at_registration": 2375.30,
        "override": false,
        "override_reason": null
      },
      "_locks": {},
      "_modification_history": [
        {
          "old_price": null,
          "new_price": 2375.50,
          "timestamp": 1712145200000,
          "reason": "initial_registration",
          "source": "extension_popup"
        }
      ],
      "_lock_history": [],
      "_price_update_history": [
        {
          "old_price": 2375.30,
          "new_price": 2375.35,
          "timestamp": 1712145300000,
          "user_reference_at_time": 2375.50,
          "status": "ignored (user ref exists)"
        }
      ]
    }
  },
  "metadata": {
    "lastUpdated": 1712145200000,
    "version": "2.0"
  }
}
```

---

## ✅ Integration Validation

### Does This Break Anything?

**Constraint 1: No breaking changes to symbol-preferences.js**
- ✅ SAFE: `registerUserReference()` method already exists
- ✅ SAFE: All parameters already match
- ✅ SAFE: File I/O already handles creation

**Constraint 2: No breaking changes to data-source-manager.js**
- ✅ SAFE: `getEffectivePrice()` already calls symbol-preferences
- ✅ SAFE: Hierarchy already respects user_reference > system
- ✅ SAFE: No agent code changes needed

**Constraint 3: No external APIs**
- ✅ SAFE: User price is from user input, not API
- ✅ SAFE: System price from mt5_data.json (local file)
- ✅ SAFE: Comparison happens server-side only

**Constraint 4: Hierarchy protection**
- ✅ SAFE: locked(contextId) > userReference > system
- ✅ SAFE: User price never silently overridden
- ✅ SAFE: system price updates don't modify user price

**Constraint 5: No UI modifications (backend only)**
- ✅ SAFE: Extension popup is NEW (not existing modification)
- ✅ SAFE: Dashboard endpoints are NEW (not existing changes)
- ✅ SAFE: Studio doesn't need modification (uses getEffectivePrice)

---

## 📋 Implementation Sequence

### Phase A: Server Endpoints (2-3 hours)

```
1. Create POST /api/user-reference (register)
2. Create GET /api/user-reference/:canonical (get one)
3. Create DELETE /api/user-reference/:canonical (clear)
4. Create GET /api/user-references (get all)
```

### Phase B: Extension UI (1-2 hours)

```
1. Add "Settings" tab to popup.html
2. Create price registration form
3. Show registered prices list
4. Update popup.js to fetch/post prices
```

### Phase C: Dashboard Integration (1 hour)

```
1. Fetch user prices on dashboard load
2. Render table with user vs system prices
3. Add "Edit" and "Clear" buttons
```

### Phase D: Testing (1 hour)

```
1. Register price from extension
2. Verify agent uses it
3. Check tolerance validation
4. Test persistence (reload page)
```

**Total Effort: 5-7 hours**

---

## 🎯 Success Criteria

- ✅ User can register price via extension popup
- ✅ Price persisted in store/symbol-preferences.json
- ✅ Agent uses registered price (not system)
- ✅ Dashboard shows all registered prices
- ✅ Tolerance validation works
- ✅ No breaking changes to existing code
- ✅ Zero external APIs
- ✅ No localStorage (all server-side persistence)

---

## 📝 Proposed Next Steps

**If validated, this analysis would lead to:**

1. ✅ Create 4 server endpoints in server.js
2. ✅ Add Settings tab to extension popup.html
3. ✅ Implement price form logic in popup.js
4. ✅ Add user price display to dashboard
5. ✅ Full integration testing

**Questions for User:**

1. **Persistence:** Agree with `store/symbol-preferences.json` as storage location?
2. **Tolerance:** Agree with tolerance rules by asset class above?
3. **Validation:** Should user be able to override tolerance with confirmation flag?
4. **UI Strategy:** Settings tab in extension popup or separate page?
5. **Ready to implement?** Or need clarification on any part?
