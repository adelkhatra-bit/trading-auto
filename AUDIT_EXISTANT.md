# AUDIT COMPLET DE L'ARCHITECTURE EXISTANTE

**Date:** 3 avril 2026  
**Objectif:** Valider ce qui existe vs ce qui manque, avant tout nouveau fichier

---

## A. CE QUI EXISTE DÉJÀ ET OÙ

### HTML Files (6 interfaces)
```
✅ index.html
   Role: Menu principal
   Scripts: Aucun JS spécifique
   Liens: Vers /studio, /audit, /agents-monitor

✅ AGENTS_MONITOR.html  
   Role: Affiche statut agents en temps réel
   Structure: Cards avec status icons
   Scripts: Inline JavaScript statique pour polling
   Manque: 6 onglets, auto-refresh, filtrage

✅ audit-dashboard.html
   Role: Dashboard audit avec 7 tabs
   Structure: Onglets (Files, Agents, Endpoints, Connections, Errors, Tasks)
   Scripts: Inline JavaScript
   État: Basique, connexion au GET /audit/state

✅ studio/index-simple.html
   Role: Interface trading principale
   Structure: Sidebar (buttons) | Center (chart + analysis) | Right (log)
   Scripts: Appelle studio/studioapp.js
   Fonctionnalités: Chart, symbol selector, timeframes, instant-trade buttons

✅ public/popup.html (Extension)
   Role: Popup extension
   Scripts: Inline
   État: Basique

✅ studio/index.html / studio/studioindex.html
   Role: Versions alternatives (possiblement anciennes)
   État: À vérifier si utilisé
```

### JavaScript Modules

#### Server Core (server.js — 2800+ lignes)
```
✅ Port 4000
✅ CORS middleware
✅ Logging system (pushLog, sysLogs array)
✅ Routes HTML (/,  /audit, /studio, /agents-monitor)
✅ Routes API: 50+ endpoints
   - MT5 integration (/mt5/*, /mt5-data.json)
   - Historical data (/klines, /quote, /news, /calendar)
   - TV-bridge (/tv-bridge)
   - SSE /stream (broadcast MT5 + analysis real-time)
   - Audit routes (/audit/state, /events, /log, /task/*)
   - System routes (/state, /instant-trade-live, /agents-report, /system-log)

✅ audit-logger.js integration (EXIST DÉJÀ)
   Route: GET /audit/state → auditLogger.getState()
   Route: GET /audit/events → auditLogger.getRecentEvents()
   Route: POST /audit/log → auditLogger.logEvent()
   Route: POST /audit/task/:id → auditLogger.updateTask()

✅ marketStore (in-memory cache)
   - bySymbol{} → latest MT5 payload
   - analysisCache{} → latest analysis
   - sseClients[] → SSE connections
   - broadcast() method
   - addSSEClient() method

✅ orchestrator.run() calling (Promise.all 4 agents)
   Line ~818-825:
   orchestrator.run({symbol, broker_symbol, price, timeframe...})
     .then(analysis => marketStore.updateAnalysis(canonical, analysis))
     .catch(e => {})
```

#### Agents (src/agents/ — 24 files)
```
✅ ACTIVE in orchestrator:
   - orchestrator.js
   - trading-core.js
   - timeframe-consensus.js (tfConsensus)
   - fear-index.js (fearIndex)
   - news-intelligence.js (newsIntelligence)

✅ AVAILABLE but not called:
   - technicalAgent.js
   - macroAgent.js
   - newsAgent.js
   - riskManager.js
   - tradeValidator.js
   - continuous-loop.js (DISABLED — CPU spike)
   - coordinator.js
   - designerAgent.js
   - strategyManager.js
   - supervisor.js
   - syncManager.js
   - And 9 more...

❌ MISSING:
   - indicatorAgent.js (CRÉER)
   - surveillanceAgent.js (CRÉER, remplace continuous-loop)
```

#### Store (store/market-store.js)
```
✅ Singleton managing:
   - Real-time MT5 data
   - Analysis cache
   - SSE client management
   - Broadcast mechanism
```

#### Audit System (audit-logger.js — 280 lignes)
```
✅ EXIST DÉJÀ avec:
   - readAudit() / writeAudit()
   - logEvent(category, action, details)
   - updateTask(), completeTask(), failTask()
   - addError(), resolveError()
   - updateEndpoint(), updateConnection()
   - markFileModified()
   - subscribe() — notification system
   - getState() — full audit state
   - getRecentEvents(limit)

✅ Lecture/Écriture: audit.json (structure JSON)
```

#### Extension (public/)
```
✅ manifest.json (Chrome extension v3)
✅ background.js (Service worker)
   - autoLoop() DISABLED
   - showSignal() with alert() popup
   - onMessage listener

✅ popup.html + related

❌ MISSING:
   - Alert subscription mechanism (SSE)
   - Notification system (chrome.notifications)
   - Symbol filtering
```

---

## B. CE QU'ON PEUT COMPLÉTER SANS CRÉER (Réutilisation)

### 1. Audit System — Extension Localisation
**Situation:** audit-logger.js logEvent() existe mais sans file/line/function  
**À faire:** Enrichir logEvent() pour capturer stack trace  
**Où:** audit-logger.js ligne ~20-40

```javascript
// AJOUTER:
const getCallerLocation = () => {
  const stack = new Error().stack.split('\n')[2];
  const match = stack.match(/at\s+(.+?)\s+\((.+):(\d+):(\d+)/);
  if (match) {
    return {
      function: match[1],
      file: match[2].replace(process.cwd() + '/', ''),
      line: parseInt(match[3])
    };
  }
  return {function: 'unknown', file: 'unknown', line: 0};
};

// MODIFIER logEvent():
logEvent(category, action, details = {}) {
  const event = {
    id: `evt-${Date.now()}-...`,
    timestamp: new Date().toISOString(),
    category, action, details,
    severity: details.severity || 'info',
    location: getCallerLocation()  // ← NOUVEAU
  };
  // ...
}
```

### 2. AGENTS_MONITOR.html — Upgrade Dashboard
**Situation:** Existe mais très basique (3 cards statiques)  
**À faire:** Ajouter 6 onglets + auto-refresh + data binding  
**Où:** AGENTS_MONITOR.html (350 lignes actuelles → 600 lignes)

**Nouveau contenu:**
```
Onglet 1: AGENTS (statut en direct)
Onglet 2: PIPELINE (flux agents)
Onglet 3: SIGNAUX (décisions historique)
Onglet 4: ALERTES (notifications)
Onglet 5: INDICATEURS (créés par indicatorAgent)
Onglet 6: AUDIT (historique enrichi)
```

### 3. studio/index-simple.html — Ajouter Préférences
**Situation:** Existe avec symbol selector, timeframes, mode toggles  
**À faire:** Ajouter section "Mes Préférences" dans le sidebar  
**Où:** studio/index-simple.html (ajouter section après buttons)

```html
<!-- Ajouter après .panel .buttons section:-->
<h3>Mes Préférences</h3>
<div id="preferences">
  <label>Symboles Surveillés:</label>
  <input type="checkbox" value="XAUUSD" id="sym-xauusd"> XAUUSD
  <input type="checkbox" value="EURUSD" id="sym-eurusd"> EURUSD
  <!-- Etc -->
  <button onclick="savePreferences()">Sauvegarder</button>
</div>
```

### 4. public/background.js — Ajouter SSE Alerts
**Situation:** Existe avec basic autoLoop DISABLED  
**À faire:** Ajouter subscribeToAlerts() SSE listener  
**Où:** public/background.js (ajouter après autoLoop function)

```javascript
// AJOUTER:
async function subscribeToAlerts() {
  const filters = JSON.parse(localStorage.getItem('alertFilters') || '{}');
  const eventSource = new EventSource('/alerts/subscribe?...');
  
  eventSource.addEventListener('message', (e) => {
    const alert = JSON.parse(e.data);
    // Filtrer, notifier, etc.
  });
}

// Lancer au démarrage:
subscribeToAlerts();
```

### 5. server.js — Routes Alertes + Surveillance
**Situation:** Existe 50+ routes, audit routes OK  
**À faire:** Ajouter routes pour alerts + surveillance monitoring  
**Où:** server.js (ajouter après audit routes section, ~ligne 500)

**Nouvelles routes:**
```javascript
// POST /alerts/subscribe (SSE)
// GET /alerts (historique)
// POST /surveillance/monitor (ajouter symbole)
// GET /surveillance/status
```

---

## C. CE QUI MANQUE RÉELLEMENT (Créer)

### 1. agent-bus.js (Module Queue Messages)
**Pourquoi:** Registre + communication inter-agents  
**Où:** Racine du projet (next to server.js)  
**Taille:** ~100 lignes  
**Responsabilités:**
  - registerAgent(name, metadata)
  - sendMessage(from, to, message)
  - subscribe(agentName, callback)
  - getMessages(), getAllAgents()

### 2. src/agents/surveillance-agent.js (Remplace continuous-loop)
**Pourquoi:** Mode continu event-driven sans CPU spike  
**Où:** dossier agents  
**Taille:** ~50 lignes  
**Responsabilités:**
  - onMT5Update(symbol, newPayload) → déclenche si prix change >0.5% OU 30s+
  - addMonitored(symbol), removeMonitored(symbol)
  - emit('trigger-analysis') events

### 3. alert-manager.js (Centralise alertes filtrées)
**Pourquoi:** Filtrage par symboles + severity  
**Où:** Racine du projet  
**Taille:** ~120 lignes  
**Responsabilités:**
  - createAlert(source, data)
  - shouldNotify(alert, userFilters)
  - addSubscriber(res, filters) — SSE endpoint
  - getAlerts(symbol, type, limit)

### 4. src/agents/indicator-agent.js (NOUVEAU agent créateur)
**Pourquoi:** Génère indicateurs MT5 adaptés au marché  
**Où:** dossier agents  
**Taille:** ~200 lignes  
**Responsabilités:**
  - generateIndicators(symbol, timeframe, marketCondition)
  - Produit {indicators[], aggregateSignal, mql5Code}
  - Intégration en Promise.all orchestrator

---

## D. FICHIERS À MODIFIER (Changements chirurgicaux)

### 1. server.js (Intégration 4 modules)
**Ajouts:**
- Ligne ~47: Require agent-bus, alert-manager, surveillance-agent
- Ligne ~55: Register agents via agentBus
- Ligne ~65: Créer instance surveillance-agent + event listener
- Ligne ~820: Log orchestrator result dans agentBus + alert si signal
- Ligne ~500 (nouvelle section): Routes /alerts/subscribe, /alerts, /surveillance/*

**Ce qui ne change PAS:**
- orchestrator.run() signature (juste ajouter indicatorAgent en Promise.all)
- All existing routes
- Market store logic

### 2. audit-logger.js (Enrichissement localisation)
**Ajout:**
- getCallerLocation() helper function
- Enrichir logEvent() avec location field

**Ce qui ne change PAS:**
- Signature existante
- Tous les autres methods

### 3. AGENTS_MONITOR.html (Upgrade 6 onglets)
**Ajout:**
- 6 onglets structure
- Auto-refresh 2s (fetch /agents-bus, /instant-trade-live, /alerts, /audit/query)
- Data binding scripts

**Ce qui ne change PAS:**
- Layout général
- Existing styles (ajouter CSS seulement)

### 4. studio/index-simple.html (Ajouter prefs)
**Ajout:**
- Section "Mes Préférences" dans sidebar
- Checkboxes symboles, timeframe select, risk level select
- Button sauvegarder → localStorage

**Ce qui ne change PAS:**
- Chart panel
- Central analysis
- Existing buttons

### 5. public/background.js (Ajouter alertes)
**Ajout:**
- subscribeToAlerts() function
- EventSource listener
- chrome.notifications.create() handler

**Ce qui ne change PAS:**
- showSignal() function
- manifest.json
- Base message listeners

### 6. orchestrator.js (Intégrer indicatorAgent)
**Ajout:**
- Ajouter indicatorAgent.generateIndicators() au Promise.all ligne 40
- Fusionner résultat en result.agents.indicatorAgent

**Ce qui ne change PAS:**
- Logique fusion agents existants
- Signature run()

---

## RÉSUMÉ CHIFFRÉ

| Type | Existe | Partiellement | Manque | Total |
|------|--------|-------------|--------|-------|
| HTML | 6 | 0 | 0 | 6 |
| Modules agents | 5 active + 14 available | 0 | 2 (indicator + surveillance) | 21 |
| API routes | 50+ | 0 | 4 (alerts + surveillance) | 54 |
| Audit system | ✅ audit-logger.js | localisation missing | 0 | ✅ |
| Alerting | ❌ | ❌ | ✅ alert-manager | ✅ |
| Agent Bus | ❌ (concept only) | ❌ | ✅ agent-bus.js | ✅ |
| Surveillance | ❌ (continuous-loop disabled) | ❌ | ✅ surveillance-agent.js | ✅ |
| Indicator creation | ❌ | ❌ | ✅ indicator-agent.js | ✅ |

---

## FILIÈRE DE CRÉATION

**À créer (3 fichiers VRAIS):**
1. agent-bus.js
2. src/agents/surveillance-agent.js
3. alert-manager.js
4. src/agents/indicator-agent.js

**À compléter (1 module, 4 HTML):**
1. audit-logger.js (+ getCallerLocation)
2. AGENTS_MONITOR.html (+ 6 onglets)
3. studio/index-simple.html (+ prefs)
4. public/background.js (+ SSE)
5. orchestrator.js (+ indicatorAgent)

**À modifier légèrement (1):**
1. server.js (+ requires, routes, broadcasts)

---

**VALIDATION AVANT PLAN FINAL:**

✅ audit-logger.js peut être enrichie (pas besoin nouvelle classe)  
✅ AGENTS_MONITOR.html peut être upgradée (pas besoin nouveau HTML)  
✅ studio/index-simple.html peut recevoir section prefs  
✅ public/background.js peut avoir SSE listener  
✅ orchestrator.js peut intégrer indicatorAgent en Promise.all  

❌ agent-bus.js DOIT être créé (aucune équivalent)  
❌ surveillance-agent.js DOIT être créé (remplace continuous-loop disabled)  
❌ alert-manager.js DOIT être créé (aucune équivalent)  
❌ indicator-agent.js DOIT être créé (core new feature)

