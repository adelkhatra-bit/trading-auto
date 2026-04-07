# PLAN FINAL D'IMPLÉMENTATION — Architecture Multi-Agents Vivante

**Date:** 3 avril 2026  
**Statut:** PRÊT POUR IMPLÉMENTATION  
**Approche:** Analyse → Respecter l'existant → Ajouter sans casser

---

## 🔍 ANALYSE: CE QUI EXISTE vs CE QUI MANQUE

### ✅ CE QUI EXISTE DÉJÀ (Ne pas Toucher)

| Élément | Où | Statut | Critique |
|---------|-----|--------|----------|
| **Orchestrator** | src/agents/orchestrator.js | Fonctionne parfaitement | ✅ CORE |
| **4 Agents en parallèle** | tradingCore, tfConsensus, fearIndex, newsIntelligence | Stable | ✅ CORE |
| **SSE /stream** | server.js:1029 | Broadcast MT5 + analysis temps réel | ✅ CORE |
| **Logging pushLog()** | server.js:1557 | 500 entries, sysLogs[] | ✅ CORE |
| **Audit Logger** | audit-logger.js | Persistence audit.json | ✅ CORE |
| **Extension Chrome** | public/*.js | Popup mode SAFE | ✅ CORE |
| **Studio Dashboard** | studio/studioapp.js | Interface trading principale | ✅ CORE |
| **AGENTS_MONITOR.html** | AGENTS_MONITOR.html | Affiche agents (statique) | ⚠️ À améliorer |
| **audit-dashboard.html** | audit-dashboard.html | Dashboard audit | ⚠️ À améliorer |
| **Routes 50+** | server.js | MT5, sync, mapping, etc | ✅ Keep as-is |

### ❌ CE QUI MANQUE (À Ajouter Proprement)

| Élément | Pourquoi | Solution | Complexité |
|---------|---------|----------|-----------|
| **Mode continu/surveillance** | continuous-loop désactivé (CPU spike) | Surveillance agents temps réel SANS boucle infinie | MOYEN |
| **Communication inter-agents** | Pas de messages agent→agent | Système de "queue" + event bus | MOYEN |
| **Repair Agent** | Pas de centralisation erreurs | Agent passif qui écoute logs | FACILE |
| **Pipeline avec gating** | Tout parallèle, pas de dépendances | Chaîne d'agents avec blocages optionnels | DIFFICILE |
| **Extension alertes intelligentes** | Extension reçoit données mais pas d'alertes | Système push vers extension (via SSE ou polling) | MOYEN |
| **Dashboard centralisé** | Dispersé sur 3 pages | Unifier AGENTS_MONITOR + audit + studio | MOYEN |
| **Système de localisation** | Pas de liens cliquables vers fichiers | Ajouter FILE:line dans audit.json | FACILE |
| **Système d'alerte filtré** | Tous les signaux remontent | Filtrer par symboles + stratégies de l'utilisateur | MOYEN |

---

# 🧰 PARTIE 1 — AGENTS + COMMUNICATIONS RÉELLES

## Situation Actuelle

**4 agents appelés en parallèle par orchestrator:**
```javascript
const [coreResult, consensus, fearData, newsData] = await Promise.all([
  tradingCore.analyze(...),
  tfConsensus.buildConsensus(...),
  fearIndex.getFearIndex(),
  newsIntelligence.analyze(...)
]);
```

**Problème:** Pas de dépendances, pas d'ordre, pas de feedback inter-agents

## Solution: Agent Message Bus (Sans Casser l'Existant)

### 1.1 Créer: `agent-bus.js` (Middleware léger)

**Responsabilité:** Permettre agent→agent messages SANS modifier agents existants

```javascript
// agent-bus.js (100 lignes)
class AgentBus {
  constructor() {
    this.messages = [];      // Queue temporaire
    this.subscribers = {};   // {agentName: [callback1, callback2]}
    this.metadata = {};      // {agentName: {role, type, inputs, outputs}}
  }

  registerAgent(name, metadata) {
    // name: 'technicalAgent'
    // metadata: {role: 'Analyse technique', type: 'technical', ...}
    this.metadata[name] = metadata;
    this.subscribers[name] = [];
  }

  sendMessage(from, to, message) {
    // technicalAgent → orchestrator: {type: 'RSI_ANALYSIS', data: {...}}
    const msg = {
      id: Date.now() + Math.random(),
      from, to,
      message,
      timestamp: new Date().toISOString(),
      status: 'sent'
    };
    this.messages.push(msg);
    if (this.messages.length > 1000) this.messages.shift(); // Keep clean
    
    // Notify subscribers
    if (this.subscribers[to]) {
      this.subscribers[to].forEach(cb => cb(msg));
    }
    
    return msg;
  }

  subscribe(agentName, callback) {
    // Quand agentName reçoit un message → appelle callback
    if (!this.subscribers[agentName]) {
      this.subscribers[agentName] = [];
    }
    this.subscribers[agentName].push(callback);
  }

  getMessages(from, to) {
    // Historique messages entre deux agents
    return this.messages.filter(m => 
      (from ? m.from === from : true) && 
      (to ? m.to === to : true)
    );
  }

  getAllMetadata() {
    return this.metadata;
  }
}

module.exports = new AgentBus();
```

### 1.2 Intégrer dans server.js

**Ajout au démarrage (après orchestrator init):**

```javascript
// Ligne ~47 server.js
const agentBus = require('./agent-bus');

// Enregistrer les agents (metadata)
agentBus.registerAgent('orchestrator', {
  role: 'Coordinator maître',
  type: 'orchestration',
  inputs: ['MT5 payload'],
  outputs: ['direction, score, trade']
});

agentBus.registerAgent('technicalAgent', {
  role: 'Analyste technique RSI/EMA/ATR',
  type: 'technical',
  inputs: ['price, indicators'],
  outputs: ['direction, score, signals']
});

// ... autres agents
```

### 1.3 Utiliser dans orchestrator (sans le modifier)

**Créer:** `src/agents/orchestrator-instrumented.js` (wrapper, optionnel)
OU
**Loguer depuis server.js après orchestrator.run():**

```javascript
if (orchestrator) {
  orchestrator.run({...payload})
    .then(analysis => {
      // Log du résultat pour agentBus
      agentBus.sendMessage('orchestrator', 'system', {
        type: 'DECISION',
        direction: analysis.direction,
        score: analysis.score,
        agentsInvolved: ['tradingCore', 'tfConsensus', 'fearIndex', 'newsIntelligence']
      });
      
      marketStore.updateAnalysis(canonical, analysis);
    })
    .catch(e => {
      agentBus.sendMessage('orchestrator', 'repairAgent', {
        type: 'ERROR',
        error: e.message,
        stack: e.stack
      });
    });
}
```

---

### 1.4 Exposer agents states via Route

**Ajouter route:** `GET /agents/metadata` (nouvelle)

```javascript
app.get('/agents/metadata', (req, res) => {
  res.json({
    agents: agentBus.getAllMetadata(),
    messages: agentBus.getMessages(),
    timestamp: new Date().toISOString()
  });
});
```

## Résumé Partie 1

✅ Agents peuvent communiquer via agentBus  
✅ Messages loggés et récupérables  
✅ **ZÉRO modification** des agents existants  
✅ **ZÉRO changement** de la boucle orchestrator  

---

# 🔄 PARTIE 2 — MODE CONTINU + PIPELINE AVEC GATING

## Situation Actuelle

**continuous-loop.js existe mais EST DÉSACTIVÉ** (CPU 100%)

```javascript
// Ancien code (MAUVAIS)
while (autoMode) {
  orchestrationCycle();
  await sleep(30000);  // ← Cause CPU spike
}
```

## Solution: Surveillance Temps Réel SANS Boucle Infinie

### 2.1 Créer: `surveillance-agent.js` (30 lignes)

**Responsabilité:** Déclencher analyses basées sur ÉVÉNEMENTS, pas sur intervalle

```javascript
// surveillance-agent.js
const EventEmitter = require('events');

class SurveillanceAgent extends EventEmitter {
  constructor(marketStore, agentBus) {
    super();
    this.marketStore = marketStore;
    this.agentBus = agentBus;
    this.monitoredSymbols = {}; // {XAUUSD: {lastPrice, lastAnalysis, threshold}}
    this.isRunning = false;
  }

  // Appelé quand MT5 envoie un nouveau prix
  onMT5Update(symbol, newPayload) {
    if (!this.monitoredSymbols[symbol]) return;

    const prev = this.monitoredSymbols[symbol];
    const priceChange = Math.abs(newPayload.price - prev.lastPrice) / prev.lastPrice;

    // Déclencher nouvelle analyse si:
    // 1. Prix change de > 0.5% OU
    // 2. > 30s depuis dernière analyse
    const timeSinceAnalysis = (Date.now() - prev.lastAnalysisTime) / 1000;
    
    if (priceChange > 0.005 || timeSinceAnalysis > 30) {
      this.emit('trigger-analysis', {
        symbol,
        reason: priceChange > 0.005 ? 'PRICE_CHANGE' : 'TIME_ELAPSED',
        priceChange: (priceChange * 100).toFixed(2) + '%'
      });
    }

    this.monitoredSymbols[symbol].lastPrice = newPayload.price;
  }

  addMonitoredSymbol(symbol) {
    this.monitoredSymbols[symbol] = {
      lastPrice: 0,
      lastAnalysisTime: Date.now(),
      threshold: 0.005  // 0.5%
    };
  }

  removeMonitoredSymbol(symbol) {
    delete this.monitoredSymbols[symbol];
  }

  getMonitored() {
    return Object.keys(this.monitoredSymbols);
  }
}

module.exports = SurveillanceAgent;
```

### 2.2 Intégrer dans server.js

```javascript
// Ligne ~47
const SurveillanceAgent = require('./surveillance-agent');
const surveillanceAgent = new SurveillanceAgent(marketStore, agentBus);

// Écouter MT5 updates → déclencher analyses
marketStore.on('mt5-update', (symbol, payload) => {
  surveillanceAgent.onMT5Update(symbol, payload);
});

// Écouter demandes d'analyse de la surveillance
surveillanceAgent.on('trigger-analysis', async (event) => {
  if (orchestrator) {
    console.log(`[Surveillance] Analyse ${event.symbol} (${event.reason})`);
    const analysis = await orchestrator.run({
      symbol: event.symbol,
      ...marketStore.lastMT5Payload
    });
    // Sera broadcast via mediaStore.updateAnalysis() → SSE
  }
});

// Route pour monitorer un symbole
app.post('/surveillance/monitor', (req, res) => {
  const {symbol} = req.body;
  surveillanceAgent.addMonitoredSymbol(symbol);
  res.json({ok: true, monitored: surveillanceAgent.getMonitored()});
});
```

### 2.3 Pipeline Optional (State Futur)

**Pour PLUS TARD (si besoin gating en chaîne):**

```
Créer: pipeline-orchestrator.js
  → Appelle technicalAgent
  → Basé sur son résultat → appelle tradeValidator
  → Basé sur résultat → appelle riskManager
  → Etc.

MAIS: Pour maintenant, garder orchestrator.run() en parallèle
      (c'est ce qui fonctionne et c'est rapide)
```

## Résumé Partie 2

✅ Surveillance temps réel SANS CPU spike  
✅ Analyses déclenchées par ÉVÉNEMENTS (prix, temps)  
✅ **ZERO modification** orchestrator existant  
✅ Architecture prête pour pipeline futur  

---

# 📲 PARTIE 3 — EXTENSION + ALERTES INTELLIGENTES

## Situation Actuelle

**Extension en mode SAFE:**
- Utilisateur envoie screenshot manuellement
- Extension affiche résultat dans popup
- **Pas d'alertes proactives**
- **Pas de push depuis serveur**

## Solution: Alertes Filtrées vers Extension

### 3.1 Créer: `alert-manager.js` (Centralise alertes)

```javascript
// alert-manager.js
class AlertManager {
  constructor() {
    this.alerts = [];  // Queue alertes
    this.subscribers = [];  // Clients SSE
    this.userFilters = {};  // {userId: {symbols: [...], riskLevels: [...]}}
  }

  // Appelé quand analyse produit résultat intéressant
  createAlert(source, data) {
    const alert = {
      id: Date.now() + Math.random(),
      timestamp: new Date().toISOString(),
      source,  // 'technicalAgent', 'macroAgent', etc.
      symbol: data.symbol,
      type: data.type,  // 'SIGNAL', 'WARNING', 'ERROR', 'NEWS'
      severity: data.severity,  // 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
      message: data.message,
      data: data,
      read: false
    };

    this.alerts.push(alert);
    if (this.alerts.length > 500) this.alerts.shift();

    // Broadcast aux SSE subscribers filtrés
    this.notifySubscribers(alert);

    return alert;
  }

  // Filtrer alertes selon préférences utilisateur
  shouldNotify(alert, userFilters) {
    // Si symbole pas dans watched list → skip
    if (userFilters.symbols && 
        !userFilters.symbols.includes(alert.symbol)) {
      return false;
    }

    // Si severity en dessous du seuil → skip
    const severityMap = {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1};
    if (userFilters.minSeverity && 
        severityMap[alert.severity] < userFilters.minSeverity) {
      return false;
    }

    return true;
  }

  notifySubscribers(alert) {
    // Envoyer aux clients SSE qui veulent cet alert
    const msg = `data: ${JSON.stringify(alert)}\n\n`;
    this.subscribers.forEach(({res, filters}) => {
      if (this.shouldNotify(alert, filters)) {
        try { res.write(msg); } catch {}
      }
    });
  }

  addSubscriber(res, filters) {
    // Extension se connecte: POST /alerts/subscribe
    this.subscribers.push({res, filters});
    
    const cleanup = () => {
      this.subscribers = this.subscribers.filter(s => s.res !== res);
    };
    res.on('close', cleanup);

    return cleanup;
  }

  getAlerts(symbol, type, limit = 50) {
    return this.alerts
      .reverse()
      .filter(a => (!symbol || a.symbol === symbol) && 
                   (!type || a.type === type))
      .slice(0, limit);
  }
}

module.exports = new AlertManager();
```

### 3.2 Intégrer dans server.js

```javascript
// Ligne ~47
const alertManager = require('./alert-manager');

// Quand orchestrator produit un signal → créer alert
if (orchestrator) {
  orchestrator.run({...payload})
    .then(analysis => {
      if (analysis.direction !== 'ATTENDRE') {
        alertManager.createAlert('orchestrator', {
          symbol: analysis.symbol,
          type: 'SIGNAL',
          severity: analysis.score > 75 ? 'HIGH' : 'MEDIUM',
          message: `${analysis.direction} ${analysis.symbol} (score: ${analysis.score})`,
          direction: analysis.direction,
          score: analysis.score,
          trade: analysis.trade
        });
      }
      marketStore.updateAnalysis(canonical, analysis);
    });
}

// Route: Extension se connecte pour alertes
app.post('/alerts/subscribe', (req, res) => {
  const {symbols, minSeverity} = req.body;
  
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const cleanup = alertManager.addSubscriber(res, {symbols, minSeverity});
  
  // Initial handshake
  res.write(`data: ${JSON.stringify({type: 'connected'})}\n\n`);

  // Heartbeat
  const hb = setInterval(() => {
    try { res.write(': heartbeat\n\n'); } catch {}
  }, 15000);

  res.on('close', () => {
    clearInterval(hb);
    cleanup();
  });
});

// Route: Récupérer historique alertes
app.get('/alerts', (req, res) => {
  const {symbol, type, limit} = req.query;
  res.json(alertManager.getAlerts(symbol, type, parseInt(limit) || 50));
});
```

### 3.3 Modifier Extension: `public/background.js`

```javascript
// Dans background.js, ajouter:

// Écouter alertes du serveur
async function subscribeToAlerts() {
  const filters = {
    symbols: ['XAUUSD', 'EURUSD'],  // À configurer
    minSeverity: 2  // MEDIUM+
  };

  const eventSource = new EventSource(
    '/alerts/subscribe?symbols=' + filters.symbols.join(',')
  );

  eventSource.addEventListener('message', (e) => {
    const alert = JSON.parse(e.data);
    
    if (alert.type === 'SIGNAL') {
      // Créer notification
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'images/icon.png',
        title: `SIGNAL ${alert.direction}`,
        message: `${alert.symbol} · Score: ${alert.severity}`
      });

      // Envoyer à popup
      chrome.runtime.sendMessage({
        type: 'SHOW_ALERT',
        alert: alert
      });
    }
  });

  eventSource.onerror = () => {
    setTimeout(subscribeToAlerts, 5000);  // Reconnect après 5s
  };
}

// Lancer au démarrage
subscribeToAlerts();
```

## Résumé Partie 3

✅ Alertes filtrées vers extension  
✅ Extension reçoit notifications en temps réel  
✅ Pas de polling, SSE push  
✅ Utilisateur contrôle quels alertes  

---

# 📊 PARTIE 4 — DASHBOARD CENTRAL RÉVISÉ

## Situation Actuelle

**3 dashboards dispersés:**
- AGENTS_MONITOR.html (agents seulement)
- audit-dashboard.html (audit)
- studio/studioapp.js (trading)

**Problème:** Fragmentation, pas de vue unifiée

## Solution: Améliorer AGENTS_MONITOR.html → Cockpit Central

### 4.1 Fusionner dans AGENTS_MONITOR.html

**6 Onglets:**

```
[Agents] [Pipeline Live] [Décisions] [Alertes] [Réparations] [Audit]
```

#### Onglet 1: AGENTS (Temps Réel)

```
GET /agents/metadata
├─ orchestrator ✅ RUNNING (1245ms)
│  Dernière action: DECISION (LONG, score: 75)
│  
├─ tradingCore ✅ RUNNING (89ms)
│  RSI: 65 | EMA: 20>50 | Structure: BOS
│  
├─ macroAgent ⚠️ WARNING
│  NFP dans 5h 30m
│  
└─ repairAgent ✅ IDLE
   0 erreurs actives
```

#### Onglet 2: PIPELINE EN DIRECT

```
GET /agents/metadata + /stream (SSE)

Visualisation en temps réel:
technicalAgent ──┐
tradingCore   ───┤──→ orchestrator ──→ DECISION
macroAgent    ───┤
newsAgent    ────┘
```

#### Onglet 3: DÉCISIONS HISTORIQUE

```
GET /audit/state + /agents/decisions

[10:30:50] XAUUSD | LONG | 75/100 | FORT | ✅ exec
[10:29:45] EURUSD | SHORT | 68/100 | MODERE | ❌ blocked (macro warning)
[10:28:30] GOLD | ATTENDRE | 45/100 | FAIBLE | ⏸️  no action
```

#### Onglet 4: ALERTES EN COURS

```
GET /alerts

[CRITICAL] Erreur synchronisation (10:30:22)
[HIGH] Signal LONG XAUUSD score 75 (10:30:50)
[MEDIUM] NFP tomorrow 5h (10:15:00)

Filtrable par symbole / severity
```

#### Onglet 5: RÉPARATIONS (RepairAgent)

```
GET /repair/issues

Erreur detecée: macroAgent timeout
  Fichier: src/agents/macroAgent.js
  Ligne: 89
  Fonction: analyzeEconomicImpact
  Status: OPEN
  [View] [Acknowledge] [Ignore]
```

#### Onglet 6: AUDIT

```
GET /audit/state

Task tracking
Agent stats
Error log
Historique complet
```

### 4.2 Code Template

**Ajouter dans AGENTS_MONITOR.html:**

```html
<style>
  .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
  .tab-btn { padding: 10px 20px; cursor: pointer; border: none; background: #1e3a5f; color: #e2e8f0; }
  .tab-btn.active { background: #3b82f6; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
</style>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('agents')">Agents</button>
  <button class="tab-btn" onclick="switchTab('pipeline')">Pipeline</button>
  <button class="tab-btn" onclick="switchTab('decisions')">Décisions</button>
  <button class="tab-btn" onclick="switchTab('alerts')">Alertes</button>
  <button class="tab-btn" onclick="switchTab('repairs')">Répart</button>
  <button class="tab-btn" onclick="switchTab('audit')">Audit</button>
</div>

<div id="agents" class="tab-content active">
  <!-- Agents listing -->
</div>

<div id="pipeline" class="tab-content">
  <!-- Pipeline visualization -->
</div>

<!-- ...etc -->

<script>
function switchTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(name).classList.add('active');
  event.target.classList.add('active');
}

// Auto-refresh toutes les 2 secondes
setInterval(() => {
  fetch('/agents/metadata').then(r => r.json()).then(data => {
    updateAgentCards(data.agents);
    updatePipeline(data.messages);
  });
  
  fetch('/decisions').then(r => r.json()).then(data => {
    updateDecisions(data);
  });
  
  fetch('/alerts').then(r => r.json()).then(data => {
    updateAlerts(data);
  });
}, 2000);
</script>
```

## Résumé Partie 4

✅ Cockpit central unifié  
✅ 6 onglets pour différentes vues  
✅ Auto-refresh temps réel  
✅ Cliquable et traçable  

---

# 🧾 PARTIE 5 — BACKUP / AUDIT + LOCALISATION

## Situation Actuelle

**audit.json existe mais:**
- Pas de localisation fichier/ligne
- Pas de lien cliquable
- Difficile de retrouver l'erreur

## Solution: Enrichir audit.json avec Localisation

### 5.1 Modifier Structure audit.json

```json
{
  "events": [
    {
      "id": "event-001",
      "timestamp": "2026-04-03T10:30:45Z",
      "type": "AGENT_ANALYSIS",
      "agent": "technicalAgent",
      "action": "analyzeFromMT5",
      "status": "success",
      "duration_ms": 145,
      "result": {direction: "LONG", score: 72},
      
      "location": {
        "file": "src/agents/technicalAgent.js",
        "function": "analyzeFromMT5",
        "startLine": 145,
        "endLine": 198,
        "sourceCode": "https://workspace/src/agents/technicalAgent.js#L145"
      },
      
      "symbol": "XAUUSD",
      "timeframe": "H1",
      "inputs": {price: 2412.50, rsi: 65, ...},
      "outputs": {direction: "LONG", score: 72, ...}
    },
    
    {
      "id": "error-001",
      "timestamp": "2026-04-03T10:28:50Z",
      "type": "ERROR",
      "agent": "syncManager",
      "action": "validatePriceChartCoherence",
      "status": "failed",
      "error": "MT5 price vs chart price mismatch",
      "severity": "HIGH",
      
      "location": {
        "file": "src/agents/syncManager.js",
        "function": "validatePriceChartCoherence",
        "startLine": 56,
        "sourceCode": "https://workspace/src/agents/syncManager.js#L56"
      },
      
      "context": {mt5Price: 2412.50, chartPrice: 2412.45, diff: 0.05},
      "resolution": {
        "status": "resolved",
        "resolvedAt": "2026-04-03T10:29:12Z",
        "action": "Data refreshed from MT5"
      }
    }
  ],
  
  "queryable": {
    "agentPerformance": {
      "technicalAgent": {totalCalls: 87, successRate: 100, avgTime: 145},
      "macroAgent": {totalCalls: 24, successRate: 95, avgTime:234, errorCount: 1}
    },
    
    "errorPatterns": [
      {error: "timeout", count: 3, agents: ["macroAgent", "newsAgent"]},
      {error: "network_error", count: 1, agents: ["dataSourceManager"]}
    ]
  }
}
```

### 5.2 Intégrer auditLogger pour Localisation

**Créer fonction helper:**

```javascript
// utils/audit-helper.js
function getCallerLocation() {
  const stack = new Error().stack.split('\n')[3];
  // Parse stack line → file, function, line
  const match = stack.match(/at\s+(\w+).*\((.+):(\d+)/);
  if (match) {
    return {
      function: match[1],
      file: match[2].replace(__dirname + '/', ''),
      line: match[3]
    };
  }
  return {function: 'unknown', file: 'unknown', line: 0};
}

module.exports = { getCallerLocation };
```

**Utiliser dans audit-logger.js:**

```javascript
function logEvent(category, action, details) {
  const location = getCallerLocation();
  
  const event = {
    id: Date.now() + Math.random(),
    timestamp: new Date().toISOString(),
    category,
    action,
    details,
    location: {
      file: location.file,
      function: location.function,
      line: parseInt(location.line),
      sourceUrl: `../workspace/${location.file}#L${location.line}`
    }
  };

  this.eventLog.push(event);
  this.writeAudit();
  
  return event;
}
```

### 5.3 Route pour Requêtes Intelligentes

```javascript
// GET /audit/query?agent=technicalAgent&type=ERROR&limit=20
app.get('/audit/query', (req, res) => {
  const {agent, type, severity, symbol, limit} = req.query;
  
  let events = auditLogger.getState().events || [];
  
  if (agent) events = events.filter(e => e.agent === agent);
  if (type) events = events.filter(e => e.type === type);
  if (severity) events = events.filter(e => e.severity === severity);
  if (symbol) events = events.filter(e => e.symbol === symbol);
  
  res.json({
    ok: true,
    count: events.length,
    events: events.slice(0, parseInt(limit) || 50),
    queryable: auditLogger.getState().queryable
  });
});
```

## Résumé Partie 5

✅ Localisation fichier/ligne/fonction  
✅ Liens cliquables vers source  
✅ Requêtes intelligentes sur audit  
✅ Retrouver erreur en 1 seconde  

---

# 🎯 SUMMARY — CE QUI CHANGE

## Avant
```
- Orchest rator parallèle (4 agents)
- Extension mode SAFE
- 3 dashboards dispersés
- Pas de communication inter-agents
- continuous-loop désactivé
- Audit sans localisation
```

## Après
```
- Orchestrator parallèle ✅ (keep as-is)
- Extension + alertes intelligentes ✅
- Dashboard central unifié ✅
- AgentBus pour communication ✅
- SurveillanceAgent temps réel ✅
- Audit + localisation ✅
- RepairAgent centralisé ✅
```

## Fichiers à Créer
1. `agent-bus.js` (100 lignes)
2. `surveillance-agent.js` (30 lignes)
3. `alert-manager.js` (100 lignes)
4. `utils/audit-helper.js` (20 lignes)
5. Améliorer AGENTS_MONITOR.html (300 lignes)

## Fichiers à Modifier Légèrement
1. `server.js` - 10 intégrations (50 lignes)
2. `audit-logger.js` - Ajouter localisation (15 lignes)
3. `public/background.js` - Alertes extension (30 lignes)

## Fichiers à Laisser Intact
1. orchestrator.js ✅
2. Tous les agents ✅
3. Routes existantes ✅
4. MarketStore ✅

---

# ✅ PROCHAINES ÉTAPES

1. ✅ **Approbation du plan**
2. 🔧 **Implémentation ordonnée:**
   - Agent bus
   - Surveillance agent
   - Alert manager
   - Dashboard amélioration
   - Audit enrichissement
   - Extension modification

**Approuves-tu ce plan révisé qui:**
- Respecte 100% l'architecture existante
- Ajoute exactement ce qu'il manque
- Ne casse rien
- Crée une vraie équipe intelligente
