"""Integration test for the approval queue flow. Run: python tests/test_approval_flow.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def run_test(label: str, fn):
    try:
        fn()
        print(f"PASS: {label}")
    except Exception as e:
        print(f"FAIL: {label} -> {e}")
        raise


def test_non_approval_tool_executes_directly():
    r = client.post("/tools/execute", json={"tool_name": "check_cash_position", "params": {}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body
    assert not body.get("result", {}).get("queued"), body
    print("  (non-approval tool executed directly, not queued)")


def test_approval_tool_queued():
    r = client.post(
        "/tools/execute",
        json={
            "tool_name": "schedule_system_task",
            "params": {"task_type": "backup", "schedule_time": "now", "notes": "test queue"},
            "needs_approval": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body
    assert body["result"]["queued"] is True, body
    assert body["result"]["approval_id"], body
    global QUEUED_ID
    QUEUED_ID = body["result"]["approval_id"]
    print(f"  queued as {QUEUED_ID}")


def test_approval_tool_queued_even_without_flag():
    # In APPROVAL_REQUIRED_TOOLS -> queued even if frontend omits the flag
    r = client.post(
        "/tools/execute",
        json={"tool_name": "forecast_cash_flow", "params": {"days": 30}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["queued"] is True, body
    global FORECAST_ID
    FORECAST_ID = body["result"]["approval_id"]
    print(f"  forecast_cash_flow queued without flag as {FORECAST_ID}")


def test_pending_list():
    r = client.get("/approvals/pending")
    assert r.status_code == 200, r.text
    approvals = r.json()["approvals"]
    ids = [a["approval_id"] for a in approvals]
    assert QUEUED_ID in ids, f"{QUEUED_ID} not in {ids}"
    assert FORECAST_ID in ids
    print(f"  pending list has {len(approvals)} entries")


def test_approve_without_edits():
    r = client.post(f"/approvals/{QUEUED_ID}/approve", json={"edited_params": None})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approval"]["status"] == "approved", body
    assert body["result"] is not None, body
    print(f"  approved, result keys: {list(body['result'].keys())[:5]}")


def test_approve_with_edited_params():
    r = client.post(
        "/tools/execute",
        json={
            "tool_name": "manage_system_preferences",
            "params": {"action": "view"},
            "needs_approval": True,
        },
    )
    aid = r.json()["result"]["approval_id"]
    # Edit params to an update action
    edited = {"action": "update", "settings": {"backup_enabled": "false"}, "setting_key": None, "value": None}
    r2 = client.post(f"/approvals/{aid}/approve", json={"edited_params": edited})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["approval"]["status"] == "edited", body
    assert body["approval"]["edited_params"] == edited, body
    assert body["result"] is not None, body
    print(f"  approved-with-edits, status=edited, result msg present: {'message' in body['result']}")


def test_reject_with_reason():
    r = client.post(f"/approvals/{FORECAST_ID}/reject", json={"reason": "management declined 30-day forecast"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approval"]["status"] == "rejected", body
    assert body["approval"]["rejection_reason"] == "management declined 30-day forecast", body
    print(f"  rejected with reason: {body['approval']['rejection_reason']}")


def test_history_contains_resolved():
    r = client.get("/approvals/history?limit=50")
    assert r.status_code == 200, r.text
    ids = [a["approval_id"] for a in r.json()["approvals"]]
    assert QUEUED_ID in ids, f"{QUEUED_ID} not in history {ids}"
    assert FORECAST_ID in ids
    print(f"  history has {len(ids)} resolved entries")


def test_approve_already_resolved_fails():
    r = client.post(f"/approvals/{QUEUED_ID}/approve", json={})
    assert r.status_code == 400, r.text
    print("  approving resolved entry correctly returns 400")


def test_approve_unknown_fails():
    r = client.post("/approvals/APR-NOPE/approve", json={})
    assert r.status_code == 404, r.text
    print("  approving unknown id correctly returns 404")


if __name__ == "__main__":
    QUEUED_ID = None
    FORECAST_ID = None
    run_test("non-approval tool executes directly", test_non_approval_tool_executes_directly)
    run_test("approval tool is queued (flag)", test_approval_tool_queued)
    run_test("approval tool is queued (server-side list)", test_approval_tool_queued_even_without_flag)
    run_test("pending list contains queued entries", test_pending_list)
    run_test("approve executes tool (no edits)", test_approve_without_edits)
    run_test("approve with edited params -> edited", test_approve_with_edited_params)
    run_test("reject with reason", test_reject_with_reason)
    run_test("history contains resolved entries", test_history_contains_resolved)
    run_test("resolved approval cannot be re-approved", test_approve_already_resolved_fails)
    run_test("unknown approval returns 404", test_approve_unknown_fails)
    print("\nALL TESTS PASSED")
