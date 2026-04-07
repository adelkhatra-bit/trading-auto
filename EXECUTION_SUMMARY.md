# RÉSUMÉ EXÉCUTIF FINAL — Plan Après Audit

**Date:** 3 avril 2026  
**Documents de référence:** AUDIT_EXISTANT.md + PLAN_EXECUTION_REVISED.md

---

# DÉCISION: 4 Fichiers à CRÉER + 6 Fichiers à ENRICHIR

## CE QUE TU DOIS SAVOIR

### ✅ RÉUTILISATION MAXIMALE
```
audit-logger.js EXISTE
├─ Branchdans server.js (/audit/state, /events, /log)
├─ Classe AuditLogger complète
└─ On ENRICHIT seulement avec getCallerLocation() [+20 lignes]

AGENTS_MONITOR.html EXISTE
├─ 3 cards statiques basiques
└─ On UPGRADER avec 6 onglets [+350 lignes, pas nouveau HTML]

studio/index-simple.html EXISTE
├─ Interface trading complète
└─ On AJOUTE section "Mes Préférences" [+100 lignes]

public/background.js EXISTE
├─ showSignal() function
└─ On AJOUTE subscribeToAlerts() [+50 lignes]

orchestrator.js EXISTE
├─ Promise.all 4 agents
└─ On AJOUTE indicatorAgent [+1 ligne logique]
```

### ❌ CE QUI N'EXISTE PAS (À CRÉER)
```
agent-bus.js [NEW]
├─ Registre agents + queue messages
└─ 100 lignes

src/agents/surveillance-agent.js [NEW]
├─ Remplace continuous-loop DISABLED
├─ Event-driven (prix >0.5% OU 30s)
└─ 50 lignes

alert-manager.js [NEW]
├─ Centralise alertes
├─ Filtre par symboles + severity
└─ 120 lignes

src/agents/indicator-agent.js [NEW]
├─ Génère indicateurs MT5
├─ Retourne {indicators[], mql5Code}
└─ 200 lignes
```

---

# POUR CHAQUE BESOIN DU PLAN

| Besoin | Existe? | Action | Où |
|--------|---------|--------|-----|
| Agent bus | ❌ | Créer | agent-bus.js |
| Surveillance | ❌ | Créer | src/agents/surveillance-agent.js |
| Alertes filtrées | ❌ | Créer | alert-manager.js |
| Indicateurs créés | ❌ | Créer | src/agents/indicator-agent.js |
| Audit localisation | ✅ Partiellement | Enrichir +20 lignes | audit-logger.js |
| Dashboard cockpit | ✅ Basique | Enrichir +350 lignes | AGENTS_MONITOR.html |
| Prefs utilisateur | ❌ | Ajouter +100 lignes | studio/index-simple.html |
| Extension SSE | ❌ | Ajouter +50 lignes | public/background.js |
| Orchestrator indicator | ✅ Pas intégré | Ajouter 1 ligne | orchestrator.js |
| Routes alertes | ❌ | Ajouter ~80 lignes | server.js |

---

# ORDRE IMPLÉMENTATION (10 ÉTAPES)

```
PHASE 1: Modules indépendants
  1. Créer agent-bus.js
  2. Créer alert-manager.js
  3. Créer src/agents/surveillance-agent.js
  
PHASE 2: Enrichissement audit
  4. Modifier audit-logger.js (+getCallerLocation)
  
PHASE 3: Server + Orchestrator
  5. Modifier server.js (requires, routes, broadcasting)
  6. Créer src/agents/indicator-agent.js
  7. Modifier orchestrator.js (add indicatorAgent)
  
PHASE 4: Frontend
  8. Améliorer AGENTS_MONITOR.html (6 onglets)
  9. Améliorer studio/index-simple.html (prefs)
  10. Améliorer public/background.js (SSE)
```

---

# FICHIER PAR FICHIER

## À CRÉER (4 fichiers)

| Fichier | Lignes | Raison |
|---------|--------|--------|
| agent-bus.js | 100 | Aucun module équivalent |
| src/agents/surveillance-agent.js | 50 | Remplace continuous-loop désactivé |
| alert-manager.js | 120 | Aucune gestion alertes centralisée |
| src/agents/indicator-agent.js | 200 | Aucun agent créateur indicateurs |

## À ENRICHIR (6 fichiers)

| Fichier | Ajout | Raison | Points clés |
|---------|-------|--------|-------------|
| audit-logger.js | +20 | Localisation stack | getCallerLocation() dans logEvent() |
| AGENTS_MONITOR.html | +350 | 6 onglets cockpit | Auto-refresh 2s, fetch /agents-bus, /alerts |
| studio/index-simple.html | +100 | Prefs utilisateur | Checkboxes symboles, localStorage save |
| public/background.js | +50 | SSE listener | subscribeToAlerts(), chrome.notifications |
| orchestrator.js | +5 | Intégrer indicateur | 1 ligne en Promise.all + 1 ligne fusion |
| server.js | +80 | Routes + broadcast | Requires, routes, setupetup surveillance |

---

# CLARIFICATIONS CRITIQUES

### Q: Pourquoi créer agent-bus.js quand AGENT_BUS.json existe?
**A:** AGENT_BUS.json est une coordination CONCEPTUELLE entre Claude et Copilot.  
Le module agent-bus.js est une IMPLEMENTATION RÉELLE exécutée par le serveur Node.

### Q: Pourquoi créer surveillance-agent.js quand continuous-loop.js existe?
**A:** continuous-loop.js est DISABLED (cause CPU 100%). surveillance-agent.js est la REMPLACER avec event-driven propre.

### Q: Pourquoi enrichir plutôt que créer une aide audit-helper.js séparé?
**A:** audit-logger.js EXISTE et est branche dans server.js. L'enrichir est ADDITIVE et évite fichier inutile.

### Q: Faut-il créer une classe NotificationManager séparé pour extension?
**A:** NON. alert-manager.js centralise tout. Extension l'écoute via SSE. Pas de classe séparée nécessaire.

---

# V1 SCOPE (Pas surcharge)

```
✅ Créer (4 modules — 470 lignes total)
✅ Enrichir (6 fichiers — 600 lignes total)
✅ Modifier (1 fichier — 80 lignes)
  TOTAL: ~1150 lignes NEW CODE

❌ Pipeline avancé (V2)
❌ Repair agent complet (V2)
❌ Persistance BD (V2)
```

---

# CHECKPOINTS VALIDATION

- ✅ 4 fichiers créés SEULEMENT (pas 5, pas 10)
- ✅ 6 fichiers enrichis (pas nouveaux)
- ✅ audit-logger.js peut être enrichi sans risque
- ✅ orchestrator.js seulement 1 ligne logique
- ✅ server.js = modifications chirurgicales (Ligne Npour ajouter, pas refactoriser)
- ✅ ZÉRO breaking changes (tout additive)
- ✅ V1 minimale = surveillade + alertes + dashboard + audit riche

---

# PROCHAINE ÉTAPE

Tu approuves cette répartition:
- 4 fichiers à créer
- 6 fichiers à enrichir
- 1 fichier à modifier

OU tu veux réviser quelque chose?

**Exemple révision:** "Je ne veux pas de alert-manager séparé, c'est mieux dans server.js" → On l'intègre.

**Approves-tu le plan?**
