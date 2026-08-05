"""Centralized agent runner with automatic retry for all specialist agents.

Shared utility used by the orchestrator's agent-tools. Provides:
- Retry on empty/malformed output
- Retry on transient Groq provider failures
- Skip provider on 402 Payment Required / 429 rate limit (billing/limit issues)
- Applies to all agents through a single wrapper function
"""
import typing
import logging

logger = logging.getLogger(__name__)

MIN_OUTPUT_LENGTH = 20

FAILURE_PATTERNS = [
    "Error: All providers unavailable",
    "unavailable due to a technical error",
    "currently unavailable",
]

# Errors that indicate a permanent provider issue - skip retries for this provider
SKIP_PROVIDER_PATTERNS = [
    "402",
    "payment required",
    "insufficient credits",
    "quota exceeded",
    "429",
    "too many requests",
    "rate limit",
    "rate_limit",
]


async def run_with_retry(
    run_fn: typing.Callable[[str], typing.Awaitable[str]],
    user_request: str,
    max_retries: int = 1,
) -> str:
    """Run a specialist agent function with automatic retry.

    Retries if:
    - Output is empty or shorter than MIN_OUTPUT_LENGTH chars
    - Output matches a known failure pattern (provider errors, rate limits)

    Args:
        run_fn: The agent's async run function (e.g., run_cost_advanced_agent)
        user_request: The user's request string
        max_retries: Max retry attempts (default 1; total attempts = 1 + max_retries).
            Capped at 1 to avoid multiplying the provider fallback chain
            (each attempt already tries Groq -> Groq fallback -> Gemini).

    Returns:
        The first valid output, or the last attempt's output if all fail
    """
    last_output = ""

    for attempt in range(1 + max_retries):
        try:
            output = await run_fn(user_request)
        except Exception as e:
            err_str = str(e).lower()
            # 402 or billing errors - don't retry, return immediately with a clear message
            if any(p in err_str for p in SKIP_PROVIDER_PATTERNS):
                logger.warning(f"Provider billing error (attempt {attempt}): {e}")
                last_output = (
                    "I was unable to process your request right now due to API rate limits. "
                    "Please wait a moment and try again, or rephrase your request."
                )
                break
            last_output = f"Error: {e}"
            continue

        last_output = output

        if _is_valid_output(output):
            return output

    # All attempts exhausted - return last attempt's output
    return last_output


def _is_valid_output(output: str) -> bool:
    """Check if an agent's output is valid (non-empty, non-failure)."""
    if not output or len(output.strip()) < MIN_OUTPUT_LENGTH:
        return False

    output_lower = output.lower()
    for pattern in FAILURE_PATTERNS:
        if pattern.lower() in output_lower:
            return False

    return True
