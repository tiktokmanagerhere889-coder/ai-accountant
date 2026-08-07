"""Agent 10 (System Admin) routing + slot-fill + formatter tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intent_router import route_tool, _params_system_preferences, _params_system_task, is_approval_required
from result_formatter import format_tool_result, has_dedicated_formatter
from slot_fill import describe_missing, is_complete, WRITE_TOOLS, PENDING_INTENTS


def test_check_status_routes():
    tool, params = route_tool("check system status")
    assert tool == "check_system_status", f"got {tool}"


def test_usage_stats_routes_with_dates():
    tool, params = route_tool("show usage statistics for last month")
    assert tool == "get_usage_statistics", f"got {tool}"
    assert params.get("from_date") and params.get("to_date")


def test_prefs_view_routes():
    tool, params = route_tool("show company settings")
    assert tool == "manage_system_preferences", f"got {tool}"
    assert params["action"] == "view"


def test_prefs_update_routes():
    tool, params = route_tool("change company name to ABC Corp")
    assert tool == "manage_system_preferences", f"got {tool}"
    assert params["action"] == "update"
    assert params.get("settings")
    # value keeps its case ('ABC Corp', not 'abc corp')
    assert params["settings"]["company_name"] == "ABC Corp"


def test_prefs_view_exempt_from_approval():
    """view is read-only - must not be queued for approval."""
    assert is_approval_required("manage_system_preferences", {"action": "view"}) is False
    assert is_approval_required("manage_system_preferences", {"action": "update", "settings": {"x": "y"}}) is True
    assert is_approval_required("manage_system_preferences") is True  # no params -> approval set default


def test_prefs_reset_routes():
    tool, params = route_tool("reset retention_days")
    assert tool == "manage_system_preferences", f"got {tool}"
    assert params["action"] == "reset"
    assert params.get("setting_key")


def test_task_backup_routes():
    tool, params = route_tool("schedule a database backup")
    assert tool == "schedule_system_task", f"got {tool}"
    assert params["task_type"] == "backup"


def test_task_maintenance_routes():
    tool, params = route_tool("schedule system maintenance")
    assert tool == "schedule_system_task", f"got {tool}"
    assert params["task_type"] == "maintenance"


def test_task_off_peak():
    tool, params = route_tool("schedule a backup off peak")
    assert tool == "schedule_system_task"
    assert params["schedule_time"] == "off_peak"


def test_approval_tools():
    assert is_approval_required("manage_system_preferences")
    assert is_approval_required("schedule_system_task")
    assert not is_approval_required("check_system_status")
    assert not is_approval_required("get_usage_statistics")


def test_write_tools():
    assert "manage_system_preferences" in WRITE_TOOLS
    assert "schedule_system_task" in WRITE_TOOLS


def test_prefs_update_slot_fill_asks():
    q = describe_missing("manage_system_preferences", {"action": "update", "settings": None})
    assert q and "setting" in q.lower()


def test_prefs_update_complete():
    assert not is_complete("manage_system_preferences", {"action": "update"})
    assert is_complete("manage_system_preferences", {"action": "update", "settings": {"company_name": "ABC Corp"}})
    assert is_complete("manage_system_preferences", {"action": "view"})


def test_task_slot_fill_complete():
    assert is_complete("schedule_system_task", {"task_type": "backup"})


def test_formatters_registered():
    for t in ("check_system_status", "get_usage_statistics", "manage_system_preferences", "schedule_system_task"):
        assert has_dedicated_formatter(t), f"{t} missing formatter"


def test_status_formatter():
    out = format_tool_result("check_system_status", {
        "overall_status": "healthy",
        "checks": [
            {"name": "database", "status": "healthy", "detail": "PostgreSQL connection OK", "latency_ms": 5},
            {"name": "providers", "status": "degraded", "detail": "Groq: configured; Gemini: not configured", "latency_ms": 0},
        ],
        "summary": "System status: HEALTHY. 1/2 checks passed.",
    })
    assert "HEALTHY" in out
    assert "database" in out
    assert "5ms" in out


def test_usage_formatter():
    out = format_tool_result("get_usage_statistics", {
        "period": "2026-07-01 to 2026-07-31",
        "total_requests": 10, "success_count": 8, "failure_count": 2,
        "breakdown": [{"dimension": "backup", "requests": 10, "successes": 8, "failures": 2}],
        "recommendations": ["High failure rate detected - review system configuration."],
    })
    assert "10 operations" in out
    assert "backup" in out
    assert "High failure rate" in out


def test_prefs_formatter():
    out = format_tool_result("manage_system_preferences", {
        "action_performed": "view",
        "settings": {"company_name": "My Company", "default_currency": "PKR"},
        "changed_keys": [],
        "message": "Retrieved 2 setting(s).",
    })
    assert "company_name" in out
    assert "My Company" in out


def test_task_formatter():
    out = format_tool_result("schedule_system_task", {
        "task_id": "TASK-A1B2C3D4", "task_type": "backup",
        "status": "scheduled", "scheduled_for": "now",
        "estimated_completion": "2 minutes",
    })
    assert "TASK-A1B2C3D4" in out
    assert "2 minutes" in out


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
