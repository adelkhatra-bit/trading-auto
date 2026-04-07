# 🔧 AUDIT DASHBOARD — Guide Complet

## Vue d'ensemble

L'Audit Dashboard est une **surcouche intelligente** de debug et observabilité qui te permet de :
- 📊 Visualiser l'état du système complet en temps réel
- 🔍 Localiser instantanément chaque fichier, tâche ou erreur
- 🎯 Cliquer pour naviguer vers les fichiers concernés
- 📋 Tracer chaque connexion frontend ↔ backend
- ❌ Identifier les erreurs et leurs impacts

## Accès

### Via le menu principal
- S'il y a un serveur actif: [http://localhost:4000/audit](http://localhost:4000/audit)
- Via l'option "🔧 Audit Dashboard" dans le menu principal

### Structure des fichiers
```
trading-auto/
├── audit.json                 ← Base de données centrale du système
├── audit-dashboard.html       ← Interface interactive d'audit
└── index.html                 ← Menu (lien vers /audit)
```

## Fonctionnalités Principales

### 1. Vue d'ensemble (Overview)

Affiche en temps réel :
- **État du backend** : Server, endpoints, agents
- **État du frontend** : Pages, connexions, issues
- **Intégrations** : MT5, TradingView, Extension
- **Prochaines actions** : Tâches prioritaires à faire

### 2. Onglet Fichiers (📁 Files)

Liste COMPLÈTE de tous les fichiers du projet :
- ✅ OK / ⚠️ PARTIAL / ❌ ERROR
- Chemin exact du fichier
- Description et type (backend-core, frontend-page, extension, etc.)
- Fichiers critiques marqués avec ⚠️
- Issues associées
- **Boutons d'action :**
  - 📋 **Copier chemin** → Copie le chemin pour recherche rapide
  - 🎯 **Localiser** → Guide pour ouvrir le fichier dans VS Code

### 3. Onglet Agents (🤖 Agents)

Liste des 23 agents du système :
- Rôle de chaque agent
- Dépendances entre agents
- Statut d'exécution
- Lien direct vers le fichier source

### 4. Onglet Endpoints (🔗 Endpoints)

Tous les 68 endpoints API :
- Méthode HTTP (GET, POST, etc.)
- Chemin exact
- Statut (OK / MISSING / ERROR / OFFLINE)
- Localisation dans le code (ex: `server.js:1031`)
- **Workarounds** pour les endpoints cassés
- **Todo** pour les endpoints à implémenter

**Exemple :**
```
POST /orchestration/run-now
❌ MISSING - HIGH PRIORITY
📝 TODO: Implement in server.js
```

### 5. Onglet Connexions (↔️ Connections)

Visualise le data flow complet :
- `index.html → server.js` (HTTP fetch)
- `studio/studioapp-simple.js → server.js` (HTTP + SSE)
- `public/content.js → TradingView` (DOM injection)
- `public/background.js → server.js` (HTTP POST)
- `MT5-EA → server.js` (Offline - awaiting EA)

Chaque connexion affiche :
- Statut (OK / PARTIAL / OFFLINE)
- Endpoints utilisés
- Issues détectées

### 6. Onglet Erreurs (❌ Errors)

Toutes les erreurs du système :
- **Type** : missing-endpoint, offline-source, etc.
- **Sévérité** : HIGH / MEDIUM / LOW
- **Description** complète
- **Fichier affecté** : Lien vers le fichier problématique
- **Ligne de code** : Localisation exacte
- **Workaround** : Comment contourner l'erreur

**Exemple :**
```
❌ MISSING ENDPOINT
Sévérité: HIGH
Description: POST /orchestration/run-now not implemented
Fichier: index.html
Code: runOrchestration() function (line 380)
Workaround: Endpoint needs to be added to server.js
```

### 7. Onglet Tâches (📋 Tasks)

État d'avancement du projet :
- **Complétées** : Backend, Agents, Studio, Extension
- **En cours** : Real-time data (70%)
- **À faire** : Broker execution (30%), Calendar automation (20%)

Pour chaque tâche :
- Fichiers impliqués
- Pourcentage de complétude
- Issues bloquantes
- Fonctionnalités incluses

## Fonctionnement

### Recherche rapide

Chaque onglet a une **barre de recherche** :
```
📁 Files: Tape "server" → Affiche tous les fichiers contenant "server"
🤖 Agents: Tape "core" → Affiche trading-core et ses dépendances
🔗 Endpoints: Tape "mt5" → Affiche tous les endpoints /mt5/*
```

### Localiser un fichier

Trois méthodes :

**1. Via le bouton "🎯 Localiser"**
- Affiche le chemin exact
- Instructions pour VS Code (Ctrl+P)

**2. Via le bouton "📋 Copier chemin"**
- Copie `./src/agents/orchestrator.js`
- Colle dans terminal ou VS Code

**3. Via Ctrl+P dans VS Code**
- Après avoir copié le chemin
- Tapez le nom du fichier
- Appuyez sur Entrée

### Naviguer entre les onglets

- Clic sur le bouton de l'onglet dans la barre de navigation
- Les données se mettent à jour automatiquement
- La recherche fonctionne dans chaque onglet

## Exemple d'utilisation

### Scénario 1 : Trouver pourquoi index.html a un problème

1. Ouvre l'Audit Dashboard : [http://localhost:4000/audit](http://localhost:4000/audit)
2. Onglet **Erreurs** → Cherche "index"
3. Tu vois : `POST /orchestration/run-now not implemented`
4. Clique sur **📍 Localiser** → Tu identifies le fichier et la ligne
5. Onglet **Endpoints** → Cherche "orchestration" → Tu vois que 2 endpoints manquent
6. **Action** → Ajouter les 2 endpoints à server.js

### Scénario 2 : Vérifier le data flow

1. Onglet **Connexions**
2. Visualise : `index.html → server.js` → **PARTIAL**
3. Clique sur la connexion → Voir les issues détaillées
4. Onglet **Endpoints** → Voir exactement quels endpoints sont manquants
5. **Action** → Implémenter les endpoints manquants

### Scénario 3 : Explorer un agent

1. Onglet **Agents**
2. Clique sur **trading-core** → Voir son rôle, dépendances, features
3.Clique sur **📍 Localiser** → Ouvre le fichier dans VS Code
4. Lis le code → Comprendre sa logique

## Statistiques en temps réel

La en-tête affiche :
- **Fichiers** : 40 fichiers totaux
- **Agents** : 23 agents actifs
- **Endpoints** : 68 routes API
- **Erreurs critiques** : 5 issues haute priorité
- **Tâches OK** : 4/7 complétées

## Mise à jour du Backup

Le fichier `audit.json` est généré UNE FOIS lors de l'analyse.

Pour mettre à jour les données :
1. Ouvre `audit.json`
2. Modifie les statuts (OK → ERROR, etc.)
3. Ajoute des erreurs détectées
4. Reload le dashboard

**Format d'ajout d'erreur :**
```json
{
  "id": "err-6",
  "type": "connection-broken",
  "severity": "high",
  "description": "Studio SSE stream disconnects after 5 minutes",
  "affectedFile": "studio/studioapp-simple.js",
  "affectedCode": "SSE connection handler",
  "line": "Line 245",
  "workaround": "Implement heartbeat/reconnect logic"
}
```

## Intégration Continue (CI/CD)

Le dashboard peut être utilisé pour :

### Avant deployment
- ✅ Vérifier **0 erreurs critiques**
- ✅ Vérifier **tous les endpoints** utilisés sont implémentés
- ✅ Vérifier **toutes les connexions** sont OK

### Monitoring en production
- 📊 Tracker les issues trouvées en prod
- 🔍 Localiser rapidement les fichiers affectés
- 📋 Planifier les fixes

## Architecture du Système

```
┌─────────────────────────────────────┐
│   audit.json (Central Database)     │
│   - files[]                         │
│   - agents[]                        │
│   - endpoints[]                     │
│   - connections[]                   │
│   - errors[]                        │
│   - tasks[]                         │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│ audit-dashboard.html (Interactive)  │
│ - Tabs navigation                   │
│ - Search + Filter                   │
│ - Clickable localization            │
│ - Data visualization                │
└─────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│   GET /audit (server.js)            │
│   Serves audit-dashboard.html       │
└─────────────────────────────────────┘
```

## FAQ

### Q: Peut-on modifier audit.json en production?
**A:** Oui, c'est un fichier de configuration. Mets-le à jour quand tu détectes de nouvelles issues.

### Q: Le dashboard se met à jour automatiquement?
**A:** Non, tu dois rafraîchir la page (F5) ou modifier audit.json manuellement.

### Q: Puis-je exporter le dashboard en PDF?
**A:** Oui, utilise Ctrl+P → Imprimer → Sauvegarder en PDF.

### Q: Comment localiser rapidement une erreur?
**A:** Onglet Erreurs → Clique sur le fichier → Copie le chemin → Ctrl+P dans VS Code → Colle et cherche.

## Checklist de Déploiement

Avant de déployer en production :

- [ ] Onglet **Erreurs** : Vérifier qu'il n'y a pas d'erreurs **HIGH**
- [ ] Onglet **Endpoints** : Vérifier que **tous les endpoints utilisés** sont **OK**
- [ ] Onglet **Connexions** : Vérifier que **toutes les connexions** sont **OK**
- [ ] Onglet **Tâches** : Vérifier que **tâches critiques** sont **OK**
- [ ] Onglet **Fichiers** : Vérifier ni les fichiers **CRITICAL** ont des issues

## Support

Pour toquer aide avec le dashboard :
1. Consulte l'Audit Dashboard lui-même pour les détails
2. Vérifie audit.json pour la structure des données
3. Ouvre audit-dashboard.html dans VS Code pour lire le code

---

**📊 Audit Dashboard v1.0** — Créé pour la transparence totale du système.

✅ **L'Audit Dashboard est maintenant actif et prêt à l'emploi !**
