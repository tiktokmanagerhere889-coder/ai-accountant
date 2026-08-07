"""Agent 8 (Audit & Registers) routing + slot-fill + formatter tests."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intent_router import route_tool, _params_statutory_registers
from result_formatter import format_tool_result
from slot_fill import describe_missing, is_complete, WRITE_TOOLS, PENDING_INTENTS


def test_anomaly_routes_with_month_range():
    tool, params = route_tool("detect anomalies in July 2026")
    assert tool == "detect_anomaly_transactions", f"got {tool}"
    assert params["from_date"] == date(2026, 7, 1)
    assert params["to_date"] == date(2026, 7, 31)


def test_fraud_routes_to_anomaly():
    tool, params = route_tool("detect fraud transactions this month")
    assert tool == "detect_anomaly_transactions"
    assert params["from_date"] == params["to_date"].replace(day=1)


def test_compliance_routes():
    tool, params = route_tool("show upcoming compliance deadlines")
    assert tool == "get_compliance_deadlines"


def test_internal_audit_routes():
    tool, params = route_tool("run internal audit for FY 2026")
    assert tool == "support_internal_audit"
    assert params["fiscal_year"] == 2026


def test_statutory_add_routes():
    msg = "add director register entry: Ali Khan appointed 2026-07-01, reference DIR-001"
    tool, params = route_tool(msg)
    assert tool == "maintain_statutory_registers", f"got {tool}"
    assert params["action"] == "add"
    assert params["register_type"] == "directors"
    assert params["entry_date"] == date(2026, 7, 1)
    assert params["reference_number"] == "DIR-001"


def test_statutory_view_routes():
    tool, params = route_tool("show the register of directors")
    assert tool == "maintain_statutory_registers"
    assert params["action"] == "view"
    assert params["register_type"] == "directors"


def test_statutory_delete_captures_register_id():
    tool, params = route_tool("delete register entry REG-CHG-A1B2C3D4 from the charges register")
    assert tool == "maintain_statutory_registers"
    assert params["action"] == "delete"
    assert params["register_id"] == "REG-CHG-A1B2C3D4"


def test_statutory_in_write_tools():
    assert "maintain_statutory_registers" in WRITE_TOOLS


def test_statutory_slot_fill_missing_register_type():
    PENDING_INTENTS.clear()
    q = describe_missing("maintain_statutory_registers", {"action": "add", "entry_date": date(2026, 7, 1)})
    assert q and "register type" in q
    assert not is_complete("maintain_statutory_registers", {"action": "add", "entry_date": date(2026, 7, 1)})
    assert is_complete(
        "maintain_statutory_registers",
        {"action": "view", "register_type": "directors", "entry_date": date(2026, 7, 1)},
    )


def test_statutory_delete_requires_register_id():
    assert not is_complete(
        "maintain_statutory_registers",
        {"action": "delete", "register_type": "charges", "entry_date": date(2026, 7, 1)},
    )
    assert is_complete(
        "maintain_statutory_registers",
        {"action": "delete", "register_id": "REG-CHG-A1B2C3D4", "register_type": "charges", "entry_date": date(2026, 7, 1)},
    )


def test_compliance_formatter():
    result = {
        "deadlines": [
            {"deadline_id": "D1", "deadline_type": "tax_filing", "description": "Q3 Sales Tax", "due_date": "2026-07-20", "days_remaining": -3, "status": "upcoming"},
            {"deadline_id": "D2", "deadline_type": "audit", "description": "Annual audit", "due_date": "2026-11-30", "days_remaining": 90, "status": "upcoming"},
        ],
        "overdue_count": 1,
        "upcoming_count": 1,
        "summary": "1 overdue, 1 upcoming compliance deadline(s).",
    }
    out = format_tool_result("get_compliance_deadlines", result)
    assert "overdue" in out
    assert "Q3 Sales Tax" in out
    assert "Annual audit" in out


def test_audit_formatter():
    result = {
        "audit_id": "AUD-ABC123",
        "total_flagged": 2,
        "flagged_entries": [
            {"entry_id": "JE-1", "description": "x", "amount": "500000", "flag_type": "round_amount", "reason": "round", "severity": "medium", "status": "open"},
            {"entry_id": "JE-2", "description": "y", "amount": "30000", "flag_type": "missing_reference", "reason": "no ref", "severity": "medium", "status": "open"},
        ],
        "summary": "Audit complete. Found 2 issue(s).",
    }
    out = format_tool_result("support_internal_audit", result)
    assert "AUD-ABC123" in out
    assert "round_amount" in out
    assert "2 issue(s)" in out


def test_statutory_formatter_add():
    result = {
        "register_id": "REG-DIR-A1B2C3D4", "action_performed": "add", "register_type": "directors",
        "entry_date": "2026-07-01", "description": "Ali Khan appointed", "reference_number": "DIR-001",
        "amount": "0", "status": "pending_approval", "message": "Register entry added. Requires approval.",
    }
    out = format_tool_result("maintain_statutory_registers", result)
    assert "add" in out
    assert "Ali Khan appointed" in out


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
