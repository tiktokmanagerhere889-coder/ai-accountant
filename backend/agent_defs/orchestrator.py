"""Orchestrator Agent — routes user requests to the right specialist agent.

Uses the "Agents as Tools" pattern from OpenAI Agents SDK (not handoffs).
The Orchestrator holds one agent for each specialist function and calls
them as tools based on user intent.

Currently registered:
  - Agent 1: Daily Entry (5 tools)
  - Agent 2: Ledger & Master Data (8 tools)
"""
import sys, os, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents import Agent, Runner
from agents.run_config import RunConfig

from agent_defs.model_providers import (
    create_cerebras_provider, create_groq_provider,
    GROQ_MODEL, GROQ_FALLBACK_MODEL, CEREBRAS_MODEL,
)

# Agent 1: Daily Entry tools
from agent_defs.daily_entry_agent import (
    tool_check_cash_position, tool_record_transaction_nl,
    tool_check_bank_transactions, tool_manage_petty_cash,
)

# Agent 2: Ledger & Master Data tools
from agent_defs.ledger_agent import (
    tool_create_journal_entry, tool_get_general_ledger,
    tool_suggest_chart_of_accounts, tool_get_ap_subledger,
    tool_get_ar_subledger, tool_get_payroll_ledger,
    tool_categorize_fixed_asset, tool_manage_contact,
)

ORCHESTRATOR_NAME = "AI Accountant Orchestrator"

ORCHESTRATOR_INSTRUCTIONS = f"""You are {ORCHESTRATOR_NAME}, the main AI assistant for the accounting system.

You MUST call a function tool to answer the user. NEVER just talk — actually call the tool.

**AGENT 1 — Daily Entry Tools:**
1. `tool_check_cash_position` — Check cash balance. Use when user asks "cash position", "balance".
2. `tool_record_transaction_nl` — Record expense/income from plain English. Use for "record expense", "add transaction", "paid X".
3. `tool_check_bank_transactions` — Get bank transactions. Use for "bank statement", "bank activity", "payments".
4. `tool_manage_petty_cash` — Manage petty cash. Use for "petty cash", "small cash", "replenish".

**AGENT 2 — Ledger & Master Data Tools:**
5. `tool_create_journal_entry` — Create a journal entry with debit/credit accounts. Use for "journal entry", "debit credit".
6. `tool_get_general_ledger` — Get the general ledger. Use for "ledger", "general ledger", "account summary".
7. `tool_suggest_chart_of_accounts` — Suggest chart of accounts (NEEDS APPROVAL). Use for "chart of accounts", "setup accounts", "COA".
8. `tool_get_ap_subledger` — Get Accounts Payable. Use for "AP", "payable", "what we owe", "vendor balance".
9. `tool_get_ar_subledger` — Get Accounts Receivable. Use for "AR", "receivable", "what customers owe", "outstanding".
10. `tool_get_payroll_ledger` — Get payroll records. Use for "payroll", "salary", "employee pay".
11. `tool_categorize_fixed_asset` — Categorize a fixed asset (NEEDS APPROVAL). Use for "fixed asset", "depreciation", "new asset".
12. `tool_manage_contact` — Add/update/delete/search vendors and customers. Use for "vendor", "customer", "contact", "supplier".

**Rules:**
- ALWAYS call a tool. Never say you cannot do something — just call the right tool.
- For approval tools (7, 11): explain the suggestion and ask user to approve.
- Pass dates in YYYY-MM-DD format.
- After each tool returns, explain the result in plain English.
"""

ORCHESTRATOR_AGENT = Agent(
    name=ORCHESTRATOR_NAME,
    instructions=ORCHESTRATOR_INSTRUCTIONS,
    tools=[
        # Agent 1
        tool_check_cash_position, tool_record_transaction_nl,
        tool_check_bank_transactions, tool_manage_petty_cash,
        # Agent 2
        tool_create_journal_entry, tool_get_general_ledger,
        tool_suggest_chart_of_accounts, tool_get_ap_subledger,
        tool_get_ar_subledger, tool_get_payroll_ledger,
        tool_categorize_fixed_asset, tool_manage_contact,
    ],
    model=GROQ_MODEL,
)


async def run_orchestrator(user_request: str) -> str:
    """Route a user request through the Orchestrator to the right agent."""
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (CEREBRAS_MODEL, create_cerebras_provider, "Cerebras"),
    ]:
        try:
            agent = ORCHESTRATOR_AGENT if attempt_model == GROQ_MODEL else Agent(
                name=ORCHESTRATOR_NAME,
                instructions=ORCHESTRATOR_INSTRUCTIONS,
                tools=ORCHESTRATOR_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(
                agent, input=user_request,
                run_config=RunConfig(model_provider=provider_fn()),
            )
            return result.final_output
        except Exception:
            last_error = f"{label}: failure"
    return f"Error: All providers unavailable.\n{last_error}"
