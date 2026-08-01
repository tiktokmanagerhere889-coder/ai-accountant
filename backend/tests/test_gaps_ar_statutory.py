"""Verify 2 untested gaps:
1. AR side: seed customer invoice, test get_ar_subledger, get_ar_aging_report, reconcile_customer_statement
2. maintain_statutory_registers: add + view flow
Run: cd backend && python verify_gaps.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app
from db.database import SessionLocal
from sqlalchemy import text

client = TestClient(app)

def seed():
    db = SessionLocal()
    try:
        for t in ["statutory_registers","flagged_entries","audit_log","reconciliation_matches","reconciliation_runs","journal_entries","cash_position","chart_of_accounts","contacts"]:
            db.execute(text(f"DELETE FROM {t}"))
        db.commit()

        # Contact (customer)
        db.execute(text("INSERT INTO contacts (contact_id,contact_name,contact_type,phone,email,address,tax_id,related_party) VALUES ('CONT-002','RetailMart Karachi','customer','021-34920002','orders@retailmart.pk','Karachi','NTN-2345678-1',false)"))
        db.commit()

        # Chart of accounts (AR + revenue)
        for code, name, atype in [("1200-Receivables","Accounts Receivable","asset"),("4000-Revenue","Sales Revenue","revenue"),("1100-Bank","Bank","asset")]:
            db.execute(text("INSERT INTO chart_of_accounts (account_code,account_name,account_type,is_active) VALUES (:c,:n,:t,1)"), {"c":code,"n":name,"t":atype})
        db.commit()

        # AR invoice journal entry: debit 1200-AR, credit 4000-Revenue, ref=CONT-002
        # Invoice date 2026-07-10 → as_of 2026-07-31 → 21 days old → current (0-30) bucket
        db.execute(text("""
            INSERT INTO journal_entries (entry_id,description,posted_date,debit_account,debit_amount,credit_account,credit_amount,status,reference)
            VALUES ('JE-AR-001','Invoice INV-101 to RetailMart','2026-07-10'::date,'1200-Receivables',150000,'4000-Revenue',150000,'posted','CONT-002')
        """))
        # Second, older AR invoice → 2026-05-01 → 91 days → 90+ bucket
        db.execute(text("""
            INSERT INTO journal_entries (entry_id,description,posted_date,debit_account,debit_amount,credit_account,credit_amount,status,reference)
            VALUES ('JE-AR-002','Invoice INV-050 to RetailMart','2026-05-01'::date,'1200-Receivables',50000,'4000-Revenue',50000,'posted','CONT-002')
        """))
        db.commit()
        print("  Seeded: CONT-002 customer, 2 AR invoices (150k on 07-10, 50k on 05-01)")
    finally:
        db.close()

def test_ar_subledger():
    print("\n=== TEST 1: get_ar_subledger (non-empty) ===")
    r = client.post("/tools/execute", json={"tool_name":"get_ar_subledger","params":{"from_date":"2026-01-01","to_date":"2026-12-31"}})
    d = r.json()
    if not d.get("success"):
        print(f"  FAIL: {d.get('error')}")
        return False
    res = d["result"]
    entries = res.get("entries", [])
    total = res.get("total_outstanding")
    print(f"  entries: {len(entries)}")
    for e in entries:
        print(f"    - {e['customer_name']}: invoice {e['invoice_amount']}, outstanding {e['outstanding_balance']}, due {e['due_date']}")
    print(f"  total_outstanding: {total}")
    ok = len(entries) == 1 and str(total) == "200000.00"
    print(f"  {'PASS' if ok else 'FAIL'} (expect 1 entry, total 200000.00)")
    return ok

def test_ar_aging():
    print("\n=== TEST 2: get_ar_aging_report (buckets) ===")
    r = client.post("/tools/execute", json={"tool_name":"get_ar_aging_report","params":{"as_of_date":"2026-07-31"}})
    d = r.json()
    if not d.get("success"):
        print(f"  FAIL: {d.get('error')}")
        return False
    res = d["result"]
    print(f"  buckets: {res.get('buckets')}")
    for det in res.get("customer_details", []):
        print(f"    - {det['customer_name']}: current={det['current']}, past_30={det['past_30']}, past_60={det['past_60']}, past_90={det['past_90']}, total={det['total_outstanding']}")
    print(f"  total_outstanding: {res.get('total_outstanding')}")
    # 07-10 invoice → 21 days → current; 05-01 invoice → 91 days → past_90
    def d(x): return float(x or 0)
    ok = d(res.get("total_outstanding")) == 200000.00
    if res.get("customer_details"):
        det = res["customer_details"][0]
        ok = ok and d(det.get("current")) == 150000.00 and d(det.get("past_90")) == 50000.00
    print(f"  {'PASS' if ok else 'FAIL'} (expect current=150k, past_90=50k, total=200k)")
    return ok

def test_reconcile_customer():
    print("\n=== TEST 3: reconcile_customer_statement (with statement lines) ===")
    # Statement matches 07-10 invoice exactly, misses 05-01 invoice
    statement_lines = [
        {"reference":"CONT-002","date":"2026-07-10","amount":"150000","description":"INV-101"},
    ]
    r = client.post("/tools/execute", json={"tool_name":"reconcile_customer_statement","params":{
        "customer_contact_id":"CONT-002","statement_date":"2026-07-31",
        "from_date":"2026-01-01","to_date":"2026-12-31","statement_lines":statement_lines
    },"bypass_approval":True})
    d = r.json()
    if not d.get("success"):
        print(f"  FAIL: {d.get('error')}")
        return False
    res = d["result"]
    matches = res.get("matches", [])
    diffs = res.get("differences", [])
    print(f"  matches: {len(matches)}")
    for m in matches:
        print(f"    - ref={m.get('statement_ref')} je={m.get('journal_entry_id')} amt={m.get('amount_match')} date={m.get('date_match')} status={m.get('status')}")
    print(f"  differences: {len(diffs)}")
    for diff in diffs:
        print(f"    - {diff.get('reference')}: internal={diff.get('internal_amount')}, reason={diff.get('reason')}")
    print(f"  total_difference: {res.get('total_difference')}")
    # Expect: 1 matched (150k), 1 difference (05-01 invoice = -50k), total_difference = 150k-200k = -50k
    ok = len(matches) == 1 and matches[0].get("status") == "matched" and len(diffs) == 1
    ok = ok and float(res.get("total_difference") or 0) == -50000.00
    print(f"  {'PASS' if ok else 'FAIL'} (expect 1 match status=matched, 1 diff -50k)")
    return ok

def test_statutory_add():
    print("\n=== TEST 4: maintain_statutory_registers add + view ===")
    # ADD a director
    r = client.post("/tools/execute", json={"tool_name":"maintain_statutory_registers","params":{
        "action":"add","register_type":"directors","entry_date":"2026-07-15",
        "description":"Appointed Hassan Khan as Director","reference_number":"REG-DIR-2026-001","amount":"0"
    },"bypass_approval":True})
    d = r.json()
    if not d.get("success"):
        print(f"  ADD FAILED: {d.get('error')}")
        return False
    add_res = d["result"]
    reg_id = add_res.get("register_id")
    print(f"  ADD: register_id={reg_id}, status={add_res.get('status')}, msg={add_res.get('message')}")
    ok = bool(reg_id) and add_res.get("action_performed") == "add"

    # VIEW it back
    r = client.post("/tools/execute", json={"tool_name":"maintain_statutory_registers","params":{
        "action":"view","register_type":"directors","entry_date":"2026-07-15","description":"view"
    },"bypass_approval":True})
    d = r.json()
    if not d.get("success"):
        print(f"  VIEW FAILED: {d.get('error')}")
        return False
    view_res = d["result"]
    print(f"  VIEW: register_id={view_res.get('register_id')}, desc={view_res.get('description')}, status={view_res.get('status')}")
    ok = ok and view_res.get("status") != "empty" and "Hassan Khan" in str(view_res.get("description"))
    print(f"  {'PASS' if ok else 'FAIL'} (add created + view returns it)")
    return ok

if __name__ == "__main__":
    print("=" * 60)
    print("VERIFY 2 UNTESTED GAPS")
    print("=" * 60)
    seed()
    ok1 = test_ar_subledger()
    ok2 = test_ar_aging()
    ok3 = test_reconcile_customer()
    ok4 = test_statutory_add()
    print(f"\n{'='*60}")
    print(f"AR_Subledger={'PASS' if ok1 else 'FAIL'} | AR_Aging={'PASS' if ok2 else 'FAIL'} | Reconcile_Customer={'PASS' if ok3 else 'FAIL'} | Statutory_add/view={'PASS' if ok4 else 'FAIL'}")
