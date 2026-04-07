# 🔄 AUDIT LOGGER — Synchronisation Automatique

## Vue d'ensemble

Le **Audit Logger** transforme le backup `audit.json` en **système vivant et synchronisé** qui met à jour automatiquement l'état du projet en temps réel.

```
Système Réel
    ↓
Événements (tâches, erreurs, endpoints)
    ↓
audit-logger.js (Module de sync)
    ↓
audit.json (Source de vérité)
    ↓
audit-dashboard.html (Auto-refresh 5s)
```

---

## Architecture

### 1. **audit-logger.js** — Module Central

Singleton qui maintient l'état synchronisé :

```javascript
const auditLogger = require('./audit-logger');

// Logger un événement
auditLogger.logEvent('task', 'created', { id: 'task-1', name: 'Test' });

// Mettre à jour une tâche
auditLogger.updateTask('task-1', { status: 'in-progress', completeness: 50 });

// Compléter une tâche
auditLogger.completeTask('task-1');

// Marquer une tâche en erreur
auditLogger.failTask('task-1', 'Reason...');

// Ajouter une erreur
auditLogger.addError('err-1', {
  type: 'missing-endpoint',
  severity: 'high',
  description: 'POST /test not implemented',
  affectedFile: 'server.js'
});

// Résoudre une erreur
auditLogger.resolveError('err-1', 'Endpoint implemented');

// Obtenir l'état complet
const state = auditLogger.getState(); // { audit: {...}, eventLog: [...] }
```

### 2. **Endpoints d'Audit** (dans server.js)

Tous les endpoints d'audit sont **lecture/écriture** :

#### **GET /audit/state** — État complet temps réel
```bash
curl http://localhost:4000/audit/state
# Response:
{
  "ok": true,
  "audit": { files, agents, endpoints, connections, errors, tasks },
  "eventLog": [...],  // Derniers 50 événements
  "timestamp": "2026-04-03T..."
}
```

#### **GET /audit/events** — Événements récents
```bash
curl http://localhost:4000/audit/events?limit=20
# Response: { events: [...] }
```

#### **POST /audit/log** — Logger manuellement
```bash
curl -X POST http://localhost:4000/audit/log \
  -H "Content-Type: application/json" \
  -d '{
    "category": "task",
    "action": "created",
    "details": { "name": "New Task", "severity": "info" }
  }'
```

#### **POST /audit/task/:taskId** — Mettre à jour une tâche
```bash
curl -X POST http://localhost:4000/audit/task/task-1 \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in-progress",
    "completeness": 50,
    "files": ["server.js", "index.html"]
  }'
```

#### **POST /audit/task/:taskId/complete** — Compléter une tâche
```bash
curl -X POST http://localhost:4000/audit/task/task-1/complete
```

#### **POST /audit/task/:taskId/fail** — Marquer en erreur
```bash
curl -X POST http://localhost:4000/audit/task/task-1/fail \
  -H "Content-Type: application/json" \
  -d '{ "reason": "Dependencies not met" }'
```

#### **POST /audit/error/:errorId** — Ajouter une erreur
```bash
curl -X POST http://localhost:4000/audit/error/err-1 \
  -H "Content-Type: application/json" \
  -d '{
    "type": "missing-endpoint",
    "severity": "high",
    "description": "POST /test not implemented",
    "affectedFile": "server.js"
  }'
```

#### **POST /audit/error/:errorId/resolve** — Résoudre une erreur
```bash
curl -X POST http://localhost:4000/audit/error/err-1/resolve \
  -H "Content-Type: application/json" \
  -d '{ "resolution": "Endpoint implemented" }'
```

#### **GET /audit/health** — Scan système
```bash
curl http://localhost:4000/audit/health
# Response: { issues: [...], count: 5 }
```

---

## Utilisation

### Intégration avec une tâche

```javascript
// Dans ton code qui lance une tâche
async function myTask() {
  const auditLogger = require('./audit-logger');
  
  // 1. Logger le démarrage
  auditLogger.updateTask('my-task-1', {
    name: 'Process data',
    status: 'in-progress',
    completeness: 0
  });

  try {
    // 2. Faire la tâche
    await processData();
    
    // Progression
    auditLogger.updateTask('my-task-1', { completeness: 50 });
    
    await moreWork();
    
    // 3. Marquer complète
    auditLogger.completeTask('my-task-1');
  } catch (error) {
    // 4. En cas d'erreur
    auditLogger.failTask('my-task-1', error.message);
  }
}
```

### Intégration avec une erreur

```javascript
// Dans un middleware Express
app.use((err, req, res, next) => {
  const auditLogger = require('./audit-logger');
  
  // Logger automatiquement l'erreur
  auditLogger.addError(`err-${Date.now()}`, {
    type: 'runtime-error',
    severity: 'high',
    description: err.message,
    affectedFile: err.stack?.split('\n')[1] || 'unknown',
    affectedComponent: req.path
  });
  
  res.status(500).json({ ok: false, error: err.message });
});
```

---

## Dashboard Auto-Refresh

Le **audit-dashboard.html** se met à jour automatiquement :

```javascript
// Auto-refresh chaque 5 secondes
const AUTO_REFRESH_INTERVAL = 5000;

autoRefreshInterval = setInterval(() => {
  loadAudit(true); // Fetch /audit/state
}, AUTO_REFRESH_INTERVAL);
```

**Ce qui se mise à jour :**
- ✅ Erreurs (nouvelles défections)
- ✅ Tâches (progression)
- ✅ Timestamps
- ✅ Événements récents
- ℹ️ Fichiers/Endpoints (moins souvent)

---

## Event Log

Chaque événement est enregistré avec :

```javascript
{
  "id": "evt-1234567890-abc123",
  "timestamp": "2026-04-03T14:30:45.123Z",
  "category": "task|error|endpoint|connection|file",
  "action": "created|updated|completed|failed|resolved",
  "details": { ... },
  "severity": "info|warning|error|success"
}
```

**Exemples :**
```json
{
  "id": "evt-...",
  "timestamp": "2026-04-03T14:30:45.123Z",
  "category": "task",
  "action": "completed",
  "details": { "id": "task-1", "name": "Backend Setup" },
  "severity": "success"
}

{
  "id": "evt-...",
  "timestamp": "2026-04-03T14:31:20.456Z",
  "category": "error",
  "action": "detected",
  "details": { "type": "missing-endpoint", "severity": "high" },
  "severity": "error"
}
```

---

## Flux Complet

### Scénario 1 : Créer et compléter une tâche

```
1. Frontend → POST /audit/task/task-1
   { "status": "in-progress", "name": "Implement feature" }

2. audit-logger.updateTask('task-1', {...})

3. Écrit audit.json
4. Envoie notification aux subscribers

5. Dashboard → GET /audit/state (auto-refresh)
6. Dashboard se met à jour avec la nouvelle tâche

7. Travail...

8. Frontend → POST /audit/task/task-1/complete

9. audit-logger.completeTask('task-1')
10. Écrit audit.json
11. Dashboard se met à jour (100% complète)
```

### Scénario 2 : Détecter une erreur

```
1. Système détecte une erreur
   (missing endpoint, API timeout, etc.)

2. Code → auditLogger.addError('err-123', {...})

3. audit-logger.addError() :
   - Crée l'erreur
   - Enregistre dans audit.json
   - Log l'événement

4. Dashboard → GET /audit/state (auto-refresh)
5. Dashboard affiche la nouvelle erreur
6. Header → badge "5 erreurs"
```

---

## File Structure

```
trading-auto/
├── audit.json              ← Source de vérité (auto-mise à jour)
├── audit-logger.js         ← Module de sync
├── audit-dashboard.html    ← Interface avec auto-refresh
├── server.js               ← Endpoints /audit/* + imports
└── AUDIT_SYNC.md          ← Ce fichier
```

---

## Intégration Continue

Le système peut être utilisé pour :

### Avant deployment
```javascript
// Check system health
auditLogger.scanSystemHealth()
// { issues: [...] }

if (issues.length === 0) {
  console.log('✅ Safe to deploy');
} else {
  console.log('❌ Resolve errors before deploying');
}
```

### Monitoring en production
```javascript
// Track nouvelle erreurs
setInterval(() => {
  const state = auditLogger.getState();
  const criticalErrors = state.audit.errors.filter(e => e.severity === 'high' && e.status === 'open');
  
  if (criticalErrors.length > 0) {
    sendAlert(`${criticalErrors.length} critical errors detected`);
  }
}, 60000); // Check every minute
```

---

## API Complète (audit-logger.js)

```javascript
// Class methods
auditLogger.logEvent(category, action, details)
auditLogger.updateTask(taskId, updates)
auditLogger.completeTask(taskId)
auditLogger.failTask(taskId, reason)
auditLogger.addError(errorId, errorData)
auditLogger.resolveError(errorId, resolution)
auditLogger.updateEndpoint(path, updates)
auditLogger.updateConnection(connId, status, details)
auditLogger.markFileModified(fileId, updates)
auditLogger.updateMetadata()
auditLogger.getState()
auditLogger.getRecentEvents(limit)
auditLogger.subscribe(callback)    // Observer pattern
auditLogger.scanSystemHealth()
```

---

## Notifications en Temps Réel (Avancé)

Le audit-logger supporte un système de subscribers :

```javascript
// Subscribe à les changements
const unsubscribe = auditLogger.subscribe(event => {
  console.log(`Event: ${event.category} ${event.action}`);
  
  // Faire quelquechose
  if (event.category === 'error') {
    alert(`Nouvelle erreur: ${event.details.description}`);
  }
});

// Unsubscribe
unsubscribe();
```

---

## Performance

- **Lecture**: O(1) - Direct depuis la mémoire
- **Écriture**: O(n) - Itération sur les arrays (petit n)
- **refresh du dashboard** : toutes les 5 secondes
- **Event log** : limité à 500 events (FIFO)

---

## Dépannage

### Les changements ne s'affichent pas

1. Vérifier que /audit/state retourne les bonnes données
   ```bash
   curl http://localhost:4000/audit/state
   ```

2. Vérifier l'auto-refresh dans le dashboard
   ```javascript
   // Dans la console
   autoRefreshInterval  // Doit être actif
   ```

3. Vérifier audit.json a été écrit
   ```bash
   cat audit.json | grep "lastUpdated"
   ```

### Les événements ne sont pas enregistrés

1. Vérifier que le chemin du fichier audit.json est correct
2. Vérifier les permissions d'écriture du fichier
3. Check les logs du serveur pour les erreurs

---

## Conclusion

Le **Audit Logger** transforme le système de backup statique en **système vivant** qui :
- 📊 Synchronise automatiquement avec le projet
- 🔄 Met à jour en temps réel
- 📈 Trace chaque événement
- 🎯 Centralise l'état dans audit.json
- ✅ Rend tout observable et traçable

**Résultat : Un seul fichier (audit.json) pour toute la vérité du système.** 🚀
