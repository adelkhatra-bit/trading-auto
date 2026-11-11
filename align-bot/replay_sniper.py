#!/usr/bin/env python3
"""Rejeu de l'entrée sniper M1/M3 sur les VRAIES bougies du bot (mêmes sources que la production). Lecture seule : aucun message envoyé.
Usage : python3 replay_sniper.py [--pair XAUUSD] [--marche GOLD] [--heures 8]
Affiche chaque proposition (heure, ordre limite, SL, TP1) et ce qu'il serait arrivé ensuite (TP1 / SL / non rempli), puis les bougies M1/M3 de la fenêtre
(lignes M1_FENETRE= / M3_FENETRE=) pour les enregistrer comme jeu de test."""
import argparse
import datetime
import json
from zoneinfo import ZoneInfo

import align_bot as ab

p = argparse.ArgumentParser()
p.add_argument("--pair", default="XAUUSD")
p.add_argument("--marche", default="GOLD")
p.add_argument("--heures", type=float, default=8)
a = p.parse_args()
S = dict(m1=ab.bougies(a.pair, 1), m5=ab.bougies(a.pair, 5), m15=ab.bougies(a.pair, 15), m30=ab.bougies(a.pair, 30), h1=ab.bougies(a.pair, 60),
         h4=ab.bougies(a.pair, 240), d1=ab.bougies(a.pair, 1440), w1=ab.bougies(a.pair, 10080))
fin = S["m1"][-1]["t"]
debut = fin - int(a.heures * 3600)
PARIS = ZoneInfo("Europe/Paris")
hp = lambda t: datetime.datetime.fromtimestamp(t, PARIS).strftime("%d/%m %H:%M")
print(f"REJEU_SNIPER {a.marche} source={a.pair} bougies M1={len(S['m1'])} fenêtre {hp(debut)} → {hp(fin)} (heure de Paris)")
mem, vus, n_prop = {}, set(), 0
T = (debut // 180 + 1) * 180
while T <= fin:
    St = {k: [x for x in v if x["t"] <= T] for k, v in S.items()}
    try:
        r = ab.analyser_avec_memoire(St, mem)
    except Exception as ex:
        T += 180
        continue
    sn = r.get("sniper")
    if sn:
        cle = (sn["d"], round(sn["niveau"] / max(sn["niveau"] * 0.0004, 1e-9)))
        if cle not in vus:
            vus.add(cle); n_prop += 1
            res = ab.simuler_sniper(sn, [x for x in S["m1"] if x["t"] > T])
            print(f"SNIPER {hp(T)} {'VENTE' if sn['d'] == -1 else 'ACHAT'} limite {ab.px(sn['za'])}–{ab.px(sn['zb'])} (entrée {ab.px(sn['e'])}, {sn['src']}) "
                  f"SL {ab.px(sn['sl'])} TP1 {ab.px(sn['tp1'])} ({sn['n1']}) R/R {sn['rr']:.1f} → {res['etat']}"
                  + (f" {res['pnl']:+.1f} pts, rempli {hp(res['t_fill'])}" if res.get("t_fill") else "")
                  + f" | UT alignées {r['bear'] if sn['d'] == -1 else r['bull']}/11, stratégie {r.get('strat') or '-'}")
    T += 180
print(f"REJEU_FIN propositions={n_prop}")
print("M1_FENETRE=" + json.dumps([[x["t"], x["o"], x["h"], x["l"], x["c"]] for x in S["m1"] if x["t"] >= debut], separators=(",", ":")))
print("M3_FENETRE=" + json.dumps([[x["t"], x["o"], x["h"], x["l"], x["c"]] for x in ab.regrouper(S["m1"], 3, 60) if x["t"] >= debut], separators=(",", ":")))
