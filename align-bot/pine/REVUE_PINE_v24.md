# Revue de l'indicateur Pine ALIGN MTF PRO (Inside) v24 — lecture seule

**Rien n'a été modifié dans le Pine** (`ALIGN_MTF_PRO_v24.pine`, copie fidèle). Chaque correction ci-dessous est une
**proposition** à valider par Adel. Les lignes citées sont celles du fichier `ALIGN_MTF_PRO_v24.pine`.

Hors sujet (voulu, pas un bug) : les niveaux entrée / TP / SL figés jusqu'à la clôture 15 min (lignes 270-290).

Légende gravité : 🔴 haute (peut coûter de l'argent) • 🟠 moyenne • 🟡 basse.
« Visuel » = la correction change-t-elle ce qui est dessiné ? (Non = design intact.)

## A. Repaint et valeurs sur bougie non clôturée

| # | Gravité | Lignes | Constat | Correction proposée | Visuel |
|---|---|---|---|---|---|
| A1 | 🟠 | 36-47, 107-110, 115, 318, 478-480 | `request.security` sans paramètre explicite : en Pine v6 le défaut est `lookahead_off` (**pas de fuite vers le futur sur l'historique**, c'est bon). Mais en temps réel, les UT supérieures (1h, 4h, D, W) renvoient la bougie **en formation** : sens, compression et RSI d'une UT peuvent changer pendant la bougie, puis être différents après un rechargement de la page (l'historique recalculé utilise des bougies finales). | Ajouter une option « valeurs clôturées » (défaut **désactivée**) qui lit `f_etat()[1]` avec `lookahead=barmerge.lookahead_on` ; à activer seulement si Adel veut zéro repaint. | Non |
| A2 | 🔴 | 358-363 | Les flèches ▲/▼ sont créées à **chaque tick** de la bougie en cours (pas de `barstate.isconfirmed`). Elles **apparaissent puis disparaissent** pendant la bougie quand `rsiAchat`, `zoneHaut`, etc. basculent. | `sigHaut = sigHaut0 and barstate.isconfirmed and bar_index - dernierH > 12` (idem `sigBas`). La flèche n'apparaît qu'à la clôture et ne bouge plus. | Non (la flèche arrive à la clôture au lieu de clignoter) |
| A3 | 🔴 | 458-467 | `alertcondition(sigHaut…)` : si l'alerte TradingView est réglée « une fois par bougie » (et pas « à la clôture »), elle part sur un signal qui disparaît ensuite. Les `alert()` (lignes 458-464) sont bien en `once_per_bar_close`. | Même correction que A2 (`sigHaut` figé à la clôture) ; ou imposer « à la clôture » dans l'alerte. | Non |
| A4 | 🟠 | 82-91, 331-337 | `rsiAchat`, `rsiVente`, `liberation`, `mom` utilisent l'unité du **graphique** : valeurs différentes selon la vue (1 / 5 / 15 min) et mouvantes en cours de bougie. | Calculer ces 4 valeurs via `request.security("15", …)` (vue de référence du bot) pour que le signal ne dépende plus de la vue. | Non |
| A5 | 🟡 | 104-110 | Pivots (5,5) : confirmés 5 bougies plus tard — **retard, pas repaint** (un pivot confirmé ne disparaît pas). Les niveaux affichés ont donc 5 bougies de délai sur chaque UT. | Aucune (comportement normal). | — |
| A6 | 🟠 | 282-289 | Les niveaux figés sont des `var` recalculés à la reconstruction de l'historique : après un **rechargement de la page**, les niveaux affichés peuvent différer légèrement de ceux vus avant (l'historique rejoue avec des bougies UT finales). | Aucune simple ; l'option A1 réduit l'écart. À savoir : le bot Telegram garde ses niveaux en mémoire et ne rejoue pas l'historique. | — |

## B. Plan, TP, SL, retournement

| # | Gravité | Lignes | Constat | Correction proposée | Visuel |
|---|---|---|---|---|---|
| B1 | 🔴 | 270-278, 282 | `ent/tp/sl`, `retDir` et `slFranchi` dépendent de la **vue du graphique** : en vue 1 min, un seul `close` d'1 min au-delà du SL déclenche « RETOURNEMENT » ; en vue 15 min il faut une clôture 15 min. Idem `atrC` (113), donc entrée, SL et TP changent selon la vue. | Documenter « vue de référence = 15 min » et/ou calculer `atrC`, `close`, `low10/high10` et `slFranchi` depuis l'UT 15 min via `request.security`. | Non |
| B2 | 🟠 | 220-228 | Quand `dirStable == 0` (neutre), le sens passe à `dirBrut` **sans confirmation 15 min / 1h** : on peut sortir du neutre sur un simple signal d'une bougie. | Exiger la même confirmation (`d15 == dirBrut or d60 == dirBrut`) pour sortir du neutre, sauf au tout premier calcul. | Non |
| B3 | 🟠 | 537-552 | `tp1Ok` ne se remet à zéro que si le **sens** change. Après un TP1 touché, l'étiquette « ✅ TP1 touché • SL à BE » (option `voirTP2`) reste pour la position suivante dans le même sens. De plus `high >= tp1M` se déclenche même si le prix n'est jamais passé par la zone d'entrée (TP touché sans position). | Remettre `tp1Ok := false` quand `strat` change ou quand l'entrée est recalculée ; exiger un passage préalable dans la zone d'entrée. | Non |
| B4 | 🟡 | 336-345 | L'anti-spam `bar_index - dernierH > 12` compte des **bougies du graphique** : 12 bougies de 1 min ≠ 12 bougies de 15 min. Densité de flèches variable selon la vue. | Convertir en durée (`time - dernierT > 12 * 15 * 60000`). | Non |
| B5 | 🟠 | 275-278 | Un **gap** (réouverture du dimanche soir, après les news) franchit le SL sans qu'il y ait eu de vraie clôture « utile » : faux « SL cassé / RETOURNEMENT ». | Ignorer `slFranchi` sur la 1re bougie qui suit un trou de plus de N minutes. | Non |

## C. Divisions par zéro et valeurs absentes

| # | Gravité | Lignes | Constat | Correction proposée | Visuel |
|---|---|---|---|---|---|
| C1 | ✅ OK | 94-95 | `ts / sw` : `sw` = somme des poids = constante 26, jamais nulle. | — | — |
| C2 | ✅ OK | 311, 315 | Divisions par `math.max(…, syminfo.mintick)` : protégées. | — | — |
| C3 | ✅ OK | 304-306 | Volume : division seulement si `volOk` (volume > 0 et moyenne > 0). | — | — |
| C4 | 🟡 | 308-311 | Avant la 1re bougie confirmée, `ent`, `tp1`, `sl` valent `na` : `distE`, `rrS` sont `na` ; les comparaisons donnent « faux » donc 0 point — pas d'erreur, mais score faussé sur les toutes premières bougies. | Initialiser `ent/tp1/sl` avec `entC/tp1C/slC` au premier calcul. | Non |
| C5 | 🟡 | 47, 235 | Si l'actif a moins de 50 bougies hebdo, `dW` = `na` → 0 (traité correctement par `nz`). | — | — |

## D. Marché fermé et week-end

| # | Gravité | Lignes | Constat | Correction proposée | Visuel |
|---|---|---|---|---|---|
| D1 | 🟠 | 17-19, 36-47 | Marché plat (Gold / NAS100 le week-end ou en pause) : écart-type et ATR tendent vers 0 → la compression (Bollinger dans Keltner) est vraie sur beaucoup d'UT → « ⚡ SURCHARGE » **fausse**, qui alimente `fortHaut/fortBas` (331-332). | Ne compter la compression que si `volume > 0` ou si l'ATR dépasse un plancher (ex. 0,02 % du prix). | Non |
| D2 | 🟠 | 293-295 | Les compte-à-rebours (`timenow`) continuent à tourner pendant la fermeture (« clôture 1h dans 12:34 ») alors qu'aucune bougie ne viendra. | Afficher « marché fermé » si `na(time_close)` ou si la dernière bougie a plus de 2 périodes. | Texte uniquement |
| D3 | 🟡 | 36-47 | Pas de bougies pendant la fermeture : l'indicateur ne se met plus à jour et affiche le dernier plan **comme s'il était encore valable** à la réouverture. | Griser / marquer « plan périmé » après un trou de plus de N bougies. | Léger |

## E. Limites TradingView

| # | Gravité | Lignes | Constat | Correction proposée | Visuel |
|---|---|---|---|---|---|
| E1 | ✅ OK | 2 | `max_lines_count=30` : jusqu'à 14 lignes simultanées (plan, Fibonacci, 50 % MTF, TP2, traits blancs) → marge de 16. `max_boxes_count=10` : 2 boîtes utilisées. | — | — |
| E2 | 🟡 | 2, 358-363 | `max_labels_count=200` : sur un long historique les flèches s'accumulent ; au-delà, **TradingView supprime les plus anciennes** silencieusement. Environ 14 étiquettes sont réservées à la dernière bougie. | Aucune (comportement acceptable) ; ne pas augmenter au-delà de 500. | — |
| E3 | ✅ OK | 36-115, 318, 478-480 | 21 appels `request.security` sur 40 autorisés : marge de 19. | — | — |

## F. Différences Gold / BTC / NAS100

| # | Gravité | Lignes | Constat | Correction proposée | Visuel |
|---|---|---|---|---|---|
| F1 | 🟠 | 304-306, 308-311 | **Volume** : BTC (Kraken) a un vrai volume ; Gold et NAS100 CFD (FOREXCOM / FX) n'ont souvent **aucun volume** → `ptsVol = 0`. Le score maximum tombe à **85** au lieu de 100 : les seuils 75 et 85 ne sont pas comparables entre BTC et Gold/NAS100. | Si le volume est indisponible, ramener le score sur 85 (`scoreV * 100 / 85`). | Non (chiffre du score) |
| F2 | 🟠 | 46-47 | Bougie **Daily** : BTC coupe à 00:00 UTC, Gold/NAS100 à 17:00 New York → sens D, pivots Daily et niveaux « Daily » différents selon l'actif et le fournisseur. | Aucune ; à connaître. Le bot utilise Kraken/Yahoo, d'où de petits écarts de niveaux Daily vs graphique. | — |
| F3 | 🟡 | 36-47 (UT 3, 10, 45, 120) | Ces UT existent sur TradingView mais le bot les **reconstruit** en regroupant 1/5/15/60 min : léger décalage possible d'alignement de session sur Gold/NAS100. | Aucune côté Pine. | — |
| F4 | 🟡 | 282-289 | Le risque minimum `close * 0,12 %` pèse différemment : souvent atteint sur Gold (ATR 15 min ≈ 0,1 %), rarement sur BTC. | Rendre le pourcentage réglable par actif (entrée utilisateur). | Non |
| F5 | 🟡 | 17-19 | NAS100 : forte hausse de volatilité à l'ouverture US (15:30 Paris) → l'ATR 15 min grimpe et élargit SL/entrée d'un coup à la clôture suivante. | Aucune (comportement normal). | — |

## Résumé : à valider en priorité

1. **A2 + A3** (flèches et alertes à la clôture seulement) — supprime les signaux qui apparaissent puis disparaissent.
2. **B1 + A4** (calculs ancrés sur l'UT 15 min quelle que soit la vue) — garantit que le graphique et Telegram donnent les mêmes niveaux, quelle que soit la vue d'Adel.
3. **D1** (compression fausse sur marché plat) et **B5** (gap pris pour un SL franchi).
4. **F1** (score comparable entre BTC, Gold et NAS100).

Le design (couleurs, tableau, étiquettes, traits) n'est touché par aucune de ces propositions.
