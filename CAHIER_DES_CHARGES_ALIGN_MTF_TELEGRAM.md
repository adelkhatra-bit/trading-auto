# Cahier des charges — ALIGN MTF BOT / Telegram / production

Date : 11 novembre 2026
Branche audit : audit/align-telegram-end-to-end-20261111-v2
Branche de référence : main après la PR #25
Périmètre : align-bot, workflows GitHub Actions, Telegram, mémoire persistante et chaîne IA.

## 1. Objectif

Rendre le bot ALIGN BTC + Gold vérifiable de bout en bout : données de marché réelles, calculs MTF, décision, messages Telegram, boutons, notifications de clôture, chronomètres, mémoire persistante, IA externe et repli interne, exécution de production et alertes techniques.

Aucun résultat de test ne doit être simulé. Aucun message de test ne doit être envoyé aux abonnés. Aucun changement de stratégie, de risque, d'entrée, de stop, d'objectif, de droits VIP, d'historique ou de mémoire ne peut être introduit comme simple nettoyage.

## 2. Règles de conservation

- Ne supprimer aucune fonction, commande, bouton, message métier, marché, règle MTF, règle de risque, historique, état utilisateur, droit VIP ou parcours existant.
- Toute correction doit être minimale, traçable et accompagnée d'un test de non-régression.
- Les branches anciennes ne sont pas fusionnées en bloc : comparer leur contenu à main, identifier les apports encore absents, puis les intégrer sans écraser les corrections plus récentes.
- Un test supprimé ou affaibli ne constitue jamais une correction.
- Les messages techniques d'erreur sont réservés aux administrateurs ; ils ne doivent pas polluer les conversations des abonnés.
- Le bot ne doit jamais prétendre qu'une IA externe est connectée si le fournisseur n'a pas réellement répondu.
- Si les IA externes sont indisponibles, le suivi du marché continue ; les commentaires spécifiques IA sont omis ou remplacés par le commentaire interne déterministe prévu.
- Aucun ordre broker n'est envoyé par les fonctions de suivi Telegram. Les messages doivent continuer à préciser que l'utilisateur place ses ordres sur sa propre plateforme.

## 3. Périmètre fonctionnel à raccorder

### 3.1 Données et moteur MTF

- BTC via Kraken et Gold via XAUUSD spot avec les sources de bougies existantes et leurs secours.
- Contrôle de fraîcheur, intégrité, ordre chronologique, doublons, trous de bougies et cohérence OHLC.
- Les bougies utilisées pour une décision ou une notification de clôture doivent être entièrement terminées.
- Conserver la hiérarchie stratégique : 4h tendance principale, 1h confirmation, 15m contexte, 5m déclencheur après clôture ; 1m pour le prix et le suivi.
- Conserver les contrôles Daily/Weekly, RSI, ATR, zones, FVG, news, sessions, clôture du Gold, SL, TP et risque existants.
- Une donnée absente ou périmée doit produire un état explicite indisponible / attendre, jamais un signal fabriqué.

### 3.2 Telegram — messages

Chaque message envoyé ou modifié doit passer par le formateur commun telegram() / mise_en_forme() :
- titre et marché immédiatement identifiables ;
- statut de décision visible ;
- prix et niveaux séparés de leurs explications ;
- prix sans séparateur de milliers ;
- paragraphes lisibles sur mobile ;
- cohérence de présentation pour BTC et Gold ;
- aucune information de prix, SL, TP, news ou risque supprimée ;
- respect des limites Telegram de longueur et des erreurs API.

Inventaire à couvrir par tests : analyse synthétique, analyse détaillée, niveaux, position ouverte, entrée, sortie, TP1, TP2, stop, break-even, préparation, attente, retrace/repli, news avant/après, fermeture Gold, ouverture des sessions, DXY, accumulation/distribution, résultats, partage, abonnement, indicateur, messages visiteurs et messages administrateur.

### 3.3 Boutons et parcours

Tester chaque action et son retour :
- Analyse BTC / Analyse Gold ;
- comprendre l'analyse ;
- voir les niveaux ;
- revenir à l'analyse ;
- revoir l'analyse précédente du bon marché ;
- suivre la prochaine position ;
- je suis rentré / je suis sorti ;
- Mon bot ON/OFF ;
- Mes résultats ;
- Partager mon gain ;
- Indicateur TradingView ;
- anglais / français ;
- abonnement VIP, accès, retrait d'accès, cadeau, validation de gain et demandes d'entrée dans les canaux.

Les callbacks doivent répondre à Telegram, contrôler les droits avant toute action privée/VIP et ne jamais appliquer une action à un autre marché ou utilisateur. Un callback inconnu ou avec un marché invalide ne doit jamais être interprété comme une sortie manuelle.

### 3.4 Clôtures et chronomètres

- Le chronomètre doit toujours afficher la prochaine clôture future, jamais l'heure d'une bougie déjà clôturée.
- L'horodatage des bougies est traité comme une heure d'ouverture ; l'heure de clôture est calculée avec la durée de l'unité.
- Les notifications de clôture doivent être fondées sur une bougie complète, envoyées une seule fois par utilisateur et par clôture, avec le verdict ALIGN et l'étape suivante.
- Les données manquantes, dupliquées ou désalignées ne doivent pas déclencher de fausse clôture.
- Les mises à jour du chronomètre doivent être cadencées pour éviter les limites Telegram et les rafales multi-utilisateurs.
- Le suivi d'un utilisateur expire selon la durée déjà définie ; aucune entrée forcée ne doit être annoncée.

### 3.5 IA et repli

- Le contrôle de disponibilité doit utiliser la même liste de fournisseurs, les mêmes modèles, le même format de requête et le même parseur que le bot de production.
- La disponibilité IA externe est informative et ne doit pas empêcher le moteur de marché de tourner.
- Le helper ia() ne doit jamais inventer une réponse : lorsqu'aucun fournisseur ne répond, il renvoie une chaîne vide.
- avis_ia() affiche alors un commentaire déterministe fondé sur la stratégie interne. Les autres commentaires IA spécifiques sont omis si aucun fournisseur n'a répondu.
- Le fournisseur réellement utilisé, la connexion externe, la réponse invalide, l'indisponibilité et le repli interne doivent être distingués.
- Le repli interne ne doit jamais être présenté comme une réponse d'IA externe.

### 3.6 Mémoire et production

- Vérifier la restauration de state.json, les abonnés, propriétaires, droits, préférences, offsets Telegram, réservations, chronomètres, historiques et états de position.
- Écrire l'état de manière à limiter le risque de fichier partiellement écrit.
- Vérifier le démarrage, le contrôle Telegram, le contrôle IA, l'analyse BTC, l'analyse Gold, le traitement des boutons, la sauvegarde et la reprise.
- Une seule instance active du worker doit traiter les mises à jour Telegram pour éviter les conflits d'offset.
- Les exécutions en attente, annulées, échouées et réussies doivent être distinguées.
- Les alertes techniques vont aux propriétaires identifiés ; aucun message de démarrage promotionnel ou happy ne doit être envoyé aux utilisateurs.
- La cadence GitHub Actions n'est pas assimilée à une disponibilité 24/7 sans preuve de continuité et de redémarrage.

## 4. Critères d'acceptation

| ID | Contrôle | Preuve exigée |
|---|---|---|
| DATA-01 | BTC réel disponible | réponse source + horodatage récent |
| DATA-02 | Gold spot et bougies cohérents | source spot + bougies complètes |
| DATA-03 | aucun OHLC invalide | tests de trous, doublons, ordre et valeurs |
| MTF-01 | 4h/1h/15m/5m conformes | tests de régression |
| MTF-02 | aucune décision sur bougie ouverte | tests de clôture |
| MSG-01 | formateur commun appliqué | test du payload Telegram simulé |
| MSG-02 | niveaux complets et lisibles | tests BTC et Gold |
| BTN-01 | callbacks connus routés | tests de callbacks et droits |
| BTN-02 | callbacks inconnus sans effet métier | tests de sécurité des actions |
| CLOSE-01 | prochaine clôture strictement future | tests aux frontières temporelles |
| CLOSE-02 | notification de clôture unique | test de déduplication |
| CLOSE-03 | aucune notification sur bougie incomplète | test de données partielles |
| AI-01 | healthcheck identique au moteur réel | appel via le helper de production |
| AI-02 | commentaire interne explicite si IA externe indisponible | test avec fournisseurs simulés indisponibles |
| STATE-01 | mémoire restaurée et sauvegardée | test aller-retour JSON |
| PROD-01 | worker actif sur le SHA de main | run GitHub réussi et SHA vérifié |
| PROD-02 | pas de doublon d'instance | preuve de concurrence / offsets |
| PROD-03 | alertes administrateur réelles | test contrôlé sur destinataire propriétaire |
| E2E-01 | parcours Telegram complet | test contrôlé sans diffusion aux abonnés |

## 5. Stratégie de test

1. Compilation Python de tous les fichiers align-bot.
2. Tests unitaires MTF, données, formateur, niveaux, boutons, droits, callbacks, mémoire, clôtures, chronomètres et repli IA.
3. Tests de non-régression de tous les tests présents sur main au début de chaque lot ; aucun test existant ne doit disparaître.
4. Tests d'intégration du backend Node déjà présents.
5. Contrôle réel Telegram getMe sans envoyer de message aux abonnés.
6. Contrôle réel d'au moins un fournisseur IA ; si indisponible, le worker doit continuer et l'état indisponible doit rester visible.
7. Exécution contrôlée des parcours Telegram sur un compte administrateur/test, jamais sur toute la base d'abonnés.
8. Contrôle de production : SHA, état du worker, logs, mémoire restaurée, réponse Telegram et absence d'erreurs non traitées.

## 6. Constats établis pendant l'audit

- Le workflow MTF a déjà échoué sur une erreur de syntaxe dans test_align_mtf.py ; le garde-fou de compilation a depuis été ajouté sur main.
- La PR #25 a corrigé le calcul de la prochaine clôture future et le timestamp du prix spot Gold. Ce correctif est conservé.
- La branche de référence main comptait 27 tests MTF au démarrage de cette branche d'audit.
- La branche historique feat/telegram-visual-cards-actions-20261111 avait une validation verte tardive, mais son jeu de tests ne contenait que 22 tests et avait supprimé quatre tests présents sur main à cette date. Ses anciens échecs concernaient notamment les attentes de formatage. Elle n'est donc pas une base de fusion fiable.
- La PR #12 reste empilée sur l'ancienne branche de la PR #11. Son choix de marché par défaut (Gold seul) et sa cadence de 5 secondes doivent être évalués séparément ; ne pas fusionner cette branche en bloc.
- Le worker #490 était encore en cours sur un ancien SHA ; le run #496 était en attente lors du début de cette branche d'audit. La nouvelle version ne peut être déclarée opérationnelle avant son exécution réelle.

## 7. État de livraison

La branche d'audit part du main après la PR #25. Elle conserve les 27 tests de départ et en ajoute 7 ciblés : cadence du chronomètre, formatage commun, callback inconnu, marché invalide, entrée/sortie explicites, réservation valide et repli IA interne. Total : 34 tests.

Preuves obtenues sur la branche d'audit :
- compilation de tous les fichiers Python : réussie ;
- compilation du bot et du healthcheck : réussie ;
- 34 tests MTF : réussis ;
- tests d'intégration backend : réussis.

Ces preuves concernent la branche d'audit, pas encore le worker de production. Les changements ne deviennent production qu'après :
- revue des différences ;
- fusion explicite vers main ;
- validation post-fusion ;
- exécution du worker sur le SHA de fusion ;
- contrôle réel Telegram et mémoire.

Aucun statut 100 % opérationnel ne doit être déclaré tant que chaque critère d'acceptation n'a pas sa preuve.
