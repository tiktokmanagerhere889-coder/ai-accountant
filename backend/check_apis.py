"""Check Groq and Cerebras API endpoints."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from agent_defs.model_providers import get_api_key
import requests, json

# --- Groq ---
gkey = get_api_key("GROQ_API_KEY")
print(f"Groq key: {gkey[:12]}...{gkey[-4:] if len(gkey) > 16 else ''}")
resp = requests.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={"Authorization": f"Bearer {gkey}", "Content-Type": "application/json"},
    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "hi"}]},
    timeout=15,
)
print(f"Groq {resp.status_code}")
if resp.status_code == 429:
    print(f"  RATE LIMITED: {resp.text[:200]}")
elif resp.status_code == 200:
    print(f"  OK: {resp.json()['choices'][0]['message']['content'][:80]}")
else:
    print(f"  {resp.text[:200]}")

# --- Cerebras ---
ckey = get_api_key("CEREBRAS_API_KEY")
print(f"\nCerebras key: {ckey[:12]}...{ckey[-4:] if len(ckey) > 16 else ''}")

# List models first
try:
    mresp = requests.get(
        "https://api.cerebras.ai/v1/models",
        headers={"Authorization": f"Bearer {ckey}"},
        timeout=10,
    )
    print(f"Cerebras models endpoint {mresp.status_code}")
    if mresp.status_code == 200:
        models = mresp.json()
        print(f"  Available: {[m['id'] for m in models.get('data', models)][:10]}")
    else:
        print(f"  {mresp.text[:200]}")
except Exception as e:
    print(f"  Model list error: {e}")

# Try chat completion
resp = requests.post(
    "https://api.cerebras.ai/v1/chat/completions",
    headers={"Authorization": f"Bearer {ckey}", "Content-Type": "application/json"},
    json={"model": "llama3.1-70b", "messages": [{"role": "user", "content": "hi"}]},
    timeout=15,
)
print(f"\nCerebras chat {resp.status_code}")
if resp.status_code == 200:
    print(f"  OK: {resp.json()['choices'][0]['message']['content'][:80]}")
else:
    print(f"  {resp.text[:300]}")

# Also test with fallback model names
for model in ["llama-3.1-70b", "llama3.1-8b", "llama-3.1-8b"]:
    resp = requests.post(
        "https://api.cerebras.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {ckey}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": "hi"}]},
        timeout=10,
    )
    print(f"  Cerebras model={model}: {resp.status_code}")
    if resp.status_code != 404:
        print(f"    => {resp.text[:100]}")
