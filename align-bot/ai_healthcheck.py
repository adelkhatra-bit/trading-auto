#!/usr/bin/env python3
"""Vérifie une vraie réponse IA via le premier fournisseur disponible de la chaîne ALIGN."""
import json
import os
import sys
import urllib.error
import urllib.request

PROVIDERS = [
    ("Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     "gemini-flash-latest", os.environ.get("GEMINI_API_KEY", "").strip()),
    ("OVH Llama", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions",
     "Meta-Llama-3_3-70B-Instruct", ""),
    ("OVH Mistral", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions",
     "Mistral-Small-3.2-24B-Instruct", ""),
    ("Pollinations", "https://text.pollinations.ai/openai", "openai", ""),
    ("LLM7", "https://api.llm7.io/v1/chat/completions", "default", ""),
]

def write_summary(status, provider, attempts):
    print(f"AI_EXTERNAL_STATUS={status} provider={provider or 'NONE'} attempts={attempts}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Contrôle réel IA — ALIGN\n\n")
            f.write(f"- **Statut :** {status}\n")
            f.write(f"- **Fournisseur utilisable :** {provider or 'aucun'}\n")
            f.write(f"- **Fournisseurs testés :** {attempts}\n")

attempts = []
for name, url, model, key in PROVIDERS:
    if name == "Gemini" and not key:
        attempts.append("Gemini=NOT_CONFIGURED")
        continue
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 24,
        "messages": [{"role": "user", "content": "Réponds uniquement OK au test de connexion ALIGN."}],
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ALIGN-AI-healthcheck",
    }
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        answer = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if isinstance(answer, str) and len(answer.strip()) >= 2:
            attempts.append(name + "=CONNECTED")
            write_summary("CONNECTED", name, ", ".join(attempts))
            sys.exit(0)
        attempts.append(name + "=EMPTY_RESPONSE")
    except urllib.error.HTTPError as exc:
        attempts.append(name + "=" + ("AUTH_REJECTED" if exc.code in (401, 403) else "HTTP_" + str(exc.code)))
    except Exception as exc:
        attempts.append(name + "=" + type(exc).__name__)

write_summary("UNAVAILABLE", "", ", ".join(attempts))
sys.exit(1)
