# VALIDATION FINALE AVANT CODING

**Date:** 3 avril 2026  
**Statut:** Logique verrouillée, prêt exécution  
**Approche:** Audit → Réutiliser → Enrichir → Créer

---

# A. FICHIERS À ENRICHIR (FINAL — 6 fichiers)

## 1. audit-logger.js (+20 lignes)
**Raison:** Existe, branche, audit.json centralisé  
**Ajout:** getCallerLocation() pour localisation stack trace  
**Où:** Ajouter helper + enrichir logEvent()  
**Impact:** Chaque log audit = {file, function, line, sourceUrl}

## 2. AGENTS_MONITOR.html (+350 lignes)
**Raison:** Existe (3 cards basiques)  
**Ajout:** 6 onglets (Agents | Pipeline | Signaux | Alertes | Indicateurs | Audit)  
**Où:** Ajouter structure HTML + CSS + scripts auto-refresh  
**Impact:** Dashboard = centre de contrôle du système

## 3. studio/index-simple.html (+100 lignes)
**Raison:** Existe (trading UI complète)  
**Ajout:** Section "Mes Préférences" (symboles surveillés, timeframe, risk level)  
**Où:** Sidebar, après buttons existants  
**Impact:** Alertes = filtrées par MES choix

## 4. public/background.js (+50 lignes)
**Raison:** Existe (showSignal basique)  
**Ajout:** subscribeToAlerts() SSE listener + chrome.notifications  
**Où:** Après autoLoop() function  
**Impact:** Extension = récepteur alertes intelligentes

## 5. orchestrator.js (+5 lignes logiques)
**Raison:** Existe (Promise.all 4 agents)  
**Ajout:** indicatorAgent dans Promise.all + fusionner résultat  
**Où:** Ligne 40-45, puis résultat final  
**Impact:** Orchestrator = 5 agents, indicateurs intégrés

## 6. server.js (+80 lignes chirurgicales)
**Raison:** Existe (2800+ lignes, 50+ routes)  
**Ajout:** Requires nouveaux modules + agent registration + routes alertes/surveillance + broadcasting  
**Où:** Ligne ~47 (requires), ~55 (init), ~500 (routes), ~820 (broadcast)  
**Impact:** Server = hub d'intégration

---

# B. FICHIERS À CRÉER (FINAL — 4 fichiers)

## 1. agent-bus.js (100 lignes)
**Raison:** AUCUN équivalent dans l'architecture  
**Justification:** Besoin d'un registre agents + queue messages  
  - audit-logger.js = audit events (tasks, errors, endpoints)
  - agent-bus.js = agent communications (from → to messages)
  - Ce sont 2 concepts distincts
**Responsabilité:**
  - registerAgent(name, metadata)
  - sendMessage(from, to, message)
  - subscribe() / getMessages()
  - Accessible via GET /agents-bus
**Ne peut pas aller dans:** server.js (trop important comme module), audit-logger.js (concepts différents)

## 2. src/agents/surveillance-agent.js (50 lignes)
**Raison:** continuous-loop.js EXISTE mais DISABLED (CPU 100%)  
**Justification:** Besoin d'une surveillance event-driven propre
  - continuous-loop.js = boucle while infinie (dangereux, désactivé)
  - surveillance-agent.js = event-driven (prix >0.5% OU temps)
  - Impossible d'enrichir continuous-loop, faut le remplacer intelligemment
**Responsabilité:**
  - onMT5Update(symbol, payload) → déclenche si conditions
  - addMonitored(symbol) / removeMonitored(symbol)
  - emit('trigger-analysis') events
  - Mode continu SANS CPU spike
**Ne peut pas aller dans:** continuous-loop.js (incompatible), server.js (trop spécialisé)

## 3. alert-manager.js (120 lignes)
**Raison:** AUCUN système d'alertes centralisé n'existe  
**Justification:** Besoin de centralisation + filtrage par préférences utilisateur
  - audit-logger = logs/events (historique technique)
  - alert-manager = alertes commerciales (notifications utilisateur)
  - Ce sont 2 concepts distincts (technique vs UX)
**Responsabilité:**
  - createAlert(source, data) → crée une alerte
  - shouldNotify(alert, userFilters) → filtre intelligent
  - addSubscriber(res, filters) → SSE endpoint pour extension
  - getAlerts() → historique
**Ne peut pas aller dans:** server.js (trop importante), audit-logger.js (concepts différents)

## 4. src/agents/indicator-agent.js (200 lignes)
**Raison:** AUCUN agent créateur d'indicateurs n'existe  
**Justification:** Besoin d'un agent MT5-spécialisé
  - Autres agents = analysent (tradingCore, technicalAgent, macroAgent)
  - indicatorAgent = GÉNÈRE (crée, propose, produit MQL5)
  - Concept distinct = agent créatif, pas analytique
**Responsabilité:**
  - generateIndicators(symbol, timeframe, marketCondition)
  - Produit {indicators[], aggregateSignal, mql5Code}
  - S'intègre en Promise.all orchestrator
  - Remonte au dashboard + extension
**Ne peut pas aller dans:** Autres agents (pas leur rôle)

---

# C. JUSTIFICATION DÉTAILLÉE CHAQUE CRÉATION

### 1. agent-bus.js — Pourquoi pas dans server.js?
```
server.js = 2800+ lignes c'est déjà ÉNORME
agent-bus = module réutilisable, logique propre
Créer un module = meilleure maintenabilité + testable séparément
```

### 2. surveillance-agent.js — Pourquoi pas enrichir continuous-loop.js?
```
continuous-loop = WHILE boucle infinie avec sleep()
surveillance-agent = EventEmitter avec triggers intelligents
INCOMPATIBLE architecturalement
Faut créer une nouvelle logique, pas corriger l'ancienne
```

### 3. alert-manager.js — Pourquoi pas dans server.js ou audit-logger.js?
```
server.js = integration hub (déjà +80 lignes de routes)
audit-logger = logging technique (timestamps, severities, files)
alert-manager = filtrage commercial (symbols, risk, timeframe)

Ce sont 2 responsabilités complètement différentes.
alert-manager = UX user
audit-logger = engineering technical
```

### 4. indicator-agent.js — Pourquoi pas enrichir technicalAgent.js?
```
technicalAgent = ANALYSE (RSI, EMA, structure)
indicatorAgent = CRÉE (générant nouveaux indicateurs)

Concepts différents:
- Analyser = utiliser des indicateurs existants
- Créer = produire de nouveaux indicateurs adaptés au marché
- Générer MQL5 = sortie spécifique MT5

Faut un agent séparé avec ce focus génération/création.
```

---

# D. PLACE EXACTE DE libraryAgent

## Rôle (Agent de Structure, pas métier)
**libraryAgent = validateur, référence, anti-doublon**

Ne doit PAS:
- ❌ Analyser le marché
- ❌ Créer de trades
- ❌ Interagir avec MT5
- ❌ Prendre des décisions métier

Doit:
- ✅ Connaître l'architecture complète
- ✅ Référencer tous les modules/agents/routes
- ✅ Répondre: "ça existe déjà?"
- ✅ Suggérer: "c'est mieux de compléter X que créer Y"
- ✅ Maintenir une "bibliothèque logique" du système

## Implémentation

**Pas un agent Node.js ordinaire**

Au lieu de:
```javascript
libraryAgent.analyze(data) ← berk
```

libraryAgent = document/référence technique:
```
- Structure JSON: {modules: {}, agents: {}, routes: {}, endpoints: {}}
- Consulté avant CHAQUE création/modification
- Maintenu manuellement (ou via script de scan)
- Accessible via GET /library/schema
```

## Où le placer dans l'architecture

**Option 1: library.json (RECOMMANDÉ)**
```
Racine du projet
library.json = catalogue complet
├─ modules: {...}
├─ agents: {...}
├─ routes: {...}
├─ endpoints: {...}
└─ metadata
```

**Option 2: library-agent.js (Module)**
```
src/library-agent.js
Classe avec méthodes:
- getModule(name)
- hasRoute(path)
- findDuplicate(concept)
- suggestBestPlace(feature)
```

**Choice:** Option 1 + Route GET /library → retourne library.json

## Intégration dans le workflow

**AVANT chaque création/modification:**
1. Consulter GET /library
2. Chercher le concept dans library.json
3. Si existe → enrichir ce qui existe
4. Si n'existe pas → créer en nouveau endroit
5. APRÈS création/modification → mettre à jour library.json

## Contenu initial library.json

```json
{
  "version": "1.0",
  "lastUpdated": "2026-04-03T10:30:00Z",
  
  "modules": {
    "orchestrator": {
      "file": "src/agents/orchestrator.js",
      "role": "Master coordinator",
      "calls": ["tradingCore", "tfConsensus", "fearIndex", "newsIntelligence"],
      "complete": true
    },
    // ...
  },
  
  "agents": {
    "tradingCore": {
      "file": "src/agents/trading-core.js",
      "type": "analyzer",
      "role": "Technical structure analysis",
      "inputs": ["MT5 data"],
      "outputs": ["direction", "score"],
      "active": true
    },
    // ... 12 agents total
  },
  
  "routes": {
    "GET /state": {
      "file": "server.js",
      "line": "...",
      "role": "System state",
      "returns": "marketStore state"
    },
    // ... 50+ routes
  },
  
  "data": {
    "audit.json": {
      "role": "Central audit log",
      "managed_by": "audit-logger.js",
      "fields": ["tasks", "errors", "endpoints", "connections"]
    }
    // ...
  }
}
```

---

# E. ORDRE FINAL D'IMPLÉMENTATION (EXACT & SÛR)

## Phase 0 — Setup libraryAgent (Fondation)
**1. Créer library.json** (au-dessous de la racine, next to server.js)
   - Contient l'inventaire complet
   - Sera source de vérité pour toute création future
   - Permet `GET /library` pour consultation
   - **Test:** GET /library retourne le JSON

## Phase 1 — Modules indépendants (0 dépendance)
**2. Créer agent-bus.js**
   - Module standalone
   - Pas besoin d'autres modules
   - Ne modifie rien existant
   - **Test:** require('./agent-bus') sans erreur

**3. Créer alert-manager.js**
   - Module standalone
   - Pas besoin d'autres modules
   - **Test:** require('./alert-manager') sans erreur

**4. Créer src/agents/surveillance-agent.js**
   - Module standalone (extends EventEmitter)
   - **Test:** require('./src/agents/surveillance-agent') sans erreur

## Phase 2 — Enrichissement technique (Audit)
**5. Modifier audit-logger.js**
   - Ajouter getCallerLocation()
   - Enrichir logEvent()
   - **Test:** POST /audit/log retourne {location: {file, function, line}}

## Phase 3 — Server intégration (Critique)
**6. Modifier server.js** (Ordre strict d'ajout):
   - a) Ligne ~47: Require agent-bus, surveillance-agent, alert-manager
   - b) Ligne ~55: Register agents via agentBus.registerAgent()
   - c) Ligne ~65: Setup surveillance + event listener
   - d) Ligne ~500: Ajouter 4 routes (/agents-bus, /alerts/subscribe, /alerts, /surveillance/*)
   - e) Ligne ~820: Broadcasting + alertManager.createAlert()
   - **Test:** `node server.js` démarre sans erreur, tous les /agents-bus, /alerts, /surveillance répondent

## Phase 4 — Orchestrator + Indicator (Métier)
**7. Créer src/agents/indicator-agent.js**
   - Après server.js marche sans erreur
   - **Test:** require('./src/agents/indicator-agent') sans erreur

**8. Modifier orchestrator.js**
   - Ajouter indicatorAgent en Promise.all
   - Fusionner résultat
   - **Test:** GET /instant-trade-live retourne agents.indicatorAgent

## Phase 5 — Dashboard central (UX)
**9. Modifier AGENTS_MONITOR.html**
   - Ajouter 6 onglets (HTML + CSS)
   - Ajouter auto-refresh scripts (fetch /agents-bus, /instant-trade-live, /alerts)
   - **Test:** http://localhost:4000/agents-monitor affiche 6 onglets, auto-refresh 2s

## Phase 6 — Studio (Utilisateur)
**10. Modifier studio/index-simple.html**
   - Ajouter section Mes Préférences
   - Checkboxes symboles + selects timeframe/risk
   - localStorage save
   - **Test:** Sauvegarder prefs, reload, persistent

## Phase 7 — Extension (Chrome)
**11. Modifier public/background.js**
   - Ajouter subscribeToAlerts()
   - EventSource listener
   - chrome.notifications.create()
   - **Test:** Extension reçoit SSE /alerts/subscribe, affiche notifications

## Phase 8 — Update library.json (Documentation)
**12. Update library.json** avec tous les changements
   - Ajouter nouveaux modules
   - Ajouter nouvelles routes
   - Ajouter nouveaux agents
   - **Test:** GET /library retourne structure à jour

---

# F. V1 MINIMALE BRANCHÉE SANS RISQUE

## Ce qui est livré en V1

```
✅ Surveillance event-driven (2 symboles monitored max)
✅ Alertes (10 max en queue à la fois)
✅ Dashboard 6 onglets (basique, pas graphiques)
✅ Extension notifications (texte simple)
✅ Indicateurs créés (3-4 basiques)
✅ Audit enrichi (localisation file/line/function)
✅ Prefs utilisateur (stockées localStorage)
✅ Agent bus (messages registrés)

ZÉRO breaking changes
ZÉRO modification signature API existante
ZÉRO risque de casser les flows actuels
```

## Architecture V1 Hub Central

```
MT5 → server.js
  ├─ marketStore.updateFromMT5()
  ├─ orchestrator.run() [4 agents parallèle + indicatorAgent]
  ├─ agentBus.sendMessage('orchestrator' → 'system')
  ├─ Si signal pertinent:
  │   └─ alertManager.createAlert()
  │       └─ SSE broadcast allClients
  │           └─ Extension reçoit (filtrée par prefs)
  │               └─ chrome.notifications.create()
  │               └─ Dashboard reçoit + affiche
  └─ audit-logger.logEvent() [avec localisation]

Dashboard = Centre
├─ Onglet Agents: GET /agents-bus en direct
├─ Onglet Alertes: GET /alerts historique
├─ Onglet Signaux: GET /instant-trade-live
├─ Onglet Audit: GET /audit/query avec localisation
└─ Onglet Prefs: Studio index-simple localStorage
```

## Garanties V1

- ✅ **Pas de modification orchestrator signature** (juste 1 ligne en Promise.all)
- ✅ **Pas de modification routes existantes** (juste ajouts ~80 lignes)
- ✅ **Pas de modification agents existants** (juste ajout 1 nouvel agent)
- ✅ **Pas de modification market-store** (juste utilisation)
- ✅ **Pas de modification HTML structure existante** (juste enrichissement)
- ✅ **Rollback facile** (chaque phase additive, testable séparément)

---

# G. LES 12 AGENTS DE TRADING (Utilité métier)

```
ANALYTIQUES (5):
  1. tradingCore ✅ — Structure, RSI, EMA, ATR, BOS
  2. technicalAgent — Alternative analyse technique
  3. macroAgent — Macro events, inflation, rates
  4. newsIntelligence ✅ — Economic calendar, sentiment
  5. indicatorAgent [NEW] — Crée indicateurs MT5

CONSENSUS (2):
  6. tfConsensus ✅ — Multi-timeframe alignment
  7. fearIndex ✅ — VIX, sentiment global

VALIDATION (2):
  8. tradeValidator — "Est-ce que ce setup est valide?"
  9. riskManager — "Quel risk level? Position size?"

ORCHESTRATION (2):
  10. supervisor — "Est-ce que tout va bien?"
  11. orchestrator ✅ — Master decision, fusionne tous les agents

SUPPORT (1):
  12. libraryAgent [NEW] — Structure, anti-doublon, référence
```

**Chacun fait une chose précise, remonte au dashboard**

---

# H. CHECKLIST FINALE VALIDATION

- ✅ Audit complet de l'existant (AUDIT_EXISTANT.md)
- ✅ 6 fichiers enrichis identifiés (pas créés)
- ✅ 4 fichiers créés justifiés (pas alternatives)
- ✅ libraryAgent = agent de structure (pas métier)
- ✅ Library.json = source de vérité
- ✅ 12 étapes implémentation (ordre sûr, testable)
- ✅ V1 minimale, branchée, sans risque
- ✅ Dashboard = hub central de tout
- ✅ Alertes = filtrées par prefs utilisateur
- ✅ Zéro breaking changes

---

# SIGNATURE VALIDATION

**Approuves-tu cette structure AVANT coding?**

Ou modifications requises sur:
- [ ] Fichiers enrichir (6)?
- [ ] Fichiers créer justification (4)?
- [ ] Rôle libraryAgent?
- [ ] Ordre implémentation (12 phases)?
- [ ] V1 scope?

