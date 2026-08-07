"""Agent 9 (Advisory) formatter + routing regression tests."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intent_router import route_tool
from result_formatter import format_tool_result, has_dedicated_formatter


def test_cost_cutting_routes_with_year():
    tool, params = route_tool("give me cost cutting ideas for 2026")
    assert tool == "generate_cost_cutting_recommendations", f"got {tool}"
    assert params["fiscal_year"] == 2026


def test_spending_routes():
    tool, params = route_tool("show my spending patterns for Q2 2026")
    assert tool == "analyze_spending_patterns", f"got {tool}"


def test_ratios_routes():
    tool, params = route_tool("calculate financial ratios for FY 2026")
    assert tool == "calculate_financial_ratios", f"got {tool}"
    assert params["fiscal_year"] == 2026


def test_health_routes():
    tool, params = route_tool("assess financial health for 2026")
    assert tool == "assess_financial_health", f"got {tool}"
    assert params["fiscal_year"] == 2026


def test_custom_report_routes_and_approval():
    tool, params = route_tool("generate a custom management report for 2026")
    assert tool == "generate_custom_report", f"got {tool}"
    assert params["report_title"]
    assert params["fiscal_year"] == 2026
    assert params["report_type"]
    from intent_router import is_approval_required
    assert is_approval_required("generate_custom_report")


def test_cost_cutting_has_formatter():
    assert has_dedicated_formatter("generate_cost_cutting_recommendations")


def test_health_formatter_rich():
    out = format_tool_result("assess_financial_health", {
        "health_assessment": "moderate", "score": 72,
        "key_metrics": [{"name": "Net profit margin", "value": "4%", "rating": "weak"}],
        "strengths": ["Liquidity 2.1"],
        "weaknesses": ["Profitability 4%"],
        "recommendations": ["Cut discretionary spend"],
    })
    assert "72/100" in out
    assert "Strengths" in out
    assert "Cut discretionary spend" in out


def test_cost_cutting_formatter_rich():
    out = format_tool_result("generate_cost_cutting_recommendations", {
        "fiscal_year": 2026, "total_expenses": 650000,
        "top_expense_categories": [{"name": "COGS", "amount": 200000, "percentage": 31, "count": 12}],
        "recommendations": [{
            "area": "COGS", "current_spend": 200000, "potential_savings": 20000,
            "suggestion": "Negotiate supplier contracts", "priority": "high",
        }],
        "estimated_total_savings": 27500,
    })
    assert "COGS" in out
    assert "Negotiate supplier contracts" in out
    assert "27,500" in out


def test_ratios_formatter():
    out = format_tool_result("calculate_financial_ratios", {
        "fiscal_year": 2026,
        "ratios": [{"name": "Current Ratio", "value": "1.8", "interpretation": "healthy"}],
    })
    assert "Current Ratio" in out
    assert "1.8" in out


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
