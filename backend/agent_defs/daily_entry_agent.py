"""Daily Entry Agent — wraps 5 tools as an OpenAI Agent."""
import sys
import os
import json
import typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import get_db, init_db, get_session
from tools.schemas import (
    CheckCashPositionInput,
    RecordTransactionNLInput,
    CheckBankTransactionsInput,
    ManagePettyCashInput,
)
from tools.cash_tools import check_cash_position
from tools.transaction_tools import record_transaction_nl
from tools.bank_tools import check_bank_transactions
from tools.petty_cash_tools import manage_petty_cash
from agent_defs.model_providers import (
    create_cerebras_provider,
    create_groq_provider,
    GROQ_MODEL,
    GROQ_FALLBACK_MODEL,
    CEREBRAS_MODEL,
)


def _get_session() -> Session:
    """Get a new database session from the shared dev database."""
    init_db()
    return get_session()


def _parse_date(date_str: typing.Optional[str], default: date | None = None) -> date:
    """Parse a date string flexibly. Accepts 'today', 'YYYY-MM-DD', or defaults."""
    if date_str is None or date_str.lower() in ("today", "now", "", "none"):
        return default or date.today()
    if date_str.lower() == "yesterday":
        from datetime import timedelta
        return (default or date.today()) - timedelta(days=1)
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return default or date.today()


def _to_json(obj) -> str:
    """Serialize a Pydantic model to JSON string."""
    return json.dumps(json.loads(obj.model_dump_json(indent=2)), indent=2, default=str)


@function_tool
def tool_check_cash_position(as_of_date: typing.Optional[str] = None, account_id: typing.Optional[str] = None) -> str:
    """Check the live cash position. Returns current cash balance and account details.

    Args:
        as_of_date: Date in YYYY-MM-DD format. Pass actual date like '2026-07-28', not 'today'.
        account_id: Optional specific cash account ID. If None, sums all accounts.
    """
    input_data = CheckCashPositionInput(
        as_of_date=_parse_date(as_of_date),
        account_id=account_id,
    )
    db = _get_session()
    try:
        result = check_cash_position(input_data, db)
        return json.dumps(json.loads(result.model_dump_json()), indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


@function_tool
def tool_record_transaction_nl(description: str, posted_date: typing.Optional[str] = None, reference: typing.Optional[str] = None) -> str:
    """Record a transaction from plain English. Creates a journal entry (debit/credit).

    Args:
        description: Plain-English transaction description (e.g., 'Paid office rent 50000 for July').
        posted_date: Date in YYYY-MM-DD format like '2026-07-28'. Defaults to today.
        reference: Optional invoice/receipt reference number.
    """
    input_data = RecordTransactionNLInput(
        description=description,
        posted_date=_parse_date(posted_date),
        reference=reference,
    )
    db = _get_session()
    try:
        result = record_transaction_nl(input_data, db)
        return json.dumps(json.loads(result.model_dump_json()), indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


@function_tool
def tool_check_bank_transactions(
    account_id: typing.Optional[str] = None,
    from_date: typing.Optional[str] = None,
    to_date: typing.Optional[str] = None,
    status: typing.Optional[str] = None,
    limit: int = 50,
) -> str:
    """Check bank transactions with optional filters.

    Args:
        account_id: Optional bank account ID to filter (e.g., 'BA-001').
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        status: Filter by 'cleared', 'pending', or 'reconciled'.
        limit: Max transactions to return (default 50, max 500).
    """
    from datetime import timedelta

    parsed_from = _parse_date(from_date, default=date.today().replace(day=1))
    parsed_to = _parse_date(to_date)

    input_data = CheckBankTransactionsInput(
        account_id=account_id,
        from_date=parsed_from,
        to_date=parsed_to,
        status=status,
        limit=limit,
    )
    db = _get_session()
    try:
        result = check_bank_transactions(input_data, db)
        return json.dumps(json.loads(result.model_dump_json()), indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


@function_tool
def tool_manage_petty_cash(
    action: str,
    fund_id: typing.Optional[str] = None,
    amount: typing.Optional[str] = None,
    description: typing.Optional[str] = None,
    paid_by: typing.Optional[str] = None,
) -> str:
    """Manage petty cash: record expense, add fund, or check replenishment.

    Args:
        action: 'expense', 'add_fund', or 'check_replenishment'.
        fund_id: Petty cash fund ID like 'PC-001'.
        amount: Amount as a number string like '2000.00'.
        description: Description of the transaction.
        paid_by: Person who paid or received.
    """
    input_data = ManagePettyCashInput(
        action=action,
        fund_id=fund_id,
        amount=Decimal(amount) if amount else None,
        description=description,
        paid_by=paid_by,
    )
    db = _get_session()
    try:
        result = manage_petty_cash(input_data, db)
        return json.dumps(json.loads(result.model_dump_json()), indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# Create the Daily Entry Agent with all tools
DAILY_ENTRY_AGENT = Agent(
    name="Daily Entry Agent",
    instructions="""You are the Daily Entry Agent for the AI Accountant system.

You ALWAYS call a function tool to answer the user. You cannot answer without calling a tool.

Available tools:

1. tool_check_cash_position(as_of_date, account_id) — Cash position / balance
2. tool_record_transaction_nl(description, posted_date, reference) — Record transaction
3. tool_check_bank_transactions(account_id, from_date, to_date, status, limit) — Bank query
4. tool_manage_petty_cash(action, fund_id, amount, description, paid_by) — Petty cash

Rules:
- ALWAYS call the correct tool.
- Pass dates in YYYY-MM-DD format.
- For 'today' pass the actual date string like '2026-07-28'.
- Never say you can't do something — just call the tool.
""",
    tools=[
        tool_check_cash_position,
        tool_record_transaction_nl,
        tool_check_bank_transactions,
        tool_manage_petty_cash,
    ],
    model=GROQ_MODEL,
)


async def run_daily_entry_agent(user_request: str) -> str:
    """Run the Daily Entry Agent with a user request.

    Uses Groq (qwen) as primary, Groq (llama-3.1-8b) as fallback, Cerebras as last resort.
    """
    try:
        result = await Runner.run(
            DAILY_ENTRY_AGENT,
            input=user_request,
            run_config=RunConfig(model_provider=create_groq_provider()),
        )
        return result.final_output
    except Exception as groq_error:
        try:
            fallback_agent = Agent(
                name="Daily Entry Agent",
                instructions=DAILY_ENTRY_AGENT.instructions,
                tools=DAILY_ENTRY_AGENT.tools,
                model=GROQ_FALLBACK_MODEL,
            )
            result = await Runner.run(
                fallback_agent,
                input=user_request,
                run_config=RunConfig(model_provider=create_groq_provider()),
            )
            return result.final_output
        except Exception as groq_fallback_error:
            try:
                cereal_agent = Agent(
                    name="Daily Entry Agent",
                    instructions=DAILY_ENTRY_AGENT.instructions,
                    tools=DAILY_ENTRY_AGENT.tools,
                    model=CEREBRAS_MODEL,
                )
                result = await Runner.run(
                    cereal_agent,
                    input=user_request,
                    run_config=RunConfig(model_provider=create_cerebras_provider()),
                )
                return result.final_output
            except Exception as cerebras_error:
                return (
                    f"All providers unavailable.\n"
                    f"Groq: {groq_error}\n"
                    f"Groq fallback: {groq_fallback_error}\n"
                    f"Cerebras: {cerebras_error}\n"
                    f"Please check API keys in .env and try again."
                )
