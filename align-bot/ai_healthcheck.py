#!/usr/bin/env python3
"""Contrôle IA externe avec EXACTEMENT la chaîne et le parseur utilisés par le bot ALIGN.

Ce contrôle est informatif : les commentaires spécifiques IA peuvent être omis
si les fournisseurs externes sont indisponibles ; le bot garde son analyse MTF interne.
"""
import os
import sys

import align_bot


def write_summary(status, provider, attempts):
    print(f"AI_EXTERNAL_STATUS={status} provider={provider or 'NONE'} attempts={attempts}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Contrôle réel IA externe — ALIGN\n\n")
            f.write(f"- **Statut :** {status}\n")
            f.write(f"- **Fournisseur utilisable :** {provider or 'aucun'}\n")
            f.write(f"- **Fournisseurs testés :** {attempts or 'aucun'}\n")
            f.write("- **Commentaire interne :** disponible dans align_bot.avis_ia()\n")


messages = [
    {"role": "system", "content": align_bot.IA_REGLES},
    {"role": "user", "content": (
        "Contrôle technique de connexion ALIGN. Réponds en français par une phrase "
        "courte confirmant que tu as reçu ce test. N'invente aucun prix ni signal."
    )},
]
attempts = []
for name, url, model, key, needs_key in align_bot.IA_FOURNISSEURS:
    if needs_key and not key:
        attempts.append(name + "=NOT_CONFIGURED")
        continue
    try:
        # Même fonction HTTP, même modèle, même extraction et même seuil
        # minimal que le véritable commentaire produit par le bot.
        reply = align_bot._appel_ia(url, model, key, messages)
        attempts.append(name + "=CONNECTED")
        print("AI_EXTERNAL_REPLY=" + " ".join(reply.split())[:220], flush=True)
        write_summary("CONNECTED", name, ", ".join(attempts))
        sys.exit(0)
    except Exception as exc:
        attempts.append(name + "=" + align_bot.detail_erreur_ia(exc, key)[:40])
        print("AI_PROVIDER_CHECK_FAILED", name, "model=" + model, align_bot.detail_erreur_ia(exc, key), flush=True)

write_summary("UNAVAILABLE", "", ", ".join(attempts))
# Code non nul pour signaler l'indisponibilité ; le workflow est non bloquant.
# avis_ia() utilise alors le verdict et la stratégie MTF internes, sans simuler une IA.
sys.exit(1)
