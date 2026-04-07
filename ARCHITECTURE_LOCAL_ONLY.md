# ARCHITECTURE LOCALE UNIQUEMENT
## Comparaison de solutions sans API externe dans le flux principal

**Date**: April 3, 2026  
**Constraint**: NO external APIs in main flow  
**Scope**: MT5 + Extension + Local bridges only

---

## CONTEXT RAPPEL

**Problème core:**
- MT5 fournit XAUUSD seulement
- Besoin: couvrir plus de symboles
- Contrainte: SANS dépendre d'Binance, Alpha Vantage, ou autre tiers
- Réalité: Données "gratuites" n'existent pas ← utilisateur maîtrise rien

---

## SOLUTION 1: MT5 MULTI-SYMBOLES (Amélioration EA)

### Concept

Reconfigurer l'EA MT5 pour écrire PLUSIEURS symboles dans mt5_data.json au lieu d'un.

```mq5
// Bridge_MT5_Studio.mq5 (ENHANCED)

// Actuellement:
// - Boucle sur XAUUSD seulement
// - Ecrit 1-2 klines à chaque tick

// Proposé:
// - Boucle sur array de symboles
// - Gère chaque symbole indépendamment
// - Écrit multi-entry dans mt5_data.json

string symbols[] = {"XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD"};

for (int i = 0; i < ArraySize(symbols); i++) {
  string sym = symbols[i];
  
  // Fetch price, klines, indicators for each
  double price = SymbolInfoDouble(sym, SYMBOL_BID);
  
  // Write to mt5_data.json: mt5_data[sym] = {price, klines, ...}
}
```

### mt5_data.json Structure

```json
{
  "XAUUSD": {
    "symbol": {"name": "XAUUSD", "price": 2375.3, "bid": 2375.2, "ask": 2375.4},
    "klines": [{...}, {...}],
    "indicators": {...}
  },
  "EURUSD": {
    "symbol": {"name": "EURUSD", "price": 1.0850, "bid": 1.0849, "ask": 1.0851},
    "klines": [{...}, {...}],
    "indicators": {...}
  },
  "GBPUSD": { ... },
  "BTCUSD": { ... },
  "ETHUSD": { ... }
}
```

### server.js Integration

```javascript
// Read mt5_data.json ONCE per tick from EA
const mt5Data = JSON.parse(fs.readFileSync('mt5_data.json', 'utf8'));

// Serve any symbol
app.get('/klines', (req, res) => {
  const symbol = req.query.symbol || 'XAUUSD';
  const data = mt5Data[symbol];  // Get symbol data from JSON
  
  if (!data) {
    return res.json({ ok: false, error: 'Symbol not in MT5' });
  }
  
  res.json({
    ok: true,
    klines: data.klines,
    source: 'mt5_local',
    symbol: symbol
  });
});
```

### Pros
- ✅ Zero external dependencies
- ✅ All data local, instant access
- ✅ Real-time (tick-level from MT5)
- ✅ Integrates seamlessly with existing system
- ✅ High stability (MT5 ecosystem mature)
- ✅ Works offline (local file)
- ✅ Zero cost
- ✅ Complete price coherence (MT5 is single source)

### Cons
- ❌ Limited to symbols available in MT5 terminal
- ❌ Requires EA reconfiguration + testing
- ❌ Depends on terminal staying open (same as now)
- ❌ Symbol coverage = broker's offering only
- ❌ Effort: 4-6 hours (EA development + testing)

### Coverage

**Depends on broker terminal:**
- Many brokers offer: EURUSD, GBPUSD, XAUUSD, USDJPY, crypto (BTCUSD)
- Some offer 100+ symbols
- **Reality**: If symbol not in terminal, can't get it

**Example IC Markets MT5:**
```
Major Forex: EURUSD, GBPUSD, USDJPY, AUDUSD, etc. (50+)
Metals: XAUUSD, XAGUSD
Crypto: BTCUSD, ETHUSD (if enabled)
Indices: US500, US30, etc. (40+)
Commodities: AAPL, MSFT, etc. (if available)
```

### Integration Complexity

**Inside system:**
- data-source-manager already expects mt5_data.json
- getSymbolData() calls _getKlines()
- ZERO changes needed, just reads more symbols

**Outside system:**
- Modify EA source code (4 hours)
- Test each symbol (2 hours)
- Verify klines quality (1 hour)

### Risk Assessment

| Risk | Mitigation |
|------|-----------|
| EA crash with many symbols | Test incrementally, add symbols one at a time |
| JSON file too large | Keep only last 500 bars per symbol, rotate daily |
| Terminal stability | Same as today (no worse) |
| Symbol not in terminal | Graceful degradation (return empty, canAnalyze=false) |

### Stability

**Very High** - Same as current MT5 ecosystem
- MT5 is stable platform, used by millions
- EA development is mature domain
- JSON writes are atomic
- No external dependency

### Real-world example process

```
Day 1: Add EURUSD to EA
  - Modify EA, add to symbols array
  - Compile, deploy
  - Run 8h, check JSON output
  - Verify klines quality

Day 2: Add GBPUSD, USDJPY
  - Same process
  - Run 16h total

Day 3: Add XAGUSD
  - Continue

Result: mt5_data.json has 5 symbols, all real-time
```

---

## SOLUTION 2: BRIDGE SOCKET LOCAL (WebSocket or TCP)

### Concept

Instead of file-based (mt5_data.json), use **persistent socket connection**.

```
MT5 EA
  ↓ (WebSocket/TCP connection)
Node.js server (ws://localhost:5555)
  ↓ (in-memory storage)
data-source-manager
  ↓
Studio/Extension/Dashboard
```

### MT5 EA Implementation

```mq5
// EA opens TCP/WebSocket connection to localhost:5555
// Sends price updates in real-time
// Server receives, stores in memory

class MT5Bridge {
  // Connect to Node.js on startup
  void Open() {
    socket = new TCPSocket("127.0.0.1", 5555);
  }
  
  // On every tick
  void OnTick() {
    // For each symbol
    for (int i = 0; i < ArraySize(symbols); i++) {
      double price = SymbolInfoDouble(symbols[i], SYMBOL_BID);
      string json = JsonFormat(symbols[i], price, klines);
      
      socket.Send(json);  // Real-time push
    }
  }
}
```

### Node.js Server

```javascript
// server.js
const WebSocket = require('ws');

const wss = new WebSocket.Server({ port: 5555 });

const mt5Cache = {};  // In-memory price cache

wss.on('connection', (ws) => {
  console.log('MT5 EA connected');
  
  ws.on('message', (data) => {
    try {
      const update = JSON.parse(data);
      const { symbol, price, klines } = update;
      
      // Update in-memory cache
      mt5Cache[symbol] = { price, klines, timestamp: Date.now() };
      
      // Broadcast to all connected clients (Studio, Extension)
      broadcast({ type: 'price-update', symbol, price });
    } catch (e) {
      console.error('MT5 parse error:', e);
    }
  });
  
  ws.on('close', () => {
    console.log('MT5 connection lost');
  });
});

// Serve cached data
app.get('/klines/:symbol', (req, res) => {
  const data = mt5Cache[req.params.symbol];
  res.json(data || { error: 'No data' });
});
```

### Pros
- ✅ Real-time push (no polling)
- ✅ Low latency (TCP/WebSocket < file I/O)
- ✅ Persistent connection = instant updates
- ✅ In-memory = very fast reads
- ✅ Zero external APIs
- ✅ Scales to many clients
- ✅ Can maintain history per symbol

### Cons
- ❌ Requires EA development (socket library integration)
- ❌ More complex than file-based
- ❌ Connection loss = data loss (need reconnect logic)
- ❌ Same symbol coverage as MT5 (not all symbols available)
- ❌ Effort: 6-8 hours

### Coverage

**Same as Solution 1:** Limited to broker's terminal symbols

### Integration Complexity

**Inside system:**
```javascript
// data-source-manager.js
class DataSourceManager {
  async getSymbolData(canonical) {
    // Instead of reading file, query in-memory cache
    const data = mt5Cache[canonical];
    return data;
  }
}
```

**Outside system:**
- Implement WebSocket in EA (complex)
- Implement server-side WebSocket handler (easy)
- Test connection stability (medium)

### Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Connection drops | Implement reconnect logic with exponential backoff |
| EA crashes | Keep file fallback (mt5_data.json) as backup |
| Data loss on restart | Write periodic snapshots to disk |
| Multiple clients | Use broadcast pattern (all clients get same data) |

### Stability

**Medium-High** - Depends on connection stability
- WebSocket over localhost = very reliable
- But connection management adds complexity
- File fallback makes it robust

### When to use this over Solution 1

**Solution 1 (file)** = simpler, all-local  
**Solution 2 (socket)** = if you need real-time push to many clients simultaneously

---

## SOLUTION 3: EXTENSION AS CONTEXT-AWARE ROUTER (NO EXTERNAL APIs)

### Concept

Extension detects context (symbol from URL), Server ROUTES based on availability:

```
User opens TradingView: BTCUSD
  ↓
Extension detects: "User wants BTCUSD"
  ↓
Server checks available sources:
  - Is BTCUSD in MT5? YES → Use MT5 local data
  - Is BTCUSD in local cache? YES → Use cache
  - Is BTCUSD unknown? NO DATA → Return empty, canAnalyze=false
  ↓
Studio displays what's available
```

### Extension Enhancement

```javascript
// public/content.js (ENHANCED - NO EXTERNAL CALLS)

function extractSymbolFromContext() {
  // Read from URL: https://www.tradingview.com/chart/BTCUSD
  const url = new URL(location.href);
  const pathParts = url.pathname.split('/');
  const symbol = pathParts[pathParts.length - 1];
  
  return {
    symbol: symbol,      // BTCUSD
    platform: 'tradingview',
    timestamp: Date.now()
  };
}

// Send to background
chrome.runtime.sendMessage({
  type: 'ACTIVE_SYMBOL_CHANGED',
  symbol: symbol,
  context: extractSymbolFromContext()
});
```

### Server Route

```javascript
// server.js
app.post('/api/active-symbol', (req, res) => {
  const { symbol } = req.body;
  
  // Check what we have for this symbol
  const mt5Data = readMT5Data();  // From mt5_data.json
  const hasInMT5 = symbol in mt5Data;
  
  // Check local cache (if using Solution 2)
  const hasInCache = symbol in mt5Cache;
  
  // Return routing info
  res.json({
    symbol: symbol,
    sources: {
      mt5: hasInMT5,
      cache: hasInCache,
      external: false  // No external APIs!
    },
    recommendation: hasInMT5 ? 'mt5' : hasInCache ? 'cache' : 'unavailable'
  });
});

// Studio queries
app.get('/klines/:symbol', (req, res) => {
  const symbol = req.params.symbol;
  
  // Try MT5 first
  const mt5Data = readMT5Data();
  if (mt5Data[symbol]) {
    return res.json({
      ok: true,
      klines: mt5Data[symbol].klines,
      source: 'mt5_local'
    });
  }
  
  // Fallback: return nothing
  res.json({
    ok: false,
    error: 'Symbol not available',
    message: 'Add to MT5 terminal or switch to supported symbol'
  });
});
```

### Pros
- ✅ Zero external dependencies
- ✅ Very transparent (user knows what's available)
- ✅ No false promises (canAnalyze=false for unknown symbols)
- ✅ Extension is minimal (just context detection)
- ✅ Integrates with data-source-manager perfectly

### Cons
- ❌ Limited to symbols in MT5
- ❌ No automatic coverage expansion
- ❌ User must actively manage symbols in terminal
- ❌ Not transparent to end user (blank chart for unsupported symbols)

### Coverage

**HONEST** - Shows what's actually available
- If BTCUSD in MT5: works
- If BTCUSD not in MT5: doesn't work (transparent)
- No hidden dependencies, no "magic"

### Integration Complexity

**EASY**
- Extension: 50 lines
- Server: 30 lines
- data-source-manager: 5 lines
- **Total: 2 hours**

### Risk Assessment

| Risk | Mitigation |
|------|-----------|
| User confused by blank charts | Show clear message: "Add symbol to MT5 to enable" |
| Symbol in URL but not in MT5 | canAnalyze=false, validation.reasons = ["Not in MT5"] |
| Extension breaks | Fallback: Manual symbol selection in Studio |

### Stability

**Very High** - No external dependencies, no fragility

---

## SOLUTION 4: LOCAL CSV/DATABASE COLLECTOR

### Concept

Create a local process that collects and maintains **historical data** from sources user controls.

```
User owns data → Local DB (SQLite)
                 ↓
          data-source-manager
                 ↓
          Studio/Extension
```

### Implementation

```javascript
// lib/local-data-collector.js

const sqlite3 = require('sqlite3');
const fs = require('fs');

class LocalDataCollector {
  constructor() {
    this.db = new sqlite3.Database('./trading-data.db');
    this.initializeSchema();
  }

  initializeSchema() {
    this.db.run(`
      CREATE TABLE IF NOT EXISTS klines (
        id INTEGER PRIMARY KEY,
        symbol TEXT,
        timestamp INTEGER,
        open REAL, high REAL, low REAL, close REAL,
        volume INTEGER,
        source TEXT,
        created_at INTEGER,
        UNIQUE(symbol, timestamp)
      )
    `);
  }

  // Ingest data from user's exported CSV
  async ingestCSV(filePath, symbol) {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');
    
    for (const line of lines.slice(1)) {  // Skip header
      const [time, open, high, low, close, volume] = line.split(',');
      
      const timestamp = new Date(time).getTime() / 1000;
      
      this.db.run(
        `INSERT OR IGNORE INTO klines 
         (symbol, timestamp, open, high, low, close, volume, source, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [symbol, timestamp, open, high, low, close, volume, 'user-csv', Date.now()]
      );
    }
  }

  // Query klines
  async getKlines(symbol, limit = 500) {
    return new Promise((resolve, reject) => {
      this.db.all(
        `SELECT * FROM klines WHERE symbol = ? 
         ORDER BY timestamp DESC LIMIT ?`,
        [symbol, limit],
        (err, rows) => {
          if (err) reject(err);
          resolve(rows?.reverse() || []);  // Oldest first
        }
      );
    });
  }
}

module.exports = LocalDataCollector;
```

### Server Integration

```javascript
// server.js
const LocalDataCollector = require('./lib/local-data-collector');
const collector = new LocalDataCollector();

// Endpoint to import user's CSV
app.post('/import-csv', (req, res) => {
  const { filePath, symbol } = req.body;
  
  try {
    collector.ingestCSV(filePath, symbol);
    res.json({ ok: true, message: `Imported ${symbol} from ${filePath}` });
  } catch (e) {
    res.status(400).json({ ok: false, error: e.message });
  }
});

// Serve from local DB
app.get('/klines/:symbol', async (req, res) => {
  const klines = await collector.getKlines(req.params.symbol);
  
  res.json({
    ok: klines.length > 0,
    klines: klines,
    source: 'local-database',
    count: klines.length
  });
});
```

### Pros
- ✅ Zero external dependencies forever
- ✅ User owns all data (stored locally)
- ✅ Can import from any source (past exports)
- ✅ Persistent storage (survives restart)
- ✅ Can accumulate data over time

### Cons
- ❌ Manual data import process
- ❌ Not automated (requires user action)
- ❌ Historical data only (not real-time)
- ❌ User must source the data themselves
- ❌ Doesn't help with real-time updates

### Coverage

**User-defined**: Whatever data user imports

### Integration Complexity

**Medium**
- SQLite integration: easy (npm sqlite3)
- CSV import: easy
- data-source-manager: needs to query DB instead of file
- Effort: 3-4 hours

### Use case

**Best for**: Backtesting, analysis with known historical data
**Not for**: Real-time trading (no live updates)

---

## COMPARISON TABLE

| Factor | MT5 Multi | Socket Bridge | Extension Context | Local DB |
|--------|-----------|---------------|-------------------|----------|
| **External APIs** | ❌ None | ❌ None | ❌ None | ❌ None |
| **Real-time** | ✅ Tick | ✅ Real-time push | ❌ No | ❌ No |
| **Stability** | Very High | Medium-High | Very High | Very High |
| **Latency** | ~500ms | <100ms | N/A | N/A |
| **Coverage expansion** | Moderate | Moderate | None (honest) | User-defined |
| **Complexity** | 4-6h | 6-8h | 2h | 3-4h |
| **Maintenance** | Low | Low | Very Low | Low |
| **Works offline** | ✅ Yes | ❌ No | ✅ Yes | ✅ Yes |
| **Scalability** | MT5 limits | Unlimited clients | High | DB size limited |
| **Best for** | Multi-symbol real-time | Real-time + many clients | Context awareness | Historical data |

---

## MY FINAL RECOMMENDATION

### **Choose: SOLUTION 1 (MT5 Multi-Symbols) + SOLUTION 3 (Extension Context)**

**Hybrid approach:**

```
MT5 EA (Enhanced)
  └─ Writes EURUSD, GBPUSD, XAUUSD, XAGUSD to mt5_data.json
    
server.js
  └─ Reads mt5_data.json
  
Extension
  └─ Detects active symbol from URL
  └─ Posts context to /api/active-symbol
  
Studio
  └─ Queries /klines/:symbol
  └─ Gets available data from MT5
  └─ Shows chart if available
  └─ Shows "unavailable" if symbol not in MT5
```

### Why this combination:

1. **No external APIs ever**
   - MT5 local data only
   - Extension doesn't call any external service
   - Everything stays on your machine

2. **Real implementation**
   - MT5 is proven, stable platform
   - Extension enhancement is simple (50 lines)
   - Integration is clean

3. **Honest coverage**
   - If symbol in MT5: works perfectly
   - If symbol not in MT5: transparent (shows unavailable)
   - No false promises

4. **Effort is reasonable**
   - MT5 EA enhancement: 4-6 hours
   - Extension: 2 hours
   - Server integration: 1 hour
   - **Total: 7-9 hours** (one working day)

5. **Integrates perfectly with existing**
   - data-source-manager.js: ZERO changes
   - symbol-preferences.js: ZERO changes
   - server.js: Add 1 route
   - Extension: 50 new lines

### How it works step-by-step

```
Day 1: Enhance MT5 EA
  Step 1: Modify bridge to handle multiple symbols
  Step 2: Test with 3-5 major pairs
  Step 3: Verify json structure
  
Day 2: Deploy + Test
  Step 1: Enhance extension content.js (context extraction)
  Step 2: Add /api/active-symbol route in server
  Step 3: Verify extension sends context
  
Day 3: Integration
  Step 1: Update data-source-manager to use context
  Step 2: Test Studio with different symbols
  Step 3: Verify charts appear/disappear as expected
```

### Result

```
User opens TradingView: EURUSD
  ↓ (Extension detects from URL)
Studio shows: EURUSD
  ↓ (If in MT5)
Chart displays 100+ real klines
  ↓
canAnalyze = true
  ↓
Agent can analyze

User opens TradingView: DOGECOIN
  ↓ (Extension detects)
Studio shows: DOGECOIN
  ↓ (Not in MT5 terminal)
Chart shows: "Add to MT5 to enable"
  ↓
canAnalyze = false
  ↓
Agent waits / acknowledges symbol
```

### Why NOT the other solutions in main flow

**Solution 2 (Socket)** = Better latency but same complexity as Solution 1. Keep as future enhancement after Solution 1 works.

**Solution 4 (Local DB)** = Only for historical analysis, not live trading.

---

## IMMEDIATE NEXT STEP

**Validate this approach:**
- Is modifying MT5 EA acceptable? (Yes/No)
- Which symbols do you want in MT5? (List them)
- Should we do Solution 1 first, then add Solution 2 later?

If yes → I implement MT5 EA enhancement + Extension context bridge.

---

**This recommendation respects:**
- ✅ No external APIs in main flow
- ✅ Local/maîtrisée (you control everything)
- ✅ Stable (MT5 + file-based)
- ✅ Doesn't break existing system
- ✅ Real implementation (not theoretical)
