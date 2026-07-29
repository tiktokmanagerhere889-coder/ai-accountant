"""Cost, Advanced Accounting & Budgeting Agent — wraps 8 tools as an OpenAI Agent."""
import sys, os, json, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import init_db, get_session
from tools.schemas import (
    CalculateBreakevenInput, CalculateBreakevenOutput,
    ConvertForeignCurrencyInput, ConvertForeignCurrencyOutput,
    PrepareBudgetForecastInput, PrepareBudgetForecastOutput,
    CalculateStandardCostingVarianceInput, CalculateStandardCostingVarianceOutput,
    AllocateOverheadCostInput, AllocateOverheadCostOutput,
    CalculateRevenueRecognitionInput, CalculateRevenueRecognitionOutput,
    FlagProvisionContingentLiabilityInput, FlagProvisionContingentLiabilityOutput,
    FlagRelatedPartyTransactionInput, FlagRelatedPartyTransactionOutput,
)
from tools.cost_advanced_tools import (
    calculate_breakeven, convert_foreign_currency, prepare_budget_forecast,
    calculate_standard_costing_variance, allocate_overhead_cost,
    calculate_revenue_recognition, flag_provision_contingent_liability,
    flag_related_party_transaction,
)
from agent_defs.model_providers import (
    create_cerebras_provider, create_groq_provider,
    GROQ_MODEL, GROQ_FALLBACK_MODEL, CEREBRAS_MODEL,
)


def _get_session():
    init_db()
    return get_session()


def _to_json(obj):
    return json.dumps(json.loads(obj.model_dump_json()), indent=2, default=str)


# -- Tool 1: calculate_breakeven --
@function_tool
def tool_calculate_breakeven(fixed_cost: str, variable_cost_per_unit: str, selling_price_per_unit: str) -> str:
    """Calculate break-even point using cost-volume-profit (CVP) analysis. Returns units and revenue needed to break even.

    Args:
        fixed_cost: Total fixed costs as string (e.g., '500000').
        variable_cost_per_unit: Variable cost per unit as string (e.g., '300').
        selling_price_per_unit: Selling price per unit as string (e.g., '500').
    """
    inp = CalculateBreakevenInput(
        fixed_cost=Decimal(fixed_cost),
        variable_cost_per_unit=Decimal(variable_cost_per_unit),
        selling_price_per_unit=Decimal(selling_price_per_unit),
    )
    db = _get_session()
    try:
        r = calculate_breakeven(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 2: convert_foreign_currency --
@function_tool
def tool_convert_foreign_currency(amount: str, from_currency: str, to_currency: str, rate_date: str = "") -> str:
    """Convert an amount between currencies using stored exchange rates.

    Args:
        amount: Amount to convert as string (e.g., '1000').
        from_currency: Source currency code (e.g., 'USD').
        to_currency: Target currency code (e.g., 'PKR').
        rate_date: Optional rate date YYYY-MM-DD. Defaults to latest available.
    """
    parsed_date = date.fromisoformat(rate_date) if rate_date else None
    inp = ConvertForeignCurrencyInput(
        amount=Decimal(amount),
        from_currency=from_currency.upper(),
        to_currency=to_currency.upper(),
        rate_date=parsed_date,
    )
    db = _get_session()
    try:
        r = convert_foreign_currency(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 3: prepare_budget_forecast --
@function_tool
def tool_prepare_budget_forecast(fiscal_year: int, periods: int = 12, account_code_prefix: str = "") -> str:
    """Prepare budget forecast from historical spending patterns.

    Args:
        fiscal_year: Fiscal year to forecast for (e.g., 2027).
        periods: Number of periods to forecast (1-12). Default 12.
        account_code_prefix: Optional account code prefix to filter (e.g., '6000').
    """
    prefix = account_code_prefix if account_code_prefix else None
    inp = PrepareBudgetForecastInput(
        fiscal_year=fiscal_year,
        periods=periods,
        account_code_prefix=prefix,
    )
    db = _get_session()
    try:
        r = prepare_budget_forecast(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 4: calculate_standard_costing_variance --
@function_tool
def tool_calculate_standard_costing_variance(account_code: str, period: int, fiscal_year: int, standard_cost: str, standard_quantity: str = "") -> str:
    """Calculate variance between standard (budgeted) cost and actual cost. Requires approval.

    Args:
        account_code: Expense account code (e.g., '6000').
        period: Period number 1-12.
        fiscal_year: Fiscal year.
        standard_cost: Standard/budgeted cost as string.
        standard_quantity: Optional standard quantity as string.
    """
    qty = Decimal(standard_quantity) if standard_quantity else None
    inp = CalculateStandardCostingVarianceInput(
        account_code=account_code,
        period=period,
        fiscal_year=fiscal_year,
        standard_cost=Decimal(standard_cost),
        standard_quantity=qty,
    )
    db = _get_session()
    try:
        r = calculate_standard_costing_variance(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 5: allocate_overhead_cost --
@function_tool
def tool_allocate_overhead_cost(total_overhead: str, allocation_basis: str, allocation_json: str, period: int, fiscal_year: int) -> str:
    """Allocate overhead costs across departments. Requires approval.

    Args:
        total_overhead: Total overhead cost to allocate as string.
        allocation_basis: Basis: 'sq_ft', 'headcount', 'revenue_pct', or 'custom'.
        allocation_json: JSON array of objects with 'name' (str) and 'value' (number) fields, e.g. [{"name": "Sales", "value": 10}, {"name": "Engineering", "value": 25}]
        period: Period number 1-12.
        fiscal_year: Fiscal year.
    """
    pool_data = json.loads(allocation_json)
    from tools.schemas import AllocationPoolItem
    pool = [AllocationPoolItem(name=item["name"], value=Decimal(str(item["value"]))) for item in pool_data]
    inp = AllocateOverheadCostInput(
        total_overhead=Decimal(total_overhead),
        allocation_basis=allocation_basis,
        allocation_pool=pool,
        period=period,
        fiscal_year=fiscal_year,
    )
    db = _get_session()
    try:
        r = allocate_overhead_cost(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 6: calculate_revenue_recognition --
@function_tool
def tool_calculate_revenue_recognition(contract_id: str, contract_value: str, completion_percentage: str, previous_recognized: str = "", period: int = 0, fiscal_year: int = 0) -> str:
    """Calculate revenue to recognize under percentage-of-completion method. Requires approval.

    Args:
        contract_id: Contract identifier.
        contract_value: Total contract value as string.
        completion_percentage: Percentage complete as string (0-100).
        previous_recognized: Optional revenue already recognized as string.
        period: Period number 1-12.
        fiscal_year: Fiscal year.
    """
    prev = Decimal(previous_recognized) if previous_recognized else None
    inp = CalculateRevenueRecognitionInput(
        contract_id=contract_id,
        contract_value=Decimal(contract_value),
        completion_percentage=Decimal(completion_percentage),
        previous_recognized=prev,
        period=period,
        fiscal_year=fiscal_year,
    )
    db = _get_session()
    try:
        r = calculate_revenue_recognition(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 7: flag_provision_contingent_liability --
@function_tool
def tool_flag_provision_contingent_liability(description: str, estimated_amount: str, probability: str, fiscal_year: int, related_party: str = "") -> str:
    """Flag a provision or contingent liability per IAS 37. Requires approval.

    Args:
        description: Description of the contingent event.
        estimated_amount: Estimated financial impact as string.
        probability: 'probable', 'possible', or 'remote'.
        fiscal_year: Fiscal year.
        related_party: Optional related party name.
    """
    rp = related_party if related_party else None
    inp = FlagProvisionContingentLiabilityInput(
        description=description,
        estimated_amount=Decimal(estimated_amount),
        probability=probability.lower(),
        fiscal_year=fiscal_year,
        related_party=rp,
    )
    db = _get_session()
    try:
        r = flag_provision_contingent_liability(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 8: flag_related_party_transaction --
@function_tool
def tool_flag_related_party_transaction(entry_id: str, transaction_description: str, amount: str, counterparty_name: str, fiscal_year: int) -> str:
    """Check if a transaction involves a related party (insider-connected). Requires approval.

    Args:
        entry_id: Journal entry ID to check.
        transaction_description: Description of the transaction.
        amount: Transaction amount as string.
        counterparty_name: Counterparty name.
        fiscal_year: Fiscal year.
    """
    inp = FlagRelatedPartyTransactionInput(
        entry_id=entry_id,
        transaction_description=transaction_description,
        amount=Decimal(amount),
        counterparty_name=counterparty_name,
        fiscal_year=fiscal_year,
    )
    db = _get_session()
    try:
        r = flag_related_party_transaction(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# Create the Cost, Advanced Accounting & Budgeting Agent with all 8 tools
COST_ADVANCED_AGENT = Agent(
    name="Cost, Advanced Accounting & Budgeting Agent",
    instructions="""You are the Cost, Advanced Accounting & Budgeting Agent for the AI Accountant.

You handle cost/management accounting, advanced accounting, and budget planning. You have 8 tools.

Available tools:
1. tool_calculate_breakeven — Break-even / CVP analysis (no approval needed).
2. tool_convert_foreign_currency — Currency conversion using stored rates (no approval needed).
3. tool_prepare_budget_forecast — Budget forecast from historical data (no approval needed).
4. tool_calculate_standard_costing_variance — Standard vs actual cost analysis (REQUIRES APPROVAL).
5. tool_allocate_overhead_cost — Overhead allocation across departments (REQUIRES APPROVAL).
6. tool_calculate_revenue_recognition — Percentage-of-completion revenue recognition (REQUIRES APPROVAL).
7. tool_flag_provision_contingent_liability — IAS 37 provision/contingency flagging (REQUIRES APPROVAL).
8. tool_flag_related_party_transaction — Related-party transaction flagging (REQUIRES APPROVAL).

Rules:
- ALWAYS call a tool to answer. Never just talk.
- For tools 4-8: explicitly tell the user these require approval before proceeding.
- Pass amounts and costs as string numbers (e.g., '500000' not 500000).
- Pass dates in YYYY-MM-DD format.
- Explain results in plain English after tool calls.
""",
    tools=[
        tool_calculate_breakeven, tool_convert_foreign_currency,
        tool_prepare_budget_forecast, tool_calculate_standard_costing_variance,
        tool_allocate_overhead_cost, tool_calculate_revenue_recognition,
        tool_flag_provision_contingent_liability, tool_flag_related_party_transaction,
    ],
    model=GROQ_MODEL,
)


async def run_cost_advanced_agent(user_request: str) -> str:
    """Run the Cost, Advanced Accounting & Budgeting Agent with a user request.

    Groq primary -> Groq fallback -> Cerebras last resort.
    """
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (CEREBRAS_MODEL, create_cerebras_provider, "Cerebras"),
    ]:
        try:
            agent = COST_ADVANCED_AGENT if attempt_model == GROQ_MODEL else Agent(
                name="Cost, Advanced Accounting & Budgeting Agent",
                instructions=COST_ADVANCED_AGENT.instructions,
                tools=COST_ADVANCED_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(agent, input=user_request, run_config=RunConfig(model_provider=provider_fn()))
            return result.final_output
        except Exception:
            last_error = f"{label}: failure"
    return f"Error: All providers unavailable.\n{last_error}"
