# ANALYSE COMPLÈTE ET SYSTÉMATIQUE DE L'ARCHITECTURE TRADING

**Date:** 3 avril 2026  
**Statut:** Architecture RÉELLE explorée et documentée  
**Objectif:** Vision complète pour intégration sans cassures

---

## 1. STRUCTURE DU SERVEUR (server.js)

### 1.1 Démarrage et Initialisation

**Port:** `4000` (PORT constant, ligne 5)  
**Adresse:** `0.0.0.0` (toutes les interfaces)  
**Lancement:** Via `node server.js`

```javascript
// Ligne 5
const PORT = 4000;

// Ligne 2805
app.listen(PORT, '0.0.0.0', () => {
  console.log('Trading Auto Studio Pro @ ' + PORT);
});
```

**Middleware de démarrage (lignes 9-26):**
- CORS activé (Access-Control-Allow-Origin: *)
- JSON parsing limité à 50MB
- Express static pour `/public`
- Injection automatique du dev-helper dans toutes les pages HTML

### 1.2 Modules Chargés

**Tentative de chargement (lignes 46-57):**

```javascript
let marketStore, normalizeSymbol, orchestrator, auditLogger;
try {
  marketStore            = require('./store/market-store');
  normalizeSymbol        = require('./lib/symbol-normalizer').normalizeSymbol;
  orchestrator           = require('./src/agents/orchestrator');
  auditLogger            = require('./audit-logger');
}
```

**Comportement:** Fallbacks minimalistes si modules absents
- MarketStore → In-memory store avec bySymbol, analysisCache, sseClients
- normalizeSymbol → Conversion symbole brut → canonical (ex: XAU → XAUUSD)
- orchestrator → **NULL si erreur** (mode agent-less)
- auditLogger → Système de logging

### 1.3 Les Trois Routes HTML Principales

**Ligne 33-40:**

| Route | Fichier | Port | Usage |
|-------|---------|------|-------|
| `/` | index.html | 4000 | Menu principal |
| `/audit` | audit-dashboard.html | 4000 | Dashboard audit/logging |
| `/studio` | studio/index-simple.html | 4000 | Studio de trading |

Chaque page reçoit injection automatique `dev-helper.js` (ligne 30)

### 1.4 Système de Logging: pushLog() et sysLogs

**Structure en mémoire (ligne 1508):**
```javascript
const sysLogs = [];  // Tableau circulaire max 500 entrées
```

**Fonction pushLog (ligne 1557):**
```javascript
function pushLog(from, to, action, status, detail) {
  const entry = {
    id: Date.now(),
    ts: new Date().toISOString(),
    from: from || 'system',
    to: to || 'system',
    action: action || '',
    status: status || 'ok',  // 'ok' | 'error' | 'warning'
    detail: detail || ''
  };
  sysLogs.unshift(entry);  // Ajout en tête
  if (sysLogs.length > 500) sysLogs.pop();  // Rotation
  
  // Broadcast à tous les clients connectés
  try { marketStore.broadcast({ type: 'syslog', entry }); } catch (_) {}
  broadcastAgentActivity(entry);
  writeSysLog();  // Débounce 5 secondes
}
```

**Routes de consultation:**
- `GET /system-log` → Retourne `{agents: agentStates, logs: sysLogs[0:50]}`
- `POST /system-log` → Ajoute une entrée
- Débounce d'écriture disque toutes les 5 secondes (ligne 1519-1532)

### 1.5 Audit Logger Intégré

**Fichier:** `audit-logger.js`

**API routes (lignes 463-500):**

| Route | Méthode | Rôle |
|-------|---------|------|
| `/audit/state` | GET | État complet du système |
| `/audit/events` | GET | Événements récents (limit param) |
| `/audit/log` | POST | Logger événement manuel |
| `/audit/task/:taskId` | POST | Mettre à jour tâche |
| `/audit/task/:taskId/complete` | POST | Marquer complète |
| `/audit/task/:taskId/fail` | POST | Marquer en erreur |
| `/audit/error/:errorId` | POST | Ajouter/mettre à jour erreur |
| `/audit/error/:errorId/resolve` | POST | Résoudre erreur |
| `/audit/health` | GET | Scan système erreurs |

**Fichier persistant:** `audit.json` (chemin ligne audit-logger.js:12)

### 1.6 SSE (Server-Sent Events)

**Endpoint:** `GET /stream` (ligne 1029)

**Fonctionnement:**
```javascript
res.setHeader('Content-Type', 'text/event-stream');
res.setHeader('Cache-Control', 'no-cache');
res.setHeader('Connection', 'keep-alive');
res.setHeader('X-Accel-Buffering', 'no');
res.flushHeaders();

const hb = setInterval(() => {
  try { res.write(': heartbeat\n\n'); }  // Keep-alive toutes les 15s
  catch { /* client closed */ }
}, 15000);

marketStore.addSSEClient(res);  // Ajout à liste broadcast
res.on('close', () => clearInterval(hb));
```

**Broadcast automatique (marketStore.broadcast):**
- Nouveaux données MT5: `{type: 'mt5-raw', symbol, price, timeframe, source: 'mt5'}`
- Analyses: `{type: 'analysis', symbol, analysis}`
- Logs système: `{type: 'syslog', entry}`
- Modèles (quotes): `{type: 'quote', symbol, price, source}`

### 1.7 MarketStore: Source de Vérité

**Fichier:** `store/market-store.js`

**Singleton global:**
```javascript
// Ligne ~40
class MarketStore extends EventEmitter {
  constructor() {
    this.lastMT5Payload = null;       // Raw payload MT5
    this.bySymbol = {};               // {XAUUSD: {latestPayload, latestAnalysis, updatedAt}}
    this.sseClients = [];             // Response objects
    this.systemStatus = {source: 'offline', lastUpdate: null, fluxStatus: 'OFFLINE'};
    this.analysisCache = {};          // {XAUUSD: analysisResult}
  }

  updateFromMT5(payload, normalizedSymbol) {
    this.lastMT5Payload = {...payload, receivedAt: Date.now()};
    this.bySymbol[sym].latestPayload = this.lastMT5Payload;
    this.bySymbol[sym].updatedAt = Date.now();
    this.systemStatus = {source: 'mt5', lastUpdate: new Date().toISOString(), fluxStatus: 'LIVE'};
    this.emit('mt5-update', sym, payload);
  }

  updateAnalysis(symbol, analysis) {
    this.analysisCache[symbol] = {...analysis, computedAt: Date.now()};
    this.broadcast({type: 'analysis', symbol, analysis});
  }

  broadcast(data) {
    const msg = `data: ${JSON.stringify(data)}\n\n`;
    this.sseClients.forEach(res => {
      try { res.write(msg); } catch { /* closed */ }
    });
  }
}
```

---

## 2. ORCHESTRATION DES AGENTS (orchestrator.js)

**Fichier:** `src/agents/orchestrator.js`

### 2.1 Fonction d'Entry Point: run()

**Signature (lignes 9-15):**
```javascript
async function run(mt5Payload) {
  const startMs = Date.now();
  const raw = mt5Payload;
  
  // 1. Normaliser symbole
  // 2. Construire données MT5
  // 3. Construire multi-TF
  // 4. Lancer agents en parallèle
  // ...
}
```

### 2.2 Pipeline d'Exécution

**Étape 1 - Normalisation (lignes 19-20):**
```javascript
const profile = normalizeSymbol(raw.symbol || raw.broker_symbol || 'EURUSD');
const symbol = profile.canonical;
```

**Étape 2 - Extraction données courantes (lignes 23-31):**
```javascript
const currentTF = raw.timeframe || 'H1';
const price = parseFloat(raw.price || raw.bid || 0);
const bid = parseFloat(raw.bid || price);
const ask = parseFloat(raw.ask || price);

const currentTFData = {
  symbol, price, bid, ask, timeframe: currentTF,
  rsi: raw.rsi, ema20: raw.ema20, ema50: raw.ema50, ema200: raw.ema200,
  atr: raw.atr, ohlc: raw.ohlc || raw.bars || [], volume: raw.volume
};
```

**Étape 3 - Multi-TF (ligne 36):**
```javascript
const multiTF = raw.timeframes || {};
if (!multiTF[currentTF]) multiTF[currentTF] = currentTFData;
```

### 2.3 Agents Appelés EN PARALLÈLE

**Promise.all (lignes 40-45):**
```javascript
const [coreResult, consensus, fearData, newsData] = await Promise.all([
  tradingCore.analyze(currentTFData, profile),           // Analyse technique
  Promise.resolve(tfConsensus.buildConsensus(multiTF)), // Multi-TF sync
  fearIndex.getFearIndex(),                             // VIX/Peur
  newsIntelligence.analyze(symbol)                      // Macro/News
]);
```

**Agents réellement appelés:**
1. **tradingCore** - Analyse technique (RSI, EMA, structure, FVG, liquidité)
2. **tfConsensus** - Consensus multi-timeframe avec poids hiérarchiques
3. **fearIndex** - VIX, peur du marché
4. **newsIntelligence** - Événements macro, sentiment

### 2.4 Assemblage Résultat Final

**Étape 4 - Market State (lignes 48-56):**
```javascript
const mState = marketState.assess({
  atr: currentTFData.atr,
  atrAvg: raw.atrAvg,
  spread: ask - bid,
  price,
  rsi: currentTFData.rsi
});
```

**Étape 5 - Trade Logic (lignes 59-71):**
```javascript
const logic = tradeLogic.explain({
  symbol, profile, direction: coreResult.direction, score: coreResult.score,
  levels: coreResult.levels, rsi: coreResult.rsi, ema: coreResult.ema,
  structure: coreResult.structure, fvgs: coreResult.fvgs,
  liquidity: coreResult.liquidity, consensus, marketState: mState, news: newsData
});
```

**Étape 6 - Décision Final (lignes 74-76):**
```javascript
const finalDirection = consensus.conflict ? 'ATTENDRE' : 
  (consensus.decision !== 'ATTENDRE' ? consensus.decision : coreResult.direction);
const finalScore = Math.round((coreResult.score || 60) * 0.6 + 
  (consensus.strength === 'FORT' ? 40 : consensus.strength === 'MODERE' ? 25 : 10));
```

### 2.5 Objet Retourné

**Structure (lignes 78-114):**
```javascript
{
  ok: true,
  orchestrator: true,
  symbol: "XAUUSD",
  brokerSymbol: "GOLD",
  assetType: "metal",
  timeframe: "H1",
  price: 2412.50,
  bid, ask, spread,
  direction: "LONG",        // ou SHORT ou ATTENDRE
  score: 75,                // 0-100
  strength: "FORT",         // ou MODERE ou FAIBLE
  trade: {                  // Objet complet seulement si direction !== ATTENDRE
    symbol, direction, entry, sl, tp, score, risk, technical, macro, sentiment,
    explanation, source, accuracy
  },
  agents: {
    tradingCore: coreResult,
    consensus: consensus,
    marketState: mState,
    news: newsData,
    fear: fearData,
    tradeLogic: logic
  },
  computedInMs: 42          // Temps d'exécution
}
```

### 2.6 Appel depuis server.js

**Ligne 818-825 (POST /mt5):**
```javascript
if (orchestrator) {
  orchestrator.run({ ...payload, symbol: canonical, broker_symbol: payload.symbol })
    .then(analysis => {
      marketStore.updateAnalysis(canonical, analysis);
      console.log(`[ORCH] ${canonical} → ${analysis.direction} score=${analysis.score}`);
    })
    .catch(e => console.error('[ORCH ERROR]', e.message));
}
```

**Comportement:** Asynchrone non-bloquant, le serveur répond immédiatement POST /mt5

---

## 3. ROUTES EXISTANTES

### 3.1 Routes Métier (Analyse & Trading)

| Route | Méthode | Paramètres | Responsabilité |
|-------|---------|-----------|-----------------|
| `/instant-trade-live` | GET | symbol, tf, mode | Ligne 1100 - Signal LIVE avec 4 niveaux de fallback |
| `/analyze` | GET | focus (symbol optionnel) | Ligne 1445 - Scan opportunités |
| `/positions` | GET | — | Ligne 1429 - État des positions |
| `/trade` | POST | symbol, direction, qty, price, sl, tp | Ligne 1418 - Exécute ordre |
| `/agents-report` | GET | — | Ligne 1411 - Rapport agents complet |
| `/agent-screen` | POST | symbol, tf, price, url, title, screenshot | Ligne 1476 - Analyse screenshot |
| `/market-intelligence` | GET | symbol (default XAUUSD) | Ligne 1373 - Events macro + sentiment |
| `/chart-data` | GET | symbol, timeframe | Ligne 1364 - Timer bougie + prix live |

### 3.2 Routes MT5/Données

| Route | Méthode | Responsabilité |
|-------|---------|-----------------|
| `POST /mt5` | POST | Reçoit payload MT5, update marketStore, lance orchestrator |
| `POST /tv-bridge` | POST | Alternative TradingView si MT5 offline |
| `GET /mt5/status` | GET | Vérifie connexion MT5 (polling désactivé) |
| `GET /mt5/latest` | GET | Dernier snapshot MT5 complet |
| `GET /mt5/symbol/:symbol` | GET | Infos détaillées symbole |
| `GET /mt5/symbols` | GET | Liste symboles reçus |
| `GET /mt5/current-chart` | GET | Symbole + rates du TF actif |
| `GET /mt5/price` | GET | Prix d'un symbole (MT5 → fallback fixture) |
| `GET /mt5/klines` | GET | Historique candles (Yahoo Finance) |
| `GET /mt5/mappings` | GET | Mappings savegaré de symboles |
| `POST /mt5/mappings` | POST | Ajouter mapping |

### 3.3 Routes SSE & Broadcasting

| Route | Type | Responsabilité |
|-------|------|-----------------|
| `GET /stream` | SSE | Broadcast market data temps réel |
| `GET /agent-activity` | SSE | Broadcast agent logs (sysLogs) |
| `GET /state` | GET | État snapshot marketStore |

### 3.4 Routes de Configuration & Mode

| Route | Méthode | Responsabilité |
|-------|---------|-----------------|
| `GET /active-symbol` | GET | Récupère symbole actif frontend |
| `POST /active-symbol` | POST | Définit symbole actif (sync TradingView ↔ Studio) |
| `GET /toggle-mode` | GET | Récupère mode (auto/manual) |
| `POST /toggle-mode` | POST | Bascule mode ou TF |
| `GET /broker-mode` | GET | Mode paper/live (env var) |
| `POST /broker-mode` | POST | Bascule broker mode |
| `POST /zones` | POST | Créer supply/demand zone |
| `GET /zones/:symbol` | GET | Récupérer zones actives |

### 3.5 Routes de Mapping Symboles

| Route | Méthode | Responsabilité |
|-------|---------|-----------------|
| `POST /match-symbol` | POST | Validation symbole avec prix |
| `GET /match-symbol/:tvSymbol` | GET | Recherche symbole MT5 depuis TradingView |
| `POST /mapping/resolve` | POST | Recherche intelligente MT5 par score |
| `POST /mapping/save` | POST | Sauvegarde mapping TVsym → MT5sym |
| `GET /mapping/list` | GET | Liste des mappings enregistrés |

### 3.6 Routes Calendrier & News

| Route | Méthode | Responsabilité |
|-------|---------|-----------------|
| `GET /economic-events` | GET | Fixture: NFP, CPI, ECB, BOE... (fixe pour test) |
| `GET /calendar` | GET | Calendrier macro compact |
| `GET /news` | GET | News CoinGecko (crypto) ou fixture |
| `GET /quote` | GET | Prix symbole (MT5 → Yahoo → fixture) |
| `GET /klines` | GET | Historique bougie Yahoo (max 200) |
| `GET /latest/:symbol` | GET | Prix + source (MT5 → Yahoo) |

### 3.7 Routes Audit & Logging

| Route | Méthode | Responsabilité | Largeur |
|-------|---------|-----------------|---------|
| `GET /system-log` | GET | 50 logs + agent states | Syslog |
| `POST /system-log` | POST | Ajouter entry | Syslog |
| `GET /button-log` | GET | Historique boutons UI | 100 entries |
| `POST /button-log` | POST | Ajouter log bouton | 200 max |
| `GET /agent-bus` | GET | Coordination multi-IA (AGENT_BUS.json) | JSON |
| `GET /tasks` | GET | Tasks.json | Coordination Claude |
| `POST /tasks/update` | POST | Mettre à jour tâche | Coordination |
| `GET /logs` | GET | Logs.json | Coordination |
| `POST /logs` | POST | Ajouter log | Coordination |
| `/agent-status` | GET | États agents actuels | Agent tracking |
| `GET /ai-repair-request` | GET | Statut repair request UUID | Repair system |
| `POST /ai-repair-request` | POST | Créer repair request | Repair system |
| `GET /ai-repair-request/:id` | GET | Récupère repair request | Repair system |

### 3.8 Routes HTML

| Route | Fichier | Type |
|-------|---------|------|
| `/` | index.html | Page principale |
| `/audit` | audit-dashboard.html | Dashboard audit |
| `/studio` | studio/index-simple.html | Studio trading |
| `/studio/*` | studio/*.{js,css} | Assets studio |

---

## 4. FLUX DE DONNÉES ACTUELS

### 4.1 Chaîne Complète MT5 → Signal Trading

```
┌─────────────────┐
│  MT5 EA Bridge  │ (External, port 5000 Python via bridge)
│  (real data)    │
└────────┬────────┘
         │
         │ POST /mt5 payload JSON
         │ {symbol, price, bid, ask, timeframe, rsi, ema20, ema50, ema200,
         │  atr, ohlc[], volume}
         │
         ▼
┌─────────────────────────────────────┐
│  server.js POST /mt5               │
│  1. normalizeSymbol → XAUUSD       │
│  2. marketStore.updateFromMT5()    │
│  3. marketStore.broadcast() → SSE  │──────┐
│  4. orchestrator.run() async       │      │
└────────┬────────────────────────────┘      │ (Real-time to /stream clients)
         │                                   │
         ▼                                   │
┌────────────────────────────┐              │
│ orchestrator.run()         │              │
│ - tradingCore.analyze()    │              │
│ - tfConsensus.build()      │              │
│ - fearIndex.getFearIndex() │              │
│ - newsIntelligence        │              │
│ - marketState.assess()     │              │
│ - tradeLogic.explain()     │              │
│                            │              │
│ → Décision final           │              │
│   direction + score        │              │
└────────┬───────────────────┘              │
         │                                   │
         ▼                                   │
┌─────────────────────────────┐             │
│ marketStore.updateAnalysis()│             │
│ analysisCache[XAUUSD] = ..  │             │
│ broadcast({type: analysis})─┼─────────────┘
└─────────┬───────────────────┘
          │
          ├─→ /stream clients (SSE)
          ├─→ AGENTS_MONITOR.html (WebSocket simulation)
          └─→ studio/studioapp.js cached response
```

### 4.2 Client Accès au Signal

**Option 1: Polling HTTP**
```
GET /instant-trade-live?symbol=XAUUSD&tf=H1&mode=SNIPER
  → Priorité:
    1. Cache analysisCache < 30s
    2. MT5Raw (rsi → direction)
    3. TradingView data
    4. Yahoo Finance
    5. Fixture prices
```

**Option 2: Real-time SSE /stream**
```
GET /stream (connect)
↓ reçoit:
{type: 'mt5-raw', symbol: 'XAUUSD', price: 2412, ...}
{type: 'analysis', symbol: 'XAUUSD', analysis: {...}}
(heartbeat toutes 15s)
```

### 4.3 Archival Signaux

**Destination:** `sysLogs[]` array en mémoire (max 500)

**Middleware auto-log (lignes 1088-1097):**
```javascript
app.use('/instant-trade-live', (req, res, next) => {
  const origJson = res.json.bind(res);
  res.json = function(data) {
    if (data && data.ok && data.trade) {
      const tr = data.trade;
      pushLog(
        'technicalAgent', 'orchestrator',
        `SIGNAL ${tr.direction} · ${tr.symbol} @ ${tr.entry}`,
        'ok',
        `Score:${tr.score} · ${tr.setup_type} · SL:${tr.sl} TP:${tr.tp} · src:${data.source}`
      );
    }
    return origJson(data);
  };
  next();
});
```

---

## 5. SYSTÈME D'AUDIT & LOGGING

### 5.1 Trois Niveaux de Logs

| Nom | Fichier | Lieu | Capacité | Persistence |
|-----|---------|------|----------|-------------|
| **sysLogs** | server.js | Mémoire array | 500 max | Débounce SYSTEM_LOG.json |
| **AuditLogger** | audit-logger.js | Mémoire + audit.json | Illimité | Instantané |
| **btnLogs** | server.js | Mémoire array | 200 max | En mémoire seulement |

### 5.2 Structure sysLogs Entry

```javascript
{
  id: Date.now(),
  ts: "2026-04-03T14:23:45.123Z",
  from: "technicalAgent",
  to: "orchestrator",
  action: "SIGNAL LONG · XAUUSD @ 2412.50",
  status: "ok",  // ou "error"
  detail: "Score:75 · SNIPER · SL:2410.23 TP:2414.77 · src:mt5-cached"
}
```

### 5.3 pushLog() Flow

```javascript
pushLog(from, to, action, status, detail)
  ↓
  1. Créer entry
  2. sysLogs.unshift() → En tête
  3. updateAgentState() → Marquer agent comme working
  4. marketStore.broadcast({type: 'syslog', entry}) → SSE /stream
  5. broadcastAgentActivity(entry) → SSE /agent-activity
  6. writeSysLog() → Débounce 5s vers SYSTEM_LOG.json
  ↓
Retour via:
  - GET /system-log (50 derniers)
  - SSE /agent-activity (real-time)
  - SYSTEM_LOG.json (fichier persistant)
```

### 5.4 broadcastAgentActivity()

**Fonction (lignes 1547-1559):**
```javascript
function broadcastAgentActivity(entry) {
  if (agentActivitySseClients.length === 0) return;
  const message = 'data: ' + JSON.stringify(entry) + '\n\n';
  for (let i = agentActivitySseClients.length - 1; i >= 0; i--) {
    try {
      agentActivitySseClients[i].write(message);  // Push à client
    } catch (e) {
      agentActivitySseClients.splice(i, 1);  // Nettoyer client fermé
    }
  }
}
```

### 5.5 Agent State Tracking

**Objet global agentStates (ligne 1540):**
```javascript
{
  'Claude': { status: 'online', lastActivity: Date.now(), activeTask: null },
  'Copilot': { status: 'idle', lastActivity: Date.now(), activeTask: null },
  'system': { status: 'running', lastActivity: Date.now(), activeTask: null }
}
```

**Mise à jour auto (ligne 1563-1567):**
```javascript
if (from && from !== 'system') {
  const agentStatus = (status === 'error') ? 'error' : 'working';
  updateAgentState(from, agentStatus, action);
  setTimeout(() => {
    if (agentStates[from]) agentStates[from].status = 'idle';  // Reset après 3s
  }, 3000);
}
```

---

## 6. DASHBOARDS EXISTANTS

### 6.1 AGENTS_MONITOR.html

**Fichier racine:** `AGENTS_MONITOR.html`

**Connexion:**
```javascript
// Simule SSE avec polling toutes les 2-3 secondes
fetch('http://127.0.0.1:4000/agent-status')
  .then(r => r.json())
  .then(data => {
    // Affiche agents avec status (online/idle/error/unknown)
    // Affiche lastActivity timestamp
  })
```

**Relit également:**
- `GET /agent-activity` (SSE) - Real-time logs
- `GET /system-log` (polling) - Historical logs

**Visuals:**
- 3-column layout: status icons (pulse animations)
- Agent cards avec timestamp
- Log feed scrollable

### 6.2 audit-dashboard.html

**Route:** `GET /audit`

**Connexion:**
```javascript
GET /audit/state      // État complet (tasks, errors, events)
GET /audit/events     // Événements récents
GET /audit/health     // Scan erreurs système
```

**Structures affichées:**
- Task status (not-started, in_progress, done, error)
- Error list avec resolution
- File audit
- Connection status

### 6.3 studio/index-simple.html (PRINCIPAL)

**Route:** `GET /studio` ou `/studio/index.html`

**Pattern:** SPA (Single Page Application)

**Code:** `studio/studioapp.js` (1700+ lignes)

**Fonctionnalités:**
1. **Sélecteur symbole** et timeframe
2. **Mode booton:** SCALPER / SNIPER / SWING
3. **Broker toggle:** Paper ↔ Live
4. **State persisté** dans localStorage
5. **Boutons actions:**
   - Get Positions
   - Analyze Market
   - Instant Trade
   - Capture Screen
   - Execute Trade
   - Test System
6. **Affichages live:**
   - Chart (Lightweight Charts lib)
   - Positions actuelles
   - Agent reports
   - Logs
   - Détails setup

**API utilisée:**
```javascript
GET /instant-trade-live?symbol=${sym}&tf=${tf}&mode=${mode}
GET /positions
GET /analyze?focus=${symbol}
POST /agent-screen (+ screenshot)
GET /chart-data?symbol=${sym}&timeframe=${tf}
POST /active-symbol (sync pour extension)
```

### 6.4 Affichages Réels vs Fallback

**Si MT5 connecté:**
```
studio → GET /instant-trade-live → POST /mt5 → orchestrator.run() → analyse complète
```

**Si MT5 offline:**
```
studio → GET /instant-trade-live → Yahoo Finance klines → niveaux ATR → affichage référence
```

---

## 7. EXTENSION CHROME (public/)

**Manifest:** `public/manifest.json`

### 7.1 Fichiers de l'extension

| Fichier | Rôle | Port |
|---------|------|------|
| background.js | Service Worker - écoute messages | — |
| content.js | Injecté dans TradingView | webSocket vers host |
| popup.js | Popup extension | Communique avec background |
| popup.html | UI popup | Affiche signaux |
| manifest.json | Config extension | v3 |

### 7.2 Background.js Auto-Mode (Désactivé pour Perf)

**Code (lignes 1-40 public/background.js):**
```javascript
let autoMode = false;

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "START_AUTO") {
    if (!autoMode) {
      autoMode = true;
      autoLoop();  // DÉSACTIVÉ — Cause CPU 100%
    }
  }
  if (message.type === "STOP_AUTO") {
    autoMode = false;
  }
});

async function autoLoop() {
  if (!autoMode) return;
  console.log('[BG] Auto-loop mode DISABLED for safety');
  // while(autoMode) { fetch() } ← ANCIEN CODE causant spike CPU
  return { disabled: true, reason: 'While loop caused CPU 100%' };
}
```

**Comportement:**
- Mode SAFE: images envoyées MANUELLEMENT via bouton
- Mode AUTO (réactivable): intervalle contrôlé > 10s minimum

### 7.3 Flux Communication

```
┌──────────────────┐
│  TradingView     │
│  (content.js)    │
└────────┬─────────┘
         │
         │ chrome.runtime.sendMessage
         │ {type: 'tv-symbol-detected', symbol, price, timeframe}
         │
         ▼
┌──────────────────┐
│  background.js   │
│  (Service Worker)│
└────────┬─────────┘
         │
         │ fetch POST to localhost:4000
         │ /tv-bridge or /match-symbol
         │
         ▼
┌──────────────────┐
│  server.js       │
│  (Node 4000)     │
└────────┬─────────┘
         │
         │ Analyse via orchestrator
         │ Response: {symbol, direction, levels}
         │
         ▼
┌──────────────────┐
│  popup.js        │
│  (Affiche signal)│
└──────────────────┘
```

### 7.4 showSignal() Display

**Couleurs et textes (lignes 50+ background.js):**
- LONG: 🟢 Vert, "SIGNAL LONG"
- SHORT: 🔴 Rouge, "SIGNAL SHORT"
- NEUTRAL: ⚫ Gris, "ATTENDRE"

---

## 8. AGENTS ACTUELLEMENT DANS LE SYSTÈME

**Fichiers:** `src/agents/*.js` (23 fichiers)

### 8.1 Agents RÉELLEMENT APPELÉS par Orchestrator

**Promise.all dans orchestrator.run() (lignes 40-45):**

| Agent | Fichier | Utilisé? | Rôle |
|-------|---------|----------|------|
| **tradingCore** | trading-core.js | ✅ OUI | Analyse technique (RSI/EMA/structure/FVG) |
| **tfConsensus** | timeframe-consensus.js | ✅ OUI | Multi-TF vote hiérarchique |
| **fearIndex** | fear-index.js | ✅ OUI | VIX, peur du marché |
| **newsIntelligence** | news-intelligence.js | ✅ OUI | Macro calendar, sentiment |

### 8.2 Agents ACTUELLEMENT IMPORTÉS dans server.js

**Middleware route /agents-report (ligne 1411):**
```javascript
const coordinator = require('./src/agents/coordinator');
const report = await coordinator.runAgentCycle(priceMap, 100000, 1);
```

### 8.3 Autres Agents Disponibles (OPTIONNELS, pas appelés en boucle)

| Agent | Fichier | Export | Usage |
|-------|---------|--------|-------|
| technicalAgent | technicalAgent.js | analyzeTechnical, analyzeFromMT5 | Fallback si tradingCore fail |
| macroAgent | macroAgent.js | getEconomicCalendar, analyzeEconomicImpact | Optionnel |
| marketState | market-state.js | assess() | Appelé dans orchestrator |
| dataSourceManager | dataSourceManager.js | fetchPrice, validatePrice | Optionnel |
| syncManager | syncManager.js | validateSync | Optionnel |
| riskManager | riskManager.js | calculatePositionSize, validateRisk | Optionnel |
| setupClassifier | setupClassifier.js | classifySetup | Optionnel |
| strategyManager | strategyManager.js | selectStrategy | Optionnel |
| stateManager | stateManager.js | getState, setState | Optionnel |
| supervisor | supervisor.js | runCycle | Optionnel |
| tradeValidator | tradeValidator.js | validateTrade | Appelé dans server.js |
| designerAgent | designerAgent.js | analyzeChartSetup | Optionnel |
| chartEngine | chartEngine.js | buildChart | Optionnel |
| continuous-loop | continuous-loop.js | orchestrationCycle | DÉSACTIVÉ (mode SAFE) |
| coordinator | coordinator.js | runAgentCycle | Optionnel (/agents-report) |
| qaTester | qaTester.js | runTests | Test automation |
| sessionManager/tradeLogic/etc | — | — | Modules support |

### 8.4 Agents JAMAIS APPELÉS dans la boucle normale

- technicalAgent (remplacé par tradingCore)
- macroAgent (remplacé par newsIntelligence)
- Tous les orchestration agents (optionnels)

### 8.5 Classification des Agents

**CORE (Must Have):**
- orchestrator
- tradingCore
- timeframe-consensus
- newsIntelligence
- fearIndex
- marketState

**OPTIONNEL (Nice to Have):**
- Tous les autres agents

**DÉSACTIVÉ (Safety):**
- continuous-loop (cause CPU spike)

---

## 9. MODES EXISTANTS

### 9.1 Engine Mode (SAFE par défaut)

**Variable (ligne 1378):**
```javascript
let engineMode = 'manual';  // ou 'auto'
```

**Routes:**
```javascript
GET /toggle-mode → {mode: 'manual'|'auto', timeframe: 'H1'}
POST /toggle-mode {mode?, timeframe?} → Update
```

**Comportement:**
- **manual:** Utilisateur décide quand analyser (via boutons UI)
- **auto:** Pas implémenté (continuous-loop disabled)

### 9.2 Broker Mode (PAPER par défaut)

**Variable (process.env.BROKER_MODE):**
```javascript
GET /broker-mode → {mode: 'paper'|'live'}
POST /broker-mode {mode: 'paper'|'live'} → Update
```

### 9.3 Trade Mode (Selector Studio = SNIPER par défaut)

**Workflow:**
```
User selects → SCALPER | SNIPER | SWING
              ↓
GET /instant-trade-live?mode=SNIPER
              ↓
classifySetup(tf, direction, score, 'SNIPER')
              ↓
Returns: {setup_type: 'SNIPER', slMultiplier: 1.0, tpMultiplier: 0.8, ...}
```

### 9.4 Orchestration Cycle Manual vs Auto

**ANCIEN:** Boucle setInterval (DÉSACTIVÉE)
```javascript
// Ligne continuous-loop.js
// while(autoMode) { orchestrationCycle(); await sleep(30s); }
// ← Cause: CPU 100%, même quand pas de signal
```

**NOUVEAU:** Mode SAFE on-demand
```javascript
POST /agents/run-cycle?symbol=XAUUSD
  → orchestrationCycle() exécute une seule fois
  → Retourne résultat
  → Pas de boucle infinie
```

---

## 10. POINTS DE CONNEXION RÉELS

### 10.1 SSE Activée

**Endpoint:** `GET /stream` (ligne 1029)

**Clients connectés:** `marketStore.sseClients[]`

**Messages envoyés:**
- MT5 raw: `{type: 'mt5-raw', symbol, price, timeframe, source: 'mt5'}`
- Analysis: `{type: 'analysis', symbol, analysis}`
- Syslog: `{type: 'syslog', entry}`
- Quote: `{type: 'quote', symbol, price, source}`

**Hearbeat:** 15s ping-pong

### 10.2 Agent Activity SSE

**Endpoint:** `GET /agent-activity` (ligne 1689)

**Clients connectés:** `agentActivitySseClients[]`

**Messages envoyés:**
- Initial state: `{type: 'initial', agents: agentStates, logs: sysLogs[0:50]}`
- Real-time logs: `{...sysLogs entry}`
- Repair requests: `{type: 'repair_request', requestId, module, timestamp}`

**Hearbeat:** 15s ping-pong

### 10.3 WebSocket

**Statut:** ABSENT

N'existe pas. Toute communication est via HTTP polling ou SSE.

### 10.4 Broadcast vers Extension

**Pattern:**
```
1. Extension POST /tv-bridge {symbol, price, tf}
2. Server reçoit, lance orchestrator
3. Server répond directement à la requête
4. Extension affiche dans popup
```

**Pas de broadcast inverse** (serveur → extension)

### 10.5 Historique & Mémoire

**En mémoire:**
- sysLogs[500]
- agentStates{}
- marketStore.analysisCache{}
- marketStore.bySymbol{}

**Persistant:**
- SYSTEM_LOG.json (débounce 5s)
- audit.json (instantané)
- audit-logger eventLog

**Pas de base de données** - Tout fichier JSON ou mémoire

---

## 11. FLUX D'ERREURS

### 11.1 Escalade d'erreurs

```
try {
  POST /mt5 → normalizeSymbol() fail
} catch (err) {
  res.status(400).json({ok: false, error: err.message})
  pushLog('system', 'mt5-bridge', 'Error', 'error', err.message)
}
```

### 11.2 AI Repair System

**Routes (lignes 1638-1688):**

```javascript
POST /ai-repair-request {
  from: 'extension',
  to: 'ai-repair',
  action: 'REPAIR_REQUEST',
  module: 'orchestrator',
  context: {errors: [...], stack: ...}
}
  ↓
Retourne: {requestId: UUID, status: 'PENDING'}
  ↓
GET /ai-repair-request/:id
  ↓
Récupère: {id, timestamp, module, status}
```

**Stockage:** Mémoire `repairRequests{}`

**Broadcast:** `/agent-activity` SSE

---

## 12. PRIORISATION DES SOURCES

### 12.1 Prix

**Priorité (lignes 1100-1200: /instant-trade-live):**

```
1. analysisCache < 30 secondes   ← Utilise résultat orchestrator
2. MT5Raw (marketStore)           ← Prix brut MT5
3. TradingView data                ← Si MT5 obsolète
4. Yahoo Finance                   ← Finance historique
5. SYMBOL_PRICES[fixture]          ← Fallback durci
```

### 12.2 Signal Trading

**Source unique:** orchestrator.run() depuis POST /mt5

**Fallback:** Calcul manuel via calcTradeLevels() + fixure

### 12.3 Indicateurs

**Source:**
1. MT5 live (rsi, ema, atr)
2. Calcul depuis klines (tradingCore)
3. Zéro fake data (pas de Math.random())

---

## 13. ARCHITECTURE DE DÉPLOIEMENT

### 13.1 Ports

| Service | Port | Protocole | Notes |
|---------|------|-----------|-------|
| Node Studio | 4000 | HTTP/1.1, SSE | TRADING AUTO EXCLUSIVE |
| MT5 Bridge Python | 5000 | HTTP/1.1 | External, fallback |
| Project Bridge | 4001 | HTTP/1.1 | DEV HELPER read/write files |

### 13.2 Fichiers Critiques

| Fichier | Rôle | Update |
|---------|------|--------|
| SYSTEM_LOG.json | Logs système | Débounce 5s |
| audit.json | Audit complet | Instantané |
| AGENT_BUS.json | Coordination multi-IA | Lecture à la demande |
| tasks.json | Tasks Claude | Lecture/écriture POST |
| logs.json | Coordination logs | Lecture/écriture POST |
| market-store.js | mémoire | Volatile |

### 13.3 Dépendances Externes

**Requises:**
- Express.js (routing)
- Node.js (runtime)

**Optionn:**
- MT5 Bridge Python (prix live)
- Yahoo Finance API (fallback historique)
- CoinGecko API (news)
- TradingView extension (symboles)

---

## 14. INTÉGRATION SANS CASSURES - RÈGLES DE SÉCURITÉ

### 14.1 Points Critiques à NE PAS Toucher

1. **orchestrator.run()** - Pipeline multi-agents
2. **marketStore** - Singleton source de vérité
3. **pushLog()** - Logging system
4. **POST /mt5** - Récepteur données MT5
5. **SSE /stream** - Real-time broadcast

### 14.2 Points Sûrs pour Extension

1. Routes de lecture (`GET /...`)
2. Routes de configuration (`POST /toggle-mode`, `/active-symbol`)
3. Routes de logging (`POST /system-log`, `/button-log`)
4. Routes audit (`GET /audit/*`, `POST /audit/*`)
5. Routes agents optionnels

### 14.3 Fallbacks Existants

- MT5 offline → Yahoo Finance
- Yahoo offline → Fixture prices
- Orchestrator error → Raw levels calculation
- Missing agent → Default (NEUTRAL)

### 14.4 À Rajouter

**Bonnes pratiques:**
1. Versionner endpoints (`/v1/...`)
2. Rate limiting sur `/instant-trade-live`
3. Valider tous les inputs (symbol, tf, mode)
4. Capturer toutes les erreurs orchestrator
5. Audit trail pour toutes les orders

---

## RÉSUMÉ ARCHITECTURE RÉELLE

Nous avons une **stack minimaliste et cohérente:**

| Couche | Composant | Statut |
|--------|-----------|--------|
| **Frontend** | studio/*, public/* | ✅ Fonctionnel |
| **Backend** | Node 4000 | ✅ Core stable |
| **Orchestration** | orchestrator.js | ✅ Fonctionne |
| **Data** | marketStore + files | ✅ Persistant |
| **Logging** | sysLogs + audit.json | ✅ Actif |
| **Real-time** | SSE /stream | ✅ Broadcast |
| **Extension** | Chrome public/* | ⚠️ Mode SAFE |
| **Loop Continue** | continuous-loop | ❌ DÉSACTIVÉE |
| **WebSocket** | — | ❌ Absent |

**La clé:** Tout passe par POST /mt5 → orchestrator → SSE broadcast. Rien d'autre n'est réellement lié.

