"""Ledger & Master Data Agent — wraps 8 tools as an OpenAI Agent."""
import sys, os, json, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import init_db, get_session
from tools.schemas import (
    CreateJournalEntryInput, GetGeneralLedgerInput,
    GetAPSubledgerInput, GetARSubledgerInput,
    GetPayrollLedgerInput, SuggestChartOfAccountsInput,
    CategorizeFixedAssetInput, ManageContactInput,
)
from tools.ledger_tools import (
    create_journal_entry, get_general_ledger,
    get_ap_subledger, get_ar_subledger, get_payroll_ledger,
    suggest_chart_of_accounts,
)
from tools.asset_tools import categorize_fixed_asset
from tools.contact_tools import manage_contact
from agent_defs.model_providers import (
    create_cerebras_provider, create_groq_provider,
    GROQ_MODEL, GROQ_FALLBACK_MODEL, CEREBRAS_MODEL,
)


def _get_session():
    init_db()
    return get_session()


# -- Tool 1: create_journal_entry --
@function_tool
def tool_create_journal_entry(
    description: str, posted_date: typing.Optional[str] = None,
    reference: typing.Optional[str] = None,
    debit_account: str = "", debit_amount: str = "",
    credit_account: str = "", credit_amount: str = "",
    status: str = "posted",
) -> str:
    """Create a journal entry with specific debit/credit accounts. Debits must equal credits.

    Args:
        description: Description of the entry.
        posted_date: Date YYYY-MM-DD. Defaults to today.
        reference: Optional reference number.
        debit_account: Full debit account code+name e.g. '6000-Office Rent'.
        debit_amount: Debit amount as string e.g. '50000.00'.
        credit_account: Full credit account code+name e.g. '1000-Cash'.
        credit_amount: Credit amount as string e.g. '50000.00'.
        status: 'posted' or 'draft'.
    """
    inp = CreateJournalEntryInput(
        description=description,
        posted_date=date.fromisoformat(posted_date) if posted_date else date.today(),
        reference=reference,
        debit_account=debit_account, debit_amount=Decimal(debit_amount or "0"),
        credit_account=credit_account, credit_amount=Decimal(credit_amount or "0"),
        status=status,
    )
    db = _get_session()
    try:
        r = create_journal_entry(inp, db)
        return json.dumps(json.loads(r.model_dump_json()), indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 2: get_general_ledger --
@function_tool
def tool_get_general_ledger(
    from_date: typing.Optional[str] = None,
    to_date: typing.Optional[str] = None,
    account_code_prefix: typing.Optional[str] = None,
) -> str:
    """Get the general ledger grouped by account for a date range.

    Args:
        from_date: Start date YYYY-MM-DD. Defaults to first of month.
        to_date: End date YYYY-MM-DD. Defaults to today.
        account_code_prefix: Optional account prefix filter e.g. '6000'.
    """
    inp = GetGeneralLedgerInput(
        from_date=date.fromisoformat(from_date) if from_date else date.today().replace(day=1),
        to_date=date.fromisoformat(to_date) if to_date else date.today(),
        account_code_prefix=account_code_prefix,
    )
    db = _get_session()
    try:
        r = get_general_ledger(inp, db)
        return json.dumps(json.loads(r.model_dump_json()), indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 3: suggest_chart_of_accounts --
@function_tool(needs_approval=True)
def tool_suggest_chart_of_accounts(
    business_type: str, description: typing.Optional[str] = None,
) -> str:
    """Suggest a chart of accounts structure for a business type. Requires approval before saving.

    Args:
        business_type: Type of business e.g. 'retail', 'freelance', 'manufacturing', 'tech_startup', 'restaurant', 'non_profit', 'real_estate'.
        description: Optional additional context.
    """
    inp = SuggestChartOfAccountsInput(business_type=business_type, description=description)
    try:
        r = suggest_chart_of_accounts(inp)
        return json.dumps(json.loads(r.model_dump_json()), indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}"


# -- Tool 4: get_ap_subledger --
@function_tool
def tool_get_ap_subledger(
    from_date: typing.Optional[str] = None,
    to_date: typing.Optional[str] = None,
    vendor_contact_id: typing.Optional[str] = None,
) -> str:
    """Get Accounts Payable subledger — what the business owes vendors.

    Args:
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        vendor_contact_id: Optional vendor contact ID to filter.
    """
    inp = GetAPSubledgerInput(
        from_date=date.fromisoformat(from_date) if from_date else date.today().replace(day=1),
        to_date=date.fromisoformat(to_date) if to_date else date.today(),
        vendor_contact_id=vendor_contact_id,
    )
    db = _get_session()
    try:
        r = get_ap_subledger(inp, db)
        return json.dumps(json.loads(r.model_dump_json()), indent=2, default=str)
    finally:
        db.close()


# -- Tool 5: get_ar_subledger --
@function_tool
def tool_get_ar_subledger(
    from_date: typing.Optional[str] = None,
    to_date: typing.Optional[str] = None,
    customer_contact_id: typing.Optional[str] = None,
) -> str:
    """Get Accounts Receivable subledger — what customers owe the business.

    Args:
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        customer_contact_id: Optional customer contact ID to filter.
    """
    inp = GetARSubledgerInput(
        from_date=date.fromisoformat(from_date) if from_date else date.today().replace(day=1),
        to_date=date.fromisoformat(to_date) if to_date else date.today(),
        customer_contact_id=customer_contact_id,
    )
    db = _get_session()
    try:
        r = get_ar_subledger(inp, db)
        return json.dumps(json.loads(r.model_dump_json()), indent=2, default=str)
    finally:
        db.close()


# -- Tool 6: get_payroll_ledger --
@function_tool
def tool_get_payroll_ledger(
    from_date: typing.Optional[str] = None,
    to_date: typing.Optional[str] = None,
    employee_name: typing.Optional[str] = None,
) -> str:
    """Get payroll ledger for a period.

    Args:
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        employee_name: Optional employee name to filter.
    """
    inp = GetPayrollLedgerInput(
        from_date=date.fromisoformat(from_date) if from_date else date.today().replace(day=1),
        to_date=date.fromisoformat(to_date) if to_date else date.today(),
        employee_name=employee_name,
    )
    db = _get_session()
    try:
        r = get_payroll_ledger(inp, db)
        return json.dumps(json.loads(r.model_dump_json()), indent=2, default=str)
    finally:
        db.close()


# -- Tool 7: categorize_fixed_asset --
@function_tool(needs_approval=True)
def tool_categorize_fixed_asset(
    asset_name: str, purchase_cost: str,
    purchase_date: typing.Optional[str] = None,
    asset_category: typing.Optional[str] = None,
) -> str:
    """Categorize a new fixed asset with depreciation suggestion. Requires approval.

    Args:
        asset_name: Name of the asset e.g. 'Delivery Truck'.
        purchase_cost: Purchase cost as string e.g. '2000000.00'.
        purchase_date: Purchase date YYYY-MM-DD.
        asset_category: Optional category: 'building', 'vehicle', 'computer', 'furniture', 'machinery'.
    """
    inp = CategorizeFixedAssetInput(
        asset_name=asset_name,
        purchase_cost=Decimal(purchase_cost),
        purchase_date=date.fromisoformat(purchase_date) if purchase_date else date.today(),
        asset_category=asset_category,
    )
    db = _get_session()
    try:
        r = categorize_fixed_asset(inp, db)
        return json.dumps(json.loads(r.model_dump_json()), indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 8: manage_contact --
@function_tool
def tool_manage_contact(
    action: str, contact_type: str, contact_name: str,
    phone: typing.Optional[str] = None,
    email: typing.Optional[str] = None,
    address: typing.Optional[str] = None,
    tax_id: typing.Optional[str] = None,
) -> str:
    """Add, update, delete, or search vendor/customer contacts.

    Args:
        action: 'add', 'update', 'delete', or 'search'.
        contact_type: 'vendor' or 'customer'.
        contact_name: Name of the contact.
        phone: Optional phone number.
        email: Optional email address.
        address: Optional physical address.
        tax_id: Optional tax ID / NTN.
    """
    inp = ManageContactInput(
        action=action, contact_type=contact_type,
        contact_name=contact_name, phone=phone,
        email=email, address=address, tax_id=tax_id,
    )
    db = _get_session()
    try:
        r = manage_contact(inp, db)
        return json.dumps(json.loads(r.model_dump_json()), indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# Create the Ledger & Master Data Agent with all 8 tools
LEDGER_AGENT = Agent(
    name="Ledger & Master Data Agent",
    instructions="""You are the Ledger & Master Data Agent for the AI Accountant.

You handle bookkeeping, journal entries, ledgers, charts of accounts, AP/AR subledgers, payroll, fixed assets, and vendor/customer contacts. You have 8 tools.

Available tools:
1. tool_create_journal_entry — Create a journal entry with specific debit/credit accounts.
2. tool_get_general_ledger — Get the general ledger grouped by account.
3. tool_suggest_chart_of_accounts — Suggest chart of accounts for a business type (NEEDS APPROVAL).
4. tool_get_ap_subledger — Get Accounts Payable (what we owe vendors).
5. tool_get_ar_subledger — Get Accounts Receivable (what customers owe us).
6. tool_get_payroll_ledger — Get payroll records for a period.
7. tool_categorize_fixed_asset — Categorize a fixed asset with depreciation suggestion (NEEDS APPROVAL).
8. tool_manage_contact — Add/update/delete/search vendor or customer contacts.

Rules:
- ALWAYS call a tool to answer. Never just talk.
- For approval tools (3, 7): tell the user the suggestion and ask for approval.
- Pass dates in YYYY-MM-DD format.
- Explain results in plain English after tool calls.
""",
    tools=[
        tool_create_journal_entry, tool_get_general_ledger,
        tool_suggest_chart_of_accounts, tool_get_ap_subledger,
        tool_get_ar_subledger, tool_get_payroll_ledger,
        tool_categorize_fixed_asset, tool_manage_contact,
    ],
    model=GROQ_MODEL,
)


async def run_ledger_agent(user_request: str) -> str:
    """Run the Ledger Agent with a user request.

    Groq primary -> Groq fallback -> Cerebras last resort.
    """
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (CEREBRAS_MODEL, create_cerebras_provider, "Cerebras"),
    ]:
        try:
            agent = LEDGER_AGENT if attempt_model == GROQ_MODEL else Agent(
                name="Ledger & Master Data Agent",
                instructions=LEDGER_AGENT.instructions,
                tools=LEDGER_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(
                agent, input=user_request,
                run_config=RunConfig(model_provider=provider_fn()),
            )
            return result.final_output
        except Exception as e:
            last_error = f"{label}: {e}"
    return f"All providers unavailable.\n{last_error}"
