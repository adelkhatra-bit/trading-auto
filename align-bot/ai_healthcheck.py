#!/usr/bin/env python3
"""Strict live Gemini check: 3 real requests, secret-safe output and Actions summary."""
import json, os, sys, time, urllib.error, urllib.request

KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = "gemini-flash-latest"
URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

def report(status, detail, successes=0):
    line = f"AI_GEMINI_STATUS={status} model={MODEL} successes={successes}/3 detail={detail}"
    print(line, flush=True)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"status={status}\nsuccesses={successes}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Contrôle réel Gemini — ALIGN\n\n")
            f.write(f"- **Statut :** {status}\n- **Modèle :** {MODEL}\n- **Appels valides :** {successes}/3\n- **Détail :** {detail}\n")
    return status == "CONNECTED"

if not KEY:
    report("NOT_CONFIGURED", "secret GEMINI_API_KEY absent ou vide")
    sys.exit(1)

successes = 0
last_error = "aucune réponse valide"
for attempt in range(1, 4):
    payload = {"model": MODEL, "temperature": 0, "max_tokens": 16,
               "messages": [{"role": "user", "content": f"Test ALIGN numéro {attempt}. Réponds uniquement OK."}]}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json","Accept":"application/json",
                 "Authorization":"Bearer " + KEY,"User-Agent":"ALIGN-AI-healthcheck"})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        answer = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if isinstance(answer, str) and len(answer.strip()) >= 2:
            successes += 1
        else:
            last_error = "réponse vide ou format inattendu"
    except urllib.error.HTTPError as exc:
        last_error = "AUTH_REJECTED" if exc.code in (401,403) else "HTTP_" + str(exc.code)
    except Exception as exc:
        last_error = type(exc).__name__
    if attempt < 3:
        time.sleep(1)
if successes == 3:
    report("CONNECTED", "3 réponses API valides", successes)
    sys.exit(0)
report("ERROR", last_error, successes)
sys.exit(1)
