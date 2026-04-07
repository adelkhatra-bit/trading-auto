# PLAN RÉVISÉ — SYSTÈME MULTI-AGENTS INTELLIGENT ET COORDONNÉ

**Document: Architecture de trading avec équipe intelligente**
**Date: 3 avril 2026**
**Statut: PLAN D'IMPLÉMENTATION**

---

# 🎯 VISION TRANSFORMÉE

**AVANT (Monitoring technique):**
```
MT5 → orchestrator → [agents parallèles] → decision
(On affiche les agents, c'est tout)
```

**APRÈS (Équipe intelligente coordonnée):**
```
MT5 → Chaîne d'agents avec dépendances
    → Chaque agent fait son job
    → Les agents communiquent entre eux
    → Les résultats influencent les suivants
    → On peut bloquer/arrêter à tout moment
    → Dashboard = cockpit de pilotage
    → Audit = mémoire intelligente
```

---

# PARTIE A — RÔLES DÉTAILLÉS DES 23 AGENTS

## 🔍 ÉTAPE 1: INPUT DATA VALIDATION

### **1. dataSourceManager** 
**Rôle:** Maître des sources — règle: MT5 > TradingView > RIEN

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Source données centralisée |
| **Input** | Demande: quel prix pour XAUUSD? |
| **Output** | {price, source: MT5/TV, timestamp, valid: true} |
| **Appelé par** | TOUT LE MONDE (premier maillon) |
| **Appelle** | marke-store, fetchYahooPrice (fallback) |
| **Peut bloquer?** | ✅ OUI — invalide la chaîne si pas de prix |
| **Poids décision** | 10/10 (fondamental) |
| **Intégration Audit** | Chaque appel: {from: dataSourceManager, source_selected, price_value, validity} |

---

### **2. syncManager**
**Rôle:** Police des données — valide que TOUT est cohérent

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Détecte incohérences price/chart/analysis |
| **Input** | {price_from_mt5, price_from_tv, chart_data, bid_ask_spread} |
| **Output** | {synchronized: true/false, inconsistencies: [...], recommendation: proceed/retry/halt} |
| **Appelé par** | orchestrator (après dataSourceManager) |
| **Appelle** | dataSourceManager.validatePrice() |
| **Peut bloquer?** | ✅ OUI — peut demander retry si incohérence |
| **Poids décision** | 9/10 (sécurité critique) |
| **Intégration Audit** | {from: syncManager, checks_performed: [...], result: pass/fail, inconsistencies_found: [...]} |

---

## 📊 ÉTAPE 2: TECHNICAL ANALYSIS PIPELINE

### **3. technicalAgent**
**Rôle:** Analyste technique réel — RSI/EMA/ATR sur données LIVE

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Structure + indicateurs (RSI/EMA/ATR live) |
| **Input** | {symbol, price, bid_ask, ohlc, timeframe, rsi_value, ema_values, atr_value} |
| **Output** | {direction: LONG/SHORT/NEUTRAL, score: 0-100, signals: [...], structure: {...}} |
| **Appelé par** | orchestrator (après dataSourceManager OK) |
| **Appelle** | symbol-normalizer, calcEMA(), calcRSI() |
| **Peut bloquer?** | ❌ NON — donne une opinion, pas un verdict |
| **Poids décision** | 8/10 (technique fondamentale) |
| **Intégration Audit** | {from: technicalAgent, symbol, direction, score, signals_found: [...], rsi_value, ema_state} |

---

### **4. chartEngine**
**Rôle:** Lecteur graphique — valide les patterns visuels de technicalAgent

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Patterns graphiques + validation structure |
| **Input** | {ohlc_data, timeframe, technicalAgent_output} |
| **Output** | {patterns_found: [...], bos_detected: true/false, fvg_zones: [...], confidence: 0-100, tech_agent_validated: true/false} |
| **Appelé par** | orchestrator (après technicalAgent) |
| **Appelle** | trading-core.detectStructure() |
| **Peut bloquer?** | ✅ PARTIELLEMENT — peut demander caution si pattern faible |
| **Poids décision** | 7/10 (confirmation technique) |
| **Intégration Audit** | {from: chartEngine, patterns: [...], bos: true/false, fvg_count, tech_agent_confidence_check} |

---

### **5. trading-core**
**Rôle:** Détecteur de structure complète — BOS/FVG/Liquidity/Support

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Structures avancées (Break of Structure, Fair Value Gaps, Liquidity) |
| **Input** | {ohlc, structure_data, previous_swing_levels} |
| **Output** | {structure: BOS/NORMAL, fvgs: [...], liquidity_zones: [...], support_levels: [...], confidence: 0-100} |
| **Appelé par** | chartEngine (dependency) |
| **Appelle** | Aucun agent (analyse pure) |
| **Peut bloquer?** | ❌ NON — data enrichissante |
| **Poids décision** | 6/10 (détail technique) |
| **Intégration Audit** | {from: tradingCore, structure_type, fvg_count, liquidity_zones_identified} |

---

### **6. timeframe-consensus**
**Rôle:** Arbitre multi-timeframe — consensus entre H1/H4/D1

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Décision multi-TF hiérarchique |
| **Input** | {technicalAgent output pour H1, H4, D1, W1} |
| **Output** | {globalBias: BULLISH/BEARISH, dominantTF: D1, decision: LONG/SHORT/ATTENDRE, strength: FORT/MODERE/FAIBLE, conflict: true/false} |
| **Appelé par** | orchestrator (fusion technique) |
| **Appelle** | technicalAgent (pour chaque TF) |
| **Peut bloquer?** | ✅ OUI — si conflit majeur, demande ATTENDRE |
| **Poids décision** | 8/10 (puissant si consensus) |
| **Intégration Audit** | {from: timeframeConsensus, tf_analysed: [H1, H4, D1], dominant_tf, conflict_detected} |

---

## 🌍 ÉTAPE 3: MACRO + SENTIMENT CHECK

### **7. macroAgent**
**Rôle:** Sentinelle économique — détecte risques macro

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Calendrier économique + impact analyse |
| **Input** | {symbol, current_time, economic_calendar} |
| **Output** | {riskLevel: LOW/MEDIUM/HIGH/CRITICAL, nextEvent: {...}, impactAnalysis: {...}, recommendation: proceed/caution/halt} |
| **Appelé par** | orchestrator (parallèle avec newsAgent) |
| **Appelle** | Aucun agent |
| **Peut bloquer?** | ✅ OUI — peut forcer ATTENDRE si NFP dans 1h |
| **Poids décision** | 8/10 (risque critique ignoré = suicide) |
| **Intégration Audit** | {from: macroAgent, riskLevel, nextEvent_name, recommendation} |

---

### **8. newsAgent**
**Rôle:** Sentiment market — actualités + tendances

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Sentiment analyse + news screen + Twitter trends |
| **Input** | {symbol, category (forex/crypto/metals), currentTime} |
| **Output** | {sentiment: BULLISH/BEARISH/NEUTRAL, sentiment_score: -100 to +100, upcomingEvents: [...], criticalNews: [...], volatilityWarning: true/false} |
| **Appelé par** | orchestrator (parallèle avec macroAgent) |
| **Appelle** | Aucun agent (web fetch) |
| **Peut bloquer?** | ✅ OUI — si volatility warning critique |
| **Poids décision** | 7/10 (sentiment peut infléchir score) |
| **Intégration Audit** | {from: newsAgent, sentiment_score, critical_news_count, volatility_warning} |

---

### **9. news-intelligence** (À consolider vers newsAgent)
**Rôle:** Doublure de newsAgent — obsolète

| Propriété | Valeur |
|-----------|--------|
| **Statut** | ⚠️ À FUSIONNER avec newsAgent |
| **Action** | Utiliser newsAgent uniquement |

---

### **10. fear-index**
**Rôle:** Jauge peur marché — VIX + stress indicator

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | VIX level + market stress |
| **Input** | Aucun (fetch VIX directement) |
| **Output** | {vix: number, level: TRÈS_BAS/BAS/MODERE/ELEVE/EXTREME, tradingNote: string} |
| **Appelé par** | orchestrator (context) |
| **Appelle** | Yahoo Finance (fallback) |
| **Peut bloquer?** | ❌ NON — contextuel seulement |
| **Poids décision** | 5/10 (contexte ambiant) |
| **Intégration Audit** | {from: fearIndex, vix_value, fear_level} |

---

## ✅ ÉTAPE 4: VALIDATION GATES

### **11. tradeValidator**
**Rôle:** Classeur de trade — LIVE / CONDITIONNEL / OBSOLÈTE

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Classe le trade (LIVE/CONDITIONNEL/OBSOLETE) |
| **Input** | {trade{entry, sl, tp}, currentPrice} |
| **Output** | {status: LIVE/CONDITIONNEL/OBSOLETE, distance_to_entry_pct, valid: true/false, reason, probability} |
| **Appelé par** | orchestrator (après technique OK) |
| **Appelle** | Aucun agent |
| **Peut bloquer?** | ✅ OUI — si status=OBSOLETE, refuse le trade |
| **Poids décision** | 9/10 (verdict d'exécutabilité) |
| **Intégration Audit** | {from: tradeValidator, trade_status, distance, valid, probability} |

---

### **12. riskManager**
**Rôle:** Gestionnaire de risque — taille position, leverage, R:R

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Position sizing + leverage control |
| **Input** | {accountBalance, riskPercent, entryPrice, stopPrice, direction} |
| **Output** | {quantity, riskAmount_USD, leverage, riskReward: X:1, valid: true/false, warning: string/null} |
| **Appelé par** | orchestrator (après validator) |
| **Appelle** | Aucun agent |
| **Peut bloquer?** | ✅ OUI — si leverage > max ou risk > 5% |
| **Poids décision** | 10/10 (protection capitale) |
| **Intégration Audit** | {from: riskManager, quantity, leverage, risk_pct, valid} |

---

### **13. setupClassifier**
**Rôle:** Identificateur de pattern — classe le setup (LIQUIDITY/BOS/FVG/SR)

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Classification pattern + confidence |
| **Input** | {trade, context{direction, levels}} |
| **Output** | {setupType: LIQUIDITY_SWEEP / BOS / FVG / SUPPORT_RESISTANCE / TREND / REVERSAL / CONSOLIDATION, confidence: 0-100, riskProfile: string} |
| **Appelé par** | supervisor (enrichissement) |
| **Appelle** | Aucun agent |
| **Peut bloquer?** | ❌ NON — information additionnelle |
| **Poids décision** | 6/10 (classification, pas critère GO/NON) |
| **Intégration Audit** | {from: setupClassifier, setup_type, confidence} |

---

### **14. market-state**
**Rôle:** Détecteur d'état marché — CLEAN / CAUTION / DANGEROUS / QUIET

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | État marché (volatilité, spread, structure) |
| **Input** | {atr, atrAvg, spread, price, rsi, volume, recentRange} |
| **Output** | {state: CLEAN/CAUTION/DANGEROUS/QUIET, dangerScore: 0-100, tradingNote: string, recommendation: proceed/caution/halt} |
| **Appelé par** | orchestrator (contexte) |
| **Appelle** | Aucun agent |
| **Peut bloquer?** | ✅ PARTIELLEMENT — si state=DANGEROUS, demande caution |
| **Poids décision** | 7/10 (environnement critique) |
| **Intégration Audit** | {from: marketState, state, dangerScore, recommendation} |

---

### **15. supervisor**
**Rôle:** Maître sécurité — valide TOUS les gating ensemble

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Validation agrégée + final check |
| **Input** | {dataSourceManager result, syncManager result, technicalAgent result, tradeValidator result, riskManager result, macroAgent result, newsAgent result} |
| **Output** | {allowed: true/false, reason: string, gatePasses: {dataSource: ✅/❌, sync: ✅/❌, validation: ✅/❌, risk: ✅/❌, macro: ✅/❌, sentiment: ✅/❌}, warnings: [...]} |
| **Appelé par** | orchestrator (avant décision) |
| **Appelle** | Tous les agents (pour vérifier leur output) |
| **Peut bloquer?** | ✅ OUI — si un gate fail, REFUSE le trade |
| **Poids décision** | 10/10 (verdict GO/NOGO) |
| **Intégration Audit** | {from: supervisor, allowed, gatePasses_summary, warnings_count} |

---

## 🎯 ÉTAPE 5: STRATEGY ADAPTATION

### **16. strategyManager**
**Rôle:** Adapteur de stratégie — applique SNIPER/SCALP/SWING/INTRADAY

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Adaptation trade selon mode actif |
| **Input** | {trade{entry, sl, tp}, strategy_mode: SNIPER/SCALP/INTRADAY/SWING} |
| **Output** | {trade_adapted{entry, sl, tp_adjusted, max_hold_time}, strategy_applied: string, msg: string} |
| **Appelé par** | orchestrator (après risk manager) |
| **Appelle** | Aucun agent |
| **Peut bloquer?** | ❌ NON — adaptation, pas blocage |
| **Poids décision** | 5/10 (ajustement) |
| **Intégration Audit** | {from: strategyManager, strategy_mode, tp_adjustment} |

---

## 🎬 ÉTAPE 6: FINAL DECISION

### **17. orchestrator**
**Rôle:** Décideur final — fusionne TOUT et décide LONG/SHORT/ATTENDRE

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Fusion de tous les résultats + décision finale |
| **Input** | {MT5 raw payload + résultats de TOUS les agents} |
| **Output** | {direction: LONG/SHORT/ATTENDRE, score: 0-100, strength: FORT/MODERE/FAIBLE, trade_final: {...}, execution_probability: 0-100, agent_consensus_report: {...}} |
| **Appelé par** | server.js (endpoint POST /mt5) |
| **Appelle** | Tous les agents |
| **Peut bloquer?** | ❌ NON — produit toujours une décision |
| **Poids décision** | 10/10 (c'est LA décision) |
| **Intégration Audit** | {from: orchestrator, decision_direction, score, agents_called, execution_probability} |

---

## 🔧 ÉTAPE 7: ERROR HANDLING

### **18. repairAgent** (NOUVEAU)
**Rôle:** Détecteur + classificateur d'erreurs — passif, écoute les erreurs

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Capture erreurs + classification + rapport |
| **Input** | Écoute les logs (passif) |
| **Output** | {error_id, error_type: CRITICAL/ERROR/WARNING/INCOMPLETE, agent_source, impact, recommendation, auto_fix_possible: yes/no} |
| **Appelé par** | Aucun (passif) |
| **Appelle** | Aucun (passif) |
| **Peut bloquer?** | ❌ NON (passif) |
| **Poids décision** | 0/10 (non décision) |
| **Intégration Audit** | {from: repairAgent, error_type, severity, agent_source, recommendation} |

---

## 🌐 STATE + PERSISTENCE

### **19. stateManager**
**Rôle:** Mémoire courte — localStorage persistence

| Propriété | Valeur |
|-----------|--------|
| **Spécialité** | Sauvegarde état système en localStorage |
| **Input** | {key, value} ou {updates{...}} |
| **Output** | {ok, saved_keys: [...]} |
| **Appelé par** | Frontend + orchestrator |
| **Appelle** | localStorage |
| **Peut bloquer?** | ❌ NON (utility) |
| **Poids décision** | 0/10 |
| **Intégration Audit** | {from: stateManager, keys_saved: [...]} |

---

## 📦 AGENTS OPTIONNELS / LEGACY

### **20. chartEngine** (OPTIONNEL)
**Rôle:** Gestion graphique temps réel

| Propriété | Valeur |
|-----------|--------|
| **Statut** | Optionnel (polling désactivé) |
| **Utilisé** | Seulement si besoin affichage avancé |

---

### **21. designerAgent** (OPTIONNEL)
**Rôle:** Optimization UI/UX

| Propriété | Valeur |
|-----------|--------|
| **Statut** | Module design (non exécuté) |
| **Utilisé** | Documentation capability seulement |

---

### **22. qaTester** (OPTIONNEL)
**Rôle:** Suite test automatisée

| Propriété | Valeur |
|-----------|--------|
| **Statut** | Dev mode only |
| **Utilisé** | Tests en développement |

---

### **23. continuous-loop** (LEGACY)
**Rôle:** Boucle continue orchestration

| Propriété | Valeur |
|-----------|--------|
| **Statut** | ❌ Remplacé par orchestrator.run() |
| **Mode** | Documenté comme legacy |

---

### **24. coordinator** (À nettoyer)
**Rôle:** Fallback orchestration

| Propriété | Valeur |
|-----------|--------|
| **Statut** | ⚠️ Yahoo fallback dépréciée |
| **Action** | Utiliser dataSourceManager uniquement |

---

### **25. news-intelligence** (À consolider)
**Rôle:** Doublure newsAgent

| Propriété | Valeur |
|-----------|--------|
| **Statut** | Fusionner vers newsAgent |

---

# PARTIE B — PIPELINE COMPLET AVEC DÉPENDANCES

## 🔄 FLUX D'EXÉCUTION RÉEL

```
┌─────────────────────────────────────────────────────────────────┐
│ ENTRÉE: MT5 BRIDGE envoie {symbol: XAUUSD, price: 2412.50, ...} │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
    ┌─ ÉTAPE 1: DATA SOURCING
    │
    ├─→ dataSourceManager
    │   Input: symbol
    │   Output: {price: 2412.50, source: MT5, valid: true}
    │   ├─ Peut bloquer: OUI (invalid price)
    │   └─ Continue → syncManager
    │
    ├─→ syncManager
    │   Input: {price, bid_ask, chart_data}
    │   Output: {synchronized: true, inconsistencies: []}
    │   ├─ Peut bloquer: OUI (major inconsist)
    │   └─ Continue → Technical Pipeline
    │
    ├─ ÉTAPE 2: TECHNICAL ANALYSIS CHAIN
    │
    ├─→ technicalAgent [PARALLÈLE]
    │   Input: {price, rsi, ema, atr, symbol}
    │   Output: {direction: LONG, score: 72, signals: [...]}
    │   └─ Envoie → chartEngine
    │
    ├─→ chartEngine [ATTEND technicalAgent]
    │   Input: {technicalAgent.output, ohlc}
    │   Output: {patterns: [...], tech_validated: true}
    │   └─ Envoie → trading-core
    │
    ├─→ trading-core [serial après chartEngine]
    │   Input: {ohlc, structure}
    │   Output: {fvgs: [...], bos: true, liquidity: [...]}
    │   └─ Retour → timeframe-consensus
    │
    ├─→ timeframe-consensus [parallèle multi-TF]
    │   Input: {tech results pour H1/H4/D1}
    │   Output: {consensus: BULLISH, dominant_tf: D1, conflict: false}
    │   └─ Continue
    │
    ├─ ÉTAPE 3: MACRO + SENTIMENT [PARALLÈLE]
    │
    ├─→ macroAgent
    │   Input: {symbol, calendar}
    │   Output: {riskLevel: MEDIUM, nextEvent: NFP+5h}
    │   ├─ Peut bloquer: OUI (si CRITICAL)
    │   └─ Continue ou HALT
    │
    ├─→ newsAgent
    │   Input: {symbol}
    │   Output: {sentiment: BULLISH, score: +65}
    │   ├─ Peut bloquer: OUI (si volatility warning)
    │   └─ Continue ou CAUTION
    │
    ├─→ fear-index
    │   Input: Aucun
    │   Output: {vix: 18, level: BAS}
    │   └─ Context only
    │
    ├─ ÉTAPE 4: TRADE VALIDATION GATES
    │
    ├─→ tradeValidator
    │   Input: {trade{entry: 2412.50, sl, tp}, price: current}
    │   Output: {status: LIVE, distance: 0.2%, valid: true}
    │   ├─ Peut bloquer: OUI (si OBSOLETE)
    │   └─ Continue ou REFUSE
    │
    ├─→ market-state
    │   Input: {atr, spread, volume}
    │   Output: {state: CLEAN, recommendation: proceed}
    │   └─ Context
    │
    ├─ ÉTAPE 5: RISK + SETUP CHECK
    │
    ├─→ riskManager
    │   Input: {entry, sl, account, risk%}
    │   Output: {qty: 0.5, leverage: 5x, valid: true}
    │   ├─ Peut bloquer: OUI (if leverage > max)
    │   └─ Continue ou ADJUST
    │
    ├─→ setupClassifier
    │   Input: {trade}
    │   Output: {setupType: LIQUIDITY_SWEEP, confidence: 85}
    │   └─ Enrichissement
    │
    ├─ ÉTAPE 6: FINAL VALIDATION GATE
    │
    └─→ supervisor
        Input: {ALL previous outputs}
        Output: {
          allowed: true,
          gatePasses: {
            dataSource: ✅,
            sync: ✅,
            technical: ✅,
            validation: ✅,
            risk: ✅,
            macro: ✅,
            sentiment: ✅
          }
        }
        └─ Continue → orchestrator
           ou HALT if any gate fails

        ║
        ▼

    ├─ ÉTAPE 7: STRATEGY ADAPTATION
    │
    └─→ strategyManager
        Input: {trade, strategy_mode: SNIPER}
        Output: {trade_adjusted{tp: adjusted}, hold_time: 2h}
        └─ Trade ready

        ║
        ▼

    ├─ ÉTAPE 8: FINAL DECISION
    │
    └─→ orchestrator.decide()
        Input: {alltrades + supervisor.allowed}
        Fusion results:
        ├─ technicalAgent: LONG (72/100)
        ├─ timeframeConsensus: BULLISH (strong)
        ├─ macroAgent: CAUTION (NFP in 5h)
        ├─ newsAgent: BULLISH (+65 sentiment)
        ├─ supervisor: ALLOWED
        ├─ riskManager: OK
        └─ → FINAL DECISION: LONG (score: 75/100, strength: FORT)

        OUTPUT: {
          direction: LONG,
          score: 75,
          strength: FORT,
          trade: {entry: 2412.50, sl: 2410, tp: 2415, qty: 0.5},
          execution_probability: 85%, 
          agent_votes: {
            technical: LONG (72),
            macro: CAUTION,
            sentiment: BULLISH,
            risk: OK,
            supervisor: ALLOWED
          },
          timeline_ms: 1245
        }

        ║
        ▼

    ├─ ÉTAPE 9: AUDIT + ERROR HANDLING
    │
    ├─→ Tout enregistré dans audit.json (mémoire)
    │   {
    │     decision_id: uuid,
    │     timestamp: 2026-04-03T10:30:50Z,
    │     symbol: XAUUSD,
    │     pipeline_stages: [
    │       {stage: dataSourceManager, result: PASS, ...},
    │       {stage: syncManager, result: PASS, ...},
    │       {stage: technicalAgent, result: LONG (72), ...},
    │       ...
    │     ],
    │     blockers: [],
    │     final_decision: LONG,
    │     execution_probability: 85%
    │   }
    │
    └─→ Si erreur quelconque:
        repairAgent écoute et classifie
        {
          error: timeout in technicalAgent,
          severity: ERROR,
          recommendation: retry,
          impact: decision delayed
        }

```

---

## 🚦 MATRICE DE BLOCAGE

| Agent | Peut Bloquer? | Raison | Exemple |
|-------|----------|--------|---------|
| dataSourceManager | ✅ OUI | Pas de prix = chaîne invalide | Prix indisponible → arrête tout |
| syncManager | ✅ OUI | Données incohérentes = dangereux | MT5 price vs Chart differ too much → RETRY |
| technicalAgent | ❌ NON | Opinion seulement | Score 45 = neutre, pas blocage, juste opinion |
| chartEngine | ✅ PARTIELLEMENT | Peut demander caution | Si patterns faibles → "proceed with caution" |
| trading-core | ❌ NON | Info enrichissante | Structure data seulement |
| timeframeConsensus | ✅ OUI | Conflit multi-TF = risque | H1 LONG vs D1 SHORT → force ATTENDRE |
| macroAgent | ✅ OUI | Risques macro critiques | NFP dans 1h + HIGH risk → HALT |
| newsAgent | ✅ OUI | Sentiment critique + volatility | Volatility warning + news critique → CAUTION |
| fear-index | ❌ NON | Contexte seulement | VIX haut = contexte, pas blocage |
| tradeValidator | ✅ OUI | Inexécutable = inutile | Status OBSOLETE → refuse trade |
| riskManager | ✅ OUI | Capital protection | Leverage > max → refuse |
| setupClassifier | ❌ NON | Classification enrichissante | Type REVERSAL = info, pas blocage |
| market-state | ✅ PARTIELLEMENT | État dangereux = caution | State DANGEROUS → "proceed with caution" |
| supervisor | ✅ OUI | Verdict final GO/NO-GO | Si un gate fails → REFUSE |
| strategyManager | ❌ NON | Adaptation, pas blocage | Adjust TP, go |
| orchestrator | ❌ NON | Décide toujours | Produit LONG/SHORT/ATTENDRE |
| repairAgent | ❌ NON | Passif, juste log | Classifie errors, pas décision |

---

# PARTIE C — DASHBOARD = COCKPIT DE PILOTAGE

## 🎮 SCREENS ESSENTIELS

### **SCREEN 1: PIPELINE ACTUEL (Live View)**

```
═══════════════════════════════════════════════════════════════
 XAUUSD | 2412.50 | H1 | Started 10:30:50 | Running...
═══════════════════════════════════════════════════════════════

┌─ STAGE 1: DATA SOURCING ──────────────────────────────────────┐
│ ✅ dataSourceManager      [PASS]  price: 2412.50 (MT5)       │
│ ✅ syncManager            [PASS]  coherence: 100%            │
└───────────────────────────────────────────────────────────────┘

┌─ STAGE 2: TECHNICAL ANALYSIS ─────────────────────────────────┐
│ ✅ technicalAgent         [PASS]  direction: LONG (72/100)   │
│    RSI: 65 (BULLISH), EMA: 20>50, ATR: 2.5                   │
│ ✅ chartEngine            [PASS]  patterns: [BOS, Uptrend]   │
│ ✅ trading-core           [PASS]  FVGs: 2, liquidity zones: 3 │
│ ✅ timeframeConsensus     [PASS]  consensus: FORT (H4>D1)    │
│    H1: LONG, H4: LONG, D1: LONG → No conflict               │
└───────────────────────────────────────────────────────────────┘

┌─ STAGE 3: MACRO + SENTIMENT ──────────────────────────────────┐
│ ⚠️  macroAgent            [CAUTION] riskLevel: MEDIUM        │
│     nextEvent: NFP (in 5h 30m)                               │
│ ✅ newsAgent              [PASS]  sentiment: +65 (BULLISH)   │
│ ℹ️  fear-index            [INFO]  VIX: 18 (Low stress)       │
└───────────────────────────────────────────────────────────────┘

┌─ STAGE 4-5: VALIDATION GATES ────────────────────────────────┐
│ ✅ tradeValidator         [PASS]  status: LIVE (distance: 0%) │
│ ✅ market-state           [PASS]  state: CLEAN               │
│ ✅ riskManager            [PASS]  qty: 0.5, leverage: 5x    │
│ ℹ️  setupClassifier         [INFO]  setupType: LIQUIDITY_SWEEP │
└───────────────────────────────────────────────────────────────┘

┌─ STAGE 6: FINAL CHECK ────────────────────────────────────────┐
│ ✅ supervisor             [ALLOWED]                           │
│    All 7 gates PASS ✅                                        │
│    No blockers → Trade approved                              │
└───────────────────────────────────────────────────────────────┘

┌─ STAGE 7: STRATEGY ──────────────────────────────────────────┐
│ ✅ strategyManager        [ADAPTED]  mode: SNIPER             │
│    TP adjusted: 2415 → 2421 (swing target)                  │
│    Max hold: 2h                                               │
└───────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════

FINAL DECISION: ✅ LONG
  score: 75/100 | strength: FORT | confidence: 85%
  Timeline: 1245ms
  
TRADE READY FOR EXECUTION:
  entry: 2412.50 | sl: 2410.00 | tp: 2415.00 | qty: 0.5

[EXECUTE] [REVIEW DETAILS] [VIEW AGENT REPORTS] [CANCEL]

═══════════════════════════════════════════════════════════════
```

---

### **SCREEN 2: AGENT INTELLIGENCE REPORT**

```
═══════════════════════════════════════════════════════════════
 AGENT INTELLIGENCE REPORT — XAUUSD LONG (75/100)
═════════════════════════════════════════════════════════════════

┌─ TECHNICAL INTELLIGENCE ──────────────────────────────────────┐
│ technicalAgent OPINION: LONG (72/100)                        │
│                                                                │
│ Signals:                                                       │
│   ✅ RSI Bullish zone (65/100)                                │
│   ✅ Price > EMA20 > EMA50 (uptrend signal)                   │
│   ✅ EMA20 crossing above EMA50 (golden cross forming)        │
│                                                                │
│ Chart Validation (chartEngine):                               │
│   ✅ BOS pattern confirmed (Break of Structure)              │
│   ✅ FVG support zones at 2410 (if pullback)                 │
│   ✅ Liquidity vacuum (buyer interest) → fuel for move       │
│                                                                │
│ Structure Detail (tradingCore):                               │
│   └─ 2 Fair Value Gaps detected                              │
│   └─ 3 Liquidity zones supporting uptrend                    │
│   └─ No major resistance until 2420                          │
│                                                                │
│ Multi-TF Consensus: BULLISH (FORT)                           │
│   H1: LONG (RSI 65, structure ✅)  → Execution TF            │
│   H4: LONG (uptrend, no resistance) → Confirmation            │
│   D1: LONG (long-term bias)         → Context OK             │
│   └─ NO CONFLICT → Clean directional agreement              │
└───────────────────────────────────────────────────────────────┘

┌─ MACRO RISK INTELLIGENCE ────────────────────────────────────┐
│ macroAgent ASSESSMENT: MEDIUM RISK (⚠️  CAUTION)              │
│                                                                │
│ Upcoming Economic Events:                                     │
│   ⚠️  NFP (Non-Farm Payroll) in 5h 30m [CRITICAL]            │
│       → Will cause volatility and potential pivot             │
│       → Recommendation: Set tight SL or close before NFP      │
│   ℹ️  Initial Jobless Claims in 1h [MEDIUM]                  │
│       → May provide early clue to NFP                        │
│       → Watch for unexpected weakness/strength               │
│                                                                │
│ Risk Scoring:                                                │
│   Current: MEDIUM (can trade, but with awareness)             │
│   Pre-NFP: Should exit before 14:30 UTC                      │
│   Post-NFP: Good volatility for scalping                      │
└───────────────────────────────────────────────────────────────┘

┌─ SENTIMENT INTELLIGENCE ──────────────────────────────────────┐
│ newsAgent ASSESSMENT: BULLISH (+65/100)                       │
│                                                                │
│ Sentiment Score: +65 (Weighted by criticality)               │
│   Positive News Weight:  70%                                  │
│   Negative News Weight:  20%                                  │
│   Neutral Events Weight:  10%                                 │
│                                                                │
│ Today's Key Stories:                                          │
│   ✅ Fed Speaker positive on rate stability (bullish gold)   │
│   ✅ Dollar weakness vs majors (bullish commodities)         │
│   ⚠️  Global growth slowdown mentioned (watch for reversals)  │
│                                                                │
│ Volatility Assessment: NORMAL (VIX: 18)                       │
│   └─ No extreme vol, good for structured trades             │
│                                                                │
│ Recommendation: BULLISH BIAS confirmed by sentiment          │
└───────────────────────────────────────────────────────────────┘

┌─ EXECUTION INTELLIGENCE ──────────────────────────────────────┐
│ tradeValidator: LIVE (Ready to execute)                       │
│   Entry Distance: 0.2% from current price                     │
│   Entry Status: LIVE (can execute now)                        │
│   Alternative Entries: CONDITIONAL at 2409 (support retest)  │
│   Probability of Execution: 95%                               │
│                                                                │
│ Risk Management:                                              │
│   Position Size: 0.5 lot (0.5% account risk)                  │
│   Leverage Used: 5x (acceptable for account)                 │
│   Risk/Reward Ratio: 2.5:1 (optimal)                          │
│   Max Loss: $125 (if SL hit at 2410)                          │
│   Target Gain: $312 (if TP hit at 2415)                       │
│                                                                │
│ SetupProfile:                                                │
│   Pattern: LIQUIDITY_SWEEP (confidence: 85%)                 │
│   Holding Time (SNIPER mode): 30min - 2h                     │
│   Market State: CLEAN (optimal conditions)                    │
└───────────────────────────────────────────────────────────────┘

═════════════════════════════════════════════════════════════════
 COMPOSITE SCORE: 75/100 (STRONG, Safe to Execute)
═════════════════════════════════════════════════════════════════

[ACCEPT & EXECUTE] [MODIFY PARAMETERS] [REJECT] [SAVE ANALYSIS]
```

---

### **SCREEN 3: DECISION HISTORY + MEMORY QUERIES**

```
═══════════════════════════════════════════════════════════════
 SYSTEM MEMORY — Intelligent Queries
═══════════════════════════════════════════════════════════════

┌─ QUICK MEMORY QUERIES ────────────────────────────────────────┐
│                                                                │
│ [Filter Decisions]                                            │
│  • By Symbol: [XAUUSD ▼] 
│  • By Direction: [All ▼] [LONG ▼] [SHORT ▼] [WAIT ▼]        │
│  • By Score: [> 70 ▼]                                        │
│  • By Agent Influence: [whichAgent ▼]                        │
│  • Date Range: [Last 7 days ▼]                               │
│  • Status: [All ▼] [Executed ▼] [Blocked ▼] [Rejected ▼]    │
│                                                                │
│ [SEARCH] [SAVE QUERY] [EXPORT]                               │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌─ INTELLIGENCE FROM HISTORY ────────────────────────────────────┐
│                                                                │
│ QUERY 1: "When did macroAgent block a decision?"             │
│ RESULT: 3 times (7 Apr, 12 Apr, 28 Apr) — always around NFP  │
│         → Pattern: 100% NFP = macro risk                      │
│         → Insight: Trust macroAgent for scheduled events      │
│                                                                │
│ QUERY 2: "Which agents are most predictive of good trades?"   │
│ RESULT: timeframeConsensus (82% win rate on LONG)            │
│         technicalAgent (79% accuracy)                         │
│         supervisor (100% safety — never approved losing)      │
│         → Use consensus + tech combos                         │
│                                                                │
│ QUERY 3: "What % of trades blocked by sentiment?"            │
│ RESULT: 12% blocked by newsAgent (mostly accurate)           │
│         → Sentiment blocking is valid predictor               │
│                                                                │
│ QUERY 4: "Show me decision chains where risk manager said NO"  │
│ RESULT: 4 instances (7 Apr, 15 Apr, 22 Apr, 26 Apr)          │
│         → All were excess leverage warnings                   │
│         → Action: Reduce leverage target from 10x to 7x max   │
│                                                                │
│ QUERY 5: "What's the average score for LONG trades?"         │
│ RESULT: 72.4 (n=47 trades)                                    │
│         SHORT trades: 65.8 (n=23 trades)                      │
│         WAIT trades: 45.2 (n=104 trades)                      │
│         → Insight: System is biased LONG (market trend)       │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌─ DECISION TIMELINE ────────────────────────────────────────────┐
│                                                                │
│ [10:30:50] ✅ XAUUSD LONG (75/100)                             │
│   Agents voted: technical✅ macro⚠️ sentiment✅ risk✅ | exec: ✓
│   [View Full Analysis] [View JSON] [Executed: YES]            │
│                                                                │
│ [09:15:22] ✅ EURUSD SHORT (68/100)                            │
│   Blocked by: macroAgent (NFP alert) → User ignored, traded   │
│   Result: -0.5% loss (macro call was right!)                  │
│   [View Full Analysis] [Why Was This Wrong?]                  │
│                                                                │
│ [08:45:10] ❌ GBPUSD SHORT (55/100)                            │
│   Rejected by: supervisor (timeframe conflict H1 vs D1)       │
│   Status: REJECTED (correct — avoided 2% loss)                │
│   [View Full Analysis]                                        │
│                                                                │
│ [07:30:45] ✅ BTC/USD LONG (82/100)                            │
│ Agents agreed: ✅✅✅✅✅ All consensus                           │
│   Result: +2.5% win (highest confidence paid off)             │
│   [View Full Analysis]                                        │
│                                                                │
└───────────────────────────────────────────────────────────────┘

═════════════════════════════════════════════════════════════════
```

---

# PARTIE D — BACKUP = MÉMOIRE INTELLIGENTE

## 📚 STRUCTURE AUDIT.JSON RÉVISÉE

```json
{
  "metadata": {
    "version": "3.0",
    "lastUpdate": "2026-04-03T10:30:50Z",
    "totalDecisions": 174,
    "executedTrades": 74,
    "blockedDecisions": 22,
    "averageScore": 68.5,
    "systemHealthScore": 94
  },

  "decisionIndex": [
    {
      "id": "decision-001-XAUUSD-LONG",
      "timestamp": "2026-04-03T10:30:50.123Z",
      "symbol": "XAUUSD",
      "finalDecision": "LONG",
      "score": 75,
      "strength": "FORT",
      "status": "APPROVED_READY_EXECUTION",
      
      "pipelineExecution": {
        "stage1_dataSourceManager": {
          "status": "PASS",
          "price": 2412.50,
          "source": "MT5",
          "confidence": 100
        },
        
        "stage2_syncManager": {
          "status": "PASS",
          "synchronized": true,
          "inconsistencies": [],
          "confidence": 100
        },
        
        "stage3_technicalAgent": {
          "status": "PASS",
          "direction": "LONG",
          "score": 72,
          "signals": ["RSI oversold 65", "Price>EMA20>EMA50"],
          "confidence": 72
        },
        
        "stage4_chartEngine": {
          "status": "PASS",
          "patternFound": "BOS",
          "validation": "confirmed",
          "confidence": 85
        },
        
        "stage5_tradingCore": {
          "status": "PASS",
          "structures": ["BOS", "FVG"],
          "fvgCount": 2,
          "liquidityZones": 3,
          "confidence": 88
        },
        
        "stage6_timeframeConsensus": {
          "status": "PASS",
          "consensus": "BULLISH",
          "dominantTF": "D1",
          "byTF": {
            "H1": {direction: "LONG", strength: "MODERE"},
            "H4": {direction: "LONG", strength: "FORT"},
            "D1": {direction: "LONG", strength: "FORT"}
          },
          "conflict": false,
          "confidence": 90
        },
        
        "stage7_macroAgent": {
          "status": "CAUTION",
          "riskLevel": "MEDIUM",
          "nextEvent": "NFP (in 5h 30m)",
          "recommendation": "Proceed with caution",
          "blockedTrade": false,
          "confidence": 85
        },
        
        "stage8_newsAgent": {
          "status": "PASS",
          "sentiment": "BULLISH",
          "sentimentScore": 65,
          "criticalNews": 0,
          "volatilityWarning": false,
          "confidence": 78
        },
        
        "stage9_fearIndex": {
          "status": "PASS",
          "vix": 18,
          "level": "BAS",
          "comment": "Low market stress",
          "confidence": 100
        },
        
        "stage10_tradeValidator": {
          "status": "PASS",
          "tradeStatus": "LIVE",
          "distanceToEntry": 0.2,
          "probability": 95,
          "confidence": 95
        },
        
        "stage11_marketState": {
          "status": "PASS",
          "state": "CLEAN",
          "dangerScore": 15,
          "confidence": 90
        },
        
        "stage12_riskManager": {
          "status": "PASS",
          "quantity": 0.5,
          "leverage": "5x",
          "riskRewardRatio": "2.5:1",
          "maxLoss": 125,
          "targetGain": 312,
          "confidence": 100
        },
        
        "stage13_setupClassifier": {
          "status": "INFO",
          "setupType": "LIQUIDITY_SWEEP",
          "confidence": 85,
          "riskProfile": "medium"
        },
        
        "stage14_supervisor": {
          "status": "ALLOWED",
          "allGatesPassed": true,
          "gateSummary": {
            "dataSource": "✅",
            "sync": "✅",
            "technical": "✅",
            "validation": "✅",
            "risk": "✅",
            "macro": "⚠️ (CAUTION)",
            "sentiment": "✅"
          },
          "warnings": ["NFP in 5h - monitor"],
          "confidence": 95
        },
        
        "stage15_strategyManager": {
          "status": "ADAPTED",
          "strategyMode": "SNIPER",
          "tpAdjusted": "2415 → 2421",
          "maxHoldTime": "2h",
          "confidence": 100
        },
        
        "stage16_orchestrator": {
          "status": "DECISION",
          "finalDecision": "LONG",
          "score": 75,
          "strength": "FORT",
          "executionProbability": 85,
          "executionTimeline": "1245ms"
        }
      },
      
      "agentWeighting": {
        "technicalAgent": {vote: "LONG", weight: 8, score: 72},
        "timeframeConsensus": {vote: "LONG", weight: 8, score: 90},
        "macroAgent": {vote: "CAUTION", weight: 8, score: 65},
        "newsAgent": {vote: "BULLISH", weight: 7, score: 78},
        "supervisor": {vote: "ALLOWED", weight: 10, score: 95},
        "riskManager": {vote: "OK", weight: 10, score: 100}
      },
      
      "finalTrade": {
        "entry": 2412.50,
        "sl": 2410.00,
        "tp": 2415.00,
        "quantity": 0.5,
        "leverage": "5x",
        "riskReward": "2.5:1",
        "maxLoss": 125,
        "targetGain": 312
      },
      
      "executionStatus": "READY_FOR_EXECUTION",
      "userAction": null,
      "executedAt": null,
      "relatedErrors": [],
      "relatedRepairs": []
    }
  ],

  "agentPerformance": {
    "technicalAgent": {
      "totalAnalyses": 174,
      "accuracyRate": 79,
      "biasTendency": "Bullish (67%)",
      "averageScore": 71.2,
      "commonSignals": ["RSI zone", "EMA cross", "Price structure"]
    },
    "timeframeConsensus": {
      "totalConsensus": 174,
      "conflictRate": 8,
      "predictionAccuracy": 82,
      "dominantBias": "Follows D1 trend"
    },
    "macroAgent": {
      "totalAssessments": 174,
      "blockageRate": 12,
      "accuracyOfBlockages": 100,
      "mostCommonEvent": "NFP",
      "riskAccuracy": 88
    },
    "newsAgent": {
      "totalAnalyses": 174,
      "sentimentAccuracy": 76,
      "falseAlarms": 14,
      "criticalNewsDetections": 22
    },
    "supervisor": {
      "totalChecks": 174,
      "blockageRate": 18,
      "falseNegatives": 1,
      "falsePositives": 0
    },
    "riskManager": {
      "totalAssessments": 174,
      "overriddenByUser": 0,
      "lowestAcceptedLeverage": "2x",
      "highestAcceptedLeverage": "10x",
      "averageLeverageApproved": "5.2x"
    }
  },

  "errorLog": [
    {
      "id": "error-001",
      "timestamp": "2026-04-03T10:28:50Z",
      "severity": "ERROR",
      "agent": "syncManager",
      "errorType": "INCONSISTENCY_DETECTED",
      "message": "MT5 price vs chart price mismatch",
      "impact": "DECISION_DELAYED",
      "resolution": "RETRY",
      "resolvedAt": "2026-04-03T10:29:12Z",
      "resolvedInMs": 22000,
      "repairAgent": {
        "classification": "DATA_QUALITY",
        "recommendation": "Refresh MT5 connection",
        "automated": true
      }
    }
  ],

  "memoryQueries": {
    "whenMacroBlocked": "3 times (7,12,28 Apr) — 100% around NFP",
    "mostPredictiveAgent": "timeframeConsensus (82% accuracy)",
    "agentBlockageAccuracy": "macroAgent: 100%, supervisor: 99%",
    "tradeWinRate": "74% (n=74 executed)",
    "averageScore": {
      "LONG": 72.4,
      "SHORT": 65.8,
      "WAIT": 45.2
    }
  }
}
```

---

## 🔍 EXAMPLE QUERY RESULTS

```javascript
// Query 1: Find all decisions where macroAgent said "Block"
audit.decisionIndex.filter(d => 
  d.pipelineExecution.stage7_macroAgent.blockedTrade === true
)
// Returns: Array of 22 blocked decisions (100% accuracy when macro blocks)

// Query 2: Show me all LONG trades with score > 70
audit.decisionIndex.filter(d => 
  d.finalDecision === "LONG" && d.score > 70
)
// Returns: Array of 47 LONG trades, average win rate 74%

// Query 3: Which agent's opinion matters most for accurate predictions?
audit.agentPerformance.timeframeConsensus.predictionAccuracy // 82%
audit.agentPerformance.technicalAgent.accuracyRate // 79%
audit.agentPerformance.macroAgent.riskAccuracy // 88%

// Query 4: Show me the timeline where supervisor blocked a trade
// (timestamp, agents opinion, supervisor reasoning)

// Query 5: Find error patterns
audit.errorLog.filter(e => e.agent === "syncManager")
// Returns: All sync errors, allowing pattern analysis
```

---

# RÉSUMÉ — NOUVELLE ARCHITECTURE

## 🎯 3 NIVEAUX

### **NIVEAU 1: AGENTS SPÉCIALISÉS (18-20 agents actifs)**
Chacun avec un rôle clair, des inputs/outputs définis, et une contribution à la décision finale.

### **NIVEAU 2: PIPELINE COORDONNÉ**
Pas orchestrator tout-parallèle, mais une **chaîne avec dépendances** où les agents communiquent real-time et peuvent bloquer.

### **NIVEAU 3: COCKPIT + MÉMOIRE INTELLIGENTE**
- Dashboard = Pilotage temps réel
- Audit = Requêtes intelligentes pour comprendre comment le système fonctionne

---

## ✅ CE QUE TU AURAS

1. **Agents qui travaillent ensemble** (pas juste parallèles)
2. **Pipeline avec gating** (certains agents peuvent arrêter la chaîne)
3. **Attribution claire** (on sait qui a influencé chaque décision)
4. **Traçabilité 100%** (retrouver une erreur / décision en 1 seconde)
5. **Contrôle total** (dashboard = vrai cockpit de pilotage)
6. **Mémoire intelligente** (requêtes sur l'historique: "montre-moi quand macro a bloqué")
7. **Zéro modification** des agents existants (architecture additive)

---

**Est-ce que cette vision te plaît? Ou tu veux que je précise certains points?**

✅ APPROUVÉ — implémenter
🔧 MODIFICATIONS — préciser lesquelles
❓ CLARIFICATIONS — lesquelles

