"""Agent 7 (Cost & Budgeting) routing + slot-fill + formatter tests.

Covers the three bugs fixed for Agent 7:
  1. prepare_budget_forecast returned "Report generated: None -" (no dedicated
     formatter) -> now has _fmt_budget_forecast.
  2. calculate_standard_costing_variance was misrouted to analyze_budget_variance
     because the bare "variance" keyword preceded the "standard costing" route.
  3. The 4 approval tools failed on approve with "Field required" because the
     router produced only {"fiscal_year": ...} and none were slot-filled.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intent_router import (
    route_tool,
    _params_standard_costing,
    _params_overhead,
    _params_revenue_recognition,
    _params_provision,
    _params_related_party,
)
from result_formatter import format_tool_result
from slot_fill import describe_missing, is_complete, WRITE_TOOLS, PENDING_INTENTS


def test_standard_costing_routes_to_itself():
    msg = "calculate standard costing variance for account 6000 period 7 fiscal year 2026 with standard cost 50000"
    tool, params = route_tool(msg)
    assert tool == "calculate_standard_costing_variance", f"got {tool}"
    assert params["account_code"] == "6000"
    assert params["period"] == 7
    assert params["fiscal_year"] == 2026
    assert params["standard_cost"] == "50000"


def test_standard_costing_parser_full():
    p = _params_standard_costing(
        "cost variance for account 6000, standard 50000 for period 7"
    )
    assert p["account_code"] == "6000"
    assert p["standard_cost"] == "50000"
    assert p["period"] == 7


def test_budget_variance_still_routes():
    tool, _ = route_tool("analyze budget variance for July 2026")
    assert tool == "analyze_budget_variance"


def test_budget_forecast_formatter():
    result = {
        "fiscal_year": 2026,
        "periods": 12,
        "data_months": 12,
        "total_forecast": "1250000.00",
        "confidence": "medium",
        "forecast_items": [
            {"account_code": "4000", "account_name": "Revenue", "forecast_amount": "1000000.00", "basis": "3m avg"},
            {"account_code": "6000", "account_name": "Office Rent", "forecast_amount": "250000.00", "basis": "inflation"},
        ],
    }
    out = format_tool_result("prepare_budget_forecast", result)
    assert "Report generated" not in out
    assert "Budget forecast for FY 2026" in out
    assert "PKR 1,250,000" in out
    assert "Office Rent" in out


def test_overhead_parser():
    p = _params_overhead(
        "allocate 100000 overhead by revenue to sales 2000, hr 1500, production 3000 for period 7 fiscal year 2026"
    )
    assert p["total_overhead"] == "100000"
    assert p["allocation_basis"] == "revenue_pct"
    assert p["period"] == 7
    assert p["fiscal_year"] == 2026
    names = {i["name"] for i in p["allocation_pool"]}
    assert names == {"sales", "hr", "production"}
    vals = [i["value"] for i in p["allocation_pool"]]
    assert vals == ["2000", "1500", "3000"]


def test_overhead_headcount_parser():
    p = _params_overhead("allocate 50000 by headcount to engineering 25 support 15 sales 10 for period 3 2026")
    assert p["allocation_basis"] == "headcount"
    names = {i["name"] for i in p["allocation_pool"]}
    assert names == {"engineering", "support", "sales"}


def test_revenue_recognition_parser():
    p = _params_revenue_recognition(
        "recognize revenue for contract CON-001 value 500000 at 60% completion for period 7 fiscal year 2026"
    )
    assert p["contract_id"] == "CON-001"
    assert p["contract_value"] == "500000"
    assert p["completion_percentage"] == 60
    assert p["period"] == 7
    assert p["fiscal_year"] == 2026


def test_provision_parser():
    p = _params_provision("flag a probable provision of 200000 for an ongoing lawsuit in fiscal year 2026")
    assert p["estimated_amount"] == "200000"
    assert p["probability"] == "probable"
    assert p["fiscal_year"] == 2026
    assert "lawsuit" in p["description"]


def test_related_party_parser():
    p = _params_related_party("flag JE-20260715-001 of 500000 paid to ABC Trading as a related party in fiscal year 2026")
    assert p["entry_id"] == "JE-20260715-001"
    assert p["amount"] == "500000"
    assert p["counterparty_name"] == "ABC Trading"
    assert p["fiscal_year"] == 2026


def test_cost_tools_in_write_tools():
    for t in (
        "calculate_standard_costing_variance",
        "allocate_overhead_cost",
        "calculate_revenue_recognition",
        "flag_provision_contingent_liability",
        "flag_related_party_transaction",
    ):
        assert t in WRITE_TOOLS, t


def test_slot_fill_missing():
    PENDING_INTENTS.clear()
    # Standard costing with only the account code -> asks for period + cost.
    q = describe_missing("calculate_standard_costing_variance", {"account_code": "6000"})
    assert q and "period" in q
    assert not is_complete("calculate_standard_costing_variance", {"account_code": "6000"})
    assert is_complete(
        "calculate_standard_costing_variance",
        {"account_code": "6000", "period": 7, "fiscal_year": 2026, "standard_cost": "50000"},
    )
    # Overhead missing the pool.
    q = describe_missing(
        "allocate_overhead_cost",
        {"total_overhead": "100000", "allocation_basis": "revenue_pct", "period": 7, "fiscal_year": 2026},
    )
    assert q and "departments" in q
    # Provision missing probability.
    q = describe_missing("flag_provision_contingent_liability", {"estimated_amount": "200000"})
    assert q and "probability" in q


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
