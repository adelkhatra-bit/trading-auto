# ALIGN — Référence stratégique multi-unités (2026-11-11)

## Décision fonctionnelle

ALIGN doit séparer systématiquement :
1. le **biais de fond** (H4, H1, Daily/Weekly),
2. l'**opportunité exploitable** (M15/M5),
3. le **déclencheur d'exécution** (clôture confirmée, rejet/retest, niveau d'invalidation).

Une opposition entre unités de temps ne doit pas effacer une opportunité courte. Elle change son profil, son risque, son horizon et ses objectifs. Aucun signal ne devient une entrée automatique sur la seule base d'un alignement.

## Profils

| Profil | Conditions indicatives | Décision |
|---|---|---|
| SWING LONG/SHORT | H4 + H1 + M15 dans le même sens | Préparer un repli, timing M5, maintien seulement tant que H4 reste valide |
| INTRADAY LONG/SHORT | H1 + M15 alignés, H4 neutre ou en transition | Opportunité de séance, revalidation aux clôtures |
| RETRACEMENT LONG/SHORT | H4 + H1 dans un sens, M15 qui corrige dans l'autre | Ne pas confondre correction et retournement ; surveiller le retour M5 dans le sens du biais |
| SCALPING CONTRE-TENDANCE | M15 + M5 alignés contre H1/H4 | Opportunité courte à risque élevé ; déclencheur M5 clôturé obligatoire ; objectif court ; jamais requalifier en swing |
| ATTENTE | Pas de confluence exploitable ou données insuffisantes | Aucun ordre proposé ; indiquer exactement ce qui manque |

Les mêmes règles s'appliquent symétriquement aux LONG et SHORT.

## Risque et garde-fous

- Afficher le conflit d'unités explicitement : « CONTRE H4 », « CONTRE H1/H4 », etc.
- Le niveau de risque est calculé à partir des unités opposées, de la volatilité/ATR, du RSI et de son essoufflement, des divergences, de la structure, de la proximité des extrêmes Daily/Weekly et des annonces économiques.
- Un setup contre-tendance ne peut pas être présenté comme « confirmé » par le biais principal.
- Une mèche seule ne valide jamais une entrée : attendre la clôture de l'unité de déclenchement et le rejet/retest exigé par la stratégie.
- Si les données de l'indicateur ou les bougies sont absentes/stales, ne pas inventer de prix, de SL, de TP ou de confirmation.
- Conserver les protections existantes, les limites de risque, les règles de session et le suivi des positions ouvertes.
- Aucune exécution broker automatique : ALIGN informe et accompagne, sauf activation séparée et explicite d'une fonction d'exécution.

## Telegram — format commun FR/EN

Chaque notification doit avoir une catégorie et un statut explicites :
- SWING SETUP
- INTRADAY SETUP
- RETRACEMENT
- COUNTER-TREND SCALP / SCALPING CONTRE-TENDANCE
- ENTRY WAITING / ENTRÉE EN ATTENTE
- ENTRY CONFIRMED / ENTRÉE CONFIRMÉE
- INVALIDATED / INVALIDÉ
- POSITION OPEN / POSITION EN COURS
- POSITION CLOSED / POSITION CLÔTURÉE

Carte courte obligatoire :
1. marché et profil ;
2. risque et unités opposées ;
3. état H4/H1/M15/M5 ;
4. entrée, SL, TP1, TP2 uniquement si calculés et valides ;
5. déclencheur restant et action attendue.

Ne jamais écrire « clôture confirmée » si le signal n'est pas confirmé à cette clôture. Distinguer clôture observée, signal confirmé et entrée autorisée.

## TradingView — présentation cible

- Conserver le style et les éléments existants de l'indicateur : lignes d'entrée, stop, TP, zones et repères.
- Ajouter une lecture multi-profils cohérente avec les catégories ci-dessus.
- Afficher le profil, le sens, le risque, les unités alignées/opposées et l'état du déclencheur.
- Les tracés d'entrée/SL/TP doivent provenir des niveaux calculés par le moteur de l'indicateur, pas d'une estimation parallèle du bot.
- FR/EN strictement identiques en structure.
- Ne pas modifier le Pine Script sans récupérer et tester son fichier source original.

## Validation obligatoire avant production

- Tests unitaires LONG et SHORT pour chaque profil.
- Cas H4/H1 baissiers avec M15/M5 haussiers (et inverse).
- Cas de retracement, retournement confirmé, divergence, essoufflement, news, extrêmes Daily/Weekly et données absentes.
- Vérifier les prix, le sens des niveaux, SL/TP, ratio gain/risque et l'invalidation.
- Vérifier que les messages Telegram FR/EN reflètent exactement le verdict du moteur.
- Tester le flux réel TradingView → extension → backend → bot Telegram.
- Aucun déploiement ou déclaration « opérationnel à 100 % » avant les tests réels et la vérification du bot en production.
