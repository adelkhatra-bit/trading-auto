# 🔐 TROIS VERROUILLAGES FINAUX — Avant Implémentation

**Status:** Architecture validée  
**Blocking:** 3 confirmations critiques avant GO  
**Scope:** Real ticks source, actual UI rendering, honest symbol coverage V1

---

## PREAMBULE

La direction générale est validée:
- ✅ Ticks → Bougies → Clôtures
- ✅ Indicateurs recalculés post-close
- ✅ Agents synchronisés
- ✅ SSE broadcast coordonné
- ✅ Extension/Studio/Dashboard alignés

**Mais avant de coder une seule ligne, il faut verrouiller 3 points essentiels.**

Sans ces confirmations, on risque de construire un système "prêt à recevoir des ticks" qui ne reçoivent jamais rien, ou une belle architecture backend sans affichage réel.

---

## 1️⃣ SOURCE RÉELLE DES TICKS

### Problème: `POST /api/mt5/tick` c'est beau en théorie

Tu dis que l'endpoint reçoit des ticks de MT5.

**Je veux confirmation sur:**

#### A. QUI envoie les ticks?

Le document dit: "MT5 EA writes to mt5_data.json every N seconds" ou "Python Bridge sends ticks"

**Précisons:**
- Existe-t-il UNE méthode unique (EA ou Python bridge)?
- Ou DEUX options possibles (EA + Python comme fallback)?
- Si EA: le Bridge_MT5_Studio.mq5 actuel peut-il être modifié pour faire POST /api/mt5/tick?
- Si Python: mt5_bridge.py peut-il faire des requires HTTP?

**Je veux:** Une SEULE source de vérité pour ticks. Pas "EA ou Python", mais "EA PUIS Python en fallback" avec ordre clair.

#### B. À QUELLE FRÉQUENCE?

- Si EA: tous les N secondes (5s? 10s? configurable?)
- Si Python: tous les M secondes (1s? 5s?)
- Peut-on avoir mix: EA rapide (5s) + Python lent (10s) en backup?

**Je veux:** Exactement combien de ticks/minute attendus?

#### C. FAISABILITÉ EA MT5

Le fichier Bridge_MT5_Studio.mq5 actuel:
- Existe-t-il?
- Peut-il être modifié pour POST HTTP?
- Ou faut-il une nouvelle EA?
- Quelle syntaxe MQL5 pour HTTP post?

**Je veux:** Code snippet exact du POST qui sera envoyé depuis l'EA, ou confirmation que Python bridge suffira.

#### D. DONNÉES RÉELLES DU TICK

Le POST /api/mt5/tick reçoit:
```json
{
  symbol: "XAUUSD",
  bid: 2375.25,
  ask: 2375.35,
  volume: 150,
  timestamp: 1712149200000
}
```

**Questions:**
- Ce `volume` du tick: c'est le volume de ce tick seul? Ou volume depuis ouverture bougie?
- Et `timestamp`: UTC ou MT5 timezone?
- Combien de décimales pour prix (4 pour forex?)

**Je veux:** Structure JSON exacte avec décimales réelles.

---

## 2️⃣ AFFICHAGE DES GRAPHIQUES

### Problème: Architecture backend ≠ Affichage utilisateur

Le document parle bien de SSE messages, mais pas comment ça **s'AFFICHE**.

**Je veux confirmation sur:**

#### A. STUDIO CHART

**Bougie en cours (NOT yet closed):**
- Affichée où? (main chart area? sub-chart?)
- Avec quelle couleur/style? (hollow candle? thin outline?)
- Label "H1 10:00-11:00 (in progress)"?
- OHLC values shown real-time as ticks arrive?

**Example display wanted:**
```
┌─ Studio Chart
│
├─ Last closed candles (history):
│  │
│  ├─ H1 09:00: O 2375.10, H 2375.80, L 2373.50, C 2374.20 [CLOSED]
│  └─ H1 08:00: O 2373.50, H 2376.20, L 2372.10, C 2375.10 [CLOSED]
│
├─ Current candle (IN PROGRESS):
│  │
│  └─ H1 10:00: O 2375.30, H 2375.52, L 2374.80, C 2375.15 [WAITING: 45 min left]
│
├─ Indicators overlay:
│  ├─ RSI(14): 52.4
│  ├─ MACD: line 0.20, signal 0.18
│  └─ BB(20,2): upper 2377.2, lower 2372.4
│
└─ Signal (when closed):
   └─ LONG, score 68, entry 2375.30, SL 2374.20, TP 2376.50
```

**I want to know:**
- Library used for chart? (TradingView Lightweight? ECharts? Canvas?)
- Can it display candles + indicators + signals clearly?
- Will refresh on tick be smooth (no flicker)?

#### B. EXTENSION POPUP

**What does extension show?**
- Current candle OHLC (live update)?
- Or just price + button to register user price?
- Closed candle list (last 5)?
- Indicators preview?

**Example popup wanted:**
```
┌─ Extension Popup
│
├─ [Price Settings] [Current]
│
├─ Current Candle (H1 10:00)
│  ├─ Open:  2375.30
│  ├─ High:  2375.52
│  ├─ Low:   2374.80
│  ├─ Close: 2375.15 (updating...)
│  └─ Status: 45 min remaining
│
├─ Last Closed (H1 09:00)
│  ├─ O 2374.20 H 2375.80 L 2373.50 C 2375.10
│
├─ User Reference Price
│  ├─ Input: [2375.50]
│  ├─ System: 2375.15
│  ├─ Status: ✓ OK (0.0086% diff)
│  └─ [Register Price]
│
└─ Latest Signal (if any)
   └─ LONG, score 68, entry 2375.30
```

**I want to know:** Exactly what is visible, what updates live, what is static?

#### C. DASHBOARD

**Signal history table:**
- New row when signal generated?
- Show: Symbol, TF, Time, Direction, Score, Entry, SL, TP, Reason?
- Color coding (green/red)?
- Real-time updates (no page refresh)?

**Candle history:**
- Show closed candles in separate panel?
- Or just in Studio chart?

**I want to know:** Exact columns, how it updates, refresh rate.

---

## 3️⃣ MULTI-SYMBOLES RÉEL

### Problème: "4 symboles" mais lesquels vraiment?

Le plan dit: "XAUUSD, EURUSD, GBPUSD, USDJPY"

**Je veux distinction honnête:**

#### A. SYMBOLES AVEC VRAIES BOUGIES (Tier 1)

Lesquels auront:
- ✅ Ticks réels de MT5
- ✅ Bougies H1 propres
- ✅ Indicateurs calculés
- ✅ Agents analysent
- ✅ Signaux générés

**Candidats:** XAUUSD (certain, on a déjà mt5_data.json)

**Autres possibles:** EURUSD, GBPUSD si EA MT5 les fournit

**Question:** L'EA MT5 peut-il écrire 4 symboles simultanément? Ou juste 1?

#### B. SYMBOLES AVEC PRIX SEULEMENT (Tier 2)

Lesquels auront:
- ✅ Prix courant (system price)
- ❌ Pas de vrais ticks
- ❌ Pas de bougies
- ❌ Pas d'indicateurs
- ❌ Pas de signaux

**Question:** Quels symboles entrent dans cette catégorie de départ?

#### C. SYMBOLES NON DISPONIBLES (Tier 3)

Lesquels n'auront:
- ❌ Aucune donnée
- ❌ Visible mais "pas de données"
- ❌ Agents ne les analysent pas

**Question:** Comment gérer les demandes pour Tier 3 symbols? Message clair "pas disponible"?

#### D. STRATÉGIE V1 → V2

**V1 (Launch):**
- Tier 1: XAUUSD (certain)
- Tier 2: EURUSD, GBPUSD,USDJPY (prix seulement, user peut activer user price)
- Tier 3: Autres (greyed out, "coming soon")

**V2 (Phase 2):**
- Move EURUSD, GBPUSD, USDJPY to Tier 1 (if EA provides)
- Add crypto/indices if needed

**I want to know:** 
- What's the HONEST Tier 1 list for Day 1?
- What's the fallback for users asking "why no analysis for EURUSD?"
- When can Tier 2 become Tier 1? (depends on EA enhancement?)

---

## VALIDATION TEMPLATE

Once confirmed, this locks it:

```javascript
// TICK SOURCE
source: {
  primary: "MT5_EA_Bridge", // "MT5_EA_Bridge" | "Python_Bridge"
  frequency: "5 seconds",     // Every N seconds
  structure: {
    symbol, bid, ask, volume, timestamp
  }
}

// DISPLAY TARGETS
display: {
  studio_chart: {
    library: "TradingView Lightweight Charts",
    shows: ["closed_candles", "current_candle", "indicators", "signals"],
    refresh: "on_tick"
  },
  extension_popup: {
    shows: ["current_candle", "last_closed", "user_price_form", "signal"],
    refresh: "on_tick"
  },
  dashboard: {
    shows: ["signal_history", "candle_history"],
    refresh: "on_signal"
  }
}

// SYMBOL COVERAGE V1
symbols: {
  tier1: ["XAUUSD"],  // Full analysis
  tier2: ["EURUSD", "GBPUSD", "USDJPY"],  // Price only
  tier3: []  // None for now
}
```

---

## RÉSUMÉ: 3 POINTS À VERROUILLER

| Point | Status | Need |
|---|---|---|
| **1. Ticks source** | ⏳ Pending | Exact method, frequency, EA modification, JSON structure |
| **2. UI display** | ⏳ Pending | Studio chart lib, extension layout, dashboard columns |
| **3. Symbol coverage** | ⏳ Pending | Tier1/Tier2/Tier3 split, V1 launch list, V2 roadmap |

**Once ALL 3 are ✅ confirmed (not "pending" or "maybe")**

→ Then: IMPLEMENTATION STARTS

---

**C'est quoi ta réponse sur ces 3 points?**
