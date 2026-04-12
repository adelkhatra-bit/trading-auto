# TASK PROTOCOL — TRADING AUTO

## PROTOCOLE OBLIGATOIRE

### ÉTAPE 0 — AVANT TOUT
- Lire .instructions.md
- Lire WORKSPACE_MAP.md
- Lire DO_NOT_TOUCH.md
- Lire ce fichier

### ÉTAPE 1 — SÉCURITÉ
- git status
- commit sécurité

### ÉTAPE 2 — SERVER FIRST
- Corriger server.js si besoin
- Démarrer le serveur
- Vérifier port 4000
- Vérifier dashboard accessible

### ÉTAPE 3 — DATA LIVE
- Vérifier réception TradingView
- Vérifier POST /tradingview/live
- Vérifier stockage live
- Vérifier exposition au dashboard

### ÉTAPE 4 — DASHBOARD
- Alimenter les blocs existants :
  - prix live
  - spread
  - direction
  - signal
  - source
  - maj
  - clôture bougie
  - speed M1

### ÉTAPE 5 — EXTENSION
- Conserver le design
- Corriger uniquement la logique
- Vérifier synchro live

### ÉTAPE 6 — AGENT
- ANALYSER doit lancer un agent réel
- L’agent doit expliquer en texte
- La voix vient seulement après flux réel OK

## RÈGLE
Si une étape n’est pas validée, ne pas passer à la suivante.

## REPAIR EXECUTION LOCK

Si un bug est déjà prouvé :
- l’agent n’attend plus
- l’agent ne demande plus
- l’agent répare

Il n’a plus le droit de dire :
- "je commence"
- "je vais analyser"
- "je vais vérifier"

Il doit directement produire :
- correction
- restart
- preuve

