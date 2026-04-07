# 🔗 GUIDE INTÉGRATION — LINE NUMBERS EXACTS

**Où ajouter le code dans les fichiers existants**

---

## 📄 FILE 1: Créer `lib/market-hours-checker.js` (NOUVEAU)

**Localisation:** `c:\...\trading-auto\lib\market-hours-checker.js` (n'existe pas)

**Structure:**
```javascript
/**
 * MarketHoursChecker — Détecte état marché (ouvert/fermé)
 * Input: symbol (EURUSD, XAUUSD, AAPL, BTC, etc)
 * Output: { isOpen, market, session, opensIn, closesIn, ... }
 */

class MarketHoursChecker {
  constructor(options = {}) {
    this.timezone = options.timezone || 'UTC';
    this.sessions = this._initSessions();
  }

  _initSessions() {
    // À remplir selon DECISION MATRIX Question 2
    // Hardcoded OU API externe OU Hybride
    return {
      forex: { ... },
      equity: { ... },
      crypto: { ... },
      metal: { ... }
    };
  }

  classify(symbol) {
    // Déterminer classe d'actif (forex/equity/crypto/metal)
    // Réutiliser logique de server.js déjà existante
  }

  getStatus(symbol) {
    // Vérifier si marché ouvert/fermé
    // Retourner JSON
  }
}

module.exports = new MarketHoursChecker();
```

**Dependencies:** AUCUNE (module standard)  
**Tests:** POST /api/mt5/tick avec ticks fermés + GET /mt5/market-status

---

## 📄 FILE 2: Modifier `server.js` — Point d'Intégration #1

**LE "GARDE": Bloquer ticks marché fermé**

### Zone à modifier: POST /api/mt5/tick

**Fichier:** `server.js`  
**Chercher:** `app.post('/api/mt5/tick'` (environ ligne 640-650)

**Avant (ACTUEL):**
```javascript
app.post('/api/mt5/tick', async (req, res) => {
  const { symbol, price, bid, ask, volume, timestamp } = req.body;
  
  //... validation code ...
  
  if (!symbol || typeof price !== 'number') {
    return res.status(400).json({ error: 'Invalid tick data' });
  }

  // ← AJOUTER CONTRÔLE MARCHÉ ICI
  
  // Process CandleManager
  if (candleManager && candleManager.initialized) {
    await candleManager.onTick(symbol, price, bid, ask, volume, timestamp);
  }
  
  // Update store
  marketStore.updateFromMT5(req.body, symbol);
  
  return res.json({ status: 'ok', symbol });
});
```

**Après (AVEC INTÉGRATION):**
```javascript
app.post('/api/mt5/tick', async (req, res) => {
  const { symbol, price, bid, ask, volume, timestamp } = req.body;
  
  //... validation code ...
  
  if (!symbol || typeof price !== 'number') {
    return res.status(400).json({ error: 'Invalid tick data' });
  }

  // ─── NEW: MARKET HOURS CHECK ─────────────────────────────
  const marketStatus = marketHoursChecker.getStatus(symbol);
  if (!marketStatus.isOpen) {
    console.log(`[TICK_BLOCKED] ${symbol} @ ${new Date().toISOString()} — Market ${marketStatus.market} closed`);
    // Behavior selon DECISION MATRIX Question 3:
    // Option A (recommandé): Silent reject
    return res.json({ 
      status: 'blocked', 
      reason: 'market_closed',
      symbol,
      market: marketStatus.market,
      opensIn: marketStatus.opensIn
    });
  }
  // ──────────────────────────────────────────────────────────
  
  // Process CandleManager (SEULEMENT si marché ouvert)
  if (candleManager && candleManager.initialized) {
    await candleManager.onTick(symbol, price, bid, ask, volume, timestamp);
  }
  
  // Update store
  marketStore.updateFromMT5(req.body, symbol);
  
  return res.json({ status: 'ok', symbol, market_open: true });
});
```

**Impact:** +7 lignes  
**Risque:** Zéro — logique avant appel CandleManager

---

## 📄 FILE 2: Modifier `server.js` — Point d'Intégration #2

**LA "VITRINE": Endpoint pour diagnostic frontend**

### Zone à modifier: Après POST /api/mt5/tick

**Fichier:** `server.js`  
**Ajouter après:** Fin du POST /api/mt5/tick (line ~700)

**Code à INSÉRER:**
```javascript
// ─── NEW ENDPOINT: Market Status Diagnostic ────────────────────────────────
// GET /mt5/market-status?symbol=EURUSD
// Retourne: { isOpen, market, session, opensIn, closesIn, ... }
app.get('/mt5/market-status', (req, res) => {
  const { symbol } = req.query;
  
  if (!symbol) {
    // Return status for all active symbols
    const activeSymbols = Object.keys(marketStore.bySymbol);
    const statuses = activeSymbols.map(sym => ({
      symbol: sym,
      ...marketHoursChecker.getStatus(sym),
      lastTickTime: marketStore.bySymbol[sym]?.updatedAt || null,
      lastTickPrice: marketStore.bySymbol[sym]?.latestPayload?.price || null
    }));
    return res.json({ count: statuses.length, statuses });
  }
  
  // Single symbol
  const status = marketHoursChecker.getStatus(symbol);
  const lastData = marketStore.bySymbol[symbol];
  
  return res.json({
    symbol,
    ...status,
    lastTickTime: lastData?.updatedAt || null,
    lastTickPrice: lastData?.latestPayload?.price || null,
    lastCandleM1: lastData?.latestPayload?.candle_m1 || null
  });
});
// ───────────────────────────────────────────────────────────────────────────
```

**Impact:** +26 lignes  
**Risque:** Zéro — nouvelle route isolée  
**Testable:** Immédiatement avec `curl http://localhost:4000/mt5/market-status`

---

## 📄 FILE 2: Modifier `server.js` — Point d'Intégration #3

**REQUIRE en haut du fichier**

### Zone à modifier: Top du server.js (après autres requires)

**Fichier:** `server.js`  
**Chercher:** Ligne ~50-80 (zone imports/requires)

**Avant:**
```javascript
const express = require('express');
const path    = require('path');
const fs      = require('fs');
const { spawn, execSync } = require('child_process');
const app     = express();
const PORT    = 4000;

// ... autres requires ...
let marketStore, normalizeSymbol, orchestrator, auditLogger;
let candleManager = null;
try {
  marketStore      = require('./store/market-store');
  // ...
```

**Après (AJOUTER UN LIGNE):**
```javascript
const express = require('express');
const path    = require('path');
const fs      = require('fs');
const { spawn, execSync } = require('child_process');
const app     = express();
const PORT    = 4000;

// ... autres requires ...
const marketHoursChecker = require('./lib/market-hours-checker'); // ← NEW LINE

let marketStore, normalizeSymbol, orchestrator, auditLogger;
let candleManager = null;
try {
  marketStore      = require('./store/market-store');
  // ...
```

**Impact:** +1 ligne  
**Risque:** Zéro — simple require

---

## 📄 FILE 3: Modifier `studio/studioapp.js` — UI Update

**LA VITRINE: Afficher badge marché**

### Chercher zone symbol-select listener

**Fichier:** `studio/studioapp.js`  
**Chercher:** `document.getElementById('symbol-select')` ou `symbolSelect.addEventListener`

**À insérer: Nouvelle fonction**
```javascript
// ─── NEW: Display market status badge ──────────────────────────────────────
function updateMarketStatusBadge(symbol) {
  const badge = document.getElementById('market-status-badge');
  if (!badge) return; // Si badge n'existe pas en HTML, skip
  
  fetch(`/mt5/market-status?symbol=${symbol}`)
    .then(r => r.json())
    .then(data => {
      if (data.isOpen) {
        badge.className = 'badge badge-open';
        badge.textContent = `🟢 ${data.market} OPEN (${data.session || 'trading'})`;
        badge.title = `Closes in ${data.closesIn || '?'}`;
      } else {
        badge.className = 'badge badge-closed';
        const opensIn = data.opensIn ? ` — reopens in ${data.opensIn}` : '';
        badge.textContent = `🔴 ${data.market} CLOSED${opensIn}`;
        badge.title = `Session: ${data.session}`;
      }
    })
    .catch(err => {
      badge.textContent = '⚠️ Status unavailable';
      console.warn('[MARKET_STATUS] Fetch failed:', err);
    });
}
// ──────────────────────────────────────────────────────────────────────────
```

### Intégrer appel dans symbol change listener

**Chercher:** `symbolSelect.addEventListener('change', ...)` (environ ligne 200-250)

**Avant:**
```javascript
symbolSelect.addEventListener('change', function(e) {
  const selectedSymbol = e.target.value;
  console.log('Selected:', selectedSymbol);
  // ... existing chart refresh, etc ...
});
```

**Après:**
```javascript
symbolSelect.addEventListener('change', function(e) {
  const selectedSymbol = e.target.value;
  console.log('Selected:', selectedSymbol);
  updateMarketStatusBadge(selectedSymbol);  // ← ADD THIS LINE
  // ... existing chart refresh, etc ...
});
```

**Impact:** +20 lignes (fonction) + 1 ligne (appel)  
**Risque:** Zéro — nouveau code isolé

---

## 🎨 FILE 4: Ajouter CSS (optionnel)

**Fichier:** `public/studio.css` ou `studio/index-simple.html` (inline style)

**Ajouter après existant:**
```css
/* Market Status Badge */
.badge {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
  margin: 5px 0;
  transition: all 0.3s ease;
}

.badge-open {
  background-color: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.badge-closed {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
  opacity: 0.7;
}

.badge:hover {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
```

**À ajouter en HTML (studio/index-simple.html):**
```html
<!-- Dans chart container section -->
<div id="market-status-badge" class="badge badge-open">
  🟢 Market Status
</div>
```

---

## ✅ CHECKLIST INTÉGRATION

- [ ] **STEP 1:** Créer `lib/market-hours-checker.js` (basé Decision Matrix)
- [ ] **STEP 2:** Ajouter require dans server.js ligne ~50
- [ ] **STEP 3:** Ajouter contrôle marché dans POST /api/mt5/tick (ligne ~680)
- [ ] **STEP 4:** Ajouter endpoint GET /mt5/market-status (ligne ~710)
- [ ] **STEP 5:** Ajouter fonction UI dans studio/studioapp.js
- [ ] **STEP 6:** Appeler fonction dans symbol-select listener
- [ ] **STEP 7:** Optionnel: CSS styling pour badge

---

## 🧪 TESTS IMMÉDIATS

### Test 1: Endpoint diagnostique
```bash
curl http://localhost:4000/mt5/market-status
# Retourner: { count, statuses: [{symbol, isOpen, market, ...}] }

curl http://localhost:4000/mt5/market-status?symbol=EURUSD
# Retourner: { symbol, isOpen, market, opensIn, closesIn, ... }
```

### Test 2: Blocker ticks fermés
```bash
# À marché fermé, envoyer:
curl -X POST http://localhost:4000/api/mt5/tick \
  -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","price":1.08,"bid":1.079,"ask":1.081,"volume":1000,"timestamp":'$(date +%s000)'}'

# Attendre réponse: { status: "blocked", reason: "market_closed" }
# Vérifier logs: "[TICK_BLOCKED] EURUSD @ ... — Market forex closed"
```

### Test 3: UI badge
- Ouvrir http://localhost:4000/studio
- Changer symbole
- Vérifier badge change couleur + texte

---

## 📊 SUMMARY FICHIERS

| Fichier | Action | Lines | Risk |
|---------|--------|-------|------|
| `lib/market-hours-checker.js` | CREATE | ~150 | Zéro |
| `server.js` (require) | EDIT +1 | 1 | Zéro |
| `server.js` (POST block) | EDIT +7 | 7 | Zéro |
| `server.js` (GET endpoint) | EDIT +26 | 26 | Zéro |
| `studio/studioapp.js` | EDIT +21 | 21 | Zéro |
| `studio/index-simple.html` | EDIT +1 | 1 | Zéro |
| `public/studio.css` | EDIT +20 | 20 | Zéro |

**Total: ~7 fichiers, ~176 lignes de code, ZÉRO refactor**

---

## 🚀 READY TO CODE?

Répondez d'abord aux **DECISION MATRIX** questions:
1. Symboles cibles?
2. Source horaires?
3. Comportement fermé?
4. Affichage UI?

Puis on code! ✅
