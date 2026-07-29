"""Orchestrator Agent — routes user requests to the right specialist agent.

Uses the "Agents as Tools" pattern from OpenAI Agents SDK (not handoffs).
The Orchestrator holds one agent-tool per specialist agent and calls them
based on user intent. Each agent-tool delegates to its own Agent + Runner.

Currently registered:
  - Agent 1: Daily Entry (4 tools)
  - Agent 2: Ledger & Master Data (8 tools)
  - Agent 3: Reconciliation & Banking (7 tools)
  - Agent 4: Month-End Reporting (10 tools)
  - Agent 5: Year-End Close & Financial Statements (8 tools)
  - Agent 6: Cost, Advanced Accounting & Budgeting (8 tools)
"""
import sys, os, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from agent_defs.model_providers import (
    create_cerebras_provider, create_groq_provider,
    GROQ_MODEL, GROQ_FALLBACK_MODEL, CEREBRAS_MODEL,
)
from agent_defs.run_utils import run_with_retry

# Specialist agent runners
from agent_defs.daily_entry_agent import run_daily_entry_agent
from agent_defs.ledger_agent import run_ledger_agent
from agent_defs.reconciliation_agent import run_reconciliation_agent
from agent_defs.month_end_reporting_agent import run_month_end_agent
from agent_defs.year_end_agent import run_year_end_agent
from agent_defs.cost_advanced_agent import run_cost_advanced_agent


@function_tool
async def agent_daily_entry(user_request: str) -> str:
    """Route to Daily Entry Agent: cash position, record transactions, bank transactions, petty cash. Use for everyday cash/expense queries."""
    return await run_with_retry(run_daily_entry_agent, user_request)


@function_tool
async def agent_ledger(user_request: str) -> str:
    """Route to Ledger & Master Data Agent: journal entries, general ledger, chart of accounts, AP/AR subledgers, payroll, fixed assets, vendor/customer contacts. Use for bookkeeping and master data."""
    return await run_with_retry(run_ledger_agent, user_request)


@function_tool
async def agent_reconciliation(user_request: str) -> str:
    """Route to Reconciliation & Banking Agent: bank reconciliation, accrual entries, vendor/customer statement reconciliation, cheque clearing, LC/BG tracking, bank charges reconciliation."""
    return await run_with_retry(run_reconciliation_agent, user_request)


@function_tool
async def agent_month_end(user_request: str) -> str:
    """Route to Month-End Reporting Agent: unpaid bills, prepaid adjustments, depreciation, amortization, payroll reconciliation, AR/AP aging reports, budget variance, loan schedule, cash flow forecast."""
    return await run_with_retry(run_month_end_agent, user_request)


@function_tool
async def agent_year_end(user_request: str) -> str:
    """Route to Year-End Close & Financial Statements Agent: trial balance, P&L, balance sheet, cash flow statement, retained earnings, carry forward balances, notes to financials, close fiscal year (IRREVERSIBLE — requires approval)."""
    return await run_with_retry(run_year_end_agent, user_request)


@function_tool
async def agent_cost_advanced(user_request: str) -> str:
    """Route to Cost, Advanced Accounting & Budgeting Agent: breakeven/CVP, currency conversion, budget forecast, standard costing variance (approval), overhead allocation (approval), revenue recognition (approval), provisions/contingencies (approval), related party transactions (approval)."""
    return await run_with_retry(run_cost_advanced_agent, user_request)


ORCHESTRATOR_NAME = "AI Accountant Orchestrator"

ORCHESTRATOR_INSTRUCTIONS = f"""You are {ORCHESTRATOR_NAME}. Route each user request to the correct specialist agent-tool.

- agent_daily_entry: cash/balance, record expense, bank statement, petty cash
- agent_ledger: journal entries, ledger, chart of accounts, AP/AR, payroll, fixed assets, contacts
- agent_reconciliation: bank reconciliation, accrual, vendor/customer statement, cheque, LC/BG, bank charges
- agent_month_end: unpaid bills, prepaid, depreciation, amortization, payroll recon, aging reports, budget variance, loan schedule, cash flow forecast
- agent_year_end: trial balance, P&L, balance sheet, cash flow statement, retained earnings, carry forward, notes, close fiscal year
- agent_cost_advanced: breakeven, currency conversion, budget forecast, cost variance, overhead allocation, revenue recognition, provisions, related party

Pass the user's full request to the tool. After the tool returns, explain the result in plain English."""

ORCHESTRATOR_AGENT = Agent(
    name=ORCHESTRATOR_NAME,
    instructions=ORCHESTRATOR_INSTRUCTIONS,
    tools=[
        agent_daily_entry,
        agent_ledger,
        agent_reconciliation,
        agent_month_end,
        agent_year_end,
        agent_cost_advanced,
    ],
    model=GROQ_MODEL,
)


async def run_orchestrator(user_request: str) -> str:
    """Route a user request through the Orchestrator to the right specialist agent."""
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
