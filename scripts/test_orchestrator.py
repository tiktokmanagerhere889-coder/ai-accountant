"""Measure Groq request count for a single chat message through the full orchestrator.

Instrumentation: monkeypatches the provider clients' chat.completions.create
to count calls per model, then runs run_orchestrator("Check Cash Position").
"""
import asyncio
import sys
import os
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import agent_defs.model_providers as mp


call_count = Counter()


def make_counting_client(create_original):
    def wrapper():
        provider = create_original()
        client = provider._client
        orig_create = client.chat.completions.create

        async def counting_create(**kwargs):
            model = kwargs.get("model", "?")
            call_count[model] += 1
            print(f"  [PROVIDER CALL] model={model}", flush=True)
            return await orig_create(**kwargs)

        client.chat.completions.create = counting_create
        return provider

    return wrapper


async def main():
    # Patch both provider factories with counting versions
    orig_groq = mp.create_groq_provider
    orig_gemini = mp.create_gemini_provider

    def count_groq():
        return make_counting_client(orig_groq)()
    def count_gemini():
        return make_counting_client(orig_gemini)()

    mp.create_groq_provider = count_groq
    mp.create_gemini_provider = count_gemini

    from agent_defs.orchestrator import run_orchestrator

    result = await run_orchestrator("Check Cash Position")
    print("\n=== RESULT ===")
    print(result[:400])
    print("\n=== GROQ CALLS FOR THIS ONE MESSAGE ===")
    for model, n in call_count.items():
        print(f"  {model}: {n}")
    print(f"  TOTAL: {sum(call_count.values())}")


asyncio.run(main())
