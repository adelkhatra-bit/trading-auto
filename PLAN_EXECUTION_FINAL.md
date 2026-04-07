# PLAN D'EXÉCUTION FINAL — Implémentation Concrete

**Date:** 3 avril 2026  
**V1:** Minimale, sans risque, sans casser l'existant  
**Code:** Pas encore. Validation du plan seulement.

---

# 1. NOUVEAUX FICHIERS (Créés de zéro)

## 1.1 - agent-bus.js (100 lignes)
**Localisation:** Racine du projet  
**Rôle:** Registre central + queue messages inter-agents  
**Pourquoi:** Permet agent→agent communication sans modifier agents existants  
**Produit:** Métadata agents + historique messages + routes GET /agents-bus

## 1.2 - src/agents/surveillance-agent.js (50 lignes)
**Localisation:** Dossier agents  
**Rôle:** Écoute MT5 updates, déclenche analyses intelligemment  
**Pourquoi:** Remplace continuous-loop (CPU 100%) par event-driven  
**Produit:** Trigger `trigger-analysis` quand prix change >0.5% OU >30s écoulées

## 1.3 - alert-manager.js (120 lignes)
**Localisation:** Racine du projet  
**Rôle:** Centralise alertes, les filtre par symbole + severity  
**Pourquoi:** Extension reçoit seulement alertes pertinentes  
**Produit:** Queue alertes + SSE endpoint `/alerts/subscribe`

## 1.4 - utils/audit-helper.js (20 lignes)
**Localisation:** Dossier utils (à créer)  
**Rôle:** Parse stack trace pour extraire file/function/line  
**Pourquoi:** Chaque log audit = lié à sa source exacte  
**Produit:** Helper getCallerLocation() retourne {file, function, line, sourceUrl}

## 1.5 - src/agents/indicator-agent.js (200 lignes)
**Localisation:** Dossier agents  
**Rôle:** Génère indicateurs personnalisés selon marché actuel  
**Pourquoi:** Complète analyse technique avec indicateurs adaptatifs  
**Produit:** {indicators: [...], aggregateSignal, mql5Code} pour MT5

---

# 2. FICHIERS MODIFIÉS (Changements chirurgicaux)

## 2.1 - server.js
**Ce qu'on ajoute:**
- Ligne ~47: Require + init des 3 nouveaux modules (agent-bus, surveillance-agent, alert-manager)
- Ligne ~55: Enregistrer agents via agentBus.registerAgent() (orchestrator, technicalAgent, indicatorAgent, repairAgent, etc)
- Ligne ~820: Après orchestrator.run(), ajouter agentBus.sendMessage() pour logger résultat
- Ligne ~825: Si analysis.direction !== 'ATTENDRE', créer alert via alertManager.createAlert()
- Ligne ~1029: Nouvelle route GET /agents-bus (retour agentBus.getState())
- Ligne ~1057: Nouvelle route POST /alerts/subscribe (SSE pour extension)
- Ligne ~1070: Nouvelle route GET /alerts (historique alertes)
- Ligne ~1084: Nouvelle route POST /surveillance/monitor (ajouter symbole surveillé)
- Ligne ~1557: Modifier pushLog() pour ajouter localisation via getCallerLocation()

**Ce qu'on NE touche pas:**
- Orchestrator.run() signature
- Tous les agents existants
- Routes MT5, TV-bridge, klines, quotes (50+ routes conservées)
- MarketStore interface
- SSE /stream broadcast (juste LOG dedans)
- Studio appels

## 2.2 - studio/index-simple.html ou index.html
**Ce qu'on ajoute:**
- Section "Symboles surveillés" dans sidebar (checkboxes XAUUSD, EURUSD, etc)
- Bouton "Sauvegarder préférences" (localStorage)
- Affichage "Alertes récentes" (3-5 dernières)

**Ce qu'on NE touche pas:**
- Chart Lightweight
- Sélecteurs timeframe
- Boutons trade (instant-trade-live, execute, etc)
- Appels API existants

## 2.3 - public/background.js (Extension)
**Ce qu'on ajoute:**
- Fonction subscribeToAlerts() qui lance EventSource '/alerts/subscribe'
- Listener SSE qui reçoit alertes
- Handler pour chrome.notifications.create() quand alert.severity = HIGH|CRITICAL
- Sauvegarde des symboles surveillés dans chrome.storage.local

**Ce qu'on NE touche pas:**
- Auto-loop (reste désactivé)
- showSignal() function
- Événement listeners existants
- Manifest.json

## 2.4 - AGENTS_MONITOR.html
**Ce qu'on ajoute:**
- 6 onglets (Agents | Pipeline | Signaux | Alertes | Indicateurs | Audit)
- Auto-refresh 2s (fetch /agents-bus, /instant-trade-live, /alerts, /audit/query)
- Affichage statut agents (✅ ✅ 🟡 🔴) + dernière action
- Grille alertes (type, severity, timestamp)
- Tableau indicateurs créés (nom, formula, signal, MQL5 link)
- Liens clickables vers fichiers (via sourceUrl de audit)

**Ce qu'on NE touche pas:**
- Sections existantes
- Styles existants (ajouter CSS au-dessus seulement)

---

# 3. ORDRE D'IMPLÉMENTATION (Précis, séquentiel)

## Phase 1 — Structure (0 dépendance)
1. **Créer utils/audit-helper.js** → Fonction getCallerLocation()
2. **Créer agent-bus.js** → Module Registre + queue messages
3. **Créer alert-manager.js** → Module Alertes + SSE

## Phase 2 — Intégration Server (Zéro breakage)
4. **Modifier server.js:**
   - a) Ligne ~47: Require agent-bus, alert-manager
   - b) Ligne ~55: Enregistrer agents (metadata seulement)
   - c) Ligne ~820: Log orchestrator résultat dans agentBus
   - d) Ligne ~825: Si signal pertinent, alertManager.createAlert()
   - e) Ligne ~1557: pushLog() enrichie avec localisation
   - f) Ajouter 4 routes: /agents-bus, /alerts/subscribe, /alerts, /surveillance/monitor

   **Test:** node server.js doit démarrer, pas d'erreur require

## Phase 3 — Surveillance
5. **Créer src/agents/surveillance-agent.js**
6. **Modifier server.js:**
   - Ligne ~47: Require surveillance-agent
   - Ligne ~55: Créer instance + enregistrer event listener MT5
   - Ligne ~65: Quand surveillance.emit('trigger-analysis'), appeler orchestrator + broadcast

   **Test:** Symptôme: Quand MT5 price change, orchestrator appelé auto

## Phase 4 — indicatorAgent
7. **Créer src/agents/indicator-agent.js**
8. **Modifier orchestrator.js:**
   - Ajouter indicatorAgent en Promise.all (ligne 40-45)
   - Intégrer résultat dans résultat final

   **Test:** GET /instant-trade-live retour dans agents.indicatorAgent les indicateurs

## Phase 5 — Dashboard + Extension
9. **Modifier AGENTS_MONITOR.html** → 6 onglets, auto-refresh
10. **Modifier studio/index-simple.html** → Section symboles surveillés
11. **Modifier public/background.js** → subscribeToAlerts()

---

# 4. V1 MINIMALE SANS RISQUE

**Scope V1:**
- ✅ Agents visible avec statut en temps réel
- ✅ Dashboard = Centre de contrôle (6 onglets)
- ✅ Alertes extension = Filtrées par MES symboles
- ✅ Audit = Enrichi file/line/function
- ✅ Zero breaking changes

**Ce qui est HORS V1 (V2 futur):**
- Pipeline avec gating en chaîne (reste parallèle)
- Indicateurs persistance JSON MT5
- Requête complexe audit (/audit/query)
- Repair Agent complet (reste basique)
- Création dynamique d'agents (reste statique)

---

# 5. WHAT'S VISIBLE DANS LE DASHBOARD

## Onglet 1: AGENTS (Agents Status)
```
Orchest: ✅ 1245ms     | DECISION LONG | Score 75
Technical: ✅ 89ms     | RSI: 65 | EMA20>50
Indicator: ✅ 156ms    | 4 indicateurs créés
Fear: ✅ 42ms          | VIX: NEUTRE
News: ✅ 201ms         | Pas d'annonce
Repair: 🟢 IDLE        | 0 erreurs
```

## Onglet 2: PIPELINE (Vue temps réel)
```
Visualisation:
technicalAgent ───┐
indicatorAgent ───├──→ orchestrator ──→ DECISION
fearIndex ────────┤                  [Signal broadcast]
newsAgent ────────┘
```

## Onglet 3: SIGNAUX (Décisions)
```
Time        | Symbol | Direction | Score | Status
10:30:50    | XAUUSD | LONG      | 75    | ✅ TRADED
10:29:45    | EURUSD | SHORT     | 68    | ⏸️  WAIT
10:28:30    | GOLD   | ATTENDRE  | 45    | —
```

## Onglet 4: ALERTES (Notifications créées)
```
[HIGH] SIGNAL LONG XAUUSD (10:30:50)
  Orchestrator | Score: 75 | [Détails] [Action]

[MEDIUM] 4 indicateurs générés (10:30:20)
  IndicatorAgent | Confluences détectées | [Voir MQL5]

[LOW] Surveillance active (10:15:00)
  Symboles: XAUUSD, EURUSD | Mode: continu
```

## Onglet 5: INDICATEURS (Créés par indicatorAgent)
```
Symbol: XAUUSD | TF: H1 | Condition: HIGH_VOLATILITY

1. RSI_Support
   Formula: RSI(14) < 30 AND Price < Support
   Signal: LONG | Weight: 0.7

2. Liquidity_Trap
   Formula: ATR(14) < 70% avg
   Signal: WAIT | Weight: 0.5

[View MQL5 Code] [Copy to MT5]
```

## Onglet 6: AUDIT (Historique enrichi)
```
Time       | Agent | Action | Status | File:Line | Severity
10:30:50   | Orch  | DECISION| ok    | orchestrator.js:78 | —
10:30:45   | Tech  | analyze | ok    | technicalAgent.js:145 | —
10:30:40   | Ind   | generate| error | indicatorAgent.js:112 | HIGH
10:30:35   | Sync  | UPDATE  | ok    | server.js:820 | —
[Clic sur file:line → ouvre fichier source]
```

---

# 6. WHAT'S VISIBLE DANS L'EXTENSION

## Type 1: Notification Chrome
```
Condition: alert.severity = HIGH | CRITICAL

Chrome notification:
┌─────────────────────────────┐
│ 🚨 SIGNAL LONG              │
│ XAUUSD • Score: 75          │
│ 10:30:50                    │
└─────────────────────────────┘
+ Beep audio
```

## Type 2: Popup Interactive
```
Condition: User clique notification

┌─────────────────────────────────┐
│  TRADING AUTO — Signal Reçu    │
├─────────────────────────────────┤
│                                 │
│  🟢 LONG XAUUSD                │
│  Score: 75/100                  │
│  Entry: 2412.50                 │
│  SL: 2410.00                    │
│  TP: 2415.00                    │
│                                 │
│  [📊 Details] [✅ OK] [❌ Skip] │
│                                 │
└─────────────────────────────────┘
```

## Déclencheurs d'Alertes (Basé sur MES choix)

```
1. Signal Détecté
   IF: direction ≠ ATTENDRE AND score > 60
   AND symbol IN [XAUUSD, EURUSD, ...] (ma liste)
   AND timeframe = MA sélection
   THEN: Créer ALERT HIGH/MEDIUM

2. Erreur dans Agent
   IF: agent status = error AND symbol = surveilli
   THEN: Créer ALERT HIGH (severity)
   + Afficher: File:Line + [View in Code]

3. Indicateur Créé
   IF: indicatorAgent génère indicateurs
   AND count > 0
   THEN: Créer ALERT MEDIUM + [See MQL5]

4. Surveillance Activée
   IF: User clique "Monitor XAUUSD"
   THEN: Créer ALERT LOW + "Monitoring active"
```

---

# 7. CE QUI EST ENREGISTRÉ DANS AUDIT/BACKUP

## Structure audit.json (Enrichie)

```json
{
  "timestamp": "2026-04-03T10:30:50.123Z",
  "sessionStart": "2026-04-03T10:00:00Z",
  
  "agents": [
    {
      "name": "orchestrator",
      "status": "ok|error|warning",
      "lastRun": "10:30:50",
      "executionMs": 145,
      "location": {
        "file": "src/agents/orchestrator.js",
        "function": "run",
        "line": 40
      }
    }
  ],
  
  "decisions": [
    {
      "id": "dec-001",
      "timestamp": "10:30:50",
      "direction": "LONG",
      "score": 75,
      "symbol": "XAUUSD",
      "timeframe": "H1",
      "source": "orchestrator",
      "agents_involved": ["technicalAgent", "tfConsensus", "indicatorAgent"],
      "trade": {entry, sl, tp, risk}
    }
  ],
  
  "alerts": [
    {
      "id": "alert-001",
      "timestamp": "10:30:50",
      "type": "SIGNAL|ERROR|INFO",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "source": "orchestrator",
      "symbol": "XAUUSD",
      "message": "LONG signal detected",
      "read": false
    }
  ],
  
  "errors": [
    {
      "id": "err-001",
      "timestamp": "10:30:40",
      "agent": "macroAgent",
      "error": "Timeout fetching calendar",
      "severity": "HIGH",
      "location": {
        "file": "src/agents/macroAgent.js",
        "function": "getCalendar",
        "line": 89,
        "sourceUrl": "workspace://src/agents/macroAgent.js#L89"
      },
      "status": "open|resolved",
      "resolution": "Fallback to fixture data"
    }
  ],
  
  "symbols": ["XAUUSD", "EURUSD"],
  
  "stats": {
    "totalDecisions": 12,
    "totalAlerts": 45,
    "totalErrors": 3,
    "successRate": 94,
    "avgExecutionMs": 156
  }
}
```

---

# 8. ALERTES DÉPENDENT DE MES CHOIX

## Dashboard: Section "Mes Préférences" (Studio)
```
┌─────────────────────────────────┐
│  MON CONFIGURATION              │
├─────────────────────────────────┤
│  Symboles Surveillés:           │
│  ☑️  XAUUSD                     │
│  ☑️  EURUSD                     │
│  ◻️  GBPUSD                     │
│                                 │
│  Timeframe: H1          ▼       │
│  Niveau alerte min: MEDIUM ▼    │
│  Risk Level: MEDIUM     ▼       │
│                                 │
│  [💾 Save] [Reset]              │
└─────────────────────────────────┘
```

## Filtrage d'Alertes (Logique dans alert-manager.js)

```javascript
function shouldNotifyUser(alert, userPreferences) {
  // 1. Symbol filter
  if (!userPreferences.symbols.includes(alert.symbol)) {
    return false;  // Alerte ignorée
  }
  
  // 2. Severity filter
  const severityOrder = {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1};
  if (severityOrder[alert.severity] < severityOrder[userPreferences.minSeverity]) {
    return false;  // Trop peu grave
  }
  
  // 3. Timeframe filter
  if (userPreferences.timeframe && 
      alert.timeframe !== userPreferences.timeframe) {
    return false;  // TF ne match pas
  }
  
  // 4. Risk level filter
  if (alert.data.risk && 
      alert.data.risk > userPreferences.maxRisk) {
    return false;  // Trop risqué
  }
  
  return true;  // ✅ Notifier l'utilisateur
}
```

## Sauvegarde Préférences
```javascript
// localStorage (studio)
{
  "tradingPrefs": {
    "symbols": ["XAUUSD", "EURUSD"],
    "timeframe": "H1",
    "minSeverity": "MEDIUM",
    "maxRisk": 2.5,
    "autoMonitor": true
  }
}

// ET renvoyé vers extension
chrome.storage.local.set({userFilters: {...}})
```

---

# 9. INDICATORAGENT — ARCHITECTURE POUR MT5

## Où il s'insère
```
server.js ligne 820:
orchestrator.run(payload)
  ├─ Appelle Promise.all([
  │   tradingCore.analyze(),
  │   tfConsensus.buildConsensus(),
  │   fearIndex.getFearIndex(),
  │   newsIntelligence.analyze(),
  │   indicatorAgent.generateIndicators()  ← NOUVEAU
  │ ])
  └─ Fusionne résultats
```

## Ce qu'il produit
```javascript
{
  agent: "indicatorAgent",
  status: "ok|error",
  symbol: "XAUUSD",
  timeframe: "H1",
  marketCondition: "HIGH_VOLATILITY|MEDIUM|LOW_LIQUIDITY",
  
  indicators: [
    {
      name: "RSI_Confluence_Support",
      type: "overbought_oversold",
      formula: "RSI(14) < 30 AND Price < PrevLow",
      thresholds: {rsiLevel: 30, confirmCandles: 1},
      signal: "LONG",
      weight: 0.7,
      mql5Code: "if (iRSI(...,14) < 30 && price < prevLow) { BUY_SIGNAL = true; }"
    }
    // ... plus d'indicateurs
  ],
  
  aggregateSignal: "LONG",
  confidence: 0.75,
  mql5Code: "// Generated 2026-04-03 10:30:50 UTC\nif (iRSI...) { ... }\nif (iATR...) { ... }"
}
```

## Comment il envoie ses signaux
```
1. indicatorAgent.generateIndicators() retourne {indicators, aggregateSignal}
2. orchestrator.js fusionne en: result.agents.indicatorAgent = {...}
3. server.js ligne 825: alertManager.createAlert('indicatorAgent', {...})
4. SSE /stream broadcast: {type: 'analysis', agents: {indicatorAgent: {...}}}
5. Extension reçoit via SSE + filtre + notifie
6. Dashboard affiche dans onglet "Indicateurs"
```

## Comment il remonte au dashboard
```
Route 1: GET /instant-trade-live
  Response: {agents: {indicatorAgent: {...}}}
  → Affichage: Onglet Indicateurs du dashboard

Route 2: SSE /stream (broadcast)
  Message: {type: 'analysis', agents: {...}}
  → Affichage: Onglet Signaux en temps réel

Route 3: GET /agents-bus
  Response: {agents: {indicatorAgent: {...}}}
  → Affichage: Onglet Agents statut

Route 4: GET /alerts
  Alert type: 'indicator'
  → Affichage: Onglet Alertes
```

---

# CHECKLIST VALIDATION FINALE

- ✅ 5 nouveaux fichiers (agent-bus, surveillance, alert-manager, audit-helper, indicator-agent)
- ✅ 5 fichiers modifiés (server.js, studio/index, background.js, AGENTS_MONITOR.html, orchestrator.js)
- ✅ 3 phases implémentation (Structure → Server → Surveillance+IndicatorAgent)
- ✅ V1 minimale, sans surcharge
- ✅ 6 onglets dashboard visibles
- ✅ Extension: notification + popup + déclencheurs clairs
- ✅ Audit: structure JSON enrichie + file/line/function
- ✅ Alertes: filtrées par MES symboles, timeframe, risk
- ✅ IndicatorAgent: Architecturé pour MT5, intégré Promise.all, remonte au dashboard
- ✅ Zéro breaking changes

---

**Plan prêt à valider. Approuves-tu pour coding?**
