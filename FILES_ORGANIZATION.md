# 📂 FILES_ORGANIZATION - Structure Proposée

**Generated:** 2026-04-03 08:25  
**Status:** 🟡 PRE-CLEANUP PLAN  

---

## 📊 DIRECTORY STRUCTURE (Current vs Proposed)

### Current Main Level: 35+ files + 10 folders

```
trading-auto/  (ROOT)
├─ server.js (KEEP - main server)
├─ index.html (KEEP - main menu)
├─ studio/ (folder)
├─ lib/ (folder)
├─ src/ (folder)
├─ store/ (folder)
├─ analysis/ (folder)
├─ public/ (folder - extension v1)
├─ tradingview-analyzer/ (folder - extension v2)
├─ backup/ (folder - snapshots)
├─ tests/ (folder)
├─ trading/ (folder)
└─ [17 more files to organize]
```

---

## 🎯 ORGANIZATION GOALS

### Priority 1: Core System (NEVER TOUCH)
```
✅ KEEP ALWAYS:
  - server.js (main server - UNTOUCHABLE)
  - /src/agents/ (23+ agents - VERIFIED ACTIVE)
  - /src/services/ (symbol-preferences, etc.)
  - /lib/ (utilities: symbol-normalizer, candle-manager, etc.)
  - /store/ (market-store.js - data cache)
  - mt5_data.json (real data writes)
  - package.json, node_modules dependencies
```

### Priority 2: Active UI Portals
```
✅ KEEP ALWAYS:
  - /index.html (main landing)
  - /studio/index-simple.html (trading interface) [EXE]
  - /dashboard.html (MT5 viewer)
  - /popup.html (extension UI)
  - /agent-log-page.html (hub)
  - /AGENTS_MONITOR.html (monitoring)
  - /audit-dashboard.html (status)
```

### Priority 3: Test/Debug (Conditional)
```
🟡 DECIDE:
  - /test-analysis.html (keep for dev)
  - /test-chart-visual.html (keep for dev)
  - /tests/ folder (unit tests)
  - ⏱️ DECISION: Keep during Phase 1/2, then decide move→archive
```

### Priority 4: Duplicates/Cleanup
```
❌ DELETE OR ARCHIVE:
  - studio/index.html (use index-simple instead)
  - studio/index_old.html (clearly old) ← DELETE
  - studio/studioindex.html (archival) ← DELETE
  - tradingview-analyzer_backup_20260402/ ← DELETE
  - public/server.js (separate server, not used) ← DELETE
```

### Priority 5: Extension Files (User Choice)
```
⚠️ ONE OF:
  A1: Keep /public/ extension (lighter) ← RECOMMENDED
      - public/popup.html
      - public/background.js
      - public/content.js
      - public/manifest.json
      → DELETE /tradingview-analyzer/
  
  B1: Keep /tradingview-analyzer/ extension (more features)
      - tradingview-analyzer/popup.html
      - tradingview-analyzer/background.js
      - tradingview-analyzer/content.js
      - tradingview-analyzer/manifest.json
      → DELETE /public/
```

---

## 📋 FILE CATALOG (All 35+ Root Files)

### ✅ CORE (Never Delete)
```
[✅] server.js
     Size: 2850+ lines
     Purpose: Main Express server
     Imports: 50+ routes, all agents
     Safety: CRITICAL - DO NOT TOUCH
     
[✅] package.json
     Purpose: Dependencies
     Safety: CRITICAL - DO NOT TOUCH

[✅] index.html
     Size: 490 lines
     Purpose: Main menu portal (8 cards)
     Routes: Links to all other portals
     Safety: ACTIVE - DO NOT DELETE
```

### ✅ ACTIVE UI
```
[✅] studio/index-simple.html
     Size: 300 lines
     Purpose: Main trading interface (LightweightCharts)
     Route: GET /studio
     Status: ACTIVELY USED ✅
     
[✅] dashboard.html
     Size: 280 lines
     Purpose: MT5 data viewer
     Status: ACTIVELY USED ✅
     
[✅] popup.html
     Size: 359 lines
     Purpose: Extension popup UI
     Status: ACTIVELY USED ✅
     Note: ROOT version (not in /public/ or /tradingview-analyzer/)
     
[✅] agent-log-page.html
     Size: 900 lines
     Purpose: HUB CENTRAL (agent monitoring)
     Status: ACTIVELY USED ✅
     
[✅] AGENTS_MONITOR.html
     Size: 400 lines
     Purpose: Agent monitoring interface
     Status: ACTIVELY USED ✅
     
[✅] audit-dashboard.html
     Purpose: Audit/status dashboard
     Status: ACTIVELY USED ✅
     
[✅] EXTENSION_TEST.html
     Purpose: Extension testing interface
     Status: TEST - keep for dev
```

### 🟡 OLD/DUPLICATE STUDIO
```
[❌] studio/index.html
     Note: Not used (server uses index-simple.html instead)
     Action: DELETE
     Backup: Make snapshot first
     
[❌] studio/index_old.html
     Note: Clearly old version
     Action: DELETE
     
[❌] studio/studioindex.html
     Note: Archival version
     Action: DELETE
```

### 🤔 CONFIGURATION FILES
```
[✅] PORT_CONFIG.js
     Status: KEEP
     
[✅] SAFE_MODE_CONFIG.json
     Status: KEEP
     
[?] QUICK_START.bat, START*.bat
    Status: Batch scripts - KEEP for convenience
    
[?] ARCHITECTURE.md, README.md
    Status: Documentation - KEEP
```

### 📊 DATA & LOGS
```
[✅] mt5_data.json
     Type: Real MT5 data (written by EA)
     Status: KEEP - actively used
     
[✅] logs.json
     Type: System logs
     Status: KEEP - data file
     
[✅] SYSTEM_LOG.json
     Type: Audit logs
     Status: KEEP - data file
     
[✅] tasks.json
     Type: Task queue
     Status: KEEP - data file
     
[✅] AGENT_BUS.json
     Type: Agent messaging
     Status: KEEP - data file
     
[?] EXTENSION_TEST.html (🤔 data file or test file?)
     Status: TEST UI - keep for Phase 1/2
```

### 📚 DOCUMENTATION
```
[✅] README.md
     Status: KEEP
     
[✅] ARCHITECTURE.md
     Status: KEEP
     
[✅] tradingview-analyzer/00_START_HERE.md
     Status: Check if used
     
[?] tradingview-analyzer/PRE_LAUNCH_CHECKLIST.md
     Status: Check if used
     
[?] tradingview-analyzer/*_ANALYSIS_REPORT.md
     Status: Check if needed
```

### 🤔 ANALYSIS EXPORTED
```
[?] agent-export/ folder
    Contents: *.txt files (looks like exports)
    Action: Examine + decide to move to backup/
    
[?] analysis/ folder  
    Contents: analyzer.js + data?
    Action: Examine + keep if active
```

### 🗂️ PENDING REVIEW
```
[?] agent.js, agent-worker.js, AGENT_BUS.json, access.js
    Status: Orphaned? (in preliminary scan)
    Action: grep search to verify imports
    Decision: Delete or keep
```

### 📦 PUBLIC EXTENSION (v1)
```
[decision A1 → KEEP] or [A2 → DELETE]

public/
  ├─ [keep] popup.html or → /popup.html ???
  ├─ [keep] background.js
  ├─ [keep] content.js
  ├─ [keep] manifest.json
  ├─ [keep] popup.js
  ├─ [keep] dev-helper.js (dev tools)
  ├─ [DELETE] server.js (separate server, unused)
  ├─ [keep] requirements.txt
  └─ [delete] index.html (if exists)
```

### 📦 TRADINGVIEW-ANALYZER (v2)
```
[decision A2 → KEEP] or [A1 → DELETE all]

tradingview-analyzer/
  ├─ [conditional] All files
  ├─ [DELETE] tradingview-analyzer_backup_20260402/
  └─ [DELETE] if user chooses A1
```

### ✅ TEST FILES
```
[keep for Phase 1/2] tests/ folder
tests/
  └─ integration/ (test files)
  
[keep for Phase 1/2] test-analysis.html, test-chart-visual.html
```

---

## 🗑️ DELETE CANDIDATES (Pre-Decision)

### Tier 1: Safe Auto-Delete
```
[001] studio/index_old.html ✅ SAFE
      Reason: Clearly old version
      Risk: ZERO (nothing imports it)
      
[002] studio/studioindex.html ✅ SAFE
      Reason: Archival naming
      Risk: ZERO
      
[003] tradingview-analyzer_backup_20260402/ ✅ SAFE
      Reason: Old backup folder
      Risk: ZERO
```

### Tier 2: Delete Based on User Cleanup Choice
```
[004] public/server.js 
      Risk: LOW (no imports found)
      If safe → DELETE
      Else → ARCHIVE
      
[005] studio/index.html
      Reason: Not used (index-simple used instead)
      Risk: MEDIUM (verify no direct links)
      
[006] Extension files (A1/A2 decision)
      If A1: DELETE /tradingview-analyzer/*
      If A2: DELETE /public/* (except dev-helper.js)
```

### Tier 3: Move Based on Cleanup Aggressiveness
```
Option 1 (Conservative):
  - Keep all test files
  - Keep all HTML
  - Only delete: old studio files + backup
  
Option 2 (Moderate - RECOMMENDED):
  - Delete: old studio files + backup + !chosen extension
  - Move to /backup/pending/: test HTML (test-analysis, test-chart)
  - Keep: tests/ folder (for Phase 1 dev)
  
Option 3 (Aggressive):
  - Delete all OLD/DUPLICATE files
  - Move: All test files except critical ones
  - Move: Old documentation
```

---

## 📂 BACKUP STRUCTURE ORGANIZATION

```
/backup/
│
├─ /2026-04-03_073752_pre_phase1_audit/ (pre-cleanup snapshot)
│  ├─ server.js (backup of original)
│  ├─ /src/, /lib/, /store/ (full copies)
│  └─ [All current state before cleanup]
│
├─ /analyzed/ 
│  └─ [Files analyzed but not changed]
│
├─ /organized/
│  └─ [Files moved due to cleanup]
│
├─ /in_progress/
│  └─ [Files being processed now]
│
├─ /pending/
│  └─ [Slated for deletion/archival]
│  ├─ studio/index_old.html
│  ├─ studio/studioindex.html
│  ├─ test-analysis.html (if Option 2/3)
│  ├─ public/server.js
│  └─ [Other non-chosen files]
│
└─ /fixed/
   └─ [Files fixed during cleanup]
```

---

## 🚀 PROPOSED FINAL STRUCTURE

### After Cleanup (Option 2 - Recommended):

```
trading-auto/  (CLEAN & ORGANIZED)
│
├─ 🔑 CORE SYSTEM
│  ├─ server.js (2850+ lines, main)
│  ├─ package.json
│  ├─ mt5_data.json
│  ├─ index.html (main menu)
│  │
│  ├─ /lib/
│  │  ├─ candle-manager.js ✅ NEW
│  │  ├─ symbol-normalizer.js
│  │  └─ [other utilities]
│  │
│  ├─ /src/
│  │  ├─ /agents/ (23+ agents - ALL KEPT)
│  │  └─ /services/ (symbol-preferences, etc.)
│  │
│  ├─ /store/
│  │  └─ market-store.js
│  │
│  ├─ /analysis/
│  │  └─ analyzer.js
│  │
│  └─ /trading/
│     └─ broker-adapter.js
│
├─ 🎨 UI PORTALS
│  ├─ index.html (links portal)
│  ├─ /studio/
│  │  ├─ index-simple.html ✅ USED
│  │  ├─ studioapp-simple.js
│  │  ├─ studioindex.html (DELETED)
│  │  ├─ index.html (DELETED)
│  │  └─ index_old.html (DELETED)
│  │
│  ├─ dashboard.html
│  ├─ popup.html
│  ├─ agent-log-page.html
│  ├─ AGENTS_MONITOR.html
│  ├─ audit-dashboard.html
│  └─ EXTENSION_TEST.html
│
├─ 📦 EXTENSION (A1 - kept)
│  └─ /public/
│     ├─ popup.html (or main /popup.html)
│     ├─ background.js
│     ├─ content.js
│     ├─ manifest.json
│     └─ dev-helper.js
│  
│  ❌ /tradingview-analyzer/ (DELETED completely)
│
├─ 📋 TESTS
│  ├─ /tests/
│  │  └─ integration/ (kept for Phase 1)
│  └─ test-analysis.html (moved to /backup/pending/)
│  └─ test-chart-visual.html (moved to /backup/pending/)
│
├─ 📚 DOCS
│  ├─ README.md
│  ├─ ARCHITECTURE.md
│  ├─ SYSTEM_MAP.md ✅ NEW
│  ├─ PENDING_TASKS.md ✅ NEW
│  ├─ PROGRESS_LOG.md ✅ NEW
│  ├─ FILES_ORGANIZATION.md ✅ THIS FILE
│  └─ [other docs]
│
├─ 🗄️ CONFIG
│  ├─ PORT_CONFIG.js
│  ├─ SAFE_MODE_CONFIG.json
│  └─ [batch files]
│
└─ 💾 BACKUP
   ├─ /2026-04-03_073752_pre_phase1_audit/ (snapshot)
   ├─ /analyzed/ (reference copies)
   ├─ /pending/ (deleted files - recoverable)
   │  ├─ studio/index_old.html
   │  ├─ studio/studioindex.html
   │  ├─ tradingview-analyzer_backup_20260402/
   │  ├─ public/server.js
   │  ├─ tradingview-analyzer/ (if A1 chosen)
   │  └─ test-analysis.html
   └─ /fixed/ (any auto-fixes applied)
```

---

## 📊 SIZE ESTIMATES

### Current Size
```
Total project: ~150-200 MB (with node_modules)
Main code: ~30-40 MB (without node_modules)
Deletable: ~15-20 MB (old files + backup)
```

### After Cleanup (Option 2)
```
Remaining: ~25-30 MB
Archived: ~15-20 MB in /backup/pending/
Reduction: ~20% smaller
```

---

## ✅ VERIFICATION CHECKLIST (Post-Cleanup)

After cleanup, verify:

```
[ ] server.js still starts without errors
[ ] All 70+ endpoints resolve correctly
[ ] /studio endpoint works (index-simple.html loads)
[ ] /dashboard loads without issues
[ ] /popup loads extension UI
[ ] agent-log-page.html hub loads
[ ] All imports still resolve (no broken requires)
[ ] Extension (chosen version) loads correctly
[ ] mt5_data.json is being written
[ ] No 404 errors in logs
[ ] All agents are callable (orchestrator.run works)
```

---

## 🎯 NEXT STEPS

1. **User Decisions** (Task 025-029)
   - Extension choice: A1 or A2
   - Cleanup level: Option 1, 2, or 3
   
2. **Execute Cleanup** (Task 030)
   - Delete auto files
   - Archive user-decided files
   - Verify no broken imports
   
3. **Run Phase 1 Tests** (Task 031)
   - Confirm system still works
   - All unit tests pass

---

Generated: 2026-04-03 08:25  
Status: COMPREHENSIVE ORGANIZATION PLAN READY
