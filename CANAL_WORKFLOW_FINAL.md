# 🔄 CANAL INTERNE WORKFLOW — JOURNAL DE COORDINATION

**Date:** 3 avril 2026  
**Statut:** CORRIGÉ et VALIDÉ — Prêt coding  
**Concept:** Journal structuré interne du système (pas chat séparé)

---

# 📋 DÉFINITION CLAIRE

**Ce qu'il est:**
- ✅ Un canal interne du système (pas externe)
- ✅ Un journal structuré du workflow réel
- ✅ Visible dans le dashboard pour suivi
- ✅ Historisé dans audit.json pour traçabilité
- ✅ Utilisé par les agents pour coordonner
- ✅ Entièrement structuré (format strict)

**Ce qu'il n'est pas:**
- ❌ Un chat séparé
- ❌ Une conversation externalisée
- ❌ Un système lourd
- ❌ Un nouvel onglet inutile

---

# 🎯 RÔLE RÉEL

Tracer l'exécution du workflow 7-étapes:

```
Qui a parlé?          → Quel agent
Pourquoi?             → Quelle étape (1-7)
Sur quel fichier?     → context.file
Avec quel status?     → status (info/pending/approved/rejected/error)
Avec quel résultat?   → action (found, pass, fail, integrated, etc)
```

**Exemple concret:**

```
Timestamp : 10:30:47
Agent     : test-agent
Étape     : 5 (test)
Fichier   : audit-logger.js
Action    : pass
Status    : approved
Message   : ✅ Tous tests passent
Résultat  : {testsRun: 8, testsPassed: 8, regressionDetected: false}
```

---

# 💾 OÙ ÇA VIT

**Structure minimale:**
```
audit.json
  ├─ workflowLog[]        (historique structuré)
  
server.js
  ├─ GET /workflow/log    (retourne les logs)
  ├─ POST /workflow/log   (agents enregistrent une étape)
  
AGENTS_MONITOR.html
  └─ Onglet "Workflow"    (affiche tableau)
```

---

# 📊 STRUCTURE AUDIT.JSON

```javascript
{
  "workflowLog": [
    {
      "timestamp": "2026-04-03T10:30:45.123Z",
      "step": 1,                    // Numéro étape (1-7)
      "stepName": "analyse",        // Nom lisible
      "agent": "agent-memory",      // Quel agent
      "context": {
        "file": "audit-logger.js",  // Fichier exact
        "function": "logEvent",     // Fonction exacte
        "line": 145,                // Ligne exacte
        "concept": "localisation"   // Concept abordé
      },
      "action": "found",            // Action réelle
      "status": "info",             // Status
      "message": "audit-logger.js existe ligne 145", // Court texte
      "result": {}                  // Données si pertinentes
    },
    // ... next entries
  ]
}
```

**Limites:**
- Garder seulement 1000 dernières lignes
- Suffisant pour traçabilité complète
- Légère en performance

---

# 🎨 DASHBOARD (AGENTS_MONITOR.html)

**Onglet "Workflow" — Tableau simple:**

```html
<table>
  <tr>
    <th>Heure</th>
    <th>Agent</th>
    <th>Étape</th>
    <th>Fichier</th>
    <th>Action</th>
    <th>Status</th>
    <th>Message</th>
  </tr>
  <!-- Lignes injectées depuis workflowLog -->
</table>

<button>🔄 Rafraîchir (manuel)</button>
```

**Mise à jour:**
- SSE événement `workflow-update` quand un agent enregistre
- Pas de polling lourd
- Bouton manuel si besoin
- Seulement 50 dernières lignes en DOM (performance)

---

# ⚡ STRATÉGIE PERFORMANCE

**✅ SSE prioritaire (temps réel):**
```javascript
// Quand agent écrit en POST /workflow/log
// Server envoie: event: workflow-update
// Dashboard reçoit et ajoute une ligne
```

**❌ PAS d'auto-refresh lourd:**
- Pas de polling 2s par défaut
- SSE uniquement (léger)

**✅ Bouton manuel optionnel:**
- Si utilisateur veut forcer refresh
- Appelle GET /workflow/log

**✅ Limite DOM:**
- Seulement 50 dernières lignes visibles
- Pas de scroll lourd

**Résultat:** Zéro surcharge système

---

# 🔧 IMPLÉMENTATION SIMPLE

**Helper pour tous les agents (1 fonction):**

```javascript
// utils/workflow-logger.js

async function logWorkflowStep(step, stepName, agent, context, action, status, message, result = {}) {
  return fetch('http://localhost:4000/workflow/log', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      step,
      stepName,
      agent,
      context,
      action,
      status,
      message,
      result
    })
  });
}
```

**Utilisation par agent (simple appel):**

```javascript
// Étape 1 - Agent Mémoire
await logWorkflowStep(
  1, 'analyse', 'agent-memory',
  {file: 'audit-logger.js', function: 'logEvent', line: 145},
  'found', 'info',
  'audit-logger.js existe ligne 145'
);

// Étape 5 - Agent Testeur
await logWorkflowStep(
  5, 'test', 'test-agent',
  {file: 'audit-logger.js'},
  'pass', 'approved',
  '✅ Tous tests passent',
  {testsRun: 8, testsPassed: 8}
);
```

---

# 🌐 ROUTES SERVER.JS

```javascript
// GET /workflow/log — Retourne l'historique (avec limit optionnel)
app.get('/workflow/log', (req, res) => {
  const logs = auditLogger.getWorkflowLog(req.query.limit || 100);
  res.json(logs);
});

// GET /workflow/log/file/:fileName — Filtrer par fichier
app.get('/workflow/log/file/:fileName', (req, res) => {
  const logs = auditLogger.getWorkflowByFile(req.params.fileName);
  res.json(logs);
});

// POST /workflow/log — Agents enregistrent une étape
app.post('/workflow/log', (req, res) => {
  const { step, stepName, agent, context, action, status, message, result } = req.body;
  
  const entry = auditLogger.logWorkflowStep(
    step, stepName, agent, context, action, status, message, result
  );
  
  // Broadcast via SSE — LÉGER
  sseClients.forEach(client => {
    client.write(`event: workflow-update\ndata: ${JSON.stringify(entry)}\n\n`);
  });
  
  res.json({ok: true, entry});
});
```

**Performance:** ~3 ms par enregistrement

---

# ✅ ACTION STANDARDISÉES

```javascript
// Étape 1 Analyse
'found'
'not-found'
'duplicate-found'

// Étape 2-3 Compréhension + Localisation
(no action, logged as info)

// Étape 4 Réparation
'proposed'
'repair-complete'

// Étape 5 Test
'pass'
'fail'
'regression'

// Étape 6-7 Validation + Intégration
'approved'
'rejected'
'integrated'
'integration-failed'
```

---

# 🔴 CONTRÔLES / FILTRES

**Via GET /workflow/log:**

```javascript
// Dernier état complet
GET /workflow/log                 → 100 dernières actions

// Historique d'un fichier
GET /workflow/log/file/audit-logger.js   → Actions sur ce fichier

// Historique d'un agent
GET /workflow/log?agent=test-agent       → Actions par test-agent
```

---

# 📈 FIABILITÉ

**Persistance:**
- Chaque action écrite en audit.json immédiatement
- Pas de risque de perte
- Rollback facile (lire audit.json)

**Audit trail complet:**
- Qui a fait quoi
- Quand
- Sur quel fichier
- Avec quel résultat

**Traçabilité 100%:**
- Erreur? Lire workflow log
- Comprendre la chaîne d'actions
- Identifier le point d'arrêt

---

# ✅ CONFIRMATIONS FINALES

**A. Canal Interne ✅**
```
✓ Interne au système (pas chat séparé)
✓ Visible dans dashboard
✓ Historisé audit.json
✓ Utilisé pour coordonner agents
✓ Entièrement structuré
```

**B. Performance Optimisée ✅**
```
✓ SSE événement (temps réel, léger)
✓ Pas auto-refresh lourd 2s
✓ Bouton refresh manuel optionnel
✓ Limite DOM 50 lignes
✓ Zéro surcharge
```

**C. Lié au Dashboard / Backup / Agents ✅**
```
✓ Dashboard = onglet "Workflow"
✓ Backup = audit.json persiste
✓ Agents = simple POST /workflow/log
✓ Extension recevoir via SSE
✓ Zéro complexité
```

---

# 🚀 RÉSUMÉ POUR CODING

| Aspect | Détail |
|--------|--------|
| **Concept** | Journal structuré interne du workflow |
| **Stockage** | audit.json → workflowLog[] (1000 max) |
| **Routes** | GET/POST /workflow/log |
| **Dashboard** | Onglet "Workflow" avec tableau SSE |
| **Performance** | SSE événement, pas polling lourd |
| **Agents** | Simple helper `logWorkflowStep()` |
| **Traçabilité** | Complète: qui/quoi/où/quand/résultat |

---

# ✅ VALIDATION DÉFINITIVE

Je confirme:

- ✅ **Concept:** Canal interne du système, pas chat séparé
- ✅ **Journal:** Traçable complètement (qui/pourquoi/fichier/status/résultat)
- ✅ **Performance:** SSE léger, pas auto-refresh lourd, bouton manuel optionnel
- ✅ **Agents:** Workflow 7-étapes immuable, agent-mémoire + test-agent + repair-agent
- ✅ **Dashboard:** Onglet "Workflow" avec tableau automatisé
- ✅ **Backup:** Persisté audit.json, rollback possible
- ✅ **Zéro surcharge:** Implémentation minimale

