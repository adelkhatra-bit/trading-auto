#!/usr/bin/env python3
"""ATTENTION : le dépôt est PUBLIC, les journaux Actions sont lisibles par tous. Les textes de messages (VIP) ne s'affichent qu'avec AUDIT_TEXTE_OK=oui.
Audit des messages RÉELLEMENT envoyés par le bot (journal_telegram de state.json). Lecture seule, rien n'est envoyé.
Affiche : volume par conversation, titres les plus répétés (même titre à quelques minutes d'écart) et ce que l'anti-répétition aurait supprimé.
Seuls les messages sortants du bot sont lus (titre tronqué) : jamais les messages des utilisateurs."""
import collections
import os
import datetime
import json
import re
import sys

import align_bot as ab

etat = json.load(open("state.json", encoding="utf-8"))
sortants = [x for x in etat.get("journal_telegram", []) if x.get("direction") == "sortant" and x.get("text") and x.get("type", "sendMessage") != "editMessageText"]
print(f"AUDIT journal={len(etat.get('journal_telegram', []))} sortants={len(sortants)}")
if not sortants:
    sys.exit(0)
ts = [float(x["timestamp"]) for x in sortants if x.get("timestamp")]
print(f"AUDIT période {(max(ts) - min(ts)) / 3600:.1f} h")
chats = {}
for x in sortants:
    chats.setdefault(str(x.get("chat_id")), []).append(x)
for i, (cid, lst) in enumerate(sorted(chats.items(), key=lambda z: -len(z[1]))[:6], 1):
    print(f"AUDIT chat#{i} messages={len(lst)}")

def titre(t):
    ligne = next((l for l in t.splitlines() if l.strip()), "")
    return re.sub(r"\s+", " ", ab._NOMBRE_RE.sub("#", ligne)).strip()[:90]

# Le plus grand chat sert d'échantillon : c'est celui qui reçoit tout.
cid, lst = max(chats.items(), key=lambda z: len(z[1]))
lst = sorted(lst, key=lambda x: float(x.get("timestamp", 0)))
principal = list(lst)                                   # plus gros chat (la boucle de routage réutilise « lst »)
exact, memes, parttl = 0, 0, collections.Counter()
etat_sim, supprimes = {}, collections.Counter()
derniere = {}
for x in lst:
    t, texte = float(x.get("timestamp", 0)), x["text"]
    parttl[titre(texte)] += 1
    ex = ab.doublon_message(etat_sim, texte, t)
    if ex:
        supprimes[titre(texte)] += 1
    k = titre(texte)
    if k in derniere and t - derniere[k] <= 3600:
        memes += 1                                      # même titre moins d'1 h après le précédent
    derniere[k] = t
print(f"AUDIT plus gros chat : {len(lst)} messages • même titre <1 h après : {memes} • supprimés par le filet : {sum(supprimes.values())}")
for k, n in parttl.most_common(18):
    print(f"TITRE {n:3d} x (supprimés {supprimes.get(k, 0):3d}) {k}")

# ── Routage par compte : chaque conversation reçoit-elle seulement les marchés qu'elle a cochés ? ──
print("ROUTAGE (marchés cochés par conversation vs marchés des messages reçus)")
choix = etat.get("marches_par_chat", {})
canal = str(etat.get("canal") or "")
for i, (cid, lst) in enumerate(sorted(chats.items(), key=lambda z: -len(z[1]))[:6], 1):
    brut = choix.get(cid)
    coches = sorted(ab._vers_ensemble(brut)) if brut is not None else None
    cpt, hors, sans, tit_hors = collections.Counter(), 0, 0, collections.Counter()
    tit_sans, ages = collections.Counter(), []
    fin_t = max(float(y.get("timestamp", 0)) for y in lst)
    for x in lst:
        ens = ab.marches_du_message(x["text"])
        if not ens:
            sans += 1
            tit_sans[titre(x["text"])] += 1
            continue
        for m in ens:
            cpt[m] += 1
        if coches is not None and not (ens & set(coches)):
            hors += 1
            tit_hors[titre(x["text"])] += 1
            ages.append(round((fin_t - float(x.get("timestamp", 0))) / 3600, 1))
    nom = "CANAL VIP" if cid == canal else f"chat#{i}"
    print(f"ROUTAGE {nom} coches={coches if coches is not None else 'jamais choisi (tout)'} messages={len(lst)} par_marche={dict(cpt)} sans_marche={sans} HORS_CHOIX={hors}")
    for k, n in tit_hors.most_common(5):
        print(f"ROUTAGE   hors choix {n:3d} x {k}")
    if ages:
        print(f"ROUTAGE   âge des messages hors choix (h avant le dernier message) : {sorted(ages)}")
    for k, n in tit_sans.most_common(8):
        print(f"ROUTAGE   sans marché {n:3d} x {k}")

# ── Exemples réels (un par type de titre, messages du bot uniquement) pour relire la forme ──
if "--exemples" in sys.argv and os.environ.get("AUDIT_TEXTE_OK") == "oui":
    vus_t, n = set(), 0
    for x in reversed(principal):
        k = titre(x["text"])
        if k in vus_t or n >= 26:
            continue
        vus_t.add(k); n += 1
        corps = [l for l in re.sub(r"</?[bi]>|</?code>", "", x["text"]).splitlines()]
        print(f"EXEMPLE ── {k}  (x{parttl.get(k, 1)}, {len(corps)} lignes)")
        for l in corps[:14]:
            print("EX|" + l[:130])

# ── Recherche ciblée : python3 audit_messages.py --cherche "baissier|mouvement" [--heures 6] ──
if "--cherche" in sys.argv and os.environ.get("AUDIT_TEXTE_OK") == "oui":
    motif = re.compile(sys.argv[sys.argv.index("--cherche") + 1], re.I)
    h = float(sys.argv[sys.argv.index("--heures") + 1]) if "--heures" in sys.argv else 6.0
    fin_t = max(float(x.get("timestamp", 0)) for x in sortants)
    trouves = [x for x in sortants if motif.search(re.sub(r"<[^>]+>", "", x["text"])) and fin_t - float(x.get("timestamp", 0)) <= h * 3600]
    print(f"CHERCHE {len(trouves)} message(s) sortants correspondant sur les {h:g} dernières heures (dernier message du journal = {datetime.datetime.fromtimestamp(fin_t, ab.PARIS).strftime('%d/%m %H:%M')} Paris)")
    vus_c = set()
    for x in sorted(trouves, key=lambda y: float(y.get("timestamp", 0)))[-14:]:
        corps = re.sub(r"</?[bi]>|</?code>", "", x["text"]).splitlines()
        cle_c = (str(x.get("chat_id")), tuple(corps[:3]))
        if cle_c in vus_c:
            continue
        vus_c.add(cle_c)
        quand = datetime.datetime.fromtimestamp(float(x.get("timestamp", 0)), ab.PARIS).strftime("%d/%m %H:%M")
        print(f"TROUVE {quand} chat#{[k for k in chats].index(str(x.get('chat_id'))) + 1}")
        for l in corps[:9]:
            print("TR|" + l[:140])
