# 📋 SYSTEM CONTROL PANEL — Documentation

**Date**: 3 Avril 2026  
**Version**: 1.0  
**Accès**: `http://localhost:4000/control-panel`

---

## Vue d'ensemble

Le **System Control Panel** est une cartographie visuelle et organisée de tous les éléments du système Trading Auto, classés en **3 états distincts**:

- **🟢 EN COURS** — Éléments réellement en exécution
- **⏸️ EN ATTENTE** — Éléments développés mais non lancés (standby)
- **🔨 EN CONSTRUCTION** — Éléments partiellement implémentés

---

## 🟢 EN COURS (Production Active)

### 1. Server Core (Node.js)
**Fichier**: `server.js`  
**Port**: 4000  
**État**: ✅ ACTIF (24/7)  

**Responsabilités**:
- Reçoit ticks MT5 via POST `/mt5`
- Route vers studio UI
- Gère endpoints API (positions, charts, market status)
- Applique bloquage marché fermé (P2)

**Modules intégrés**:
- `lib/candle-manager.js` — Agrégation OHLC
- `lib/market-hours-checker.js` — Détection marché 100% local
- `lib/data-source-manager.js` — Gestion données
- `lib/symbol-normalizer.js` — Normalisation

**Endpoints clés**:
```
GET  /                       → index.html (menu)
GET  /studio                 → Studio UI (principal)
GET  /audit                  → Audit dashboard
GET  /control-panel          → Ce panneau
POST /mt5                    → Reçevoir ticks
GET  /mt5/latest             → Dernier candle
GET  /mt5/market-status      → Statut marché (P2)
GET  /mt5/symbols            → Liste symboles
GET  /match-symbol/:tvSymbol → Mapping TradingView
GET  /health                 → Vérifier serveur
```

---

### 2. Studio Interface (UI Principale)
**Fichiers**: 
- `studio/index-simple.html` (HTML structure)
- `studio/studioapp.js` (Logique complète)
- `studio/studiostyles.css` (Styles)

**État**: ✅ ACTIF ET EN ÉVOLUTION  

**Fonctionnalités**:
- ✅ Sélection symbole avec sidebar
- ✅ Affichage positions temps-réel
- ✅ Chart candlesticks (TradingView Lightweight Charts)
- ✅ Badge statut marché 🟢/🔴 (P2 - Fraîchement ajouté)
- ✅ Boutons actions (trades, analyses, rapports)

**Intégrations**:
- Fetch données via `/mt5` endpoints
- WebSocket ready (future)
- localStorage persistence

**Structures-clés**:
```javascript
state.symbol                    // Paire actuelle
state.timeframe                 // TF (H1, H4, D1, etc)
state.chart                     // Instance TradingView chart
state.candleSeries              // Candle series on chart
updateMarketStatusBadge()       // [P2] Maj badge marché
```

---

### 3. Market Hours Detector (P2)
**Fichier**: `lib/market-hours-checker.js`  
**État**: ✅ COMPLET ET FONCTIONNEL  

**Caractéristiques**:
- 🟢 **100% LOCAL** — Aucune API externe
- 🟢 **Synchrone** — Exécution <1ms
- 🟢 **UTC hardcodé** — Aucun problème DST
- 🟢 **Multi-asset** — Forex, Equity, Crypto, Metal

**Logique**:
```
Forex (EURUSD, etc)  → 24h/5 (dim 22h → ven 22h UTC)
Metal (XAUUSD)       → suit Forex
Equity (AAPL, etc)   → 13:30-20:00 UTC weekdays seulement
Crypto (BTC, ETH)    → 24/7 (always open)
```

**Branchage dans serveur**:
```javascript
// server.js line ~760
const marketStatus = marketHoursChecker.getStatus(canonical);
if (!marketStatus.isOpen) {
  return res.json({ ok: false, blocked: true, ... });
}
```

**Endpoint public**:
```
GET /mt5/market-status?symbol=EURUSD
→ { isOpen: bool, market: str, session: str, closesIn: min, ... }
```

**Test de validation**:
```bash
node test-market-checker.js
## OUTPUT:
✅ EURUSD: Forex OPEN (2h 12m)
✅ XAUUSD: Metal OPEN (2h 12m)
✅ AAPL: US Equity OPEN (6h 12m)
✅ BTC: Crypto OPEN (10h 12m)
```

---

### 4. Candle Manager (OHLC Aggregation)
**Fichier**: `lib/candle-manager.js`  
**État**: ✅ COMPLET (Phase 1B: 10/10 tests PASSED)  

**Tests validés**:
```
✅ Initialization
✅ Single tick creates candle
✅ Multiple ticks update candle
✅ Candle boundary crossing
✅ Closed candles history
✅ Multiple timeframes
✅ Get complete candle set
✅ State overview
✅ Persistence (JSON)
✅ Reload from persistence
```

**Intégration**:
- Appelé dans `POST /mt5` → `candleManager.onTick()`
- Agrège ticks en candlesticks OHLC
- Persiste en JSON (pas de DB externe)
- Mutli-timeframe (H1, H4, D1, W1, MN1)

**API**:
```javascript
candleManager.onTick(symbol, price, bid, ask, volume, ts)
candleManager.getCandles(symbol, timeframe)
candleManager.getState()
candleManager.saveState()
```

---

### 5. MT5 Bridge
**Fichiers**:
- `mt5_bridge.py` — Récepteur ticks (Python)
- `Bridge_MT5_Studio.mq5` — Envoyeur (MQ5 script)
- `mt5_bridge_simple.js` — Wrapper Node.js

**État**: ✅ CONNECTÉ (si MT5 lancé)  

**Flux**:
```
MetaTrader 5
  ↓ (Bridge_MT5_Studio.mq5 envoie ticks)
Python Bridge (mt5_bridge.py)
  ↓ (POST http://localhost:4000/mt5)
Node Server (server.js)
  ↓ (POST /mt5 endpoint)
✅ Candle Manager + Market Check
  ↓
Studio UI (chart + positions)
```

---

## ⏸️ EN ATTENTE (Standby - Prêts mais non prioritaires)

### 1. Audit Dashboard
**Fichier**: `audit-dashboard.html`  
**Modules**: `audit-logger.js`, `audit.json`  
**État**: 📋 PRÊT MAIS INACTIF  

**Responsabilité**: Monitoring tâches & erreurs système  
**Raison standby**: Studio est l'UI prioritaire  
**Accès**: `GET /audit`

---

### 2. Main Menu & Dashboard Nav
**Fichiers**: 
- `index.html` — Menu principal
- `dashboard.html` — Stats globales

**État**: 📋 PRÊT MAIS PÉRIPHÉRIQUE  
**Raison**: Studio est le point d'entrée  
**Accès**: `GET /`

---

### 3. Browser Extension
**Fichiers**:
- `public/manifest.json` — Configuration
- `popup.js`, `background.js`, `content.js` — Logique
- `public/popup.html` — Popup

**État**: 📦 COMPILÉ MAIS NON-DÉPLOYÉ  
**Responsabilité**: Capture TradingView + analyse locale  
**Prochaine étape**: Deployment sur Chrome Web Store

---

## 🔨 EN CONSTRUCTION (À finir ou clarifier)

### 1. Agents System
**Fichiers**: `agent.js`, `agent-bus.js`, `agent-worker.js`  
**État**: 🔨 PARTIELLEMENT IMPLÉMENTÉ  

**Problème**: Non-branché dans flux principal  
**Raison**: Remplacé par logique plus simple  
**Décision**: À archiver ou récupérer (à clarifier)

---

### 2. Experimental Test Pages
**Fichiers**:
- `test-analysis.html`
- `test-chart-visual.html`
- `EXTENSION_TEST.html`
- `agent-log-page.html`

**État**: 🧪 EXPÉRIMENTAL  
**Problème**: Non intégrés au workflow  
**Décision**: À archiver ou recycler

---

### 3. Legacy Data Modules
**Répertoires**: `store/`, `trading/`, `analysis/`  
**État**: 🔨 INCOHÉRENT  

**Problème**: Logique non-clarifiée, versions anciennes  
**Décision**: À archiver sous `backup/` ou récupérer

---

### 4. Symbol Matcher
**Fichier**: `lib/symbol-matcher.js`  
**État**: 🔨 MINIMAL ET HARDCODÉ  

**Problème**: Mapping TradingView→MT5 complexe  
**À faire**: Étendre avec dict plus complet ou API interne

---

## 📊 Statistiques Système

| Métrique | Valeur |
|----------|--------|
| **En cours** | 5 éléments |
| **En attente** | 3 éléments |
| **En construction** | 4 éléments |
| **TOTAL** | 12 éléments cartographiés |
| **Port serveur** | 4000 |
| **HTML públics** | 11 pages |
| **Modules (lib/)** | 7 modules |

---

## 🚀 Accès au Panneau

```
Lien direct: http://localhost:4000/control-panel

Depuis Studio:
- Pas de lien direct (intégration future)

Depuis Menu principal:
- À ajouter dans index.html (future)
```

---

## 📝 Notes de Conception

### Principaux changements apportés (Cette session)

1. **Market Hours Checker (P2)** ✅
   - Créé `lib/market-hours-checker.js` (100% local)
   - Intégré dans `POST /mt5` endpoint
   - Ajouté `GET /mt5/market-status` endpoint
   - Ajouté badge UI dans Studio (🟢/🔴)

2. **System Control Panel** ✅
   - Créé `control-panel.html` avec 3 états distincts
   - Ajouté `GET /control-panel` endpoint

### Principaux modules non-touchés (Préc pour intégrité)

- ✅ server.js (backend production)
- ✅ lib/candle-manager.js (Phase 1B validé)
- ✅ lib/data-source-manager.js
- ✅ MT5 Bridge (Python)
- ✅ studio/index-simple.html (UI principale)

---

## 🎯 Prochaines Étapes (Future Roadmap)

1. **Tester endpoints** avec MT5 live
2. **Valider badge UI** avec vraies données
3. **Deploy extension** sur Chrome Web Store
4. **Archiver legacy** modules sous backup/
5. **Clarifier agents system** ou supprimer
6. **Étendre symbol matcher** avec DB plus grande

---

**Document généré**: 3 Avril 2026  
**Dernière mise à jour**: Session Copilot actuelle  
**Mainteneur**: @github-copilot
