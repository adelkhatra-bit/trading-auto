# PROJECT_STATUS.md
**Last Updated:** 2026-04-03 07:37  
**Backup Location:** `/backup/2026-04-03_073752_pre_phase1_audit`

---

## 📊 GLOBAL PROJECT STATE

| Status | Phase | Progress | ETA |
|--------|-------|----------|-----|
| 🔵 ACTIVE | Phase 1: CandleManager | 100% Code | 2h remaining |
| 🟡 PENDING | Phase 2: IndicatorEngine | 0% | After Ph1 validation |
| 🟡 PENDING | Phase 3: OrchestrationRT | 0% | After Ph2 validation |
| 🟡 PENDING | Phase 4: SyncBroadcaster | 0% | After Ph3 validation |
| 🟡 PENDING | Server Integration | 0% | After all modules |
| 🔴 BLOCKED | Structure Audit | IN PROGRESS | Must complete first |

---

## 🗂️ DIRECTORY STRUCTURE AUDIT

### Critical Finding: MASSIVE DUPLICATION & DISORGANIZATION

```
Project Root
├── /lib/                          ✅ CLEAN (core modules)
│   ├── candle-manager.js         ✅ NEW (Phase 1)
│   ├── indicator-engine.js        ⏳ NEEDED
│   ├── sync-broadcaster.js        ⏳ NEEDED
│   ├── symbol-normalizer.js       ✅ EXISTS
│   ├── symbol-matcher.js          ✅ EXISTS
│   ├── data-source-manager.js     ✅ EXISTS
│   ├── chart-renderer.js          ✅ EXISTS
│   └── broker-calculator.js       ✅ EXISTS
│
├── /src/                          ⚠️ COMPLEX (23 agents + services)
│   ├── agents/                    ⚠️ 23 files (needs review)
│   └── services/
│       ├── symbol-preferences.js  ✅ CRITICAL (price hierarchy)
│       └── fileService.js         ✅ OK
│
├── /public/                       😕 DUPLICATE (Extension UI v1)
│   ├── popup.html                 ⚠️ DUPLICATE
│   ├── popup.js                   ⚠️ DUPLICATE
│   ├── manifest.json              ⚠️ DUPLICATE
│   ├── background.js              ⚠️ DUPLICATE
│   ├── content.js                 ⚠️ DUPLICATE
│   └── server.js                  ⚠️ DUPLICATE
│
├── /tradingview-analyzer/         😕 DUPLICATE (Extension UI v2 + extras)
│   ├── popup.html                 ⚠️ DUPLICATE
│   ├── popup.js                   ⚠️ DUPLICATE
│   ├── manifest.json              ⚠️ DUPLICATE
│   ├── background.js              ⚠️ DUPLICATE
│   ├── content.js                 ⚠️ DUPLICATE
│   ├── symbol-manager.js          ⚠️ DUPLICATE (vs symbol-mapper.js)
│   ├── symbol-mapper.js           ⚠️ DUPLICATE
│   ├── chart-module.js            ✅ UNIQUE (charts logic)
│   ├── ai-debugger.js             ✅ UNIQUE (debugging)
│   ├── mt5_data*.json             ⚠️ SAMPLE DATA (vs /store)
│   └── [35+ files total]
│
├── /tradingview-analyzer_backup_20260402/  🔴 STALE BACKUP (should remove)
│   └── [23 files - old version]
│
├── /studio/                       ⚠️ MULTIPLE VERSIONS
│   ├── index.html                 ? ACTIVE VERSION?
│   ├── index-simple.html          ? ALTERNATIVE
│   ├── index_old.html             🔴 OLD VERSION
│   ├── studioindex.html           ? DUPLICATE NAME?
│   ├── studioapp.js               ? ACTIVE VERSION?
│   ├── studioapp-simple.js        ? ALTERNATIVE
│   └── studioapp-old.js           🔴 OLD VERSION
│
├── /store/                        ✅ DATA PERSISTENCE
│   └── market-store.js            ✅ SSE broadcast
│
├── /dashboard/                    ⏳ NOT FOUND (needs creation or clarification)
│
├── Root-Level Files              🔴 ORPHANED
│   ├── server.js                  ⚠️ MAIN SERVER (duplicate in /public)
│   ├── agent.js                   ? UNCLEAR PURPOSE
│   ├── agent-worker.js            ? UNCLEAR PURPOSE
│   ├── agent-bus.js               ? UNCLEAR PURPOSE (vs AGENT_BUS.json)
│   ├── audit-logger.js            ✅ Audit logging
│   ├── access.js                  ? UNCLEAR PURPOSE
│   ├── mt5_bridge_simple.js       ✅ MT5 integration
│   └── [+10 HTML files scattered]
│
└── /backup/                       ✅ NEW - Pre-Phase1 snapshot
    └── 2026-04-03_073752_pre_phase1_audit/  ✅ CREATED
```

---

## 📋 MODULE STATUS DETAIL

### PHASE 1: CORE MARKET ENGINE

#### ✅ lib/candle-manager.js
- **State:** 🟢 COMPLETE (created, 400 lines)
- **Status:** Tick aggregation, candle state machine, persistence
- **Tests:** 10/10 unit tests (not yet run)
- **API:** 
  - `onTick(symbol, price, bid, ask, volume, timestamp)`
  - `getCurrentCandle(symbol, timeframe)`
  - `getClosedCandles(symbol, timeframe, limit)`
  - `persist()`, `getHealth()`
- **Dependencies:** None (Node.js built-in EventEmitter)
- **Ready for:** Unit test execution

**Action Required:** Run test suite → report results

---

### PHASE 2: INDICATORS (BLOCKED until Ph1 validated)

#### ⏳ lib/indicator-engine.js
- **State:** 🔴 NOT STARTED
- **Status:** RSI, MACD, BB, ATR, MA calculations
- **Estimated Time:** 6-8 hours development + 2 hours testing
- **Dependencies:** lib/candle-manager.js (MUST complete first)
- **API Design:** (from FINAL_REALTIME_ARCHITECTURE_COMPLETE.md)
  - `onCandleClose(symbol, timeframe, candle)`
  - `calculateRSI(data, period=14)`
  - `calculateMACD(data, fast=12, slow=26, signal=9)`
  - `calculateBB(data, period=20, stdDev=2)`
  - `calculateATR(data, period=14)` 
  - `calculateMA(data, periods=[20,50,200])`

---

### CORE SERVICES (EXISTING, VALIDATED)

#### ✅ src/services/symbol-preferences.js
- **State:** 🟢 COMPLETE & INTEGRATED
- **Status:** User price hierarchy (locked > userRef > system)
- **Methods:** registerUserReference, getEffectivePrice, updateUserReference
- **Persistence:** /store/symbol-preferences.json
- **Dependencies:** None
- **Integration:** Used by data-source-manager, agents

**No changes needed**

#### ✅ src/services/data-source-manager.js
- **State:** 🟢 COMPLETE & INTEGRATED
- **Status:** Price API for agents
- **Methods:** getEffectivePrice(symbol, contextId)
- **Integration:** Wraps symbol-preferences, called by agents
- **Persistence:** Uses symbol-preferences

**No changes needed**

---

### 🔴 DUPLICATION ISSUES FOUND

#### Extension UIs (Multiple Versions)
| File | /public | /tradingview-analyzer | How to resolve |
|------|---------|----------------------|-----------------|
| popup.html | ✅ | ✅ | Choose ONE, delete other |
| popup.js | ✅ | ✅ | Choose ONE, delete other |
| manifest.json | ✅ | ✅ | Choose ONE, delete other |
| background.js | ✅ | ✅ | Choose ONE, delete other |
| content.js | ✅ | ✅ | Choose ONE, delete other |
| server.js | ✅ | ❌ | Keep only /public (or root) |

**Decision Needed:** Which version is "active"?

#### Symbol Mapping
| File | Location | Purpose |
|------|----------|---------|
| symbol-mapper.js | /tradingview-analyzer | Symbol mapping? |
| symbol-manager.js | /tradingview-analyzer | Symbol management? |
| symbol-matcher.js | /lib | Symbol matching |
| symbol-normalizer.js | /lib | Symbol normalization |

**Clarity Needed:** What's the difference between all 4?

#### Studio UI (Multiple Versions)
| File | Purpose |
|------|---------|
| index.html | Active version? |
| index-simple.html | Simplified version? |
| index_old.html | Deprecated? |
| studioindex.html | Duplicate of index.html? |
| studioapp.js | Active version? |
| studioapp-simple.js | Simplified version? |
| studioapp-old.js | Deprecated? |

**Decision Needed:** Keep which version(s)? Delete old?

---

## 📦 AGENTS (23 TOTAL - REVIEW NEEDED)

Located in `/src/agents/`:

| Agent | Purpose | Status |
|-------|---------|--------|
| orchestrator.js | Main agent orchestration | ? UNCLEAR |
| coordinator.js | Agent coordination | ? DUPLICATE? |
| trading-core.js | Core trading logic | ? ACTIVE? |
| trade-logic.js | Trade logic | ? DUPLICATE? |
| technicalAgent.js | Technical analysis | ✅ |
| macroAgent.js | Macro analysis | ✅ |
| newsAgent.js | News analysis | ✅ |
| fear-index.js | Volatility/fear | ✅ |
| setupClassifier.js | Pattern classification | ✅ |
| riskManager.js | Risk management | ✅ |
| tradeValidator.js | Trade validation | ✅ |
| timeframe-consensus.js | Multi-timeframe consensus | ✅ |
| supervisor.js | Agent supervision | ✅ |
| syncManager.js | Synchronization | ? NEEDS REVIEW |
| stateManager.js | State management | ✅ |
| strategyManager.js | Strategy management | ✅ |
| qaTester.js | QA/testing | ✅ |
| continuous-loop.js | Main loop | ✅ |
| chartEngine.js | Chart rendering | ✅ |
| dataSourceManager.js | Data sourcing | ? DUPLICATE? |
| designerAgent.js | UI design logic | ✅ |
| market-state.js | Market state tracking | ✅ |
| news-intelligence.js | News processing | ? DUPLICATE? |

**Action Required:** 
1. Identify DUPLICATE agents (orchestrator/coordinator, trading-core/trade-logic, etc.)
2. Verify which are ACTIVE vs DEPRECATED
3. Update Integration Points

---

## 📁 CRITICAL FILES REQUIRING CLARIFICATION

| File | Location | Status | Question |
|------|----------|--------|----------|
| server.js | Root + /public | ? | Which is active? |
| mt5_bridge_simple.js | Root | ✅ | MT5 EA communication |
| mt5_data.json | Root + /tradingview-analyzer | ⚠️ | Source of truth? |
| AGENT_BUS.json | Root | ? | Purpose? |
| audit-logger.js | Root | ✅ | Audit logging system |
| access.js | Root | ? | Purpose? |
| agent.js | Root | ? | ACTIVE vs /src/agents? |
| agent-worker.js | Root | ? | Worker pattern? |
| agent-bus.js | Root | ? | Message bus? |
| audit-dashboard.html | Root | ✅ | Audit UI |
| dashboard.html | Root | ? | Trading dashboard? |

---

## 🎯 REQUIRED CLEANUP BEFORE CONTINUING

### MUST DO (Blocking Phase 1 continuation):
1. ✅ [DONE] Create backup of current state → `/backup/2026-04-03_073752_pre_phase1_audit`
2. ⏳ [TODO] Choose canonical Extension UI version (/public or /tradingview-analyzer, DELETE OTHER)
3. ⏳ [TODO] Clarify symbol mapping (symbol-mapper vs symbol-manager vs symbol-matcher vs symbol-normalizer)
4. ⏳ [TODO] Choose canonical Studio UI version (index.html or index-simple.html, DELETE OTHERS)
5. ⏳ [TODO] Identify & REMOVE duplicate agents
6. ⏳ [TODO] Verify which server.js is active (root vs /public)
7. ⏳ [TODO] Document purpose of orphaned root-level files (agent.js, agent-worker.js, agent-bus.js, access.js)
8. ⏳ [TODO] Remove /tradingview-analyzer_backup_20260402 (stale backup)

### NICE TO HAVE (after cleanup):
- Consolidate mt5_data.json to single location (/store)
- Create comprehensive ARCHITECTURE.md covering all dependencies
- Document which mt5-symbols.js, symbol-mapper.js, symbol-manager.js should be canonical

---

## 📋 DECISIONS AWAITING FROM USER

Before proceeding to Phase 1 test execution and Phase 2 implementation:

1. **Extension UI**: `/public/` or `/tradingview-analyzer/`?
   - **Recommendation:** Use `/public/` (follows convention)

2. **Studio UI**: `index.html` or `index-simple.html`?
   - **Recommendation:** Keep `index.html` (production) + `index-simple.html` (dev), DELETE `index_old.html` and `studioindex.html`

3. **Server.js**: Root or /public?
   - **Recommendation:** Use root `/server.js` (main entry point), DELETE `/public/server.js`

4. **Symbol Mapping**: Consolidate 4 files to 2?
   - `/lib/symbol-normalizer.js` (normalize to canonical)
   - `/lib/symbol-matcher.js` (match trading view → canonical)
   - DELETE: symbol-mapper.js, symbol-manager.js (consolidate into above)

5. **Agent Deduplication**: Identify duplicates?
   - orchestrator.js vs coordinator.js?
   - trading-core.js vs trade-logic.js?
   - newsAgent.js vs news-intelligence.js?

6. **Orphaned Root Files**: Keep or delete?
   - agent.js, agent-worker.js, agent-bus.js (worker pattern? message bus?)
   - access.js (access control?)
   - Unclear purpose → DOCUMENT or REMOVE

---

## ✅ BACKUP CREATED

```
Location: /backup/2026-04-03_073752_pre_phase1_audit
Contains:
  ├── /lib/               (all core modules including new candle-manager.js)
  ├── /src/agents/        (all 23 agents)
  ├── /src/services/      (symbol-preferences, fileService)
  ├── /public/            (extension UI)
  ├── /studio/            (studio UI)
  └── server.js           (main server)

Usage: If cleanup breaks something, restore from this backup.
```

---

## 🚀 CONTINUATION PLAN

### STEP 1: STRUCTURE CLEANUP (USER INPUT NEEDED)
- [ ] User answers 6 decision questions above
- [ ] Execute cleanup / deduplication
- [ ] Verify no broken imports

### STEP 2: PHASE 1 VALIDATION
- [ ] Run candle-manager.test.js (10 unit tests)
- [ ] Report results (PASS/FAIL per test)
- [ ] Fix any failures
- [ ] Get user approval to proceed to Phase 2

### STEP 3: PHASE 2 DEVELOPMENT  
- [ ] Implement lib/indicator-engine.js (600-800 lines)
- [ ] Implement unit tests (10-15 tests)
- [ ] Integration test (indicator:ready event flow)
- [ ] Get approval to proceed to Phase 3

### STEP 4: PHASE 3 DEVELOPMENT
- [ ] Implement src/agents/orchestrator-realtime.js
- [ ] Hook symbol state validation (READY vs INIT vs MISSING)
- [ ] Run agents in parallel on indicators:ready

### STEP 5: PHASE 4 DEVELOPMENT
- [ ] Implement lib/sync-broadcaster.js
- [ ] Test SSE coordination

### STEP 6: SERVER INTEGRATION
- [ ] Add POST /api/mt5/tick endpoint
- [ ] Wire candle-manager.onTick()
- [ ] Wire sync-broadcaster events

### STEP 7: CLIENT UPDATES
- [ ] Extension popup event handlers
- [ ] Studio chart rendering
- [ ] Dashboard signal table

### STEP 8: END-TO-END TESTING
- [ ] Tick → Candle close → Indicators → Agents → Signal → SSE → Clients

---

## 📊 TIME ESTIMATES (if cleanup approved)

| Phase | Component | Est. Time | Blocking |
|-------|-----------|-----------|----------|
| 1 | candle-manager tests | 1-2 hours | Phase 2 |
| 2 | indicator-engine dev | 6-8 hours | Phase 3 |
| 2 | indicator-engine tests | 2 hours | Phase 3 |
| 3 | orchestrator dev | 4-5 hours | Phase 4 |
| 4 | sync-broadcaster dev | 2-3 hours | Server |
| Server | Integration | 3-4 hours | Clients |
| Clients | Extension + Studio | 6-8 hours | Testing |
| Testing | E2E validation | 4-6 hours | DONE |
| **TOTAL** | | **28-40 hours** | |

---

## 🔐 AUDIT SUMMARY

✅ **Backup created successfully**  
⚠️ **MASSIVE DUPLICATION DETECTED** (Extension UI, Studio UI, agents)  
🔴 **Cannot proceed until structure clarified**  

**Next Action:** User provides answers to 6 decision questions, then cleanup can begin.

---

*Status Report Generated: 2026-04-03 07:37:52*  
*Backup: /backup/2026-04-03_073752_pre_phase1_audit*
