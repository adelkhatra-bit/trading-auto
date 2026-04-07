# GARDE-FOUS & VALIDATION PRÉ-IMPLÉMENTATION

**Date**: April 3, 2026  
**Status**: Pre-implementation specification  
**Architecture**: MT5 Multi + Extension Context + Local Server

---

## GARDE-FOU A: PAS DE FAUX GRAPHIQUE

### Règle stricte

**If symbol absent from MT5 local → NO chart display, no fake data**

### Comportement exact

**Studio requests**: `GET /klines?symbol=EURUSD`

**Scenario 1: Symbol exists in mt5_data.json**
```json
{
  "ok": true,
  "symbol": "EURUSD",
  "klines": [...100 real bars from MT5...],
  "source": "mt5_local",
  "canAnalyze": true,
  "confidence": "high"
}

→ Studio displays real chart
→ Agent can analyze
```

**Scenario 2: Symbol does NOT exist in mt5_data.json**
```json
{
  "ok": false,
  "symbol": "EURUSD",
  "error": "EURUSD_NOT_IN_MT5",
  "message": "Symbol detected in extension context but no local data. Add to MT5 terminal.",
  "klines": [],
  "source": "none",
  "canAnalyze": false,
  "confidence": "none",
  "reasons": ["No klines available", "Symbol not in MT5 local data"]
}

→ Studio shows CLEAR message (not blank chart)
→ Message: "EURUSD — Données locales absentes. Ajouter au terminal MT5."
→ Agent does NOT analyze
→ No silent fallback
→ No fake signals
```

### in Studio UI

```javascript
// studio/studioapp.js

async function loadChart(force) {
  const response = await fetch(`/klines?symbol=${state.symbol}`);
  const data = await response.json();
  
  if (!data.ok || data.klines.length === 0) {
    // IMPORTANT: Show clear message, not blank chart
    setOverlay(
      `⚠️ ${data.symbol}\n\n` +
      `${data.message}\n\n` +
      `Actions:\n` +
      `• Ajouter au terminal MT5\n` +
      `• OU Sélectionner un symbole disponible`
    );
    
    return;  // Do NOT try to draw chart
  }
  
  // Draw real chart
  drawChart(data.klines);
}
```

### Trust Model

**User sees exactly what's available locally. No magic, no fallback tricks.**

---

## GARDE-FOU B: EXTENSION = CONTEXTE SEULEMENT

### Scope

Extension does ONE thing: **Extract context from active tab**

```javascript
// public/content.js (ENHANCED)

function extractActiveContext() {
  // READ: URL, title, page state
  // DO NOT: Call APIs, call external services, compute prices
  
  const url = new URL(location.href);
  
  return {
    symbol: extractSymbolFromURL(url),      // "EURUSD" from tradingview.com/chart/EURUSD
    platform: extractPlatform(url),         // "tradingview"
    timeframe: extractTimeframe(url),       // "H1" from chart settings (if visible)
    timestamp: Date.now(),
    
    // DO NOT INCLUDE:
    // price, bid, ask, indicators, etc.
  };
}

// Send to background
function sendContextUpdate() {
  const context = extractActiveContext();
  
  if (context.symbol) {
    chrome.runtime.sendMessage({
      type: 'ACTIVE_CONTEXT_CHANGED',
      payload: context
    });
  }
}

// Listen for page changes
window.addEventListener('hashchange', sendContextUpdate);
document.addEventListener('visibilitychange', sendContextUpdate);
```

### What Extension CANNOT do

- ❌ Read prices from DOM
- ❌ Call external APIs
- ❌ Implement price hierarchy logic
- ❌ Cache prices locally
- ❌ Apply fuzzy symbol matching
- ❌ Fallback to secondary sources

### What Extension MUST do

- ✅ Extract symbol from URL/title (stable, unlikely to break)
- ✅ Send context to server
- ✅ Nothing else

### Code constraint

```javascript
// Allowed in content.js:
const symbol = location.href.split('/chart/')[1];  // URL parsing ✅
const title = document.title;  // Page title ✅

// NOT allowed:
const price = document.querySelector('.price-element').innerText;  // DOM parsing ❌
const quote = await fetch('https://api.example.com/price');  // External API ❌
const priceFromCache = await chrome.storage.local.get('price');  // Caching logic ❌
```

---

## GARDE-FOU C: TOUT PAR DATA-SOURCE-MANAGER

### Architecture du flux

```
┌─────────────────────────────────────────┐
│ Extension detects EURUSD on TradingView │
└──────────────┬──────────────────────────┘
               │
               ▼
        postMessage to background
        {type: 'ACTIVE_CONTEXT', symbol: 'EURUSD'}
               │
               ▼
┌─────────────────────────────────────────────┐
│ Background posts to server:3000             │
│ POST /api/active-symbol-context             │
│ {symbol: 'EURUSD', platform: 'tradingview'} │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ server.js processes                                     │
│ - Stores in global state: activeSymbol = 'EURUSD'      │
│ - NO price logic here, just context storage            │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│ Studio queries: GET /klines?symbol=EURUSD            │
│ Server routes to data-source-manager                 │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
    ┌──────────────────────────────┐
    │ data-source-manager.js       │
    │ getSymbolData('EURUSD')       │
    │                              │
    │ 1. Load mt5_data.json        │
    │ 2. getEffectivePrice()       │
    │ 3. _getKlines()              │
    │ 4. _validateData()           │
    │ 5. return {ok, klines, ...}  │
    └──────────────┬───────────────┘
                   │
                   ▼
    ┌──────────────────────────────┐
    │ getEffectivePrice()          │
    │                              │
    │ Calls symbol-preferences:    │
    │ - Check locked(contextId)    │
    │ - Check userReference        │
    │ - Check systemPrice from MT5 │
    │                              │
    │ Returns: {price, source}     │
    └──────────────┬───────────────┘
                   │
                   ▼
    ┌──────────────────────────────┐
    │ Studio receives response     │
    │ {klines, price, source, ...} │
    │                              │
    │ Displays chart if ok: true   │
    │ Shows message if ok: false   │
    └──────────────────────────────┘
```

### Code structure

```javascript
// server.js

// ONLY endpoint for context from extension
app.post('/api/active-symbol-context', (req, res) => {
  const { symbol, platform } = req.body;
  
  // ONLY: Store context
  global.activeContext = { symbol, platform, timestamp: Date.now() };
  
  // DO NOT: Fetch prices, validate symbol, apply logic
  
  res.json({ ok: true, stored: true });
});

// Studio queries for chart data
app.get('/klines', async (req, res) => {
  const symbol = req.query.symbol || 'XAUUSD';
  
  // DELEGATE ALL to data-source-manager
  const manager = await getDataSourceManager();
  
  try {
    const data = await manager.getSymbolData(symbol);
    res.json(data);
  } catch (error) {
    res.status(400).json({
      ok: false,
      error: error.message
    });
  }
});

// data-source-manager.js
class DataSourceManager {
  async getSymbolData(canonical) {
    // Load preferences
    const priceData = await this.preferences.getEffectivePrice(canonical);
    
    // Load klines
    const klines = this._getKlines(canonical);
    
    // Validate
    const validation = this._validateData(canonical, priceData, klines);
    
    // Return unified response
    return {
      ok: validation.canUsePrice && validation.canAnalyze,
      canonical,
      price: priceData.price,
      source: priceData.source,
      klines,
      validation,
      warning: validation.canAnalyze ? null : (`Cannot analyze: ${validation.reasons.join(', ')}`)
    };
  }
}
```

### Trust boundary

**ONLY data-source-manager reads from mt5_data.json**

No other component:
- ❌ server.js (directly)
- ❌ extension
- ❌ studio
- ❌ agents

reads prices or klines directly.

---

## GARDE-FOU D: LISTE DE SYMBOLES CIBLE (PRIORITÉS)

### Phase 1: Support Local (Week 1)

**Symbols to add to MT5 EA immediately:**

```mq5
string targets[] = {
  "XAUUSD",   // Already working
  "EURUSD",   // Major pair, common in brokers
  "GBPUSD",   // Major pair, common
  "USDJPY",   // Major pair, common
};
```

**Why these 4?**
- XAUUSD: Already have (keep)
- EURUSD, GBPUSD, USDJPY: Most common forex pairs
- Available in ALL mt5 brokers (IC Markets, Pepperstone, etc.)
- High trading volume = stable data

**Real coverage by broker (IC Markets example):**
- ✅ EURUSD available
- ✅ GBPUSD available
- ✅ USDJPY available
- ✅ XAUUSD available

**Implementation effort:**
- Modify EA: Add 4 symbols to array
- Test: Verify each symbol writes correctly to mt5_data.json
- **Time: 3-4 hours**

### Phase 2: Selective Expansion (Week 2+)

**If user has these in terminal, can add:**

```mq5
// Optional: Add only if available in your broker terminal
"XAGUSD",     // Silver (common)
"AUDUSD",     // Aussie dollar (common)
"NZDUSD",     // Kiwi (common)
"USDCAD",     // Canadian (common)
"USDCHF",     // Franc (common)
```

**Rule: Only add symbols that:**
1. User can see in MT5 terminal
2. Are actively traded by user
3. Have stable broker data

### Phase 3: Intentionally NOT supporting (clear decision)

**These stay OUT of mt5_data.json:**

```
❌ BTCUSD / ETHUSD
   Reason: MT5 crypto support varies by broker
   If user has crypto in MT5: can be added to Phase 2
   If not: Don't force it, accept limitation

❌ US500, US30, DE40
   Reason: Index data quality varies, not all brokers offer
   If user has indices: can be added
   If not: Accept that indices unavailable locally

❌ Anything not in user's broker terminal
   Reason: Can't fetch data that broker doesn't provide
   Rule: LOCAL ONLY means respecting broker limits
```

### Actually supported (honest list)

**With Phase 1 alone (4 symbols):**

```
✅ XAUUSD   - Gold (MT5 native)
✅ EURUSD   - Euro (any MT5 broker)
✅ GBPUSD   - British Pound (any MT5 broker)
✅ USDJPY   - Japanese Yen (any MT5 broker)
```

**That's real, honest, achievable.**

### MT5 EA Code (actual implementation)

```mq5
// Bridge_MT5_Studio.mq5 (ENHANCED)
// Phase 1: 4 target symbols

#include <json.mqh>  // JSON library

string TARGET_SYMBOLS[] = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY"};

void OnTick() {
  // Build JSON for ALL target symbols
  CJAVal root;
  
  for (int i = 0; i < ArraySize(TARGET_SYMBOLS); i++) {
    string sym = TARGET_SYMBOLS[i];
    
    // Check symbol exists
    if (!SymbolSelect(sym, true)) {
      PrintFormat("Symbol %s not available", sym);
      continue;
    }
    
    // Get current data
    double bid = SymbolInfoDouble(sym, SYMBOL_BID);
    double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
    double price = (bid + ask) / 2;
    
    // Get klines
    int bars = iBars(sym, PERIOD_H1);
    if (bars < 2) continue;
    
    CJAVal klines;
    for (int j = bars - 1; j >= bars - 100; j--) {
      if (j < 0) break;
      
      CJAVal candle;
      candle["time"] = TimeToString(iTime(sym, PERIOD_H1, j), TIME_DATE|TIME_MINUTES);
      candle["open"] = iOpen(sym, PERIOD_H1, j);
      candle["high"] = iHigh(sym, PERIOD_H1, j);
      candle["low"] = iLow(sym, PERIOD_H1, j);
      candle["close"] = iClose(sym, PERIOD_H1, j);
      candle["volume"] = (long)iVolume(sym, PERIOD_H1, j);
      
      klines.Add(candle);
    }
    
    // Add to root JSON
    CJAVal symData;
    symData["symbol"]["name"] = sym;
    symData["symbol"]["bid"] = bid;
    symData["symbol"]["ask"] = ask;
    symData["symbol"]["price"] = price;
    symData["symbol"]["timestamp"] = TimeLocal();
    symData["klines"] = klines;
    
    root[sym] = symData;
  }
  
  // Write to file
  string json = root.Serialize();
  int handle = FileOpen("mt5_data.json", FILE_WRITE|FILE_TXT);
  FileWriteString(handle, json);
  FileClose(handle);
}
```

### server.js integration

```javascript
// Reads mt5_data.json
const mt5Data = JSON.parse(fs.readFileSync('mt5_data.json', 'utf8'));

// Available symbols
const availableSymbols = Object.keys(mt5Data);
// → ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]

app.get('/available-symbols', (req, res) => {
  res.json({
    local: availableSymbols,
    message: 'These symbols have real data in MT5'
  });
});
```

### Reality check

**This is NOT:**
- ❌ "Everything works"
- ❌ "Unlimited symbol coverage"
- ❌ "Fallback to external sources"

**This IS:**
- ✅ "4 major pairs work locally"
- ✅ "User knows exactly what's supported"
- ✅ "Can expand if user adds more to MT5"
- ✅ "Zero dependencies, zero fallback"

---

## CONFIRMATION FINALE

### Je confirme les 4 garde-fous:

**A. Pas de faux graphique** ✅
- Symbole absent = message clair, pas de chart
- Validation stricte: `ok: false` + raison explicite
- Studio affiche message transparent au lieu de graphique

**B. Extension = contexte seulement** ✅
- Extension: Lit URL/title, envoie {symbol, platform}
- Extension: Ne lit PAS DOM for prices
- Extension: Ne call RIEN d'externe
- Extension: Reste < 100 lignes

**C. Tout par data-source-manager** ✅
- Extension contexte → server /api/active-symbol-context → stockage seulement
- Studio query → server /klines → data-source-manager.getSymbolData()
- data-source-manager → symbol-preferences → getEffectivePrice()
- ZERO bypass, ZERO direct reads ailleurs

**D. Liste de symboles (Phase 1)** ✅
- XAUUSD (déjà there)
- EURUSD (nouveau)
- GBPUSD (nouveau)
- USDJPY (nouveau)
- Effort: 3-4 heures EA + test
- Couverture: Honnête et maîtrisée
- Expansible mais intentionnel

---

## READY FOR IMPLEMENTATION

**Quand tu dis "go", j'implémente dans cet ordre:**

1. **Enhance MT5 EA** (3-4h)
   - Add EURUSD, GBPUSD, USDJPY to mt5_data.json
   - Test output format
   - Verify klines quality

2. **Enhance Extension** (1-2h)
   - public/content.js: extractActiveContext()
   - public/background.js: Send to /api/active-symbol-context
   - Test on tradingview.com

3. **Server routes** (1h)
   - POST /api/active-symbol-context (store context)
   - GET /available-symbols (list what's actually available)
   - GET /klines delegates to data-source-manager

4. **Integration test** (1h)
   - Open TradingView EURUSD
   - Verify extension sends context
   - Verify server responds with real klines
   - Verify Studio shows chart

5. **Studio UI** (30min)
   - Add "symbol not available" message handler
   - Show clear messaging when canAnalyze=false

---

**Total: 6-8 hours, deliverable in 1-2 days.**

**Architecture is locked, guardrails in place, symbols defined.**

Tu dis "ok, go" et j'implémente demain.
