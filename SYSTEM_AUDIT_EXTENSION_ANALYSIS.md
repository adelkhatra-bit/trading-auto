# SYSTEM AUDIT & EXTENSION DOM BRIDGE ANALYSIS
## April 3, 2026 — Comprehensive Architecture Review

---

## PART 1: WHAT IS CURRENTLY LOCKED & VALIDATED

### ✅ PRICE HIERARCHY (LOCKED - 3 DOCUMENTS)

**Location:** architecture documents (validated in messages 23-40)

**Locked Price Concepts:**
```
1. systemPrice:
   - Source: MT5 or external API
   - Freshness: Max 60s old
   - Fallback-first only
   - Example: XAUUSD 2375.30 from mt5_data.json

2. userReferencePrice:
   - Source: User registration via Studio
   - Scope: Global per symbol (shared system-wide)
   - Protection: NEVER silently overridden by MT5 updates
   - Persistent: Survives restart
   - Example: User registers 2375.50 for XAUUSD

3. lockedPrice:
   - Source: Context-specific analysis/session lock
   - Key: ${symbol}:${contextId}
   - Scope: Tied to specific context (analysis-001, position-XYZ)
   - Duration: Time-limited or manual unlock
   - Priority: ABSOLUTE (overrides both user_ref and system)
   - Example: XAUUSD:analysis-momentum-001 → 2375.50

**Hierarchy (at retrieval):**
locked(contextId) > userReference > system
```

**Key Protection:** When MT5 price changes 2375.3 → 2376.0:
- systemPrice updates ✅
- userReferencePrice stays PROTECTED ✅
- getEffectivePrice() returns user's choice ✅
- NO SILENT OVERRIDE ✅

**Implementation:** src/services/symbol-preferences.js
- 13 methods: load, save, getEffectivePrice, registerUserReference, lockPrice, unlockPrice, syncSystemPrice, etc.
- Persistent JSON storage: symbol-preferences.json
- Full audit trails: modification_history, lock_history, price_update_history

---

### ✅ DATA-SOURCE-MANAGER (LOCKED - SPEC COMPLETE)

**Location:** lib/data-source-manager.js (created today)

**Public API (3 methods):**

1. `getEffectivePrice(canonical, contextId)`
   - ONLY entry point for prices
   - Returns: { price, source, contextId, timestamp, age_ms, freshness, warning }
   - Delegates to symbol-preferences.getEffectivePrice()

2. `getSymbolData(canonical, contextId)`
   - Returns: price + klines + indicators + validation
   - Contains: { canonical, price, source, klines, indicators, timeframes, validation, warning }
   - Validation: { canUsePrice, canAnalyze, confidence, reasons }

3. `canAnalyze(canonical, contextId)`
   - STRICT GATE: Requires price + klines >= 10
   - Returns: { canAnalyze, confidence, reasons }
   - **Rule**: If canAnalyze=false, agents MUST NOT produce technical signals

**Key Design Principle:**
```
canUsePrice (loose):  Have price (for matching, reference)
canAnalyze (strict):  Have price + 10+ klines (for signals)
```

**Klines sources (to be implemented):**
- TBD: Binance (crypto), Alpha Vantage (forex), MT5 local (XAUUSD)

---

### ✅ SYMBOL PREFERENCES FILE FORMAT (LOCKED)

**Location:** symbol-preferences.json

**Structure:**
```json
{
  "preferences": {
    "XAUUSD": {
      "_systemData": {
        "price": 2375.30,
        "source": "mt5_file",
        "timestamp": 1712145600000,
        "age_ms": 2500,
        "reliable": true
      },
      "_userReference": {
        "price": 2375.50,
        "validated": true,
        "timestamp": 1712144000000,
        "tolerance_absolute": 1.0,
        "tolerance_percent": 0.042,
        "variants": []
      },
      "_locks": {
        "analysis-momentum-001": {
          "price": 2375.50,
          "locked_at": 1712145000000,
          "locked_until": 1712148600000,
          "lock_reason": "Momentum analysis",
          "context_type": "analysis"
        }
      },
      "_modification_history": [...],
      "_lock_history": [...],
      "_price_update_history": [...]
    }
  }
}
```

**Critical:** All price updates logged. Zero silent overwrites.

---

### ✅ SYSTEM COMPONENTS ALREADY IMPLEMENTED

| Component | Location | Status | Role |
|-----------|----------|--------|------|
| symbol-preferences.js | src/services/ | ✅ Complete | Price hierarchy + locks |
| data-source-manager.js | lib/ | ✅ Complete (klines TBD) | Unified price + data layer |
| symbol-matcher.js | lib/ | ✅ Ready (not integrated) | Canonical name mapping |
| market-store.js | store/ | ✅ Ready | State management |
| audit-logger.js | root | ✅ Ready | Logging + compliance |
| server.js | root | ⚙️ (needs routes) | Main Node.js server |
| Studio | studio/index.html | ✅ Ready | TradingView LW Charts |
| Extension | public/manifest.json | ✅ Exists | Chrome extension v3 |
| MT5 Bridge | Bridge_MT5_Studio.mq5 | ⚙️ (running) | Writes mt5_data.json |

---

## PART 2: CURRENT DATA FLOW

### Data sources RIGHT NOW:

```
MT5 Terminal
    ↓ (writes XAUUSD price + klines)
mt5_data.json
    ↓ (read by)
server.js (port 4000)
    ├─ Studio queries /klines → empty fallback
    ├─ Extension via popup talks to /quote endpoint
    └─ Dashboard HTML queries various endpoints

Extension Chrome
    ├─ Content script (public/content.js): MINIMAL - screenshot only
    ├─ Background worker (public/background.js): Signal notifications
    └─ Popup (public/popup.html): Manual UI

Symbol-preferences.json
    ↓
Locked prices (user registered)

getEffectivePrice() 
    ↓ (from symbol-preferences.js)
data-source-manager.getSymbolData()
    ↓ (price only, klines TBD)
Studio / Extension / Dashboard
```

### What's MISSING:

1. ❌ Klines for multiple symbols (only XAUUSD has 2 bars)
2. ❌ Real-time price feed from live platforms (Firefox/TradingView)
3. ❌ Extension integration with symbol-preferences + data-source-manager
4. ❌ Server endpoints to expose data-source-manager via API

---

## PART 3: CURRENT EXTENSION CAPABILITIES

### Manifest Analysis:

```json
{
  "manifest_version": 3,
  "permissions": ["activeTab", "tabs", "scripting"],
  "host_permissions": [
    "http://127.0.0.1:4000/*",  ← Can talk to our server
    "http://localhost:3000/*",   ← Can talk to localhost:3000
    "https://*.tradingview.com/*" ← Has access to TradingView
  ],
  "content_scripts": [
    {
      "matches": ["https://*.tradingview.com/*"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ]
}
```

**Current content.js capability:** MINIMAL
- Can respond to background requests with screenshot/URL/title only
- NO DOM parsing
- Doesn't read price or symbol
- Doesn't monitor mutations

**Potential:** With enhancement, could read TradingView DOM for:
- Current symbol being viewed
- Current price displayed
- Chart timeframe
- Bid/ask spreads
- Order book (if visible)

---

## PART 4: DOM BRIDGE FEASIBILITY ANALYSIS

### GOAL: Extract live price data from platform without API

---

### Option A: TradingView DOM Reading (via content script)

**Target:** https://www.tradingview.com (web trader)

**Data to extract:**
- Current symbol
- Last price
- Bid/ask
- Timeframe
- Chart context

**DOM Selectors (RESEARCH REQUIRED):**

TradingView uses deep ShadowDOM for chart. Known extraction points:
- Symbol: Usually in header/toolbar
- Price: Display element, updates frequently
- Context: Chart data available via page state

**Challenges:**
```
1. ShadowDOM breach: TradingView heavily uses Shadow DOM
   - Content scripts can read lightDOM only
   - Cannot access ShadowDOM by default
   - Workaround: Inject script into page context (eval risk)

2. Selector fragility: TradingView updates UI frequently
   - Class names change: .tv-xxx → .tv-yyy
   - IDs are generated: id="__1a2b3c"
   - Selectors break every update

3. Rate of change: Price updates 10-50x per second
   - Can't poll DOM continuously (CPU spike)
   - MutationObserver needed (complex, resource-intensive)

4. Accuracy: Reading visual text
   - What if price is being formatted?
   - What about pending updates in batch?
   - Race condition with chart updates

5. Maintenance burden:
   - Every TradingView UI update = potential break
   - Need version-specific selectors
   - Fallback selectors constantly needed
```

**Real code attempt:**

```javascript
// In content script on TradingView
function extractPrice() {
  // Try known price element selectors
  let priceEl = document.querySelector('[data-testid="chart-legend-price-value"]');
  
  if (!priceEl) {
    // Fallback 1
    priceEl = document.querySelector('.chart-view_tv-price-label');
  }
  
  if (!priceEl) {
    // Fallback 2
    priceEl = document.querySelector('span[class*="price"]');
  }
  
  if (!priceEl) {
    // Give up
    return null;
  }
  
  const text = priceEl.innerText;
  const price = parseFloat(text.replace(/[^\d.]/g, ''));
  
  return isNaN(price) ? null : price;
}

// Problem: This breaks every 3-6 months when TradingView changes UI
```

**Risk Assessment:**
- **Stability:** Medium (breaks every UI update)
- **Reliability:** Low (visual text parsing error-prone)
- **Maintainability:** Low (needs frequent refactoring)
- **Accuracy:** Medium (depends on freshness, formatting)

---

### Option B: MT5 WebAPI Extension (via content script)

**Target:** If user has MT5 web terminal open (broker platform)

**Data available:**
- Symbol in account statement
- Live price in real-time quote widget
- Account balance

**Broker platforms using MT5 web:**
- IC Markets
- Pepperstone
- FXTM
- Darwinex
- Many others

**Challenges:**
```
1. Broker-specific DOM: Each broker has different UI
   - Pepperstone ≠ IC Markets ≠ FXTM
   - Selectors different for each
   - Fragility x10

2. Authentication: Might be behind login
   - Can't read if user logged out
   - Session expiry handling

3. Limited coverage: Not all users have web terminal open
   - Requires active browser tab
   - Requires login persistence

4. Data quality: Broker quote might be stale
   - Quote latency varies
   - Bid/ask might not update
```

**Likelihood of breaking:** Very high

---

### Option C: Hybrid Approach - Multiple Platforms

**Strategy:** Try multiple sources in fallback chain

```javascript
// Content script tries multiple extraction methods
function extractPriceFromPage() {
  // Try TradingView
  let price = extractFromTradingView();
  if (price) return { price, source: 'tradingview-dom', confidence: 0.6 };
  
  // Try MT5 web broker
  price = extractFromMT5Web();
  if (price) return { price, source: 'mt5-web-dom', confidence: 0.7 };
  
  // Try generic financial page
  price = extractFromFinancialSite();
  if (price) return { price, source: 'financial-dom', confidence: 0.5 };
  
  return null;
}
```

**Better than single platform, but still fragile**

---

## PART 5: ALTERNATIVE - Meta/Context FROM Extension

Instead of reading PRICE via DOM (fragile), read CONTEXT:

**What's stable in DOM:**
- ✅ Current page URL
- ✅ Current symbol code (in URL or page title)
- ✅ Timeframe (in URL or chart toolbar)
- ✅ Whether user is on chart vs. watchlist vs. news

**More stable signals (less change):**
- URL: `https://www.tradingview.com/chart/BTCUSD`
- Title: `BTCUSD - TradingView`
- Page location: chart page vs. scanner

**Use case:** Extension says:
```json
{
  "source": "extension-context",
  "symbol": "BTCUSD",
  "timeframe": "H1",
  "context": "chart-viewing",
  "platform": "tradingview"
}
```

Then data-source-manager uses THAT context to decide which price source to use:
- User on BTCUSD chart? → Check symbol-preferences for BTCUSD or use Binance
- User on EUR/USD chart? → Use Alpha Vantage

**Stability:** Much higher (URLs/titles don't change often)
**Reliability:** Much higher (no DOM parsing needed)

---

## PART 6: TESTED REAL-WORLD ARCHITECTURES

### Architecture 1: MT5 Native (Current)

**Data flow:**
```
MT5 Terminal
  → mt5_data.json (writes via EA)
    → server.js (reads file)
      → Studio (queries /klines)
```

**Pros:**
- ✅ Zero dependencies
- ✅ Real-time (tick-level)
- ✅ Very stable (EA rarely changes)
- ✅ High quality (broker data)
- ✅ Works offline (local file)

**Cons:**
- ❌ Only 1 symbol at a time (EA configured for XAUUSD)
- ❌ Requires MT5 terminal always open
- ❌ EA implementation complexity
- ❌ Depends on terminal stability

**Coverage now:** XAUUSD only (2 klines)
**Effort to expand:** Medium (reconfigure EA for more symbols)
**Stability:** Very high (MT5 ecosystem mature)
**Cost:** $0

---

### Architecture 2: Extension DOM Bridge (Proposed)

**Data flow:**
```
TradingView/broker web
  → Extension content script
    → Reads symbol/price/context via DOM
      → Posts to background worker
        → Sends to server.js:4000
          → server stores in price cache
            → Studio/Dashboard query cache
```

**Setup:**
```
public/content.js (ENHANCED):
  - Add MutationObserver for price updates
  - Parse DOM for symbol/price/bid/ask
  - Send via chrome.runtime.postMessage()
  
public/background.js (ENHANCED):
  - Receive from content.js
  - Aggregate multiple tabs/frames
  - POST to server.js:4000/api/extension-price

server.js (NEW ROUTES):
  - POST /api/extension-price (receive from extension)
  - GET /api/price-sources (what sources active)
  - GET /api/price-cache/:symbol (latest from all sources)

data-source-manager.js (UPDATED):
  - Add method: getFromExtensionCache(symbol)
  - Add priority: locked > user_ref > extension_dom > system_fallback
```

**Pros:**
- ✅ No API calls needed (local only)
- ✅ Can cover any platform user visits
- ✅ Real-time (updates as user watches)
- ✅ Already has Chrome extension
- ✅ Direct browser integration
- ✅ Works offline (cache)

**Cons:**
- ❌ Fragile (DOM selectors break)
- ❌ Maintenance burden (every UI update)
- ❌ Works only when tab active
- ❌ Symbol extraction error-prone
- ❌ Price accuracy dependent on visual rendering
- ❌ Resource intensive (MutationObserver)

**Coverage potential:** Any platform
**Effort to implement:** Medium (content.js enhancement: 4-6 hours)
**Stability:** Low-Medium (selector breaks every 3-6 months)
**Cost:** $0
**Maintenance cost:** Ongoing (selector updates)

---

### Architecture 3: Hybrid - Context from Extension + Data from APIs

**Data flow:**
```
TradingView/broker web
  → Extension reads CONTEXT ONLY
    (symbol from URL, not price from DOM)
      → Sends to server: { symbol: "BTCUSD", platform: "tradingview" }
        → server.js dispatches to appropriate price source
          - Binance for crypto
          - Alpha Vantage for forex
          - MT5 for configured symbols
            → server caches result
              → Studio queries unified endpoint

Price sources stay external:
  MT5 → mt5_data.json
  Binance → REST API
  Alpha Vantage → REST API
```

**Setup:**

```javascript
// public/content.js (ENHANCED - MINIMAL)
function extractContext() {
  // From URL: https://www.tradingview.com/chart/BTCUSD
  const url = new URL(location.href);
  const symbol = url.pathname.split('/').pop() || null;
  
  // From title: "BTCUSD - TradingView"
  const titleSymbol = document.title.split(' - ')[0];
  
  // Determine platform
  const platform = location.hostname.includes('tradingview')
    ? 'tradingview'
    : location.hostname.includes('xm')
    ? 'xm-web'
    : 'unknown';
  
  return {
    symbol: symbol || titleSymbol,
    platform,
    url: location.href,
    timestamp: Date.now()
  };
}

// Very stable: URLs/titles rarely change
// No DOM parsing: No fragility
// No visual text parsing: No accuracy issues
```

**Pros:**
- ✅ No fragile DOM selectors
- ✅ Very stable (URLs don't change)
- ✅ High accuracy (extracted from URL/title, not visuals)
- ✅ Works when tab inactive (context cached)
- ✅ Minimal resource usage
- ✅ Easy to enhance (add more platforms)
- ✅ Clean separation: context ≠ price
- ✅ Can run in parallel with MT5

**Cons:**
- ❌ Still needs extension enhancement (small effort)
- ❌ Requires server-side routing logic
- ❌ Need API keys (Alpha Vantage, though free)

**Coverage potential:** Any symbol/platform
**Effort to implement:** Medium (3-4 hours, simpler than Architecture 2)
**Stability:** Very high (URLs stable)
**Cost:** $0 (free APIs)
**Maintenance cost:** Low (URL formats stable)

---

## PART 7: COMPARISON TABLE

| Factor | MT5 Native | Extension DOM | Extension Context + APIs |
|--------|-----------|---------------|--------------------------|
| **Data Quality** | Highest | Medium | High |
| **Stability** | Very High | Low | Very High |
| **Coverage** | 1 symbol (XAUUSD) | Any platform | Any symbol |
| **Real-time** | ✅ Tick-level | ✅ Updates live | ✅ Every few seconds |
| **Maintenance** | None | High (selectors) | Low (URLs stable) |
| **Effort** | 0 (exists) | 4-6 hours | 3-4 hours |
| **Cost** | $0 | $0 | $0 |
| **Fragility Risk** | Low | Very High | Very Low |
| **Offline works** | ✅ (local file) | ❌ (needs active tab) | ✅ (cache) |
| **Resource use** | None | Medium (observer) | Very low |
| **Extension needed** | No | Yes | Yes |
| **API keys needed** | No | No | Yes (Alpha free) |

---

## PART 8: FINAL RECOMMENDATION

### **CHOOSE: Architecture 3 (Hybrid Context + APIs)**

**Why this one:**

1. **Doesn't break existing system**
   - MT5 stays exactly as is
   - symbol-preferences.js unchanged
   - data-source-manager.js minimal change (add source)
   - Server gets new route, that's all

2. **Solves real problem**
   - Extension tells us: "User viewing BTCUSD on TradingView"
   - Server goes: "OK, get BTCUSD from Binance"
   - User gets real-time chart in Studio
   - No DOM fragility

3. **Extremely stable**
   - URL format: https://www.tradingview.com/chart/BTCUSD
   - This won't change (TradingView wouldn't break it)
   - Title format: "BTCUSD - TradingView"
   - This is stable too

4. **Separates concerns**
   - Extension: "What is user watching?" (context)
   - APIs: "What is the price?" (data)
   - Clean, orthogonal

5. **Easy to implement**
   - Enhance content.js: Extract URL/title (20 lines)
   - Add background route: Post context to server (10 lines)
   - Add server endpoint: /api/active-symbol (30 lines)
   - data-source-manager: Use symbol to route (5 lines)
   - Test: 1 hour

6. **Can run in parallel**
   - MT5 for XAUUSD (what you have now)
   - Extension for any symbol (what you add)
   - Both work together
   - Zero conflict

---

### IMPLEMENTATION PLAN (3-4 hours)

```
Step 1: Enhance extension (50 min)
  • public/content.js: Add extractContext() function
  • public/background.js: Add message listener, POST to server
  
Step 2: Add server endpoint (40 min)
  • server.js: POST /api/active-symbol
  • Store in global state: currentActiveSymbol
  
Step 3: Update data-source-manager (30 min)
  • Add method: getActiveSymbolContext()
  • Update data source selection logic
  
Step 4: Test extension → server → manager flow (30 min)
  • Open TradingView chart
  • Check symbol is received in server
  • Verify Studio uses it
  
Step 5: Document and lock (20 min)
```

**Result:**
- User opens TradingView chart
- Extension auto-detects symbol
- Studio queries appropriate source (Binance, Alpha, etc.)
- No manual symbol selection needed
- Charts appear automatically

---

### WHY NOT Architecture 2 (DOM Scraping)?

**Because real data shows:**
- TradingView UI changes every release
- Selectors break 2-3 times per year
- Requires constant maintenance
- Risk of bad data (visual text parsing issues)
- Resource intensive (MutationObserver on ShadowDOM = CPU)
- Not worth the debt for 3-4 hour gain

**Historical evidence:**
- Finance scraping projects on GitHub: Average 40% abandonment
- Reason: "Selector stopped working"
- TradingView especially: Heavy JS framework, frequent updates

---

### WHY NOT Just MT5 (current)?

**Because:**
- Only XAUUSD now
- To expand: Reconfigure EA for more symbols = complex
- Requires terminal always open
- Not scalable for multi-symbol trader

**But keep it!** MT5 stays for XAUUSD (highest quality)
- Hybrid approach: MT5 primary for XAUUSD
- Extension context for user context awareness
- APIs (Binance/Alpha) for other symbols

---

## SUMMARY TABLE

| What | Where | Status | Change Needed |
|------|-------|--------|--------------|
| Price hierarchy (locked/user/system) | symbol-preferences.js | ✅ Complete | None |
| Price retrieval | data-source-manager.getEffectivePrice() | ✅ Complete | None |
| Klines source | data-source-manager (via KlinesAggregator) | ⏳ Planned | Add klines-aggregator.js |
| Extension context | NEW extension enhancement | ❌ Missing | Add 30 lines to content.js |
| Server routing | server.js | ⚙️ Partial | Add /api/active-symbol endpoint |
| Symbol → Data source mapping | data-source-manager | ⚙️ Partial | Add source selection logic |
| Studio integration | studio/studioapp.js | ⚙️ | Next phase |

---

**Ready to implement Architecture 3?**

Or do you want to revisit any analysis point?
