"""Advisory Agent - wraps 5 tools as an OpenAI Agent."""
import sys, os, json, typing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal

from agents import Agent, function_tool, Runner
from agents.run_config import RunConfig

from db.database import init_db, get_session
from tools.schemas import (
    AnalyzeSpendingPatternsInput, AnalyzeSpendingPatternsOutput,
    CalculateFinancialRatiosInput, CalculateFinancialRatiosOutput,
    AssessFinancialHealthInput, AssessFinancialHealthOutput,
    GenerateCostCuttingInput, GenerateCostCuttingOutput,
    GenerateCustomReportInput, GenerateCustomReportOutput,
)
from tools.advisory_tools import (
    analyze_spending_patterns, calculate_financial_ratios,
    assess_financial_health, generate_cost_cutting_recommendations,
    generate_custom_report,
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


# -- Tool 1: analyze_spending_patterns --
@function_tool
def tool_analyze_spending_patterns(from_date: str, to_date: str, account_prefixes: str = "", description_keyword: str = "") -> str:
    """Analyze expense patterns over a date range. Groups by account category. No approval needed.

    Args:
        from_date: Start date YYYY-MM-DD.
        to_date: End date YYYY-MM-DD.
        account_prefixes: Optional comma-separated prefixes to filter (e.g., '5,6,8').
        description_keyword: Optional keyword to filter by description.
    """
    prefixes = [p.strip() for p in account_prefixes.split(",") if p.strip()] if account_prefixes else None
    kw = description_keyword if description_keyword else None
    inp = AnalyzeSpendingPatternsInput(
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
        account_prefixes=prefixes,
        description_keyword=kw,
    )
    db = _get_session()
    try:
        r = analyze_spending_patterns(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 2: calculate_financial_ratios --
@function_tool
def tool_calculate_financial_ratios(fiscal_year: int, period: int = 0, ratio_types: str = "") -> str:
    """Calculate standard financial ratios. No approval needed.

    Args:
        fiscal_year: Fiscal year (e.g., 2026).
        period: Optional month 1-12. 0 = full year.
        ratio_types: Optional comma-separated: liquidity, profitability, leverage, efficiency.
    """
    types = [t.strip() for t in ratio_types.split(",") if t.strip()] if ratio_types else None
    inp = CalculateFinancialRatiosInput(
        fiscal_year=fiscal_year,
        period=period if period > 0 else None,
        ratio_types=types,
    )
    db = _get_session()
    try:
        r = calculate_financial_ratios(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 3: assess_financial_health --
@function_tool
def tool_assess_financial_health(fiscal_year: int, period: int = 0) -> str:
    """Assess overall financial health with a weighted score. No approval needed.

    Args:
        fiscal_year: Fiscal year (e.g., 2026).
        period: Optional month 1-12. 0 = full year.
    """
    inp = AssessFinancialHealthInput(
        fiscal_year=fiscal_year,
        period=period if period > 0 else None,
    )
    db = _get_session()
    try:
        r = assess_financial_health(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 4: generate_cost_cutting_recommendations --
@function_tool
def tool_generate_cost_cutting_recommendations(fiscal_year: int, period: int = 0, target_account_prefixes: str = "", min_savings_threshold: str = "") -> str:
    """Identify cost-cutting opportunities. No approval needed.

    Args:
        fiscal_year: Fiscal year (e.g., 2026).
        period: Optional month 1-12. 0 = full year.
        target_account_prefixes: Optional comma-separated expense prefixes (e.g., '6,8').
        min_savings_threshold: Minimum savings as string to recommend.
    """
    prefixes = [p.strip() for p in target_account_prefixes.split(",") if p.strip()] if target_account_prefixes else None
    threshold = Decimal(min_savings_threshold) if min_savings_threshold else None
    inp = GenerateCostCuttingInput(
        fiscal_year=fiscal_year,
        period=period if period > 0 else None,
        target_account_prefixes=prefixes,
        min_savings_threshold=threshold,
    )
    db = _get_session()
    try:
        r = generate_cost_cutting_recommendations(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


# -- Tool 5: generate_custom_report --
@function_tool
def tool_generate_custom_report(report_title: str, fiscal_year: int, report_type: str, period_from: int = 0, period_to: int = 0, include_sections: str = "", notes: str = "") -> str:
    """Generate a structured financial report. REQUIRES APPROVAL.

    Args:
        report_title: Title for the report.
        fiscal_year: Fiscal year.
        report_type: summary, detailed, comparative, trend.
        period_from: Start month 1-12. 0 = first month.
        period_to: End month 1-12. 0 = last month.
        include_sections: Optional comma-separated: revenue, expenses, ratios, budget_variance, trends.
        notes: Optional additional notes.
    """
    pf = period_from if period_from > 0 else None
    pt = period_to if period_to > 0 else None
    sections = [s.strip() for s in include_sections.split(",") if s.strip()] if include_sections else None
    n = notes if notes else None
    inp = GenerateCustomReportInput(
        report_title=report_title,
        fiscal_year=fiscal_year,
        period_from=pf,
        period_to=pt,
        report_type=report_type.lower().strip(),
        include_sections=sections,
        notes=n,
    )
    db = _get_session()
    try:
        r = generate_custom_report(inp, db)
        return _to_json(r)
    except ValueError as e:
        return f"Error: {e}"
    finally:
        db.close()


ADVISORY_AGENT = Agent(
    name="Advisory Agent",
    instructions="""You are the Advisory Agent for the AI Accountant.

You handle financial analysis, health assessment, cost-cutting ideas, and custom reports. You have 5 tools.

Available tools:
1. tool_analyze_spending_patterns - Analyze expense patterns, grouped by category (no approval).
2. tool_calculate_financial_ratios - Compute liquidity/profitability/leverage/efficiency ratios (no approval).
3. tool_assess_financial_health - Weighted health score 0-100 with strengths/weaknesses (no approval).
4. tool_generate_cost_cutting_recommendations - Identify savings opportunities (no approval).
5. tool_generate_custom_report - Build structured reports (REQUIRES APPROVAL).

Rules:
- Greetings, chit-chat, or general questions ('hi', 'hello', 'how are you',
  'what can you do', 'thanks'): answer conversationally. Do NOT call any tool.
- Call a tool ONLY when the user asks for specific accounting work (cash balance,
  record expense, reports, etc.).
- For tool 5: tell the user it requires approval before generating.
- Pass dates in YYYY-MM-DD format.
- Pass amounts as string numbers (e.g., '500000').
- Explain results in plain English after tool calls.
""",
    tools=[
        tool_analyze_spending_patterns,
        tool_calculate_financial_ratios,
        tool_assess_financial_health,
        tool_generate_cost_cutting_recommendations,
        tool_generate_custom_report,
    ],
    model=GROQ_MODEL,
)


async def run_advisory_agent(user_request: str) -> str:
    """Run the Advisory Agent. Groq -> Groq fallback -> Gemini."""
    for attempt_model, provider_fn, label in [
        (GROQ_MODEL, create_groq_provider, "Groq"),
        (GROQ_FALLBACK_MODEL, create_groq_provider, "Groq fallback"),
        (GEMINI_MODEL, create_gemini_provider, "Gemini"),
    ]:
        try:
            agent = ADVISORY_AGENT if attempt_model == GROQ_MODEL else Agent(
                name="Advisory Agent",
                instructions=ADVISORY_AGENT.instructions,
                tools=ADVISORY_AGENT.tools,
                model=attempt_model,
            )
            result = await Runner.run(agent, input=user_request, run_config=RunConfig(model_provider=provider_fn()))
            return result.final_output
        except Exception:
            last_error = f"{label}: failure"
    return f"Error: All providers unavailable.\n{last_error}"
