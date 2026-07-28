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

CRITICAL: Choose the RIGHT tool. Read descriptions carefully before calling.

**AGENT 1 — Daily Entry Tools:**
1. `tool_check_cash_position(as_of_date)` — Check cash balance. "cash position", "balance", "how much money".
2. `tool_record_transaction_nl(description, posted_date)` — Record expense/income from plain English. "record expense", "add transaction", "paid X amount".
3. `tool_check_bank_transactions(account_id, from_date, to_date)` — Get bank transactions. "bank statement", "bank activity".
4. `tool_manage_petty_cash(action, fund_id, amount)` — Manage petty cash. "petty cash", "small cash", "replenish".

**AGENT 2 — Ledger & Master Data Tools (IMPORTANT - Read Descriptions Carefully):**
5. `tool_create_journal_entry(description, debit_account, debit_amount, credit_account, credit_amount)` — Create JE with specific accounts. "journal entry", "debit credit", "JE".
6. `tool_get_general_ledger(from_date, to_date)` — Get the general ledger. "ledger", "general ledger", "account summary".
7. `tool_suggest_chart_of_accounts(business_type)` — Suggest chart of accounts. "chart of accounts", "setup accounts", "COA".
8. `tool_get_ap_subledger(from_date, to_date)` — **AP subledger: what we OWE vendors**. "AP", "accounts payable", "what we owe", "vendor balances". DO NOT use manage_contact for this.
9. `tool_get_ar_subledger(from_date, to_date)` — **AR subledger: what customers OWE US**. "AR", "accounts receivable", "outstanding", "customer receivables".
10. `tool_get_payroll_ledger(from_date, to_date)` — Payroll records. "payroll", "salary", "employee pay".
11. `tool_categorize_fixed_asset(asset_name, purchase_cost)` — Categorize a fixed asset. "fixed asset", "depreciation", "new asset".
12. `tool_manage_contact(action, contact_type, contact_name)` — **ONLY for adding/updating/deleting contact records.** "add vendor", "new customer", "update contact". DO NOT use this for AP/AR queries.

**Rules:**
- ALWAYS call a tool. Never say you cannot do something.
- tool_manage_contact is ONLY for adding/updating/deleting contacts. For financial queries use the specific tools.
- Pass dates in YYYY-MM-DD format.
- After tool returns, explain the result in plain English.
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
