# 🏗️ TRADING-AUTO COMPLETE ARCHITECTURE

**Version:** 1.0.0  
**Last Updated:** 2026-04-01  
**Status:** Production-Ready Multi-AI System  

---

## 📋 TABLE OF CONTENTS
1. [System Overview](#system-overview)
2. [File Structure & Organization](#file-structure--organization)
3. [Core Components](#core-components)
4. [Data Flow & Communication](#data-flow--communication)
5. [API Routes](#api-routes)
6. [Agent System](#agent-system)
7. [Symbol Normalization](#symbol-normalization)
8. [AI Coordination](#ai-coordination)
9. [Troubleshooting](#troubleshooting)

---

## 🎯 SYSTEM OVERVIEW

**Trading-Auto** is a multi-AI trading platform that combines:
- ✅ Real-time market data from MT5 + Yahoo Finance + TradingView
- ✅ Technical analysis via coordinated agents
- ✅ Risk management & position tracking
- ✅ TradingView extension for live symbol detection
- ✅ Studio frontend for visualization & control
- ✅ Multi-AI system for autonomous operation

**Architecture Pattern:** Server-based backend + Browser-based frontend + Extension connector

---

## 📁 FILE STRUCTURE & ORGANIZATION

```
trading-auto/
├── 🔵 SERVER CORE
│   ├── server.js                    [CRITICAL] Backend server (Express, port 4000)
│   ├── AGENT_BUS.json               [CRITICAL] AI coordination protocol
│   ├── SYSTEM_LOG.json              System event log
│   └── package.json                 Node.js dependencies
│
├── 🔧 BACKEND MODULES
│   ├── store/
│   │   └── market-store.js          [CRITICAL] In-memory market data store
│   │
│   ├── lib/
│   │   ├── symbol-normalizer.js     [CRITICAL] Symbol mapping engine
│   │   └── zone-manager.js          Support/Resistance zones
│   │
│   ├── src/agents/                  [CRITICAL] Coordinated AI agents
│   │   ├── orchestrator.js          Master coordinator
│   │   ├── trading-core.js          Trade execution logic
│   │   ├── technicalAgent.js        RSI/EMA/Bollinger calculations
│   │   ├── macroAgent.js            Economic data analysis
│   │   ├── newsAgent.js             News sentiment analysis
│   │   ├── riskManager.js           Position sizing & SL/TP
│   │   ├── supervisor.js            Overall system monitor
│   │   ├── coordinator.js           Price data coordinator
│   │   ├── stateManager.js          State persistence
│   │   ├── syncManager.js           Data synchronization
│   │   ├── tradeValidator.js        Trade validation rules
│   │   ├── chartEngine.js           Candle computation
│   │   ├── dataSourceManager.js     Data source routing
│   │   ├── market-state.js          Market conditions
│   │   ├── timeframe-consensus.js   Multi-TF validation
│   │   ├── designerAgent.js         Trade setup design
│   │   ├── fear-index.js            Market fear gauge
│   │   ├── qaTester.js              Quality assurance
│   │   ├── setupClassifier.js       Trade setup classification
│   │   ├── strategyManager.js       Strategy coordination
│   │   ├── trade-logic.js           Entry/exit logic
│   │   └── news-intelligence.js     News processing
│   │
│   └── services/
│       └── fileService.js           File I/O utilities
│
├── 🎨 FRONTEND (STUDIO)
│   └── studio/
│       ├── index.html               [CRITICAL] Main UI (contains all sections)
│       ├── studioapp.js             [CRITICAL] UI logic & API calls
│       ├── studiostyles.css         UI styling
│       ├── app.js                   Alternative entry point
│       └── styles.css               Additional styles
│
├── 🌐 BROWSER EXTENSION (TradingView)
│   └── tradingview-analyzer/
│       ├── manifest.json            [CRITICAL] Extension manifest (v3)
│       ├── background.js            Service worker (extension lifecycle)
│       ├── content.js               [CRITICAL] DOM access + relay
│       ├── injected.js              [CRITICAL] Page context script
│       ├── popup.js                 [CRITICAL] Extension UI
│       ├── popup.html               Extension UI template
│       └── styles.css               Extension styling
│
└── 📊 OTHER
    ├── README.md                    User guide
    ├── CHECKLIST.md                 Development checklist
    └── analysis/                    Analysis tools
```

---

## 🔧 CORE COMPONENTS

### 1️⃣ **server.js** — Backend Server
**Purpose:** HTTP API server for studio + bridge from TradingView  
**Port:** 4000 (hardcoded)  
**Responsibilities:**
- Receive market data from MT5
- Serve /studio frontend
- Execute API routes
- Relay data to SSE clients
- Coordinate with agents

**Key Variables:**
- `marketStore` — Central data repository
- `normalizeSymbol()` — Symbol mapper
- `orchestrator` — Agent coordinator
- `zoneManager` — Support/Resistance zones

**Init Sequence:**
```
1. Load dependencies (market-store, symbol-normalizer, orchestrator)
2. Setup CORS + JSON middleware
3. Register routes (/health, /mt5, /quote, /analyze, etc.)
4. Start listening on :4000
```

### 2️⃣ **market-store.js** — Singleton Data Store
**Purpose:** Single source of truth for market data  
**Key Methods:**
- `updateFromMT5(payload, symbol)` — Receive MT5 data
- `updateAnalysis(symbol, analysis)` — Cache analysis
- `addSSEClient(res)` — Register browser client
- `broadcast(data)` — Send to all connected clients
- `getLatestForSymbol(symbol)` — Query data

**Data Structure:**
```javascript
{
  bySymbol: {
    "XAUUSD": {
      latestPayload: { symbol, bid, ask, time, ... },
      latestAnalysis: { rsi, ema, trend, ... },
      updatedAt: 1234567890
    }
  },
  systemStatus: { source: "mt5", fluxStatus: "LIVE" },
  analysisCache: { ... },
  sseClients: [ ... ]
}
```

### 3️⃣ **symbol-normalizer.js** — Critical Symbol Engine
**Purpose:** Convert broker symbols → canonical form  
**Key Features:**
- 50+ defined profiles (XAUUSD, EURUSD, BTCUSD, etc.)
- Pattern matching for variants (GOLD, XAU/USD, XAUUSDmicro, etc.)
- Asset type classification (metal, forex, crypto, index)
- Proper pip calculation per asset type

**Example Usage:**
```javascript
const {normalizeSymbol} = require('./lib/symbol-normalizer');
const profile = normalizeSymbol('XAUUSD.a'); // Returns canonical profile
// → { canonical: 'XAUUSD', type: 'metal', digits: 2, pip: 0.1, ... }
```

**Symbol Mapping Rules:**
1. **Exact match** — Direct PROFILES lookup
2. **Pattern match** — Regex CANONICAL_PATTERNS
3. **Default** — Generic profile with stripped name

### 4️⃣ **orchestrator.js** — Master Agent Coordinator
**Purpose:** Orchestrate all agents for analysis  
**Workflow:**
1. Receive market data
2. Dispatch to technical/macro/news agents
3. Collect results
4. Generate consensus recommendation
5. Broadcast to clients

**Agents it uses:**
- technicalAgent (RSI, EMA, Bollinger)
- macroAgent (economic data)
- newsAgent (sentiment)
- riskManager (position sizing)

---

## 🔄 DATA FLOW & COMMUNICATION

### **Real-Time Data Pipeline**

```
┌─────────────────┐
│   MT5 / Broker  │ (Real trading data)
└────────┬────────┘
         │ POST /mt5
         ▼
┌─────────────────────────────────────┐
│  server.js                          │
│  ├─> route: POST /mt5 { price... }  │
│  ├─> normalizeSymbol()              │
│  └─> marketStore.updateFromMT5()    │
└──────┬──────────────────────────────┘
       │ .broadcast() via SSE
       │── TradingView Extension (popup ← data)
       │── Studio Browser (index.html ← SSE)
       ▼
┌─────────────────────────────────────┐
│  Agents (src/agents/)               │
│  ├─> technicalAgent: RSI, EMA       │
│  ├─> macroAgent: Economic           │
│  ├─> newsAgent: Sentiment           │
│  └─> riskManager: Position sizing   │
└─────┬───────────────────────────────┘
      │ marketStore.updateAnalysis()
      │
      ▼
┌─────────────────┐
│  ANALYSIS CACHE │
└─────────────────┘
```

### **Extension ↔ Backend**

```
TradingView Page
   ↓ (DOM query symbol)
injected.js
   ↓ (window.postMessage)
content.js
   ↓ (chrome.runtime.sendMessage)
popup.js
   ↓ (fetch /quote?symbol=XAUUSD)
server.js
   ↓ (marketStore.getLatestForSymbol)
┌────────────────────┐
│ Market Data        │
│ (bid/ask/time)     │
└────────────────────┘
```

---

## 🛣️ API ROUTES

### **Core Routes**
| Route | Method | Purpose | Response |
|-------|--------|---------|----------|
| `/health` | GET | System status | `{ ok, version, source }` |
| `/mt5` | POST | Receive market data | `{ ok, symbol, updated }` |
| `/quote` | GET | Get latest price | `{ bid, ask, time, symbol }` |
| `/analyze` | POST | Run analysis | `{ rsi, ema, trend, recommendation }` |
| `/klines` | GET | Get candles | `{ candles: [{time,o,h,l,c,v}] }` |
| `/positions` | GET | Get open positions | `{ positions: [...] }` |
| `/trade` | POST | Execute trade | `{ ok, orderId, ... }` |
| `/agents-report` | GET | Agent analysis | `{ agents: [...] }` |
| `/calendar` | GET | Economic calendar | `{ events: [...] }` |
| `/news` | GET | Latest news | `{ articles: [...] }` |
| `/stream` | GET | SSE stream | EventStream |
| `/market-intelligence` | GET | Market summary | `{ setup, levels, fear }` |

### **Example Calls**
```bash
# Get price
curl "http://127.0.0.1:4000/quote?symbol=XAUUSD"

# Run analysis
curl -X POST http://127.0.0.1:4000/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol":"XAUUSD","timeframe":"H1"}'

# Get candles
curl "http://127.0.0.1:4000/klines?symbol=XAUUSD&tf=H1"

# Stream updates (SSE)
curl http://127.0.0.1:4000/stream
```

---

## 🤖 AGENT SYSTEM

### **Agent Roles**

| Agent | Input | Output | Frequency |
|-------|-------|--------|-----------|
| **technicalAgent** | Candles, timeframe | RSI, EMA, Bollinger, trend | Per candle close |
| **macroAgent** | Economic calendar | Event impact, strength | Hourly |
| **newsAgent** | News feed | Sentiment score, keywords | 15-30 sec |
| **riskManager** | Entry price, account | SL/TP levels, lot size | Per trade |
| **supervisor** | All agents | Health check, alerts | 5 min |
| **coordinator** | Multiple sources | Price consensus | Real-time |
| **tradeValidator** | Trade setup | Validation pass/fail | Per setup |
| **designerAgent** | Market state | Trade setup design | On-demand |

### **Orchestrator Workflow**
```javascript
// Orchestrator dispatches to agents
await orchestrator.analyzeSymbol('XAUUSD', 'H1')
  .then(result => {
    // result = { 
    //   technical: {...},
    //   macro: {...},
    //   news: {...},
    //   risk: {...},
    //   consensus: {...}
    // }
    marketStore.updateAnalysis('XAUUSD', result);
    broadcastToStudio(result);
  })
```

---

## 🏷️ SYMBOL NORMALIZATION ENGINE

### **Purpose**
Convert any broker/exchange symbol representation to canonical internal form, maintaining price integrity.

### **Profile Structure**
```javascript
{
  canonical: 'XAUUSD',              // Standard name
  type: 'metal',                    // Asset class
  category: 'gold',                 // Subcategory
  digits: 2,                        // Display decimals
  contractSize: 100,                // Units per lot
  tickSize: 0.01,                   // Minimum price move
  tickValue: 1.00,                  // Monetary value of tick
  pip: 0.1,                         // 1 pip in price
  slPct: 0.004,                     // Default SL % 
  tpPct: 0.012                      // Default TP %
}
```

### **Mapping Examples**
```
Input: "XAUUSD.a"     → Canonical: XAUUSD
Input: "GOLDmicro"    → Canonical: XAUUSD
Input: "XAU/USD"      → Canonical: XAUUSD
Input: "GOLD"         → Canonical: XAUUSD
Input: "XAUUSD.cash"  → Canonical: XAUUSD
Input: "EURUSD"       → Canonical: EURUSD
Input: "BTC"          → Canonical: BTCUSD
Input: "BTCUSD"       → Canonical: BTCUSD
```

### **Price Tolerance**
```javascript
// Check if backend price is acceptable
const allowed = checkPriceTolerance(tvPrice, backendPrice, symbol);
// Tolerance: assets within 0.5% of TradingView price = OK
// Beyond 0.5% = ALERT and search alternative sources
```

---

## 🧠 AI COORDINATION PROTOCOL

### **AGENT_BUS.json Structure**

**Purpose:** Communication file between Claude (backend) and Copilot (frontend)

**Usage:**
1. Claude reads `AGENT_BUS.json`
2. Claude writes task in `tasks.pending`
3. Copilot reads task from `pending`
4. Copilot moves to `tasks.inProgress`
5. Copilot completes work
6. Copilot writes result in `tasks.done`
7. Claude reads result and integrates

**File Format:**
```json
{
  "roles": {
    "claude": {
      "scope": ["server.js", "src/agents/", "store/", "..."],
      "status": "active"
    },
    "copilot": {
      "scope": ["studio/", "tradingview-analyzer/"],
      "status": "waiting"
    }
  },
  "tasks": {
    "pending": [
      {
        "id": "T001",
        "priority": 1,
        "from": "claude",
        "to": "copilot",
        "title": "Fix CSS classes",
        "files": ["studio/index.html"],
        "acceptanceCriteria": "..."
      }
    ],
    "inProgress": [],
    "done": [
      {
        "id": "T000",
        "result": "Completed successfully",
        "filesModified": ["studio/index.html"],
        "timestamp": "2026-04-01T12:30:00Z"
      }
    ]
  },
  "rules": {
    "claude": ["Don't touch copilot.scope", "Backend only"],
    "copilot": ["Don't touch server.js", "Frontend only"]
  }
}
```

### **Task Lifecycle**
```
PENDING → IN_PROGRESS → DONE
  ↓           ↓          ↓
Claude   Copilot    Claude reads
writes   modifies   result
```

---

## 🔍 TROUBLESHOOTING

### **Extension Not Detecting Symbol**
1. Check if `injected.js` is loaded: DevTools → Sources → injected.js
2. Verify XPath selector for symbol: ✓ `document.querySelector('[class*="symbol-text"]')`
3. Check console for `[content.js]` messages
4. Ensure manifest.json permissions include current TradingView URL

### **Price Mismatch (TV ≠ Studio)**
1. Check `symbol-normalizer.js` profiles (is symbol recognized?)
2. Verify `market-store.js` is receiving PT5 updates: `GET /health`
3. Check SSE connection: Browser DevTools → Network → stream
4. Review `SYSTEM_LOG.json` for data processing errors

### **Studio not updating**
1. Server running? `curl http://127.0.0.1:4000/health`
2. Check browser console for fetch errors
3. Verify SSE client registration in `market-store.js`
4. Check `studioapp.js` event listeners initializing

### **Agent Analysis Empty**
1. Check if `orchestrator.js` is imported in server.js
2. Verify agents in `src/agents/` are exporting functions
3. Run `testSystem()` button in studio
4. Check `SYSTEM_LOG.json` for agent errors

### **Extension Popup Blank**
1. Check `popup.js` is working: ExtensionID → inspect popup
2. Verify `content.js` relay working: `chrome.runtime.sendMessage()` logs
3. Check backend `/quote` route responding: `curl http://127.0.0.1:4000/quote?symbol=XAUUSD`
4. Check CORS headers in `server.js`

---

## 👥 FOR OTHER AIs (Copilot, etc.)

**If this AI becomes unavailable:**

1. **Read this document first** to understand architecture
2. **Check AGENT_BUS.json** for pending tasks
3. **Verify server.js is running** on port 4000
4. **Check market-store.js** for data flow issues
5. **Use symbol-normalizer.js** for symbol handling
6. **Run testSystem() in studio** to diagnose

**Scope Boundaries:**
```
✅ BACKEND (Claude): server.js, src/agents/, store/, lib/, trading/
❌ FRONTEND (Copilot): studio/, tradingview-analyzer/
```

**Never edit across scope boundaries without updating AGENT_BUS.json**

---

## 📞 GETTING HELP

For other AIs to continue:
- This document explains everything
- AGENT_BUS.json shows what needs doing
- SYSTEM_LOG.json shows what went wrong
- Code comments explain "why" not just "what"

**Success = System runs autonomously without human intervention. 🎯**
