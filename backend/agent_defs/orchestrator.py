"""Orchestrator Agent — routes user requests to the right specialist agent.

Uses the "Agents as Tools" pattern from OpenAI Agents SDK (not handoffs).
The Orchestrator holds one agent for each specialist function and calls
them as tools based on user intent.

Currently registered:
  - Agent 1: Daily Entry (5 tools)
  - Agent 2: Ledger & Master Data (8 tools)
  - Agent 3: Reconciliation & Banking (7 tools)
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

# Agent 3: Reconciliation & Banking tools
from agent_defs.reconciliation_agent import (
    tool_run_bank_reconciliation, tool_post_accrual_entry,
    tool_reconcile_vendor_statement, tool_reconcile_customer_statement,
    tool_track_cheque_clearing, tool_track_lc_bank_guarantee,
    tool_reconcile_bank_charges,
)

ORCHESTRATOR_NAME = "AI Accountant Orchestrator"

ORCHESTRATOR_INSTRUCTIONS = f"""You are {ORCHESTRATOR_NAME}, the main AI assistant for the accounting system.

You MUST call a function tool to answer the user. NEVER just talk — actually call the tool.

**AGENT 1 — Daily Entry:**
1. tool_check_cash_position — Check cash balance. "cash position", "balance".
2. tool_record_transaction_nl — Record expense/income. "record expense".
3. tool_check_bank_transactions — Get bank transactions. "bank statement".
4. tool_manage_petty_cash — Manage petty cash. "petty cash", "replenish".

**AGENT 2 — Ledger & Master Data:**
5. tool_create_journal_entry — Create JE. "journal entry".
6. tool_get_general_ledger — General ledger. "ledger", "account summary".
7. tool_suggest_chart_of_accounts — Chart of accounts. "chart of accounts".
8. tool_get_ap_subledger — AP: what we OWE. "AP", "accounts payable".
9. tool_get_ar_subledger — AR: what customers OWE. "AR", "receivable".
10. tool_get_payroll_ledger — Payroll. "payroll", "salary".
11. tool_categorize_fixed_asset — Fixed asset. "depreciation".
12. tool_manage_contact — ONLY for contacts. NOT for financial queries.

**AGENT 3 — Reconciliation & Banking (NEW):**
13. tool_run_bank_reconciliation — Bank reconciliation. "reconcile", "bank match".
14. tool_post_accrual_entry — Accrual entry. "accrual".
15. tool_reconcile_vendor_statement — Vendor statement. "vendor statement".
16. tool_reconcile_customer_statement — Customer statement. "customer statement".
17. tool_track_cheque_clearing — Cheque tracking. "cheque".
18. tool_track_lc_bank_guarantee — LC/BG tracking. "LC", "letter of credit".
19. tool_reconcile_bank_charges — Bank charges. "bank charges", "bank fees".

**Rules:**
- ALWAYS call a tool. Never say you cannot do something.
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
        # Agent 3
        tool_run_bank_reconciliation, tool_post_accrual_entry,
        tool_reconcile_vendor_statement, tool_reconcile_customer_statement,
        tool_track_cheque_clearing, tool_track_lc_bank_guarantee,
        tool_reconcile_bank_charges,
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
