# EXECUTION_PLAN_COMPLETE.md

**Status:** 🟡 PLANNING  
**Date:** 2026-04-03 07:55  
**Goal:** Complete cleanup, organization, and Phase 1 execution ready-state

---

## ⏱️ TIME ESTIMATES (TOTAL: 3-4 HOURS)

| Phase | Task | Est. Time |
|-------|------|-----------|
| **ANALYSIS** | Verify imports + HTML analysis | 30 min |
| **DOCUMENTATION** | Create final audit documents | 20 min |
| **BACKUP** | Archive deletable files | 15 min |
| **CLEANUP** | Execute deletions + moves | 20 min |
| **VALIDATION** | Verify no broken imports | 15 min |
| **PHASE 1 TESTING** | Run candle-manager tests | 30 min |
| **BUFFER** | For any issues | 30 min |
| **TOTAL** | **4 hours (worst case)** | |

---

## 🎯 PHASE 1: VERIFY IMPORTS (30 min)

**Task 1.1: Check who imports coordinator.js**
```
grep -r "coordinator" /src/ /lib/ /studio/
```

**Task 1.2: Check who imports news-intelligence.js**
```
grep -r "news-intelligence" /src/ /lib/ /studio/
```

**Task 1.3: Check who imports /public/server.js**
```
grep -r "/public/server" /src/ /lib/
```

**Task 1.4: Analyze all HTML files**
- Read all root-level HTML (9 files)
- Understand purpose of each
- Identify duplicates, stale versions

**Deliverable:** 
- Import verification report
- HTML analysis report

---

## 📋 PHASE 2: DOCUMENTATION (20 min)

**Task 2.1: Create comprehensive import map**
```
SYSTEM_IMPORTS.md
- Every require/import
- Where it comes from
- Where it goes to
- Safe to delete? YES/NO
```

**Task 2.2: Create final audit summary**
```
AUDIT_FINAL_SUMMARY.md
- All findings
- All recommendations
- Decision matrix (KEEP/DELETE/ARCHIVE)
```

**Task 2.3: Create SYSTEM_HISTORY.md**
```
SYSTEM_HISTORY.md
- What existed
- What we found
- What we will change
- Why
- Remaining work
```

**Deliverable:**
- 3 new markdown documents
- Clear decision matrix
- Complete traceability

---

## 🗂️ PHASE 3: ORGANIZE BACKUPS (15 min)

**Task 3.1: Create archive structure**
```
/backup/archive_2026-04-03/
  ├── /deleted_files/
  │   ├── coordinator.js
  │   ├── news-intelligence.js
  │   ├── public_server.js
  │   ├── studio/index_old.html
  │   ├── studio/studioindex.html
  │   ├── studio/studioapp-old.js
  │   └── [others to be determined]
  /
  ├── /extension_v2_archive/
  │   └── (tradingview-analyzer extension files if choosing v1)
  │
  ├── /studio_old_versions/
  │   └── (old studio files)
  │
  └── ARCHIVE_MANIFEST.md
      (list of what was archived and why)
```

**Deliverable:**
- Organized backup structure
- Archive manifest
- Clear traceability

---

## 🧹 PHASE 4: EXECUTE CLEANUP (20 min)

**Task 4.1: Delete coordinator.js**
- Verify: not imported anywhere
- Move to /backup/archive_2026-04-03/deleted_files/

**Task 4.2: Delete news-intelligence.js**
- Verify: not imported anywhere
- Move to /backup/archive_2026-04-03/deleted_files/

**Task 4.3: Delete /public/server.js** (keep root /server.js)
- Move to /backup/archive_2026-04-03/deleted_files/

**Task 4.4: Clean up Studio UI**
- DELETE: /studio/index_old.html
- DELETE: /studio/studioindex.html
- DELETE: /studio/studioapp-old.js
- KEEP: /studio/index.html
- KEEP: /studio/index-simple.html  
- KEEP: /studio/studioapp.js
- KEEP: /studio/studioapp-simple.js

**Task 4.5: Choose & Archive Extension**
- Option A1: KEEP /public/, ARCHIVE /tradingview-analyzer extension files
  - Move: /tradingview-analyzer/{popup.html, popup.js, manifest.json, background.js, content.js} to archive
  - KEEP: /tradingview-analyzer/{chart-module.js, ai-debugger.js, news-engine.js, etc.}
  
  OR
  
- Option A2: KEEP /tradingview-analyzer/, ARCHIVE /public extension files
  - Move: /public/{popup.html, popup.js, manifest.json, background.js, content.js} to archive
  - KEEP: /public/{dev-helper.js, ...}

**Task 4.6: Delete stale backup**
- DELETE: /tradingview-analyzer_backup_20260402/

**Task 4.7: Consolidate mt5_data**
- Single source: /store/mt5_data.json (or /mt5_data.json)
- Archive duplicates

**Deliverable:**
- Cleaned project structure
- All deletions backed up
- Clear manifest

---

## ✅ PHASE 5: VALIDATE (15 min)

**Task 5.1: Verify no broken imports**
- If coordinator.js was deleted, verify nothing requires it
- If news-intelligence.js was deleted, verify nothing requires it
- If server.js was deleted, verify nothing requires it

**Task 5.2: Check project structure**
```
/lib/                    ✅ Clean (no duplicates)
/src/agents/            ✅ Cleaned (old files removed)
/src/services/          ✅ Clean
/public/                ✅ One extension version
/tradingview-analyzer/  ✅ Either moved or kept
/studio/                ✅ Only active versions
/store/                 ✅ Single data source
/backup/                ✅ Organized archives
```

**Task 5.3: Verify no build/run errors**
```
node server.js          ← Should start without error
npm list                ← All dependencies intact
```

**Deliverable:**
- Validation report
- Project structure clean
- No broken references

---

## 🧪 PHASE 6: PHASE 1 TESTING (30 min)

**Task 6.1: Run candle-manager tests**
```
node tests/unit/candle-manager.test.js
```

**Expected:** 10/10 tests PASS

**Task 6.2: Report test results**
```
PHASE1_TEST_RESULTS.md
- Each test result
- Statuses
- Any failures
- Next steps
```

**Task 6.3: If failures, debug and fix**
- 15-20 min reserved for fixes if needed

**Deliverable:**
- Test results
- Phase 1 validation complete
- Ready for Phase 2

---

## 📊 DECISION MATRIX (USER INPUT REQUIRED)

### DECISION 1: Extension UI Version
- [ ] A1: Keep /public/ (recommended - lighter, standard structure)
- [ ] A2: Keep /tradingview-analyzer/ (more features)

### DECISION 2: Studio UI Version  
- [x] C1: Keep index.html + index-simple.html, DELETE old files (recommended)
- [ ] C2: Keep ONLY index.html (aggressive)

### DECISION 3: Cleanup Level
- [ ] Option 1: Conservative (only obviously stale)
- [x] Option 2: Moderate (recommended)
- [ ] Option 3: Aggressive (clean slate)

---

## 📋 ORDERS OF OPERATION

### IF NO DECISION PROVIDED:
Use **RECOMMENDED DEFAULTS**:
- Extension: A1 (/public/)
- Studio: C1 (main + simple)
- Cleanup: Option 2 (moderate)
- Agents: Delete coordinator, news-intelligence
- Orphaned: DOCUMENT, then delete if unused

### IF DECISIONS PROVIDED:
Execute exactly as specified.

---

## 📁 FINAL PROJECT STRUCTURE (AFTER CLEANUP)

```
trading-auto/
├── /lib/                           ✅ CLEAN
│   ├── candle-manager.js          (NEW Phase 1)
│   ├── indicator-engine.js        (PENDING Phase 2)
│   ├── sync-broadcaster.js        (PENDING Phase 4)
│   ├── data-source-manager.js     (KEEP)
│   ├── symbol-normalizer.js       (KEEP)
│   ├── symbol-matcher.js          (KEEP)
│   ├── chart-renderer.js          (KEEP)
│   └── broker-calculator.js       (KEEP)
│
├── /src/
│   ├── /agents/                   ✅ CLEANED
│   │   ├── orchestrator.js        (PRIMARY)
│   │   ├── trading-core.js        (KEEP)
│   │   ├── trade-logic.js         (KEEP)
│   │   ├── newsAgent.js           (PRIMARY)
│   │   └── [17 other agents]      (ALL OTHER KEPT)
│   │   ✗ coordinator.js deleted
│   │   ✗ news-intelligence.js deleted
│   │
│   └── /services/
│       ├── symbol-preferences.js  (KEEP)
│       └── fileService.js         (KEEP)
│
├── /public/                        ✅ ONE EXTENSION VERSION
│   ├── popup.html, popup.js
│   ├── manifest.json, background.js, content.js
│   └── dev-helper.js
│
├── /studio/                        ✅ CONSOLIDATED
│   ├── index.html, studioapp.js
│   ├── index-simple.html, studioapp-simple.js
│   ├── app.js, styles.css
│   ✗ index_old.html deleted
│   ✗ studioindex.html deleted
│   ✗ studioapp-old.js deleted
│
├── /store/                         ✅ CLEAN
│   ├── market-store.js
│   └── mt5_data.json (single source)
│
├── /backup/                        ✅ ORGANIZED
│   ├── /2026-04-03_073752_pre_phase1_audit/ (original backup)
│   └── /archive_2026-04-03/
│       ├── /deleted_files/
│       ├── /extension_v2_archive/
│       ├── /studio_old_versions/
│       └── ARCHIVE_MANIFEST.md
│
├── /tests/                         ✅ READY
│   └── /unit/
│       └── candle-manager.test.js
│
└── ROOT                           ✅ CLEAN
    ├── server.js                  (PRIMARY - Port 4000)
    ├── mt5_bridge_simple.js       (KEEP)
    ├── audit-logger.js            (KEEP)
    ├── PORT_CONFIG.js             (KEEP)
    ├── package.json               (KEEP)
    └── [data files preserved]
    ✗ /public/server.js deleted
```

---

## 📈 SUCCESS CRITERIA

✅ **Phase 1 Complete When:**
1. All imports verified (no broken references)
2. All old/duplicate files deleted or archived
3. Project structure clean
4. candle-manager tests pass 10/10
5. Complete audit trail documented
6. User ready for Phase 2: indicator-engine

---

## 🚀 NEXT PHASE (After cleanup approval)

**Phase 2: indicator-engine.js**
- Implement RSI, MACD, BB, ATR, MA calculations
- ~6-8 hours development
- ~2 hours testing
- Integration with candle-manager (event-driven)

---

**Status:** Ready for execution upon user decision  
**Decision Matrix:** Awaiting input (or use recommended defaults)  
**Backup:** ✅ Pre-cleanup snapshot secured at `/backup/2026-04-03_073752_pre_phase1_audit/`
