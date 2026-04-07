# DECISION_FORM.md - 2 Choix à Faire

**For User:** Choose NOW and say "GO"  
**Time Estimate:** 2 minutes to decide, 50 minutes total to execute + test

---

## CHOICE 1: EXTENSION UI VERSION

Which version of the extension should remain?

### Option A1: Keep /public/ ✅ RECOMMENDED
```
Keep:
  ├── /public/popup.html
  ├── /public/popup.js
  ├── /public/manifest.json (v1.0)
  ├── /public/background.js
  ├── /public/content.js
  └── /public/dev-helper.js

Archive:
  └── /tradingview-analyzer/{popup, manifest, background, content files}

Benefit: 
  - Lighter weight
  - Standard web structure  
  - Simpler to maintain

Tradeoff:
  - Lose advanced features from v2 (chart-module, ai-debugger, etc.)
```

### Option A2: Keep /tradingview-analyzer/
```
Keep:
  ├── /tradingview-analyzer/popup.html
  ├── /tradingview-analyzer/popup.js
  ├── /tradingview-analyzer/manifest.json (v2.0)
  ├── /tradingview-analyzer/background.js
  ├── /tradingview-analyzer/content.js
  ├── /tradingview-analyzer/chart-module.js
  ├── /tradingview-analyzer/ai-debugger.js
  ├── /tradingview-analyzer/news-engine.js
  └── [+ 6 more feature modules]

Archive:
  └── /public/{popup, manifest, background, content files}

Benefit:
  - More features
  - Comprehensive extension

Tradeoff:
  - Heavier (more code)
  - Non-standard structure
```

---

## CHOICE 2: CLEANUP AGGRESSIVENESS

How thorough should the cleanup be?

### Option 1: CONSERVATIVE
```
Delete only obviously obsolete files:
  ✅ /public/server.js (legacy, not imported)
  ✅ /studio/index_old.html (marked old)
  ✅ /studio/studioapp-old.js (marked old)
  ✅ /studio/studioindex.html (duplicate name)
  ✅ /tradingview-analyzer_backup_20260402/ (stale backup)

Keep:
  ✅ ALL agents unchanged
  ✅ ALL studio versions (both index.html + index-simple.html)
  ✅ ALL lib modules
  ✅ All data files

Time: 5-10 minutes  
Risk: ZERO (only delete marked-old files)
```

### Option 2: MODERATE ✅ RECOMMENDED
```
Delete:
  ✅ /public/server.js
  ✅ /studio/index_old.html
  ✅ /studio/studioapp-old.js
  ✅ /studio/studioindex.html
  ✅ /tradingview-analyzer_backup_20260402/

Consolidate Studio:
  ✅ KEEP: index.html + index-simple.html
  ✅ KEEP: studioapp.js + studioapp-simple.js
  ✅ DELETE: studiostyles.css (if duplicate) or keep both CSS files
  ✅ CLEAN: Remove dead code, old imports

Choose Extension:
  ✅ Keep A1 or A2 (your choice)
  ✅ Archive the other version

Keep:
  ✅ ALL agents (verified actively used)
  ✅ ALL core lib modules
  ✅ ALL services

Time: 20-30 minutes  
Risk: LOW (only deletes obviously unused, all verified)
```

### Option 3: AGGRESSIVE
```
Everything from Option 2, PLUS:
  ⚠️ Deep investigation of root-level orphaned files:
    - agent.js (purpose unclear)
    - agent-worker.js (purpose unclear)
    - agent-bus.js (purpose unclear)
    - access.js (purpose unclear)
  
  ⚠️ Document their purpose OR delete if unused
  ⚠️ Consolidate duplicate data files if needed
  ⚠️ Clean up any dead imports throughout codebase

Time: 1 hour total  
Risk: MEDIUM (depends on findings of orphaned files)
```

---

## 📋 MY RECOMMENDATION

**Extension:** ✅ **A1** (lighter, more standard)  
**Cleanup:** ✅ **Option 2** (good balance of clean + safe)

**Why:**
- A1: Simpler foundation for Phase 1-4 development
- Option 2: Removes obvious junk, keeps all active code, minimal risk

---

## 🚀 WHAT HAPPENS AFTER YOU DECIDE

**Step 1:** You reply with your choices (A1 or A2, Option 1/2/3)

**Step 2:** Agent executes (automatically):
```
a) Archive marked files to /backup/archive_2026-04-03/
b) Delete obsolete files
c) Verify no broken imports (5 verification checks)
d) Validate project structure
e) Generate cleanup completion report
```

**Step 3:** Run Phase 1 Tests (automatically):
```
a) Execute candle-manager.test.js
b) Run 10 unit tests
c) Report each test result
d) Ask for Phase 2 approval
```

**Step 4:** You get report with:
- ✅ Cleanup complete status
- ✅ Tests pass/fail results
- ✅ Project structure validation
- ⏳ Ready for Phase 2 (indicator-engine)

---

## ✅ DECISION FORM (COPY & PASTE YOUR ANSWER)

```
EXTENSION: A1 [ ] or A2 [ ]
CLEANUP: Option 1 [ ] or Option 2 [ ] or Option 3 [ ]
READY: GO [ ]
```

---

## ⏱️ TIMELINE FROM "GO"

| Step | Time | What |
|------|------|------|
| User says "GO" | 0 min | Decision made |
| Archive & Delete | 15 min | Files moved to backup |
| Verify imports | 10 min | Check all dependencies |
| Phase 1 Tests | 30 min | Run 10 candle-manager tests |
| Report | 5 min | Results + next steps |
| **TOTAL** | **~1 hour** | **Ready for Phase 2** |

---

## 🎯 BOTTOM LINE

**Right now:**
1. Choose Extension: A1 or A2
2. Choose Cleanup: 1, 2, or 3
3. Say "GO"

**In 1 hour:**
- Clean project structure
- Phase 1 tests pass/fail report
- Ready to begin Phase 2 (6-8 hour development)

---

**Ready? Reply with your 2 choices and GO! 👇**
