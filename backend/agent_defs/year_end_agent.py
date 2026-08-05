"""Year-End Close & Financial Statements Agent - wraps 8 tools as an OpenAI Agent."""
import sys, os, json, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import init_db, get_session
from tools.schemas import (
    GenerateTrialBalanceInput, GenerateProfitLossInput, GenerateBalanceSheetInput,
    GenerateCashFlowInput, TransferRetainedEarningsInput,
    CarryForwardBalancesInput, DraftNotesToFinancialsInput, CloseFiscalYearInput,
)
from tools.year_end_tools import (
    generate_trial_balance, generate_profit_loss, generate_balance_sheet,
    generate_cash_flow_statement, transfer_retained_earnings,
    carry_forward_balances, draft_notes_to_financials, close_fiscal_year,
)
from agent_defs.model_providers import (
    create_groq_provider, create_gemini_provider,
    GROQ_MODEL, GROQ_FALLBACK_MODEL, GEMINI_MODEL,
)


def _get_session():
    init_db()
    return get_session()


def _to_json(obj):
    return json.dumps(json.loads(obj.model_dump_json()), indent=2, default=str)


# -- Tool 1: generate_trial_balance --
@function_tool
def tool_generate_trial_balance(as_of_date: str = "") -> str:
    """Generate trial balance as of a date. Checks if total debits = total credits.

    Args:
        as_of_date: Date in YYYY-MM-DD format. Defaults to today.
    """
    parsed_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
    inp = GenerateTrialBalanceInput(as_of_date=parsed_date)
    db = _get_session()
    try:
        r = generate_trial_balance(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 2: generate_profit_loss --
@function_tool
def tool_generate_profit_loss(from_date: str, to_date: str) -> str:
    """Generate profit & loss (income statement) for a date range.

    Args:
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
    """
    inp = GenerateProfitLossInput(
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
    )
    db = _get_session()
    try:
        r = generate_profit_loss(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 3: generate_balance_sheet --
@function_tool
def tool_generate_balance_sheet(as_of_date: str = "") -> str:
    """Generate balance sheet as of a date. Verifies assets = liabilities + equity.

    Args:
        as_of_date: Date in YYYY-MM-DD format. Defaults to today.
    """
    parsed_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
    inp = GenerateBalanceSheetInput(as_of_date=parsed_date)
    db = _get_session()
    try:
        r = generate_balance_sheet(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 4: generate_cash_flow_statement --
@function_tool
def tool_generate_cash_flow_statement(from_date: str, to_date: str) -> str:
    """Generate cash flow statement for a date range (operating/investing/financing).

    Args:
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
    """
    inp = GenerateCashFlowInput(
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
    )
    db = _get_session()
    try:
        r = generate_cash_flow_statement(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 5: transfer_retained_earnings --
@function_tool
def tool_transfer_retained_earnings(fiscal_year: int) -> str:
    """Transfer net income to retained earnings for a fiscal year.

    Args:
        fiscal_year: Fiscal year e.g. 2026.
    """
    inp = TransferRetainedEarningsInput(fiscal_year=fiscal_year)
    db = _get_session()
    try:
        r = transfer_retained_earnings(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 6: carry_forward_balances --
@function_tool
def tool_carry_forward_balances(from_fiscal_year: int, to_fiscal_year: int, closing_date: str = "") -> str:
    """Carry forward balance sheet account balances to the new fiscal year.

    Args:
        from_fiscal_year: Current fiscal year being closed.
        to_fiscal_year: Next fiscal year.
        closing_date: Closing date YYYY-MM-DD. Defaults to today.
    """
    parsed_date = date.fromisoformat(closing_date) if closing_date else date.today()
    inp = CarryForwardBalancesInput(
        from_fiscal_year=from_fiscal_year,
        to_fiscal_year=to_fiscal_year,
        closing_date=parsed_date,
    )
    db = _get_session()
    try:
        r = carry_forward_balances(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 7: draft_notes_to_financials --
@function_tool
def tool_draft_notes_to_financials(fiscal_year: int, note_types: typing.Optional[str] = None) -> str:
    """Draft explanatory notes to financial statements.

    Args:
        fiscal_year: Fiscal year e.g. 2026.
        note_types: Optional comma-separated list: accounting_policies,revenue_recognition,depreciation_method,commitments,contingencies
    """
    parsed_types = [t.strip() for t in note_types.split(",")] if note_types else None
    inp = DraftNotesToFinancialsInput(fiscal_year=fiscal_year, note_types=parsed_types)
    db = _get_session()
    try:
        r = draft_notes_to_financials(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 8: close_fiscal_year --
@function_tool
def tool_close_fiscal_year(fiscal_year: int, closing_date: str = "", confirm: bool = False) -> str:
    """CLOSE a fiscal year - IRREVERSIBLE. Requires confirm=True.

    Args:
        fiscal_year: Fiscal year to close e.g. 2026.
        closing_date: Closing date YYYY-MM-DD. Defaults to today.
        confirm: Must be True to execute. If False or missing, returns error.
    """
    parsed_date = date.fromisoformat(closing_date) if closing_date else date.today()
    inp = CloseFiscalYearInput(fiscal_year=fiscal_year, closing_date=parsed_date, confirm=confirm)
    db = _get_session()
    try:
        r = close_fiscal_year(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# Create the Year-End Close & Financial Statements Agent with all 8 tools
YEAR_END_AGENT = Agent(
    name="Year-End Close & Financial Statements Agent",
    instructions="""You are the Year-End Close & Financial Statements Agent for the AI Accountant.

You handle all year-end closing tasks and financial statement generation. You have 8 tools.

Available tools:
1. tool_generate_trial_balance - Trial balance: checks if total debits = total credits.
2. tool_generate_profit_loss - Profit & Loss statement (income statement).
3. tool_generate_balance_sheet - Balance sheet: verifies assets = liabilities + equity.
4. tool_generate_cash_flow_statement - Cash flow statement (operating/investing/financing).
5. tool_transfer_retained_earnings - Transfer net income to retained earnings.
6. tool_carry_forward_balances - Carry forward balance sheet balances to new year.
7. tool_draft_notes_to_financials - Draft explanatory notes to financial statements.
8. tool_close_fiscal_year - Close fiscal year (IRREVERSIBLE, requires approval).

Rules:
- ALWAYS call a tool to answer. Never just talk.
- For tool 8 (close_fiscal_year): explicitly warn the user this is irreversible and ask for confirmation. Set confirm=True only when user agrees.
- Pass dates in YYYY-MM-DD format.
- Explain results in plain English after tool calls.
- Statement order: trial balance -> P&L -> balance sheet -> cash flow.
""",
    tools=[
        tool_generate_trial_balance, tool_generate_profit_loss,
        tool_generate_balance_sheet, tool_generate_cash_flow_statement,
        tool_transfer_retained_earnings, tool_carry_forward_balances,
        tool_draft_notes_to_financials, tool_close_fiscal_year,
    ],
    model=GROQ_MODEL,
)


async def run_year_end_agent(user_request: str) -> str:
    """Run the Year-End Close & Financial Statements Agent with a user request.

    Groq primary -> Groq fallback -> Gemini last resort.
    """
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (GEMINI_MODEL, create_gemini_provider, "Gemini"),
    ]:
        try:
            agent = YEAR_END_AGENT if attempt_model == GROQ_MODEL else Agent(
                name="Year-End Close & Financial Statements Agent",
                instructions=YEAR_END_AGENT.instructions,
                tools=YEAR_END_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(agent, input=user_request, run_config=RunConfig(model_provider=provider_fn()))
            return result.final_output
        except Exception:
            last_error = f"{label}: failure"
    return f"Error: All providers unavailable.\n{last_error}"
