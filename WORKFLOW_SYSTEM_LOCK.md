# 🔒 WORKFLOW SYSTÈME GLOBAL — IMMUABLE

**Date:** 3 avril 2026  
**Statut:** VERROUILLÉ — S'applique à TOUS les agents SANS EXCEPTION  
**Validé par:** Utilisateur principal  

---

# 🚨 RÈGLE ABSOLUE

**AUCUN AGENT ne peut agir directement**

**CHAQUE action doit passer par le workflow obligatoire dans l'ordre exact**

---

# 🔁 LES 7 ÉTAPES OBLIGATOIRES (ORDRE IMMUABLE)

## ÉTAPE 1 — ANALYSE (Agent Mémoire) 
**Avant TOUTE action**

L'agent mémoire analyse:
- ✅ Tous les fichiers existants
- ✅ Tous les modules existants
- ✅ Toutes les functions existantes
- ✅ Toutes les dépendances
- ✅ Toutes les liaisons

**Objectif:** Savoir exactement ce qui existe avant de faire quoi que ce soit

**Output:** "Ça existe déjà dans [fichier] ligne [X], fonction [Y]"

---

## ÉTAPE 2 — COMPRÉHENSION
**Après analyse**

- Comprendre la structure actuelle
- Comprendre les flux inter-agents
- Comprendre les liaisons existantes
- Comprendre ce qui est déjà branché

**Objectif:** Avoir une cartographie mentalale complète du système

---

## ÉTAPE 3 — LOCALISATION
**Avant modification**

- Identifier le bon fichier précis
- Identifier la bonne fonction précise
- Identifier l'emplacement exact (ligne N)
- Vérifier qu'il n'existe PAS déjà sous une autre forme

**Objectif:** Savoir EXACTEMENT où modifier

```
Exemple:
❌ "Il faut ajouter la localisation"
✅ "audit-logger.js ligne 145, fonction logEvent(), 
    avant le return statement, ajouter getCallerLocation()"
```

---

## ÉTAPE 4 — RÉPARATION / COMPLÉTION
**Ensuite seulement**

- Réparer ce qui existe
- Compléter ce qui manque
- Brancher correctement
- NE PAS recréer ce qui existe déjà
- NE PAS casser le système existant

**RÈGLES STRICTES:**
- ❌ Jamais copier-coller un code existant ailleurs
- ❌ Jamais redéfinir une fonction existante
- ❌ Jamais dupliquer un module
- ✅ Toujours enrichir en place
- ✅ Toujours réutiliser ce qui existe
- ✅ Toujours modifier dans le bon fichier

---

## ÉTAPE 5 — TEST (Agent Testeur) ⚠️ OBLIGATOIRE
**AVANT toute intégration**

L'agent testeur vérifie:
- ✅ Rien n'est cassé
- ✅ Les fonctions existantes marchent toujours
- ✅ Les connexions sont correctes
- ✅ Le système reste stable
- ✅ Les performances sont OK
- ✅ Pas de régressions

**Test minimum:**
```javascript
// Line 1: Vérifier le fichier se charge sans erreur
const module = require('./fichier-modifié.js');

// Line 2: Vérifier que les fonctions existantes marchent
console.log(module.existingFunction('test'));

// Line 3: Vérifier les nouvelles additions
console.log(module.newFunction('test'));

// Line 4: Vérifier les liaisons
const linked = require('./autre-fichier.js');
console.log(linked.callsModifiedFunction());
```

**Output:** "✅ Tous les tests passent" ou "❌ Erreur détectée: ligne X, raison Y"

**🚨 AUCUN changement ne passe sans validation testeur**

---

## ÉTAPE 6 — DEMANDE VALIDATION (Si important)
**Si modification importante**

- Expliquer ce qui a été modifié
- Expliquer l'impact sur le système
- Attendre validation avant intégration

**Exemple:**
```
❌ FAUX: "J'ai modifié server.js"
✅ BON: "J'ai enrichi audit-logger.js ligne 145, 
         ajou getCallerLocation() qui ajoute 
         {file, function, line} à chaque log audit. 
         Impact: +20 lignes, zéro breaking change, 
         testeur a validé ✅"
```

---

## ÉTAPE 7 — INTÉGRATION (SEULEMENT APRÈS VALIDATION)
**Seulement si étapes 1-6 OK**

- Intégrer dans le système
- Mettre à jour library.json
- Enregistrer dans audit
- Documenter la modification

---

# 🧠 AGENT MÉMOIRE — STRUCTURE OBLIGATOIRE

**Ce n'est PAS un agent métier**

C'est:
- La mémoire centrale du système
- Le registre complet des fichiers
- Le système de localisation
- Le gardien anti-doublon

## Données que l'agent mémoire maintient

```json
{
  "files": {
    "audit-logger.js": {
      "path": "audit-logger.js",
      "lines": 280,
      "functions": ["logEvent()", "updateTask()", "completeTask()"],
      "exports": ["AuditLogger"],
      "used_by": ["server.js"],
      "status": "active"
    }
  },
  
  "functions": {
    "logEvent": {
      "file": "audit-logger.js",
      "line": 45,
      "signature": "logEvent(type, message, meta)",
      "purpose": "Enregistre un event dans audit.json"
    }
  },
  
  "routes": {
    "GET /audit/state": {
      "file": "server.js",
      "line": 442,
      "returns": "complete audit state"
    }
  },
  
  "agent_registry": {
    "tradingCore": {
      "file": "src/agents/trading-core.js",
      "active": true,
      "calls": ["MT5"]
    }
  }
}
```

## Interface minimale agent mémoire

```javascript
class LibraryAgent {
  constructor() {
    this.registry = require('./library.json');
  }
  
  // Avant TOUTE action
  analyze(concept) {
    // "Existe-t-il une fonction logEvent?"
    // "Existe-t-il un module alert-manager?"
    // Retour: {exists: true, location: "audit-logger.js:45"}
  }
  
  findFile(concept) {
    // "Où est la gestion des réconciliations?"
    // Retour: {file: "audit-logger.js", status: "complete"}
  }
  
  getLocation(functionName) {
    // "Où exactement est logEvent()?"
    // Retour: {file, line, function_signature}
  }
  
  checkDuplicate(feature) {
    // "Est-ce qu'il y a déjà une création d'alerts?"
    // Retour: {exists: yes/no, whereExactly: "alert-manager.js:120"}
  }
  
  suggestBestPlace(newFeature) {
    // "Où je dois ajouter la localisation?"
    // Retour: {file: "audit-logger.js", 
    //          function: "logEvent", 
    //          beforeLine: 145,
    //          reason: "logEvent est l'endroit central pour tous les logs"}
  }
}
```

---

# 🧪 AGENT TESTEUR — STRUCTURE OBLIGATOIRE

**Ce n'est PAS un agent métier**

C'est:
- Le validateur de toutes les modifications
- Gardien de la stabilité système
- Détecteur de régressions
- Vérificateur de performance

## Responsabilités obligatoires

Pour CHAQUE modification:
1. ✅ Vérifie le fichier charge sans erreur
2. ✅ Vérifie fonctions existantes marchent
3. ✅ Vérifie nouvelles additions marchent
4. ✅ Vérifie liaisons inter-modules
5. ✅ Vérifie pas de régression
6. ✅ Vérifie perfs (pas de CPU spike)

## Interface minimale agent testeur

```javascript
class TestAgent {
  async testModification(filePath, changes) {
    // Charge le fichier
    const result = this.loadFile(filePath);
    if (!result.ok) return {ok: false, error: result.error};
    
    // Teste les fonctions existantes
    const existingTests = await this.testExisting(filePath);
    if (!existingTests.ok) return existingTests;
    
    // Teste les nouvelles additions
    const newTests = await this.testNew(filePath, changes);
    if (!newTests.ok) return newTests;
    
    // Teste les liaisons
    const linkTests = await this.testLinks(filePath);
    if (!linkTests.ok) return linkTests;
    
    // Test de performance
    const perfTests = await this.testPerformance(filePath);
    if (!perfTests.ok) return perfTests;
    
    // Tous les tests passent
    return {
      ok: true,
      summary: "✅ File loads, existing functions work, new additions work, no breaking changes, performance OK"
    };
  }
  
  // Test chaque fonction du fichier
  async testExisting(filePath) {
    // Charge chaque export
    // Appelle chaque fonction avec données test
    // Vérifie pas d'erreur
    // Retour: {ok: true/false, details: {...}}
  }
  
  // Test les nouvelles additions
  async testNew(filePath, changes) {
    // Teste les new functions/exports
    // Teste les paramètres
    // Retour: {ok: true/false, error: "Y si erreur"}
  }
  
  // Teste liaisons avec autres modules
  async testLinks(filePath) {
    // Charge autres modules qui l'utilisent
    // Vérifie ils marchent toujours
    // Retour: {ok: true/false, broken: [...]}
  }
  
  // Vérifie performance
  async testPerformance(filePath) {
    // Exécute le nouvelle code
    // Mesure temps d'exécution
    // Vérifie pas de spike
    // Retour: {ok: true/false, time: "150ms"}
  }
}
```

---

# 📋 CHECKLIST D'APPLICATION STRICTE

**AVANT TOUT CODING:**

## Pour CHAQUE agent, CHAQUE action, CHAQUE modification

- [ ] **Étape 1**: Agent mémoire analyses "Ça existe où?"
- [ ] **Étape 2**: Comprendre structure + flux
- [ ] **Étape 3**: Localiser fichier exact + ligne exacte
- [ ] **Étape 4**: Réparer/compléter EN PLACE (pas recréer)
- [ ] **Étape 5**: Agent testeur execute tests complets
- [ ] **Étape 6**: Demande validation si impact important
- [ ] **Étape 7**: Intégrer seulement si tout OK

---

# 🚨 INTERDICTIONS ABSOLUES

❌ **Agent qui agit SANS passer par agent mémoire**
→ Risque doublons, créations inutiles

❌ **Modification SANS passer par agent testeur**
→ Risque régressions, système cassé

❌ **Intégration SANS validation testeur**
→ Risque instabilité

❌ **Créer nouveau code au lieu de compléter existant**
→ Risque duplication, maintenance cauchemar

❌ **Oublier de mettre à jour library.json**
→ Risque mémoire système un jour obsolète

---

# 💬 CANAL INTERNE CENTRAL (JOURNAL DE COORDINATION)

**Concept:** Un flux structuré interne au système pour tracer l'exécution du workflow

Ce n'est PAS un chat séparé, c'est un **journal central de coordination** :
- Interne au système (pas une conversation externalisée)
- Visible dans le dashboard pour suivi
- Historisé dans audit.json pour traçabilité
- Utilisé par les agents pour coordonner leurs actions
- Entièrement structuré (pas de texte libre, format strict)

## Intégration au système

**Structure fichier (existant + minimal ajout):**
```
audit.json → workflowLog[] (array structuré)
server.js → Enregistre chaque étape du workflow
server.js → Route GET /workflow/log (retourne le dernier état)
AGENTS_MONITOR.html → Onglet "Workflow" affiche le journal en tableau
dashboard → Filtre par agent / fichier / status
```

**Log Entry Structure (standardisé):**
```javascript
{
  timestamp: "2026-04-03T10:30:45.123Z",
  step: 1,                    // Numéro étape (1-7)
  stepName: "analyse",        // Nom étape
  agent: "agent-memory",      // Quel agent
  context: {
    file: "audit-logger.js",  // Sur quel fichier
    function: "logEvent",     // Quelle fonction
    line: 145,                // Quelle ligne
    concept: "localisation"   // Quel concept
  },
  action: "found",            // Action réelle (found, proposed, pass, fail, integrated)
  status: "approved",         // Status (info, pending, approved, rejected, error)
  message: "audit-logger.js existe ligne 145", // Message court
  result: { /* données si importants */ }      // Résultats si utiles
}
```

## Intégration Dashboard (Performance optimisée)

**AGENTS_MONITOR.html onglet "Workflow":**

```html
<!-- Onglet 6: Workflow Log (Journal) -->
<div id="tab-workflow" class="tab-content">
  <h2>Journal Workflow (Canal Central)</h2>
  <div style="margin-bottom: 10px;">
    <button onclick="refreshWorkflowLog()" style="padding: 5px 10px;">
      🔄 Rafraîchir (manuel)
    </button>
    <small style="margin-left: 10px;">Mis à jour via SSE</small>
  </div>
  
  <table id="workflow-table" style="width: 100%; font-size: 12px;">
    <thead>
      <tr style="border-bottom: 2px solid #333;">
        <th>Heure</th>
        <th>Agent</th>
        <th>Étape</th>
        <th>Fichier</th>
        <th>Action</th>
        <th>Status</th>
        <th>Message</th>
      </tr>
    </thead>
    <tbody id="workflow-body">
      <!-- Lignes injectées ici -->
    </tbody>
  </table>
</div>

<script>
// SSE listener (reçoit les mises à jour en temps réel)
const sseListener = new EventSource('/stream');

sseListener.addEventListener('workflow-update', (event) => {
  // Mise à jour reçue du serveur via SSE
  const data = JSON.parse(event.data);
  appendWorkflowRow(data);
  // Scroll vers le bas automatique
  document.getElementById('workflow-table').scrollIntoView(false);
});

// Rafraîchissement manuel (charge l'état complet)
async function refreshWorkflowLog() {
  const res = await fetch('/workflow/log');
  const logs = await res.json();
  
  const tbody = document.getElementById('workflow-body');
  tbody.innerHTML = logs.map(log => `
    <tr style="border-bottom: 1px solid #ddd;">
      <td>${new Date(log.timestamp).toLocaleTimeString()}</td>
      <td><strong>${log.agent}</strong></td>
      <td>Étape ${log.step}</td>
      <td>${log.context.file}</td>
      <td>${log.action}</td>
      <td style="color: ${log.status === 'approved' ? 'green' : log.status === 'rejected' ? 'red' : 'orange'};">
        ${log.status}
      </td>
      <td>${log.message}</td>
    </tr>
  `).join('');
}

// Ajouter une ligne au tableau (via SSE)
function appendWorkflowRow(log) {
  const tbody = document.getElementById('workflow-body');
  const row = document.createElement('tr');
  row.style.borderBottom = '1px solid #ddd';
  row.innerHTML = `
    <td>${new Date(log.timestamp).toLocaleTimeString()}</td>
    <td><strong>${log.agent}</strong></td>
    <td>Étape ${log.step}</td>
    <td>${log.context.file}</td>
    <td>${log.action}</td>
    <td style="color: ${log.status === 'approved' ? 'green' : log.status === 'rejected' ? 'red' : 'orange'};">
      ${log.status}
    </td>
    <td>${log.message}</td>
  `;
  tbody.insertBefore(row, tbody.firstChild); // Ajouter en haut
  
  // Garder seulement les 50 dernières lignes
  while (tbody.children.length > 50) {
    tbody.removeChild(tbody.lastChild);
  }
}

// Charge initiale au chargement
document.addEventListener('DOMContentLoaded', refreshWorkflowLog);
</script>
```

**Stratégie Performance:**
1. **SSE prioritaire:** Quand un agent enregistre une action, le serveur envoie via SSE `workflow-update`
2. **Pas d'auto-refresh lourd:** Pas de polling en boucle
3. **Bouton manuel disponible:** Si utilisateur veut forcer un rafraîchissement
4. **Affichage limité:** Seulement les 50 dernières lignes en mémoire DOM
5. **Charge minimale:** SSE event = une ligne ajoutée au tableau

## Comment elle est historisée (audit.json)

**audit.json contient workflowLog[]:**

```javascript
{
  "workflowLog": [
    {
      "timestamp": "2026-04-03T10:30:45.123Z",
      "step": 1,
      "stepName": "analyse",
      "agent": "agent-memory",
      "context": {
        "file": "audit-logger.js",
        "function": "logEvent",
        "line": 145,
        "concept": "localisation"
      },
      "action": "found",
      "status": "info",
      "message": "audit-logger.js existe ligne 145"
    },
    {
      "timestamp": "2026-04-03T10:30:46.456Z",
      "step": 4,
      "stepName": "réparation",
      "agent": "repair-agent",
      "context": {
        "file": "audit-logger.js",
        "function": "logEvent",
        "line": 145,
        "concept": "localisation"
      },
      "action": "proposed",
      "status": "pending",
      "message": "Ajouter getCallerLocation() +20 lignes",
      "result": {
        "file": "audit-logger.js",
        "linesAdded": 20,
        "functionEnhanced": "logEvent"
      }
    },
    {
      "timestamp": "2026-04-03T10:30:47.789Z",
      "step": 5,
      "stepName": "test",
      "agent": "test-agent",
      "context": {
        "file": "audit-logger.js",
        "function": "logEvent"
      },
      "action": "pass",
      "status": "approved",
      "message": "✅ Tous tests passent: charge OK, fonctions existantes OK, liaisons OK",
      "result": {
        "testsRun": 8,
        "testsPassed": 8,
        "regressionDetected": false,
        "performanceOK": true
      }
    },
    {
      "timestamp": "2026-04-03T10:30:48.901Z",
      "step": 7,
      "stepName": "intégration",
      "agent": "system",
      "context": {
        "file": "audit-logger.js"
      },
      "action": "integrated",
      "status": "approved",
      "message": "✅ Intégration réussie",
      "result": {
        "filesModified": ["audit-logger.js", "library.json"]
      }
    }
  ]
}
```

**audit-logger.js enrichi (minimal):**

```javascript
class AuditLogger {
  constructor() {
    this.workflowLog = [];  // NEW: Array des étapes workflow
    this.loadFromDisk();
  }
  
  // Enregistrer une étape du workflow
  logWorkflowStep(step, stepName, agent, context, action, status, message, result = {}) {
    const entry = {
      timestamp: new Date().toISOString(),
      step,           // 1-7
      stepName,       // "analyse", "réparation", "test", etc
      agent,          // "agent-memory", "test-agent", "repair-agent", "system"
      context,        // {file, function, line, concept}
      action,         // "found", "proposed", "pass", "fail", "integrated"
      status,         // "info", "pending", "approved", "rejected", "error"
      message,        // Court texte descriptif
      result          // Données supplémentaires si utiles
    };
    
    this.workflowLog.push(entry);
    
    // Garder seulement les 1000 dernières étapes
    if (this.workflowLog.length > 1000) {
      this.workflowLog = this.workflowLog.slice(-1000);
    }
    
    this.saveToDisk();
    return entry;
  }
  
  // Retourner dernier état du workflow
  getWorkflowLog(limit = 100) {
    if (limit) {
      return this.workflowLog.slice(-limit);
    }
    return this.workflowLog;
  }
  
  // Retourner étapes d'un fichier spécifique
  getWorkflowByFile(fileName) {
    return this.workflowLog.filter(entry => entry.context.file === fileName);
  }
  
  // Retourner étapes d'un agent spécifique
  getWorkflowByAgent(agentName) {
    return this.workflowLog.filter(entry => entry.agent === agentName);
  }
}
```

**server.js routes (minimal):**

```javascript
// GET /workflow/log — Retourne l'historique workflow
app.get('/workflow/log', (req, res) => {
  const logs = auditLogger.getWorkflowLog(req.query.limit || 100);
  res.json(logs);
});

// GET /workflow/log/file/:fileName — Filtrer par fichier
app.get('/workflow/log/file/:fileName', (req, res) => {
  const logs = auditLogger.getWorkflowByFile(req.params.fileName);
  res.json(logs);
});

// POST /workflow/log — Les agents enregistrent une étape
app.post('/workflow/log', (req, res) => {
  const { step, stepName, agent, context, action, status, message, result } = req.body;
  
  const entry = auditLogger.logWorkflowStep(
    step, stepName, agent, context, action, status, message, result
  );
  
  // Broadcast via SSE à tous les clients
  sseClients.forEach(client => {
    client.write(`event: workflow-update\n`);
    client.write(`data: ${JSON.stringify(entry)}\n\n`);
  });
  
  res.json({ok: true, entry});
});
```

## Comment les agents l'utilisent (Fonction Helper)

**Helper utilitaire pour tous les agents:**

```javascript
// utils/workflow-logger.js

async function logWorkflowStep(step, stepName, agent, context, action, status, message, result = {}) {
  return fetch('http://localhost:4000/workflow/log', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      step,       // 1-7
      stepName,   // "analyse", "test", etc
      agent,      // Nom de l'agent
      context,    // {file, function, line, concept}
      action,     // "found", "pass", "fail", etc
      status,     // "info", "approved", "rejected", "error"
      message,    // Court texte
      result      // Données supplémentaires
    })
  });
}

module.exports = { logWorkflowStep };
```

**Exemple: Agent Mémoire enregistre une analyse**

```javascript
// Étape 1: ANALYSE
const {logWorkflowStep} = require('./utils/workflow-logger');

async function analyzeSystem(concept) {
  const exists = findFile('audit-logger.js');
  
  // Enregistrer l'étape 1 dans le journal
  await logWorkflowStep(
    1,                    // Étape 1
    'analyse',            // Nom étape
    'agent-memory',       // Quel agent
    {
      file: 'audit-logger.js',
      function: 'logEvent',
      line: 145,
      concept: concept
    },                    // Contexte exact
    exists ? 'found' : 'not-found',  // Action réelle
    'info',               // Status
    exists 
      ? 'audit-logger.js existe ligne 145'
      : 'audit-logger.js non trouvé'
  );
  
  return {exists, location: exists ? 145 : null};
}
```

**Exemple: Agent Testeur enregistre résultat test**

```javascript
// Étape 5: TEST
async function validateModification(filePath, changes) {
  const testResult = runTests(filePath);
  
  if (testResult.ok) {
    // Test PASS
    await logWorkflowStep(
      5,                  // Étape 5
      'test',             // Nom étape
      'test-agent',       // Quel agent
      {file: filePath},   // Contexte
      'pass',             // Action: test réussi
      'approved',         // Status: approuvé
      `✅ Tous tests passent`,
      {
        testsRun: testResult.count,
        testsPassed: testResult.count,
        regressionDetected: false,
        performanceOK: true
      }
    );
    return {ok: true};
  } else {
    // Test FAIL
    await logWorkflowStep(
      5,
      'test',
      'test-agent',
      {file: filePath},
      'fail',             // Action: test échoué
      'rejected',         // Status: rejeté
      `❌ FAIL: ${testResult.error}`,
      {
        testsRun: testResult.count,
        testsPassed: testResult.passed,
        error: testResult.error
      }
    );
    return {ok: false, error: testResult.error};
  }
}
```

**Exemple: Repair Agent enregistre proposition**

```javascript
// Étape 4: RÉPARATION
async function proposeRepair(concept) {
  const repair = generateRepair(concept);
  
  await logWorkflowStep(
    4,                  // Étape 4
    'réparation',       // Nom étape
    'repair-agent',     // Quel agent
    {
      file: repair.file,
      function: repair.function,
      line: repair.line,
      concept: concept
    },
    'proposed',         // Action: proposition
    'pending',          // Status: en attente
    `Proposition: ${repair.description}`,
    {
      file: repair.file,
      linesAdded: repair.linesAdded,
      linesRemoved: repair.linesRemoved,
      functionEnhanced: repair.function,
      changeType: repair.type
    }
  );
  
  return repair;
}
```

## Message Types (Standardisés)

```javascript
const MESSAGE_TYPES = {
  // Agent Mémoire
  'analysis': 'L\'agent mémoire a trouvé quelque chose',
  'duplicate-found': 'Doublon détecté',
  'location-found': 'Localisation trouvée',
  
  // Agent Réparateur
  'proposal': 'Proposition de modification',
  'repair-start': 'Réparation commencée',
  'repair-complete': 'Réparation terminée',
  
  // Agent Testeur
  'validation': 'Résultat de test',
  'test-pass': 'Test réussi',
  'test-fail': 'Test échoué',
  'regression-detected': 'Régression détectée',
  
  // Système
  'error': 'Erreur système',
  'warning': 'Avertissement',
  'info': 'Information',
  'integration': 'Intégration effectuée'
};

const MESSAGE_STATUS = [
  'info',              // Information
  'pending_review',    // En attente de validation
  'approved',          // Approuvé
  'rejected',          // Rejeté
  'error',             // Erreur
  'warning',           // Avertissement
  'integrated'         // Intégré
];
```

## Timeline exemple

```
10:30:45 | agent-memory    | analysis    | audit-logger.js existe ligne 145
10:30:46 | repair-agent    | proposal    | Ajouter getCallerLocation() +20 lignes
10:30:47 | test-agent      | validation  | ✅ PASS audit-logger.js
10:30:48 | system          | integration | ✅ Intégré avec succès
10:30:49 | audit-logger    | info        | library.json mis à jour
```

---

# ✅ CONFIRMATIONS OBLIGATOIRES (MISES À JOUR)

**Je confirme:**

- ✅ Ce workflow s'applique à **TOUS les agents SANS EXCEPTION**
- ✅ Aucun agent ne peut intégrer **SANS passer par agent testeur**
- ✅ Aucune création ne se fait **SANS vérification agent mémoire**
- ✅ Les 7 étapes doivent être **dans cet ordre exact immuable**
- ✅ Chaque modification est **testée et validée**
- ✅ Chaque action est **enregistrée en audit**
- ✅ Le système reste **100% stable** à chaque étape
- ✅ **Conversation centrale** relie tous les agents
- ✅ **Dashboard onglet Conversation** affiche le flux en temps réel
- ✅ **audit.json** historise toute la conversation
- ✅ **SSE broadcasts** envoient les mises à jour live

---

# 🎯 OBJECTIF FINAL

**Un système:**
- Jamais de doublons
- Jamais d'erreurs sournoise
- Toujours stable
- Toujours retrouvable
- Toujours validé avant intégration

**Chaque agent sait:**
- Où il est
- Où il va
- Pourquoi il y va
- Qu'il a été testé avant d'agir

---

# 🚀 SIGNATURE VALIDATION

**L'utilisateur confirme:**

- ✅ Ce workflow est valide et immuable
- ✅ Tous les agents le respectent
- ✅ Aucun agent n'a le droit de dévier
- ✅ On peut maintenant lancer le coding en confiance

**Prêt à coder ?** → OUI (si confirmé)

