"""Custom model providers for Groq (primary) and Gemini (fallback).

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
# Gemini fallback: gemini-flash-lite-latest (verified standalone 2026-08-05 against
#   https://generativelanguage.googleapis.com/v1beta/openai/chat/completions —
#   HTTP 200, tool-calling works). Replaces Cerebras, which kept hitting billing/402.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")

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


def create_gemini_provider() -> OpenAIProvider:
    """Create an OpenAI-compatible provider for Gemini inference.

    Base URL: https://generativelanguage.googleapis.com/v1beta/openai/
    Uses Chat Completions API (OpenAI compatibility layer).
    Verified standalone 2026-08-05: HTTP 200 + tool-calling on gemini-flash-lite-latest.

    Fail-fast: the underlying AsyncOpenAI client uses max_retries=0 so a 429
    or 5xx surfaces immediately instead of triggering SDK backoff retries
    (4s/7s/10s) that pile up inside the frontend's 30s timeout. Provider
    fallback in the orchestrator handles the failure instead.
    """
    client = AsyncOpenAI(
        api_key=get_api_key("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
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
    Same fail-fast client as Gemini: max_retries=0, 30s timeout.
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
