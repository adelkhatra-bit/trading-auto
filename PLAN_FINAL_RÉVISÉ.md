# 🎯 PLAN FINAL RÉVISÉ — Système Multi-Agents Vivant avec Indicateurs Créatifs

**Date:** 3 avril 2026  
**Statut:** PRÊT POUR IMPLÉMENTATION  
**Méthodologie:** Analyse complète → Respect absolu de l'existant → Intégrations chirurgicales

---

# 📍 PARTIE 1 — ANALYSE COMPLÈTE DE L'ARCHITECTURE ACTUELLE

## 1.1 État Actuel (Ce Qui Fonctionne)

### Serveur Principal
```
PORT 4000 (server.js)
├─ Routes HTML: / (accueil), /studio, /audit
├─ Routes API: 50+ endpoints (MT5, TV-bridge, klines, quotes, etc.)
├─ SSE /stream: Broadcast temps réel via marketStore.addSSEClient()
├─ SSE /agent-activity: Activity log broadcast en direct
└─ Logging: pushLog() → sysLogs[] (500 max, circulaire)
```

### Orchestrator (src/agents/orchestrator.js)
```
orchestrator.run(mt5Payload) → Promise.all([
  tradingCore.analyze(currentTFData, profile),
  tfConsensus.buildConsensus(multiTF),
  fearIndex.getFearIndex(),
  newsIntelligence.analyze(symbol)
]) → Résultat fusionné {direction, score, strength, trade}
```

**Appel depuis server.js (ligne ~818-825):**
```javascript
if (orchestrator) {
  orchestrator.run({ symbol, broker_symbol, price, timeframe, ... })
    .then(analysis => marketStore.updateAnalysis(canonical, analysis))
    .catch(() => {});
}
```

### Communication Actuelle
```
MT5 → POST /mt5 → mt5_data.json
                ↓
          server.js lit
                ↓
          orchestrator.run()
                ├─ [4 agents en parallèle]
                └─ Résultat fusionné
                        ↓
              marketStore.updateAnalysis()
                        ↓
                    SSE /stream broadcast
                        ↓
        [Dashboard, Extension, Studio reçoivent]
```

### Agents Actuels
- **tradingCore** → Structure, RSI, EMA, ATR, BOS, liquidity
- **tfConsensus** → Multi-timeframe consensus
- **fearIndex** → VIX, fear level
- **newsIntelligence** → Economic events, sentiment

**Architecture agent standard:**
```javascript
module.exports = {
  analyze: async (data, profile) => {
    // Retourne: {direction, score, levels, rsi, ema, structure, fvgs, liquidity, ...}
  }
};
```

### Storage / Persistence
- **sysLogs[]** (500 max) → pushLog() → broadcast SSE → débounce 5s → SYSTEM_LOG.json
- **audit.json** → Logs audit (audit-logger.js)
- **marketStore.bySymbol{}** → Cache MT5 latest
- **marketStore.analysisCache{}** → Cache analyses
- **Aucune DB** → Tout en JSON

### Dashboard Actuel
- **AGENTS_MONITOR.html** → Interface statique (à améliorer)
- **audit-dashboard.html** → Tracking audit (7 tabs)
- **studio/** → Interface trading principale (appelle /instant-trade-live, /state, /stream SSE)

### Extension Chrome
```
public/background.js → Service worker (mode SAFE)
  ├─ Auto-loop DÉSACTIVÉ (CPU 100%)
  ├─ Manuel buttons seulement
  └─ showSignal() → alert() popup simple
```

---

## 1.2 Ce Qui Existe MAIS Est Limité

| Élément | État | Limitation |
|---------|------|-----------|
| Architecture agents | ✅ Modulaire | Agents statiques, pas de création dynamique |
| Communication | ✅ SSE /stream | One-way broadcast seulement |
| Dashboard | ✅ Existe | Statique, pas de cockpit vivant |
| Extension | ✅ Existe | Popup simple, pas d'alertes intelligentes |
| Logging | ✅ 3 niveaux | Pas de localisation file/line/function |
| Surveillance | ❌ continuous-loop désactivé | CPU spike si réactivé |
| Indicateurs | ❌ N'existe pas | ZÉRO création dynamique |
| Gating/Pipeline | ❌ N'existe pas | Tout en parallèle, pas de dépendances |

---

# 🔧 PARTIE 2 — AGENTS: ARCHITECTURE RÉVISÉE + INDICATORAGENT

## 2.1 Nouvelle Architecture: 4 Couches d'Agents

### Couche 1: Analyseurs Fondamentaux (Existants, Optimisés)
```
tradingCore       → Structure, support/résistance, BOS/CHoCH
tfConsensus       → Multi-timeframe alignment
fearIndex         → Sentiment global
newsIntelligence  → Macro events + sentiment
```

### Couche 2: NOUVEL AGENT — indicatorAgent

**Responsabilité CRITIQUE:**

```
indicatorAgent.generateIndicators(symbol, timeframe, marketCondition)
  ├─ Analyser condition du marché actuelle
  ├─ Proposer indicateurs adaptés (tradables)
  ├─ Générer logique exploitable (conditions + signaux)
  ├─ Créer code MQL5 compatible MT5
  ├─ Retourner struct: {indicators: [], signals: [], mql5Code: '...'}
  └─ Chaque entrée = {name, type, formula, thresholds, signal}
```

**Exemples d'indicateurs créés:**

1. **Confluence RSI+Structure** (volatilité moyenne)
   ```
   Condition: RSI(14) < 30 AND candle.low < support
   Signal: LONG si price ↑ après oversold
   MQL5: if (iRSI(...) < 30 && currentPrice < prevLow) { BuySignal = true; }
   ```

2. **Liquidité & Manipulation** (volatilité basse)
   ```
   Condition: ATR(14) < ATR_moyenne AND HIGH-LOW < threshold
   Signal: Attendre breakout
   MQL5: if (iATR(...) < avgATR && (HIGH-LOW) < liquidRange) { WaitForBreakout = true; }
   ```

3. **Timing Entrée** (volatilité haute)
   ```
   Condition: EMA20 > EMA50 AND RSI(14) entre 45-55 (neutre)
   Signal: LONG sur cassure resistance + confirmation
   MQL5: if (iMA(...,PERIOD_H1,20) > iMA(...,PERIOD_H1,50) && iRSI > 45 && iRSI < 55)
   ```

4. **Volatilité Spécifique** (metals)
   ```
   Condition: ATR > historique 70% + EMA20 au-dessus EMA50
   Signal: LONG sur volatilité haute + trend
   MQL5: GenerateATRAlert()
   ```

### 2.2 Format Agent Standardisé (Tous)

```javascript
// src/agents/AGENT_NAME.js
module.exports = {
  name:        'AgentName',
  type:        'analyzer|indicator|validator|repair',
  inputs:      ['MT5 data', 'other agents output'],
  outputs:     ['direction', 'score', 'custom data'],
  
  async analyze/generate/validate(data, context) {
    // Implémentation
    return {
      agent: 'AgentName',
      status: 'ok|warning|error',
      direction: 'LONG|SHORT|ATTENDRE',
      score: 0-100,
      data: {...},  // Custom output
      executionMs: Date.now() - start
    };
  }
};
```

### 2.3 Intégration indicatorAgent dans Orchestrator

**Approche 1: Parallèle (Recommandée)**
```javascript
// orchestrator.js lignes 40-45
const [coreResult, consensus, fearData, newsData, indicatorData] = await Promise.all([
  tradingCore.analyze(currentTFData, profile),
  tfConsensus.buildConsensus(multiTF),
  fearIndex.getFearIndex(),
  newsIntelligence.analyze(symbol),
  indicatorAgent.generateIndicators(symbol, currentTF, marketCondition)  // NOUVEAU
]);
```

**Approche 2: Série (Si indicateur dépend de core)**
```javascript
// orchestrator.js
const coreResult = await tradingCore.analyze(...);
const indicatorData = await indicatorAgent.generateIndicators(
  symbol, currentTF, 
  { coreDirection: coreResult.direction, volatility: currentTFData.atr }
);
```

**➜ RECOMMANDATION:** Parallèle (plus rapide, indicateurs indépendants)

### 2.4 Structure Résultat indicatorAgent

```javascript
{
  agent: 'indicatorAgent',
  status: 'ok',
  symbol: 'XAUUSD',
  timeframe: 'H1',
  marketCondition: 'HIGH_VOLATILITY|MEDIUM|LOW_LIQUIDITY',
  indicators: [
    {
      name: 'RSI_Confluence_Support',
      type: 'overbought_oversold',
      formula: 'RSI(14) < 30 AND Price < Prev_Low',
      thresholds: {rsiLevel: 30, confirmCandle: 1},
      signal: 'LONG',
      weight: 0.7,  // Confiance dans ce signal
      mql5Line: 'if (iRSI(...,14) < 30 && currentPrice < prevLow) { signal = BUY; }'
    },
    {
      name: 'Liquidity_Trap',
      type: 'time_to_wait',
      formula: 'ATR(14) < 70% historical_avg',
      signal: 'WAIT',
      weight: 0.5
    },
    // ... autres indicateurs générés
  ],
  aggregateSignal: 'LONG',  // Consensus des indicateurs
  mql5Code: `// Indicateurs générés 2026-04-03T10:30:00Z
             if (iRSI(...) < 30) { BUY_SIGNAL = true; }
             if (iATR(...) < avgATR) { WAIT_SIGNAL = true; }
             ...`
}
```

---

# ⚡ PARTIE 3 — PIPELINE + MODE CONTINU INTELLIGENT

## 3.1 Surveillance Temps Réel (Remplace continuous-loop)

### Problème actual
```
continuous-loop.js:
while(autoMode) {
  orchestrationCycle();
  await sleep(30000);  // ← CPU spike + blocking
}
```

### Solution: Event-Driven Surveillance

**Créer: src/agents/surveillance-agent.js (40 lignes)**

```javascript
class SurveillanceAgent extends EventEmitter {
  constructor(marketStore, orchestrator) {
    super();
    this.marketStore = marketStore;
    this.orchestrator = orchestrator;
    this.monitored = {};  // {symbol: {lastPrice, lastAnalysisTime, threshold}}
    this.isLive = false;
  }

  // Appelé POUR CHAQUE MT5 update reçue
  onMT5Update(symbol, newPayload) {
    if (!this.monitored[symbol]) return;

    const prev = this.monitored[symbol];
    const priceChange = Math.abs(newPayload.price - prev.lastPrice) / prev.lastPrice;
    const timeSinceAnalysis = (Date.now() - prev.lastAnalysisTime) / 1000;

    // Déclencher analyse SI:
    // 1. Prix change > 0.5% OU
    // 2. > 30 secondes depuis dernière analyse
    if (priceChange > 0.005 || timeSinceAnalysis > 30) {
      this.emit('trigger-analysis', {
        symbol,
        reason: priceChange > 0.005 ? 'PRICE_CHANGE' : 'TIME_ELAPSED',
        priceChange: (priceChange * 100).toFixed(2) + '%'
      });
      
      prev.lastAnalysisTime = Date.now();
    }
    prev.lastPrice = newPayload.price;
  }

  addMonitored(symbol) {
    this.monitored[symbol] = {
      lastPrice: 0,
      lastAnalysisTime: Date.now(),
      threshold: 0.005  // 0.5%
    };
    pushLog('surveillance', 'monitor-start', symbol, 'ok', '');
  }

  removeMonitored(symbol) {
    delete this.monitored[symbol];
    pushLog('surveillance', 'monitor-stop', symbol, 'ok', '');
  }

  getMonitored() {
    return Object.keys(this.monitored);
  }
}
```

### Intégration dans server.js

**Ajout après orchestrator init (ligne ~47):**
```javascript
const SurveillanceAgent = require('./src/agents/surveillance-agent');
const surveillanceAgent = new SurveillanceAgent(marketStore, orchestrator);

// Écouter MT5 updates → déclencher analyses
marketStore.on('mt5-update', (symbol, payload) => {
  surveillanceAgent.onMT5Update(symbol, payload);
});

// Écouter demandes d'analyse
surveillanceAgent.on('trigger-analysis', async (event) => {
  console.log(`[Surveillance] Analyse ${event.symbol} (${event.reason})`);
  const latest = marketStore.getLatestForSymbol(event.symbol);
  if (orchestrator && latest) {
    const analysis = await orchestrator.run(latest.latestPayload);
    // Sera broadcast via marketStore.updateAnalysis() → SSE
  }
});

// Route: Activer surveillance pour symbole
app.post('/surveillance/monitor', (req, res) => {
  const {symbol} = req.body;
  surveillanceAgent.addMonitored(symbol);
  res.json({ok: true, monitored: surveillanceAgent.getMonitored()});
});

// Route: État surveillance
app.get('/surveillance/status', (req, res) => {
  res.json({ok: true, monitored: surveillanceAgent.getMonitored()});
});
```

## 3.2 Pipeline avec Gating (Optionnel Futur)

**Pour PLUS TARD si besoin dépendances en chaîne:**

```
technicalAgent → Analysé
  ↓
tradeValidator → "Ce setup est valide?" 
  ↓ (si YES)
riskManager → "Risk: LOW/MEDIUM/HIGH?"
  ↓
orchestrator → Décision finale
```

**Pour MAINTENANT:** Garder Promise.all (rapide, parallèle)

---

# 📲 PARTIE 4 — COMMUNICATION INTER-AGENTS + ORCHESTRATION

## 4.1 Créer: Agent Message Bus (Middleware léger)

**Créer: agent-bus.js (90 lignes)**

```javascript
class AgentBus {
  constructor() {
    this.messages = [];      // Queue temporaire
    this.subscribers = {};   // {agentName: [callback1, callback2]}
    this.agents = {};        // {agentName: metadata}
  }

  registerAgent(name, metadata) {
    // Enregistrer un agent avec metadata
    this.agents[name] = metadata;
    this.subscribers[name] = [];
    pushLog('agentbus', name, 'REGISTER', 'ok', metadata.type || '');
  }

  sendMessage(from, to, message) {
    // from (ex: 'technicalAgent') → to (ex: 'orchestrator')
    const msg = {
      id: Date.now() + Math.random(),
      from, to,
      message,
      timestamp: new Date().toISOString()
    };
    this.messages.push(msg);
    if (this.messages.length > 500) this.messages.shift();

    // Notifier subscribers
    if (this.subscribers[to]) {
      this.subscribers[to].forEach(cb => {
        try { cb(msg); } catch(e) { 
          pushLog('agentbus-error', to, 'MESSAGE_HANDLER', 'error', e.message);
        }
      });
    }

    return msg;
  }

  subscribe(agentName, callback) {
    if (!this.subscribers[agentName]) {
      this.subscribers[agentName] = [];
    }
    this.subscribers[agentName].push(callback);
  }

  getMessages(from, to, limit = 50) {
    return this.messages
      .filter(m => (from ? m.from === from : true) && (to ? m.to === to : true))
      .slice(-limit);
  }

  getAllAgents() {
    return this.agents;
  }

  getState() {
    return {
      agents: this.agents,
      messageCount: this.messages.length,
      recentMessages: this.messages.slice(-10)
    };
  }
}

module.exports = new AgentBus();
```

### Intégration dans server.js

```javascript
// Ligne ~47
const agentBus = require('./agent-bus');

// Enregistrer agents
agentBus.registerAgent('orchestrator', {type: 'coordinator', role: 'Master decision maker'});
agentBus.registerAgent('technicalAgent', {type: 'analyzer', role: 'Technical structure'});
agentBus.registerAgent('indicatorAgent', {type: 'generator', role: 'Create indicators'});
// ...

// Quand orchestrator retourne résultat
if (orchestrator) {
  orchestrator.run({...payload})
    .then(analysis => {
      // Log pour bus
      agentBus.sendMessage('orchestrator', 'system', {
        type: 'DECISION',
        direction: analysis.direction,
        score: analysis.score
      });
      marketStore.updateAnalysis(canonical, analysis);
    })
    .catch(e => {
      agentBus.sendMessage('system', 'repairAgent', {
        type: 'ERROR',
        error: e.message,
        severity: 'HIGH'
      });
    });
}

// Route: État du bus
app.get('/agents-bus', (req, res) => {
  res.json(agentBus.getState());
});
```

---

# 🎯 PARTIE 5 — EXTENSION + ALERTES INTELLIGENTES

## 5.1 Alert Manager (Centralise alertes filtrées)

**Créer: alert-manager.js (120 lignes)**

```javascript
class AlertManager {
  constructor() {
    this.alerts = [];          // Queue alertes
    this.sseSubscribers = [];  // Clients SSE
    this.userFilters = {};     // {userId: {symbols, minSeverity}}
  }

  createAlert(source, data) {
    // Appelé quand événement intéressant détecté
    const alert = {
      id: Date.now() + Math.random(),
      timestamp: new Date().toISOString(),
      source,              // 'orchestrator', 'indicatorAgent', 'repairAgent'
      symbol: data.symbol,
      type: data.type,     // 'SIGNAL', 'WARNING', 'ERROR', 'INFO'
      severity: data.severity,  // 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
      message: data.message,
      data: data,
      read: false
    };

    this.alerts.push(alert);
    if (this.alerts.length > 500) this.alerts.shift();

    // Broadcast aux SSE subscribers
    this.notifySubscribers(alert);
    pushLog('alertManager', source, 'ALERT', 'ok', data.message);

    return alert;
  }

  shouldNotify(alert, userFilters) {
    // Filtrer selon préférences utilisateur
    if (userFilters.symbols && !userFilters.symbols.includes(alert.symbol)) {
      return false;
    }

    const severityMap = {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1};
    if (userFilters.minSeverity && 
        severityMap[alert.severity] < userFilters.minSeverity) {
      return false;
    }

    return true;
  }

  notifySubscribers(alert) {
    const msg = `data: ${JSON.stringify(alert)}\n\n`;
    this.sseSubscribers = this.sseSubscribers.filter(({res, filters}) => {
      try {
        if (this.shouldNotify(alert, filters)) {
          res.write(msg);
        }
        return true;
      } catch(e) {
        return false;  // Remove closed connection
      }
    });
  }

  addSubscriber(res, filters) {
    // Extension ou client SSE se connecte
    this.sseSubscribers.push({res, filters});
    
    res.on('close', () => {
      this.sseSubscribers = this.sseSubscribers.filter(s => s.res !== res);
    });

    return () => {
      this.sseSubscribers = this.sseSubscribers.filter(s => s.res !== res);
    };
  }

  getAlerts(symbol, type, limit = 50) {
    return this.alerts
      .reverse()
      .filter(a => (!symbol || a.symbol === symbol) && 
                   (!type || a.type === type))
      .slice(0, limit);
  }

  getState() {
    return {
      totalAlerts: this.alerts.length,
      recentAlerts: this.alerts.slice(0, 20),
      subscriberCount: this.sseSubscribers.length
    };
  }
}

module.exports = new AlertManager();
```

### Intégration dans server.js

```javascript
// Ligne ~47
const alertManager = require('./alert-manager');

// Quand orchestrator produit signal
if (orchestrator) {
  orchestrator.run({...})
    .then(analysis => {
      if (analysis.direction !== 'ATTENDRE' && analysis.score > 60) {
        alertManager.createAlert('orchestrator', {
          symbol: analysis.symbol,
          type: 'SIGNAL',
          severity: analysis.score > 75 ? 'HIGH' : 'MEDIUM',
          message: `${analysis.direction} ${analysis.symbol} (score: ${analysis.score})`
        });
      }
    });
}

// Quand indicatorAgent génère indicateur
// (After indicatorAgent result added to orchestrator)
if (indicatorData && indicatorData.indicators.length > 0) {
  alertManager.createAlert('indicatorAgent', {
    symbol: indicatorData.symbol,
    type: 'INFO',
    severity: 'MEDIUM',
    message: `${indicatorData.indicators.length} indicateurs générés pour ${indicatorData.marketCondition}`
  });
}

// Route: Subscribe to alerts (Extension SSE)
app.post('/alerts/subscribe', (req, res) => {
  const {symbols, minSeverity} = req.body || {};
  
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const cleanup = alertManager.addSubscriber(res, {symbols, minSeverity});
  
  res.write(`data: ${JSON.stringify({type: 'connected'})}\n\n`);

  const hb = setInterval(() => {
    try { res.write(': heartbeat\n\n'); } catch {}
  }, 15000);

  res.on('close', () => {
    clearInterval(hb);
    cleanup();
  });
});

// Route: Récupérer alertes
app.get('/alerts', (req, res) => {
  const {symbol, type, limit} = req.query;
  res.json(alertManager.getAlerts(symbol, type, parseInt(limit) || 50));
});
```

## 5.2 Modifier Extension: public/background.js

```javascript
// Ajouter après autoLoop():

async function subscribeToAlerts() {
  const filters = {
    symbols: ['XAUUSD', 'EURUSD'],  // À lire depuis localStorage
    minSeverity: 2  // MEDIUM+
  };

  const eventSource = new EventSource(
    '/alerts/subscribe?symbols=' + filters.symbols.join(',')
  );

  eventSource.addEventListener('message', (e) => {
    const alert = JSON.parse(e.data);
    
    if (alert.type === 'SIGNAL') {
      // Notifier utilisateur
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'images/icon-48.png',
        title: `🚨 SIGNAL ${alert.data.direction || '?'}`,
        message: `${alert.symbol} • Score: ${alert.data.score || '?'}`
      });

      // Envoyer à popup
      chrome.runtime.sendMessage({
        type: 'SHOW_ALERT',
        alert: alert
      });
    }
  });

  eventSource.onerror = () => {
    setTimeout(subscribeToAlerts, 5000);  // Reconnect
  };
}

// Lancer au démarrage
subscribeToAlerts();
```

---

# 📊 PARTIE 6 — DASHBOARD CENTRAL + AUDIT ENRICHI

## 6.1 Améliorer AGENTS_MONITOR.html → Cockpit Central

**6 Onglets:**

```
[Agents] [Pipeline] [Décisions] [Alertes] [Indicateurs] [Réparations]
```

### Onglet 1: AGENTS (EN DIRECT)

```
GET /agents-bus

┌─────────────────────┐
│ orchestrator    ✅  │ RUNNING (1245ms)
│ Last: DECISION LONG │ Score 75
├─────────────────────┤
│ technicalAgent  ✅  │ RUNNING (89ms)
│ RSI: 65 | EMA: ↑    │
├─────────────────────┤
│ indicatorAgent  ✅  │ RUNNING (156ms)  [NOUVEAU]
│ 4 indicateurs créés │
├─────────────────────┤
│ repairAgent     🟢  │ IDLE
│ 0 erreurs actives   │
└─────────────────────┘
```

### Onglet 2: PIPELINE EN TEMPS RÉEL

```
Visualisation arrows:

technicalAgent ─┐
indicatorAgent ─┤─→ orchestrator ──→ DECISION
fearIndex    ───┤                  [BROADCAST]
newsAgent    ───┘
```

### Onglet 3: DÉCISIONS HISTORIQUE

```
[10:30:50] XAUUSD | LONG | 75/100 | ✅ traded
[10:29:45] EURUSD | SHORT | 68/100 | ❌ blocked
[10:28:30] GOLD | WAIT | 45/100 | ⏸️  no action
```

### Onglet 4: ALERTES EN COURS

```
GET /alerts

[HIGH] SIGNAL LONG XAUUSD (10:30:50)
  Indicateurs: RSI_Support + Liquidity
  
[MEDIUM] 4 indicateurs créés (10:30:20)
  Type: confluence, liquidité, timing

[INFO] Surveillance active (10:15:00)
  Symboles: XAUUSD, EURUSD
```

### Onglet 5: INDICATEURS CRÉÉS [NOUVEAU]

```
GET /instant-trade-live (section indicators)

Sym: XAUUSD | TF: H1 | Condition: HIGH_VOLATILITY

1️⃣ RSI_Confluence_Support
   Formula: RSI(14) < 30 AND Price < Support
   Signal: LONG
   Weight: 0.7

2️⃣ Liquidity_Trap  
   Formula: ATR(14) < 70% avg
   Signal: WAIT
   Weight: 0.5

3️⃣ Timing_Entry
   Formula: EMA20>50 + RSI 45-55
   Signal: LONG + breakout
   Weight: 0.8

🔗 [View MQL5 Code] [Import to MT5]
```

### Onglet 6: RÉPARATIONS

```
GET /repair/issues

⚠️ OPEN: macroAgent timeout
   File: src/agents/macroAgent.js:89
   Function: analyzeEconomicImpact
   Status: OPEN
   [Acknowledge] [Resolve] [Ignore]

✅ RESOLVED: technicalAgent RSI calc
   File: src/agents/technicalAgent.js:56
   Resolved: 2026-04-03 10:45:00
```

## 6.2 Code Template AGENTS_MONITOR.html

```html
<style>
  .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
  .tab-btn { padding: 10px 20px; cursor: pointer; border: none; background: #1e3a5f; }
  .tab-btn.active { background: #3b82f6; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .agent-card { background: rgba(30,58,95,0.4); border-radius: 8px; padding: 12px; margin: 8px 0; }
  .agent-status { display: flex; align-items: center; justify-content: space-between; }
  .status-dot { width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
  .status-dot.online { background: #10b981; }
  .status-dot.warning { background: #f59e0b; }
</style>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('agents')">Agents</button>
  <button class="tab-btn" onclick="switchTab('pipeline')">Pipeline</button>
  <button class="tab-btn" onclick="switchTab('decisions')">Décisions</button>
  <button class="tab-btn" onclick="switchTab('alerts')">Alertes</button>
  <button class="tab-btn" onclick="switchTab('indicators')">Indicateurs</button>
  <button class="tab-btn" onclick="switchTab('repairs')">Réparations</button>
</div>

<div id="agents" class="tab-content active">
  <div id="agents-grid" class="status-grid"></div>
</div>

<div id="pipeline" class="tab-content">
  <svg id="pipeline-svg" width="100%" height="200"></svg>
</div>

<!-- ... autres onglets ... -->

<script>
function switchTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(name).classList.add('active');
  event.target.classList.add('active');
}

// Auto-refresh 2 secondes
setInterval(() => {
  fetch('/agents-bus').then(r => r.json()).then(data => {
    updateAgentCards(data.agents);
  });
  
  fetch('/instant-trade-live?symbol=XAUUSD&timeframe=H1').then(r => r.json()).then(data => {
    if (data.agents && data.agents.indicatorAgent) {
      updateIndicators(data.agents.indicatorAgent);
    }
  });
  
  fetch('/alerts').then(r => r.json()).then(data => {
    updateAlerts(data);
  });
}, 2000);
</script>
```

---

# 🧾 PARTIE 6 — BACKUP / AUDIT + LOCALISATION

## 6.1 Enrichir Logs avec Localisation

**Créer: utils/audit-helper.js**

```javascript
function getCallerLocation() {
  const stack = new Error().stack.split('\n');
  // Parse ligne 3: "at functionName (file:line:col)"
  const match = stack[3].match(/at\s+(.+?)\s+\((.+):(\d+):(\d+)/);
  
  if (match) {
    const [, func, file, line, col] = match;
    const cleanFile = file.replace(process.cwd() + '/', '');
    
    return {
      file: cleanFile,
      function: func || 'anonymous',
      line: parseInt(line),
      column: parseInt(col),
      sourceUrl: `workspace://${cleanFile}#L${line}`
    };
  }
  
  return {file: 'unknown', function: 'unknown', line: 0, sourceUrl: ''};
}

module.exports = { getCallerLocation };
```

## 6.2 Modifier pushLog() pour Ajouter Localisation

**Dans server.js, ligne ~1557:**

```javascript
const {getCallerLocation} = require('./utils/audit-helper');

function pushLog(from, to, action, status, detail) {
  const location = getCallerLocation();
  
  const entry = {
    id:     Date.now(),
    ts:     new Date().toISOString(),
    from:   from   || 'system',
    to:     to     || 'system',
    action: action || '',
    status: status || 'ok',
    detail: detail || '',
    location: {
      file: location.file,
      function: location.function,
      line: location.line,
      sourceUrl: location.sourceUrl
    }
  };

  sysLogs.unshift(entry);
  if (sysLogs.length > 500) sysLogs.pop();
  
  try { marketStore.broadcast({ type: 'syslog', entry }); } catch (_) {}
  broadcastAgentActivity(entry);
  writeSysLog();
}
```

## 6.3 Routes Intelligentes de Requête d'Audit

```javascript
// GET /audit/query?agent=technicalAgent&type=ERROR&symbol=XAUUSD&limit=20
app.get('/audit/query', (req, res) => {
  const {agent, type, severity, symbol, limit} = req.query;
  
  let results = sysLogs;
  
  if (agent) results = results.filter(e => e.from === agent);
  if (type) results = results.filter(e => e.status === type);
  if (symbol) results = results.filter(e => e.detail.includes(symbol));
  
  res.json({
    ok: true,
    count: results.length,
    logs: results.slice(0, parseInt(limit) || 50),
    stats: {
      totalLogs: sysLogs.length,
      errorCount: sysLogs.filter(e => e.status === 'error').length,
      agentCount: [...new Set(sysLogs.map(e => e.from))].length
    }
  });
});

// GET /audit/locate?file=src/agents/technicalAgent.js&line=145
// Retourne: entier log entry avec localisation clickable
app.get('/audit/locate', (req, res) => {
  const {file, line} = req.query;
  
  const found = sysLogs.find(e => 
    e.location?.file === file && 
    e.location?.line === parseInt(line)
  );
  
  if (found) {
    res.json({ok: true, entry: found});
  } else {
    res.json({ok: false, error: 'No log entry for this location'});
  }
});
```

---

# ✅ RÉSUMÉ — CE QUI CHANGE EXACTEMENT

## Fichiers à Créer (ZÉRO modification des existants)

| Fichier | Lignes | Responsabilité |
|---------|--------|-----------------|
| src/agents/indicatorAgent.js | 150 | Génère indicateurs MT5 |
| src/agents/surveillance-agent.js | 40 | Mode continu event-driven |
| agent-bus.js | 90 | Communication inter-agents |
| alert-manager.js | 120 | Alertes filtrées |
| utils/audit-helper.js | 20 | Localisation stack |

## Fichiers à Modifier Légèrement

| Fichier | Ajout | Raison |
|---------|-------|--------|
| server.js | 50 lignes | Intégrer 4 nouveaux modules |
| AGENTS_MONITOR.html | 300 lignes | Améliorer tabs + auto-refresh |
| public/background.js | 30 lignes | Alertes SSE subscription |

## Fichiers à Laisser Intact

✅ orchestrator.js (juste ajouter indicatorAgent en Promise.all)  
✅ Tous les agents existants  
✅ Routes 50+  
✅ MarketStore  
✅ Style d'appel async  
✅ studio/studioapp.js (utilise déjà /instant-trade-live)

---

# 🎯 RÉSULTAT FINAL

## Avant
```
- Orchestrator: 4 agents parallèles (fixe)
- Indicateurs: AUCUN, analyse seulement
- Surveillance: DÉSACTIVÉE (CPU)
- Communication: One-way broadcast
- Extension: Popup simple
- Dashboard: Statique
- Audit: Pas de localisation
```

## Après
```
- Orchestrator: 5 agents (+ indicatorAgent CRÉATEUR)
- Indicateurs: Générés dynamiquement par marché
- Surveillance: Event-driven temps réel
- Communication: Agent bus + messages
- Extension: Alertes intelligentes SSE
- Dashboard: Cockpit vivant 6 tabs
- Audit: Localisation file/line/function
- Mode: VIVANT, CONTINU, RÉACTIF
```

---

# 🚀 PROCHAINES ÉTAPES

1. ✅ **Approbation du plan**
2. 🔧 **Implémentation (6 modules + modifications mineures)**
   - agent-bus.js + intégration
   - indicatorAgent.js + Promise.all
   - surveillance-agent.js + MT5 event listener
   - alert-manager.js + SSE routes
   - AGENTS_MONITOR.html amélioration
   - Extension background.js modification

---

## ❓ QUESTIONS DE VALIDATION AVANT CODING

1. **indicatorAgent:** Génère dynamiquement? ✅ (OUI)
2. **Mode continu:** Event-driven? ✅ (OUI, pas de boucle infinie)
3. **Communication:** Via agent-bus? ✅ (OUI, middleware)
4. **Surveillance:** Basée sur prix OU temps? ✅ (OUI, les deux)
5. **Extension:** Alertes SSE? ✅ (OUI, push intelligentes)

---

**Approuves-tu ce plan FINAL révisé qui intègre indicatorAgent correctement?**
