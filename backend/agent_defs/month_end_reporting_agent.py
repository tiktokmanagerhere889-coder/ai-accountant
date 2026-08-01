"""Month-End Reporting Agent - wraps 10 tools as an OpenAI Agent."""
import sys, os, json, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import init_db, get_session
from tools.schemas import (
    ReviewUnpaidBillsInput, CalculatePrepaidAdjustmentInput,
    CalculateDepreciationInput, CalculateAmortizationInput,
    ReconcilePayrollInput, GetARAgingReportInput,
    GetAPAgingReportInput, AnalyzeBudgetVarianceInput,
    GetLoanDebtScheduleInput, ForecastCashFlowInput,
)
from tools.month_end_tools import (
    review_unpaid_bills, calculate_prepaid_adjustment,
    calculate_depreciation, calculate_amortization,
    reconcile_payroll, get_ar_aging_report,
    get_ap_aging_report, analyze_budget_variance,
    get_loan_debt_schedule, forecast_cash_flow,
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


# -- Tool 1: review_unpaid_bills --
@function_tool
def tool_review_unpaid_bills(as_of_date: str = "", vendor_contact_id: typing.Optional[str] = None, min_days_overdue: typing.Optional[int] = None) -> str:
    """Review unpaid bills/AP items as of a date. No approval needed.

    Args:
        as_of_date: Date in YYYY-MM-DD format, e.g. '2026-07-29'.
        vendor_contact_id: Optional vendor contact ID to filter.
        min_days_overdue: Optional minimum days overdue filter.
    """
    parsed_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
    inp = ReviewUnpaidBillsInput(
        as_of_date=parsed_date,
        vendor_contact_id=vendor_contact_id,
        min_days_overdue=min_days_overdue,
    )
    db = _get_session()
    try:
        r = review_unpaid_bills(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 2: calculate_prepaid_adjustment --
@function_tool
def tool_calculate_prepaid_adjustment(as_of_date: str = "", prepaid_id: typing.Optional[str] = None) -> str:
    """Calculate monthly prepaid expense adjustments. No approval needed.

    Args:
        as_of_date: Date in YYYY-MM-DD format.
        prepaid_id: Optional specific prepaid ID to process.
    """
    parsed_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
    inp = CalculatePrepaidAdjustmentInput(as_of_date=parsed_date, prepaid_id=prepaid_id)
    db = _get_session()
    try:
        r = calculate_prepaid_adjustment(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 3: calculate_depreciation --
@function_tool
def tool_calculate_depreciation(period_date: str = "", asset_id: typing.Optional[str] = None) -> str:
    """Calculate monthly straight-line depreciation for fixed assets. No approval.

    Args:
        period_date: Period date YYYY-MM-DD.
        asset_id: Optional specific asset ID.
    """
    parsed_date = date.fromisoformat(period_date) if period_date else date.today()
    inp = CalculateDepreciationInput(period_date=parsed_date, asset_id=asset_id)
    db = _get_session()
    try:
        r = calculate_depreciation(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 4: calculate_amortization --
@function_tool
def tool_calculate_amortization(period_date: str = "", asset_id: typing.Optional[str] = None) -> str:
    """Calculate monthly straight-line amortization for intangible assets.

    Args:
        period_date: Period date YYYY-MM-DD.
        asset_id: Optional specific intangible asset ID.
    """
    parsed_date = date.fromisoformat(period_date) if period_date else date.today()
    inp = CalculateAmortizationInput(period_date=parsed_date, asset_id=asset_id)
    db = _get_session()
    try:
        r = calculate_amortization(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 5: reconcile_payroll --
@function_tool
def tool_reconcile_payroll(from_date: str, to_date: str, employee_name: typing.Optional[str] = None) -> str:
    """Reconcile payroll entries against GL salary expense.

    Args:
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        employee_name: Optional employee name filter.
    """
    inp = ReconcilePayrollInput(
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
        employee_name=employee_name,
    )
    db = _get_session()
    try:
        r = reconcile_payroll(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 6: get_ar_aging_report --
@function_tool
def tool_get_ar_aging_report(as_of_date: str = "", customer_contact_id: typing.Optional[str] = None) -> str:
    """Generate AR aging report - what customers owe us.

    Args:
        as_of_date: Date in YYYY-MM-DD format.
        customer_contact_id: Optional customer contact ID to filter.
    """
    parsed_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
    inp = GetARAgingReportInput(as_of_date=parsed_date, customer_contact_id=customer_contact_id)
    db = _get_session()
    try:
        r = get_ar_aging_report(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 7: get_ap_aging_report --
@function_tool
def tool_get_ap_aging_report(as_of_date: str = "", vendor_contact_id: typing.Optional[str] = None) -> str:
    """Generate AP aging report - what we owe vendors.

    Args:
        as_of_date: Date in YYYY-MM-DD format.
        vendor_contact_id: Optional vendor filter.
    """
    parsed_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
    inp = GetAPAgingReportInput(as_of_date=parsed_date, vendor_contact_id=vendor_contact_id)
    db = _get_session()
    try:
        r = get_ap_aging_report(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 8: analyze_budget_variance --
@function_tool
def tool_analyze_budget_variance(fiscal_year: int, period: int, account_code_prefix: typing.Optional[str] = None) -> str:
    """Analyze budget vs actual variance for a fiscal year and period.

    Args:
        fiscal_year: Fiscal year e.g. 2026.
        period: Period number 1-12.
        account_code_prefix: Optional account filter prefix.
    """
    inp = AnalyzeBudgetVarianceInput(
        fiscal_year=fiscal_year,
        period=period,
        account_code_prefix=account_code_prefix,
    )
    db = _get_session()
    try:
        r = analyze_budget_variance(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 9: get_loan_debt_schedule --
@function_tool
def tool_get_loan_debt_schedule(loan_id: str, as_of_date: typing.Optional[str] = None) -> str:
    """Get or compute loan/debt amortisation schedule.

    Args:
        loan_id: Loan ID e.g. 'LN-001'.
        as_of_date: Optional date in YYYY-MM-DD to filter future payments.
    """
    parsed_as_of = date.fromisoformat(as_of_date) if as_of_date else None
    inp = GetLoanDebtScheduleInput(loan_id=loan_id, as_of_date=parsed_as_of)
    db = _get_session()
    try:
        r = get_loan_debt_schedule(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 10: forecast_cash_flow --
@function_tool
def tool_forecast_cash_flow(forecast_days: int = 30, starting_balance: str = "0", as_of_date: typing.Optional[str] = None) -> str:
    """Forecast future cash flows from historical averages. Requires approval.

    Args:
        forecast_days: 30, 60, or 90 days.
        starting_balance: Starting cash balance as string.
        as_of_date: Optional base date in YYYY-MM-DD for forecast start.
    """
    parsed_as_of = date.fromisoformat(as_of_date) if as_of_date else None
    inp = ForecastCashFlowInput(
        forecast_days=forecast_days,
        starting_balance=Decimal(starting_balance),
        as_of_date=parsed_as_of,
    )
    db = _get_session()
    try:
        r = forecast_cash_flow(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# Create the Month-End Reporting Agent with all 10 tools
MONTH_END_AGENT = Agent(
    name="Month-End Reporting Agent",
    instructions="""You are the Month-End Reporting Agent for the AI Accountant.

You handle all month-end close tasks. You have 10 tools.

Available tools:
1. tool_review_unpaid_bills - Review unpaid bills/AP items as of a date.
2. tool_calculate_prepaid_adjustment - Calculate monthly prepaid expense adjustments.
3. tool_calculate_depreciation - Calculate monthly straight-line depreciation for fixed assets.
4. tool_calculate_amortization - Calculate monthly amortization for intangible assets.
5. tool_reconcile_payroll - Reconcile payroll entries against GL salary expense.
6. tool_get_ar_aging_report - Generate AR aging report (what customers owe).
7. tool_get_ap_aging_report - Generate AP aging report (what we owe vendors).
8. tool_analyze_budget_variance - Analyze budget vs actual variance.
9. tool_get_loan_debt_schedule - Get or compute loan amortisation schedule.
10. tool_forecast_cash_flow - Forecast future cash flows from historical averages (NEEDS APPROVAL).

Rules:
- ALWAYS call a tool to answer. Never just talk.
- For tool 10 (forecast_cash_flow): tell the user the projection and ask for approval.
- Pass dates in YYYY-MM-DD format.
- Explain results in plain English after tool calls.
""",
    tools=[
        tool_review_unpaid_bills, tool_calculate_prepaid_adjustment,
        tool_calculate_depreciation, tool_calculate_amortization,
        tool_reconcile_payroll, tool_get_ar_aging_report,
        tool_get_ap_aging_report, tool_analyze_budget_variance,
        tool_get_loan_debt_schedule, tool_forecast_cash_flow,
    ],
    model=GROQ_MODEL,
)


async def run_month_end_agent(user_request: str) -> str:
    """Run the Month-End Reporting Agent with a user request.

    Groq primary -> Groq fallback -> Cerebras last resort.
    """
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (CEREBRAS_MODEL, create_cerebras_provider, "Cerebras"),
    ]:
        try:
            agent = MONTH_END_AGENT if attempt_model == GROQ_MODEL else Agent(
                name="Month-End Reporting Agent",
                instructions=MONTH_END_AGENT.instructions,
                tools=MONTH_END_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(agent, input=user_request, run_config=RunConfig(model_provider=provider_fn()))
            return result.final_output
        except Exception:
            last_error = f"{label}: failure"
    return f"Error: All providers unavailable.\n{last_error}"
