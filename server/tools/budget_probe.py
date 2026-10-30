"""Find the max_tokens a free provider will actually accept.

The Nvidia free endpoint answered a 200-token request and returned HTTP 404 —
not 400 — for a 3000-token one, which is not a limit anyone would guess. This
walks the value so the number in report.py is measured rather than assumed.

    python server/tools/budget_probe.py [model-id]
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV = os.path.join(os.path.dirname(HERE), ".env.local")
if os.path.exists(ENV):
    with open(ENV, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"'))

KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = sys.argv[1] if len(sys.argv) > 1 else "nvidia/nemotron-3.5-super-vl:free"


def try_budget(n: int, reasoning: dict | None) -> str:
    payload: dict = {
        "model": MODEL,
        "messages": [{"role": "user", "content": 'Return JSON: {"bias":"neutral","n":1}'}],
        "response_format": {"type": "json_object"},
        "max_tokens": n,
    }
    if reasoning is not None:
        payload["reasoning"] = reasoning
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3100",
            "X-Title": "HERMES",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            doc = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    if doc.get("error"):
        return f"err {str(doc['error'])[:60]}"
    ch = doc["choices"][0]
    c = ch.get("message", {}).get("content") or ""
    u = doc.get("usage") or {}
    return (
        f"ok  finish={ch.get('finish_reason')}  content={len(c)}ch  "
        f"completion={u.get('completion_tokens')}  "
        f"reasoning={(u.get('completion_tokens_details') or {}).get('reasoning_tokens')}"
    )


print(f"model: {MODEL}\n")
print("--- plain, no reasoning param ---")
for n in (200, 800, 1500, 2000, 3000, 4000, 8000):
    print(f"  max_tokens={n:<6} {try_budget(n, None)}")

print("\n--- with reasoning effort low ---")
for n in (2000, 4000, 8000):
    print(f"  max_tokens={n:<6} {try_budget(n, {'effort': 'low'})}")
