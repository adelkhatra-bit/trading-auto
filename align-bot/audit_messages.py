#!/usr/bin/env python3
"""Audit des messages RÉELLEMENT envoyés par le bot (journal_telegram de state.json). Lecture seule, rien n'est envoyé.
Affiche : volume par conversation, titres les plus répétés (même titre à quelques minutes d'écart) et ce que l'anti-répétition aurait supprimé.
Seuls les messages sortants du bot sont lus (titre tronqué) : jamais les messages des utilisateurs."""
import collections
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
