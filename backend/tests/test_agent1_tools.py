"""Test Agent 1 (Daily Entry) tools against the live backend."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

tests = {
    "check_cash_position": {"as_of_date": "2026-07-31", "account_id": "ALL"},
    "check_bank_transactions": {"from_date": "2026-07-01", "to_date": "2026-07-31"},
    "manage_petty_cash": {"action": "status", "fund_id": "PC-001"},
}

for tool, params in tests.items():
    r = client.post("/tools/execute", json={"tool_name": tool, "params": params})
    d = r.json()
    if d.get("success"):
        res = d["result"]
        if tool == "check_cash_position":
            print(f"{tool}: closing={res.get('closing_balance')}, name={res.get('account_name')}")
        elif tool == "check_bank_transactions":
            txns = res.get("transactions", [])
            print(f"{tool}: txns={len(txns)}")
            for t in txns[:3]:
                print(f"    - {t.get('transaction_id')}: {t.get('description')} {t.get('amount')} {t.get('type')}")
        elif tool == "manage_petty_cash":
            print(f"{tool}: balance={res.get('current_balance')}, msg={str(res.get('message',''))[:50]}")
    else:
        print(f"{tool}: ERROR {str(d.get('error',''))[:100]}")
