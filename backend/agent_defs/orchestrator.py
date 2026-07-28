"""Orchestrator Agent — routes user requests to the right specialist agent.

Uses the "Agents as Tools" pattern from OpenAI Agents SDK (not handoffs).
The Orchestrator holds one agent for each specialist function and calls
them as tools based on user intent.

Primary model: Groq (llama-3.3-70b-versatile via OpenAI-compatible API)
Fallback model: Cerebras (gemma-4-31b)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents import Agent, Runner
from agents.run_config import RunConfig

from agent_defs.model_providers import (
    create_cerebras_provider,
    create_groq_provider,
    GROQ_MODEL,
    CEREBRAS_MODEL,
)
from agent_defs.daily_entry_agent import (
    tool_check_cash_position,
    tool_record_transaction_nl,
    tool_check_bank_transactions,
    tool_manage_petty_cash,
    DAILY_ENTRY_AGENT,
)

ORCHESTRATOR_NAME = "AI Accountant Orchestrator"

ORCHESTRATOR_INSTRUCTIONS = f"""You are {ORCHESTRATOR_NAME}, the main AI assistant for the accounting system.

You MUST call a function tool to answer the user. Never just talk about what you could do — actually call the tool with real parameters.

**Available tools (CALL THESE DIRECTLY):**

1. `tool_check_cash_position` — Check current cash balance. Call when user says "what is our cash position", "check balance", "how much money".
2. `tool_record_transaction_nl` — Record a financial transaction. Call when user says "record expense", "add transaction", "paid X amount for Y".
3. `tool_check_bank_transactions` — Retrieve bank transactions. Call when user asks "bank statement", "transactions", "payments".
4. `tool_manage_petty_cash` — Manage petty cash. Call when user says "petty cash", "small cash".

**Rules:**
- ALWAYS call a tool. Do not refuse or say you cannot do something — just call the tool.
- Pass dates in YYYY-MM-DD format like '2026-07-28'. Never pass 'today' or 'now' — use the actual date.
- After the tool returns, explain the result in plain English.
"""

# Orchestrator agent — holds all specialist agents as tools
# For now, Daily Entry Agent tools are registered directly
ORCHESTRATOR_AGENT = Agent(
    name=ORCHESTRATOR_NAME,
    instructions=ORCHESTRATOR_INSTRUCTIONS,
    tools=[
        tool_check_cash_position,
        tool_record_transaction_nl,
        tool_check_bank_transactions,
        tool_manage_petty_cash,
    ],
    model=CEREBRAS_MODEL,
)


async def run_orchestrator(user_request: str) -> str:
    """Route a user request through the Orchestrator to the right agent.

    Args:
        user_request: Natural language request from the user.

    Returns:
        The final response as a string.
    """
    try:
        result = await Runner.run(
            ORCHESTRATOR_AGENT,
            input=user_request,
            run_config=RunConfig(model_provider=create_cerebras_provider()),
        )
        return result.final_output
    except Exception as cerebras_error:
        # Fall back to Groq
        try:
            fallback = Agent(
                name=ORCHESTRATOR_NAME,
                instructions=ORCHESTRATOR_INSTRUCTIONS,
                tools=ORCHESTRATOR_AGENT.tools,
                model=GROQ_MODEL,
            )
            result = await Runner.run(
                fallback,
                input=user_request,
                run_config=RunConfig(model_provider=create_groq_provider()),
            )
            return result.final_output
        except Exception as groq_error:
            return (
                f"Error: All providers unavailable.\n"
                f"Groq: {groq_error}\n"
                f"Cerebras: {cerebras_error}\n"
                f"Please check API keys in .env and try again."
            )
