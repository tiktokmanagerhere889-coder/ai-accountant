"""Verify the fail-fast provider fix: key works, no SDK retry on 429."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent_defs.model_providers import (
    create_groq_provider,
    GROQ_MODEL,
    GROQ_FALLBACK_MODEL,
)


async def main():
    provider = create_groq_provider()
    client = provider._client

    print(f"max_retries on client: {client.max_retries} (want 0)")

    # 1. Raw completion against primary model — proves the new key works
    resp = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
    )
    print(f"[primary {GROQ_MODEL}] -> {resp.choices[0].message.content!r}")

    # 2. Raw completion against fallback model
    resp2 = await client.chat.completions.create(
        model=GROQ_FALLBACK_MODEL,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
    )
    print(f"[fallback {GROQ_FALLBACK_MODEL}] -> {resp2.choices[0].message.content!r}")

    await client.close()


asyncio.run(main())
