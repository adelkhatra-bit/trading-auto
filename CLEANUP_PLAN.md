# CLEANUP PLAN - VALIDATION REQUISE VIA USER

**Status:** ⏳ AWAITING VALIDATION - NO FILES MODIFIED YET  
**Created:** 2026-04-03  
**Backup Location:** `/backup/2026-04-03_073752_pre_phase1_audit` ✅ READY TO RESTORE

---

## OVERVIEW

Basé sur l'audit complet, j'ai identifié **3 domaines de duplication**:
1. **Extension UI** (2 versions complètes)
2. **Server** (2 entrées différentes)
3. **Studio UI** (4 fichiers pour 1 app)

Plus des fichiers orphelins qui nécessitent une classification.

---

## 🔍 ANALYSE DÉTAILLÉE

### ❌ EXTENSION UI - DUPLICATION (2 versions)

| Localisation | Version | Manifest | Purpose |
|--------------|---------|----------|---------|
| `/public/` | v1.0 | "Trading Auto" | Simple, légère |
| `/tradingview-analyzer/` | v2.0 | "Trading Auto Analyzer" | Plus complète, "détecte symbole/TF/prix" |

**Fichiers dupliqués:**
- `popup.html` (✅ /public vs ✅ /tradingview-analyzer)
- `popup.js` (✅ /public vs ✅ /tradingview-analyzer)
- `manifest.json` (v1.0 /public vs v2.0 /tradingview-analyzer)
- `background.js` (✅ /public vs ✅ /tradingview-analyzer)
- `content.js` (✅ /public vs ✅ /tradingview-analyzer)

**Différences substantielles?**
- `/tradingview-analyzer/` a des fichiers supplémentaires (chart-module.js, ai-debugger.js, news-engine.js, etc.)
- `/public/` est plus simple et légère
- `/tradingview-analyzer/` semble être une version "complète/étendue"

---

### ❌ SERVER - 2 PORTS DIFFÉRENTS

| Localisation | Version | Port | Purpose | Statut |
|--------------|---------|------|---------|--------|
| `/server.js` (root) | FULL | 4000 | Backend complet Trading Auto | 🟢 ACTIF |
| `/public/server.js` | LIGHT | 3000 | Serveur d'images léger | 🟡 ANCIEN/SUPPORT? |

**Analyse:**
- `/server.js` (root) : 400+ lignes, logique complexe, routes multiples
- `/public/server.js` : 40-50 lignes, juste image serving + status
- **Verdict:** `/server.js` root = production, `/public/server.js` = legacy

---

### ❌ STUDIO UI - MULTIPLE VERSIONS

| Fichier | Version | Statut | Purpose |
|---------|---------|--------|---------|
| `index.html` | CURRENT? | ❓ Active? |Principal UI? |
| `index-simple.html` | SIMPLE | ❓ Fallback? | Simplified/dev version? |
| `index_old.html` | OLD | 🔴 Stale | Definitely old |
| `studioindex.html` | ??? | ❓ Unclear | Duplicate? |
| `studioapp.js` | CURRENT? | ❓ Active? | Main app logic? |
| `studioapp-simple.js` | SIMPLE | ❓ Fallback? | Dev/test version? |
| `studioapp-old.js` | OLD | 🔴 Stale | Definitely old |

---

### ⚠️ SYMBOL MAPPING - 4 FICHIERS (UNIQUE, PAS DE DOUBLON)

| Fichier | Localisation | Purpose | Tier | Duplication? |
|---------|--------------|---------|------|--------------|
| symbol-normalizer.js | `/lib/` | Profiles & canonical patterns | **CORE** | 🟢 UNIQUE |
| symbol-matcher.js | `/lib/` | Map TradingView → sources | **CORE** | 🟢 UNIQUE |
| symbol-mapper.js | `/tradingview-analyzer/` | Client-side mapping (extension) | EXT | 🟡 Complément de matcher.js |
| symbol-manager.js | `/tradingview-analyzer/` | Extension symbol state | EXT | 🟡 Complémentaire (pas doublon) |

**Verdict:** ✅ PAS DE DOUBLON, chaque fichier a une utilité spécifique.
- `/lib/` = backend core
- `/tradingview-analyzer/` = extension frontend

---

### 🔴 AGENTS - POTENTIELLE DUPLICATION (23 TOTAL)

| Paire Suspecte | /src/agents/ | Similarity Level | Verdict |
|---|---|---|---|
| orchestrator.js | YES | High (both orchestration) | ❓ À vérifier |
| coordinator.js | YES | High (both coordination) | ❓ À vérifier |
| trading-core.js | YES | High (both core logic) | ❓ À vérifier |
| trade-logic.js | YES | High | ❓ À vérifier |
| newsAgent.js | YES | Medium | ❓ À vérifier |
| news-intelligence.js | YES | Maybe duplicate? | ❓ À vérifier |
| dataSourceManager.js | YES | vs /lib/data-source-manager.js? | ❓ Possible |

**Je ne peux pas affirmer sans lire les fichiers. Besoin de vérification.**

---

### 🟡 FICHIERS ORPHELINS (ROOT LEVEL)

| Fichier | Purpose | Statut | Action |
|---------|---------|--------|--------|
| agent.js | ??? | ❓ Unclear | DOCUMENT or DELETE |
| agent-worker.js | ??? | ❓ Unclear | DOCUMENT or DELETE |
| agent-bus.js | ??? Message bus? | ❓ Unclear | DOCUMENT or DELETE |
| access.js | ??? Access control? | ❓ Unclear | DOCUMENT or DELETE |
| AGENT_BUS.json | Config? State? | ❓ Unclear | DOCUMENT or DELETE |
| mt5_bridge_simple.js | MT5 interface | ✅ USEFUL | KEEP |
| audit-logger.js | Audit logging | ✅ USEFUL | KEEP |
| PORT_CONFIG.js | Port configuration | ✅ USEFUL | KEEP |
| SYSTEM_LOG.json | Log data | ✅ DATA | KEEP |
| audit.json | Audit data | ✅ DATA | KEEP |

---

## 📋 CLEANUP PLAN - PROPOSITION DÉTAILLÉE

### **PLAN A: EXTENSION UI** (Choose one)

#### Option A1: Keep `/public/` (RECOMMANDÉ)
```
KEEP:
  ├── /public/popup.html
  ├── /public/popup.js
  ├── /public/manifest.json (v1.0)
  ├── /public/background.js
  ├── /public/content.js
  └── /public/dev-helper.js

ARCHIVE to /backup/:
  ├── /tradingview-analyzer/popup.html
  ├── /tradingview-analyzer/popup.js
  ├── /tradingview-analyzer/manifest.json
  ├── /tradingview-analyzer/background.js
  ├── /tradingview-analyzer/content.js

RATIONALE: /public/ follows standard structure, lighter weight
```

#### Option A2: Keep `/tradingview-analyzer/` (ALTERNATIVE)
```
KEEP:
  ├── /tradingview-analyzer/popup.html
  ├── /tradingview-analyzer/popup.js
  ├── /tradingview-analyzer/manifest.json
  ├── /tradingview-analyzer/background.js
  ├── /tradingview-analyzer/content.js
  └── [all other extension-specific files]

ARCHIVE to /backup/:
  ├── /public/popup.html
  ├── /public/popup.js
  ├── /public/manifest.json
  ├── /public/background.js
  ├── /public/content.js

RATIONALE: Has additional modules (chart, AI-debugger, etc.)
```

---

### **PLAN B: SERVER** (Only one choice)

```
KEEP:
  └── /server.js (root)  ← MAIN BACKEND PORT 4000

MOVE to /backup/nonfunctional/:
  └── /public/server.js  ← LEGACY PORT 3000 (for reference if needed)

RATIONALE: 
- /server.js is comprehensive (400+ lines, full Trading Auto backend)
- /public/server.js is lightweight legacy image server
- Only one should be active to avoid port conflicts
```

---

### **PLAN C: STUDIO UI** (Choose one)

#### Option C1: Keep `index.html` + `index-simple.html` (RECOMMENDED)
```
KEEP:
  ├── /studio/index.html           ← Production/main version
  ├── /studio/index-simple.html    ← Dev/fallback version
  ├── /studio/studioapp.js         ← Main app logic
  ├── /studio/studioapp-simple.js  ← Dev/fallback logic
  ├── /studio/app.js               ← If different from studioapp.js
  ├── /studio/styles.css
  └── /studio/studiostyles.css

DELETE:
  ├── /studio/index_old.html       ← STALE (clearly old)
  ├── /studio/studioindex.html     ← DUPLICATE NAME (redundant)
  ├── /studio/studioapp-old.js     ← STALE (clearly old)

RATIONALE:
- index.html = production
- index-simple.html = dev/fallback (useful to keep)
- *_old.* and studioindex.html = obvious duplicates/stale
```

#### Option C2: Keep ONLY `index.html` (AGGRESSIVE)
```
KEEP:
  ├── /studio/index.html
  ├── /studio/studioapp.js
  └── /studio/styles.css

DELETE:
  ├── /studio/index-simple.html   ← Not needed if aggressive
  ├── /studio/index_old.html
  ├── /studio/studioindex.html
  ├── /studio/studioapp-simple.js
  ├── /studio/studioapp-old.js
  ├── /studio/app.js              ← If redundant vs studioapp.js
  └── /studio/studiostyles.css    ← If redundant vs styles.css

RATIONALE: Single source of truth, minimal maintenance
```

---

### **PLAN D: SYMBOL MAPPING** (No cleanup needed)

```
✅ NO DUPLICATES FOUND

KEEP ALL:
  ├── /lib/symbol-normalizer.js   ← Backend canonical profiles
  ├── /lib/symbol-matcher.js      ← Backend mapping logic
  ├── /tradingview-analyzer/symbol-mapper.js    ← Extension mapping
  └── /tradingview-analyzer/symbol-manager.js   ← Extension state

EACH SERVES DIFFERENT PURPOSE - NO CONSOLIDATION NEEDED
```

---

### **PLAN E: AGENTS** (REQUIRES VERIFICATION)

**Cannot recommend without reading files. Need to:**

1. Read `/src/agents/orchestrator.js` vs `coordinator.js`
2. Read `/src/agents/trading-core.js` vs `trade-logic.js`
3. Read `/src/agents/newsAgent.js` vs `news-intelligence.js`
4. Check if `/src/agents/dataSourceManager.js` duplicates `/lib/data-source-manager.js`

**Temporary recommendation:**
```
HOLD FOR NOW:
  └── Do not modify agents until analysis complete

TO DECIDE:
  1. Are orchestrator.js & coordinator.js duplicates? (likely yes)
  2. Are trading-core.js & trade-logic.js duplicates? (likely yes)
  3. Are newsAgent.js & news-intelligence.js duplicates? (possible)
  4. Is /src/agents/dataSourceManager.js needed vs /lib/data-source-manager.js? (verify)
```

---

### **PLAN F: ORPHANED ROOT FILES** (REQUIRES DECISION)

```
⏳ NEED YOUR INPUT:

agent.js              - Purpose unclear (KEEP or DELETE?)
agent-worker.js       - Worker pattern? (KEEP or DELETE?)
agent-bus.js          - Message bus? (KEEP or DELETE?)
access.js             - Access control? (KEEP or DELETE?)
AGENT_BUS.json        - Config/state? (KEEP or DELETE?)

✅ DEFINITELY KEEP:
mt5_bridge_simple.js  - MT5 communication (important)
audit-logger.js       - Audit logging (useful)
PORT_CONFIG.js        - Port config (useful)
SYSTEM_LOG.json       - Log data (data)
audit.json            - Audit data (data)
```

---

### **PLAN G: STALE BACKUP FOLDER** (Delete)

```
DELETE:
  └── /tradingview-analyzer_backup_20260402/  ← Old snapshot from 2026-04-02

RATIONALE: We have fresh backup at /backup/2026-04-03_073752_pre_phase1_audit
           No need to keep old backup
```

---

## 📊 FINAL CONSOLIDATED CLEANUP

### OPTION 1: CONSERVATIVE (Keep more, delete less)
```
DELETE:
  ✅ /trading-view-analyzer_backup_20260402/  (stale backup)
  ✅ /studio/index_old.html                    (clearly old)
  ✅ /studio/studioindex.html                  (duplicate name)
  ✅ /studio/studioapp-old.js                  (clearly old)
  ✅ /public/server.js                         (legacy, keep /server.js)

ARCHIVE (keep as reference):
  ✅ /tradingview-analyzer/popup.html,js,manifest,background.js,content.js
     → Move to /backup/extension_v2_reference/

KEEP ALL AGENTS (at least for now)
KEEP ALL ORPHANED FILES (until purpose clarified)
CLEAN RESULT:
  - Single extension version (/public/)
  - Single server (root /server.js)
  - Clean studio UI (2 versions: main + simple)
  - All agents preserved
  - Orphaned files preserved
```

### OPTION 2: MODERATE (Recommended)
```
DELETE:
  ✅ /tradingview-analyzer_backup_20260402/
  ✅ /studio/index_old.html
  ✅ /studio/studioindex.html
  ✅ /studio/studioapp-old.js
  ✅ /studio/studiostyles.css              (consolidate to styles.css)
  ✅ /studio/index-simple.html             (if not needed)
  ✅ /studio/studioapp-simple.js           (if not needed)
  ✅ /public/server.js
  
ARCHIVE:
  ✅ /tradingview-analyzer extension files → /backup/extension_v2_archive/

AGENTS:
  ⏳ Awaiting analysis (verify duplicates then remove)

ORPHANED:
  ⏳ Awaiting clarification
```

### OPTION 3: AGGRESSIVE (Clean slate)
```
DELETE:
  ✅ Everything from Option 2
  ✅ /studio/index-simple.html + studioapp-simple.js
  ✅ /public/dev-helper.js                 (if unused)
  ✅ /studio/app.js                        (verify it's not needed)
  
DELETE DUPLICATED AGENTS:
  ✅ orchestrator.js OR coordinator.js     (keep one)
  ✅ trading-core.js OR trade-logic.js     (keep one)
  ✅ newsAgent.js OR news-intelligence.js  (keep one)

DELETE ORPHANED:
  ✅ agent.js, agent-worker.js, agent-bus.js, access.js
     (unless documented as needed)
```

---

## ✋ WHAT HAPPENS NEXT

### Step 1: YOU CHOOSE (multiple options allowed)

1. **Extension version:**
   - [ ] A1: Keep `/public/` (recommended)
   - [ ] A2: Keep `/tradingview-analyzer/` (alternative)

2. **Studio UI version:**
   - [ ] C1: Keep both `index.html` + `index-simple.html` (recommended)
   - [ ] C2: Keep only `index.html` (aggressive)

3. **Cleanup aggressiveness:**
   - [ ] Option 1: Conservative (delete only obviously stale)
   - [ ] Option 2: Moderate (recommended)
   - [ ] Option 3: Aggressive (clean slate)

4. **Agent consolidation:**
   - [ ] Let me verify orchestrator vs coordinator (I'll read and report)
   - [ ] Let me verify trading-core vs trade-logic (I'll read and report)
   - [ ] Let me verify news agents (I'll read and report)

5. **Orphaned files:**
   - [ ] DELETE all (agent.js, agent-worker.js, agent-bus.js, access.js)
   - [ ] KEEP all (might be needed)
   - [ ] Document them (I'll check git history or comments)

---

## 🚀 STEP 2: I EXECUTE (after validation)

Once you approve:

```bash
1. Archive selected files to /backup/cleanup_archive_YYYYMMDD/
2. Delete marked files (but ONLY marked ones)
3. Update imports if any references (grep for file paths)
4. Verify structure integrity
5. Report: "Cleanup complete, X files removed, Y files archived"
```

---

## ✅ VALIDATION TEMPLATE

```
USER RESPONSE TEMPLATE:

EXTENSION: [ ] A1  [ ] A2
STUDIO:    [ ] C1  [ ] C2
CLEANUP:   [ ] Opt1  [ ] Opt2  [ ] Opt3
AGENTS:    [ ] Verify all  [ ] Verify specific pairs
ORPHANED:  [ ] DELETE  [ ] KEEP  [ ] Document first

SPECIAL REQUESTS: (anything else?)
```

---

**Awaiting your selections. No files will be modified until you validate.** ✋
