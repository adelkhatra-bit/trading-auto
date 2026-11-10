#!/usr/bin/env python3
"""Non-invasive live health check for the Gemini provider. Never prints credentials."""
import json
import os
import sys
import urllib.error
import urllib.request

key = os.environ.get("GEMINI_API_KEY", "").strip()
if not key:
    print("AI_GEMINI_STATUS=NOT_CONFIGURED secret GEMINI_API_KEY absent ou non transmis au workflow")
    sys.exit(0)

url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
payload = {
    "model": "gemini-flash-latest",
    "temperature": 0,
    "max_tokens": 8,
    "messages": [{"role": "user", "content": "Réponds uniquement OK"}],
}
request = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Bearer " + key,
        "User-Agent": "ALIGN-AI-healthcheck",
    },
)
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    answer = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not isinstance(answer, str) or len(answer.strip()) < 2:
        print("AI_GEMINI_STATUS=ERROR réponse vide ou format inattendu")
        sys.exit(0)
    print("AI_GEMINI_STATUS=CONNECTED model=gemini-flash-latest response=VALID")
except urllib.error.HTTPError as exc:
    # Do not print the request, headers, or API key.
    detail = "AUTH_REJECTED" if exc.code in (401, 403) else "HTTP_" + str(exc.code)
    print("AI_GEMINI_STATUS=ERROR " + detail)
except Exception as exc:
    print("AI_GEMINI_STATUS=ERROR " + type(exc).__name__)
