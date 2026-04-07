# SYSTEM_STATUS.md - État Détaillé de Chaque Module

**Last Updated:** 2026-04-03 08:05  
**Status:** 🟡 MONITORING PHASE  
**Next Update:** Continuous until completion

---

## 🎯 OVERALL STATUS

| Component | Status | Progress | ETA | Blocker |
|-----------|--------|----------|-----|---------|
| **Project Audit** | 🟢 COMPLETE | 100% | DONE | None |
| **Cleanup Planning** | 🟢 COMPLETE | 100% | DONE | Awaiting user decision |
| **Cleanup Execution** | 🟡 PENDING APPROVAL | 0% | 1 hour | User approval |
| **Phase 1: CandleManager** | 🟢 CODE READY | 100% (code) | 30 min (tests) | Testing |
| **Phase 2: IndicatorEngine** | 🔴 BLOCKED | 0% | 8 hours | After Ph1 pass |
| **Phase 3: OrchestrationRT** | 🔴 BLOCKED | 0% | 5 hours | After Ph2 pass |
| **Phase 4: SyncBroadcaster** | 🔴 BLOCKED | 0% | 3 hours | After Ph3 pass |
| **Server Integration** | 🔴 BLOCKED | 0% | 4 hours | After Ph4 pass |
| **Client Updates** | 🔴 BLOCKED | 0% | 8 hours | After Server |

---

## 📦 CORE LIBRARY STATUS

### ✅ /lib/ (No changes needed, all ACTIVE)

| Module | Purpose | Status | Lines | Dependencies |
|--------|---------|--------|-------|---|
| candle-manager.js | Real-time candle aggregation + state machine | 🟢 READY | 420 | EventEmitter (built-in) |
| data-source-manager.js | Price API for agents | 🟢 ACTIVE | 150 | symbol-preferences |
| symbol-preferences.js | User price hierarchy (locked > user > system) | 🟢 ACTIVE | 250 | fileService |
| symbol-normalizer.js | Symbol canonicalization + profiles | 🟢 ACTIVE | 400 | None |
| symbol-matcher.js | TradingView → source mapping | 🟢 ACTIVE | 300 | symbol-normalizer |
| chart-renderer.js | Chart rendering logic | 🟢 ACTIVE | 200 | (unknown) |
| broker-calculator.js | Broker-specific calculations | 🟢 ACTIVE | 150 | symbol-normalizer |

**Summary:** ✅ ALL CLEAN, NO CHANGES

---

## 🤖 AGENTS STATUS (/src/agents/)

### 🟢 CORE AGENTS (Primary, Modern, Keep)

| Agent | Role | Pattern | Lines | Status |
|-------|------|---------|-------|--------|
| **orchestrator.js** | Master orchestration | async/Promise.all | 200 | 🟢 PRIMARY |
| **trading-core.js** | Technical analysis | Analytical | 300 | 🟢 PRIMARY |
| **trade-logic.js** | Analysis explanation | Narrative | 200 | 🟢 PRIMARY |
| **newsAgent.js** | News intelligence | State-based | 300 | 🟢 PRIMARY |
| **technicalAgent.js** | Technical analysis | Agent | 250 | 🟢 ACTIVE |
| **macroAgent.js** | Macro analysis | Agent | 200 | 🟢 ACTIVE |

**Verdict:** ✅ ALL KEEP

---

### 🟡 LEGACY AGENTS (Older patterns, candidates for deletion)

| Agent | Role | Pattern | Lines | Status | Action |
|-------|------|---------|-------|--------|--------|
| **coordinator.js** | Price coordination | Callback-based | 250 | 🟡 LEGACY | DELETE if not imported |
| **news-intelligence.js** | Simple news | Function-based | 150 | 🟡 LEGACY | DELETE if not imported |

**Verdict:** Delete unless imports found

---

### ✅ SUPPORTING AGENTS (All keep, unique roles)

| Agent | Role | Status |
|-------|------|--------|
| fear-index.js | Volatility/VIX | ✅ KEEP |
| setupClassifier.js | Pattern detection | ✅ KEEP |
| riskManager.js | Risk management | ✅ KEEP |
| tradeValidator.js | Trade validation | ✅ KEEP |
| timeframe-consensus.js | Multi-TF consensus | ✅ KEEP |
| supervisor.js | Supervision | ✅ KEEP |
| syncManager.js | Synchronization | ✅ KEEP |
| stateManager.js | State management | ✅ KEEP |
| strategyManager.js | Strategy management | ✅ KEEP |
| qaTester.js | QA testing | ✅ KEEP |
| continuous-loop.js | Main loop | ✅ KEEP |
| chartEngine.js | Chart rendering | ✅ KEEP |
| designerAgent.js | UI design | ✅ KEEP |
| market-state.js | Market state | ✅ KEEP |
| dataSourceManager.js | (if exists, check purpose) | ? |

**Summary:** 15 agents to keep, 2 to delete (if no imports)

---

## 🌐 UI COMPONENTS STATUS

### Extension UIs (Choose ONE)

#### Option A1: /public/ (Recommended)

| File | Status | Action |
|------|--------|--------|
| popup.html | 🟢 KEEP | Primary version |
| popup.js | 🟢 KEEP | Primary logic |
| manifest.json | 🟢 KEEP | Primary manifest |
| background.js | 🟢 KEEP | Service worker |
| content.js | 🟢 KEEP | Content script |
| dev-helper.js | 🟢 KEEP | Development helper |
| server.js | 🔴 DELETE | Use /server.js root |

**Verdict:** Keep all except server.js

---

#### Option A2: /tradingview-analyzer/ (Alternative)

| File | Status | Action |
|------|--------|--------|
| popup.html | 🟢 KEEP | Alternative version |
| popup.js | 🟢 KEEP | Alternative logic |
| manifest.json | 🟢 KEEP | Alternative manifest |
| background.js | 🟢 KEEP | Service worker |
| content.js | 🟢 KEEP | Content script |
| chart-module.js | 🟢 KEEP | Chart features |
| ai-debugger.js | 🟢 KEEP | Debug features |
| news-engine.js | 🟢 KEEP | News analysis |
| market-session.js | 🟢 KEEP | Market sessions |
| economic-calendar.js | 🟢 KEEP | Calendar |
| error-handler.js | 🟢 KEEP | Error handling |

**Verdict:** Keep all (more comprehensive)

---

**User Choice Needed:** A1 or A2?

---

### Studio UI (Consolidate)

| File | Purpose | Status | Action | Notes |
|------|---------|--------|--------|-------|
| index.html | Production UI | 🟢 ACTIVE | KEEP | Main version |
| index-simple.html | Dev/fallback | 🟢 ALTERNATIVE | KEEP | Dev version |
| index_old.html | Old version | 🔴 STALE | DELETE | Clearly old |
| studioindex.html | ??? | ❓ UNCLEAR | DELETE | Duplicate name? |
| studioapp.js | Production logic | 🟢 ACTIVE | KEEP | Main version |
| studioapp-simple.js | Dev/fallback | 🟢 ALTERNATIVE | KEEP | Dev version |
| studioapp-old.js | Old version | 🔴 STALE | DELETE | Clearly old |
| app.js | ??? | ❓ CHECK | (depends) | May be alias/dup |
| styles.css | Production styles | 🟢 KEEP | KEEP | |
| studiostyles.css | Alternative styles | ❓ UNCLEAR | (depends) | Duplicate? |

**Verdict:** 
- KEEP: index.html, studioapp.js, index-simple.html, studioapp-simple.js
- DELETE: index_old.html, studioapp-old.js, studioindex.html
- VERIFY: app.js, studiostyles.css (may be duplicates)

---

## 📂 STORAGE & DATA STATUS

### /store/ (Data layer)

| File | Purpose | Status | Action |
|------|---------|--------|--------|
| market-store.js | SSE broadcast coordination | 🟢 ACTIVE | KEEP |
| mt5_data.json | **Single source** | 🟢 | CONSOLIDATE |
| mt5_data_EURUSD.json | Sample/old | 🟡 | ARCHIVE |
| mt5_data_GBPUSD.json | Sample/old | 🟡 | ARCHIVE |
| mt5_data_USDCAD.json | Sample/old | 🟡 | ARCHIVE |

**Verdict:** One canonical /store/mt5_data.json, archive samples

---

### /backup/ (Already organized)

| Folder | Status | Purpose |
|--------|--------|---------|
| /2026-04-03_073752_pre_phase1_audit/ | ✅ EXISTS | Pre-cleanup snapshot |
| /archive_2026-04-03/ | 🟡 PENDING | New archive structure (to create) |

**Verdict:** Organize deletions into archive when cleanup executes

---

## 🔧 SERVER STATUS

### Main Server

| File | Port | Status | Action |
|------|------|--------|--------|
| /server.js (root) | 4000 | 🟢 PRIMARY | KEEP - Production backend |
| /public/server.js | 3000 | 🟡 LEGACY | DELETE - Old image server |

**Verdict:** Delete /public/server.js, keep root /server.js

---

## 🔍 CRITICAL DECISION MATRIX

| Category | Status | Options | Recommendation |
|----------|--------|---------|---|
| **Extension** | 🟡 AWAITING | A1 (/public/) or A2 | **A1 (lighter)** |
| **Studio** | 🟡 PARTIAL | Keep C1 or C2 | **C1 (both versions)** |
| **Cleanup Level** | 🟡 AWAITING | Opt1, Opt2, Opt3 | **Opt2 (moderate)** |
| **Agent Delete** | 🟡 CONDITIONAL | If imports verified | **coordinator.js, news-intelligence.js** |
| **Public Server** | 🟢 CLEAR | Delete 100% | **DELETE** |

**Blocking Items:** 3 require user decision

---

## 📋 ESTIMATED TIMES (FROM NOW)

| Task | When | Duration | Status |
|------|------|----------|--------|
| Verify imports | RIGHT NOW | 15 min | 🟡 IN PROGRESS |
| Get user decisions | RIGHT NOW | depends | 🟡 AWAITING |
| Execute cleanup | IF APPROVED | 20 min | 🔴 PENDING |
| Validate project | AFTER CLEANUP | 15 min | 🔴 PENDING |
| Run Ph1 tests | AFTER CLEANUP | 30 min | 🔴 PENDING |
| **TOTAL BLOCKING TIME** | | **40 min** | |
| **TOTAL WITH DECISIONS** | | **1-2 hours** | |

---

## 🚦 TRAFFIC LIGHT STATUS

```
🟢 GREEN   → Ready to proceed
🟡 YELLOW  → Awaiting decision / verification
🔴 RED     → Blocked / not started

OVERALL: 🟡 YELLOW (awaiting user decisions)
```

---

## ✅ COMPLETION CHECKLIST

### Audit Phase
- [x] Complete file inventory
- [x] Analyze duplication
- [x] Identify agents status
- [x] Create documentation
- [ ] Verify imports (in progress)

### Decision Phase  
- [ ] User chooses Extension (A1/A2)
- [ ] User chooses Studio (C1/C2)
- [ ] User chooses cleanup level (1/2/3)

### Cleanup Phase
- [ ] Archive old files
- [ ] Delete obsolete files
- [ ] Verify no broken refs
- [ ] Validate structure

### Testing Phase
- [ ] Run candle-manager tests
- [ ] All 10 tests pass
- [ ] Phase 1 approval

### Implementation Phase
- [ ] Phase 2: indicator-engine
- [ ] Phase 3: orchestrator-realtime
- [ ] Phase 4: sync-broadcaster
- [ ] Full integration
- [ ] End-to-end testing

---

**Next Action:** ⏳ Awaiting user decision on cleanup options

**Last Update:** 2026-04-03 08:05  
**Status:** 🟡 LIVE MONITORING
