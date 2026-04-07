# 📋 PENDING_TASKS - File d'Attente Complète

**Generated:** 2026-04-03 08:22  
**Status:** 🟡 ORGANIZED BY PRIORITY  

---

## 📊 SUMMARY

```
🟢 READY (no blockers)      : 8 tasks
🟡 ANALYSIS PHASE          : 12 tasks
🔴 BLOCKED (awaiting input) : 5 tasks
⏳ NEXT PHASES (Phase 2-4)   : 4 tasks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOTAL TASKS                  : 29 tasks
```

---

## 🟢 IMMEDIATELY READY (Can Execute Now)

### CLEANUP - Safe to Execute
```
[001] Delete studio/index_old.html
      Status: ✅ SAFE TO DELETE (clearly old, no imports)
      Lines: ~500 (estimate)
      Time: 1 min
      Risk: ✅ ZERO
      Decision: AUTO-DELETE (no user choice needed)
      
[002] Delete studio/studioindex.html  
      Status: ✅ SAFE TO DELETE (archival, not used)
      Lines: ~400 (estimate)
      Time: 1 min
      Risk: ✅ ZERO
      Decision: AUTO-DELETE

[003] Delete tradingview-analyzer_backup_20260402/
      Status: ✅ SAFE TO DELETE (stale backup)
      Time: 1 min (move to /backup/pending/)
      Risk: ✅ ZERO
      Decision: AUTO-DELETE

[004] Verify & Archive public/server.js
      Status: 🟡 NEEDS VERIFICATION (separate Node server?)
      Check: Imported anywhere? (preliminary: NO imports found)
      Time: 5 min (grep + decision)
      Risk: 🟡 LOW (if no imports)
      Decision: IF NOK IMPORTS FOUND → DELETE to /backup/pending/
```

### ANALYSIS - Critical Decisions (Small)
```
[005] Map all studio endpoints in server.js
      Status: ✅ DONE (in SYSTEM_MAP.md)
      Endpoints: /studio, /studio/*, /data, /agent-screen, etc.
      Time: ALREADY DONE
      
[006] Verify HTML serving order (no duplication)
      Status: 🟡 IN PROGRESS
      Concern: /popup, popup.html, public/popup.html (3 sources?)
      Action: Trace which is actually served
      Time: 10 min
      
[007] Confirm agent imports (all ACTIVE)
      Status: ✅ DONE (coordinator + orchestrator verified)
      Verified: All 23+ agents are kept (no duplicates)
      
[008] Audit missing reference files
      Status: 🟡 TODO
      Concern: agent.js, agent-worker.js, AGENT_BUS.json, access.js
      Action: Check if imported or orphaned
      Time: 10 min
```

---

## 🟡 ANALYSIS PHASE (Ongoing Now)

### Phase 1A: Deep Code Analysis

```
[009] Complete server.js endpoint audit
      Status: 🟡 IN PROGRESS (70+ endpoints documented)
      Completeness: 90% (SYSTEM_MAP created)
      Remaining: Verify live/paper mode separation
      Time: 10 min
      
[010] Trace all frontend JS dependencies
      Status: 🟡 TODO
      Concern: Which JS files load which modules?
      Files to check:
        - studioapp-simple.js → dependencies
        - studioapp.js → dependencies
        - popup.js (v1 vs v2)
        - background.js (service worker)
        - content.js (page injection)
      Time: 20 min
      
[011] Create import graph (circular deps?)
      Status: 🟡 TODO
      Check: Any circular requires? Any unused imports?
      Time: 15 min
      
[012] Analyze agent usage patterns
      Status: 🟢 PARTIAL (orchestrator+coordinator verified)
      Remaining: Verify all 23 agents are called by someone
      Time: 10 min

[013] Map symbol preference flow
      Status: 🟡 TODO
      Trace: How user prices flow through system
      Path: popup → server → symbol-preferences → orchestrator
      Time: 10 min
      
[014] Verify real-time data paths
      Status: 🟡 TODO
      Trace: MT5 → mt5_data.json → server.js → /stream → UI
      Time: 10 min
      
[015] Catalog all test files
      Status: 🟡 TODO
      Check: tests/ directory contents
      Decision: Keep or delete?
      Time: 5 min
      
[016] Document HTML asset loading
      Status: 🟡 TODO
      Check: Which HTML loads which CSS/JS?
      Purpose: Identify unused assets
      Time: 15 min
      
[017] Verify Python bridge dependencies
      Status: 🟡 TODO
      Check: mt5_bridge.py requirements vs requirements-mt5.txt
      Time: 10 min
      
[018] Create handler/controller map
      Status: 🟡 TODO
      Analysis: Which server endpoints use which handler?
      Purpose: Optimize endpoint organization
      Time: 15 min

[019] Identify middleware dependencies
      Status: 🟡 TODO
      Check: CORS, body-parser, static paths, error handling
      Time: 10 min
      
[020] Map browser extension architecture
      Status: 🟡 TODO
      Concern: public/ vs tradingview-analyzer/ (which is active?)
      Check: manifest.json versions, permissions, ports
      Time: 15 min
```

### Phase 1B: Duplication Analysis

```
[021] Resolve popup.html duplicate sources
      Status: 🟡 BLOCKED
      Sources Found:
        - /popup.html (root, 359 lines)
        - /public/popup.html (extension v1)
        - /tradingview-analyzer/popup.html (extension v2)
      Decision Needed: Which ONE to keep?
      Impact: HIGH (affects extension functionality)
      Time: Take decision when user reviews cleanup options
      
[022] Resolve server duplication  
      Status: ✅ IDENTIFIED
      Issue: /public/server.js (separate server?)
      Check: Not imported anywhere, safe to delete
      Decision: Move to /backup/pending/ (Option 1-2-3)
      
[023] Resolve studio index confusion
      Status: ✅ IDENTIFIED
      Files: index.html, index-simple.html, index_old.html
      Decision: Keep index-simple.html (only used), delete others
      
[024] Map background.js duplicates
      Status: 🟡 TODO
      Issue: /public/background.js vs /tradingview-analyzer/background.js
      Decision: Depends on extension choice (A1: /public vs A2: /tradingview-analyzer)
```

---

## 🔴 BLOCKED - Awaiting User Input

```
[025] USER DECISION: Extension Choice
      Options:
        A1: Keep /public/ extension (lighter, standard)
        A2: Keep /tradingview-analyzer/ extension (more features)
      Impact: Determines which popup.html, background.js, manifest.json to keep
      Time Estimate: 2 min decision
      Blocking: Tasks [021], cleanup execution
      ⏳ STATUS: WAITING FOR USER

[026] USER DECISION: Cleanup Aggressiveness  
      Options:
        Option 1: Conservative (only obvious deletes)
        Option 2: Moderate (delete old + stale) ← RECOMMENDED
        Option 3: Aggressive (delete even old extensions)
      Impact: Determines cleanup scope
      Time Estimate: 2 min decision
      Blocking: Cleanup execution
      ⏳ STATUS: WAITING FOR USER

[027] USER DECISION: Keep Phase 1 Backup?
      Question: Archive pre-cleanup backup?
      Options:
        YES: Keep /backup/2026-04-03_073752_pre_phase1_audit/
        NO: Delete (save disk space)
      Impact: Disk usage (~100MB estimate)
      Time Estimate: 1 min decision
      ⏻ STATUS: WAITING FOR USER (default: YES)

[028] USER DECISION: Cleanup Timing
      Question: Execute now or wait for Phase 1 tests?
      Options:
        BEFORE tests: Clean first, then test candle-manager
        AFTER tests: Test first, then clean
      Recommended: BEFORE (cleaner state for Phase 1)
      Time Estimate: 1 min decision
      ⏻ STATUS: WAITING FOR USER

[029] USER DECISION: Test Environment
      Question: Run Phase 1 tests in isolation or with full system?
      Options:
        ISOLATED: Mock all dependencies
        FULL: Run against live server + MT5 (if available)
      Time Estimate: 1 min decision
      Recommended: ISOLATED (faster, deterministic)
      ⏻ STATUS: WAITING FOR USER
```

---

## ⏳ NEXT PHASES (After Decision + Cleanup)

```
[030] Phase 1: Execute Cleanup
      Subtasks:
        - Archive/delete old files (Task [001-004])
        - Archive non-chosen extension (Task [021])
        - Update imports (if any broken)
        - Verify no broken refs (grep check 5x)
      Time: 20-30 min
      Blocking: Phase 1 tests
      
[031] Phase 1: Run Candle-Manager Tests
      Subtasks:
        - Run 10 unit tests
        - Generate PHASE1_TEST_RESULTS.md
        - All tests PASS or identify failures
      Time: 30 min
      Expected Result: ✅ ALL PASS
      Blocking: Phase 2 dev start
      
[032] Phase 2: Implement Indicator-Engine
      Subtasks:
        - 600-800 lines of code
        - RSI, MACD, Bollinger, ATR, MA
        - Event-driven on candle:closed
        - 20 unit tests
      Time: 6-8 hours
      Blocking: Phase 3
      
[033] Phase 3: Implement Orchestrator-Realtime
      Subtasks:
        - 400-500 lines
        - Listen indicators:ready
        - Run agents in parallel
        - Symbol state machine
      Time: 4-5 hours
      Blocking: Phase 4
      
[034] Phase 4: Implement Sync-Broadcaster
      Subtasks:
        - 300-400 lines
        - SSE coordination (3-sequence)
        - Client synchronization
      Time: 2-3 hours
      Blocking: Integration testing
```

---

## 📅 TIMELINE

```
PHASE 0   Analysis (CURRENT)              ~ 1 hour  (in progress)
          └─ Tasks 001-020 (most done)
          └─ SYSTEM_MAP.md created ✅
          └─ Awaiting user decision (Task 025-029)

PHASE 1   Cleanup + Phase 1 Tests         ~ 1 hour
          └─ Tasks 030-031
          └─ Execution: TBD (when user decides)

PHASE 2   Phase 2 Implementation          ~ 6-8 hours
          └─ Tasks 032
          └─ Execution: After Phase 1 tests pass

PHASE 3   Phase 3 Implementation          ~ 4-5 hours
          └─ Tasks 033
          └─ Execution: After Phase 2 complete

PHASE 4   Phase 4 Implementation          ~ 2-3 hours
          └─ Tasks 034
          └─ Execution: After Phase 3 complete

INTEGRATION: Service + Client integration  ~ 3-4 hours
TESTING:    End-to-end validation        ~ 2-3 hours

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOTAL TIMELINE (If All Go Smoothly):       ~ 18-22 hours
```

---

## 🎯 CRITICAL PATH

```
1. USER INPUT (Tasks 025-029)           ← BLOCKER #1
   ↓
2. ANALYSIS COMPLETE (Tasks 009-024)    ← In progress now
   ↓
3. CLEANUP EXECUTE (Task 030)            ~ 20-30 min
   ↓
4. PHASE 1 TESTS (Task 031)              ~ 30 min
   ↓
5. PHASE 2 DEV (Task 032)                ~ 6-8 hours
   ↓
6. PHASE 3 DEV (Task 033)                ~ 4-5 hours
   ↓
7. PHASE 4 DEV (Task 034)                ~ 2-3 hours
   ↓
8. INTEGRATION TESTING                   ~ 3-4 hours
```

---

## 📊 PRIORITIES BY IMPACT

### 🔴 CRITICAL (Blocks Everything)
- Task 025: Extension choice (A1/A2)
- Task 026: Cleanup scope (Option 1/2/3)

### 🟠 HIGH (Blocks Phases)
- Task 030: Cleanup execution
- Task 031: Phase 1 tests

### 🟡 MEDIUM (Quality)
- Tasks 009-020: Deep analysis
- Tasks 021-024: Duplication resolution

### 🟢 LOW (Nice to Have)
- Task 027: Archive decision
- Task 028: Timing preference

---

## ✅ COMPLETION CHECKLIST

- [ ] All analysis complete (Tasks 001-024)
- [ ] User decisions received (Tasks 025-029)
- [ ] Cleanup executed (Task 030)
- [ ] Phase 1 tests PASS (Task 031)
- [ ] Phase 2 code written (Task 032)
- [ ] Phase 3 code written (Task 033)
- [ ] Phase 4 code written (Task 034)
- [ ] Integration testing complete
- [ ] Real-time system working end-to-end

---

Generated: 2026-04-03 08:22  
Next Action: User provides decisions → Execute cleanup → Phase 1 tests
