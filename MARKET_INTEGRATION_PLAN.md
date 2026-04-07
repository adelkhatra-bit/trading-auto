# 📋 PLAN INTÉGRATION DÉTECTION MARCHÉ OUVERT/FERMÉ

**Date:** 2026-04-03  
**Phase:** P2 - Détection Marché (Post CandleManager Phase 1)  
**Scope:** Modifications isolées UNIQUEMENT — zéro refactor global

---

## 🎯 OBJECTIF

Bloquer les signaux et candles en marché fermé (forex, équités, crypto, métaux)  
✅ Pas de suppression de code  
✅ Pas de refactor  
✅ Modifications localisées uniquement

---

## 📍 ARCHITECTURE ACTUELLE (STATE OF ART)

### Modules Existants
- ✅ **CandleManager** (`lib/candle-manager.js`) — reçoit ticks en temps réel
- ✅ **server.js** — routes `/api/mt5/tick` (POST) pour ticks réels
- ✅ **market-session.js** (`tradingview-analyzer/`) — horaires sessions FOREX/US Equity
- ✅ **DataSourceManager** (`lib/data-source-manager.js`) — récupère données réelles MT5

### Flux Actuel (multi-symbol)
```
MT5 EA (Bridge)
  ↓
POST /api/mt5/tick {symbol, price, bid, ask, volume, timestamp}
  ↓
server.js → CandleManager.onTick()
  ↓
CandleManager (multi-timeframes: D1, H1, M15, M5, M1)
  ↓
Emit: 'candle:closed' → broadcast SSE
  ↓
Frontend: studio/studioapp.js reçoit bougie fermée
```

---

## 🔧 PLAN IMPLÉMENTATION (4 ÉTAPES)

### **ÉTAPE 1: Créer module MarketHoursChecker**
**Fichier:** `lib/market-hours-checker.js` (NOUVEAU)  
**Responsabilité:** Déterminer état du marché par symbole/classe d'actif

```javascript
// Pseudo-code structure (à valider avant coding)
class MarketHoursChecker {
  
  // Input: symbol = "EURUSD", "XAUUSD", "AAPL", "BTC" etc
  // Output: { isOpen: boolean, market: string, session: string, ... }
  
  getMarketStatus(symbol) {
    const assetClass = this.classifyAsset(symbol); // forex|equity|metal|crypto
    
    switch (assetClass) {
      case 'forex':
        return this.checkForexSession(symbol);  // 24h/5 (dim 22h UTC → ven 22h UTC)
      case 'equity':
        return this.checkUSEquitySession();     // 8:30-17:00 ET weekdays only
      case 'metal':
        return this.checkMetalSession();        // XAUUSD = forex hours
      case 'crypto':
        return this.checkCryptoSession();       // 24/7 mais avec alertes volatilité
    }
  }
  
  // Helper: déterminer classe d'actif
  classifyAsset(symbol) {
    const s = symbol.toUpperCase();
    if (/XAU|XAG/.test(s)) return 'metal';
    if (/BTC|ETH|XRP/.test(s)) return 'crypto';
    if (/AAPL|MSFT|GOOGL|SPY|QQQ/.test(s)) return 'equity';
    return 'forex';  // Default: EURUSD, GBPUSD, etc
  }
}
```

**Validation:** Choisir source horaires (internet ≠ hardcoded)

---

### **ÉTAPE 2: Intégrer dans POST /api/mt5/tick**
**Fichier:** `server.js` (modification localisée)  
**Ligne:** ~500 (zone POST /api/mt5/tick)

**Action:** 
1. Avant `candleManager.onTick()` 
2. Vérifier `marketHoursChecker.getMarketStatus(symbol)`
3. SI marché fermé → log + return (bloquer silent)
4. SI marché ouvert → proceed normal

```javascript
// PSEUDO-CODE (à intégrer dans POST /api/mt5/tick)
app.post('/api/mt5/tick', async (req, res) => {
  const { symbol, price, bid, ask, volume, timestamp } = req.body;
  
  // NEW: Market hours check
  const marketStatus = marketHoursChecker.getMarketStatus(symbol);
  if (!marketStatus.isOpen) {
    console.log(`[BLOCKED] ${symbol} tick rejeté — marché fermé (${marketStatus.market})`);
    return res.json({ status: 'blocked', reason: 'market_closed' });
  }
  
  // EXISTING: Process normally
  candleManager.onTick(symbol, price, bid, ask, volume, timestamp);
  // ... rest of code
});
```

---

### **ÉTAPE 3: Ajouter endpoint de diagnostic**
**Fichier:** `server.js` (nouvelle route)  
**Endpoint:** `GET /api/market-status` ou `GET /mt5/market-status`

**Responsabilité:** Frontend peut vérifier avant affichage signal

```javascript
// NEW ROUTE
app.get('/mt5/market-status', (req, res) => {
  const { symbol } = req.query; // ?symbol=EURUSD
  
  if (!symbol) {
    // Retourner état de tous les symboles en mémoire
    const allSymbols = Object.keys(marketStore.bySymbol);
    const statuses = allSymbols.map(s => ({
      symbol: s,
      ...marketHoursChecker.getMarketStatus(s),
      lastTickTime: marketStore.bySymbol[s]?.updatedAt
    }));
    return res.json({ statuses });
  }
  
  // Single symbol
  const status = marketHoursChecker.getMarketStatus(symbol);
  return res.json({ symbol, ...status });
});
```

---

### **ÉTAPE 4: Préparer base pour graphique (TradingView-like)**
**Fichier:** `studio/studioapp.js` (modification UI)  
**Concept:** Afficher état marché ouvert/fermé sur le chart

**Éléments à ajouter:**
- State badge: `Market: [OPEN | CLOSED]` 
- Warning: Si fermé → afficher "Marché fermé — pas de signal"
- Color code: Green (ouvert) | Gray (fermé)

```javascript
// PSEUDO-CODE studio/studioapp.js
function displayMarketStatus(symbol) {
  fetch(`/mt5/market-status?symbol=${symbol}`)
    .then(r => r.json())
    .then(data => {
      const badge = document.getElementById('market-status-badge');
      if (data.isOpen) {
        badge.className = 'badge-open';
        badge.textContent = `Market: OPEN (${data.session})`;
      } else {
        badge.className = 'badge-closed';
        badge.textContent = `Market: CLOSED (opens ${data.opensIn})`;
      }
    });
}

// Call whenever symbol changes
symbolSelect.addEventListener('change', (e) => {
  displayMarketStatus(e.target.value);
  // ... existing code
});
```

---

## 📊 STRUCTURE FICHIERS À CRÉER/MODIFIER

| Fichier | Action | Raison |
|---------|--------|--------|
| `lib/market-hours-checker.js` | CREATE | Module central détection marché |
| `server.js` | EDIT (POST /api/mt5/tick) | Bloquer ticks marché fermé |
| `server.js` | EDIT (ajouter route) | New: GET /mt5/market-status |
| `studio/studioapp.js` | EDIT (UI) | Afficher état marché |
| `public/studio.css` | EDIT (optionnel) | Style badge marché |

**Total impact:** ~150 lignes de code nouveau  
**Risque refactor:** ✅ ZÉRO — modifications isolées

---

## ✅ VALIDATION AVANT CODING

### 1️⃣ Source données horaires
- Option 1: Hardcoded UTC (risque: changements DST)
- Option 2: Interroger API externe (http://worldtimeapi.org)
- Option 3: Hybride (hardcoded + check périodique)

**Recommandation:** Option 3 (fiable + performant)

### 2️⃣ Symboles multi-class
- Vérifier quels symboles sont en portefeuille actuel
- Forex: EURUSD, GBPUSD, XAUUSD
- US Equity: AAPL, MSFT, SPY?
- Crypto: BTC, ETH?

**Action:** Lister symboles cibles

### 3️⃣ Comportement "marché fermé"
- Bloquer silenciously (log seulement)? ← Recommandé
- Retourner erreur HTTP? (plus visible mais noise)
- Buffer les ticks pour lecture ultérieure? (complexe)

**Recommandation:** Bloquer silencieusement + log INFO

### 4️⃣ Tests après intégration
- [ ] POST /api/mt5/tick pendant marché fermé → vérifier rejet
- [ ] GET /mt5/market-status?symbol=EURUSD → vérifier JSON correct
- [ ] Vérifier CandleManager reçoit SEULEMENT ticks marché ouvert
- [ ] Vérifier SSE frontend affiche badge correct

---

## 🚀 PROCHAINES ACTIONS

### Phase 2a (Détection)
1. ✅ Valider plan (vos choix: source horaires + symboles cibles)
2. ⏳ Créer `market-hours-checker.js`
3. ⏳ Intégrer dans `server.js` (POST + GET route)
4. ⏳ Tester avec curl/Postman

### Phase 2b (Affichage graphique)
5. ⏳ Modifier `studio/studioapp.js` pour badge marché
6. ⏳ Préparer data structure pour TradingView-like chart
7. ⏳ Tests UI

### Phase 3 (Validation multi-symbols)
8. ⏳ Vérifier CandleManager multi-symbols en conditions réelles
9. ⏳ Valider persistance candles (fermé/ouvert)

---

## 📌 QUESTIONS AVANT CODING

1. **Symboles cibles prioritaires?** (quels assets trader réellement?)
   - [ ] EURUSD, GBPUSD (forex)
   - [ ] XAUUSD (métal)
   - [ ] AAPL, MSFT (équités? — lequel?)
   - [ ] BTC (crypto?)

2. **Source horaires?**
   - [ ] Hardcoded (rapide, DST problème)
   - [ ] API externe (fiable, latence)
   - [ ] Hybride (recommandé)

3. **Comportement marché fermé?**
   - [ ] Bloquer silencieusement (log INFO)
   - [ ] Rejeter avec HTTP 403
   - [ ] Buffer et remettre en queue

---

## 📝 RÉSUMÉ

✅ **Plan:** 4 étapes isolées  
✅ **Impact:** ~150 lignes de code nouveau  
✅ **Refactor:** ZÉRO  
✅ **Risque:** Minimal (modifications localisées)  
✅ **Temps estimé:** 2-3h (avec validations)

**Status:** ⏳ En attente de réponses questions de validation
