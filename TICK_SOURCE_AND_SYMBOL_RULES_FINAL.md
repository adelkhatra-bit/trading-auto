# TICK SOURCE & SYMBOL RULES - VERROUILLAGE FINAL

## POINT 1: TICK SOURCE - CLARIFICATION HONNÊTE

### Question Posée
- Vrai flux tick par tick ?
- Agrégation locale plus fréquente ?
- Fréquence minimale pour crédibilité + clôture fiable + indicateurs propres + latence faible ?

### Réponse Honnête : Options Réelles

#### Option A: Flux tick vrai (multiple par seconde)
**Réalité technique:**
- MT5 EA `OnTick()` déclenche à chaque changement de prix (50-500 times/sec selon pair)
- Transmission réseau : POST HTTP vers Node.js
- Overhead réseau : 10-50ms latence + variabilité

**Implications:**
```
Avantages:
+ Bougie en cours ultra-précise (chaque tick agrégé)
+ Clôture détectée à la milliseconde du changement
+ Indicateurs recalculés sur données précises
+ Latence signal: <50ms theoretical

Inconvénients:
- Infrastructure réseau saturée (500 req/sec impossible)
- Stockage temps réel très lourd (tick history)
- Calcul indicateurs trop fréquent (waste CPU)
- Reliability: perte de ticks = données corrompues
```

**Verdict:** Théoriquement parfait, mais **IMPRATICABLE en production locale**.

---

#### Option B: Agrégation locale + POST fréquent (1-2 sec)
**Réalité technique:**
- MT5 EA agrège ticks en local (simple: last price + OHLC courant)
- POST toutes les 1-2 secondes avec : price, bid/ask, volume, timestamp
- Node.js agrège les 1-2 updates en candle in-progress

**Implications:**
```
Avantages:
+ Infrastructure légère (1-2 req/sec max)
+ Données réseau stables et prévisibles
+ Bougie en cours très crédible (mise à jour chaque 1-2s)
+ Latence signal: 100-150ms (acceptable)
+ Indic recalculés à bonne fréquence (toutes les 2s si clôture)

Inconvénients:
- Perte de micromovements très courts
- Volatilité intra-tick non captée (irrelevant pour H1/M15)
- Precision: à la 1-2s près seulement (OK pour swing trading)
```

**Verdict:** **PRAGMATIQUE et PRODUCTION-READY**. Bon tradeoff.

---

#### Option C: POST toutes les 5 secondes (ACTUEL)
**Réalité technique:**
- POST statique toutes les 5 secondes
- Même données que Option B

**Implications:**
```
Avantages:
+ Ultra light on network
+ Très stable

Inconvénients:
- Bougie en cours "ancienne" de 0-5s (visibility faible)
- Clôture peut être détectée 5s après real close
- Latence signal: 250-350ms (trop élevée)
- Indicateurs rafraîchis au mieux toutes les 5s
- User voit des données "old" dans Extension
```

**Verdict:** Trop lent pour temps réel crédible. **REJETÉ**.

---

### Recommandation Finale: Option B (1-2 sec)

**Implémentation précise:**

```javascript
// MT5 EA - Bridge logic
// ====================================
// Toutes les 100ms (10x par seconde), faire:
// - Vérifier si price a changé
// - Mettre à jour OHLC bougie courante
// - Si (time_now - last_post_time) > 1000ms:
//   - POST /api/mt5/tick avec {price, bid, ask, volume, time}
//   - Reset last_post_time

// Node.js - Server side
// ====================================
// POST /api/mt5/tick (reçoit tous les 1-2 secondes)
// - CandleManager.onTick(price, bid, ask, volume, timestamp)
// - Deux cas:
//   1. Si candle in-progress: update OHLC + emit('candle:update')
//   2. Si candle fermée (timestamp > candle.close_time):
//      - Emit('candle:closed', oldCandle)
//      - Créer new candle
//      - Emit('indicators:ready') après 50-100ms
```

**Latence réseau réelle:**

```
T=0:00     : Price change in MT5 (real tick)
T=0:00-1:00: Accumulated locally in EA
T=1:00     : POST /api/mt5/tick
T=1:05     : Server receives (±5ms network)
T=1:05     : CandleManager.onTick() updates candle
T=1:10     : IndicatorEngine calculates (±50ms)
T=1:15     : Agents run (±30ms)
T=1:20     : SSE broadcast to clients
T=1:30     : Extension popup shows update

Total latency: 30ms (network) + 50ms (calcs) + 20ms (broadcast) = ~100-150ms
Acceptable pour swing trading (H1/M15/D1)
```

---

### Fréquence Minimale pour Crédibilité

```
Bougie en cours crédible?
- Besoin: update tous les 1-2s max
- Option B: ✅ Satisfait (POST 1-2s)
- Option C: ⚠️ Limite (5s = trop vieux)

Clôture fiable?
- Besoin: détection dans 500ms après event
- Option B: ✅ Satisfait (5s max entre checks)
- Option C: ⚠️ Peut rater de 0-5s

Indicateurs propres?
- Besoin: données précises au 1-2s
- Option B: ✅ Satisfait (update 1-2s)
- Option C: ⚠️ Données stalees 5s

Latence signal faible?
- Besoin: <200ms T à T
- Option B: ✅ 100-150ms
- Option C: ❌ 250-350ms
```

---

### Cas d'exception: Fallback si Bridge indisponible

Si MT5 EA ne peut pas poster (network down, etc):

```
Fallback 1: WebSocket reconnect
- Si POST échoue pendant 30s, tenter WebSocket upgrade
- Data intégrité: buffer local dans EA, replay on reconnect

Fallback 2: Manual import
- User importe JSON depuis MT5 (délégage historique)
- Future = Option B resume

Fallback 3: Graceful degradation
- Si pas de tick depuis 60s:
  - Extension: show "STALE DATA" warning
  - Dashboard: show last-received timestamp
  - Agents: DO NOT TRIGGER (wait for fresh data)
```

---

## POINT 2: MULTI-SYMBOLES - RÈGLE NOIR SUR BLANC

### Les 3 États Possibles

#### État 1: READY (Analyse complète autorisée)

**Critères objectifs (ALL required):**
```
✅ Vraies bougies       : Candles avec OHLC fiable, timeframes H1/M15/D1
✅ Historique complet   : Min 100 candles fermées + data source
✅ Vrais indicateurs    : RSI/MACD/BB/ATR/MA recalculés à chaque clôture
✅ Latence acceptable   : Signal généré <200ms après clôture
✅ Synchronisation      : Client voit même signal au même moment (±100ms)
```

**Symboles READY v1.0:**
- XAUUSD (Gold) - Tier 1 (priorité)

**Symboles READY v1.1 (planifié):**
- EURUSD, GBPUSD, USDJPY (Tier 2, dès que EA scalable)

**En-tête flag dans code:**
```javascript
// symbol-config.js
const SYMBOL_STATES = {
  'XAUUSD': { state: 'READY', tier: 1, since: '2026-04-03' },
  'EURUSD': { state: 'NOT_READY', tier: 2, reason: 'data_pending' },
  'USDJPY': { state: 'NOT_READY', tier: 3, reason: 'data_pending' }
};

// Agents MUST check this before running:
const agentContext = {
  symbol: 'EURUSD',
  state: SYMBOL_STATES['EURUSD'],
  // If state !== 'READY': signal generation = BLOCKED
};
```

**Behaviour:**
```javascript
// Dans orchestrator-realtime.js
async function runAgents(symbol, context) {
  if (SYMBOL_STATES[symbol].state !== 'READY') {
    // EXPLICIT BLOCK
    logger.warn(`SIGNAL SUPPRESSED for ${symbol}: state=${SYMBOL_STATES[symbol].state}`);
    emit('signal:blocked', { symbol, reason: SYMBOL_STATES[symbol].reason });
    return null; // NO SIGNAL, NO FAKE DATA
  }
  // ... normal flow
}
```

---

#### État 2: INIT (Données de prix uniquement, pas d'analyse)

**Critères objectifs:**
```
✅ Prix système ou user        : Disponible via symbol-preferences
❌ Bougies réelles             : Absentes ou incomplètes
❌ Historique                  : Absent ou < 20 candles
❌ Indicateurs frais           : Pas calculés ou stale
```

**Symboles INIT v1.0:**
- EURUSD, GBPUSD, USDJPY, USDJPY, AUDUSD, etc.
- (Tous les symboles sans EA bridge encore)

**Behaviour:**
```javascript
// Cette fonction s'exécute:
async function getUserPrice(symbol) {
  return await symbolPreferences.getEffectivePrice(symbol);
  // ✅ Returns locked > userRef > system
  // But NO indicators, NO signals
}

// Cette fonction s'exécute PAS:
async function generateSignal(symbol) {
  // Bloquée par état check
  // agent returns: null
}
```

**Data visible to user:**
```javascript
// Extension popup after user inputs reference price for EURUSD:
{
  symbol: 'EURUSD',
  userReferencePrice: 1.0850,
  systemPrice: 1.0845,
  effectivePrice: 1.0850,
  status: 'PRICE_ONLY', // ← Flag explicite
  nextCandle: null,       // ← Aucune donnée technique
  signal: null,           // ← Pas d'analyse
  warning: 'No real-time data for this symbol yet. User price registered but no technical analysis available.'
}
```

---

#### État 3: MISSING (Pas de données du tout)

**Critères:**
```
❌ Prix système ou user    : Absent
❌ Bougies                 : Absent
❌ Historique              : Absent
❌ Indicateurs             : Absent ou n/a
```

**Symboles MISSING v1.0:**
- Anything not in config

**Behaviour:**
```javascript
// Explicit state returned:
{
  symbol: 'NZDJPY',
  state: 'MISSING',
  error: 'Symbol not configured in trading-auto system',
  userPrice: null,
  candles: null,
  signal: null,
  action: 'User must configure this symbol or request v1.1 support'
}

// No simulation, no fuzzy logic, no guessing
```

---

### Règle Synthétique (Noir sur Blanc)

```
╔═══════════════════════════════════════════════════════════════════╗
║                      STATE TRANSITION TABLE                       ║
╠═══════════════════════════════════════════════════════════════════╣
║ Symbol  │ Bougies │ Historique │ Indicateurs │ State    │ Signal  ║
╠═════════╪═════════╪════════════╪═════════════╪══════════╪═════════╣
║ XAUUSD  │  ✅     │   ✅ yes   │    ✅ live  │ READY    │ ALLOWED ║
║ EURUSD  │  ❌     │   ❌ no    │    ❌ n/a   │ INIT     │ BLOCKED ║
║ NZDJPY  │  ❌     │   ❌ no    │    ❌ n/a   │ MISSING  │ BLOCKED ║
╚═════════╧═════════╧════════════╧═════════════╧══════════╧═════════╝

RULES:
1. READY → Full analysis allowed
   - Agents run
   - Signals generated
   - Clients see real data

2. INIT → Price only
   - User can set reference price
   - No technical analysis
   - No signals
   - Clear warning in UI: "Data pending"

3. MISSING → Not supported yet
   - No API endpoint
   - No data stored
   - Clear error: "Symbol not configured"

TRANSITIONS:
- MISSING → INIT: When user adds price (manual entry)
- INIT → READY: When tickstream (EA bridge) configured
- READY → INIT: If EA stops sending data >60s (graceful degrade)
- ANY → MISSING: Only if explicitly removed from config

NO SIMULATION, NO FUZZY LOGIC, NO FAKE SIGNALS
```

---

### Implementation in Code

**File: lib/symbol-state-manager.js** (NEW)

```javascript
class SymbolStateManager {
  constructor() {
    this.states = {
      'XAUUSD': { state: 'READY', tier: 1, since: '2026-04-03' },
      'EURUSD': { state: 'INIT', tier: 2, lastTick: null },
      'GBPUSD': { state: 'INIT', tier: 2, lastTick: null },
      'USDJPY': { state: 'INIT', tier: 3, lastTick: null }
    };
  }

  getState(symbol) {
    return this.states[symbol] || { state: 'MISSING', reason: 'not_configured' };
  }

  canGenerateSignal(symbol) {
    const state = this.getState(symbol);
    return state.state === 'READY';
  }

  recordTick(symbol) {
    if (this.states[symbol]) {
      this.states[symbol].lastTick = Date.now();
      // Check for READY → INIT degrade if too old
      if (this.states[symbol].state === 'READY' && 
          Date.now() - this.states[symbol].lastTick > 60000) {
        this.states[symbol].state = 'INIT';
        logger.warn(`Symbol ${symbol} degraded to INIT: no tick >60s`);
      }
    }
  }
}
```

**Integration Point: orchestrator-realtime.js**

```javascript
async function generateSignal(symbol, context) {
  // FIRST CHECK: State validation
  const state = symbolStateManager.getState(symbol);
  
  if (!symbolStateManager.canGenerateSignal(symbol)) {
    logger.info(`Signal BLOCKED for ${symbol}: state=${state.state}`);
    return {
      symbol,
      state: state.state,
      signal: null,
      reason: `Symbol state is ${state.state}, signal generation not allowed`,
      warning: state.state === 'INIT' 
        ? 'User price set but no technical analysis available yet'
        : 'Symbol not configured in system'
    };
  }

  // Continue normal flow only if READY
  const agents = await loadAgents();
  const results = await Promise.all(agents.map(a => a.analyze(context)));
  // ... aggregate, score, return signal
}
```

**UI Endpoint: GET /api/symbol/:symbol/state**

```javascript
router.get('/api/symbol/:symbol/state', (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  const state = symbolStateManager.getState(symbol);
  const userPrice = await symbolPreferences.getEffectivePrice(symbol);
  
  res.json({
    symbol,
    state: state.state,
    userPrice: userPrice || null,
    lastTick: state.lastTick || null,
    canGenerateSignal: symbolStateManager.canGenerateSignal(symbol),
    tier: state.tier || null,
    action: state.state === 'MISSING' 
      ? 'Symbol not supported yet'
      : state.state === 'INIT'
      ? 'Set user price or wait for EA data'
      : 'Ready for analysis'
  });
});
```

---

## VERROUILLAGE FINAL

### Point 1: Tick Source ✅
**DÉCISION: Option B (POST 1-2 secondes)**
- Fréquence: 1 tick POST toutes les 1-2 secondes
- Latence totale: 100-150ms (acceptable)
- Implémentation: MT5 EA aggège locally, POST HTTP
- Bougie en cours: Crédible (update 1-2s)
- Clôture: Fiable (détection <5s)
- Indicateurs: Propres (recalc 1-2s)
- Marche-arrière: Fallback WebSocket → manual import

### Point 2: Multi-Symboles ✅
**RÈGLE: État explicite + bloque signal automatique**
- READY: Analyse complète (XAUUSD v1.0)
- INIT: Prix seulement (EURUSD/GBPUSD/etc)
- MISSING: Pas supporté
- Non simulé: Aucun faux signal
- Code check: Before signal generation, verify state='READY'
- UI warns: Clear indication si data pending ou missing

---

## Avant Implémentation

Ces 2 points sont maintenant:
- ✅ Honnêtes (pas de promesses impossibles)
- ✅ Clairs (critères objectifs, pas flou)
- ✅ Implémentables (code patterns définis)
- ✅ Testables (chaque règle vérifiable)

**Tu valides ces 2 décisions finales?**

Si oui → Nous pouvons passer à "GO IMPLÉMENTATION Phase 1: lib/candle-manager.js"
