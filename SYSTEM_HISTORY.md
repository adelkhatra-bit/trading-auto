# SYSTEM_HISTORY.md - Historique Complet du Projet

**Last Updated:** 2026-04-03 08:00  
**Status:** 🟡 DOCUMENTING PHASE  
**Backup:** `/backup/2026-04-03_073752_pre_phase1_audit` ✅

---

## 📖 TABLE OF CONTENTS

1. [Historique Avant Audit](#avant-audit)
2. [Découvertes Pendant Audit](#découvertes)
3. [Changements Planifiés](#changements-planifiés)
4. [État Actuel](#état-actuel)
5. [Prochaines Étapes](#prochaines-étapes)

---

## 🔴 AVANT AUDIT

### État Existant (2026-04-03 matin)

**Architecture:**
```
Project était un mélange de:
- Extension TradingView (v1 /public/ et v2 /tradingview-analyzer/)
- Backend Node.js + agents multiples
- Studio interface (multiple versions)
- 23+ agents d'analyse avec possibles doublons
- Fichiers orphelins au root level
```

**Problèmes Connus Avant Audit:**
- ❓ User reference price system + candle closes + indicators = architecture réelle?
- ❓ Real-time market data foundation?
- ❓ How do agents work together?

**Problèmes À Déterminer:**
- Structure unclear
- Multiple versions of same components
- No clear single source of truth for data

---

## 🔍 DÉCOUVERTES PENDANT AUDIT

### A. DUPLICATION D'EXTENSIONS

**Situation:** 2 extensions complètes et différentes

| Aspect | /public/ (v1.0) | /tradingview-analyzer/ (v2.0) |
|--------|---|---|
| Manifest Version | 3 | 3 |
| Name | "Trading Auto" | "Trading Auto Analyzer" |
| Version | 1.0.0 | 2.0.0 |
| Scope | Standard/Light | Extended (includes analysis modules) |
| Core Files | popup, background, content | popup, background, content |
| Extra Files | dev-helper | chart-module, ai-debugger, news-engine, economic-calendar, error-handler |

**Problème:** 
- Impossible de savoir laquelle est "active"
- Risque: User installe v1, features de v2 manquent
- Ou: User installe v2, dependencies manquent

**Solution:** 
- Choisir UNE version
- Archiver l'autre
- Documenter pourquoi

---

### B. DUPLICATION DE SERVEURS

**Situation:** 2 serveurs à ports différents

| Aspect | /server.js (root) | /public/server.js |
|--------|---|---|
| Port | 4000 | 3000 |
| Lignes de code | 400+ | 40-50 |
| Complexité | Complet (Trading Auto backend) | Léger (image server) |
| Purpose | Production backend | Legacy/image serving |

**Problème:**
- Confusion sur lequel lancer
- Conflit de ports possible
- /public/server.js semble obsolete

**Solution:**
- Garder ONLY /server.js (root, port 4000)
- Archiver /public/server.js
- Verifier qu'aucun code n'en dépend

---

### C. MULTIPLE VERSIONS STUDIO

**Situation:** 4 fichiers HTML + 3 fichiers JS pour une UI

```
Studio files:
├── index.html           ← production?
├── index-simple.html    ← fallback?
├── index_old.html       🔴 OLD - clearly stale
├── studioindex.html     ❓ DUPLICATE NAME?
├── studioapp.js         ← production?
├── studioapp-simple.js  ← fallback?
└── studioapp-old.js     🔴 OLD - clearly stale
```

**Problème:**
- Unclear which is production
- Old versions taking up space  
- Risk of old version being used by accident

**Solution:**
- Keep: index.html + index-simple.html
- Keep: studioapp.js + studioapp-simple.js
- Delete: *_old.html, studioindex.html, studioapp-old.js

---

### D. AGENTS ANALYSIS

**Découvertes Clés:**

#### ✅ NOT DUPLICATES (complementary):
- **trading-core.js** + **trade-logic.js** = Pipeline
  - trading-core = analysis engine (RSI, EMA, BOS/CHoCH, FVG detection)
  - trade-logic = explanation engine (WHY to enter/wait/avoid)

#### 🟡 POSSIBLE DUPLICATES (need verification):
1. **orchestrator.js** (MODERN) vs **coordinator.js** (LEGACY)
   - orchestrator: Master orchestration, Promise.all, 6 agents
   - coordinator: Price fetching, callbacks, 3 agents + Yahoo
   - Verdict: Keep orchestrator, can delete coordinator if not imported

2. **newsAgent.js** (MODERN) vs **news-intelligence.js** (LEGACY)
   - newsAgent: State-based, comprehensive (indicators, sentiment, geopolitical)
   - news-intelligence: Function-based, simple (events, fallback data)
   - Verdict: Keep newsAgent, can delete news-intelligence if not imported

#### ✅ ALL OTHER AGENTS (17+):
All unique, no duplication detected.

---

### E. SYMBOL MAPPING (NO DUPLICATION)

**Situation:** 4 fichiers différents, chacun avec rôle unique

| Fichier | Location | Role | Type |
|---------|----------|------|------|
| symbol-normalizer.js | /lib/ | Canonical profiles, patterns | Backend |
| symbol-matcher.js | /lib/ | TradingView → sources mapping logic | Backend |
| symbol-mapper.js | /tradingview-analyzer/ | Client-side symbol resolution | Extension |
| symbol-manager.js | /tradingview-analyzer/ | Extension symbol state mgmt | Extension |

**Verdict:** ✅ NO CONSOLIDATION NEEDED - Each serves different tier (backend vs extension)

---

### F. HTML FILES (ROOT LEVEL)

**Found:** 9 HTML files at root

| File | Purpose | Keeper? |
|------|---------|---------|
| index.html | ❓ Unknown | ? |
| popup.html | ❓ Duplicate of /public/popup.html? | ? |
| dashboard.html | ✅ Audit dashboard? | KEEP |
| audit-dashboard.html | ✅ Audit interface | KEEP |
| AGENTS_MONITOR.html | ✅ Agent monitor | KEEP |
| agent-log-page.html | ✅ Agent logs | KEEP |
| EXTENSION_TEST.html | ✅ Testing | KEEP |
| test-analysis.html | ✅ Testing | KEEP |
| test-chart-visual.html | ✅ Testing | KEEP |

**Status:** NEED TO ANALYZE - root popup.html may be duplicate

---

### G. ORPHANED FILES (ROOT)

| File | Purpose | Keep? | Status |
|------|---------|-------|--------|
| agent.js | ❓ | ? | UNCLEAR |
| agent-worker.js | ❓ Worker pattern? | ? | UNCLEAR |
| agent-bus.js | ❓ Message bus? | ? | UNCLEAR |
| access.js | ❓ Access control? | ? | UNCLEAR |
| AGENT_BUS.json | ❓ | ? | UNCLEAR |
| mt5_bridge_simple.js | ✅ MT5 interface | ✅ KEEP | CLEAR |
| audit-logger.js | ✅ Audit logging | ✅ KEEP | CLEAR |
| PORT_CONFIG.js | ✅ Port configuration | ✅ KEEP | CLEAR |

**Status:** Need to grep imports before deciding on deletion

---

## 🔧 CHANGEMENTS PLANIFIÉS

### Phase 1: Structure Cleanup (THIS WEEK)

#### Action A: Extension UI
Choose ONE:
- **A1 (Recommended):** Keep /public/, archive /tradingview-analyzer extension files
- **A2:** Keep /tradingview-analyzer/, archive /public extension files

#### Action B: Server
- **DELETE:** /public/server.js  
- **KEEP:** /server.js (root, port 4000)
- **Verify:** No imports of public/server.js

#### Action C: Studio UI
- **KEEP:** index.html + index-simple.html
- **KEEP:** studioapp.js + studioapp-simple.js
- **DELETE:** index_old.html, studioindex.html, studioapp-old.js

#### Action D: Agents
- **DELETE:** coordinator.js (if no imports found)
- **DELETE:** news-intelligence.js (if no imports found)
- **KEEP:** orchestrator.js, newsAgent.js (modern, complete versions)
- **KEEP:** trading-core.js + trade-logic.js (complementary, not duplicates)
- **KEEP:** all 17+ other agents (all unique)

#### Action E: Backup Cleanup
- **DELETE:** /tradingview-analyzer_backup_20260402/ (stale, 2026-04-02)
- **REASON:** Fresh backup at /backup/2026-04-03_073752_pre_phase1_audit/

#### Action F: Data Consolidation
- **Single source:** /store/mt5_data.json or /mt5_data.json (to be determined)
- **Archive:** duplicate mt5_data files

### Phase 2: Implementation (AFTER CLEANUP)

#### indicator-engine.js
- Built on candle-manager
- RSI(14), MACD(12,26,9), BB(20,2), ATR(14), MA(20,50,200)
- Event-driven (candle:closed → calculate indicators → emit indicators:ready)
- Est: 6-8 hours dev + 2 hours testing

#### orchestrator-realtime.js
- Listens to indicators:ready
- Runs agents in parallel
- Validates symbol state (READY vs INIT vs MISSING)
- Est: 4-5 hours dev

#### sync-broadcaster.js
- Coordinates SSE broadcasts to clients
- 3-message sequence (candle_closed, indicators_calculated, signal_generated)
- Est: 2-3 hours dev

#### Server Integration
- POST /api/mt5/tick endpoint
- Wire candle-manager.onTick(data)
- Start close-detection timer
- Est: 3-4 hours

#### Client Updates
- Extension popup event handlers
- Studio chart auto-update
- Dashboard signal table
- Est: 6-8 hours

### Phase 3: Testing & Validation

#### Unit Tests
- candle-manager.test.js (10 tests) ✅ READY
- indicator-engine.test.js (10-15 tests)
- orchestrator-realtime.test.js (5-10 tests)

#### Integration Tests
- Tick → Candle close → Indicators → Agents → Signal
- SSE broadcast coordination
- Multi-client synchronization

#### E2E Tests
- Full flow: MT5 tick → signal → client UI

---

## 📊 ÉTAT ACTUEL

### Statut des Modules

| Module | Phase | Status | Progress | ETA |
|--------|-------|--------|----------|-----|
| candle-manager.js | 1 | 🟢 COMPLETE | 100% | Tests pending |
| indicator-engine.js | 2 | 🔴 NOT STARTED | 0% | After Ph1 approval |
| orchestrator-realtime.js | 3 | 🔴 NOT STARTED | 0% | After Ph2 approval |
| sync-broadcaster.js | 4 | 🔴 NOT STARTED | 0% | After Ph3 approval |
| Server integration | 5 | 🔴 NOT STARTED | 0% | After Ph4 approval |
| Client updates | 6 | 🔴 NOT STARTED | 0% | After Server |
| Testing | 7 | 🔴 NOT STARTED | 0% | After all modules |

### Statut Cleanup

| Item | Status | Notes |
|------|--------|-------|
| Audit complete | 🟢 YES | Inventory + detailed analysis done |
| Import verification | 🟡 PENDING | Need to grep coordinator, news-intel, public/server |
| Decision approval | 🟡 PENDING | Awaiting user choices on A1/A2, cleanup level |
| Backup organized | 🟡 PENDING | Structure ready, execution pending |
| Files archived | 🔴 NOT STARTED | Awaiting decision approval |
| Project structure validated | 🔴 NOT STARTED | Awaiting cleanup completion |

---

## 🚀 PROCHAINES ÉTAPES

### IMMEDIATE (Next 30 min)

1. ✅ Complete audit documentation
2. ⏳ Verify imports (coordinator.js, news-intelligence.js, /public/server.js)
3. ⏳ Analyze root-level HTML files
4. ⏳ Create comprehensive import map

### SHORT TERM (This hour)

1. ⏳ Get user decisions on cleanup options
2. ⏳ Execute cleanup with full traceability
3. ⏳ Validate no broken imports
4. ⏳ Run Phase 1 tests (candle-manager)

### FOLLOW-UP (After cleanup approval)

1. ⏳ Phase 2: Implement indicator-engine
2. ⏳ Phase 3: Implement orchestrator-realtime
3. ⏳ Phase 4: Implement sync-broadcaster
4. ⏳ Server integration
5. ⏳ Client updates
6. ⏳ Full testing suite

---

## 📝 NOTES & DECISIONS

### Decision Log

**Decision 1: Extension UI**
- User preference: (awaiting)
- Chosen: (awaiting)
- Date: (awaiting)

**Decision 2: Studio UI**
- Recommendation: Keep index.html + index-simple.html
- User preference: (awaiting confirmation)
- Chosen: (awaiting)
- Date: (awaiting)

**Decision 3: Cleanup Level**
- Recommendation: Option 2 (Moderate)
- User preference: (awaiting)
- Chosen: (awaiting)
- Date: (awaiting)

### Risks Identified

1. **Import breaking**: coordinator.js or news-intelligence.js may be imported somewhere → verify before delete
2. **public/server.js**: May be required by extension or tests → verify before delete  
3. **Studio UI**: Users may have bookmarks to old versions → document new canonical URL
4. **Extension conflicts**: Both v1 and v2 may coexist in browser → clear migration path needed

### Mitigation

✅ All files backed up at `/backup/2026-04-03_073752_pre_phase1_audit/`  
✅ Additional archive at `/backup/archive_2026-04-03/` (created during cleanup)  
✅ Full import map before any deletion  
✅ Validation testing after cleanup

---

## 📈 SUCCESS METRICS

**Cleanup Complete When:**
- ✅ All decisions made and documented
- ✅ All imports verified (no breaking changes)
- ✅ All old files archived with manifest
- ✅ Project structure validated
- ✅ No broken references in codebase

**Phase 1 Complete When:**
- ✅ candle-manager tests pass 10/10
- ✅ "go Phase 2" decision made

**Overall Success When:**
- ✅ 4-phase system implemented end-to-end
- ✅ Phase 7 (testing) complete
- ✅ Full real-time system operational
- ✅ No fluff, no legacy code, no confusion

---

**Document Status:** 🟡 LIVE UPDATE  
**Last Action:** Cleanup planning phase  
**Next Milestone:** User decision + cleanup execution
