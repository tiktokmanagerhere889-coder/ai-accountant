"""Reconciliation & Banking Agent - wraps 7 tools as an OpenAI Agent."""
import sys, os, json, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import init_db, get_session
from tools.schemas import (
    RunBankReconciliationInput, PostAccrualEntryInput,
    ReconcileVendorStatementInput, ReconcileCustomerStatementInput,
    TrackChequeClearingInput, TrackLCBGInput,
    ReconcileBankChargesInput,
)
from tools.reconciliation_tools import (
    run_bank_reconciliation, post_accrual_entry,
    reconcile_vendor_statement, reconcile_customer_statement,
    track_cheque_clearing, track_lc_bank_guarantee,
    reconcile_bank_charges,
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


# -- Tool 1: run_bank_reconciliation --
@function_tool
def tool_run_bank_reconciliation(
    bank_account_id: str, statement_date: str,
    from_date: str, to_date: str,
) -> str:
    """Run bank reconciliation - match bank statement lines against journal entries. Returns suggested matches requiring approval.

    Args:
        bank_account_id: Bank account ID e.g. 'BA-001'.
        statement_date: Statement date YYYY-MM-DD.
        from_date: Start date for matching YYYY-MM-DD.
        to_date: End date for matching YYYY-MM-DD.
    """
    inp = RunBankReconciliationInput(
        bank_account_id=bank_account_id,
        statement_date=date.fromisoformat(statement_date),
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
    )
    db = _get_session()
    try:
        r = run_bank_reconciliation(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 2: post_accrual_entry --
@function_tool
def tool_post_accrual_entry(
    accrual_type: str, amount: str, description: str, period_date: str,
    debit_account: typing.Optional[str] = None,
    credit_account: typing.Optional[str] = None,
    partial_period_days: typing.Optional[int] = None,
) -> str:
    """Suggest a month-end accrual entry. Requires approval before posting.

    Args:
        accrual_type: 'salary', 'utilities', 'rent', or 'other'.
        amount: Amount as string e.g. '150000.00'.
        description: Description of the accrual.
        period_date: Period date YYYY-MM-DD.
        debit_account: Override debit account.
        credit_account: Override credit account.
        partial_period_days: Days for prorated calculation.
    """
    inp = PostAccrualEntryInput(
        accrual_type=accrual_type, amount=Decimal(amount),
        description=description, period_date=date.fromisoformat(period_date),
        debit_account=debit_account, credit_account=credit_account,
        partial_period_days=partial_period_days,
    )
    db = _get_session()
    try:
        r = post_accrual_entry(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 3: reconcile_vendor_statement --
@function_tool
def tool_reconcile_vendor_statement(
    vendor_contact_id: str, statement_date: str,
    from_date: str, to_date: str,
    statement_lines: str,
) -> str:
    """Reconcile a vendor statement against internal AP records. Requires approval.

    Args:
        vendor_contact_id: Contact ID for the vendor.
        statement_date: Statement date YYYY-MM-DD.
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        statement_lines: JSON array of lines, each with reference, date, amount, description.
    """
    import json as _json
    parsed_lines = _json.loads(statement_lines)
    from tools.schemas import VendorStatementLine
    lines = [VendorStatementLine(**line) for line in parsed_lines]

    inp = ReconcileVendorStatementInput(
        vendor_contact_id=vendor_contact_id,
        statement_date=date.fromisoformat(statement_date),
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
        statement_lines=lines,
    )
    db = _get_session()
    try:
        r = reconcile_vendor_statement(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 4: reconcile_customer_statement --
@function_tool
def tool_reconcile_customer_statement(
    customer_contact_id: str, statement_date: str,
    from_date: str, to_date: str,
    statement_lines: str,
) -> str:
    """Reconcile a customer statement against internal AR records. Requires approval.

    Args:
        customer_contact_id: Contact ID for the customer.
        statement_date: Statement date YYYY-MM-DD.
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        statement_lines: JSON array of lines.
    """
    import json as _json
    parsed_lines = _json.loads(statement_lines)
    from tools.schemas import VendorStatementLine
    lines = [VendorStatementLine(**line) for line in parsed_lines]

    inp = ReconcileCustomerStatementInput(
        customer_contact_id=customer_contact_id,
        statement_date=date.fromisoformat(statement_date),
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
        statement_lines=lines,
    )
    db = _get_session()
    try:
        r = reconcile_customer_statement(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 5: track_cheque_clearing --
@function_tool(strict_mode=False)
def tool_track_cheque_clearing(
    action: str,
    cheque_id: typing.Optional[str] = None,
    vendor_name: typing.Optional[str] = None,
    amount: typing.Optional[str] = None,
    issue_date: typing.Optional[str] = None,
    bank_account_id: typing.Optional[str] = None,
) -> str:
    """Track cheque lifecycle: issue, clear, bounce, reconcile, or check status.

    Args:
        action: 'issue', 'clear', 'bounce', 'reconcile', or 'status'.
        cheque_id: Cheque ID like 'CHQ-000001'.
        vendor_name: Vendor/payee name for issue action.
        amount: Amount as string for issue action.
        issue_date: Issue date YYYY-MM-DD for issue action.
        bank_account_id: Bank account ID.
    """
    inp = TrackChequeClearingInput(
        action=action, cheque_id=cheque_id, vendor_name=vendor_name,
        amount=Decimal(amount) if amount else None,
        issue_date=date.fromisoformat(issue_date) if issue_date else None,
        bank_account_id=bank_account_id,
    )
    db = _get_session()
    try:
        r = track_cheque_clearing(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 6: track_lc_bank_guarantee --
@function_tool(strict_mode=False)
def tool_track_lc_bank_guarantee(
    action: str,
    lc_id: typing.Optional[str] = None,
    lc_type: typing.Optional[str] = None,
    beneficiary: typing.Optional[str] = None,
    amount: typing.Optional[str] = None,
    issue_date: typing.Optional[str] = None,
    expiry_date: typing.Optional[str] = None,
    currency: str = "PKR",
) -> str:
    """Track LC or Bank Guarantee: issue, amend, expire, close, or check status. Requires approval.

    Args:
        action: 'issue', 'amend', 'expire', 'close', or 'status'.
        lc_id: LC/BG ID like 'LC-202607-001'.
        lc_type: 'LC' or 'BG' for issue action.
        beneficiary: Beneficiary name for issue action.
        amount: Amount as string for issue action.
        issue_date: Issue date YYYY-MM-DD.
        expiry_date: Expiry date YYYY-MM-DD.
        currency: Currency code (default PKR).
    """
    # lc_type param maps to 'type' in the Pydantic model
    actual_type = lc_type
    inp = TrackLCBGInput(
        action=action, lc_id=lc_id, type=actual_type, beneficiary=beneficiary,
        amount=Decimal(amount) if amount else None,
        issue_date=date.fromisoformat(issue_date) if issue_date else None,
        expiry_date=date.fromisoformat(expiry_date) if expiry_date else None,
        currency=currency,
    )
    db = _get_session()
    try:
        r = track_lc_bank_guarantee(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 7: reconcile_bank_charges --
@function_tool
def tool_reconcile_bank_charges(
    bank_account_id: str, from_date: str, to_date: str,
    charge_type: typing.Optional[str] = None,
) -> str:
    """Reconcile bank charges/fees against journal entries. No approval needed - purely backend calculation.

    Args:
        bank_account_id: Bank account ID.
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        charge_type: Optional filter: 'service', 'maintenance', 'transfer', 'other'.
    """
    inp = ReconcileBankChargesInput(
        bank_account_id=bank_account_id,
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
        charge_type=charge_type,
    )
    db = _get_session()
    try:
        r = reconcile_bank_charges(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# Create the Reconciliation Agent with all 7 tools
RECONCILIATION_AGENT = Agent(
    name="Reconciliation & Banking Agent",
    instructions="""You are the Reconciliation & Banking Agent for the AI Accountant.

You handle bank reconciliation, accruals, vendor/customer statements, cheques, LCs, and bank charges. You have 7 tools.

Available tools:
1. tool_run_bank_reconciliation - Match bank transactions against journal entries (NEEDS APPROVAL).
2. tool_post_accrual_entry - Suggest month-end accrual entry (NEEDS APPROVAL).
3. tool_reconcile_vendor_statement - Match vendor statement against AP records (NEEDS APPROVAL).
4. tool_reconcile_customer_statement - Match customer statement against AR records (NEEDS APPROVAL).
5. tool_track_cheque_clearing - Track cheque: issue, clear, bounce, reconcile, status.
6. tool_track_lc_bank_guarantee - Track LC/BG: issue, amend, expire, close, status (NEEDS APPROVAL).
7. tool_reconcile_bank_charges - Reconcile bank fees/charges against ledger entries.

Rules:
- Call the right tool based on the user's request.
- For approval tools: explain the suggestion and ask user to approve.
- Pass dates in YYYY-MM-DD format.
- For statement_lines, describe them clearly in your response.
""",
    tools=[
        tool_run_bank_reconciliation, tool_post_accrual_entry,
        tool_reconcile_vendor_statement, tool_reconcile_customer_statement,
        tool_track_cheque_clearing, tool_track_lc_bank_guarantee,
        tool_reconcile_bank_charges,
    ],
    model=GROQ_MODEL,
)


async def run_reconciliation_agent(user_request: str) -> str:
    """Run the Reconciliation Agent with a user request."""
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (GEMINI_MODEL, create_gemini_provider, "Gemini"),
    ]:
        try:
            agent = RECONCILIATION_AGENT if attempt_model == GROQ_MODEL else Agent(
                name="Reconciliation & Banking Agent",
                instructions=RECONCILIATION_AGENT.instructions,
                tools=RECONCILIATION_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(agent, input=user_request, run_config=RunConfig(model_provider=provider_fn()))
            return result.final_output
        except Exception:
            last_error = f"{label}: failure"
    return f"Error: All providers unavailable.\n{last_error}"
