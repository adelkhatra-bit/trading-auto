# 🎯 MATRICE DÉCISION — AVANT CODING

**Lire puis choisir pour CHAQUE section**

---

## 1️⃣ SYMBOLES CIBLES À TRADER

### Situation actuelle
- CandleManager: supporte illimité de symboles
- MT5 Bridge: envoie ticks réels pour chaque symbole
- Base: EURUSD (forex par défaut)

### À choisir: Qui trader réellement?

#### Option A: FOREX ONLY (conservative)
```
✅ EURUSD       → Forex 24h/5 (ouvert dim 22h UTC → ven 22h UTC)
✅ GBPUSD       → Forex 24h/5
✅ XAUUSD (Or)  → Forex hours (même que EURUSD)
```
**Avantage:** Horaires simples (24h/5), haute liquidité, pas de weekend  
**Choix si:** Préférez stabilité forex

#### Option B: FOREX + US EQUITY (diversifié)
```
✅ EURUSD       → Forex 24h/5
✅ XAUUSD       → Forex 24h/5
✅ AAPL, MSFT   → US Equity weekdays: 8:30-17:00 ET (13:30-20:00 UTC)
```
**Avantage:** Couvre 2 time zones, possibilités swing + intraday  
**Choix si:** Voulez diversifier actifs

#### Option C: DIVERSIFIÉ MAX (complet)
```
✅ EURUSD       → Forex 24h/5
✅ XAUUSD       → Forex 24h/5
✅ AAPL         → US Equity 8:30-17:00 ET (weekdays)
✅ BTC/USD      → Crypto 24/7 (toujours ouvert)
```
**Avantage:** Maximum flexibilité, 24/7 couverture  
**Choix si:** Stratégie vraiment multi-markets

---

**👉 VOTRE CHOIX:**
- [ ] A: Forex only
- [ ] B: Forex + US Equity
- [ ] C: Forex + Equity + Crypto

---

## 2️⃣ SOURCE DONNÉES HORAIRES

### Situation
- `market-session.js` a horaires hardcoded (peut être obsolète avec DST)
- API externe possible mais ajoute latence réseau

### À choisir: Source de vérité

#### Option 1: HARDCODED (actuellement dans market-session.js)
```javascript
const SESSIONS = {
  'London': [7, 0, 16, 0],      // 07:00-16:00 UTC
  'NewYork': [13, 30, 22, 0]    // 13:30-22:00 UTC
};
```
**Avantage:** Zéro latence, connu et prévisible  
**Risque:** DST changes (mars/mai/octobre) non automatiques  
**Choix si:** Vous acceptez mise à jour manuelle 2x/an

#### Option 2: API EXTERNAL (world.timeapi.org)
```javascript
const response = await fetch('http://worldtimeapi.org/api/timezone/Etc/UTC');
const utcTime = response.json().datetime;
// Calculer dynamiquement si ouvert
```
**Avantage:** Toujours correct, gère DST automatique  
**Risque:** ~0.5-1s latence réseau par check  
**Coût:** 1 requête HTTP par POST /api/mt5/tick = traitement plus lent  
**Choix si:** Voulez "fire and forget" sans maintenance

#### Option 3: HYBRIDE RECOMMANDÉ ⭐
```javascript
// Logique:
// 1. Hardcoded UTC pour tous les calculs (rapide)
// 2. Check API externe 1x par heure en background
// 3. Sync horaires si changement détecté
```
**Avantage:** Rapide (99% cas) + correct (gère DST)  
**Coût:** 1 requête/heure max (negligible)  
**Choix si:** Idéal pour production (recommandé ✅)

---

**👉 VOTRE CHOIX:**
- [ ] 1: Hardcoded (maintenance 2x/an acceptable)
- [ ] 2: API externe (latence acceptable)
- [ ] 3: Hybride (recommandé)

---

## 3️⃣ COMPORTEMENT MARCHÉ FERMÉ

### Situation
- POST /api/mt5/tick arrive → marché fermé
- Quoi faire?

#### Option A: SILENT REJECT (recommandé)
```javascript
// Comportement:
if (!marketStatus.isOpen) {
  console.log(`[INFO] ${symbol} blocked — market closed`);
  return res.json({ status: 'blocked', reason: 'market_closed' });
}
// CandleManager.onTick() NOT CALLED
// = Pas de bruit, pass silencieux
```
**Avantage:** Zéro stress, logs propres, EA pas confusé  
**Risque:** Aucun  
**Choix si:** Vous voulez système stable (recommandé ✅)

#### Option B: HTTP REJECTION (visible)
```javascript
// Comportement:
if (!marketStatus.isOpen) {
  return res.status(403).json({ error: 'Market closed for ' + symbol });
}
// EA reçoit 403 = error handling nécessaire
```
**Avantage:** Erreur explicite, EA peut réagir  
**Risque:** Crée noise, EA peut spam retries  
**Choix si:** Voulez feedback explicite à MT5

#### Option C: QUEUE & REPLAY (complexe)
```javascript
// Comportement:
if (!marketStatus.isOpen) {
  queue.push({ symbol, price, timestamp });
  // Replay plus tard quand marché ouvre
}
```
**Avantage:** Aucune donnée perdue  
**Risque:** Complexe, peut créer décalages temps  
**Choix si:** Données très critiques

---

**👉 VOTRE CHOIX:**
- [ ] A: Silent reject (recommandé)
- [ ] B: HTTP 403 rejection
- [ ] C: Queue & replay

---

## 4️⃣ AFFICHAGE FRONTEND

### Situation
- Frontend (studio/studioapp.js) doit montrer état marché
- Quoi afficher pendant fermé?

#### Option A: MINIMAL (badge couleur)
```
┌─────────────────────────────────┐
│ EURUSD  🟢 OPEN                 │
├─────────────────────────────────┤
│ [Chart]                         │
└─────────────────────────────────┘

// Fermé:
│ EURUSD  🔴 CLOSED (opens in 2h) │
```
**Avantage:** Simple, pas intrusive  
**Choix si:** Design minimaliste

#### Option B: AVEC AVERTISSEMENT
```
┌─────────────────────────────────┐
│ ⚠️ Market CLOSED until 22:00 UTC │
├─────────────────────────────────┤
│ (No signals generated)          │
│ [Chart greyed out]              │
└─────────────────────────────────┘
```
**Avantage:** Clair, évite confusion  
**Choix si:** Voulez éviter erreurs utilisateur

#### Option C: AVEC COUNTDOWN
```
┌─────────────────────────────────┐
│ Market closes: 2h 15m remaining │
├─────────────────────────────────┤
│ Next: London opens tomorrow 07:00│
│ [Chart live]                    │
└─────────────────────────────────┘
```
**Avantage:** Info maximale, user informed  
**Choix si:** UX premium, users aiment countdown

---

**👉 VOTRE CHOIX:**
- [ ] A: Badge simple couleur
- [ ] B: Badge + warning text
- [ ] C: Badge + countdown + next session

---

## 📋 RÉSUMÉ CHOIX

Recopier vos réponses ici:

```
QUESTION 1 - Symboles cibles:
Réponse: [ ]

QUESTION 2 - Source horaires:
Réponse: [ ]

QUESTION 3 - Comportement fermé:
Réponse: [ ]

QUESTION 4 - Affichage UI:
Réponse: [ ]
```

---

## 🚀 PROCHAINE ÉTAPE

Une fois vos choix confirmés:

1. ✅ Créer `lib/market-hours-checker.js` (basé vos choix)
2. ✅ Intégrer dans `server.js`
3. ✅ Modifier `studio/studioapp.js` (UI)
4. ✅ Tests avec Postman

**Pas de coding avant validation** ✅

---

## ⏱️ TEMPS ESTIMÉ (avec validations)

- Décisions: 5-10 min (maintenant)
- Coding: 45-60 min
- Tests: 30-45 min
- **Total: 1.5-2h**
