"""Tax Agent - wraps 8 tools as an OpenAI Agent."""
import sys, os, json, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import init_db, get_session
from tools.schemas import (
    CalculateWithholdingTaxInput, CalculateWithholdingTaxOutput,
    GetTaxPlanningAdviceInput, GetTaxPlanningAdviceOutput,
    CalculateAdvanceMinimumTaxInput, CalculateAdvanceMinimumTaxOutput,
    CalculateEobiDeductionsInput, CalculateEobiDeductionsOutput,
    AdjustSalesTaxInputOutputInput, AdjustSalesTaxInputOutputOutput,
    FlagTaxExemptionZeroRatingInput, FlagTaxExemptionZeroRatingOutput,
    PrepareSalesTaxFilingInput, PrepareSalesTaxFilingOutput,
    PrepareIncomeTaxFilingInput, PrepareIncomeTaxFilingOutput,
)
from tools.tax_tools import (
    calculate_withholding_tax, get_tax_planning_advice,
    calculate_advance_minimum_tax, calculate_eobi_deductions,
    adjust_sales_tax_input_output, flag_tax_exemption_zero_rating,
    prepare_sales_tax_filing, prepare_income_tax_filing,
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


# -- Tool 1: calculate_withholding_tax --
@function_tool
def tool_calculate_withholding_tax(amount: str, withholding_type: str, transaction_date: str = "") -> str:
    """Calculate withholding tax (WHT) on a payment. Rate from tax_rates table or default.

    Args:
        amount: Gross payment amount as string (e.g., '50000').
        withholding_type: 'salary', 'contract', 'supply', 'service', 'rent', 'commission'.
        transaction_date: Date in YYYY-MM-DD format. Defaults to today.
    """
    parsed_date = date.fromisoformat(transaction_date) if transaction_date else date.today()
    inp = CalculateWithholdingTaxInput(
        amount=Decimal(amount),
        withholding_type=withholding_type.lower(),
        transaction_date=parsed_date,
    )
    db = _get_session()
    try:
        r = calculate_withholding_tax(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 2: get_tax_planning_advice --
@function_tool
def tool_get_tax_planning_advice(query: str, fiscal_year: int) -> str:
    """Get tax planning advice based on financial data for a fiscal year.

    Args:
        query: Tax planning question.
        fiscal_year: Fiscal year (e.g., 2026).
    """
    inp = GetTaxPlanningAdviceInput(query=query, fiscal_year=fiscal_year)
    db = _get_session()
    try:
        r = get_tax_planning_advice(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 3: calculate_advance_minimum_tax --
@function_tool
def tool_calculate_advance_minimum_tax(annual_turnover: str, fiscal_year: int, business_type: str = "company") -> str:
    """Calculate advance minimum tax (AMT) on turnover.

    Args:
        annual_turnover: Annual turnover as string (e.g., '10000000').
        fiscal_year: Fiscal year.
        business_type: 'company', 'individual', or 'aop'. Default 'company'.
    """
    inp = CalculateAdvanceMinimumTaxInput(
        annual_turnover=Decimal(annual_turnover),
        fiscal_year=fiscal_year,
        business_type=business_type.lower(),
    )
    db = _get_session()
    try:
        r = calculate_advance_minimum_tax(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 4: calculate_eobi_deductions --
@function_tool
def tool_calculate_eobi_deductions(gross_salary: str, period: int, fiscal_year: int, employee_category: str = "") -> str:
    """Calculate EOBI (social security) deductions on salary.

    Args:
        gross_salary: Gross salary amount as string.
        period: Period 1-12.
        fiscal_year: Fiscal year.
        employee_category: Optional category 'worker', 'staff', 'executive'.
    """
    cat = employee_category if employee_category else None
    inp = CalculateEobiDeductionsInput(
        gross_salary=Decimal(gross_salary),
        period=period,
        fiscal_year=fiscal_year,
        employee_category=cat,
    )
    db = _get_session()
    try:
        r = calculate_eobi_deductions(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 5: adjust_sales_tax_input_output --
@function_tool
def tool_adjust_sales_tax_input_output(period: int, fiscal_year: int, output_tax_amount: str = "", input_tax_amount: str = "", adjustment_reason: str = "") -> str:
    """Adjust sales tax input vs output. Requires approval.

    Args:
        period: Period 1-12.
        fiscal_year: Fiscal year.
        output_tax_amount: Override output tax as string (optional).
        input_tax_amount: Override input tax as string (optional).
        adjustment_reason: Reason for adjustment (optional).
    """
    out_tax = Decimal(output_tax_amount) if output_tax_amount else None
    in_tax = Decimal(input_tax_amount) if input_tax_amount else None
    reason = adjustment_reason if adjustment_reason else None
    inp = AdjustSalesTaxInputOutputInput(
        period=period, fiscal_year=fiscal_year,
        output_tax_amount=out_tax, input_tax_amount=in_tax,
        adjustment_reason=reason,
    )
    db = _get_session()
    try:
        r = adjust_sales_tax_input_output(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 6: flag_tax_exemption_zero_rating --
@function_tool
def tool_flag_tax_exemption_zero_rating(fiscal_year: int, entry_ids: str = "", period: int = 0) -> str:
    """Flag potentially tax-exempt or zero-rated transactions. Requires approval.

    Args:
        fiscal_year: Fiscal year.
        entry_ids: Optional comma-separated entry IDs.
        period: Optional period 1-12.
    """
    ids = [e.strip() for e in entry_ids.split(",") if e.strip()] if entry_ids else None
    per = period if period > 0 else None
    inp = FlagTaxExemptionZeroRatingInput(
        entry_ids=ids, fiscal_year=fiscal_year, period=per,
    )
    db = _get_session()
    try:
        r = flag_tax_exemption_zero_rating(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 7: prepare_sales_tax_filing --
@function_tool
def tool_prepare_sales_tax_filing(period: int, fiscal_year: int, confirm: bool = False) -> str:
    """Prepare sales tax filing data for FBR. Requires confirm=True and approval.

    Args:
        period: Period 1-12.
        fiscal_year: Fiscal year.
        confirm: Must be True to proceed.
    """
    inp = PrepareSalesTaxFilingInput(period=period, fiscal_year=fiscal_year, confirm=confirm)
    db = _get_session()
    try:
        r = prepare_sales_tax_filing(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 8: prepare_income_tax_filing --
@function_tool
def tool_prepare_income_tax_filing(fiscal_year: int, confirm: bool = False) -> str:
    """Prepare income tax filing data for FBR. Requires confirm=True and approval.

    Args:
        fiscal_year: Fiscal year.
        confirm: Must be True to proceed.
    """
    inp = PrepareIncomeTaxFilingInput(fiscal_year=fiscal_year, confirm=confirm)
    db = _get_session()
    try:
        r = prepare_income_tax_filing(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


TAX_AGENT = Agent(
    name="Tax Agent",
    instructions="""You are the Tax Agent for the AI Accountant.

You handle all tax calculation and filing-preparation tasks. You have 8 tools.

Available tools:
1. tool_calculate_withholding_tax - WHT calculation (no approval).
2. tool_get_tax_planning_advice - Tax planning guidance from data (no approval).
3. tool_calculate_advance_minimum_tax - AMT on turnover (no approval).
4. tool_calculate_eobi_deductions - EOBI payroll deductions (no approval).
5. tool_adjust_sales_tax_input_output - Sales tax input/output adjustment (REQUIRES APPROVAL).
6. tool_flag_tax_exemption_zero_rating - Flag exempt/zero-rated entries (REQUIRES APPROVAL).
7. tool_prepare_sales_tax_filing - Prepare FBR sales tax filing (REQUIRES confirm=True + APPROVAL).
8. tool_prepare_income_tax_filing - Prepare FBR income tax filing (REQUIRES confirm=True + APPROVAL).

Rules:
- Greetings, chit-chat, or general questions ('hi', 'hello', 'how are you',
  'what can you do', 'thanks'): answer conversationally. Do NOT call any tool.
- Call a tool ONLY when the user asks for specific accounting work (cash balance,
  record expense, reports, etc.).
- For tools 5-8: tell the user these require approval.
- For tools 7-8 (filing): warn confirm=True is needed and data is for human submission only.
- Pass amounts as string numbers (e.g., '50000' not 50000).
- Pass dates in YYYY-MM-DD format.
- Explain results in plain English after tool calls.
""",
    tools=[
        tool_calculate_withholding_tax, tool_get_tax_planning_advice,
        tool_calculate_advance_minimum_tax, tool_calculate_eobi_deductions,
        tool_adjust_sales_tax_input_output, tool_flag_tax_exemption_zero_rating,
        tool_prepare_sales_tax_filing, tool_prepare_income_tax_filing,
    ],
    model=GROQ_MODEL,
)


async def run_tax_agent(user_request: str) -> str:
    """Run the Tax Agent. Groq -> Groq fallback -> Gemini."""
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (GEMINI_MODEL, create_gemini_provider, "Gemini"),
    ]:
        try:
            agent = TAX_AGENT if attempt_model == GROQ_MODEL else Agent(
                name="Tax Agent",
                instructions=TAX_AGENT.instructions,
                tools=TAX_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(agent, input=user_request, run_config=RunConfig(model_provider=provider_fn()))
            return result.final_output
        except Exception:
            last_error = f"{label}: failure"
    return f"Error: All providers unavailable.\n{last_error}"
