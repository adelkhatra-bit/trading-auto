# 🎯 CONCEPT VISUEL — Pourquoi Détection Marché?

---

## PROBLÈME ACTUEL (SANS DÉTECTION)

```
Timeline: Samedi 20h UTC
───────────────────────────────────────────

[Samedi 20h UTC]  
  ↓
MT5 EA envoie tick: { symbol: "EURUSD", price: 1.0850 }
  ↓
CandleManager.onTick() → crée/update candle
  ↓
Frontend affiche: "Chart OK, signal possible"
  ↓
❌ PROBLÈME: 
   - EURUSD marché FERMÉ (forex ferme ven 22h UTC)
   - Pas de liquidité réelle
   - Signal basé sur données mortes/stale
   - Risque trade fermé
```

---

## SOLUTION NOUVEAU (AVEC DÉTECTION)

```
Timeline: Samedi 20h UTC
───────────────────────────────────────────

[Samedi 20h UTC]  
  ↓
MT5 EA envoie tick: { symbol: "EURUSD", price: 1.0850 }
  ↓
✅ MarketHoursChecker.getStatus("EURUSD") 
   → { isOpen: false, market: "forex", closesIn: null, opensIn: "40h25m" }
  ↓
❌ Si fermé → BLOQUER tick (log + return)
  ↓
Frontend reçoit badge: "🔴 FOREX CLOSED (opens dimanche 22h UTC)"
  ↓
✅ RESULT:
   - Aucune bougie créée
   - Aucun signal généré
   - Utilisateur informé (badge rouge)
   - Zero risque
```

---

## COMPARAISON: AVANT vs APRÈS

### Scénario 1: Vendredi 16:00 UTC (US Cash fermé, Forex ouvert)

#### AVANT (sans détection)
```
AAPL: Post signal "BUY 180.50"
---
❌ US Equity marché FERMÉ depuis 16:00 UTC
❌ Pas de liquidité = slippage énorme
❌ Utilisateur ne sait pas

Result: Mauvaise trade possible
```

#### APRÈS (avec détection)
```
AAPL: Badge rouge "🔴 US EQUITY CLOSED (opens lundi)"
---
✅ Signal bloqué automatiquement
✅ Utilisateur informé
✅ Zéro opportunité mauvaise trade

Result: Protection passive
```

---

### Scénario 2: Dimanche 22:00 UTC (Forex vient ouvrir)

#### AVANT (sans détection)
```
Tick: { EURUSD: 1.0865 }
CandleManager: "Nouvelle bougie M1 créée"
---
❌ Peut débuter avec un seul tick = manque contexte
❌ Aucune vérification "marché réel"

Result: Bougie incomplète possible
```

#### APRÈS (avec détection)
```
Tick: { EURUSD: 1.0865 }
MarketHoursChecker: ✅ Dimanche 22h = Forex OPEN
CandleManager: "Nouvelle bougie M1 créée (marché ouvert confirmé)"
---
✅ Bougie créée avec confiance
✅ Liquidité réelle garantie
✅ Logs clairs pour audit

Result: H1/M15/M5/M1 fiables
```

---

## MULTI-SYMBOLS EXAMPLE

```
Dimanche 22:30 UTC (Nuit)
──────────────────────────────────────

Symbol: EURUSD
  ✅ getStatus() → { isOpen: true, market: "forex", session: "Sydney-Tokyo overlap" }
  ✅ Tick accepté → CandleManager process
  
Symbol: AAPL  
  ❌ getStatus() → { isOpen: false, market: "us-equity", opensIn: "4h30m" }
  ❌ Tick bloqué → Pas de candle
  
Symbol: BTC/USD
  ✅ getStatus() → { isOpen: true, market: "crypto", session: "24/7" }
  ✅ Tick accepté → CandleManager process

Frontend Display:
┌─────────────────────────────┐
│ Market Status Dashboard     │
├─────────────────────────────┤
│ EURUSD: 🟢 OPEN            │
│ AAPL:   🔴 CLOSED (4h30m)  │
│ BTC:    🟢 OPEN 24/7       │
└─────────────────────────────┘
```

---

## HORAIRES EXPLICATION (UTC)

### FOREX (24h/5)
```
Dimanche 22:00 UTC → Vendredi 22:00 UTC = OPEN

Exemple:
┌──────────┬──────────┬──────────┐
│ Dimanche │   Week   │ Samedi   │
├──────────┼──────────┼──────────┤
│ ✅ OPEN  │ ✅ OPEN  │ ❌ CLOSED│
│ 22h-*    │ 00h-22h  │ tout jour│
└──────────┴──────────┴──────────┘
```

### US EQUITY (9:30-16:00 ET = 13:30-20:00 UTC)
```
Weekdays ONLY (lun-ven)

Exemple:
┌───────────┬────────┬──────────┐
│  Lundi    │ Vendredi│ Samedi   │
├───────────┼────────┼──────────┤
│13:30-20:00│13:30-20│ ❌ CLOSED│
│ ✅ OPEN   │:00 ✅  │ weekend  │
└───────────┴────────┴──────────┘
```

### CRYPTO (24/7)
```
Toujours ouvert

Exemple:
┌──────┬──────┬──────┬──────┐
│Lundi │Mercredi│Vendredi│Dimanche│
├──────┼──────┼──────┼──────┤
│✅ ONopen │✅ OPEN│✅ OPEN│✅ OPEN │
└──────┴──────┴──────┴──────┘
```

---

## BLOC DECISION SIMPLE

```
User envoie tick pour AAPL le samedi 14:00 UTC:
───────────────────────────────────────────────

MarketHoursChecker.getStatus("AAPL"):
  1. Classe asset: equity
  2. Vérifie horaires US: 13:30-20:00 UTC weekdays
  3. Aujourd'hui: SAMEDI ≠ weekday
  4. Résultat: { isOpen: false, reason: "weekend" }

Action:
  IF isOpen = false:
    → Bloquer tick
    → Log: "[TICK_BLOCKED] AAPL samedi — US Equity fermé weekend"
    → Return response: { status: "blocked" }
    
  CandleManager.onTick() ← JAMAIS APPELÉ

Frontend:
  Badge: "🔴 US EQUITY CLOSED (opens lundi 13:30 UTC)"
```

---

## FLUX COMPLETE (LIVE EXAMPLE)

```
Timeline: Mercredi 19:00 UTC

[Mercredi 19:00 UTC]
  ↓
MT5 Bridge envoie: POST /api/mt5/tick
  {
    symbol: "EURUSD",
    price: 1.0876,
    bid: 1.0875,
    ask: 1.0877,
    volume: 1000,
    timestamp: 1712350800000
  }
  ↓
server.js POST /api/mt5/tick handler:
  ├─ Valide data ✅
  │  (symbol, price, volume OK)
  │
  ├─ ✅ NEW: Appelle marketHoursChecker.getStatus("EURUSD")
  │  └─ Résultat: 
  │     {
  │       isOpen: true,
  │       market: "forex",
  │       session: "London session",
  │       closesIn: "9h",
  │       opensIn: null
  │     }
  │
  ├─ Vérifies isOpen:
  │  ├─ IF true → Procéder normal
  │  └─ IF false → Return blocked
  │
  ├─ ✅ isOpen = true → Continue
  │
  ├─ Appelle CandleManager.onTick(EURUSD, 1.0876, ...)
  │  └─ Crée/update candle M1, M5, M15, H1, D1
  │
  ├─ Émet event: "candle:updated"
  │
  ├─ Broadcast SSE aux clients
  │  └─ studio/studioapp.js reçoit nouvelle candle
  │
  └─ Return response: { status: "ok", symbol: "EURUSD" }

Frontend (studio/studioapp.js):
  ├─ Reçoit SSE candle:updated event
  │
  ├─ ✅ DÉJÀ FAIT: updateMarketStatusBadge("EURUSD")
  │
  ├─ Badge affiche: "🟢 FOREX OPEN (closes in 9h)"
  │
  ├─ Chart affiche nouvelle candle M1, H1, etc
  │
  └─ Utilisateur peut générer signal (marché confirmé ouvert)
```

---

## 🔍 QUOI QUI SE PASSE EN COULISSE

### API Calls (très rapide)

```javascript
// marketHoursChecker.getStatus("EURUSD") — !!moins de 1ms!!

1. Classify asset:
   ├─ Symbol: "EURUSD"
   ├─ Regex check: /USD|EUR/ → forex
   └─ Return: "forex"

2. Get forex hours:
   ├─ Source: hardcoded ou API
   ├─ Lookup London session: [7, 0] → [16, 0]
   ├─ Current UTC time: 19:00
   ├─ 19:00 between [7, 0] and [16, 0]? NO
   │  ← mais check OTHER sessions
   ├─ New York session: [13, 30] → [22, 0]
   ├─ 19:00 between [13, 30] and [22, 0]? YES ✅
   └─ Return: { isOpen: true, session: "New York" }

3. Calculate times until:
   ├─ Now: 19:00 UTC
   ├─ New York closes: 22:00 UTC
   ├─ Diff: 3 hours
   └─ Return: { closesIn: "3h", opensIn: null }

TOTAL TIME: <1ms
```

---

## WHY THIS MATTERS

### Sans détection → RISKS
```
❌ Signaux basés données fermées (pas de liquidité)
❌ Slippage énorme à execution
❌ Overnight risk (marché ferme avant SL hit)
❌ Faux breakouts parfois samedi
```

### Avec détection → SAFE
```
✅ Signaux SEULEMENT si marché réel ouvert
✅ Liquidité garantie
✅ Pas de surprise overnight
✅ Feedback utilisateur (badge)
```

---

## RÉSUMÉ EN 1 PHRASE

**Détection marché = Gatekeeper** qui dit:
- ✅ "Marché ouvert, laisse la bougie se créer"
- ❌ "Marché fermé, jette le tick à la poubelle"

Result: **Trading fiable** basé données réelles seulement.
