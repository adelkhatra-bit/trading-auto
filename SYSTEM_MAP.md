# 🗺️ SYSTEM_MAP - Cartographie Architecturale Complète

**Generated:** 2026-04-03 08:20  
**Status:** 🟢 COMPLETE MAPPING IN PROGRESS  

---

## 1. ARCHITECTURE DE HAUT NIVEAU

```
┌─────────────────────────────────────────────────────────────┐
│                    EXPRESS SERVER (port 4000)                │
├─────────────────────────────────────────────────────────────┤
│  server.js (2800+ lines, main entry point)                  │
│  - Manages 70+ routes                                       │
│  - Coordination multi-sources (MT5, TradingView, Yahoo)     │
│  - Real-time data aggregation                               │
│  - Agent orchestration                                       │
└─────────────────────────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────────────────────────────┐
│                       UI LAYER (4 portals)                           │
├──────────────────────────────────────────────────────────────────────┤
│ Portal 1: STUDIO (index-simple.html) - Main trading interface        │
│           └─ LightweightCharts v4.1.3 + Real-time symbols           │
│                                                                       │
│ Portal 2: DASHBOARD (dashboard.html) - MT5 data viewer              │
│           └─ Symbol mapping + price display                         │
│                                                                       │
│ Portal 3: POPUP (popup.html) - Extension UI                         │
│           └─ Price registration + quick actions                     │
│                                                                       │
│ Portal 4: AGENT_LOG (agent-log-page.html) - Hub central             │
│           └─ Agent status + system monitoring                       │
└──────────────────────────────────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────────────────────────────┐
│                     AGENT SYSTEM (23+ agents)                        │
├──────────────────────────────────────────────────────────────────────┤
│ ORCHESTRATION LAYER:                                                 │
│  ├─ orchestrator.js (ACTIVE) - Main agent coordinator               │
│  ├─ coordinator.js (ACTIVE) - Alternative entry point               │
│  └─ continuous-loop.js - Background processing                      │
│                                                                       │
│ ANALYSIS LAYER:                                                      │
│  ├─ newsAgent.js (ACTIVE) - News analysis                           │
│  ├─ news-intelligence.js (ACTIVE) - Fallback intelligence            │
│  ├─ macroAgent.js - Economic calendar                               │
│  ├─ market-state.js - Market conditions assessment                  │
│  ├─ fear-index.js - Sentiment analysis                              │
│  ├─ trading-core.js - Core trading logic                            │
│  ├─ trade-logic.js - Position management                            │
│  └─ 15+ specialized agents (see AGENTS_INVENTORY)                   │
│                                                                       │
│ DATA LAYER:                                                          │
│  ├─ symbol-preferences.js (SERVICE) - User symbols + prices         │
│  ├─ dataSourceManager.js (AGENT) - Data coordination                │
│  └─ marketStore (MEMORY) - Real-time cache                          │
└──────────────────────────────────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────────────────────────────┐
│                    DATA SOURCES (3-tier priority)                     │
├──────────────────────────────────────────────────────────────────────┤
│ TIER 1: MT5 (Priority 1)                                             │
│         └─ mt5_bridge.py + mt5_data.json                            │
│                                                                       │
│ TIER 2: TradingView (Priority 2)                                     │
│         └─ Extension bridge (content.js + background.js)            │
│                                                                       │
│ TIER 3: Yahoo Finance (Priority 3)                                  │
│         └─ Klines only (fallback)                                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. ENDPOINT MAP (70+ routes)

### **CORE PORTALS** (HTML Serving)
```
GET  /                          → index.html (MAIN MENU)
GET  /studio                    → studio/index-simple.html (USED)
GET  /studio/                   → studio/index-simple.html (USED)
GET  /audit                     → audit-dashboard.html (STATUS)
GET  /dashboard                 → dashboard.html (MT5 VIEWER)
GET  /popup                     → popup.html (EXTENSION)
GET  /agent-log                 → agent-log-page.html (HUB)
GET  /agents-monitor            → AGENTS_MONITOR.html (MONITORING)
GET  /extension-test            → EXTENSION_TEST.html (TEST)
GET  /test-analysis             → test-analysis.html (TEST)
GET  /test-chart                → test-chart-visual.html (TEST)
```

### **MT5 DATA** (Real Market Data)
```
GET  /mt5/latest                → Real-time price + candles
GET  /mt5/price                 → Current bid/ask/volume
GET  /mt5/klines                → OHLC historical candles
GET  /mt5/symbols               → Available symbol list
GET  /mt5/symbol/:symbol        → Specific symbol info
GET  /mt5/status                → Connection status
GET  /mt5/connection            → Bridge connection check
GET  /mt5/detect                → Auto-detect MT5 instance
```

### **SYMBOL MAPPING** (Symbol Resolution)
```
POST /match-symbol              → Resolve TV symbol → Broker
GET  /match-symbol/:tvSymbol    → Get broker mapping
POST /mapping/resolve           → Manual symbol resolution
POST /mapping/save              → Save user mapping
GET  /mapping/list              → List saved mappings
```

### **ANALYSIS** (Agent Results)
```
GET  /analyze                   → Run symbol analysis
GET  /positions                 → Current open positions
GET  /agents-report             → All agents report
GET  /market-intelligence       → Market analysis summary
GET  /latest/:symbol            → Latest symbol analysis
```

### **AGENT CONTROL** (Orchestration)
```
GET  /agent-status              → Agent state
GET  /agent-activity            → Recent actions
GET  /agent-bus                 → Inter-agent messaging
POST /agent-screen              → Run agent screen
POST /agent-filtre              → Filter agent results
GET  /orchestration-status      → Orchestrator state
POST /orchestration/enable      → Enable orchestration
POST /orchestration/disable     → Disable orchestration
POST /orchestration/run-now     → Force run cycle
```

### **NEWS & CALENDAR** (Sentiment/Events)
```
GET  /calendar                  → Economic calendar
GET  /news                      → Latest news
GET  /market-news               → Market-specific news
GET  /economic-calendar         → Full calendar
GET  /economic-events           → Upcoming events
```

### **TRADING OPERATIONS** (Live)
```
POST /trade                     → Execute trade (paper/live)
GET  /broker-mode               → Paper/Live mode
POST /broker-mode               → Switch mode
POST /broker-select             → Select broker
GET  /broker-config/:broker     → Broker settings
```

### **LIVE STREAMING** (Real-time SSE)
```
GET  /stream                    → Server-sent events
POST /tv-bridge                 → TradingView data push
GET  /instant-trade-live        → Live trade execution
POST /instant-trade-live        → Submit trade
GET  /state                     → Current system state
```

### **UI DATA** (Studio endpoints)
```
GET  /studio/data               → Studio view data
GET  /studio/agent-screen       → Agent analysis for studio
GET  /studio/mapping-list       → Available symbols
GET  /studio/mapping/:input     → Resolve symbol
POST /studio/mapping-save       → Save symbol mapping
POST /studio/system-log         → Log from studio
GET  /studio/system-log         → Studio logs
```

### **PYTHON BRIDGE** (MT5 Connection)
```
POST /pip/install               → Install Python dependencies
POST /pip/stop                  → Stop bridge
GET  /pip/check                 → Bridge health
POST /bridge/start              → Start MT5 bridge (python)
POST /bridge/stop               → Stop bridge
```

### **AUDIT & LOGGING**
```
GET  /health                    → Server health
POST /audit/log                 → Log audit event
GET  /audit/state               → Audit state
GET  /audit/events              → Audit event stream
GET  /audit/health              → Audit system health
POST /system-log                → System logging
GET  /system-log                → Get system logs
POST /button-log                → UI button clicks
GET  /button-log                → Get button logs
POST /ai-repair-request         → Request AI fix
GET  /ai-repair-request/:id     → Get AI fix status
```

### **ZONES & CHARTS** (Technical Analysis)
```
POST /zones                     → Create support/resistance
GET  /zones/:symbol             → Get zones
GET  /chart-data                → Chart candles + zones
```

### **UTILITY**
```
GET  /toggle-mode               → Get engine mode
POST /toggle-mode               → Switch engine mode
GET  /quote                     → Symbol quote
POST /analyze-screenshot        → AI screenshot analysis
POST /tasks/update              → Task management
GET  /tasks                     → Get tasks
POST /logs                      → Add log
GET  /logs                      → Get logs
GET  /active-symbol             → Current active symbol
POST /active-symbol             → Set active symbol
```

---

## 3. HTML INVENTORY (Active vs Inactive)

### ✅ ACTIVE (In Use)
```
Root Level:
  ✅ index.html (490 lines)
     └─ Main menu + 8 portal cards
     └─ Links: /studio, /dashboard, /popup, /test-analysis, 
                /EXTENSION_TEST, /AGENTS_MONITOR, /audit-dashboard

  ✅ audit-dashboard.html (system status)
  ✅ dashboard.html (280 lines, MT5 viewer)
  ✅ popup.html (359 lines, Extension UI v1)
  ✅ agent-log-page.html (900 lines, HUB CENTRAL)
  ✅ AGENTS_MONITOR.html (400 lines, monitoring)
  ✅ test-analysis.html (120 lines, test)
  ✅ test-chart-visual.html (test)

Studio:
  ✅ studio/index-simple.html (300 lines)
     └─ LightweightCharts v4.1.3
     └─ Calls studioapp-simple.js
     └─ Used by: GET /studio

Other:
  ✅ studio/studioindex.html (archival, NOT used)
  ? tradingview-analyzer/popup.html (Extension v2, check usage)
  ? public/popup.html (check if used)
```

### ❌ INACTIVE / OLD
```
  ❌ studio/index.html (used index-simple instead)
  ❌ studio/index_old.html (clearly old)
```

### 🤔 DUPLICATE SOURCES (Need Analysis)
```
  popup.html (root) + tradingview-analyzer/popup.html (extension v2)
     → Only ONE should be active
     
  public/popup.html + popup.html
     → Check which is actually served
     
  public/server.js (separate Node server?)
     → Not imported anywhere (safe delete?)
```

---

## 4. AGENT INVENTORY (23+ agents mapped)

### **Core Orchestration**
```
✅ orchestrator.js
   - Exports: { run }
   - Purpose: Main agent coordinator
   - Called by: server.js line ~1369

✅ coordinator.js  
   - Exports: { runAgentCycle }
   - Purpose: Alternative orchestration entry
   - Called by: server.js line 1371, 1373
```

### **Analysis Pipeline**
```
✅ newsAgent.js
   - Exports: newsAgent (full object)
   - Purpose: News analysis + sentiment
   - Called by: server.js, agent-log-page.html

✅ news-intelligence.js
   - Exports: { analyze, getUpcomingEvents }
   - Purpose: Intelligence gathering
   - Called by: server.js + orchestrator.js

✅ macroAgent.js
   - Exports: { getEconomicCalendar, analyzeEconomicImpact }
   - Purpose: Macro analysis

✅ market-state.js
   - Exports: { assess }
   - Purpose: Market conditions

✅ fear-index.js
   - Exports: { getFearIndex }
   - Purpose: Sentiment/fear index
```

### **Trading Logic**
```
✅ trading-core.js (complementary to trade-logic)
✅ trade-logic.js (position management)
✅ designerAgent.js (pattern recognition)
✅ qaTester.js (quality assurance)
```

### **Data & Services**
```
✅ dataSourceManager.js
   - Purpose: Coordinate data sources
   - Exports: { ...functions }

✅ chartEngine.js
   - Purpose: Chart rendering

✅ continuous-loop.js
   - Purpose: Background event loop
```

### **Services (Not Agents)**
```
✅ symbol-preferences.js
   - Location: /src/services/
   - Purpose: User symbol preferences + price hierarchy
   - Integration: Symbol normalization + user overrides

✅ Other services in /src/services/
```

### **Specialized Agents** (15+ more)
```
- All verified to have unique purposes
- No true duplicates (coordinator + orchestrator serve different entry points)
- No redundant deletable agents
```

---

## 5. DATA FLOW MAP

```
TradingView                MT5                    Yahoo Finance
    ↓                      ↓                           ↓
┌─────────────────────────────────────────────────────┐
│             server.js (Data Aggregator)              │
│  - mt5_bridge.py (MT5 connection)                   │
│  - mt5_data.json (Latest MT5 candles)               │
│  - Real-time price updates                          │
└─────────────────────────────────────────────────────┘
    ↓                      ↓                           ↓
 market-store (In-Memory Cache)                   
    ├─ bySymbol[symbol]    
    ├─ analysisCache[symbol]
    └─ sseClients (for broadcast)
    ↓                      ↓                           ↓
┌─────────────────────────────────────────────────────┐
│            Agent System (orchestrator)                │
│  - 23+ agents analyze in parallel                   │
│  - newsAgent, macroAgent, market-state, etc.       │
└─────────────────────────────────────────────────────┘
    ↓                      ↓                           ↓
┌─────────────────────────────────────────────────────┐
│        Results → UI (Studio + Dashboard)             │
│  - Real-time updates via SSE /stream                │
│  - WebSocket for live trading                       │
└─────────────────────────────────────────────────────┘
```

---

## 6. DEPENDENCY GRAPH

### **Server.js** imports:
```javascript
const express = require('express');
const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');
const orchestrator = require('./src/agents/orchestrator');        // ACTIVE
const coordinator = require('./src/agents/coordinator');          // ACTIVE
const newsIntel = require('./news-intelligence');                 // ACTIVE
const marketStore = require('./store/market-store');              // DATA
const symbolNorm = require('./lib/symbol-normalizer');            // LIB
```

### **Studio (index-simple.html)** →
```javascript
studioapp-simple.js (270 lines)
  → /studio/data
  → /analyze
  → /studio/agent-screen
  → /studio/mapping-list
  → /studio/mapping/:symbol
  → /instant-trade-live
```

### **Extension (popup.html)** →
```javascript
popup.js (Version 1: /public/)
OR
tradingview-analyzer/popup.js (Version 2)

Depends on:
  → background.js (service worker)
  → content.js (page injection)
  → manifest.json (permissions)
```

---

## 7. STATIC ASSETS

### **Public Static Files** (/public/)
```
public/
  ├─ background.js (Extension service worker)
  ├─ content.js (Extension page script)
  ├─ manifest.json (Extension config)
  ├─ popup.html (Extension UI v1)
  ├─ popup.js (Extension UI v1 script)
  ├─ dev-helper.js (Dev tools injection)
  ├─ server.js (🤔 Separate server?)
  └─ requirements.txt (dependencies)
```

### **Studio Assets** (/studio/)
```
studio/
  ├─ studioapp.js (Advanced logic - used by index.html)
  ├─ studioapp-simple.js (270 lines - used by index-simple.html) ✅ ACTIVE
  ├─ styles.css
  ├─ studiostyles.css
  ├─ index.html (NOT used - index-simple used instead)
  ├─ index-simple.html (300 lines) ✅ ACTIVE
  ├─ index_old.html (OLD)
  └─ studioindex.html (archival)
```

### **Extension Alt** (/tradingview-analyzer/)
```
tradingview-analyzer/
  ├─ popup.html (Extension UI v2)
  ├─ popup.js
  ├─ background.js
  ├─ content.js
  ├─ manifest.json
  ├─ styles.css
  ├─ ... (other extension files)
  └─ BACKUP folder (old version)
```

---

## 8. DATA STORAGE

### **Files**
```
✅ mt5_data.json (Active, written by EA)
✅ logs.json (System logs)
✅ SYSTEM_LOG.json (Audit logs)
✅ tasks.json (Task queue)
✅ AGENT_BUS.json (Agent messaging)
✅ SAFE_MODE_CONFIG.json (Safety settings)
✅ PORT_CONFIG.js (Port configuration)
```

### **Directories**
```
✅ /store/market-store.js (In-memory handler)
✅ /analysis/ (analyzer.js)
✅ /lib/ (utilities: candle-manager, symbol-normalizer, etc.)
✅ /src/agents/ (23+ agents)
✅ /src/services/ (symbol-preferences, etc.)
✅ /tests/ (integration tests)
✅ /trading/ (broker-adapter)
```

---

## SUMMARY TABLE

| Component | Type | Status | Lines | Notes |
|-----------|------|--------|-------|-------|
| server.js | Core | ✅ ACTIVE | 2850+ | Main entry point |
| index.html | UI | ✅ ACTIVE | 490 | Main menu |
| studio/index-simple.html | UI | ✅ ACTIVE | 300 | Charts interface |
| popup.html | UI | ✅ ACTIVE | 359 | Extension UI v1 |
| orchestrator.js | Agent | ✅ ACTIVE | 116+ | Main orchestrator |
| coordinator.js | Agent | ✅ ACTIVE | 164 | Alt entry point |
| newsAgent.js | Agent | ✅ ACTIVE | 341 | News analysis |
| news-intelligence.js | Agent | ✅ ACTIVE | 65 | Intelligence |
| candle-manager.js | Lib | ✅ NEW | 420 | Real-time candles |
| Public/server.js | Server | ❓ UNUSED | ? | Need verification |
| studio/index.html | UI | ❌ UNUSED | ? | Use index-simple |
| studio/index_old.html | UI | ❌ OLD | ? | Delete |

---

Generated: 2026-04-03 08:20  
Status: COMPREHENSIVE MAPPING COMPLETE
