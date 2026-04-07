# PLAN D'EXÉCUTION RÉVISÉ — Après Audit Complet

**Date:** 3 avril 2026  
**Basé sur:** AUDIT_EXISTANT.md  
**Règle:** Réutiliser avant de créer

---

# 1. FICHIERS À CRÉER SEULEMENT (4 fichiers requis)

## 1.1 - agent-bus.js (NEW — 100 lignes)
**Justification:** Aucun équivalent dans l'architecture  
**Raison:** Registre agents + queue messages inter-agents  
**Position:** Racine du projet (next to server.js)

```
Produit:
├─ registerAgent(name, metadata) → enregistre un agent
├─ sendMessage(from, to, message) → queue message
├─ subscribe(agentName, callback) → listener
├─ getMessages(), getAllAgents() → queries
└─ Module est appelé par server.js + agents
```

## 1.2 - src/agents/surveillance-agent.js (NEW — 50 lignes)
**Justification:** continuous-loop.js existe mais DISABLED (CPU spike)  
**Raison:** Remplacer par event-driven sans boucle infinie  
**Position:** Dossier agents

```
Produit:
├─ onMT5Update(symbol, newPayload) → trigger analyse si:
│  ├─ Prix change > 0.5%  OU
│  └─ 30 secondes écoulées
├─ addMonitored(symbol), removeMonitored(symbol)
├─ emit('trigger-analysis') events
└─ Mode continu VIVANT sans CPU spike
```

## 1.3 - alert-manager.js (NEW — 120 lignes)
**Justification:** Aucune gestion d'alertes filtrées dans l'architecture  
**Raison:** Centraliser alertes, filtrer par symboles + severity  
**Position:** Racine du projet

```
Produit:
├─ createAlert(source, data) → crée une alerte
├─ shouldNotify(alert, userFilters) → filtre
├─ addSubscriber(res, filters) → SSE endpoint
├─ getAlerts(symbol, type, limit) → historique
└─ Broadcast filtré vers extension
```

## 1.4 - src/agents/indicator-agent.js (NEW — 200 lignes)
**Justification:** Aucun agent créateur d'indicateurs n'existe  
**Raison:** Génère indicateurs adaptés au marché + MQL5  
**Position:** Dossier agents

```
Produit:
├─ generateIndicators(symbol, timeframe, condition)
├─ Retourne {indicators[], aggregateSignal, mql5Code}
├─ Intégré en Promise.all dans orchestrator
└─ Remonte au dashboard via SSE + /instant-trade-live
```

---

# 2. FICHIERS À ENRICHIR (5 fichiers — extensions seulement)

## 2.1 - audit-logger.js (ENRICHIR — +20 lignes)
**État:** Existe déjà, routes branchées dans server.js  
**À ajouter:** Localisation stack trace  
**Où:** Ajouter fonction + modifier logEvent()  
**Impact:** getState() retourne maintenant {location: {file, function, line}}

## 2.2 - AGENTS_MONITOR.html (UPGRADER — +350 lignes)
**État:** Existe (3 cards statiques)  
**À ajouter:** 6 onglets + auto-refresh + data binding  

## 2.3 - studio/index-simple.html (AJOUTER SECTION — +100 lignes)
**État:** Existe (chart, buttons, analysis)  
**À ajouter:** Section "Mes Préférences" dans le sidebar  

## 2.4 - public/background.js (AJOUTER FONCTION — +50 lignes)
**État:** Existe (autoLoop DISABLED, showSignal)  
**À ajouter:** subscribeToAlerts() SSE listener  

## 2.5 - orchestrator.js (SIMPLIFIER INTÉGRATION — +5 lignes logiques)
**État:** Existe (Promise.all 4 agents)  
**À ajouter:** indicatorAgent en Promise.all  

---

# 3. FICHIERS À MODIFIER (Changements chirurgicaux)

## 3.1 - server.js (Intégration 4 modules + routes)
**Total:** ~80 lignes ajoutées (out of 2800+)

### Ajout A: Requires (Ligne ~47)
```javascript
const agentBus = require('./agent-bus');
const SurveillanceAgent = require('./src/agents/surveillance-agent');
const alertManager = require('./alert-manager');
```

### Ajout B: Register Agents (Ligne ~55)
```javascript
agentBus.registerAgent('orchestrator', {type: 'coordinator'});
agentBus.registerAgent('technicalAgent', {type: 'analyzer'});
agentBus.registerAgent('indicatorAgent', {type: 'generator'});
// ... autres
```

### Ajout C: Surveillance Setup (Ligne ~65)
```javascript
const surveillanceAgent = new SurveillanceAgent(marketStore, orchestrator);

marketStore.on('mt5-update', (symbol, payload) => {
  surveillanceAgent.onMT5Update(symbol, payload);
});

surveillanceAgent.on('trigger-analysis', async (event) => {
  const latest = marketStore.getLatestForSymbol(event.symbol);
  if (orchestrator && latest) {
    const analysis = await orchestrator.run(latest.latestPayload);
  }
});
```

### Ajout D: Orchestrator Broadcasting (Ligne ~820)
```javascript
if (orchestrator) {
  orchestrator.run({...payload})
    .then(analysis => {
      agentBus.sendMessage('orchestrator', 'system', {
        type: 'DECISION',
        direction: analysis.direction,
        score: analysis.score
      });
      
      if (analysis.direction !== 'ATTENDRE' && analysis.score > 60) {
        alertManager.createAlert('orchestrator', {
          symbol: analysis.symbol,
          type: 'SIGNAL',
          severity: analysis.score > 75 ? 'HIGH' : 'MEDIUM'
        });
      }
      
      marketStore.updateAnalysis(canonical, analysis);
    });
}
```

### Ajout E: Routes (Ligne ~500)
```javascript
// GET /agents-bus
// POST /alerts/subscribe (SSE)
// GET /alerts
// POST /surveillance/monitor
// GET /surveillance/status
```

---

# 4. ORDRE D'IMPLÉMENTATION

## Phase 1 — Créer modules (Indépendants)
1. agent-bus.js
2. alert-manager.js
3. surveillance-agent.js

## Phase 2 — Enrichir audit
4. audit-logger.js (+getCallerLocation)

## Phase 3 — Server integration
5. server.js (requires + register + setup + routes + broadcasting)

## Phase 4 — Indicator
6. indicator-agent.js
7. orchestrator.js (add to Promise.all)

## Phase 5 — UI
8. AGENTS_MONITOR.html (6 onglets)
9. studio/index-simple.html (prefs)
10. public/background.js (SSE)

---

# 5. CE QUE TU VERAS

**Après Phase 1:** Modules chargés, pas d'effet visible  
**Après Phase 2:** Audit enrichi, logs ont location  
**Après Phase 3:** Server routes fonctionnelles, alertes broadcast  
**Après Phase 4:** Indicateurs dans /instant-trade-live  
**Après Phase 5:** Dashboard 6 onglets, extension notif, prefs stored  

---

# 6. V1 SCOPE

**In:**
- Surveillance event-driven
- Alertes filtrées symboles
- Dashboard 6 onglets
- Extension notifications
- Audit enrichi localisation

**Out (V2):**
- Pipeline gating avancé
- Repair Agent complet
- Indicateurs persistance BD

---

**PRÊT À CODER?**
