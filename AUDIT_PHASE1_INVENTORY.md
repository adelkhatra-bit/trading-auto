# AUDIT COMPLET - PHASE 1: INVENTAIRE EXHAUSTIF

**Status:** 🟢 IN PROGRESS  
**Start Time:** 2026-04-03 07:45  
**Scanning:** All .js, .html, .json files (excluding backup/)  

---

## 📊 STATISTIQUES

- **Total Files (all):** 460
- **Excluding /backup/:** ~230  
- **Active Project:** ~150 (excluding old versions, samples, tests)

---

## 🔍 ANALYSE PAR CATÉGORIE

### 1. HTML FILES (Duplication Risk - HIGH)

**Root Level HTML:**
- [ ] index.html
- [ ] popup.html
- [ ] dashboard.html
- [ ] audit-dashboard.html
- [ ] AGENTS_MONITOR.html
- [ ] agent-log-page.html
- [ ] EXTENSION_TEST.html
- [ ] test-analysis.html
- [ ] test-chart-visual.html

**Status:** ❓ TO ANALYZE - Are all these needed? Any duplicates?

---

**Extension HTML (/public/):**
- [ ] popup.html
- [ ] manifest.json

**Status:** ❓ Same as root popup.html?

---

**Extension HTML (/tradingview-analyzer/):**
- [ ] popup.html
- [ ] manifest.json

**Status:** ❓ Another duplicate popup?

---

**Studio HTML (/studio/):**
- [ ] index.html
- [ ] index-simple.html
- [ ] index_old.html (🔴 STALE?)
- [ ] studioindex.html (❓ DUPLICATE?)

**Status:** ❓ Multiple versions - which is production?

---

### 2. JAVASCRIPT - SERVER & CORE

**Backend Server:**
- [ ] /server.js (root) - Port 4000, comprehensive
- [ ] /public/server.js - Port 3000, lightweight (legacy?)

**Status:** ❌ DUPLICATE - Choose one

**MT5 Integration:**
- [ ] /mt5_bridge_simple.js - Simple bridge
- [ ] /bridge/mt5_bridge.py - Python bridge

**Status:** ✅ Different implementations (keep?)

---

### 3. JAVASCRIPT - AGENTS (23+ files)

**Location:** `/src/agents/`

**Potential Duplicates Detected:**

```
Pair 1: orchestrator.js + coordinator.js
  - Both for orchestration?
  - Status: ❓ VERIFY

Pair 2: trading-core.js + trade-logic.js  
  - Both for trading logic?
  - Status: ❓ VERIFY

Pair 3: newsAgent.js + news-intelligence.js
  - Both for news analysis?
  - Status: ❓ VERIFY

Singleton Agents:
  - technicalAgent.js ✅
  - macroAgent.js ✅
  - fear-index.js ✅
  - setupClassifier.js ✅
  - riskManager.js ✅
  - tradeValidator.js ✅
  - timeframe-consensus.js ✅
  - supervisor.js ✅
  - syncManager.js ✅
  - stateManager.js ✅
  - strategyManager.js ✅
  - qaTester.js ✅
  - continuous-loop.js ✅
  - chartEngine.js ✅
  - designerAgent.js ✅
  - market-state.js ✅
```

**Status:** ⚠️ NEED TO READ each agent and confirm

---

### 4. JAVASCRIPT - CORE LIBRARIES

**Location:** `/lib/`

| File | Purpose | Status |
|------|---------|--------|
| candle-manager.js | ✨ NEW - Tick aggregation | ✅ Phase 1 |
| data-source-manager.js | Price API for agents | ✅ Existing |
| symbol-normalizer.js | Symbol canonicalization | ✅ Backend |
| symbol-matcher.js | Symbol mapping logic | ✅ Backend |
| chart-renderer.js | Chart rendering | ✅ Existing |
| broker-calculator.js | Broker calculations | ✅ Existing |

**Status:** ✅ No obvious duplicates in /lib/

---

### 5. JAVASCRIPT - EXTENSION

**Location:** `/public/` + `/tradingview-analyzer/`

**Public (v1):**
- popup.js
- manifest.json
- background.js
- content.js
- dev-helper.js
- server.js (legacy?)

**TradingView Analyzer (v2):**
- popup.js
- manifest.json
- background.js
- content.js
- symbol-mapper.js
- symbol-manager.js
- chart-module.js
- ai-debugger.js
- news-engine.js
- market-session.js
- economic-calendar.js
- error-handler.js
- lightweight-charts.min.js

**Status:** ❌ TWO COMPLETE EXTENSIONS - Choose one

---

### 6. JAVASCRIPT - STUDIO

**Location:** `/studio/`

| File | Purpose | Status |
|------|---------|--------|
| index.html | Production UI? | ❓ |
| index-simple.html | Dev UI? | ❓ |
| index_old.html | Old version | 🔴 DELETE |
| studioindex.html | Duplicate? | ❓ |
| app.js | App logic | ❓ |
| studioapp.js | Studio app | ❓ |
| studioapp-simple.js | Simple studio? | ❓ |
| studioapp-old.js | Old version | 🔴 DELETE |

**Status:** ⚠️ Multiple versions - consolidate

---

### 7. JAVASCRIPT - SERVICES

**Location:** `/src/services/`

| File | Purpose|
|------|---------|
| symbol-preferences.js | User price hierarchy ✅ |
| fileService.js | File I/O |

**Status:** ✅ Clean

---

### 8. JAVASCRIPT - ORPHANED (ROOT LEVEL)

| File | Purpose | Status |
|------|---------|--------|
| agent.js | ❓ | UNKNOWN |
| agent-worker.js | ❓ Worker? | UNKNOWN |
| agent-bus.js | ❓Message bus? | UNKNOWN |
| access.js | ❓ Access control? | UNKNOWN |
| audit-logger.js | ✅ Logging | KEEP |
| PORT_CONFIG.js | ✅ Port config | KEEP |
| mt5_bridge_simple.js | ✅ MT5 bridge | KEEP |

**Status:** 🔴 4 files with unclear purpose

---

### 9. DATA FILES

**JSON Configuration:**
- [ ] AGENT_BUS.json
- [ ] SAFE_MODE_CONFIG.json
- [ ] PORT_CONFIG.js
- [ ] package.json
- [ ] package-lock.json

**JSON Data:**
- [ ] mt5_data.json (root)
- [ ] mt5_data.json (/tradingview-analyzer/)
- [ ] mt5_data_EURUSD.json
- [ ] mt5_data_GBPUSD.json
- [ ] mt5_data_USDCAD.json
- [ ] audit.json
- [ ] SYSTEM_LOG.json
- [ ] AGENT_BUS.json
- [ ] logs.json
- [ ] library.json
- [ ] PROJECT_ANALYSIS_REPORT.json

**Status:** ❓ Which mt5_data.json is source of truth?

---

## 🔴 DUPLICATION SUMMARY

| Type | Count | Severity | Action |
|------|-------|----------|--------|
| Extension UIs | 2 complete | 🔴 HIGH | Choose A1 or A2 |
| Servers | 2 | 🔴 HIGH | Keep root only |
| Studio UIs | 4 versions | 🔴 HIGH | Consolidate to 2 |
| Agents | 3+ pairs | 🟡 MEDIUM | Verify then merge |
| Root HTML | 9 files | ❓ UNCLEAR | Analyze purpose |
| mt5_data | 5+ files | 🟡 MEDIUM | Single source |
| Orphaned | 4 files | 🟡 MEDIUM | Document or delete |

---

## 📋 NEXT STEP: DETAILED ANALYSIS

Need to:
1. Read EVERY HTML file (understand what each does)
2. Read EVERY duplicate-suspect agent (are they ACTUALLY duplicates?)
3. Verify EVERY extension file dependency
4. Check EVERY import/require statement (prevent breaking changes)

---

**Current Phase:** 🟡 INITIAL SCAN COMPLETE  
**Next Phase:** 🟠 DETAILED ANALYSIS  
**Estimated Time Remaining:** 2-3 hours for full cleanup readiness

