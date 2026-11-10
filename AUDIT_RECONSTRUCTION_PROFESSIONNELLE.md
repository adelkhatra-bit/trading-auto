# Audit de reconstruction — Trading Auto

Date: 2026-11-10  
Base auditée: `main` à `2d72122abdaa7dc6d9d0d37973c765ccfb098329`  
Branche de travail: `audit/reconstruction-professional-platform`

## Objectif verrouillé

Reconstituer et renforcer la plateforme sans retirer les fonctionnalités historiques. Le terme « nettoyer » signifie corriger, fiabiliser, dédupliquer et intégrer — jamais simplifier en supprimant une capacité utile. Les changements de stratégie doivent rester compatibles avec l'indicateur ALIGN MTF PRO et être couverts par des tests.

## Inventaire retrouvé

### 1. Bot Telegram ALIGN BTC + Gold
- Fichier principal: `align-bot/align_bot.py` (3 370 lignes).
- Données BTC: Kraken OHLC.
- Données Gold: spot Swissquote avec bougies futures Yahoo et solution de repli PAXG/Kraken.
- Unités présentes: 1m, 2m, 5m, 10m, 15m, 30m, 45m, 1h, 2h, 4h, Daily; pondérations multi-unités définies.
- Règles visibles: tendance 4h, confirmation 1h, contexte 15m, déclencheur 5m clôturé; gestion de sessions, niveaux journaliers/hebdomadaires, ATR, news, stop et objectifs.
- Le bot gère aussi les abonnements, les messages gratuits/VIP, le suivi de position, les résultats et les alertes Telegram. Ces fonctions sont à préserver.

### 2. IA du bot
- La fonction `ia()` appelle un endpoint compatible OpenAI.
- Fournisseurs déclarés: Google Gemini (`gemini-flash-latest`, clé `GEMINI_API_KEY` requise), puis OVH Llama, OVH Mistral, Pollinations et LLM7.
- La fonction enregistre le dernier fournisseur ayant répondu dans `ia_ok`; en cas d'échec global, elle conserve l'analyse interne et prévient le propriétaire.
- **Limite vérifiée dans le code:** une liste de fournisseurs configurés n'est pas une preuve de disponibilité ni de qualité. Les fournisseurs OVH sont appelés sans authentification dans ce code; leur accès réel doit être testé. Gemini n'est essayé que si le secret est présent. Il n'y a pas, dans le code examiné, de preuve d'un modèle OpenAI/OpenAI API branché.
- L'IA est un commentateur contraint par les données et le verdict du bot; elle ne remplace pas le moteur de calcul des signaux. Il faut conserver cette séparation et l'expliciter.

### 3. Actualités et macro
- `src/agents/news-intelligence.js`: flux ForexLive, Kitco, Reuters et FXStreet; recherche d'actualités CoinGecko et Reuters commodities; filtrage par symbole et calendrier.
- `src/agents/newsAgent.js`: contient des exemples de news et de breaking news codés en dur/simulés. Ne doit pas être présenté comme un flux réel.
- `src/agents/macroAgent.js`: calendrier économique et score macro simple; dépend d'une source externe à vérifier.
- `tradingview-analyzer/news-engine.js`: consomme `/economic-events`, met en cache 5 minutes, filtre les événements par actif et estime un biais à partir de forecast/previous/actual. Cette inférence est heuristique, pas une analyse IA.
- `tradingview-analyzer/economic-calendar.js`: interface calendrier qui consomme également `/economic-events`.
- Les flux et calendriers doivent exposer la source, l'heure de publication, l'heure de dernière mise à jour, la devise/pays, l'importance, l'événement et le statut de fraîcheur.

### 4. Sessions et ouvertures
- `tradingview-analyzer/market-session.js`: sessions Sydney, Tokyo, Londres, Francfort, New York, pré-marché US, cash US et after-hours; événements d'ouverture/fermeture et chevauchements.
- Les heures sont codées en UTC fixes. Les changements d'heure saisonniers et calendriers propres aux places ne sont pas gérés de manière robuste dans ce module. Les horaires doivent être corrigés avec des fuseaux IANA et calendriers de jours fériés, sans supprimer les sessions existantes.
- `lib/market-hours-checker.js`: autre module d'horaires à rapprocher pour éviter deux vérités différentes.

### 5. Agents de la plateforme
- `src/agents/orchestrator.js` appelle notamment `news-intelligence` et les modules techniques/état du marché.
- `src/agents/indicator-agent.js`: RSI, EMA, MACD, confluences et génération MQL5; vérifier son branchement réel au flux principal.
- `src/agents/strategyManager.js`, `riskManager.js`, `timeframe-consensus.js`, `market-state.js`, `fear-index.js`, `trading-core.js`, `tradeValidator.js`, `supervisor.js`, `surveillance-agent.js`, `stateManager.js` et `syncManager.js` existent et doivent être cartographiés avant toute modification.
- L'audit historique `AUDIT_EXISTANT.md` signale plusieurs agents disponibles mais non appelés à la date de ce document historique. Leur statut doit être revérifié dans le code actuel avant de les activer.

## Écarts et risques prioritaires

1. **Sources non qualifiées:** distinguer données live, cache, simulation, heuristique et indisponibilité. Aucune donnée simulée ne doit apparaître comme actualité réelle.
2. **IA non prouvée en production:** ajouter un contrôle de santé réel par fournisseur (authentification, modèle, latence, réponse, erreur), avec fournisseur actif affiché. Ne jamais annoncer « IA connectée » si le test n'a pas réussi.
3. **Dépendance IA:** les signaux déterministes et la gestion du risque restent maîtres; l'IA enrichit le contexte et peut renforcer une interdiction, jamais inventer prix ou événements.
4. **Calendrier économique:** vérifier la source du endpoint `/economic-events`, sa couverture mondiale, ses timestamps/timezones, ses événements reportés et les discours. Les flux RSS généraux ne remplacent pas un calendrier économique.
5. **Discours et annonces:** détecter les discours des banques centrales et publications officielles; récupérer/transcrire le contenu uniquement depuis des sources accessibles et légales; résumer les éléments nouveaux et leur impact potentiel.
6. **Ouvertures mondiales:** fuseaux IANA, DST, jours fériés, pré-ouverture, ouverture cash, clôture, after-hours, réouverture et gaps.
7. **Indicateur ALIGN:** construire une matrice de parité entre règles TradingView et bot Python; aucun changement de seuil, timeframe ou pondération sans test de non-régression.
8. **Risque et exécution:** séparer recommandation, simulation et ordre réel; aucun passage live automatique sans contrôle explicite du mode, du broker et des limites.
9. **Observabilité:** statut par actif, dernière bougie, source, fraîcheur, dernière analyse, fournisseur IA, dernière alerte envoyée, erreurs et raison d'un refus de signal.

## Architecture cible

1. **Collecte:** prix/bougies, calendrier officiel, news vérifiées, discours, annonces géopolitiques et horaires des places.
2. **Normalisation:** fuseaux, horodatages, dédoublonnage, provenance, fraîcheur et mapping par actif.
3. **Analyse fondamentale IA:** résumés sourcés, extraction des chiffres/ton/changement de guidance, classification de l'impact et horizon (immédiat, séance, plusieurs jours).
4. **Analyse technique ALIGN:** indicateurs et règles actuels, multi-timeframes, zones, volatilité et clôtures confirmées.
5. **Fusion/risque:** consensus explicable, blocage pré-news, spread/volatilité, invalidation, stop, objectifs et taille.
6. **Diffusion:** Telegram en français simple, sans jargon inutile, avec actif, biais, raison, événement/source, heure, niveaux et statut.
7. **Surveillance:** contrôles périodiques, alertes d'indisponibilité et journal d'audit.

## Plan d'exécution sans régression

- Phase A — inventaire exhaustif des routes, modules, agents, variables, workflows, secrets requis et fonctions UI; identifier les fichiers critiques et les doublons.
- Phase B — tests de caractérisation des comportements existants et sauvegarde des sorties de référence.
- Phase C — fiabilisation des sources d'actualités, calendrier, discours et sessions; ajout de provenance et fraîcheur.
- Phase D — branchement et test réel du fournisseur IA principal, puis fournisseurs de secours explicitement authentifiés/validés; afficher le fournisseur réellement utilisé.
- Phase E — intégration contrôlée au moteur de décision sans modifier les règles ALIGN non couvertes par tests.
- Phase F — tests BTC/Gold, marchés ouverts/fermés, news imminente, news publiée, flux indisponible, IA indisponible, changement d'heure, jours fériés et Telegram.
- Phase G — rapport de parité, validation CI et déploiement contrôlé. Ne pas fusionner en production tant que les contrôles critiques échouent.

## Critères d'acceptation

- Zéro suppression non approuvée d'une fonctionnalité historique.
- Chaque actualité/événement porte source et horodatage; les données périmées sont signalées.
- Les discours et événements à fort impact sont repérés avant leur horaire quand la source les publie à l'avance.
- Les ouvertures/fermetures sont exactes selon le fuseau local de la place et le calendrier de jours fériés.
- Le tableau de bord et Telegram indiquent le fournisseur IA réellement actif, ou « IA indisponible ».
- Les signaux ALIGN restent conformes aux tests de référence.
- Les erreurs de source ou d'IA ne produisent jamais de faux signal ni de fausse confirmation.
- CI verte et validation sur données réelles avant activation live.

## État de ce document

Cet audit est une première cartographie basée sur le code et les documents de `main`. Il ne prétend pas encore certifier les connexions externes ni l'exécution en direct. Aucune modification de stratégie de trading n'a été faite dans cette branche.
