"""Custom model providers for Cerebras (primary) and Groq (fallback).

Both providers implement OpenAI-compatible chat completions APIs.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents.models.openai_provider import OpenAIProvider
from db.database import SessionLocal
from db.models import UserApiKey as DBUserApiKey

# Load .env from project root
dotenv_path = Path(__file__).resolve().parents[2] / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path, override=True)

# Model configuration - Groq primary (verified against Groq's live model list 2026-07)
# primary: llama-3.3-70b-versatile (strong tool calling, free tier)
# fallback: llama-3.1-8b-instant (fast, reliable)
# Cerebras: gemma-4-31b (verified against Cerebras /v1/models - 2026-08)
#   previous llama-3.3-70b was 404: not in Cerebras model list.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
CEREBRAS_MODEL = os.environ.get("CEREBRAS_MODEL", "gemma-4-31b")

def get_api_key(key_name: str) -> str:
    """Check user_api_keys table first, fall back to env var.

    Safe to call before init_db() - silently falls back to env var if table doesn't exist yet.
    """
    try:
        db = SessionLocal()
        record = db.query(DBUserApiKey).filter(DBUserApiKey.key_name == key_name).first()
        db.close()
        if record and record.key_value:
            return record.key_value
    except Exception:
        pass
    return os.environ.get(key_name, "")


def create_cerebras_provider() -> OpenAIProvider:
    """Create an OpenAI-compatible provider for Cerebras inference.

    Base URL: https://api.cerebras.ai/v1
    Uses Chat Completions API (not Responses API).

    Fail-fast: the underlying AsyncOpenAI client uses max_retries=0 so a 429
    or 5xx surfaces immediately instead of triggering SDK backoff retries
    (4s/7s/10s) that pile up inside the frontend's 30s timeout. Provider
    fallback in the orchestrator handles the failure instead.
    """
    client = AsyncOpenAI(
        api_key=get_api_key("CEREBRAS_API_KEY"),
        base_url="https://api.cerebras.ai/v1",
        max_retries=0,
        timeout=30.0,
    )
    return OpenAIProvider(
        openai_client=client,
        use_responses=False,
    )


def create_groq_provider() -> OpenAIProvider:
    """Create an OpenAI-compatible provider for Groq inference.

    Base URL: https://api.groq.com/openai/v1
    Uses Chat Completions API (not Responses API).
    Same fail-fast client as Cerebras: max_retries=0, 30s timeout.
    """
    client = AsyncOpenAI(
        api_key=get_api_key("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        max_retries=0,
        timeout=30.0,
    )
    return OpenAIProvider(
        openai_client=client,
        use_responses=False,
    )
