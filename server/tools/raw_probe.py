"""Show exactly what one model returns for a trivial structured request.

Exists because "no JSON object in the answer" is a conclusion, not evidence —
this prints the raw message object so the shape of the refusal is visible.
Never prints the key.

    python server/tools/raw_probe.py [model-id]
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


def ask(payload: dict) -> None:
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
        print("  HTTP", e.code, e.read().decode()[:300])
        return
    if doc.get("error"):
        print("  error:", str(doc["error"])[:300])
        return
    msg = doc["choices"][0].get("message", {})
    print("  finish_reason:", doc["choices"][0].get("finish_reason"))
    print("  message keys :", list(msg.keys()))
    for k in ("content", "reasoning"):
        v = msg.get(k)
        if v:
            print(f"  {k} ({len(v)} chars): {v[:400]!r}")
        else:
            print(f"  {k}: {v!r}")
    print("  usage:", doc.get("usage"))


print(f"model: {MODEL}   key present: {bool(KEY)}\n")

print("A. json_object mode, tiny ask")
ask({
    "model": MODEL,
    "messages": [{"role": "user", "content": 'Return JSON: {"bias":"neutral","n":1}'}],
    "response_format": {"type": "json_object"},
    "max_tokens": 200,
})

print("\nB. no response_format at all, tiny ask")
ask({
    "model": MODEL,
    "messages": [{"role": "user", "content": 'Reply with only this JSON: {"bias":"neutral","n":1}'}],
    "max_tokens": 200,
})

print("\nC. json_object, higher max_tokens (reasoning models spend budget thinking)")
ask({
    "model": MODEL,
    "messages": [{"role": "user", "content": 'Return JSON: {"bias":"neutral","n":1}'}],
    "response_format": {"type": "json_object"},
    "max_tokens": 3000,
})
