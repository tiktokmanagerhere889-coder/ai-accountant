
"""Orchestrator Agent - routes user requests to the right specialist agent.

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
  - Agent 7: Tax (8 tools)
  - Agent 8: Audit & Regulatory (4 tools)
  - Agent 9: Advisory (5 tools)
  - Agent 10: System Admin (4 tools)
"""
import sys, os, typing, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from agent_defs.model_providers import (
    create_groq_provider, create_gemini_provider,
    GROQ_MODEL, GROQ_FALLBACK_MODEL, GEMINI_MODEL,
)

logger = logging.getLogger("orchestrator")
from agent_defs.run_utils import run_with_retry

# Specialist agent runners
from agent_defs.daily_entry_agent import run_daily_entry_agent
from agent_defs.ledger_agent import run_ledger_agent
from agent_defs.reconciliation_agent import run_reconciliation_agent
from agent_defs.month_end_reporting_agent import run_month_end_agent
from agent_defs.year_end_agent import run_year_end_agent
from agent_defs.cost_advanced_agent import run_cost_advanced_agent
from agent_defs.tax_agent import run_tax_agent
from agent_defs.audit_agent import run_audit_agent
from agent_defs.advisory_agent import run_advisory_agent
from agent_defs.system_admin_agent import run_system_admin_agent


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
    """Route to Year-End Close & Financial Statements Agent: trial balance, P&L, balance sheet, cash flow statement, retained earnings, carry forward balances, notes to financials, close fiscal year (IRREVERSIBLE - requires approval)."""
    return await run_with_retry(run_year_end_agent, user_request)


@function_tool
async def agent_cost_advanced(user_request: str) -> str:
    """Route to Cost, Advanced Accounting & Budgeting Agent: breakeven/CVP, currency conversion, budget forecast, standard costing variance (approval), overhead allocation (approval), revenue recognition (approval), provisions/contingencies (approval), related party transactions (approval)."""
    return await run_with_retry(run_cost_advanced_agent, user_request)


@function_tool
async def agent_tax(user_request: str) -> str:
    """Route to Tax Agent: withholding tax, tax planning, advance minimum tax, EOBI deductions, sales tax adjustment, tax exemption flagging, sales tax filing (approval), income tax filing (approval)."""
    return await run_with_retry(run_tax_agent, user_request)


@function_tool
async def agent_audit(user_request: str) -> str:
    """Route to Audit & Regulatory Agent: anomaly detection, compliance deadlines, internal audit (approval), statutory registers (approval)."""
    return await run_with_retry(run_audit_agent, user_request)


@function_tool
async def agent_advisory(user_request: str) -> str:
    """Route to Advisory Agent: spending analysis, financial ratios, financial health assessment, cost cutting recommendations, custom reports (approval)."""
    return await run_with_retry(run_advisory_agent, user_request)


@function_tool
async def agent_system_admin(user_request: str) -> str:
    """Route to System Admin Agent: system status, health check, usage statistics, system preferences (approval), schedule task (approval)."""
    return await run_with_retry(run_system_admin_agent, user_request)


ORCHESTRATOR_NAME = "AI Accountant Orchestrator"

ORCHESTRATOR_INSTRUCTIONS = f"""You are {ORCHESTRATOR_NAME}. Route each user request to the correct specialist agent-tool.

- agent_daily_entry: cash/balance, record expense, bank statement, petty cash
- agent_ledger: journal entries, ledger, chart of accounts, AP/AR, payroll, fixed assets, contacts
- agent_reconciliation: bank reconciliation, accrual, vendor/customer statement, cheque, LC/BG, bank charges
- agent_month_end: unpaid bills, prepaid, depreciation, amortization, payroll recon, aging reports, budget variance, loan schedule, cash flow forecast
- agent_year_end: trial balance, P&L, balance sheet, cash flow statement, retained earnings, carry forward, notes, close fiscal year
- agent_cost_advanced: breakeven, currency conversion, budget forecast, cost variance, overhead allocation, revenue recognition, provisions, related party
- agent_tax: withholding tax, WHT, tax planning, minimum tax, EOBI, sales tax adjustment, exemption flagging, sales tax filing, income tax filing
- agent_audit: anomaly detection, fraud detection, suspicious transaction, internal audit, audit support, compliance deadline, filing deadline, due date, statutory register, register of directors
- agent_advisory: spending analysis, spending pattern, financial advice, financial health, cost cutting, reduce expenses, financial ratios, ratio analysis, custom report, report generation
- agent_system_admin: system status, health check, is everything working, usage stats, system preferences, company settings, configuration, schedule backup, backup data, system task, maintenance, admin

Pass the user's full request to the tool. After the tool returns, explain the result in plain English.

Greetings, chit-chat, or general questions ('hi', 'hello', 'how are you', 'what can you do', 'thanks'): answer directly and conversationally — do NOT route them to a specialist agent and do NOT call any tool. Just greet the user, briefly introduce yourself, and ask what accounting task you can help with."""

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
        agent_tax,
        agent_audit,
        agent_advisory,
        agent_system_admin,
    ],
    model=GROQ_MODEL,
)


async def run_orchestrator(user_request: str) -> str:
    """Route a user request through the Orchestrator to the right specialist agent."""
    # Sanitize non-ASCII from the request so httpx never hits an ascii encode
    # error when serializing to a provider (fixes 'ascii' codec crash).
    user_request = _ascii_safe(user_request)
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (GEMINI_MODEL, create_gemini_provider, "Gemini"),
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
        except Exception as e:
            error_detail = _ascii_safe(str(e))[:100]
            last_error = f"{label}: {error_detail}"
            logger.warning(f"Provider {label} failed: {error_detail}")
    return f"Error: All providers unavailable.\n{last_error}"


def _ascii_safe(text: str) -> str:
    """Replace non-ASCII chars with ASCII equivalents so httpx/provider
    serialization never raises UnicodeEncodeError. Keeps the message readable."""
    if not isinstance(text, str):
        return str(text)
    # Map common non-ASCII to ASCII; drop the rest
    replacements = {"—": "-", "–": "-", "→": "->", "“": '"', "”": '"', "‘": "'", "’": "'"}
    for k, v in replacements.items():
        text = text.replace(k, v)
    return "".join(ch if ord(ch) < 128 else "?" for ch in text)
