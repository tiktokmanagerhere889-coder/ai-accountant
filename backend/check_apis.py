"""Check Groq and Gemini API endpoints."""
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

# --- Gemini (OpenAI-compatible endpoint) ---
gkey = get_api_key("GEMINI_API_KEY")
print(f"\nGemini key: {gkey[:12]}...{gkey[-4:] if len(gkey) > 16 else ''}")

try:
    mresp = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest",
        headers={"x-goog-api-key": gkey},
        timeout=10,
    )
    print(f"Gemini models endpoint {mresp.status_code}")
    if mresp.status_code == 200:
        info = mresp.json()
        print(f"  displayName: {info.get('displayName')}")
    else:
        print(f"  {mresp.text[:200]}")
except Exception as e:
    print(f"  Model info error: {e}")

# Try chat completion via OpenAI-compat layer
resp = requests.post(
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    headers={"Authorization": f"Bearer {gkey}", "Content-Type": "application/json"},
    json={"model": "gemini-flash-lite-latest", "messages": [{"role": "user", "content": "hi"}]},
    timeout=15,
)
print(f"\nGemini chat {resp.status_code}")
if resp.status_code == 200:
    print(f"  OK: {resp.json()['choices'][0]['message']['content'][:80]}")
else:
    print(f"  {resp.text[:300]}")
