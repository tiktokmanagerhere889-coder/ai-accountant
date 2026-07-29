"""Custom model providers for Cerebras (primary) and Groq (fallback).

Both providers implement OpenAI-compatible chat completions APIs.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from agents.models.openai_provider import OpenAIProvider

# Load .env from project root
dotenv_path = Path(__file__).resolve().parents[2] / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path, override=True)

# Model configuration — Groq primary (best free-tier tool calling)
# llama-4-scout is Groq's newest free model with strong tool use
# llama-3.3-70b-versatile as fallback — reliable tool calling
# Cerebras llama3.1-8b as last resort (requires active plan)
GROQ_MODEL = os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
CEREBRAS_MODEL = os.environ.get("CEREBRAS_MODEL", "llama3.1-8b")

# API keys from .env
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")


def create_cerebras_provider() -> OpenAIProvider:
    """Create an OpenAI-compatible provider for Cerebras inference.

    Base URL: https://api.cerebras.ai/v1
    Uses Chat Completions API (not Responses API).
    """
    return OpenAIProvider(
        base_url="https://api.cerebras.ai/v1",
        api_key=CEREBRAS_API_KEY,
        use_responses=False,
    )


def create_groq_provider() -> OpenAIProvider:
    """Create an OpenAI-compatible provider for Groq inference.

    Base URL: https://api.groq.com/openai/v1
    Uses Chat Completions API (not Responses API).
    """
    return OpenAIProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY,
        use_responses=False,
    )
